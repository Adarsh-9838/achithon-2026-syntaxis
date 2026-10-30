import xml.etree.ElementTree as ET

from forgetgraph.certificate_image import build_certificate_receipt_svg


def test_certificate_receipt_is_valid_branded_svg_with_execution_and_verification():
    certificate = {
        "status": "VERIFIED",
        "certificate_id": "cert-123",
        "request_id": "request-456",
        "integrity_hash": "a" * 64,
        "affected_artifacts": ["source_records", "engineered_features"],
        "execution": {
            "status": "COMPLETED",
            "requested_at": "2026-10-30T12:00:00+00:00",
            "replacement_model_id": "active:2",
            "stages": [
                {
                    "stage": "remove_source",
                    "status": "COMPLETED",
                    "result": True,
                    "started_at": "2026-10-30T12:00:01+00:00",
                    "completed_at": "2026-10-30T12:00:02+00:00",
                }
            ],
        },
        "verification": {
            "status": "PASSED",
            "result": "PASS",
            "reference_model_id": "reference:123",
            "replacement_model_id": "active:2",
            "coefficient_comparison": {"passed": True},
            "intercept_comparison": {"passed": True},
            "prediction_comparison": {
                "max_absolute_difference": 0.0,
                "mean_absolute_difference": 0.0,
            },
            "tolerances": {"rtol": 1e-8, "atol": 1e-10},
        },
    }

    receipt = build_certificate_receipt_svg(certificate)
    root = ET.fromstring(receipt)
    visible_text = "".join(root.itertext())

    assert root.attrib["aria-label"] == "FORGETGRAPH deletion evidence receipt"
    assert "FORGETGRAPH" in visible_text
    assert "DELETION EVIDENCE RECEIPT" in visible_text
    assert "VERIFIED" in visible_text
    assert "request-456" in visible_text
    assert "remove_source" in visible_text
    assert "reference:123" in visible_text
    assert f"SHA-256: {'a' * 32}" in visible_text
    assert f"Continued: {'a' * 32}" in visible_text


def test_certificate_receipt_escapes_untrusted_text_and_supports_incomplete_evidence():
    certificate = {
        "status": "INCOMPLETE",
        "request_id": "<request&1>",
        "affected_artifacts": [],
        "execution": {"status": "RUNNING", "stages": []},
        "verification": {"status": "NOT_RUN"},
    }

    receipt = build_certificate_receipt_svg(certificate)

    assert "&lt;request&amp;1&gt;" in receipt
    assert "<request&1>" not in receipt
    assert "INCOMPLETE" in receipt
    ET.fromstring(receipt)
