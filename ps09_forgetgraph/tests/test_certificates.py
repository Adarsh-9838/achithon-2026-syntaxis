import json
import sqlite3
from pathlib import Path

import pytest

from forgetgraph import ForgetGraphOrchestrator, SimulatedCrash
from forgetgraph import orchestrator as orchestrator_module
from forgetgraph.certificates import validate_certificate_integrity


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "synthetic_users.csv"
CONFIG = PROJECT_ROOT / "config.json"


@pytest.fixture
def orchestrator(tmp_path):
    return ForgetGraphOrchestrator(
        database_path=tmp_path / "forgetgraph.sqlite",
        dataset_path=DATASET,
        config_path=CONFIG,
    )


def choose_deletion_user():
    import pandas as pd

    return str(pd.read_csv(DATASET)["user_id"].iloc[0])


def test_verified_certificate_contains_distinct_real_execution_and_verification_evidence(
    orchestrator,
):
    result = orchestrator.request_deletion(choose_deletion_user())
    certificate = orchestrator.get_certificate(result["deletion_id"])
    document = certificate["document"]

    assert certificate["status"] == "VERIFIED"
    assert certificate["integrity_valid"] is True
    assert validate_certificate_integrity(document) is True
    assert document["evidence_complete"] is True
    assert document["request"]["request_id"] == result["deletion_id"]
    assert document["request"]["deleted_source_record_ids"][0]["deleted"] is True
    assert set(document["request"]["affected_artifact_ids"]) == {
        "source_records",
        "engineered_features",
        "prediction_cache",
        "ridge_model",
    }

    stages = document["execution_evidence"]["stages"]
    assert [stage["stage"] for stage in stages] == [
        "remove_source",
        "recompute_features",
        "invalidate_cache",
        "replace_model",
    ]
    assert all(
        stage["status"] == "COMPLETED"
        and stage["started_at"]
        and stage["completed_at"]
        for stage in stages
    )
    verification = document["verification_evidence"]
    assert verification["replacement_model_id"].startswith("sha256:")
    assert verification["reference_model_id"].startswith("sha256:")
    assert verification["coefficient_comparison"] is True
    assert verification["intercept_comparison"] is True
    assert verification["max_absolute_prediction_delta"] <= 1e-10
    assert verification["mean_absolute_prediction_delta"] <= 1e-10
    assert verification["configured_tolerances"] == {
        "rtol": 1e-8,
        "atol": 1e-10,
    }
    assert "does not prove permanent or universal erasure" in document["integrity_scope"]

    before_retry = len(orchestrator.get_certificate_history(result["deletion_id"]))
    repeat = orchestrator.request_deletion(choose_deletion_user())
    assert repeat["already_deleted"] is True
    assert repeat["deletion_id"] == result["deletion_id"]
    assert orchestrator.get_certificate(result["deletion_id"])["certificate_id"] == (
        certificate["certificate_id"]
    )
    assert len(orchestrator.list_certificates()) == 1
    assert len(orchestrator.get_certificate_history(result["deletion_id"])) == before_retry


def test_failed_certificate_is_preserved_when_execution_retry_recovers(
    orchestrator, monkeypatch
):
    original_apply = orchestrator._apply_step

    def fail_feature_rebuild(connection, step_name, user_hash):
        if step_name == "recompute_features":
            raise RuntimeError("temporary feature rebuild failure")
        return original_apply(connection, step_name, user_hash)

    monkeypatch.setattr(orchestrator, "_apply_step", fail_feature_rebuild)
    with pytest.raises(RuntimeError, match="temporary feature rebuild failure"):
        orchestrator.request_deletion(choose_deletion_user())

    deletion_id = orchestrator.list_workflows()[0]["deletion_id"]
    failed_certificate = orchestrator.get_certificate(deletion_id)
    assert failed_certificate["status"] == "FAILED"
    failed_stage = next(
        stage
        for stage in failed_certificate["document"]["execution_evidence"]["stages"]
        if stage["stage"] == "recompute_features"
    )
    assert failed_stage["status"] == "FAILED"
    assert failed_stage["error"] == "temporary feature rebuild failure"
    assert failed_stage["started_at"] and failed_stage["completed_at"]

    monkeypatch.setattr(orchestrator, "_apply_step", original_apply)
    orchestrator.resume_workflow(deletion_id)
    recovered = orchestrator.get_certificate(deletion_id)
    history = orchestrator.get_certificate_history(deletion_id)
    assert recovered["status"] == "VERIFIED"
    assert [revision["status"] for revision in history].count("FAILED") >= 1
    assert len(orchestrator.list_certificates()) == 1
    assert recovered["certificate_id"] == failed_certificate["certificate_id"]


def test_interrupted_workflow_gets_incomplete_certificate_and_resumes_once(orchestrator):
    with pytest.raises(SimulatedCrash) as raised:
        orchestrator.request_deletion(
            choose_deletion_user(), fail_after_step="recompute_features"
        )

    deletion_id = raised.value.deletion_id
    incomplete = orchestrator.get_certificate(deletion_id)
    assert incomplete["status"] == "INCOMPLETE"
    assert incomplete["document"]["execution_evidence"]["status"] == "RUNNING"
    assert "execution is still in progress" in incomplete["document"]["missing_evidence"]
    certificate_id = incomplete["certificate_id"]

    orchestrator.resume_workflow(deletion_id)
    final = orchestrator.get_certificate(deletion_id)
    history = orchestrator.get_certificate_history(deletion_id)
    assert final["status"] == "VERIFIED"
    assert final["certificate_id"] == certificate_id
    assert history[0]["status"] == "INCOMPLETE"
    assert history[-1]["status"] == "VERIFIED"


def test_failed_independent_verification_is_retained_when_retry_passes(orchestrator):
    result = orchestrator.request_deletion(choose_deletion_user())
    with sqlite3.connect(orchestrator.database_path) as connection:
        original_model = connection.execute(
            "SELECT model_json FROM models WHERE model_id = 'active'"
        ).fetchone()[0]
        changed_model = json.loads(original_model)
        changed_model["intercept"] += 50.0
        connection.execute(
            "UPDATE models SET model_json = ? WHERE model_id = 'active'",
            (json.dumps(changed_model),),
        )

    failed_report = orchestrator.verify_deletion(result["deletion_id"])
    failed_certificate = orchestrator.get_certificate(result["deletion_id"])
    assert failed_report["passed"] is False
    assert failed_certificate["status"] == "FAILED"
    assert failed_certificate["document"]["verification_evidence"][
        "intercept_comparison"
    ] is False

    with sqlite3.connect(orchestrator.database_path) as connection:
        connection.execute(
            "UPDATE models SET model_json = ? WHERE model_id = 'active'",
            (original_model,),
        )
    passed_report = orchestrator.verify_deletion(result["deletion_id"])
    recovered = orchestrator.get_certificate(result["deletion_id"])
    history = orchestrator.get_certificate_history(result["deletion_id"])
    assert passed_report["passed"] is True
    assert recovered["status"] == "VERIFIED"
    assert any(revision["status"] == "FAILED" for revision in history)
    assert len(orchestrator.list_certificates()) == 1


def test_existing_workflow_step_schema_is_migrated_without_data_loss(
    orchestrator,
):
    result = orchestrator.request_deletion(choose_deletion_user())
    with sqlite3.connect(orchestrator.database_path) as connection:
        connection.execute(
            "DELETE FROM deletion_certificate_history WHERE deletion_id = ?",
            (result["deletion_id"],),
        )
        connection.execute(
            "DELETE FROM deletion_certificates WHERE deletion_id = ?",
            (result["deletion_id"],),
        )
        connection.execute(
            """
            DELETE FROM audit_events
            WHERE deletion_id = ? AND event_type = 'step_started'
            """,
            (result["deletion_id"],),
        )
        connection.execute("ALTER TABLE workflow_steps DROP COLUMN started_at")
        connection.execute("ALTER TABLE workflow_steps DROP COLUMN completed_at")

    migrated = ForgetGraphOrchestrator(
        database_path=orchestrator.database_path,
        dataset_path=DATASET,
        config_path=CONFIG,
    )
    workflow = migrated.get_workflow(result["deletion_id"])
    assert all(step["status"] == "COMPLETED" for step in workflow["steps"])
    assert all(step["started_at"] is None for step in workflow["steps"])
    assert migrated.get_certificate(result["deletion_id"])["status"] == "INCOMPLETE"
    assert "missing start timestamp for remove_source" in migrated.get_certificate(
        result["deletion_id"]
    )["document"]["missing_evidence"]


def test_certificate_integrity_detects_tampered_persisted_document(orchestrator):
    result = orchestrator.request_deletion(choose_deletion_user())
    with sqlite3.connect(orchestrator.database_path) as connection:
        document = json.loads(
            connection.execute(
                "SELECT document_json FROM deletion_certificates WHERE deletion_id = ?",
                (result["deletion_id"],),
            ).fetchone()[0]
        )
        document["status"] = "FAILED"
        connection.execute(
            """
            UPDATE deletion_certificates SET document_json = ?
            WHERE deletion_id = ?
            """,
            (json.dumps(document), result["deletion_id"]),
        )

    certificate = orchestrator.get_certificate(result["deletion_id"])
    assert certificate["integrity_valid"] is False
    assert certificate["status"] == "FAILED"
    assert validate_certificate_integrity(certificate["document"]) is False
    assert orchestrator.list_certificates()[0]["integrity_valid"] is False
