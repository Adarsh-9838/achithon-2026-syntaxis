import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from forgetgraph import (  # noqa: E402
    ForgetGraphOrchestrator,
    SimulatedCrash,
    UnknownUserError,
)


st.set_page_config(
    page_title="FORGETGRAPH | Data deletion control plane",
    page_icon="FG",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --fg-ink: #13243a;
        --fg-muted: #607087;
        --fg-line: #e4eaf1;
        --fg-blue: #2457d6;
        --fg-blue-soft: #eaf0ff;
        --fg-green: #17865b;
        --fg-green-soft: #e8f6ef;
        --fg-amber: #9a6411;
        --fg-amber-soft: #fff5df;
        --fg-red: #b42335;
        --fg-red-soft: #fff0f1;
    }
    .stApp {
        background: #f6f8fb;
        color: var(--fg-ink);
    }
    [data-testid="stHeader"] { background: rgba(246, 248, 251, .82); }
    [data-testid="stSidebar"] {
        background: #101d31;
        border-right: 1px solid #23344c;
    }
    [data-testid="stSidebar"] * { color: #e8eef8; }
    [data-testid="stSidebar"] [data-testid="stMetric"] {
        background: #1b2b43;
        border: 1px solid #2d4260;
        padding: 12px 14px;
        box-shadow: none;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"],
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] p {
        color: #b6c6dc !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"],
    [data-testid="stSidebar"] [data-testid="stMetricValue"] div {
        color: #ffffff !important;
    }
    .block-container { max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--fg-ink); letter-spacing: -.025em; }
    h1 { font-size: 2.45rem; font-weight: 750; }
    h2 { font-size: 1.42rem; font-weight: 700; }
    h3 { font-size: 1.08rem; font-weight: 700; }
    p, li { color: #405168; }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--fg-line);
        border-radius: 14px;
        padding: 17px 19px;
        box-shadow: 0 2px 8px rgba(19, 36, 58, .035);
    }
    [data-testid="stMetricLabel"] { color: var(--fg-muted); font-weight: 600; }
    [data-testid="stMetricValue"] { color: var(--fg-ink); font-size: 1.8rem; }
    [data-testid="stTabs"] button { font-weight: 650; }
    [data-testid="stTabs"] [aria-selected="true"] { color: var(--fg-blue); }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff;
        border-color: var(--fg-line);
        border-radius: 15px;
        box-shadow: 0 2px 10px rgba(19, 36, 58, .035);
    }
    [data-testid="stForm"] {
        background: #ffffff;
        border: 1px solid var(--fg-line);
        border-radius: 15px;
        padding: 20px;
    }
    .fg-eyebrow {
        color: var(--fg-blue);
        font-size: .73rem;
        font-weight: 800;
        letter-spacing: .13em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }
    .fg-subtitle { color: var(--fg-muted); font-size: 1.03rem; margin-top: -.5rem; }
    .fg-card {
        background: #fff;
        border: 1px solid var(--fg-line);
        border-radius: 15px;
        padding: 18px 20px;
        box-shadow: 0 2px 10px rgba(19, 36, 58, .035);
        min-height: 112px;
    }
    .fg-card-label { color: var(--fg-muted); font-size: .82rem; font-weight: 650; }
    .fg-card-value { color: var(--fg-ink); font-size: 1.35rem; font-weight: 760; margin-top: .55rem; }
    .fg-card-detail { color: var(--fg-muted); font-size: .8rem; margin-top: .25rem; }
    .fg-pill {
        display: inline-block;
        border-radius: 999px;
        padding: .3rem .7rem;
        font-size: .75rem;
        font-weight: 750;
        background: var(--fg-green-soft);
        color: var(--fg-green);
    }
    .fg-pill-blue { background: var(--fg-blue-soft); color: var(--fg-blue); }
    .fg-pill-amber { background: var(--fg-amber-soft); color: var(--fg-amber); }
    .fg-pill-red { background: var(--fg-red-soft); color: var(--fg-red); }
    .fg-legend {
        color: var(--fg-muted);
        font-size: .79rem;
        display: flex;
        flex-wrap: wrap;
        gap: .55rem 1.15rem;
        padding: .2rem .1rem;
    }
    .fg-dot {
        display: inline-block;
        width: .63rem;
        height: .63rem;
        border-radius: 50%;
        margin-right: .38rem;
    }
    .fg-note {
        border-left: 3px solid #d59a28;
        background: #fff8e9;
        color: #654b1c;
        padding: .8rem 1rem;
        border-radius: 0 9px 9px 0;
        font-size: .87rem;
    }
    .fg-footer {
        color: #77859a;
        font-size: .76rem;
        border-top: 1px solid var(--fg-line);
        padding-top: 1rem;
        margin-top: 2rem;
    }
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            scroll-behavior: auto !important;
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_orchestrator():
    return ForgetGraphOrchestrator(
        database_path=PROJECT_DIR / "data" / "forgetgraph.sqlite",
        dataset_path=PROJECT_DIR / "data" / "synthetic_users.csv",
        config_path=PROJECT_DIR / "config.json",
    )


def graphviz_source(graph: dict, affected: set[str] | None = None) -> str:
    affected = affected or set()
    colors = {
        "source_records": "#dce8ff",
        "engineered_features": "#dce8ff",
        "ridge_model": "#e9e2ff",
        "prediction_cache": "#fff0cb",
    }
    lines = [
        "digraph ForgetGraph {",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.22", nodesep="0.62", ranksep="0.78"];',
        '  node [shape="box", style="rounded,filled", fontname="Arial", fontsize="12", margin="0.20,0.14", color="#ccd6e3", penwidth="1.25", fontcolor="#13243a"];',
        '  edge [fontname="Arial", fontsize="9", fontcolor="#708097", color="#9aabc0", penwidth="1.5", arrowsize="0.75"];',
    ]
    for node in graph["nodes"]:
        node_id = node["id"]
        count_label = {
            "source_records": "source rows",
            "engineered_features": "feature rows",
            "prediction_cache": "predictions",
            "ridge_model": "model",
        }[node_id]
        fill = "#e7f6ed" if node["count"] else "#fff2d6"
        if node_id == "ridge_model":
            fill = "#e9e2ff"
        color = "#7a62c7" if node_id in affected else "#ccd6e3"
        width = "2.3" if node_id in affected else "1.25"
        lines.append(
            f'  {node_id} [label="{node["label"]}\\n{node["count"]:,} {count_label}", '
            f'fillcolor="{fill}", color="{color}", penwidth="{width}"];'
        )
    for edge in graph["edges"]:
        edge_affected = edge["source"] in affected or edge["target"] in affected
        edge_color = "#7a62c7" if edge_affected else "#9aabc0"
        edge_width = "2.0" if edge_affected else "1.4"
        lines.append(
            f'  {edge["source"]} -> {edge["target"]} '
            f'[color="{edge_color}", penwidth="{edge_width}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def section_heading(title: str, description: str | None = None) -> None:
    st.subheader(title)
    if description:
        st.caption(description)


def status_emoji(status: str) -> str:
    return {
        "COMPLETED": "✅",
        "PASSED": "✅",
        "RUNNING": "🔄",
        "PENDING": "◷",
        "FAILED": "❌",
        "NOT_RUN": "—",
    }.get(status, "•")


def status_label(status: str) -> str:
    return {
        "COMPLETED": "Completed",
        "PASSED": "Passed",
        "RUNNING": "In progress",
        "PENDING": "Waiting",
        "FAILED": "Failed",
        "NOT_RUN": "Not checked yet",
    }.get(status, status.replace("_", " ").title())


STEP_DETAILS = {
    "remove_source": "Remove this user's source record.",
    "recompute_features": "Rebuild features, including group averages, from retained users.",
    "invalidate_cache": "Clear saved predictions because the model or features changed.",
    "replace_model": "Train and save the replacement model.",
}

WORKFLOW_STAGES = (
    ("remove_source", "Remove source record", "Remove this user's original record."),
    (
        "recompute_features",
        "Rebuild feature rows",
        "Recalculate values and group averages for retained users.",
    ),
    (
        "invalidate_cache",
        "Clear saved predictions",
        "Remove predictions that may rely on the deleted user or old model.",
    ),
    (
        "replace_model",
        "Train replacement model",
        "Fit the model again using only retained users.",
    ),
)

VERIFICATION_FAILURES = {
    "deleted_user_absent": "The deleted user's data remains in a source, feature, or cache table.",
    "tombstone_present": "The saved block for this deleted user is missing.",
    "features_match_source": "Feature rows do not match the retained source records.",
    "coefficients_match": "The replacement model's coefficients do not match the reference.",
    "intercept_match": "The replacement model's intercept does not match the reference.",
    "predictions_match": "Predictions from the replacement and reference models differ.",
}


orchestrator = get_orchestrator()
graph = orchestrator.get_artifact_graph()
counts = orchestrator.get_database_counts()
workflow_rows = orchestrator.list_workflows(limit=max(counts["workflows"], 1))
certificate_rows = orchestrator.list_certificates(
    limit=max(counts["workflows"], 1)
)
active_model_count = next(
    (node["count"] for node in graph["nodes"] if node["id"] == "ridge_model"), 0
)

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.75rem;font-weight:800;color:white;margin:.25rem 0 0;">FORGETGRAPH</div>'
        '<div style="color:#aab9ce;font-size:.86rem;margin:.25rem 0 1.4rem;">PS09 · Data deletion demo</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption("Local demo · SQLite persistence · Synthetic records")
    st.caption("No external API calls or credentials")

st.markdown('<div class="fg-eyebrow">PS09 · DATA DELETION DEMO</div>', unsafe_allow_html=True)
st.title("Deletion operations")
st.markdown(
    '<div class="fg-subtitle">Remove a synthetic user from the pipeline, follow each step, and check the replacement model independently.</div>',
    unsafe_allow_html=True,
)
st.caption(
    "**Artifact** means a file or data product created by the pipeline. "
    "**Tombstone** means a saved block that prevents a deleted user from being added again."
)
st.write("")

overview_tab, deletion_tab, verification_tab, certificate_tab, audit_tab = st.tabs(
    [
        "Overview",
        "Deletion workflow",
        "Verification",
        "Evidence Certificates",
        "Audit trail",
    ]
)

with overview_tab:
    section_heading(
        "Current database state",
        "These counts describe the database now. Completed deletions count finished workflows; tombstones count blocked IDs, so the numbers may differ.",
    )
    metric_data = (
        ("Source records", counts["source_records"], "Synthetic users currently stored"),
        ("Feature rows", counts["feature_rows"], "Calculated values currently stored"),
        ("Prediction cache", counts["prediction_cache"], "Saved predictions currently stored"),
        ("Models", active_model_count, "Active model artifacts in the pipeline"),
        (
            "Completed deletions",
            sum(row["execution_status"] == "COMPLETED" for row in workflow_rows),
            "Workflows whose deletion steps finished",
        ),
        ("Tombstones", counts["tombstones"], "IDs blocked from managed re-ingestion"),
    )
    for row_start in range(0, len(metric_data), 3):
        metric_columns = st.columns(3)
        for column, (label, value, detail) in zip(
            metric_columns, metric_data[row_start : row_start + 3]
        ):
            column.metric(label, f"{value:,}", help=detail)

    st.caption(
        "Feature rows are calculated values used by the model. A model is the trained prediction system. "
        "A cache stores saved predictions; "
        "it may be empty after deletion because it is cleared and is not automatically refilled."
    )
    section_heading(
        "Pipeline dependencies",
        "This graph shows the overall pipeline structure; it does not change shape for each user. "
        "Arrows show which products depend on earlier products.",
    )
    st.graphviz_chart(graphviz_source(graph), width="stretch")
    st.markdown(
        '<div class="fg-legend">'
        '<span><i class="fg-dot" style="background:#e7f6ed"></i>Data product with records</span>'
        '<span><i class="fg-dot" style="background:#e9e2ff"></i>Trained model</span>'
        '<span><i class="fg-dot" style="background:#fff2d6"></i>Empty data product</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    if workflow_rows:
        latest = workflow_rows[0]
        st.caption(
            "Latest deletion: "
            f"{status_emoji(latest['execution_status'])} "
            f"{status_label(latest['execution_status'])}; independent verification "
            f"{status_emoji(latest['verification_status'])} "
            f"{status_label(latest['verification_status'])}."
        )
    st.info(
        "This local demonstration supports one user and one process at a time. "
        "Do not run overlapping deletion or resume actions."
    )

with deletion_tab:
    section_heading(
        "Delete one synthetic user",
        "Enter an ID from the sample data. Review the affected products before starting; the deletion is permanent in this database.",
    )
    form_column, impact_column = st.columns([1, 1], gap="large")
    with form_column:
        user_id = st.text_input(
            "User ID",
            placeholder="user-0002",
            key="deletion_user_id",
            help="Use an active ID from the synthetic sample data. A completed deletion cannot be undone in this database.",
        ).strip()
        inject_failure = st.checkbox(
            "Test recovery by simulating an interruption",
            help="For demonstration only: the selected step is saved, then the workflow pauses so you can resume it.",
        )
        failure_step = st.selectbox(
            "Pause after step",
            (
                "remove_source",
                "recompute_features",
                "invalidate_cache",
                "replace_model",
            ),
            format_func=lambda step: STEP_DETAILS[step].split(".")[0],
            disabled=not inject_failure,
        )
        if st.button("Run deletion", type="primary", width="stretch"):
            if not user_id:
                st.error("Enter a user ID before starting.")
            else:
                try:
                    result = orchestrator.request_deletion(
                        user_id,
                        fail_after_step=failure_step if inject_failure else None,
                    )
                except SimulatedCrash as error:
                    st.session_state["selected_workflow"] = error.deletion_id
                    st.warning(
                        f"Deletion paused after “{STEP_DETAILS[error.step_name]}” "
                        "The completed step is saved; resume the workflow below."
                    )
                    st.rerun()
                except UnknownUserError as error:
                    st.error(f"That user ID was not found. {error}")
                except (RuntimeError, ValueError, sqlite3.Error) as error:
                    st.error(
                        "The deletion request could not finish. Check the saved progress "
                        "below before retrying. "
                        f"Details: {error}"
                    )
                else:
                    if result.get("already_deleted"):
                        st.info(
                            "This user is already deleted. No database changes were made."
                        )
                    else:
                        st.session_state["selected_workflow"] = result["deletion_id"]
                        st.rerun()
        st.caption(
            "Unknown IDs are rejected without creating a deletion record. "
            "Repeating a completed request makes no further changes."
        )

    with impact_column:
        with st.container(border=True):
            section_heading(
                "Artifacts affected by this user",
                "This graph keeps the overall pipeline shape. The outlined nodes and arrows show this user's saved links to products; arrows indicate downstream dependencies.",
            )
            affected_artifacts = set(
                orchestrator.get_affected_artifacts(user_id) if user_id else []
            )
            selected_workflow_id = st.session_state.get("selected_workflow")
            if user_id and not affected_artifacts and selected_workflow_id:
                saved_workflow = orchestrator.get_workflow(selected_workflow_id)
                if saved_workflow["user_hash"] == orchestrator.hash_user_id(user_id):
                    affected_artifacts = set(saved_workflow["affected_artifacts"])
                    st.caption(
                        "This user is already deleted. Showing the artifacts saved in that deletion record."
                    )
            if affected_artifacts:
                st.write(
                    f"Products linked to this user: {', '.join(sorted(affected_artifacts))}"
                )
            elif user_id:
                st.info(
                    "No saved lineage found. Check that the ID belongs to an active sample user."
                )
            else:
                st.caption("Enter an ID to highlight artifacts associated with it.")
            st.graphviz_chart(
                graphviz_source(graph, affected_artifacts),
                width="stretch",
            )

    if workflow_rows:
        section_heading("Deletion progress")
        workflow_ids = [row["deletion_id"] for row in workflow_rows]
        selected_default = st.session_state.get("selected_workflow")
        default_index = (
            workflow_ids.index(selected_default)
            if selected_default in workflow_ids
            else 0
        )
        selected_id = st.selectbox(
            "Workflow",
            workflow_ids,
            index=default_index,
            format_func=lambda value: next(
                (
                    f"{value[:8]} · deletion {status_label(row['execution_status'])} · "
                    f"check {status_label(row['verification_status'])}"
                    for row in workflow_rows
                    if row["deletion_id"] == value
                ),
                value,
            ),
        )
        st.session_state["selected_workflow"] = selected_id
        workflow = orchestrator.get_workflow(selected_id)
        status_columns = st.columns(2)
        status_columns[0].metric(
            "Deletion steps",
            f"{status_emoji(workflow['execution_status'])} "
            f"{status_label(workflow['execution_status'])}",
            help="Execution status: whether all deletion operations finished.",
        )
        status_columns[1].metric(
            "Independent verification",
            f"{status_emoji(workflow['verification_status'])} "
            f"{status_label(workflow['verification_status'])}",
            help="Verification means checking the new model against a separately trained reference model.",
        )
        if workflow["execution_status"] == "COMPLETED":
            if workflow["verification_status"] == "PASSED":
                st.success("Deletion steps completed. Independent verification passed.")
            elif workflow["verification_status"] == "FAILED":
                st.error(
                    "Deletion steps completed, but independent verification failed. "
                    "Review the Verification section before treating the request as successful."
                )
            else:
                st.warning(
                    "Deletion steps completed. Independent verification has not passed yet."
                )
        elif workflow["execution_status"] == "FAILED":
            st.error(
                "Deletion did not finish. Resolve the failed step below and resume before considering the deletion complete."
            )
        else:
            st.warning("Deletion is interrupted or still in progress. Resume it to continue.")
        st.caption(
            "Impacted artifacts: "
            + (", ".join(workflow["affected_artifacts"]) or "none recorded")
        )

        steps = workflow["steps"]
        if steps:
            completed = sum(step["status"] == "COMPLETED" for step in steps)
            st.progress(
                completed / len(steps),
                text=f"{completed} of {len(steps)} required steps completed",
            )
            step_by_name = {step["step_name"]: step for step in steps}
            stage_columns = st.columns(4)
            for column, (step_name, title, explanation) in zip(
                stage_columns, WORKFLOW_STAGES
            ):
                step = step_by_name.get(step_name)
                with column:
                    with st.container(border=True):
                        st.caption(
                            f"STEP {next(i for i, stage in enumerate(WORKFLOW_STAGES, 1) if stage[0] == step_name):02d}"
                        )
                        st.markdown(f"**{title}**")
                        if step is None:
                            stage_status = "Not needed"
                            if (
                                step_name == "invalidate_cache"
                                and workflow["counts_before"].get(
                                    "prediction_cache", 0
                                )
                                == 0
                            ):
                                stage_description = (
                                    "The cache was already empty; there were no saved predictions to clear."
                                )
                            else:
                                stage_description = (
                                    "This operation was not included in the recorded steps for this request."
                                )
                            st.write(f"➖ **{stage_status}**")
                            st.caption(stage_description)
                            continue
                        st.write(
                            f"{status_emoji(step['status'])} "
                            f"**{status_label(step['status'])}**"
                        )
                        st.caption(explanation)
                        st.caption(
                            f"Items changed: {step['effect_count']:,}"
                        )
                        if step["status"] == "FAILED" and step["error_text"]:
                            st.error(
                                f"Could not finish: {step['error_text']}. "
                                "Address the issue, then resume."
                            )
        if workflow["execution_status"] != "COMPLETED":
            if st.button(
                "Resume interrupted deletion",
                key=f"resume-{selected_id}",
                type="primary",
            ):
                try:
                    orchestrator.resume_workflow(selected_id)
                except (RuntimeError, ValueError, sqlite3.Error, KeyError) as error:
                    st.error(
                        "The deletion could not be resumed. "
                        f"Resolve the issue and try again. Details: {error}"
                    )
                else:
                    st.session_state["selected_workflow"] = selected_id
                    st.rerun()

        report = orchestrator.get_verification_report(selected_id)
        if report:
            st.markdown("---")
            section_heading(
                "This request: before and after",
                "These counts belong to the selected deletion request, not the current database totals.",
            )
            count_columns = st.columns(3)
            for column, artifact, label in zip(
                count_columns,
                ("source_records", "feature_rows", "prediction_cache"),
                ("Source records", "Feature rows", "Saved predictions"),
            ):
                column.metric(
                    label,
                    f"{report['counts_after'].get(artifact, 0):,}",
                    delta=f"{report['counts_after'].get(artifact, 0) - report['counts_before'].get(artifact, 0):,}",
                    help="Change from immediately before this workflow.",
                )
            st.info(
                (
                    f"Cache clearing removed {report['cache_invalidation_count']:,} saved "
                    "prediction(s). The cache is not automatically refilled."
                    if any(
                        step["step_name"] == "invalidate_cache"
                        for step in workflow["steps"]
                    )
                    else
                    "There were no cached predictions to clear for this request. "
                    "The cache is not automatically refilled."
                )
            )
    else:
        section_heading(
            "Deletion stages",
            "Each accepted request records the outcome and timestamps for these ordered operations.",
        )
        stage_columns = st.columns(4)
        for column, (_, title, explanation) in zip(stage_columns, WORKFLOW_STAGES):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    st.caption(explanation)
        st.caption(
            "The cache stage may find it already empty; until a request runs, these operations are not included in recorded workflow evidence."
        )

with verification_tab:
    section_heading(
        "Check the deletion and new model",
        "Verification means checking that the new model agrees with a separately trained reference model. It is separate from completing the deletion steps.",
    )
    if not workflow_rows:
        st.info("Run a deletion to show its results and independent model check.")
        status_columns = st.columns(2)
        status_columns[0].metric("Deletion steps", "Not run")
        status_columns[1].metric("Independent verification", "Not run")
        st.caption(
            "These are separate results: one describes the deletion operations; "
            "the other describes the independent model and data checks."
        )
    else:
        verification_ids = [row["deletion_id"] for row in workflow_rows]
        selected_for_report = st.selectbox(
            "Deletion request",
            verification_ids,
            key="verification_workflow",
            format_func=lambda value: next(
                (
                    f"{value[:8]} · deletion {status_label(row['execution_status'])} · "
                    f"verification {status_label(row['verification_status'])}"
                    for row in workflow_rows
                    if row["deletion_id"] == value
                ),
                value,
            ),
        )
        selected_status = next(
            row["verification_status"]
            for row in workflow_rows
            if row["deletion_id"] == selected_for_report
        )
        selected_workflow = orchestrator.get_workflow(selected_for_report)
        report = orchestrator.get_verification_report(selected_for_report)
        current_report_fields = {
            "tombstone_present",
            "max_reference_coefficient_abs_diff",
            "reference_intercept_abs_diff",
            "max_reference_prediction_abs_diff",
            "max_old_replacement_coefficient_abs_diff",
            "old_replacement_intercept_abs_diff",
        }
        legacy_report = report is not None and not current_report_fields.issubset(
            report
        )
        left, right = st.columns(2)
        left.metric(
            "Deletion steps",
            f"{status_emoji(selected_workflow['execution_status'])} "
            f"{status_label(selected_workflow['execution_status'])}",
        )
        right.metric(
            "Independent verification",
            f"{status_emoji(selected_status)} {status_label(selected_status)}",
        )
        if (
            selected_workflow["execution_status"] == "COMPLETED"
            and (selected_status != "PASSED" or legacy_report)
            and st.button(
                "Retry verification",
                key=f"retry-verification-{selected_for_report}",
                type="primary",
            )
        ):
            try:
                orchestrator.verify_deletion(selected_for_report)
            except (RuntimeError, ValueError, sqlite3.Error) as error:
                st.session_state["verification_retry_notice"] = (
                    "Verification could not finish. Deletion steps remain complete. "
                    f"Details: {error}"
                )
            else:
                st.session_state["verification_retry_notice"] = (
                    "Verification attempt completed; review the new persisted result below."
                )
            st.rerun()
        retry_notice = st.session_state.pop("verification_retry_notice", None)
        if retry_notice:
            if retry_notice.startswith("Verification could not finish."):
                st.error(retry_notice)
            else:
                st.info(retry_notice)
        if report is None:
            if (
                selected_workflow["execution_status"] == "COMPLETED"
                and selected_status == "FAILED"
            ):
                st.error(
                    "Independent verification failed before it could produce a report. "
                    "Deletion steps remain complete; retry after resolving the issue."
                )
            elif selected_workflow["execution_status"] != "COMPLETED":
                st.warning(
                    "Deletion steps have not completed, so verification is not available yet."
                )
            else:
                st.info("Independent verification has not been run yet.")
        else:
            if (
                selected_workflow["execution_status"] == "COMPLETED"
                and report["passed"]
            ):
                st.success("Deletion steps completed. Independent verification passed.")
            elif selected_workflow["execution_status"] != "COMPLETED":
                st.error(
                    "Deletion steps have not completed. A passing model comparison "
                    "does not mean the deletion is complete."
                )
            else:
                st.error(
                    "Independent verification did not pass: "
                    + " ".join(
                        VERIFICATION_FAILURES.get(reason, reason.replace("_", " "))
                        for reason in report["failure_reasons"]
                    )
                )
            if legacy_report:
                st.info(
                    "This saved report predates the current evidence fields. "
                    "Retry verification to persist tombstone and coefficient/intercept deltas."
                )
            check_rows = [
                {"Check": "Deleted ID absent from source, features, and cache", "Result": report["deleted_user_absent"]},
                {"Check": "Feature membership matches retained source", "Result": report["features_match_source"]},
                {"Check": "Replacement coefficients match reference", "Result": report["coefficients_match"]},
                {"Check": "Replacement intercept matches reference", "Result": report["intercept_match"]},
                {"Check": "Retained-user predictions match reference", "Result": report["predictions_match"]},
            ]
            if "tombstone_present" in report:
                check_rows.append(
                    {"Check": "Tombstone remains present", "Result": report["tombstone_present"]}
                )
            st.dataframe(
                pd.DataFrame(check_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "Result": st.column_config.CheckboxColumn("Passed", disabled=True)
                },
            )
            st.caption(
                "The old model may differ from the replacement, but that is evidence only "
                "and is not required for verification to pass."
            )
            model_rows = []
            feature_names = ("signal_a", "signal_b", "region_mean_signal_a")
            for index, feature in enumerate(feature_names):
                model_rows.append(
                    {
                        "Parameter": feature,
                        "Previous model": report["old_model"]["coefficients"][index],
                        "Replacement": report["replacement"]["coefficients"][index],
                        "Independent reference": report["reference"]["coefficients"][index],
                    }
                )
            model_rows.append(
                {
                    "Parameter": "intercept",
                    "Previous model": report["old_model"]["intercept"],
                    "Replacement": report["replacement"]["intercept"],
                    "Independent reference": report["reference"]["intercept"],
                }
            )
            st.markdown("#### Model parameter comparison")
            st.dataframe(
                pd.DataFrame(model_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "Previous model": st.column_config.NumberColumn(format="%.10f"),
                    "Replacement": st.column_config.NumberColumn(format="%.10f"),
                    "Independent reference": st.column_config.NumberColumn(format="%.10f"),
                },
            )
            if not legacy_report:
                evidence_columns = st.columns(5)
                evidence_columns[0].metric(
                    "Relative tolerance",
                    f"{report['rtol']:.1e}",
                    help="Allowed proportional difference when comparing model values.",
                )
                evidence_columns[1].metric(
                    "Absolute tolerance",
                    f"{report['atol']:.1e}",
                    help="Allowed small absolute difference when comparing model values.",
                )
                evidence_columns[2].metric(
                    "Max coefficient delta",
                    f"{report['max_reference_coefficient_abs_diff']:.2e}",
                    help="Maximum absolute replacement/reference coefficient difference.",
                )
                evidence_columns[3].metric(
                    "Intercept delta",
                    f"{report['reference_intercept_abs_diff']:.2e}",
                    help="Absolute replacement/reference intercept difference.",
                )
                evidence_columns[4].metric(
                    "Max prediction delta",
                    f"{report['max_reference_prediction_abs_diff']:.2e}",
                    help="Maximum absolute retained-user replacement/reference prediction difference.",
                )
                st.caption(
                    f"Old model differs from replacement: "
                    f"{'yes' if report['old_model_differs'] else 'no'}. "
                    f"Old-to-replacement maximum coefficient difference: "
                    f"{report['max_old_replacement_coefficient_abs_diff']:.2e}; "
                    f"intercept difference: "
                    f"{report['old_replacement_intercept_abs_diff']:.2e}. "
                    "These are evidence only, not pass conditions."
                )
            else:
                legacy_evidence = st.columns(3)
                legacy_evidence[0].metric(
                    "Relative tolerance",
                    f"{report['rtol']:.1e}",
                    help="Allowed proportional difference when comparing model values.",
                )
                legacy_evidence[1].metric(
                    "Absolute tolerance",
                    f"{report['atol']:.1e}",
                    help="Allowed small absolute difference when comparing model values.",
                )
                if "max_prediction_abs_diff" in report:
                    legacy_evidence[2].metric(
                        "Max prediction delta",
                        f"{report['max_prediction_abs_diff']:.2e}",
                    )

        st.caption(
            "Verification attempts and technical events are recorded in the Audit trail."
        )

with certificate_tab:
    section_heading(
        "Deletion evidence certificates",
        "One certificate identity per accepted request. Updates preserve earlier integrity-sealed evidence snapshots in its history.",
    )
    if not certificate_rows:
        st.info("Accepted deletion requests will appear here with their evidence.")
    else:
        certificate_ids = [row["deletion_id"] for row in certificate_rows]
        selected_certificate_id = st.selectbox(
            "Deletion request",
            certificate_ids,
            key="certificate_request",
            format_func=lambda value: next(
                (
                    f"{row['certificate_id'][:8]} · {row['status']} · "
                    f"request {value[:8]}"
                    for row in certificate_rows
                    if row["deletion_id"] == value
                ),
                value,
            ),
        )
        certificate = orchestrator.get_certificate(selected_certificate_id)
        document = certificate["document"]
        if not certificate["integrity_valid"]:
            st.error(
                "Certificate integrity validation failed. Treat this certificate as FAILED."
            )
        elif certificate["status"] == "VERIFIED":
            st.success("VERIFIED · execution and independent verification evidence are complete.")
        elif certificate["status"] == "FAILED":
            st.error("FAILED · recorded execution or independent verification did not pass.")
        else:
            st.warning("INCOMPLETE · required execution or independent verification evidence is missing.")

        request = document["request"]
        st.write(
            f"**Certificate ID:** `{certificate['certificate_id']}`  \n"
            f"**Request ID:** `{request['request_id']}`  \n"
            f"**Requested at:** {request['requested_at']}  \n"
            f"**Affected artifact IDs:** {', '.join(request['affected_artifact_ids']) or 'none recorded'}"
        )
        st.caption(
            "Deleted source record IDs are one-way SHA-256 user-ID hashes; raw identifiers are not included."
        )
        st.json(request["deleted_source_record_ids"])

        execution_column, verification_column = st.columns(2)
        with execution_column:
            st.markdown("#### Execution evidence")
            st.caption(
                f"Execution status: {document['execution_evidence']['status']}"
            )
            st.json(document["execution_evidence"])
        with verification_column:
            st.markdown("#### Independent verification evidence")
            st.caption(
                f"Verification status: {document['verification_evidence']['status']}"
            )
            st.json(document["verification_evidence"])

        st.code(certificate["integrity_hash"], language=None)
        st.caption(
            f"SHA-256 integrity valid: {'yes' if certificate['integrity_valid'] else 'no'} · "
            f"Certificate revision {certificate['version']} · created {certificate['created_at']}"
        )
        st.download_button(
            "Download certificate JSON",
            data=json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False),
            file_name=f"deletion-certificate-{certificate['certificate_id']}.json",
            mime="application/json",
            key=f"download-certificate-{selected_certificate_id}",
        )

        history = orchestrator.get_certificate_history(selected_certificate_id)
        st.markdown("#### Certificate history")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Revision": revision["version"],
                        "Status": revision["status"],
                        "Recorded at": revision["recorded_at"],
                        "Reason": revision["reason"],
                        "Integrity valid": revision["integrity_valid"],
                    }
                    for revision in history
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Earlier FAILED or INCOMPLETE revisions remain in history when a retry records new evidence; retries never create another certificate ID for the request."
        )
        st.warning(document["integrity_scope"])

with verification_tab:
    with st.expander("Security and prototype limits"):
        section_heading(
            "Security and privacy controls",
            "Concrete controls implemented in this prototype, plus explicit production gaps.",
        )
        security_rows = [
            {
                "Control": "Identifier minimization",
                "Status": "Implemented",
                "Evidence": "SQLite stores SHA-256 user-ID hashes in source keys, lineage, and tombstones.",
                "Boundary": "Hashing is pseudonymization, not anonymization; low-entropy IDs can be guessed.",
            },
            {
                "Control": "Re-ingestion prevention",
                "Status": "Implemented",
                "Evidence": "Managed ingestion checks the persistent tombstone registry before insert.",
                "Boundary": "Only ingestion through this application is guarded.",
            },
            {
                "Control": "Repeated-request safety",
                "Status": "Implemented",
                "Evidence": "Tombstoned requests return already deleted without new workflow effects.",
                "Boundary": "Concurrent multi-host orchestration is outside this local prototype.",
            },
            {
                "Control": "Concurrency boundary",
                "Status": "Single user / process only",
                "Evidence": "SQLite transactions persist individual state changes.",
                "Boundary": "No workflow lock; simultaneous requests or resumes are unsupported.",
            },
            {
                "Control": "Database query handling",
                "Status": "Implemented",
                "Evidence": "User-supplied values use SQLite parameter binding.",
                "Boundary": "Protect the database file and runtime host in a real deployment.",
            },
            {
                "Control": "Auditability",
                "Status": "Implemented",
                "Evidence": "Persisted steps, timestamps, effect counts, outcomes, and verification evidence.",
                "Boundary": "SQLite file owners can alter local database contents.",
            },
            {
                "Control": "Authentication / authorization",
                "Status": "Not provided",
                "Evidence": "Dashboard is intended for a trusted local demo.",
                "Boundary": "Production deployment requires identity, role checks, and protected access.",
            },
            {
                "Control": "Encryption and backups",
                "Status": "Not provided",
                "Evidence": "SQLite is stored locally without application-level encryption.",
                "Boundary": "Production must define encryption, backup erasure, retention, and key handling.",
            },
            {
                "Control": "External-system deletion",
                "Status": "Not provided",
                "Evidence": "All artifacts are synthetic and local to this demo.",
                "Boundary": "Production needs verified adapters and lineage for every external store.",
            },
        ]
        st.dataframe(
            pd.DataFrame(security_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "Control": st.column_config.TextColumn("Control", width="medium"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Evidence": st.column_config.TextColumn("Implemented evidence", width="large"),
                "Boundary": st.column_config.TextColumn("Limit / production gap", width="large"),
            },
        )
        st.markdown(
            '<div class="fg-note"><strong>Deployment boundary:</strong> this prototype demonstrates deletion orchestration and verification; it is not a production security certification or a connection to external data systems.</div>',
            unsafe_allow_html=True,
        )

with audit_tab:
    section_heading(
        "Operational audit trail",
        "Newest events first. User identifiers are represented by hashes in persisted event details.",
    )
    audit_rows = orchestrator.get_audit_events(limit=250)
    if audit_rows:
        audit_frame = pd.DataFrame(audit_rows)
        audit_frame["created_at"] = pd.to_datetime(
            audit_frame["created_at"], utc=True
        )
        st.dataframe(
            audit_frame,
            hide_index=True,
            width="stretch",
            column_config={
                "event_id": st.column_config.NumberColumn("Event", format="%d"),
                "deletion_id": st.column_config.TextColumn("Workflow ID", width="medium"),
                "event_type": st.column_config.TextColumn("Event", width="medium"),
                "details": st.column_config.TextColumn("Details", width="large"),
                "created_at": st.column_config.DatetimeColumn("Recorded at", format="YYYY-MM-DD HH:mm:ss"),
            },
        )
    else:
        st.info("No audit events have been recorded.")
    st.caption(f"Showing up to 250 most recent events · {len(audit_rows)} displayed.")

st.markdown(
    '<div class="fg-footer">FORGETGRAPH · PS09 prototype · Synthetic data only · Execution and verification are independent records</div>',
    unsafe_allow_html=True,
)
