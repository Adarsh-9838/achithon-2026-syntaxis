import sys
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from forgetgraph import ForgetGraphOrchestrator, SimulatedCrash  # noqa: E402


@st.cache_resource
def get_orchestrator():
    return ForgetGraphOrchestrator(
        database_path=PROJECT_DIR / "data" / "forgetgraph.sqlite",
        dataset_path=PROJECT_DIR / "data" / "synthetic_users.csv",
        config_path=PROJECT_DIR / "config.json",
    )


st.set_page_config(page_title="FORGETGRAPH", page_icon="FG", layout="wide")
st.title("FORGETGRAPH")
st.caption("Dependency-aware deletion for a synthetic Ridge regression pipeline.")
orchestrator = get_orchestrator()

graph = orchestrator.get_artifact_graph()
workflow_rows = orchestrator.list_workflows()

node_counts = {node["id"]: node["count"] for node in graph["nodes"]}
graph_colors = {
    "source_records": "#b7e4c7" if node_counts["source_records"] else "#f4a6a6",
    "engineered_features": (
        "#b7e4c7" if node_counts["engineered_features"] else "#f4a6a6"
    ),
    "ridge_model": "#b7e4c7",
    "prediction_cache": (
        "#b7e4c7" if node_counts["prediction_cache"] else "#ffe08a"
    ),
}
graph_lines = [
    "digraph ForgetGraph {",
    '  graph [rankdir="LR"];',
    '  node [shape="box", style="rounded,filled", fontname="Arial"];',
]
for node in graph["nodes"]:
    graph_lines.append(
        f'  {node["id"]} [label="{node["label"]}\\nrows: {node["count"]}", '
        f'fillcolor="{graph_colors[node["id"]]}"];'
    )
for edge in graph["edges"]:
    graph_lines.append(f'  {edge["source"]} -> {edge["target"]};')
graph_lines.append("}")
st.subheader("Artifact dependency graph")
st.graphviz_chart("\n".join(graph_lines), width="stretch")

counts = orchestrator.get_database_counts()
metric_cols = st.columns(4)
for column, label, key in zip(
    metric_cols,
    ("Source records", "Feature rows", "Cached predictions", "Tombstones"),
    ("source_records", "feature_rows", "prediction_cache", "tombstones"),
):
    column.metric(label, counts[key])

st.subheader("Request a deletion")
with st.form("deletion_request"):
    user_id = st.text_input("Synthetic user ID", placeholder="user-0001")
    inject_failure = st.checkbox("Inject a simulated crash after a step")
    failure_step = st.selectbox(
        "Crash after",
        (
            "remove_source",
            "recompute_features",
            "invalidate_cache",
            "replace_model",
        ),
        disabled=not inject_failure,
    )
    submitted = st.form_submit_button("Run deletion")

if submitted:
    if not user_id.strip():
        st.error("Enter a user ID.")
    else:
        try:
            result = orchestrator.request_deletion(
                user_id.strip(),
                fail_after_step=failure_step if inject_failure else None,
            )
        except SimulatedCrash as error:
            st.warning(
                f"Simulated crash after {error.step_name}. "
                f"Workflow {error.deletion_id} is persisted and can be resumed below."
            )
            st.session_state["selected_workflow"] = error.deletion_id
        else:
            if result.get("already_deleted"):
                st.info("This identifier is already deleted; no state was changed.")
            else:
                st.success(
                    f"Deletion workflow {result['deletion_id']} finished. "
                    f"Execution: {result['execution_status']}; "
                    f"verification: {result['verification_status']}."
                )
                st.session_state["selected_workflow"] = result["deletion_id"]

if workflow_rows:
    st.subheader("Workflow progress")
    workflow_options = [row["deletion_id"] for row in workflow_rows]
    current_selection = st.session_state.get("selected_workflow")
    default_index = (
        workflow_options.index(current_selection)
        if current_selection in workflow_options
        else 0
    )
    selected_id = st.selectbox(
        "Select a workflow",
        workflow_options,
        index=default_index,
        format_func=lambda value: next(
            (
                f"{value[:8]} — "
                f"{row['execution_status']} / {row['verification_status']}"
                for row in workflow_rows
                if row["deletion_id"] == value
            ),
            value,
        ),
    )
    st.session_state["selected_workflow"] = selected_id
    selected_workflow = orchestrator.get_workflow(selected_id)
    status_cols = st.columns(2)
    status_cols[0].metric("Execution status", selected_workflow["execution_status"])
    status_cols[1].metric(
        "Verification status", selected_workflow["verification_status"]
    )
    st.write("Affected artifacts:", selected_workflow["affected_artifacts"])
    if selected_workflow["steps"]:
        steps = pd.DataFrame(selected_workflow["steps"])
        st.dataframe(
            steps[
                ["step_order", "step_name", "artifact_id", "status", "effect_count"]
            ],
            hide_index=True,
            width="stretch",
        )
    if selected_workflow["execution_status"] != "COMPLETED":
        if st.button("Resume workflow", key=f"resume-{selected_id}"):
            result = orchestrator.resume_workflow(selected_id)
            st.success(
                f"Resume finished. Execution: {result['execution_status']}; "
                f"verification: {result['verification_status']}."
            )
            st.rerun()

    report = orchestrator.get_verification_report(selected_id)
    if report is not None:
        st.subheader("Verification evidence")
        if report["passed"]:
            st.success("Verification PASSED")
        else:
            st.error(
                "Verification FAILED: "
                + ", ".join(report["failure_reasons"])
            )
        st.write(
            f"Tolerance: rtol={report['rtol']:.1e}, atol={report['atol']:.1e}; "
            f"alpha={report['alpha']}, seed={report['random_seed']}."
        )
        st.write(
            f"Old model differs from replacement: {report['old_model_differs']}; "
            f"maximum reference prediction difference: "
            f"{report['max_prediction_abs_diff']:.3e}."
        )
        st.write(
            f"Cache invalidation removed {report['cache_invalidation_count']} "
            "cached predictions."
        )
        comparison_rows = []
        names = report["replacement"]["coefficients"]
        for index, name in enumerate(
            ("signal_a", "signal_b", "region_mean_signal_a")
        ):
            comparison_rows.append(
                {
                    "Parameter": name,
                    "Old model": report["old_model"]["coefficients"][index],
                    "Replacement": names[index],
                    "Independent reference": report["reference"]["coefficients"][
                        index
                    ],
                }
            )
        comparison_rows.append(
            {
                "Parameter": "intercept",
                "Old model": report["old_model"]["intercept"],
                "Replacement": report["replacement"]["intercept"],
                "Independent reference": report["reference"]["intercept"],
            }
        )
        st.dataframe(
            pd.DataFrame(comparison_rows),
            hide_index=True,
            width="stretch",
        )
        counts_table = pd.DataFrame(
            [
                {"Artifact": name, "Before": count, "After": report["counts_after"].get(name)}
                for name, count in report["counts_before"].items()
                if name in ("source_records", "feature_rows", "prediction_cache")
            ]
        )
        st.caption("Before/after artifact counts")
        st.dataframe(counts_table, hide_index=True, width="stretch")

st.subheader("Audit log")
audit_rows = orchestrator.get_audit_events()
st.dataframe(pd.DataFrame(audit_rows), hide_index=True, width="stretch")
