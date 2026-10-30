# FORGETGRAPH: implementation specification

## Requirements

Implement a deterministic, local-only deletion orchestrator for a synthetic
Ridge-regression pipeline. A deletion request must identify the affected
artifacts from SQLite lineage and process its recorded operations in this
order: remove the source record, recompute engineered features, invalidate
prediction cache entries, and replace the model. SQLite persists source
records, artifact graph and user lineage, tombstones, workflow/step states,
model snapshots, and audit events. Repeated deletion requests are no-ops;
managed ingestion rejects tombstoned identifiers. A Streamlit dashboard
exposes the graph, deletion and failure-injection controls, progress,
counts, cache invalidation, model comparisons, tolerances, verification,
and audit history.

The replacement model's execution status is distinct from its verification
status. Verification checks deleted-user absence from all applicable data
artifacts, feature/source consistency, and replacement-model agreement with
an independently implemented reference fit. It also checks that the new model
differs from the saved old model.

The dashboard presents an overview and lineage graph, an impact preview and
deletion workspace, independent verification evidence, a security-controls
matrix that explicitly identifies production gaps, and an audit-event view.

## Data model

- `source_records`: SHA-256 user key and synthetic numeric/categorical fields.
- `feature_rows`: keyed by user hash; includes raw numeric features and a
  region-level mean feature recomputed across the retained population.
- `prediction_cache`: one prediction per user hash; invalidated as a whole
  because both the regional feature and model can change.
- `models`: serialized numeric scaler/model parameters and generation.
- `artifacts`, `artifact_dependencies`: durable graph nodes and directed
  lineage edges.
- `artifact_user_lineage`: versioned user-to-artifact associations, retained
  historically and marked active/inactive as artifact contents change.
- `tombstones`: durable SHA-256 identifiers of deletion requests.
- `deletion_workflows`, `workflow_steps`: execution state, separate
  verification state, affected artifact snapshot, old-model snapshot, ordered
  idempotent operations, and effect counts.
- `audit_events`: append-only operational events with timestamps and details.

SQLite transactions make each data mutation and its step-completion update
atomic. A process restart can resume any non-completed operation. Each handler
is also safe to run again if a process stopped before its transaction
committed.

## Graph and affected-artifact discovery

The persisted graph is:

```text
source_records -> engineered_features -> ridge_model -> prediction_cache
                              \----------------------> prediction_cache
```

For a requested identifier, the system hashes the identifier and queries
active `artifact_user_lineage` rows. The returned artifact IDs are the source
of truth for both the reported impact and the workflow operations. An
`artifact_operations` table associates each artifact with its operation and
order; workflow steps are selected from this relation rather than inferred
from a hard-coded affected-artifact list.

## Workflow algorithm

1. Hash the identifier and check `tombstones`. If present, return
   `already_deleted` without writing any row or event.
2. Reject an identifier that is not present in active source records without
   creating a tombstone or workflow. In one transaction, insert the tombstone,
   capture the affected artifact IDs and old-model snapshot, create a workflow,
   and create its ordered steps.
3. Before each pending step, persist `RUNNING`. In a transaction, apply its
   idempotent handler and mark it `COMPLETED`. On an ordinary handler error,
   persist `FAILED` and mark execution `FAILED`; verification remains
   independently `NOT_RUN`.
4. An injected crash after a selected completed step leaves the workflow
   resumable. `resume_workflow` skips completed steps and finishes pending
   ones without duplicating effects.
5. Once all operations complete, set execution `COMPLETED`, independently
   verify the result, and persist `PASSED` or `FAILED` without changing the
   execution status.
6. Managed ingestion checks tombstones and refuses a deleted identifier
   before any database write.

## Features, model, and verification

The committed CSV contains 700 seeded synthetic users in four regions.
Feature engineering computes a mean `signal_a` for each region and joins it
to every user in that region, ensuring that deletion changes another user's
feature. A `StandardScaler` is fitted on retained feature rows only, then a
Ridge model is fitted with `alpha=1.0` and `random_seed=42`.

The orchestrator's trainer and `reference.py` are separate implementations.
The reference module imports no orchestrator training code and independently
fits its own scaler and Ridge model on the same retained features, alpha, and
seed. Verification compares replacement and reference coefficients,
intercept, and predictions with `rtol=1e-8` and `atol=1e-10`. It reports each
comparison, the configured tolerances, and whether the replacement differs
from the previous model. It also fails on deleted-ID reappearance or
inconsistent source/feature membership.

## Assumptions

- There are no additional input schemas, output files, APIs, credentials, or
  external services required beyond the root `PS09.md`.
- The CSV is wholly synthetic and generated deterministically for this demo.
- User identifiers are hashed in SQLite, lineage, and tombstones; no
  real-person data is involved.
- The cache is invalidated in full because model replacement can affect every
  prediction, while feature recomputation can affect every member of a region.
- A simulated crash is injected only after a step's committed transaction;
  ordinary exceptions exercise the persisted `FAILED` state.
- The project is self-contained under `ps09_forgetgraph/`; the existing
  repository-level virtual environment and all other problem materials are
  left untouched.

## Test plan

Pytest covers lineage-based artifact identification; source, feature, and
cache deletion; correct aggregate recomputation for retained users;
independent-reference numerical agreement; old/new model difference; tamper
and re-insertion verification failures; status independence; repeated-request
no-op behavior; ingestion rejection; and crash/restart idempotency.
Dashboard startup is checked separately from the unit suite.
