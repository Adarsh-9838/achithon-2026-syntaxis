# FORGETGRAPH (PS09)

A local, deterministic prototype for dependency-aware deletion in a synthetic
Ridge-regression pipeline. It records source, engineered-feature, prediction
cache, and model lineage in SQLite; persists execution steps and independent
verification attempts; blocks managed re-ingestion of tombstoned IDs; and
provides a guided Streamlit demonstration.

## Setup

Use Python 3.10 or later. No API keys or remote services are required. If
PowerShell script activation is disabled, you can invoke the project interpreter
directly without activating the virtual environment.

```powershell
cd ps09_forgetgraph
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In an offline environment, make the required package wheels available before
installing; the running application itself has no network dependency.

## Run and test

Run these commands from `ps09_forgetgraph` after activation:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
pytest -q
```

If script activation is blocked by the local PowerShell execution policy, use
the interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m pytest -q
```

The database `data/forgetgraph.sqlite` is initialized from the committed
700-user `data/synthetic_users.csv` on first run. IDs are `user-0000` through
`user-0699`. A new database starts with 700 source rows, 700 feature rows, and
700 cached predictions.

## Judge demo script

1. Open **Guided demo** and note the before counts and the selected user's
   impacted artifacts, which are read from SQLite lineage.
2. Select an active synthetic ID and click **Run guided deletion**. Expect the
   stages to complete in order: remove source, recompute features, invalidate
   prediction cache, replace the Ridge model. In a fresh database the source
   and feature counts become 699, the cache becomes 0, and a tombstone is
   recorded. Regional aggregate features for retained users are recomputed.
3. Review the separately labeled execution and verification statuses, counts,
   old/replacement/reference model parameters, numerical tolerances, and
   measured maximum absolute differences.
4. Click **Test managed re-ingestion guard**. The managed ingestion API should
   reject the deleted ID, and database counts should stay unchanged.
5. In **Verification & security**, inspect the persisted attempt and audit
   history. If execution completed but verification failed, use **Retry
   verification** after correcting the issue. Every retry is recorded.
6. To demonstrate execution recovery, use **Deletion workflow** and enable
   failure injection. Resume the resulting interrupted workflow; already
   completed steps are not repeated.
7. Open **Evidence Certificates** to select a request, review execution and
   independent verification evidence separately, download its JSON certificate,
   and inspect revisions. Failed and incomplete snapshots remain in history
   after a retry; the request retains one stable certificate ID.

The app also supports a typed deletion request and a lineage impact preview.
Unknown IDs are rejected without creating a workflow or tombstone. Repeating a
request for a tombstoned ID returns `already deleted` without changing the
database.

## Design and verification

- The artifact graph and versioned user-to-artifact lineage are persisted in
  SQLite. Affected artifact IDs and ordered operations are derived from those
  records, rather than a hard-coded affected-artifact list.
- Deletion removes the source row, recomputes all engineered features,
  invalidates the full prediction cache, and replaces the model. The step
  mutation and completion record commit atomically. Completed steps are
  skipped on resume.
- Source IDs, lineage keys, and tombstones use SHA-256 hashes. Managed
  ingestion checks tombstones before writing. This guard applies only to
  ingestion through this application.
- `training.py` fits the replacement model. `reference.py` independently fits
  its scaler and Ridge model and does not import the replacement trainer.
  Both refit preprocessing on retained rows, with Ridge `alpha=1.0` and seed
  `42`.
- `config.json` declares `rtol=1e-8` and `atol=1e-10`. Verification compares
  replacement/reference coefficients, intercepts, and predictions under those
  tolerances. It reports old-to-replacement differences as evidence; a model
  does **not** have to differ from the old model to pass independent-reference
  verification.
- Execution (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`) and verification
  (`NOT_RUN`, `RUNNING`, `PASSED`, `FAILED`) are separate persisted statuses.
  Verification attempts and their audit events are retained independently.
- Each accepted request has one stable deletion-certificate ID. Its JSON
  records the request time, hashed source-record ID, lineage-derived affected
  artifact IDs, per-stage outcomes/counts/timestamps, and distinct execution
  and independent-verification evidence. Verification includes content-derived
  replacement/reference model IDs, coefficient/intercept comparisons, maximum
  and mean absolute prediction deltas, exact configured tolerances, and
  attempt outcomes.
- Certificates use SHA-256 over canonical UTF-8 JSON (sorted keys, compact
  separators, excluding the `integrity` object). Prior failed or incomplete
  certificate snapshots are retained in request history as retries update the
  same certificate. This hash detects document changes when the expected hash
  is trusted; it is not a digital signature or proof of permanent or universal
  erasure.

## Database reset behavior

Tombstones and workflow history exist only in the SQLite database. Deleting or
replacing `data/forgetgraph.sqlite` and starting the app again rebuilds state
from the original CSV; this **reintroduces previously deleted synthetic IDs**
and removes their tombstones. Do not treat database deletion as a safe reset
when demonstrating persistent erasure. The reset test uses only a temporary
database and confirms this behavior; it never deletes the application's
database or its backups.

## Tests

The pytest suite covers lineage-based artifact identification; source, feature,
and cache effects; aggregate recomputation; independent numerical agreement;
old-model comparison as non-mandatory evidence; tampering and re-ingestion
verification failures; independent statuses; verification exceptions,
retries, interrupted attempts, and audit events; repeated-request no-op;
tombstone ingestion prevention; database reinitialization semantics; ordinary
failures at every execution stage; and crash/resume without duplicate effects.
Certificate tests cover successful, failed, incomplete, and tampered JSON
certificates, deterministic integrity validation, retained retry history, and
idempotent certificate identity. Streamlit AppTest renders every dashboard
section, including Evidence Certificates.

## Limitations

This is a local synthetic demonstration, not a production erasure service.
It has no authentication, external data connectors, distributed coordination,
or protection against bypassing managed ingestion. The current workflow
orchestrator is **single-process and single-user**: do not run concurrent
deletion requests or simultaneous resume/verification operations. SQLite
transactions make individual mutations durable, but there is no workflow-level
concurrency lock.

The cache is invalidated in full because model replacement can affect any
prediction. A downstream consumer would need to repopulate it. Database
reinitialization is a destructive reset of the registry and can restore IDs
from the source CSV; tombstones do not survive deletion of the database.

## AI assistance

An AI coding agent was used to translate PS09 into a testable design, implement
the orchestrator and dashboard, and prepare verification tests and
documentation. The team should review the code, exercise the guided demo, and
confirm the submission behavior before judging.
