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
an independently implemented reference fit. Old-to-replacement model
differences are reported as evidence, but are not a required pass condition.

The dashboard presents an overview and lineage graph, an impact preview and
deletion workspace, independent verification evidence, a security-controls
matrix that explicitly identifies production gaps, an evidence-certificate area, and an audit-event view.

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
  idempotent operations, effect counts, and per-stage start/outcome times.
- `verification_attempts`: a durable record for each verification run,
  including start/completion time, result or exception, and attempt number.
- `audit_events`: append-only operational events with timestamps and details.
- `deletion_certificates`: one stable certificate identity and latest
  integrity-sealed JSON snapshot per accepted deletion request.
- `deletion_certificate_history`: immutable prior certificate snapshots,
  including failed and incomplete results, retained when a retry records new
  evidence.

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
   execution status. Every attempt has a persisted start, outcome, and audit
   event. Exceptions and failed comparisons leave execution completed and
   verification retryable. A retry marks a stranded `RUNNING` attempt failed
   before starting a new numbered attempt.
6. Managed ingestion checks tombstones and refuses a deleted identifier
   before any database write.

## Deletion evidence certificates

Each accepted request receives one stable certificate ID and a structured
JSON certificate, initially marked `INCOMPLETE`. The certificate is refreshed
from the persisted workflow, step, verification-attempt, and audit records as
real outcomes become available. Every prior certificate snapshot is retained
in `deletion_certificate_history`; retries update the same request's current
certificate rather than creating duplicate certificate identities or
discarding earlier failures.

The JSON contains the request ID and time, SHA-256 source-record identifier,
lineage-derived affected artifact IDs, tombstone time, execution status and
per-stage outcomes/effect counts/start and completion timestamps, and a
separate verification section. Independent verification includes replacement
and reference model fingerprints, coefficient/intercept comparisons, maximum
and mean absolute prediction deltas, the exact configured `rtol`/`atol`, each
attempt's timestamps/status/report/error, and its final outcome. Missing
evidence or a running workflow remains `INCOMPLETE`; failed execution,
verification, or integrity validation is `FAILED`; only complete passing
execution and independent verification evidence is `VERIFIED`.

The integrity digest is SHA-256 over the UTF-8 bytes of canonical JSON with
sorted keys, compact separators, and the complete `integrity` object omitted.
The exported JSON includes the algorithm and canonicalization rule so a
consumer can recompute the digest. This detects accidental or deliberate
document changes when the expected digest is trusted; it is not a digital
signature and does not prove permanent or universal erasure. Dashboard
history shows retained certificate revisions, distinct execution and
verification evidence, integrity status, and a JSON download.

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
comparison, the configured tolerances, maximum absolute coefficient,
intercept, and prediction differences, mean absolute prediction difference,
content-derived replacement/reference model IDs, and whether the replacement
differs from the previous model. The old-model difference is evidence only. It also
fails on a missing tombstone, deleted-ID reappearance, or inconsistent
source/feature membership.

## Database reset and concurrency boundaries

Tombstones and workflow history are stored only in the SQLite database.
Deleting that database and constructing a new orchestrator seeds all 700 IDs
from the original CSV again; previous tombstones do not survive. Reset
semantics are tested using a temporary database only. Do not reset the
application database when persistent tombstone behavior is being demonstrated.

The prototype does not implement a workflow-level lock. It is explicitly
single-process and single-user; overlapping deletion, resume, or verification
requests are unsupported. Individual state mutations use SQLite transactions,
but that is not a concurrency guarantee for an entire workflow.

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
- The demo is single-process/single-user; cross-process locking and
  distributed coordination are outside this scope.
- The project is self-contained under `ps09_forgetgraph/`; the existing
  repository-level virtual environment and all other problem materials are
  left untouched.

## Test plan

Pytest covers lineage-based artifact identification; source, feature, and
cache deletion; correct aggregate recomputation for retained users;
independent-reference numerical agreement; old-model comparison as
non-mandatory evidence; tamper and re-insertion verification failures;
verification exceptions, explicit retries, abandoned-attempt recovery, and
audit history; passing verification when old and replacement models are
equal; status independence; repeated-request no-op behavior; ingestion
rejection; ordinary failure and resume at every workflow step; crash/restart
idempotency; and database reinitialization from the source CSV. Dashboard
sections, including the guided demo and retry control, are checked separately
from the unit suite. Certificate tests cover successful, failed, incomplete,
and tampered evidence, canonical hash validation, retry history preservation,
and one stable certificate identity per deletion request.
