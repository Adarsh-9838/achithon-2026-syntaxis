# FORGETGRAPH (PS09)

A local, deterministic prototype for dependency-aware deletion in a synthetic
Ridge-regression pipeline. It records source, engineered-feature, prediction
cache, and model lineage in SQLite; persists each deletion step; blocks managed
re-ingestion of tombstoned IDs; and separately verifies execution and model
replacement.

## Setup

Use Python 3.10 or later. The project is self-contained and does not use a
remote API or require credentials.

```powershell
cd ps09_forgetgraph
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For the first setup in an offline environment, make the listed wheels available
locally before running `pip install`; runtime operation itself has no network
dependency.

## Run

Start the dashboard from this directory:

```powershell
streamlit run app.py
```

The app initializes `data/forgetgraph.sqlite` from the committed
`data/synthetic_users.csv` on its first run. Use the synthetic ID shown in the
CSV (for example, `user-0001`). Select the failure-injection checkbox and a
workflow step to simulate a crash, then use **Resume workflow** to continue.

Run the test suite:

```powershell
pytest
```

Recreate the deterministic 700-user dataset if needed:

```powershell
python generate_dataset.py
```

## Design summary

- The persisted dependency graph and versioned user-to-artifact lineage are
  stored in SQLite. A deletion workflow snapshots the impacted artifact IDs
  and derives its operations from the stored artifact-operation mapping.
- Source removal, global feature recomputation, full prediction-cache
  invalidation, and model replacement execute in that order. Each step's
  status and effect count persist transactionally and completed steps are
  skipped on resume.
- The `tombstones` table stores SHA-256 user-ID hashes. Repeated requests make
  no database changes; managed ingestion checks tombstones before writing.
- `training.py` fits the replacement model; `reference.py` independently fits
  a separate scaler and Ridge model without importing the replacement trainer.
  The verifier checks coefficients, intercept, and retained-user predictions,
  feature/source membership, deleted-user absence, and difference from the old
  model.
- Execution status (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`) and
  verification status (`NOT_RUN`, `RUNNING`, `PASSED`, `FAILED`) are separate
  database fields and are displayed independently.

## Model configuration and tolerances

`config.json` fixes Ridge `alpha=1.0`, training seed `42`, and comparison
tolerances `rtol=1e-8`, `atol=1e-10`. A `StandardScaler` is refitted only on
retained feature rows. The dashboard report shows both tolerances, old vs.
replacement vs. reference coefficients/intercepts, and the maximum absolute
prediction difference.

## Tests

The pytest suite exercises lineage-based artifact identification; deletion
from source, feature, and cache data; aggregate recomputation; independent
model agreement and old/new difference; model tampering and direct record
re-insertion failures; status independence; repeated-request no-op behavior;
managed ingestion prevention; and crash/restart recovery without duplicate
steps.

## Limitations

This is a local synthetic demonstration, not a production erasure service.
It has no authentication, distributed coordination, external storage
connectors, or real personal data. The SQLite database is the workflow and
lineage authority. Full cache invalidation is intentionally conservative
because a model replacement can change every cached prediction. A completed
deletion clears the cache; a downstream consumer must repopulate it when
needed.

## AI assistance

An AI coding agent was used to translate the PS09 specification into a
testable design, implement the orchestrator and dashboard, and prepare
verification tests and documentation. The team should review the code,
exercise the dashboard, and confirm the demo behavior before submission.
