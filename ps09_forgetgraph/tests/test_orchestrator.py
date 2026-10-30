import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from forgetgraph import (
    DeletedUserError,
    ForgetGraphOrchestrator,
    SimulatedCrash,
    UnknownUserError,
)
from forgetgraph import orchestrator as orchestrator_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "synthetic_users.csv"
CONFIG = PROJECT_ROOT / "config.json"
EXPECTED_ARTIFACTS = {
    "source_records",
    "engineered_features",
    "prediction_cache",
    "ridge_model",
}


@pytest.fixture
def orchestrator(tmp_path):
    return ForgetGraphOrchestrator(
        database_path=tmp_path / "forgetgraph.sqlite",
        dataset_path=DATASET,
        config_path=CONFIG,
    )


def choose_deletion_user():
    rows = pd.read_csv(DATASET)
    region = rows["region"].iloc[0]
    return rows.loc[rows["region"] == region, "user_id"].iloc[
        rows.loc[rows["region"] == region, "signal_a"].argmax()
    ]


def test_affected_artifacts_come_from_recorded_lineage(orchestrator):
    user_id = choose_deletion_user()

    assert set(orchestrator.get_affected_artifacts(user_id)) == EXPECTED_ARTIFACTS
    with sqlite3.connect(orchestrator.database_path) as connection:
        rows = connection.execute(
            "SELECT COUNT(*) FROM artifact_user_lineage "
            "WHERE user_hash = ? AND is_active = 1",
            (orchestrator.hash_user_id(user_id),),
        ).fetchone()
    assert rows[0] == len(EXPECTED_ARTIFACTS)


def test_deletion_removes_user_from_source_features_and_cache(orchestrator):
    user_id = choose_deletion_user()

    result = orchestrator.request_deletion(user_id)

    assert result["execution_status"] == "COMPLETED"
    state = orchestrator.get_user_state(user_id)
    assert state == {"source": False, "features": False, "cache": False}
    assert orchestrator.get_workflow(result["deletion_id"])["verification_status"] == "PASSED"


def test_deletion_recomputes_aggregate_features_for_retained_users(orchestrator):
    source = pd.read_csv(DATASET)
    region = source["region"].iloc[0]
    group = source.loc[source["region"] == region]
    selected = group.loc[group["signal_a"].idxmax()]
    deleted_user = selected["user_id"]
    retained_user = group.loc[group["user_id"] != deleted_user, "user_id"].iloc[0]
    old_feature = orchestrator.get_feature_row(retained_user)["region_mean_signal_a"]
    expected_mean = group.loc[group["user_id"] != deleted_user, "signal_a"].mean()

    orchestrator.request_deletion(deleted_user)

    new_feature = orchestrator.get_feature_row(retained_user)["region_mean_signal_a"]
    assert new_feature == pytest.approx(expected_mean)
    assert new_feature != pytest.approx(old_feature)


def test_replacement_matches_independent_reference_and_reports_old_difference(orchestrator):
    user_id = choose_deletion_user()

    result = orchestrator.request_deletion(user_id)
    report = orchestrator.get_verification_report(result["deletion_id"])

    assert report["passed"] is True
    assert report["coefficients_match"] is True
    assert report["intercept_match"] is True
    assert report["predictions_match"] is True
    assert report["old_model_differs"] is True
    assert report["old_model_difference_required"] is False
    assert report["rtol"] == 1e-8
    assert report["atol"] == 1e-10
    assert report["max_reference_coefficient_abs_diff"] <= report["atol"]
    assert report["reference_intercept_abs_diff"] <= report["atol"]
    assert report["max_reference_prediction_abs_diff"] <= report["atol"]
    np.testing.assert_allclose(
        report["replacement"]["coefficients"],
        report["reference"]["coefficients"],
        rtol=report["rtol"],
        atol=report["atol"],
    )


def test_verification_fails_when_replacement_model_is_tampered(orchestrator):
    user_id = choose_deletion_user()
    result = orchestrator.request_deletion(user_id)

    with sqlite3.connect(orchestrator.database_path) as connection:
        row = connection.execute(
            "SELECT model_json FROM models WHERE model_id = 'active'"
        ).fetchone()
        model = json.loads(row[0])
        correct_model_json = row[0]
        model["coefficients"][0] += 100.0
        connection.execute(
            "UPDATE models SET model_json = ? WHERE model_id = 'active'",
            (json.dumps(model),),
        )

    report = orchestrator.verify_deletion(result["deletion_id"])
    workflow = orchestrator.get_workflow(result["deletion_id"])
    assert report["passed"] is False
    assert workflow["execution_status"] == "COMPLETED"
    assert workflow["verification_status"] == "FAILED"
    with sqlite3.connect(orchestrator.database_path) as connection:
        connection.execute(
            "UPDATE models SET model_json = ? WHERE model_id = 'active'",
            (correct_model_json,),
        )

    retry_report = orchestrator.verify_deletion(result["deletion_id"])
    attempts = orchestrator.get_verification_attempts(result["deletion_id"])
    assert retry_report["passed"] is True
    assert [attempt["status"] for attempt in attempts] == ["PASSED", "FAILED", "PASSED"]
    assert orchestrator.get_workflow(result["deletion_id"])["execution_status"] == "COMPLETED"
    assert orchestrator.get_workflow(result["deletion_id"])["verification_status"] == "PASSED"


def test_matching_previous_model_is_not_required_to_change(orchestrator):
    user_id = choose_deletion_user()
    result = orchestrator.request_deletion(user_id)
    with sqlite3.connect(orchestrator.database_path) as connection:
        active_model_json = connection.execute(
            "SELECT model_json FROM models WHERE model_id = 'active'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE deletion_workflows SET old_model_json = ? WHERE deletion_id = ?",
            (active_model_json, result["deletion_id"]),
        )

    report = orchestrator.verify_deletion(result["deletion_id"])

    assert report["passed"] is True
    assert report["old_model_differs"] is False
    assert report["old_model_difference_required"] is False
    assert "old_model_differs" not in report["failure_reasons"]


def test_verification_fails_when_deleted_record_is_reinserted(orchestrator):
    user_id = choose_deletion_user()
    result = orchestrator.request_deletion(user_id)
    source = pd.read_csv(DATASET).set_index("user_id").loc[user_id]
    user_hash = orchestrator.hash_user_id(user_id)

    with sqlite3.connect(orchestrator.database_path) as connection:
        connection.execute(
            "INSERT INTO source_records "
            "(user_hash, region, signal_a, signal_b, target) VALUES (?, ?, ?, ?, ?)",
            (
                user_hash,
                source["region"],
                source["signal_a"],
                source["signal_b"],
                source["target"],
            ),
        )

    report = orchestrator.verify_deletion(result["deletion_id"])

    assert report["passed"] is False
    assert report["deleted_user_absent"] is False


def test_execution_and_verification_statuses_are_independent(orchestrator):
    user_id = choose_deletion_user()
    result = orchestrator.request_deletion(user_id)

    assert result["execution_status"] == "COMPLETED"
    assert result["verification_status"] == "PASSED"

    with sqlite3.connect(orchestrator.database_path) as connection:
        model = json.loads(
            connection.execute(
                "SELECT model_json FROM models WHERE model_id = 'active'"
            ).fetchone()[0]
        )
        model["intercept"] += 50.0
        connection.execute(
            "UPDATE models SET model_json = ? WHERE model_id = 'active'",
            (json.dumps(model),),
        )

    orchestrator.verify_deletion(result["deletion_id"])
    workflow = orchestrator.get_workflow(result["deletion_id"])
    assert workflow["execution_status"] == "COMPLETED"
    assert workflow["verification_status"] == "FAILED"


def test_repeated_deletion_is_a_no_op(orchestrator):
    user_id = choose_deletion_user()
    first = orchestrator.request_deletion(user_id)
    before = orchestrator.get_database_counts()

    second = orchestrator.request_deletion(user_id)

    assert second["already_deleted"] is True
    assert second["deletion_id"] == first["deletion_id"]
    assert orchestrator.get_database_counts() == before


def test_unknown_user_is_rejected_without_creating_a_workflow(orchestrator):
    before = orchestrator.get_database_counts()

    with pytest.raises(UnknownUserError, match="not in the active source dataset"):
        orchestrator.request_deletion("not-a-dataset-user")

    assert orchestrator.get_database_counts() == before


def test_managed_ingestion_rejects_tombstoned_user(orchestrator):
    user_id = choose_deletion_user()
    orchestrator.request_deletion(user_id)
    source = pd.read_csv(DATASET).set_index("user_id").loc[user_id]
    before = orchestrator.get_database_counts()

    with pytest.raises(DeletedUserError):
        orchestrator.ingest_record(
            {
                "user_id": user_id,
                "region": source["region"],
                "signal_a": source["signal_a"],
                "signal_b": source["signal_b"],
                "target": source["target"],
            }
        )
    assert orchestrator.get_database_counts() == before


def test_verification_exception_can_be_retried_without_changing_execution(
    orchestrator, monkeypatch
):
    user_id = choose_deletion_user()
    real_fit = orchestrator_module.fit_independent_reference

    def fail_reference(*args, **kwargs):
        raise RuntimeError("temporary reference trainer failure")

    monkeypatch.setattr(
        orchestrator_module, "fit_independent_reference", fail_reference
    )
    with pytest.raises(RuntimeError, match="temporary reference trainer failure"):
        orchestrator.request_deletion(user_id)

    deletion_id = orchestrator.list_workflows()[0]["deletion_id"]
    failed = orchestrator.get_workflow(deletion_id)
    assert failed["execution_status"] == "COMPLETED"
    assert failed["verification_status"] == "FAILED"
    attempts = orchestrator.get_verification_attempts(deletion_id)
    assert [attempt["status"] for attempt in attempts] == ["FAILED"]
    assert "temporary reference trainer failure" in attempts[0]["error_text"]

    monkeypatch.setattr(orchestrator_module, "fit_independent_reference", real_fit)
    report = orchestrator.verify_deletion(deletion_id)
    attempts = orchestrator.get_verification_attempts(deletion_id)

    assert report["passed"] is True
    assert [attempt["status"] for attempt in attempts] == ["FAILED", "PASSED"]
    assert orchestrator.get_workflow(deletion_id)["execution_status"] == "COMPLETED"
    assert orchestrator.get_workflow(deletion_id)["verification_status"] == "PASSED"
    events = orchestrator.get_audit_events(limit=20)
    event_types = [event["event_type"] for event in events]
    assert event_types.count("verification_attempt_started") == 2
    assert "verification_attempt_failed" in event_types
    assert "verification_attempt_completed" in event_types


def test_retry_marks_abandoned_running_verification_attempt_failed(orchestrator):
    user_id = choose_deletion_user()
    result = orchestrator.request_deletion(user_id)
    with sqlite3.connect(orchestrator.database_path) as connection:
        connection.execute(
            """
            UPDATE deletion_workflows
            SET verification_status = 'RUNNING', verification_report_json = NULL
            WHERE deletion_id = ?
            """,
            (result["deletion_id"],),
        )
        connection.execute(
            """
            INSERT INTO verification_attempts
            (deletion_id, attempt_number, started_at, status)
            VALUES (?, 2, 'simulated-interruption', 'RUNNING')
            """,
            (result["deletion_id"],),
        )

    report = orchestrator.verify_deletion(result["deletion_id"])
    attempts = orchestrator.get_verification_attempts(result["deletion_id"])

    assert report["passed"] is True
    assert [attempt["status"] for attempt in attempts] == [
        "PASSED",
        "FAILED",
        "PASSED",
    ]
    assert "Superseded by retry" in attempts[1]["error_text"]
    assert orchestrator.get_workflow(result["deletion_id"])["execution_status"] == "COMPLETED"
    assert any(
        event["event_type"] == "verification_attempt_interrupted"
        for event in orchestrator.get_audit_events(limit=20)
    )


def test_crash_and_restart_resumes_without_duplicate_effects(orchestrator):
    user_id = choose_deletion_user()

    with pytest.raises(SimulatedCrash) as raised:
        orchestrator.request_deletion(user_id, fail_after_step="recompute_features")

    deletion_id = raised.value.deletion_id
    interrupted = orchestrator.get_workflow(deletion_id)
    assert interrupted["execution_status"] == "RUNNING"
    assert [step["status"] for step in interrupted["steps"]] == [
        "COMPLETED",
        "COMPLETED",
        "PENDING",
        "PENDING",
    ]

    restarted = ForgetGraphOrchestrator(
        database_path=orchestrator.database_path,
        dataset_path=DATASET,
        config_path=CONFIG,
    )
    result = restarted.resume_workflow(deletion_id)
    workflow = restarted.get_workflow(deletion_id)

    assert result["execution_status"] == "COMPLETED"
    assert result["verification_status"] == "PASSED"
    assert [step["status"] for step in workflow["steps"]] == ["COMPLETED"] * 4
    assert len(workflow["steps"]) == 4
    assert [
        (step["step_name"], step["effect_count"]) for step in workflow["steps"]
    ] == [
        ("remove_source", 1),
        ("recompute_features", 699),
        ("invalidate_cache", 700),
        ("replace_model", 1),
    ]
    assert restarted.get_database_counts()["source_records"] == 699
    assert restarted.get_user_state(user_id) == {
        "source": False,
        "features": False,
        "cache": False,
    }


@pytest.mark.parametrize(
    "failed_step",
    [
        "remove_source",
        "recompute_features",
        "invalidate_cache",
        "replace_model",
    ],
)
def test_ordinary_failure_at_each_stage_can_resume_without_duplicate_effects(
    orchestrator, monkeypatch, failed_step
):
    user_id = choose_deletion_user()
    apply_step = orchestrator._apply_step

    def fail_selected_step(connection, step_name, user_hash):
        if step_name == failed_step:
            raise RuntimeError(f"injected ordinary failure at {step_name}")
        return apply_step(connection, step_name, user_hash)

    monkeypatch.setattr(orchestrator, "_apply_step", fail_selected_step)
    with pytest.raises(RuntimeError, match=f"injected ordinary failure at {failed_step}"):
        orchestrator.request_deletion(user_id)

    deletion_id = orchestrator.list_workflows()[0]["deletion_id"]
    failed_workflow = orchestrator.get_workflow(deletion_id)
    assert failed_workflow["execution_status"] == "FAILED"
    assert failed_workflow["verification_status"] == "NOT_RUN"
    assert next(
        step for step in failed_workflow["steps"] if step["step_name"] == failed_step
    )["status"] == "FAILED"

    monkeypatch.setattr(orchestrator, "_apply_step", apply_step)
    result = orchestrator.resume_workflow(deletion_id)
    completed_workflow = orchestrator.get_workflow(deletion_id)
    assert result["execution_status"] == "COMPLETED"
    assert result["verification_status"] == "PASSED"
    assert [step["status"] for step in completed_workflow["steps"]] == [
        "COMPLETED"
    ] * 4
    assert [
        (step["step_name"], step["effect_count"])
        for step in completed_workflow["steps"]
    ] == [
        ("remove_source", 1),
        ("recompute_features", 699),
        ("invalidate_cache", 700),
        ("replace_model", 1),
    ]


def test_database_reinitialization_from_csv_reintroduces_deleted_ids(tmp_path):
    database_path = tmp_path / "reset.sqlite"
    first_instance = ForgetGraphOrchestrator(
        database_path=database_path, dataset_path=DATASET, config_path=CONFIG
    )
    user_id = choose_deletion_user()
    first_instance.request_deletion(user_id)
    assert first_instance.is_tombstoned(user_id) is True
    assert first_instance.get_user_state(user_id)["source"] is False

    database_path.unlink()
    reinitialized = ForgetGraphOrchestrator(
        database_path=database_path, dataset_path=DATASET, config_path=CONFIG
    )

    assert reinitialized.is_tombstoned(user_id) is False
    assert reinitialized.get_user_state(user_id)["source"] is True
    assert reinitialized.get_database_counts()["source_records"] == 700
