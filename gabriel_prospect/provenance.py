"""Tamper-evident proof that a saved row came from a server preview."""

import hashlib
import json
import secrets

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


_SALT = "gabriel-prospect-import-preview-v1"


def _serializer():
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("Flask secret key is not configured")
    return URLSafeTimedSerializer(secret, salt=_SALT)


def _digest(import_meta, icp, prospect):
    protected = {
        "import": {
            "filename": import_meta.get("filename"),
            "sha256": import_meta.get("sha256"),
            "size_bytes": import_meta.get("size_bytes"),
        },
        "icp": icp,
        "source_row": prospect.get("source_row"),
        "data": prospect.get("data"),
    }
    canonical = json.dumps(protected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_preview(preview):
    for prospect in preview.get("prospects", []):
        prospect["provenance_token"] = _serializer().dumps({
            "digest": _digest(preview.get("import", {}), preview.get("icp", {}), prospect),
        })
    return preview


def verify_selected_payload(payload):
    if not isinstance(payload, dict):
        return False
    import_meta = payload.get("import")
    icp = payload.get("icp")
    prospects = payload.get("prospects")
    if not isinstance(import_meta, dict) or not isinstance(icp, dict) or not isinstance(prospects, list):
        return False
    for prospect in prospects:
        if not isinstance(prospect, dict):
            return False
        token = prospect.get("provenance_token")
        if not isinstance(token, str):
            return False
        try:
            signed = _serializer().loads(token, max_age=2 * 60 * 60)
        except (BadSignature, SignatureExpired):
            return False
        expected = _digest(import_meta, icp, prospect)
        if not isinstance(signed, dict) or not secrets.compare_digest(str(signed.get("digest", "")), expected):
            return False
    return bool(prospects)
