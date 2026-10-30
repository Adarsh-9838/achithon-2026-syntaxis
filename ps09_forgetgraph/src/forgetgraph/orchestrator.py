import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .config import ModelConfig, load_config
from .features import FEATURE_COLUMNS, engineer_features
from .reference import fit_independent_reference
from .training import fit_model, predict


class DeletedUserError(ValueError):
    pass


class SimulatedCrash(RuntimeError):
    def __init__(self, deletion_id: str, step_name: str):
        super().__init__(f"Simulated crash after completed step: {step_name}")
        self.deletion_id = deletion_id
        self.step_name = step_name


class ForgetGraphOrchestrator:
    ARTIFACTS = (
        ("source_records", "Source records", "source_records", "remove_source", 1),
        (
            "engineered_features",
            "Engineered features",
            "feature_rows",
            "recompute_features",
            2,
        ),
        (
            "prediction_cache",
            "Prediction cache",
            "prediction_cache",
            "invalidate_cache",
            3,
        ),
        ("ridge_model", "Ridge model", "models", "replace_model", 4),
    )
    GRAPH_EDGES = (
        ("source_records", "engineered_features"),
        ("engineered_features", "ridge_model"),
        ("ridge_model", "prediction_cache"),
        ("engineered_features", "prediction_cache"),
    )
    VALID_STEPS = {
        "remove_source",
        "recompute_features",
        "invalidate_cache",
        "replace_model",
    }

    def __init__(
        self,
        database_path: str | Path,
        dataset_path: str | Path | None = None,
        config_path: str | Path | None = None,
    ):
        project_dir = Path(__file__).resolve().parents[2]
        self.database_path = Path(database_path).resolve()
        self.dataset_path = Path(
            dataset_path or project_dir / "data" / "synthetic_users.csv"
        ).resolve()
        self.config_path = Path(config_path or project_dir / "config.json").resolve()
        self.config: ModelConfig = load_config(self.config_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()
        self._seed_if_needed()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def hash_user_id(user_id: str) -> str:
        identifier = str(user_id)
        if not identifier:
            raise ValueError("user_id must not be empty")
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()

    def _create_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                count_table TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifact_dependencies (
                upstream_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                downstream_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                PRIMARY KEY (upstream_artifact_id, downstream_artifact_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifact_operations (
                artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
                operation_name TEXT NOT NULL,
                operation_order INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS source_records (
                user_hash TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                signal_a REAL NOT NULL,
                signal_b REAL NOT NULL,
                target REAL NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS feature_rows (
                user_hash TEXT PRIMARY KEY,
                signal_a REAL NOT NULL,
                signal_b REAL NOT NULL,
                region_mean_signal_a REAL NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS prediction_cache (
                user_hash TEXT PRIMARY KEY,
                prediction REAL NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                model_json TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifact_user_lineage (
                lineage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                user_hash TEXT NOT NULL,
                generation INTEGER NOT NULL,
                is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
                UNIQUE (artifact_id, user_hash, generation)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_lineage_active_user
                ON artifact_user_lineage(user_hash, is_active)
            """,
            """
            CREATE TABLE IF NOT EXISTS deletion_workflows (
                deletion_id TEXT PRIMARY KEY,
                user_hash TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                execution_status TEXT NOT NULL
                    CHECK (execution_status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
                verification_status TEXT NOT NULL
                    CHECK (verification_status IN ('NOT_RUN','RUNNING','PASSED','FAILED')),
                affected_artifacts_json TEXT NOT NULL,
                counts_before_json TEXT NOT NULL,
                old_model_json TEXT,
                verification_report_json TEXT,
                error_text TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                deletion_id TEXT NOT NULL REFERENCES deletion_workflows(deletion_id),
                step_name TEXT NOT NULL,
                artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                step_order INTEGER NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
                effect_count INTEGER NOT NULL DEFAULT 0,
                error_text TEXT,
                PRIMARY KEY (deletion_id, step_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tombstones (
                user_hash TEXT PRIMARY KEY,
                deleted_at TEXT NOT NULL,
                deletion_id TEXT NOT NULL UNIQUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                deletion_id TEXT,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        )
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            for statement in statements:
                connection.execute(statement)
            for artifact_id, label, count_table, operation, order in self.ARTIFACTS:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO artifacts
                    (artifact_id, label, count_table)
                    VALUES (?, ?, ?)
                    """,
                    (artifact_id, label, count_table),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO artifact_operations
                    (artifact_id, operation_name, operation_order)
                    VALUES (?, ?, ?)
                    """,
                    (artifact_id, operation, order),
                )
            for upstream, downstream in self.GRAPH_EDGES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO artifact_dependencies
                    (upstream_artifact_id, downstream_artifact_id)
                    VALUES (?, ?)
                    """,
                    (upstream, downstream),
                )

    def _seed_if_needed(self) -> None:
        with self._connection() as connection:
            initialized = connection.execute(
                "SELECT value FROM metadata WHERE key = 'initialized'"
            ).fetchone()
            if initialized:
                return
            existing = connection.execute(
                "SELECT COUNT(*) AS count FROM source_records"
            ).fetchone()["count"]
            if existing:
                raise RuntimeError(
                    "Database contains source records without initialization metadata"
                )

            source = pd.read_csv(self.dataset_path)
            required = {"user_id", "region", "signal_a", "signal_b", "target"}
            if not required.issubset(source.columns):
                raise ValueError(
                    f"Dataset is missing required columns: {sorted(required - set(source.columns))}"
                )
            source_rows = []
            user_hashes = []
            for record in source.to_dict(orient="records"):
                user_hash = self.hash_user_id(record["user_id"])
                user_hashes.append(user_hash)
                source_rows.append(
                    (
                        user_hash,
                        str(record["region"]),
                        float(record["signal_a"]),
                        float(record["signal_b"]),
                        float(record["target"]),
                    )
                )
            connection.executemany(
                """
                INSERT INTO source_records
                (user_hash, region, signal_a, signal_b, target)
                VALUES (?, ?, ?, ?, ?)
                """,
                source_rows,
            )
            self._refresh_lineage(connection, "source_records", user_hashes)
            self._rebuild_features(connection)
            self._replace_model(connection)
            self._rebuild_cache(connection)
            connection.execute(
                "INSERT INTO metadata (key, value) VALUES ('initialized', '1')"
            )

    def _record_audit(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        details: str,
        deletion_id: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (deletion_id, event_type, details, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (deletion_id, event_type, details, self._now()),
        )

    def _refresh_lineage(
        self,
        connection: sqlite3.Connection,
        artifact_id: str,
        user_hashes: list[str],
    ) -> None:
        connection.execute(
            "UPDATE artifact_user_lineage SET is_active = 0 "
            "WHERE artifact_id = ? AND is_active = 1",
            (artifact_id,),
        )
        connection.execute(
            "UPDATE artifacts SET generation = generation + 1 WHERE artifact_id = ?",
            (artifact_id,),
        )
        generation = connection.execute(
            "SELECT generation FROM artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()["generation"]
        connection.executemany(
            """
            INSERT INTO artifact_user_lineage
            (artifact_id, user_hash, generation, is_active)
            VALUES (?, ?, ?, 1)
            """,
            [(artifact_id, user_hash, generation) for user_hash in sorted(set(user_hashes))],
        )

    def _active_source(self, connection: sqlite3.Connection) -> pd.DataFrame:
        rows = connection.execute(
            """
            SELECT user_hash, region, signal_a, signal_b, target
            FROM source_records ORDER BY user_hash
            """
        ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def _active_features(
        self, connection: sqlite3.Connection
    ) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
        rows = connection.execute(
            """
            SELECT f.user_hash, f.signal_a, f.signal_b, f.region_mean_signal_a,
                   s.target
            FROM feature_rows AS f
            JOIN source_records AS s USING (user_hash)
            ORDER BY f.user_hash
            """
        ).fetchall()
        records = [dict(row) for row in rows]
        frame = pd.DataFrame(records)
        if frame.empty:
            frame = pd.DataFrame(columns=["user_hash", *FEATURE_COLUMNS, "target"])
        return (
            frame[["user_hash", *FEATURE_COLUMNS]],
            frame["target"].to_numpy(dtype=np.float64),
            frame["user_hash"].tolist(),
        )

    def _rebuild_features(self, connection: sqlite3.Connection) -> int:
        source = self._active_source(connection)
        features = engineer_features(source)
        connection.execute("DELETE FROM feature_rows")
        connection.executemany(
            """
            INSERT INTO feature_rows
            (user_hash, signal_a, signal_b, region_mean_signal_a)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    row.user_hash,
                    float(row.signal_a),
                    float(row.signal_b),
                    float(row.region_mean_signal_a),
                )
                for row in features.itertuples(index=False)
            ],
        )
        self._refresh_lineage(
            connection, "engineered_features", features["user_hash"].tolist()
        )
        return len(features)

    def _replace_model(self, connection: sqlite3.Connection) -> int:
        features, targets, user_hashes = self._active_features(connection)
        if features.empty:
            raise ValueError("Cannot fit a Ridge model without retained feature rows")
        model = fit_model(
            features,
            targets,
            alpha=self.config.alpha,
            random_seed=self.config.random_seed,
        )
        previous = connection.execute(
            "SELECT generation FROM models WHERE model_id = 'active'"
        ).fetchone()
        generation = 1 if previous is None else previous["generation"] + 1
        connection.execute(
            """
            INSERT INTO models (model_id, model_json, generation, updated_at)
            VALUES ('active', ?, ?, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                model_json = excluded.model_json,
                generation = excluded.generation,
                updated_at = excluded.updated_at
            """,
            (
                json.dumps(model, sort_keys=True),
                generation,
                self._now(),
            ),
        )
        self._refresh_lineage(connection, "ridge_model", user_hashes)
        return 1

    def _rebuild_cache(self, connection: sqlite3.Connection) -> int:
        features, _, user_hashes = self._active_features(connection)
        model_row = connection.execute(
            "SELECT model_json FROM models WHERE model_id = 'active'"
        ).fetchone()
        if model_row is None:
            raise RuntimeError("Cannot populate predictions without an active model")
        predictions = predict(json.loads(model_row["model_json"]), features)
        connection.execute("DELETE FROM prediction_cache")
        connection.executemany(
            "INSERT INTO prediction_cache (user_hash, prediction) VALUES (?, ?)",
            [
                (user_hash, float(prediction))
                for user_hash, prediction in zip(user_hashes, predictions)
            ],
        )
        self._refresh_lineage(connection, "prediction_cache", user_hashes)
        return len(user_hashes)

    def _count_records(self, connection: sqlite3.Connection) -> dict[str, int]:
        tables = {
            "source_records": "source_records",
            "feature_rows": "feature_rows",
            "prediction_cache": "prediction_cache",
            "workflows": "deletion_workflows",
            "tombstones": "tombstones",
            "audit_events": "audit_events",
            "lineage_rows": "artifact_user_lineage",
        }
        return {
            key: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for key, table in tables.items()
        }

    def get_database_counts(self) -> dict[str, int]:
        with self._connection() as connection:
            return self._count_records(connection)

    def get_affected_artifacts(self, user_id: str) -> list[str]:
        user_hash = self.hash_user_id(user_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT artifact_id
                FROM artifact_user_lineage
                WHERE user_hash = ? AND is_active = 1
                ORDER BY artifact_id
                """,
                (user_hash,),
            ).fetchall()
            return [row["artifact_id"] for row in rows]

    def get_artifact_graph(self) -> dict[str, list[dict]]:
        with self._connection() as connection:
            artifacts = connection.execute(
                "SELECT artifact_id, label, count_table FROM artifacts ORDER BY artifact_id"
            ).fetchall()
            edges = connection.execute(
                """
                SELECT upstream_artifact_id, downstream_artifact_id
                FROM artifact_dependencies
                ORDER BY upstream_artifact_id, downstream_artifact_id
                """
            ).fetchall()
            counts = self._count_records(connection)
            nodes = [
                {
                    "id": row["artifact_id"],
                    "label": row["label"],
                    "count": (
                        counts[row["count_table"]]
                        if row["count_table"] in counts
                        else 1
                    ),
                }
                for row in artifacts
            ]
            return {
                "nodes": nodes,
                "edges": [
                    {
                        "source": row["upstream_artifact_id"],
                        "target": row["downstream_artifact_id"],
                    }
                    for row in edges
                ],
            }

    def _create_workflow(self, user_hash: str) -> tuple[str, bool]:
        deletion_id = str(uuid.uuid4())
        with self._connection() as connection:
            tombstone = connection.execute(
                "SELECT deletion_id FROM tombstones WHERE user_hash = ?",
                (user_hash,),
            ).fetchone()
            if tombstone:
                return tombstone["deletion_id"], True

            affected = [
                row["artifact_id"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT artifact_id
                    FROM artifact_user_lineage
                    WHERE user_hash = ? AND is_active = 1
                    ORDER BY artifact_id
                    """,
                    (user_hash,),
                ).fetchall()
            ]
            old_model_row = connection.execute(
                "SELECT model_json FROM models WHERE model_id = 'active'"
            ).fetchone()
            old_model = old_model_row["model_json"] if old_model_row else None
            counts_before = self._count_records(connection)
            now = self._now()
            connection.execute(
                """
                INSERT INTO deletion_workflows (
                    deletion_id, user_hash, requested_at, execution_status,
                    verification_status, affected_artifacts_json,
                    counts_before_json, old_model_json
                ) VALUES (?, ?, ?, 'PENDING', 'NOT_RUN', ?, ?, ?)
                """,
                (
                    deletion_id,
                    user_hash,
                    now,
                    json.dumps(affected),
                    json.dumps(counts_before, sort_keys=True),
                    old_model,
                ),
            )
            connection.execute(
                """
                INSERT INTO tombstones (user_hash, deleted_at, deletion_id)
                VALUES (?, ?, ?)
                """,
                (user_hash, now, deletion_id),
            )
            if affected:
                placeholders = ",".join("?" for _ in affected)
                operations = connection.execute(
                    f"""
                    SELECT artifact_id, operation_name, operation_order
                    FROM artifact_operations
                    WHERE artifact_id IN ({placeholders})
                    ORDER BY operation_order, artifact_id
                    """,
                    affected,
                ).fetchall()
                for operation in operations:
                    connection.execute(
                        """
                        INSERT INTO workflow_steps
                        (deletion_id, step_name, artifact_id, step_order, status)
                        VALUES (?, ?, ?, ?, 'PENDING')
                        """,
                        (
                            deletion_id,
                            operation["operation_name"],
                            operation["artifact_id"],
                            operation["operation_order"],
                        ),
                    )
            self._record_audit(
                connection,
                "deletion_requested",
                json.dumps(
                    {"affected_artifacts": affected, "user_hash": user_hash},
                    sort_keys=True,
                ),
                deletion_id,
            )
        return deletion_id, False

    def request_deletion(
        self, user_id: str, fail_after_step: str | None = None
    ) -> dict:
        if fail_after_step is not None and fail_after_step not in self.VALID_STEPS:
            raise ValueError(f"Unknown failure-injection step: {fail_after_step}")
        user_hash = self.hash_user_id(user_id)
        with self._connection() as connection:
            existing = connection.execute(
                """
                SELECT t.deletion_id, w.execution_status, w.verification_status
                FROM tombstones AS t
                JOIN deletion_workflows AS w USING (deletion_id)
                WHERE t.user_hash = ?
                """,
                (user_hash,),
            ).fetchone()
        if existing:
            return {
                "already_deleted": True,
                "deletion_id": existing["deletion_id"],
                "execution_status": existing["execution_status"],
                "verification_status": existing["verification_status"],
            }
        deletion_id, already_deleted = self._create_workflow(user_hash)
        if already_deleted:
            return {
                "already_deleted": True,
                "deletion_id": deletion_id,
                **self._workflow_statuses(deletion_id),
            }
        return self._execute_workflow(deletion_id, fail_after_step)

    def resume_workflow(
        self, deletion_id: str, fail_after_step: str | None = None
    ) -> dict:
        if fail_after_step is not None and fail_after_step not in self.VALID_STEPS:
            raise ValueError(f"Unknown failure-injection step: {fail_after_step}")
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM deletion_workflows WHERE deletion_id = ?",
                (deletion_id,),
            ).fetchone()
        if exists is None:
            raise KeyError(f"Unknown deletion workflow: {deletion_id}")
        return self._execute_workflow(deletion_id, fail_after_step)

    def _workflow_statuses(self, deletion_id: str) -> dict[str, str]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT execution_status, verification_status
                FROM deletion_workflows WHERE deletion_id = ?
                """,
                (deletion_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown deletion workflow: {deletion_id}")
        return {
            "execution_status": row["execution_status"],
            "verification_status": row["verification_status"],
        }

    def _execute_workflow(
        self, deletion_id: str, fail_after_step: str | None = None
    ) -> dict:
        with self._connection() as connection:
            workflow = connection.execute(
                "SELECT execution_status FROM deletion_workflows WHERE deletion_id = ?",
                (deletion_id,),
            ).fetchone()
            if workflow is None:
                raise KeyError(f"Unknown deletion workflow: {deletion_id}")
            if workflow["execution_status"] == "COMPLETED":
                return {
                    "already_deleted": False,
                    "deletion_id": deletion_id,
                    **self._workflow_statuses(deletion_id),
                }
            connection.execute(
                """
                UPDATE deletion_workflows
                SET execution_status = 'RUNNING', error_text = NULL
                WHERE deletion_id = ?
                """,
                (deletion_id,),
            )

        with self._connection() as connection:
            steps = connection.execute(
                """
                SELECT step_name, status
                FROM workflow_steps
                WHERE deletion_id = ?
                ORDER BY step_order, artifact_id
                """,
                (deletion_id,),
            ).fetchall()
        for step in steps:
            if step["status"] == "COMPLETED":
                continue
            step_name = step["step_name"]
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE workflow_steps
                    SET status = 'RUNNING', error_text = NULL
                    WHERE deletion_id = ? AND step_name = ?
                    """,
                    (deletion_id, step_name),
                )
            try:
                with self._connection() as connection:
                    workflow = connection.execute(
                        "SELECT user_hash FROM deletion_workflows WHERE deletion_id = ?",
                        (deletion_id,),
                    ).fetchone()
                    effect_count = self._apply_step(
                        connection, step_name, workflow["user_hash"]
                    )
                    connection.execute(
                        """
                        UPDATE workflow_steps
                        SET status = 'COMPLETED', effect_count = ?, error_text = NULL
                        WHERE deletion_id = ? AND step_name = ?
                        """,
                        (effect_count, deletion_id, step_name),
                    )
                    self._record_audit(
                        connection,
                        "step_completed",
                        json.dumps(
                            {"effect_count": effect_count, "step": step_name},
                            sort_keys=True,
                        ),
                        deletion_id,
                    )
            except Exception as error:
                with self._connection() as connection:
                    connection.execute(
                        """
                        UPDATE workflow_steps
                        SET status = 'FAILED', error_text = ?
                        WHERE deletion_id = ? AND step_name = ?
                        """,
                        (str(error), deletion_id, step_name),
                    )
                    connection.execute(
                        """
                        UPDATE deletion_workflows
                        SET execution_status = 'FAILED', error_text = ?
                        WHERE deletion_id = ?
                        """,
                        (str(error), deletion_id),
                    )
                    self._record_audit(
                        connection,
                        "step_failed",
                        json.dumps({"step": step_name, "error": str(error)}),
                        deletion_id,
                    )
                raise
            if fail_after_step == step_name:
                raise SimulatedCrash(deletion_id, step_name)

        with self._connection() as connection:
            connection.execute(
                """
                UPDATE deletion_workflows
                SET execution_status = 'COMPLETED', error_text = NULL
                WHERE deletion_id = ?
                """,
                (deletion_id,),
            )
            self._record_audit(
                connection,
                "execution_completed",
                "All recorded deletion operations completed",
                deletion_id,
            )
        self.verify_deletion(deletion_id)
        return {
            "already_deleted": False,
            "deletion_id": deletion_id,
            **self._workflow_statuses(deletion_id),
        }

    def _apply_step(
        self, connection: sqlite3.Connection, step_name: str, user_hash: str
    ) -> int:
        if step_name == "remove_source":
            cursor = connection.execute(
                "DELETE FROM source_records WHERE user_hash = ?", (user_hash,)
            )
            connection.execute(
                """
                UPDATE artifact_user_lineage SET is_active = 0
                WHERE artifact_id = 'source_records' AND user_hash = ?
                  AND is_active = 1
                """,
                (user_hash,),
            )
            return cursor.rowcount
        if step_name == "recompute_features":
            return self._rebuild_features(connection)
        if step_name == "invalidate_cache":
            cursor = connection.execute("DELETE FROM prediction_cache")
            self._refresh_lineage(connection, "prediction_cache", [])
            return cursor.rowcount
        if step_name == "replace_model":
            return self._replace_model(connection)
        raise ValueError(f"No handler is registered for step {step_name!r}")

    def verify_deletion(self, deletion_id: str) -> dict:
        with self._connection() as connection:
            workflow = connection.execute(
                """
                SELECT * FROM deletion_workflows WHERE deletion_id = ?
                """,
                (deletion_id,),
            ).fetchone()
            if workflow is None:
                raise KeyError(f"Unknown deletion workflow: {deletion_id}")
            if workflow["execution_status"] != "COMPLETED":
                raise ValueError("Cannot verify a workflow before execution completes")
            connection.execute(
                """
                UPDATE deletion_workflows
                SET verification_status = 'RUNNING', verification_report_json = NULL
                WHERE deletion_id = ?
                """,
                (deletion_id,),
            )

        try:
            with self._connection() as connection:
                workflow = connection.execute(
                    "SELECT * FROM deletion_workflows WHERE deletion_id = ?",
                    (deletion_id,),
                ).fetchone()
                user_hash = workflow["user_hash"]
                source_hashes = {
                    row["user_hash"]
                    for row in connection.execute(
                        "SELECT user_hash FROM source_records"
                    ).fetchall()
                }
                feature_hashes = {
                    row["user_hash"]
                    for row in connection.execute(
                        "SELECT user_hash FROM feature_rows"
                    ).fetchall()
                }
                cache_hashes = {
                    row["user_hash"]
                    for row in connection.execute(
                        "SELECT user_hash FROM prediction_cache"
                    ).fetchall()
                }
                model_row = connection.execute(
                    "SELECT model_json FROM models WHERE model_id = 'active'"
                ).fetchone()
                if model_row is None or workflow["old_model_json"] is None:
                    raise RuntimeError("Verification requires both old and active models")
                current_model = json.loads(model_row["model_json"])
                old_model = json.loads(workflow["old_model_json"])
                features, targets, _ = self._active_features(connection)
                if features.empty:
                    raise RuntimeError("Verification cannot fit a reference on empty data")
                reference_model, reference_predictions = fit_independent_reference(
                    features,
                    targets,
                    alpha=self.config.alpha,
                    random_seed=self.config.random_seed,
                )
                current_predictions = predict(current_model, features)
                deleted_user_absent = (
                    user_hash not in source_hashes
                    and user_hash not in feature_hashes
                    and user_hash not in cache_hashes
                )
                features_match_source = source_hashes == feature_hashes
                coefficients_match = bool(
                    np.allclose(
                        current_model["coefficients"],
                        reference_model["coefficients"],
                        rtol=self.config.rtol,
                        atol=self.config.atol,
                    )
                )
                intercept_match = bool(
                    np.isclose(
                        current_model["intercept"],
                        reference_model["intercept"],
                        rtol=self.config.rtol,
                        atol=self.config.atol,
                    )
                )
                predictions_match = bool(
                    np.allclose(
                        current_predictions,
                        reference_predictions,
                        rtol=self.config.rtol,
                        atol=self.config.atol,
                    )
                )
                old_model_differs = not (
                    np.allclose(
                        old_model["coefficients"],
                        current_model["coefficients"],
                        rtol=self.config.rtol,
                        atol=self.config.atol,
                    )
                    and np.isclose(
                        old_model["intercept"],
                        current_model["intercept"],
                        rtol=self.config.rtol,
                        atol=self.config.atol,
                    )
                )
                counts_after = self._count_records(connection)
                counts_before = json.loads(workflow["counts_before_json"])
                cache_step = connection.execute(
                    """
                    SELECT effect_count FROM workflow_steps
                    WHERE deletion_id = ? AND step_name = 'invalidate_cache'
                    """,
                    (deletion_id,),
                ).fetchone()
                report = {
                    "passed": all(
                        (
                            deleted_user_absent,
                            features_match_source,
                            coefficients_match,
                            intercept_match,
                            predictions_match,
                            old_model_differs,
                        )
                    ),
                    "deleted_user_absent": deleted_user_absent,
                    "features_match_source": features_match_source,
                    "coefficients_match": coefficients_match,
                    "intercept_match": intercept_match,
                    "predictions_match": predictions_match,
                    "old_model_differs": old_model_differs,
                    "rtol": self.config.rtol,
                    "atol": self.config.atol,
                    "alpha": self.config.alpha,
                    "random_seed": self.config.random_seed,
                    "prediction_count": len(current_predictions),
                    "max_prediction_abs_diff": float(
                        np.max(np.abs(current_predictions - reference_predictions))
                    ),
                    "counts_before": counts_before,
                    "counts_after": counts_after,
                    "cache_invalidation_count": (
                        cache_step["effect_count"] if cache_step else 0
                    ),
                    "old_model": {
                        "coefficients": old_model["coefficients"],
                        "intercept": old_model["intercept"],
                    },
                    "replacement": {
                        "coefficients": current_model["coefficients"],
                        "intercept": current_model["intercept"],
                    },
                    "reference": {
                        "coefficients": reference_model["coefficients"],
                        "intercept": reference_model["intercept"],
                    },
                    "failure_reasons": [
                        key
                        for key, passed in (
                            ("deleted_user_absent", deleted_user_absent),
                            ("features_match_source", features_match_source),
                            ("coefficients_match", coefficients_match),
                            ("intercept_match", intercept_match),
                            ("predictions_match", predictions_match),
                            ("old_model_differs", old_model_differs),
                        )
                        if not passed
                    ],
                }
                verification_status = "PASSED" if report["passed"] else "FAILED"
                connection.execute(
                    """
                    UPDATE deletion_workflows
                    SET verification_status = ?, verification_report_json = ?,
                        error_text = NULL
                    WHERE deletion_id = ?
                    """,
                    (
                        verification_status,
                        json.dumps(report, sort_keys=True),
                        deletion_id,
                    ),
                )
                self._record_audit(
                    connection,
                    "verification_completed",
                    json.dumps(
                        {
                            "verification_status": verification_status,
                            "failure_reasons": report["failure_reasons"],
                        },
                        sort_keys=True,
                    ),
                    deletion_id,
                )
                return report
        except Exception as error:
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE deletion_workflows
                    SET verification_status = 'FAILED', error_text = ?
                    WHERE deletion_id = ?
                    """,
                    (str(error), deletion_id),
                )
                self._record_audit(
                    connection,
                    "verification_error",
                    str(error),
                    deletion_id,
                )
            raise

    def get_verification_report(self, deletion_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT verification_report_json
                FROM deletion_workflows WHERE deletion_id = ?
                """,
                (deletion_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown deletion workflow: {deletion_id}")
        if row["verification_report_json"] is None:
            return None
        return json.loads(row["verification_report_json"])

    def get_workflow(self, deletion_id: str) -> dict:
        with self._connection() as connection:
            workflow = connection.execute(
                "SELECT * FROM deletion_workflows WHERE deletion_id = ?",
                (deletion_id,),
            ).fetchone()
            if workflow is None:
                raise KeyError(f"Unknown deletion workflow: {deletion_id}")
            steps = connection.execute(
                """
                SELECT step_name, artifact_id, step_order, status, effect_count, error_text
                FROM workflow_steps
                WHERE deletion_id = ?
                ORDER BY step_order, artifact_id
                """,
                (deletion_id,),
            ).fetchall()
            result = dict(workflow)
            result["affected_artifacts"] = json.loads(
                result.pop("affected_artifacts_json")
            )
            result["counts_before"] = json.loads(result.pop("counts_before_json"))
            result["old_model"] = (
                json.loads(result["old_model_json"])
                if result["old_model_json"]
                else None
            )
            result["verification_report"] = (
                json.loads(result["verification_report_json"])
                if result["verification_report_json"]
                else None
            )
            result["steps"] = [dict(step) for step in steps]
            return result

    def get_user_state(self, user_id: str) -> dict[str, bool]:
        user_hash = self.hash_user_id(user_id)
        with self._connection() as connection:
            return {
                "source": connection.execute(
                    "SELECT 1 FROM source_records WHERE user_hash = ?", (user_hash,)
                ).fetchone()
                is not None,
                "features": connection.execute(
                    "SELECT 1 FROM feature_rows WHERE user_hash = ?", (user_hash,)
                ).fetchone()
                is not None,
                "cache": connection.execute(
                    "SELECT 1 FROM prediction_cache WHERE user_hash = ?", (user_hash,)
                ).fetchone()
                is not None,
            }

    def get_feature_row(self, user_id: str) -> dict | None:
        user_hash = self.hash_user_id(user_id)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT signal_a, signal_b, region_mean_signal_a
                FROM feature_rows WHERE user_hash = ?
                """,
                (user_hash,),
            ).fetchone()
            return dict(row) if row is not None else None

    def get_model_snapshot(self) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT model_json, generation FROM models WHERE model_id = 'active'"
            ).fetchone()
            if row is None:
                raise RuntimeError("No active model is available")
            model = json.loads(row["model_json"])
            model["generation"] = row["generation"]
            return model

    def get_audit_events(self, limit: int = 100) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, deletion_id, event_type, details, created_at
                FROM audit_events
                ORDER BY event_id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_workflows(self, limit: int = 100) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT deletion_id, requested_at, execution_status,
                       verification_status, affected_artifacts_json
                FROM deletion_workflows
                ORDER BY requested_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "deletion_id": row["deletion_id"],
                    "requested_at": row["requested_at"],
                    "execution_status": row["execution_status"],
                    "verification_status": row["verification_status"],
                    "affected_artifacts": json.loads(
                        row["affected_artifacts_json"]
                    ),
                }
                for row in rows
            ]

    def ingest_record(self, record: dict) -> None:
        required = {"user_id", "region", "signal_a", "signal_b", "target"}
        missing = required - set(record)
        if missing:
            raise ValueError(f"Record is missing required fields: {sorted(missing)}")
        user_hash = self.hash_user_id(record["user_id"])
        with self._connection() as connection:
            tombstone = connection.execute(
                "SELECT 1 FROM tombstones WHERE user_hash = ?", (user_hash,)
            ).fetchone()
            if tombstone:
                raise DeletedUserError("A tombstoned user cannot be re-ingested")
            connection.execute(
                """
                INSERT INTO source_records
                (user_hash, region, signal_a, signal_b, target)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_hash,
                    str(record["region"]),
                    float(record["signal_a"]),
                    float(record["signal_b"]),
                    float(record["target"]),
                ),
            )
            generation = connection.execute(
                "SELECT generation FROM artifacts WHERE artifact_id = 'source_records'"
            ).fetchone()["generation"]
            connection.execute(
                """
                INSERT INTO artifact_user_lineage
                (artifact_id, user_hash, generation, is_active)
                VALUES ('source_records', ?, ?, 1)
                """,
                (user_hash, generation),
            )
            self._rebuild_features(connection)
            self._replace_model(connection)
            self._rebuild_cache(connection)
