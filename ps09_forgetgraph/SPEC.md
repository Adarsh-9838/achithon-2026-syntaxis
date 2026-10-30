# FORGETGRAPH: implementation specification

## Requirements

Implement a deterministic, local-only deletion orchestrator for a synthetic
Ridge-regression pipeline. A deletion request must identify the affected
artifacts from SQLite lineage and process its recorded operations in this
order: remove the source record, recompute engineered features, invalidate
prediction cache entries, and replace the model. SQLite persists source
records, artifact graph and user lineage, tombstones, workflow/step states,
model snapshots, verification scorecards, deletion certificates and revisions,
and audit events. Repeated deletion requests are no-ops;
managed ingestion rejects tombstoned identifiers. A Streamlit dashboard
exposes the graph, deletion and failure-injection controls, progress,
counts, cache invalidation, model comparisons, tolerances, verification,
audit history, readable deletion certificates, and a Model Verification
Scorecard.

The replacement model's execution status is distinct from its verification
status. Verification checks deleted-user absence from all applicable data
artifacts, feature/source consistency, and replacement-model agreement with
an independently implemented reference fit. Old-to-replacement model
differences are reported as evidence, but are not a required pass condition.

The dashboard presents an overview and lineage graph, an impact preview and
deletion workspace, independent verification evidence, a security-controls
matrix that explicitly identifies production gaps, an audit-event view, a
Model Verification Scorecard, and a certificate viewer with downloadable
machine-readable JSON.

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
  idempotent operations, effect counts, and a snapshot of the verification
  configuration (including numerical tolerances) used for that request.
  Workflow steps also persist started/completed timestamps and failure details
  for certificate evidence.
- `verification_attempts`: a durable record for each verification run,
  including start/completion time, result or exception, and attempt number.
  The existing `report_json` is the persisted scorecard evidence and is reused
  by certificate generation rather than copied into another scorecard table.
- `deletion_certificates`: one unique certificate identity per accepted
  deletion workflow, linked one-to-one to `deletion_workflows`; stores the
  current certificate lifecycle status, latest canonical JSON, revision
  number, and payload hash.
- `deletion_certificate_revisions`: append-only canonical JSON snapshots and
  payload hashes for certificate lifecycle changes, linked to the parent
  certificate. New revisions preserve earlier states rather than overwriting
  certificate history.
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
   execution status. Every attempt has a persisted start, outcome, and audit
   event. Exceptions and failed comparisons leave execution completed and
   verification retryable. A retry marks a stranded `RUNNING` attempt failed
   before starting a new numbered attempt. Update the linked certificate and
   append a certificate revision after each persisted workflow-stage or
   verification outcome; a fully verified state is permitted only when
   execution is `COMPLETED` and verification is `PASSED`.
6. Managed ingestion checks tombstones and refuses a deleted identifier
   before any database write.
7. Rejected unknown-ID submissions do not create workflows or deletion
   certificates. A repeated request for a tombstoned ID remains a no-op and
   returns its existing workflow/certificate reference when available; it
   does not issue another certificate for the same deletion.

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
intercept, and predictions using the workflow's captured `rtol` and `atol`
(defaults `1e-8` and `1e-10`). Feature ordering, preprocessing definition,
fixed training settings, and deterministic random settings must be identical;
the scaler is fitted only on retained rows. Tolerance values are captured
before execution starts so changing configuration later cannot change the
evaluation of an existing request.

Each verification attempt creates a Model Verification Scorecard. It
individually reports coefficient agreement, intercept agreement, and
prediction agreement under the captured tolerances; records maximum absolute
coefficient difference, absolute intercept difference, maximum absolute
prediction difference, and mean absolute prediction difference; and reports
overall PASS only if all required data-integrity and model-agreement checks
pass. Each scorecard is stored in SQLite with its attempt and evidence hashes.
The old-model difference remains informational and is not a pass condition.
Verification also fails on a missing tombstone, deleted-ID reappearance, or
inconsistent source/feature membership.

Scorecard evidence is limited to the retained synthetic dataset, tracked local
artifact tables, and this implementation's checks. Numerical agreement is
not cryptographic proof of universal erasure: it does not prove deletion from
untracked or external systems, every possible copy, or backups.

## Proof-carrying deletion certificates

Every accepted deletion workflow receives a globally unique certificate ID
and a certificate associated one-to-one with its original deletion request.
Certificate creation begins with the workflow and is updated as persisted
execution and verification state changes. Each update appends a numbered,
immutable certificate revision; current state points to the latest revision
without replacing revision history.

The downloadable JSON certificate and readable dashboard view contain at
minimum:

- schema version, certificate ID, original request/deletion ID, request time,
  certificate revision, and lifecycle status;
- deleted record IDs as SHA-256 pseudonymous identifiers (never raw IDs) and
  affected artifact IDs captured from recorded lineage;
- every ordered execution-stage name, status, effect count, available start
  and completion timestamps, and failure details when applicable;
- execution and verification status as separate values;
- old and replacement model IDs/generations when available;
- verification attempt ID/number, individual checks, overall result,
  captured tolerances, scorecard measurements, and evidence hashes when
  available;
- request, execution, verification, and certificate issue/update timestamps.
  Values that do not yet exist are explicitly null or not-run, never
  success-shaped defaults.

Certificate lifecycle values are `INCOMPLETE`, `FAILED`, and `VERIFIED`.
`INCOMPLETE` means required execution or verification evidence is not yet
available; `FAILED` means execution failed or a completed verification
comparison failed; `VERIFIED` means execution is complete, verification passed,
and the required stage timestamps and comparison evidence are present. A
certificate is never marked `VERIFIED` unless execution is `COMPLETED` and
its verification has `PASSED`. Verification alone cannot repair failed
execution. A failed verification creates a non-verified revision; a successful
retry creates a later revision without removing failed-attempt or prior
certificate evidence.

Evidence hashes are SHA-256 digests over canonical UTF-8 JSON representations
of the scorecard and certificate payload; each payload hash is computed with
its own hash field excluded. These hashes support integrity/change detection
for stored evidence, but are not digital signatures, proof of authorship, or
proof of universal data erasure. Certificates and revisions are retained in
SQLite and share the workflow/tombstone database-reset boundary.

## API contract

The application is a local Python orchestrator with a Streamlit interface,
not currently an HTTP service. These stable service operations define its
application API and any later transport adapter. They must call the same
orchestrator and persistence layer rather than duplicating business logic:

| Operation | Inputs | Result / behavior |
|---|---|---|
| `request_deletion(user_id, fail_after_step=None)` | User ID and optional demo failure stage | Creates and returns a workflow and certificate reference; repeated tombstoned ID is a no-op with the existing reference when available; unknown IDs are rejected. |
| `resume_workflow(deletion_id)` | Existing workflow ID | Resumes persisted execution idempotently and updates certificate revisions. |
| `verify_deletion(deletion_id)` | Execution-completed workflow ID | Creates a numbered independent attempt and scorecard; retryable after failure without changing execution status. |
| `get_workflow(deletion_id)` | Workflow ID | Returns execution state, separate verification state, ordered stages, lineage impact, and certificate ID/status. |
| `get_deletion_certificate(deletion_id)` | Workflow ID | Returns the latest machine-readable JSON certificate and status. |
| `list_deletion_certificates(limit=100)` | Optional maximum count | Returns persisted current certificates for dashboard history. |
| `list_deletion_certificate_revisions(deletion_id)` | Workflow ID | Returns ordered immutable certificate revisions. |
| `validate_deletion_certificate(deletion_id, revision_number=None)` | Workflow ID and optional revision | Recomputes canonical JSON SHA-256 integrity hash for current or selected stored revision. |

There is no HTTP server in this project. The operations above are the
orchestrator's Python API; they must preserve status separation, idempotency,
privacy, and error semantics.

## Dashboard components

- **Deletion workflow:** distinguishes a new request from saved history,
  shows Waiting/PENDING before a request is run, then stage progress and
  separate execution and verification status.
- **Model Verification Scorecard:** shows coefficient, intercept, and
  prediction check outcomes; captured tolerances; maximum and mean absolute
  prediction differences; other measured deltas; evidence hashes; and a
  prominent overall PASS/FAIL that cannot override execution status.
- **Deletion certificate:** renders the latest certificate status and
  evidence, provides JSON download, and allows explicit selection of earlier
  revisions. Pending and failed certificates cannot be styled/described as
  fully verified.
- **Audit trail:** links request, stage, attempt, scorecard, and certificate
  revision events by workflow/certificate ID without exposing raw identifiers.

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

- The proof-carrying certificate and scorecard are local application
  deliverables requested as an extension to the root `PS09.md`. The route
  contract is defined here; the current project remains a local Python/
  Streamlit application and does not imply a deployed HTTP server,
  credentials, or external services.
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
from the unit suite. Additional tests cover scorecard calculations and
tolerance snapshotting; certificate creation after successful verification;
certificate contents, JSON serialization, evidence hashes, and revision
retention; and ensuring failed execution or verification never yields a fully
verified certificate. Dashboard tests cover pending state on a new visit,
scorecard/certificate presentation, failure labeling, history selection, and
retry controls.
