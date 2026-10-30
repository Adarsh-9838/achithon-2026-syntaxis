import hashlib
import json
from typing import Any


INTEGRITY_ALGORITHM = "SHA-256"
CANONICALIZATION = "UTF-8 JSON with sorted keys and compact separators"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def seal_certificate(certificate: dict) -> dict:
    sealed = dict(certificate)
    sealed.pop("integrity", None)
    digest = hashlib.sha256(canonical_json(sealed).encode("utf-8")).hexdigest()
    sealed["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "canonicalization": CANONICALIZATION,
        "sha256": digest,
    }
    return sealed


def validate_certificate_integrity(certificate: dict) -> bool:
    integrity = certificate.get("integrity")
    if (
        not isinstance(integrity, dict)
        or integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("canonicalization") != CANONICALIZATION
        or not isinstance(integrity.get("sha256"), str)
    ):
        return False
    unsigned = dict(certificate)
    unsigned.pop("integrity", None)
    expected = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    return integrity["sha256"] == expected
