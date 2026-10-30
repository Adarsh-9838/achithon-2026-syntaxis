from xml.sax.saxutils import escape


_STATUS_COLORS = {
    "VERIFIED": "#137a53",
    "FAILED": "#b42335",
    "INCOMPLETE": "#98600c",
}


def build_certificate_receipt_svg(certificate: dict) -> str:
    """Render a certificate as a self-contained, downloadable receipt image."""
    execution = certificate.get("execution") or {}
    verification = certificate.get("verification") or {}
    status = certificate.get("status", "INCOMPLETE")
    status_color = _STATUS_COLORS.get(status, _STATUS_COLORS["INCOMPLETE"])
    stages = execution.get("stages") or []
    artifacts = certificate.get("affected_artifacts") or []
    predictions = verification.get("prediction_comparison") or {}
    coefficients = verification.get("coefficient_comparison") or {}
    intercept = verification.get("intercept_comparison") or {}

    text_elements = []
    y = 206

    def text(value, *, x=72, size=20, fill="#142b4e", weight=400, family="Arial, sans-serif"):
        nonlocal y
        text_elements.append(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{escape(str(value))}</text>'
        )
        y += size + 12

    def section(title):
        nonlocal y
        y += 14
        text(title.upper(), size=15, fill="#98600c", weight=700)
        text_elements.append(
            f'<line x1="72" y1="{y - 4}" x2="888" y2="{y - 4}" '
            'stroke="#e8e4de" stroke-dasharray="5 6"/>'
        )
        y += 10

    def detail(label, value, *, size=17, family="Arial, sans-serif"):
        text(f"{label}: {value}", size=size, fill="#405168", family=family)

    section("Request")
    detail("Request ID", certificate.get("request_id", "Unavailable"))
    detail("Certificate ID", certificate.get("certificate_id", "Unavailable"))
    detail("Requested", execution.get("requested_at") or "Not recorded")
    detail("Affected artifacts", ", ".join(map(str, artifacts)) or "None recorded")

    section("Execution")
    detail("Execution status", execution.get("status", "NOT AVAILABLE"))
    for stage in stages:
        detail(
            stage.get("stage", "Unknown stage"),
            f"{stage.get('status', 'NOT AVAILABLE')} · "
            f"result: {stage.get('result') if stage.get('result') is not None else 'not recorded'}",
        )
        if stage.get("started_at") or stage.get("completed_at"):
            detail(
                "  Recorded",
                f"{stage.get('started_at') or 'start unavailable'} → "
                f"{stage.get('completed_at') or 'completion unavailable'}",
            )
    if not stages:
        detail("Stages", "No execution stage evidence")
    if execution.get("replacement_model_id"):
        detail("Replacement model", execution["replacement_model_id"])

    section("Independent model verification")
    detail("Verification status", verification.get("status", "NOT AVAILABLE"))
    detail("Verification result", verification.get("result") or "NOT AVAILABLE")
    detail("Reference model", verification.get("reference_model_id") or "Not recorded")
    detail("Replacement model", verification.get("replacement_model_id") or "Not recorded")
    detail(
        "Coefficient comparison",
        "PASS" if coefficients.get("passed") is True
        else "FAIL" if coefficients.get("passed") is False
        else "NOT AVAILABLE",
    )
    detail(
        "Intercept comparison",
        "PASS" if intercept.get("passed") is True
        else "FAIL" if intercept.get("passed") is False
        else "NOT AVAILABLE",
    )
    detail(
        "Max / mean prediction difference",
        f"{predictions.get('max_absolute_difference', 'Unavailable')} / "
        f"{predictions.get('mean_absolute_difference', 'Unavailable')}",
    )
    detail("Tolerances", verification.get("tolerances") or "Not recorded")

    section("Evidence integrity")
    evidence_hash = certificate.get("integrity_hash", "Not available")
    detail("SHA-256", evidence_hash[:32], size=14, family="monospace")
    if len(evidence_hash) > 32:
        detail("Continued", evidence_hash[32:], size=14, family="monospace")

    footer_y = y + 30
    height = footer_y + 105
    header = (
        '<rect x="34" y="34" width="892" height="'
        f'{height - 68}" rx="14" fill="#ffffff" stroke="#ded8ce" stroke-width="2"/>'
        '<path d="M48 34 H912 Q926 34 926 48 V166 H34 V48 Q34 34 48 34" '
        'fill="#142b4e"/>'
        '<text x="72" y="82" font-family="Arial, sans-serif" font-size="17" '
        'font-weight="700" letter-spacing="3" fill="#f3bd56">FORGETGRAPH</text>'
        '<text x="72" y="123" font-family="Georgia, serif" font-size="27" '
        'font-weight="700" fill="#ffffff">DELETION EVIDENCE RECEIPT</text>'
        f'<rect x="720" y="72" width="168" height="42" rx="21" fill="{status_color}"/>'
        f'<text x="804" y="99" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="16" font-weight="700" fill="#ffffff">{escape(status)}</text>'
    )
    footer = (
        f'<line x1="72" y1="{footer_y}" x2="888" y2="{footer_y}" '
        'stroke="#e8e4de" stroke-dasharray="5 6"/>'
        f'<text x="72" y="{footer_y + 32}" font-family="Arial, sans-serif" '
        'font-size="13" fill="#58677c">Integrity hash checks whether this evidence changed. '
        'It does not prove permanent erasure from every copy or system.</text>'
        f'<text x="72" y="{footer_y + 60}" font-family="Arial, sans-serif" '
        'font-size="12" fill="#8792a0">Generated from persisted FORGETGRAPH execution and verification evidence.</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
        f'viewBox="0 0 960 {height}" role="img" aria-label="FORGETGRAPH deletion evidence receipt">'
        '<rect width="960" height="100%" fill="#f3f0ea"/>'
        f"{header}{''.join(text_elements)}{footer}</svg>"
    )
