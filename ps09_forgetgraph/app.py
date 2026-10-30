import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from forgetgraph import (  # noqa: E402
    DeletedUserError,
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
        background:
            radial-gradient(ellipse at 92% 0%, rgba(36, 87, 214, .06), transparent 34rem),
            #f6f8fb;
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


orchestrator = get_orchestrator()
graph = orchestrator.get_artifact_graph()
counts = orchestrator.get_database_counts()
workflow_rows = orchestrator.list_workflows()

with st.sidebar:
    st.markdown(
        '<div style="font-size:.76rem;font-weight:800;letter-spacing:.16em;color:#9eb8ff;">CONTROL PLANE</div>'
        '<div style="font-size:1.75rem;font-weight:800;color:white;margin:.25rem 0 0;">FORGETGRAPH</div>'
        '<div style="color:#aab9ce;font-size:.86rem;margin:.25rem 0 1.4rem;">PS09 · ML data deletion</div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Pipeline health")
    st.metric("Source records", f"{counts['source_records']:,}")
    st.metric("Feature rows", f"{counts['feature_rows']:,}")
    st.metric("Prediction cache", f"{counts['prediction_cache']:,}")
    st.metric("Deletion tombstones", f"{counts['tombstones']:,}")
    st.divider()
    st.caption("Local demo · SQLite persistence · Synthetic records")
    st.caption("No external API calls or credentials")
    st.warning("Single-process, single-user demo. Do not run overlapping requests.")

st.markdown('<div class="fg-eyebrow">DATA LIFECYCLE GOVERNANCE</div>', unsafe_allow_html=True)
st.title("Deletion operations")
st.markdown(
    '<div class="fg-subtitle">Trace user impact through the ML pipeline, execute an auditable deletion, and independently verify the replacement model.</div>',
    unsafe_allow_html=True,
)
st.write("")

overview_tab, deletion_tab, verification_tab, guided_demo_tab, audit_tab = st.tabs(
    [
        "Overview",
        "Deletion workflow",
        "Verification & security",
        "Guided demo",
        "Audit trail",
    ]
)

with overview_tab:
    section_heading(
        "Pipeline at a glance",
        "Lineage is persisted in SQLite. Select an ID in the workflow tab to highlight its recorded impact.",
    )
    metric_columns = st.columns(4)
    metric_data = (
        ("Source records", counts["source_records"], "Synthetic source dataset"),
        ("Engineered features", counts["feature_rows"], "Includes regional aggregates"),
        ("Prediction cache", counts["prediction_cache"], "Invalidated on model update"),
        ("Completed requests", sum(row["execution_status"] == "COMPLETED" for row in workflow_rows), "Persisted deletion workflows"),
    )
    for column, (label, value, detail) in zip(metric_columns, metric_data):
        column.metric(label, f"{value:,}", help=detail)

    section_heading("Artifact dependency graph")
    st.graphviz_chart(graphviz_source(graph), width="stretch")
    st.markdown(
        '<div class="fg-legend">'
        '<span><i class="fg-dot" style="background:#e7f6ed"></i>Populated data artifact</span>'
        '<span><i class="fg-dot" style="background:#e9e2ff"></i>Model artifact</span>'
        '<span><i class="fg-dot" style="background:#fff2d6"></i>Empty / invalidated data artifact</span>'
        '<span><i class="fg-dot" style="background:#7a62c7"></i>Impacted by selected request</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.2, 1])
    with left:
        with st.container(border=True):
            section_heading("Deletion sequence")
            st.markdown(
                "1. **Remove** the source record  \n"
                "2. **Recompute** aggregate features  \n"
                "3. **Invalidate** cached predictions  \n"
                "4. **Replace** the Ridge model and verify it independently"
            )
    with right:
        with st.container(border=True):
            section_heading("Latest workflow")
            if workflow_rows:
                latest = workflow_rows[0]
                st.write(f"Execution: **{latest['execution_status']}**")
                st.write(f"Verification: **{latest['verification_status']}**")
                st.caption(f"Workflow `{latest['deletion_id'][:8]}`")
            else:
                st.info("No deletion requests yet. Start one in the Deletion workflow tab.")
    st.warning(
        "Concurrency boundary: this SQLite prototype supports one process and one "
        "user at a time; it does not lock concurrent deletion or resume requests."
    )

with deletion_tab:
    section_heading(
        "Request and track a deletion",
        "This demo accepts identifiers from the committed synthetic dataset only: user-0000 through user-0699.",
    )
    form_column, impact_column = st.columns([1, 1], gap="large")
    with form_column:
        with st.form("deletion_request"):
            user_id = st.text_input(
                "Synthetic user ID",
                placeholder="user-0002",
                help="Use an active ID from data/synthetic_users.csv.",
            )
            inject_failure = st.checkbox(
                "Inject a simulated crash for recovery testing",
                help="The chosen step commits, then execution stops so Resume can demonstrate recovery.",
            )
            failure_step = st.selectbox(
                "Simulate crash after",
                (
                    "remove_source",
                    "recompute_features",
                    "invalidate_cache",
                    "replace_model",
                ),
                disabled=not inject_failure,
            )
            submitted = st.form_submit_button(
                "Run deletion workflow", type="primary", width="stretch"
            )
        st.caption(
            "Repeated requests are idempotent. Unknown IDs are rejected without a workflow or tombstone."
        )
        if submitted:
            if not user_id.strip():
                st.error("Enter a synthetic user ID.")
            else:
                try:
                    result = orchestrator.request_deletion(
                        user_id.strip(),
                        fail_after_step=failure_step if inject_failure else None,
                    )
                except SimulatedCrash as error:
                    st.warning(
                        f"Simulated interruption after {error.step_name}. "
                        "The committed workflow can be resumed."
                    )
                    st.session_state["selected_workflow"] = error.deletion_id
                    st.rerun()
                except UnknownUserError as error:
                    st.error(str(error))
                else:
                    if result.get("already_deleted"):
                        st.info("Already deleted. No database state was changed.")
                    else:
                        st.session_state["selected_workflow"] = result["deletion_id"]
                        st.success(
                            f"Execution {result['execution_status']} · "
                            f"verification {result['verification_status']}"
                        )
                        st.rerun()

    with impact_column:
        with st.container(border=True):
            section_heading("Recorded impact preview")
            preview_id = st.text_input(
                "Preview an ID",
                key="impact_preview_id",
                placeholder="Type an ID to inspect lineage",
                label_visibility="collapsed",
            )
            affected_artifacts = (
                set(orchestrator.get_affected_artifacts(preview_id.strip()))
                if preview_id.strip()
                else set()
            )
            if preview_id.strip() and affected_artifacts:
                st.success(
                    f"{len(affected_artifacts)} active artifacts in recorded lineage."
                )
                st.write(", ".join(sorted(affected_artifacts)))
            elif preview_id.strip():
                st.info(
                    "No active artifact lineage found. The ID may be unknown or already deleted."
                )
            else:
                st.caption("Enter an ID to highlight artifacts associated with it.")
            st.graphviz_chart(
                graphviz_source(graph, affected_artifacts),
                width="stretch",
            )

    if workflow_rows:
        section_heading("Persisted workflow execution")
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
                    f"{value[:8]} · {row['execution_status']} / {row['verification_status']}"
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
            "Execution status",
            f"{status_emoji(workflow['execution_status'])} {workflow['execution_status']}",
        )
        status_columns[1].metric(
            "Verification status",
            f"{status_emoji(workflow['verification_status'])} {workflow['verification_status']}",
        )
        st.caption(
            "Impacted artifacts: "
            + (", ".join(workflow["affected_artifacts"]) or "none recorded")
        )

        steps = workflow["steps"]
        if steps:
            completed = sum(step["status"] == "COMPLETED" for step in steps)
            st.progress(completed / len(steps), text=f"{completed} of {len(steps)} steps completed")
            step_columns = st.columns(len(steps))
            for column, step in zip(step_columns, steps):
                with column:
                    with st.container(border=True):
                        st.caption(f"STEP {step['step_order']:02d}")
                        st.markdown(f"**{step['step_name'].replace('_', ' ').title()}**")
                        st.write(f"{status_emoji(step['status'])} {step['status']}")
                        st.caption(f"Effects: {step['effect_count']:,}")
        if workflow["execution_status"] != "COMPLETED":
            if st.button("Resume workflow", key=f"resume-{selected_id}"):
                result = orchestrator.resume_workflow(selected_id)
                st.session_state["selected_workflow"] = selected_id
                st.toast(
                    f"Execution {result['execution_status']} · "
                    f"verification {result['verification_status']}"
                )
                st.rerun()

        report = orchestrator.get_verification_report(selected_id)
        if report:
            st.markdown("---")
            section_heading("Before / after evidence")
            count_columns = st.columns(3)
            for column, artifact, label in zip(
                count_columns,
                ("source_records", "feature_rows", "prediction_cache"),
                ("Source records", "Feature rows", "Cached predictions"),
            ):
                column.metric(
                    label,
                    f"{report['counts_after'].get(artifact, 0):,}",
                    delta=f"{report['counts_after'].get(artifact, 0) - report['counts_before'].get(artifact, 0):,}",
                    help="Change from immediately before this workflow.",
                )
            st.info(
                f"Cache invalidation removed **{report['cache_invalidation_count']:,}** "
                f"prediction(s). Tolerance: rtol={report['rtol']:.1e}, "
                f"atol={report['atol']:.1e}."
            )

with guided_demo_tab:
    section_heading(
        "Guided synthetic deletion",
        "Walk through a real persisted deletion using one synthetic user. The selected ID is permanently deleted from this demo database.",
    )
    st.markdown(
        "1. Preview live counts and lineage impact.  "
        "2. Run the four persisted stages.  "
        "3. Review before/after counts and independent model evidence.  "
        "4. Attempt managed re-ingestion to see the tombstone guard reject it."
    )
    active_ids = orchestrator.get_available_user_ids(limit=700)
    previous_demo_user = st.session_state.get("guided_demo_user_id")
    demo_options = list(active_ids)
    if previous_demo_user and previous_demo_user not in demo_options:
        demo_options.insert(0, previous_demo_user)
    if not demo_options:
        st.info("No active synthetic IDs remain for a new guided deletion.")
    else:
        selected_demo_user = st.selectbox(
            "Synthetic user for this demonstration",
            demo_options,
            key="guided_demo_user_id",
        )
        demo_state = orchestrator.get_user_state(selected_demo_user)
        demo_counts = orchestrator.get_database_counts()
        demo_impacts = orchestrator.get_affected_artifacts(selected_demo_user)
        preview_columns = st.columns(4)
        for column, key, label in zip(
            preview_columns,
            ("source_records", "feature_rows", "prediction_cache", "tombstones"),
            ("Source before", "Features before", "Cache before", "Tombstones"),
        ):
            column.metric(label, f"{demo_counts[key]:,}")
        st.markdown(
            "**Recorded impacted artifacts:** "
            + (", ".join(sorted(demo_impacts)) if demo_impacts else "none")
        )
        st.graphviz_chart(
            graphviz_source(graph, set(demo_impacts)),
            width="stretch",
        )
        if st.button(
            "Run guided deletion",
            type="primary",
            disabled=not demo_state["source"],
            key="run-guided-deletion",
        ):
            result = orchestrator.request_deletion(selected_demo_user)
            st.session_state["guided_demo_deletion_id"] = result["deletion_id"]
            st.rerun()

        demo_deletion_id = st.session_state.get("guided_demo_deletion_id")
        if demo_deletion_id:
            demo_workflow = orchestrator.get_workflow(demo_deletion_id)
            demo_report = orchestrator.get_verification_report(demo_deletion_id)
            st.markdown("---")
            st.subheader("Persisted stage-by-stage execution")
            st.caption(
                f"Execution: {status_emoji(demo_workflow['execution_status'])} "
                f"{demo_workflow['execution_status']}  ·  "
                f"Verification: {status_emoji(demo_workflow['verification_status'])} "
                f"{demo_workflow['verification_status']}"
            )
            step_columns = st.columns(max(len(demo_workflow["steps"]), 1))
            for column, step in zip(step_columns, demo_workflow["steps"]):
                with column:
                    st.markdown(
                        f"**{step['step_order']}. "
                        f"{step['step_name'].replace('_', ' ').title()}**"
                    )
                    st.write(f"{status_emoji(step['status'])} {step['status']}")
                    st.caption(f"Effects: {step['effect_count']:,}")
            if demo_report:
                st.markdown("#### Before / after counts")
                count_columns = st.columns(3)
                for column, artifact, label in zip(
                    count_columns,
                    ("source_records", "feature_rows", "prediction_cache"),
                    ("Source records", "Feature rows", "Cached predictions"),
                ):
                    before_count = demo_report["counts_before"].get(artifact, 0)
                    after_count = demo_report["counts_after"].get(artifact, 0)
                    column.metric(
                        label,
                        f"{after_count:,}",
                        delta=f"{after_count - before_count:,}",
                    )
                st.write(
                    f"Cache invalidation removed "
                    f"**{demo_report['cache_invalidation_count']:,}** predictions. "
                    f"Tombstone present: **{demo_report['tombstone_present']}**."
                )
                if demo_report["passed"]:
                    st.success(
                        "Independent reference verification passed; the old/new "
                        "difference is evidence, not a pass condition."
                    )
                else:
                    st.error(
                        "Independent verification failed: "
                        + ", ".join(demo_report["failure_reasons"])
                    )
                st.caption(
                    f"rtol={demo_report['rtol']:.1e}, "
                    f"atol={demo_report['atol']:.1e}; maximum absolute replacement/reference "
                    f"differences: coefficients="
                    f"{demo_report['max_reference_coefficient_abs_diff']:.3e}, "
                    f"intercept={demo_report['reference_intercept_abs_diff']:.3e}, "
                    f"predictions={demo_report['max_reference_prediction_abs_diff']:.3e}."
                )
                st.write(
                    "Old model differs from replacement: "
                    f"**{demo_report['old_model_differs']}** "
                    "(reported as evidence only)."
                )
                if demo_workflow["execution_status"] == "COMPLETED":
                    if st.button(
                        "Test managed re-ingestion guard",
                        key=f"test-ingest-{demo_deletion_id}",
                    ):
                        original = (
                            pd.read_csv(orchestrator.dataset_path)
                            .set_index("user_id")
                            .loc[selected_demo_user]
                        )
                        record = {
                            "user_id": selected_demo_user,
                            "region": original["region"],
                            "signal_a": original["signal_a"],
                            "signal_b": original["signal_b"],
                            "target": original["target"],
                        }
                        counts_before_ingestion = orchestrator.get_database_counts()
                        try:
                            orchestrator.ingest_record(record)
                        except DeletedUserError:
                            if orchestrator.get_database_counts() != counts_before_ingestion:
                                st.error("Guard raised, but database counts changed unexpectedly.")
                            else:
                                st.success(
                                    "Managed ingestion rejected the tombstoned ID; "
                                    "database counts were unchanged."
                                )
                        else:
                            st.error(
                                "The managed ingestion guard accepted a deleted ID."
                            )

with verification_tab:
    section_heading(
        "Independent verification",
        "Verification is recorded separately from execution. A completed workflow can fail verification.",
    )
    if not workflow_rows:
        st.info("Run a deletion workflow to generate verification evidence.")
    else:
        verification_ids = [row["deletion_id"] for row in workflow_rows]
        selected_for_report = st.selectbox(
            "Verification report",
            verification_ids,
            key="verification_workflow",
            format_func=lambda value: next(
                (
                    f"{value[:8]} · {row['verification_status']}"
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
            "Execution status",
            f"{status_emoji(selected_workflow['execution_status'])} "
            f"{selected_workflow['execution_status']}",
        )
        right.metric(
            "Verification status",
            f"{status_emoji(selected_status)} {selected_status}",
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
                st.session_state["verification_retry_notice"] = str(error)
            else:
                st.session_state["verification_retry_notice"] = (
                    "Verification attempt completed; review the new persisted result below."
                )
            st.rerun()
        retry_notice = st.session_state.pop("verification_retry_notice", None)
        if retry_notice:
            st.info(retry_notice)
        if report is None:
            if selected_status == "FAILED":
                st.error(
                    "The latest verification attempt failed before producing a report. "
                    "Execution remains complete; retry after resolving the reported issue."
                )
            else:
                st.info("Verification has not produced a report for this workflow.")
        else:
            if report["passed"]:
                st.success("All deletion and independent model verification checks passed.")
            else:
                st.error("Verification failed: " + ", ".join(report["failure_reasons"]))
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
            check_rows.append(
                {
                    "Check": "Old model differs (evidence only; not required)",
                    "Result": report["old_model_differs"],
                }
            )
            st.dataframe(
                pd.DataFrame(check_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "Result": st.column_config.CheckboxColumn("Passed", disabled=True)
                },
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
                evidence_columns[0].metric("Relative tolerance", f"{report['rtol']:.1e} rtol")
                evidence_columns[1].metric("Absolute tolerance", f"{report['atol']:.1e} atol")
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
                    f"Old-to-replacement evidence (not a pass condition): maximum "
                    f"coefficient delta "
                    f"{report['max_old_replacement_coefficient_abs_diff']:.2e}; "
                    f"intercept delta {report['old_replacement_intercept_abs_diff']:.2e}. "
                    f"Ridge α={report['alpha']}, seed={report['random_seed']}."
                )
            else:
                legacy_evidence = st.columns(3)
                legacy_evidence[0].metric(
                    "Relative tolerance", f"{report['rtol']:.1e} rtol"
                )
                legacy_evidence[1].metric(
                    "Absolute tolerance", f"{report['atol']:.1e} atol"
                )
                if "max_prediction_abs_diff" in report:
                    legacy_evidence[2].metric(
                        "Max prediction delta",
                        f"{report['max_prediction_abs_diff']:.2e}",
                    )

        attempts = orchestrator.get_verification_attempts(selected_for_report)
        st.markdown("#### Verification attempt history")
        if attempts:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Attempt": attempt["attempt_number"],
                            "Status": attempt["status"],
                            "Started": attempt["started_at"],
                            "Completed": attempt["completed_at"],
                            "Error": attempt["error_text"],
                        }
                        for attempt in attempts
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("No verification attempts have been recorded.")

    st.markdown("---")
    section_heading(
        "Security & privacy controls",
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
