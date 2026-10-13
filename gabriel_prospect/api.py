"""Authenticated Flask endpoint for an in-memory prospect import preview."""

import json

from flask import Blueprint, jsonify, request

from api.auth import login_required_api
from core.security import rate_limit, safe_log_event

from .importer import ImportValidationError
from .persistence import PersistenceValidationError, prepare_selected_import
from .provenance import sign_preview, verify_selected_payload
from .repository import (
    PROSPECT_STATUSES,
    ProspectConflict,
    ProspectNotFound,
    ProspectStorageUnavailable,
    get_repository,
)
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
        preview = sign_preview(build_import_preview(uploaded.filename, raw_bytes, mapping=mapping, icp=icp))
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


def _current_user_id():
    from api.auth import current_user
    user = current_user()
    return user.get("user_id") if isinstance(user, dict) else None


def _storage_error_response(exc, operation):
    safe_log_event(
        "prospect_storage_failed",
        user_id=_current_user_id(),
        metadata={"operation": operation, "failure_type": type(exc).__name__},
    )
    return jsonify({
        "success": False,
        "error": "Le stockage des prospects est temporairement indisponible.",
        "error_code": "prospect_storage_unavailable",
    }), 503


@prospect_bp.post("")
@login_required_api
@rate_limit("30 per hour")
def save_prospects():
    if request.content_length and request.content_length > 8 * 1024 * 1024:
        return jsonify({
            "success": False,
            "error": "La sélection de prospects est trop volumineuse.",
            "error_code": "payload_too_large",
        }), 413
    try:
        payload = request.get_json(silent=True)
        if not verify_selected_payload(payload):
            return jsonify({
                "success": False,
                "error": "La provenance de la prévisualisation est invalide ou expirée.",
                "error_code": "invalid_preview_provenance",
            }), 400
        prepared = prepare_selected_import(payload)
        result = get_repository().save_selected(_current_user_id(), prepared)
        return jsonify({"success": True, "result": result}), 201
    except PersistenceValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": exc.code}), exc.status_code
    except ProspectStorageUnavailable as exc:
        return _storage_error_response(exc, "save")


@prospect_bp.get("")
@login_required_api
@rate_limit("120 per hour")
def list_prospects():
    status = request.args.get("status") or None
    try:
        min_score = int(request.args.get("min_score", "0"))
        limit = int(request.args.get("limit", "200"))
    except (TypeError, ValueError):
        min_score, limit = -1, 0
    if (status and status not in PROSPECT_STATUSES) or not 0 <= min_score <= 100 or not 1 <= limit <= 500:
        return jsonify({
            "success": False,
            "error": "Les filtres demandés sont invalides.",
            "error_code": "invalid_filter",
        }), 400
    try:
        prospects = get_repository().list_prospects(
            _current_user_id(), status=status, min_score=min_score, limit=limit,
        )
        return jsonify({"success": True, "prospects": prospects, "count": len(prospects)})
    except ProspectStorageUnavailable as exc:
        return _storage_error_response(exc, "list")


@prospect_bp.get("/<prospect_id>")
@login_required_api
@rate_limit("120 per hour")
def get_saved_prospect(prospect_id):
    try:
        prospect = get_repository().get_prospect(_current_user_id(), prospect_id)
        return jsonify({"success": True, "prospect": prospect})
    except ProspectNotFound:
        return jsonify({"success": False, "error": "Prospect introuvable.", "error_code": "prospect_not_found"}), 404
    except ProspectStorageUnavailable as exc:
        return _storage_error_response(exc, "get")


@prospect_bp.patch("/<prospect_id>/status")
@login_required_api
@rate_limit("60 per hour")
def update_prospect_status(prospect_id):
    payload = request.get_json(silent=True)
    status = payload.get("status") if isinstance(payload, dict) else None
    if status not in PROSPECT_STATUSES:
        return jsonify({"success": False, "error": "Le statut commercial est invalide.", "error_code": "invalid_status"}), 400
    try:
        prospect = get_repository().update_status(_current_user_id(), prospect_id, status)
        return jsonify({"success": True, "prospect": prospect})
    except ProspectNotFound:
        return jsonify({"success": False, "error": "Prospect introuvable.", "error_code": "prospect_not_found"}), 404
    except ProspectConflict as exc:
        if str(exc) == "contact_not_eligible":
            return jsonify({
                "success": False,
                "error": "Ce prospect doit être enrichi avant tout statut de prise de contact.",
                "error_code": "contact_not_eligible",
            }), 409
        return jsonify({
            "success": False,
            "error": "Un contact marqué « ne pas contacter » ne peut pas être réactivé.",
            "error_code": "do_not_contact_preserved",
        }), 409
    except ProspectStorageUnavailable as exc:
        return _storage_error_response(exc, "update_status")


@prospect_bp.delete("/<prospect_id>")
@login_required_api
@rate_limit("30 per hour")
def delete_saved_prospect(prospect_id):
    try:
        get_repository().delete_prospect(_current_user_id(), prospect_id)
        return jsonify({"success": True, "deleted": True})
    except ProspectNotFound:
        return jsonify({"success": False, "error": "Prospect introuvable.", "error_code": "prospect_not_found"}), 404
    except ProspectConflict:
        return jsonify({
            "success": False,
            "error": "Ce refus de contact ne peut pas être supprimé sans identifiant durable.",
            "error_code": "do_not_contact_deletion_blocked",
        }), 409
    except ProspectStorageUnavailable as exc:
        return _storage_error_response(exc, "delete")
