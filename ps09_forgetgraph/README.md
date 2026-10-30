# FORGETGRAPH (PS09)

A local, deterministic prototype for dependency-aware deletion in a synthetic
Ridge-regression pipeline. It records source, engineered-feature, prediction
cache, and model lineage in SQLite; persists execution steps and independent
verification attempts; blocks managed re-ingestion of tombstoned IDs; and
provides a Streamlit demonstration with hash-validated Deletion Evidence
Certificates.

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

The app also supports a typed deletion request and a lineage impact preview.
Unknown IDs are rejected without creating a workflow or tombstone. Repeating a
request for a tombstoned ID returns `already deleted` without changing the
database.

On a fresh dashboard visit, the deletion workflow and verification views start
in **Waiting / Not checked yet** rather than selecting an older result. Previous
requests remain saved and can be reviewed explicitly under **Saved deletion
history**. Each saved-history option and its detail view identify the deleted
synthetic user ID as well as execution and verification statuses. The ID is
resolved against the committed synthetic seed CSV; for IDs outside that
dataset, the app displays an unavailable-ID note and a short hash reference
instead of storing or exposing a raw ID in the certificate. Submitting a
previously deleted ID displays a notification and does not create another
workflow or change database contents.

## Deletion Evidence Certificates

Open **Evidence Certificates** to select a deletion request and certificate
revision. The view separates persisted execution stages from independent
verification evidence, labels the certificate **VERIFIED**, **FAILED**, or
**INCOMPLETE**, and provides both a branded receipt-style image and the
machine-readable JSON certificate. The receipt always displays FORGETGRAPH at
the top. Download the image as SVG to print or share it, or expand **View
receipt image** for an inline, scrollable preview; the preview is collapsed by
default to keep the page compact. Download JSON when you need the complete
structured evidence. The SHA-256 integrity check
validates that the stored certificate payload matches its recorded hash.

Certificates are generated and revised from the existing workflow steps,
verification report, and audit-backed timestamps. A request has one stable
certificate ID; repeated requests for a tombstoned user return the existing
certificate reference and do not create a duplicate. Old databases are
upgraded with certificate tables and historical certificate snapshots. If an
older workflow lacks required timestamps or verification evidence, its
certificate is marked **INCOMPLETE**, not retroactively called verified.

The certificate's deleted-record identifier is a SHA-256 pseudonymous hash,
not the raw synthetic ID. Hash validation detects accidental or direct
payload changes relative to the stored digest, but it is not a digital
signature and does **not** independently prove permanent erasure from every
copy, backup, or external system.

### Certificate demonstration

1. In **Deletion workflow**, enter an active synthetic ID and select **Run
   deletion**. The orchestrator records the request, stage results, timestamps,
   and model generation while running the existing workflow.
2. Open **Evidence Certificates** and select that request. A complete,
   successfully independently verified request is **VERIFIED**. An execution
   or comparison failure is **FAILED**; missing evidence is **INCOMPLETE**.
3. Review the separate execution and verification evidence. Select **Download
   receipt image (SVG)** to save the FORGETGRAPH-branded receipt, or expand
   **View receipt image** for a scrollable inline preview. Select **Download
   certificate JSON** for the complete machine-readable certificate.
4. The SHA-256 integrity check validates the selected current or historical
   certificate revision against its stored hash.
5. To test failure, tampering, retry, and incomplete-state behavior without
   changing the app database, run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v tests\test_orchestrator.py
   ```

Older workflows are migrated from saved execution and verification records.
When they lack stage timestamps or complete verification metrics, their
certificates remain **INCOMPLETE** rather than receiving a retroactive
verified claim.

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
- Each accepted request receives a UUID certificate. SQLite stores its
  canonical JSON, SHA-256 integrity hash, current status, and append-only
  revisions. Verification measurements are reused from the existing
  verification attempt report; certificate history is linked to the workflow
  instead of duplicating execution or verification records.
- `VERIFIED` requires completed execution, passing independent verification,
  and complete stage/verification evidence. Failed execution or comparisons
  cannot produce that status; missing evidence remains `INCOMPLETE`.
- Certificate verification evidence includes model identifiers, individual
  coefficient/intercept/prediction comparison results, configured
  tolerances, and maximum and mean absolute prediction differences.
- Execution (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`) and verification
  (`NOT_RUN`, `RUNNING`, `PASSED`, `FAILED`) are separate persisted statuses.
  Verification attempts and their audit events are retained independently.

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
Certificate tests cover successful JSON generation, execution failure,
verification failure and retry, incomplete evidence, duplicate-request
idempotency, historical model IDs, revision retention, and tamper detection.
Streamlit AppTest renders every dashboard section, including the certificate
viewer and download control.

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
