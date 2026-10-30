from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_sections_render_without_exceptions():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Deletion workflow",
        "Verification & security",
        "Audit trail",
    ]

    for tab in app.tabs:
        tab.run()
        assert not app.exception, [exception.message for exception in app.exception]
