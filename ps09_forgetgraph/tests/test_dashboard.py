from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_sections_render_without_exceptions():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Deletion workflow",
        "Verification",
        "Audit trail",
    ]

    for tab in app.tabs:
        tab.run()
        assert not app.exception, [exception.message for exception in app.exception]


def test_dashboard_uses_beginner_friendly_labels_and_explanations():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    subheaders = [element.value for element in app.get("subheader")]
    captions = [element.value for element in app.get("caption")]
    infos = [element.value for element in app.get("info")]
    button_labels = [element.label for element in app.get("button")]
    metric_labels = [element.label for element in app.get("metric")]
    markdown = [element.value for element in app.get("markdown")]
    visible_copy = "\n".join(subheaders + captions + infos + markdown)

    assert "Pipeline dependencies" in subheaders
    assert "Artifacts affected by this user" in subheaders
    assert "overall pipeline structure" in visible_copy
    assert "arrows indicate downstream dependencies" in visible_copy
    assert "Artifact** means a file or data product" in visible_copy
    assert "Tombstone** means a saved block" in visible_copy
    assert "cache stores saved predictions" in visible_copy
    assert "not automatically refilled" in visible_copy
    assert "it is cleared" in visible_copy
    assert "Run deletion" in button_labels
    assert "Models" in metric_labels
    assert "Completed deletions" in metric_labels
    assert "Tombstones" in metric_labels
    assert "Deletion steps" in metric_labels
    assert "Independent verification" in metric_labels
    assert "Current database state" in subheaders
    assert "Remove source record" in visible_copy
    assert "Rebuild feature rows" in visible_copy
    assert "Clear saved predictions" in visible_copy
    assert "Train replacement model" in visible_copy
    assert "already empty" in visible_copy or "not included" in visible_copy
