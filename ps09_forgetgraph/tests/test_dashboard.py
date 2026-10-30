from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECTIONS = [
    "Overview",
    "Deletion workflow",
    "Verification",
    "Evidence Certificates",
    "Audit trail",
]


def run_section(app: AppTest, section: str) -> AppTest:
    app.radio[0].set_value(section).run()
    assert not app.exception, [exception.message for exception in app.exception]
    return app


def visible_copy(app: AppTest) -> str:
    return "\n".join(
        str(element.value)
        for element_type in ("title", "subheader", "caption", "info", "markdown", "success", "warning", "error")
        for element in app.get(element_type)
    )


def test_dashboard_sections_render_without_exceptions():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    assert not app.exception
    assert app.radio[0].options == SECTIONS
    assert app.title[0].value == "Delete once. Remove everywhere."

    for section in SECTIONS[1:]:
        run_section(app, section)


def test_overview_has_screenshot_style_content_and_clear_statistics():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    copy = visible_copy(app)
    metric_labels = [element.label for element in app.get("metric")]
    button_labels = [element.label for element in app.get("button")]

    assert "FORGETGRAPH" in copy
    assert "Delete once. Remove everywhere." in copy
    assert "Start a deletion" in button_labels
    assert metric_labels == [
        "SOURCE RECORDS",
        "FEATURE ROWS",
        "CACHED PREDICTIONS",
        "MODEL GENERATION",
        "COMPLETED DELETIONS",
    ]
    assert "Current state of the database" in copy
    assert "Completed deletions count finished workflows" in copy
    assert "Tombstones:" in copy
    assert "How it works" in copy
    assert "Trace" in copy
    assert "Delete in order" in copy
    assert "Verify independently" in copy

    if "0" in [element.value for element in app.get("metric") if element.label == "CACHED PREDICTIONS"]:
        assert "The prediction cache is empty" in copy
        assert "not automatically repopulated" in copy


def test_start_button_navigates_to_deletion_workflow():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    app.button[0].click().run()

    assert not app.exception
    assert app.radio[0].value == "Deletion workflow"
    assert "Request a deletion" in [element.value for element in app.title]
    assert "Artifacts affected by this user" in [
        element.value for element in app.get("subheader")
    ]
    copy = visible_copy(app)
    assert "overall pipeline shape" in copy
    assert "arrows indicate downstream dependencies" in copy
    assert "Run deletion" in [element.label for element in app.button]


def test_fresh_deletion_workflow_waits_instead_of_showing_saved_pass():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    run_section(app, "Deletion workflow")

    metrics = {element.label: element.value for element in app.get("metric")}
    copy = visible_copy(app)

    assert metrics["Deletion steps"] == "◷ Waiting"
    assert metrics["Independent verification"] == "— Not checked yet"
    assert "Waiting for a deletion request" in copy
    assert "Independent verification passed." not in copy
    assert any(element.label == "Saved deletion history" for element in app.expander)


def test_fresh_verification_view_does_not_select_an_old_pass():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    run_section(app, "Verification")

    metrics = {element.label: element.value for element in app.get("metric")}
    copy = visible_copy(app)
    assert metrics["Deletion steps"] == "◷ Waiting"
    assert metrics["Independent verification"] == "— Not checked yet"
    assert "No deletion has been started in this visit" in copy
    assert "Independent verification passed." not in copy


def test_verification_and_execution_status_are_separate():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    run_section(app, "Verification")

    metric_labels = [element.label for element in app.get("metric")]
    copy = visible_copy(app)
    assert "Deletion steps" in metric_labels
    assert "Independent verification" in metric_labels
    assert "Verification means checking" in copy


def test_evidence_certificate_section_renders_without_exceptions():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    run_section(app, "Evidence Certificates")

    copy = visible_copy(app)
    assert "Deletion Evidence Certificates" in copy
    if "No deletion certificates yet" in copy:
        assert "A certificate is created when a valid deletion request is accepted" in copy
    else:
        assert "Certificate status:" in copy
        assert "Hash validation detects changes" in copy
        assert "View receipt image" in [
            element.label for element in app.get("expander")
        ]
        assert {
            button.label for button in app.get("download_button")
        } >= {"Download certificate JSON", "Download receipt image (SVG)"}
        assert not app.exception


def test_all_navigation_sections_have_expected_headings():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    run_section(app, "Verification")
    assert "Check the deletion and new model" in [
        element.value for element in app.get("subheader")
    ]

    run_section(app, "Audit trail")
    assert "Operational audit trail" in [
        element.value for element in app.get("subheader")
    ]
