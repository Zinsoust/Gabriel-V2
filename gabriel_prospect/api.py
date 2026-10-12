"""Authenticated Flask endpoint for an in-memory prospect import preview."""

import json

from flask import Blueprint, jsonify, request

from api.auth import login_required_api
from core.security import rate_limit, safe_log_event

from .importer import ImportValidationError
from .schema import MAX_FILE_BYTES
from .scoring import IcpValidationError
from .service import build_import_preview


prospect_bp = Blueprint("gabriel_prospect", __name__, url_prefix="/api/v2/prospects")

_ALLOWED_MIME_TYPES = {
    "", "text/csv", "application/csv", "text/plain",
    "application/vnd.ms-excel", "application/octet-stream",
}


def _json_form_field(name):
    raw_value = request.form.get(name)
    if raw_value in (None, ""):
        return None
    if len(raw_value) > 50_000:
        raise ImportValidationError("invalid_json_field", f"Le champ « {name} » est invalide.")
    try:
        return json.loads(raw_value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ImportValidationError("invalid_json_field", f"Le champ « {name} » est invalide.") from exc


@prospect_bp.post("/imports/preview")
@login_required_api
@rate_limit("30 per hour")
def import_preview():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({
            "success": False,
            "error": "Un fichier CSV est requis.",
            "error_code": "missing_file",
        }), 400

    mime_type = (uploaded.mimetype or "").casefold()
    if mime_type not in _ALLOWED_MIME_TYPES:
        return jsonify({
            "success": False,
            "error": "Le type de fichier envoyé n'est pas accepté.",
            "error_code": "unsupported_media_type",
        }), 415

    try:
        mapping = _json_form_field("mapping")
        icp = _json_form_field("icp")
        raw_bytes = uploaded.stream.read(MAX_FILE_BYTES + 1)
        preview = build_import_preview(uploaded.filename, raw_bytes, mapping=mapping, icp=icp)
        return jsonify({"success": True, "preview": preview})
    except (ImportValidationError, IcpValidationError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
            "error_code": exc.code,
        }), exc.status_code
    except Exception as exc:
        safe_log_event(
            "prospect_import_preview_failed",
            metadata={"failure_type": type(exc).__name__},
        )
        return jsonify({
            "success": False,
            "error": "La prévisualisation de l'import a échoué.",
            "error_code": "preview_failed",
        }), 500
