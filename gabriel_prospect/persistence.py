"""Validation boundary for explicitly persisted prospect previews.

The browser sends declarations selected by the user. Scores, facts and contact
eligibility are rebuilt here so client-side values are never trusted as
verified or authoritative.
"""

import re

from .deduplication import detect_duplicates
from .normalization import normalize_row
from .schema import CANONICAL_FIELDS, MAX_ROWS
from .scoring import default_icp, score_prospect, validate_icp
from .service import assess_contact_eligibility


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PersistenceValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.status_code = 400


def _clean_filename(value):
    if not isinstance(value, str) or not value.strip():
        raise PersistenceValidationError("invalid_import", "Les métadonnées de l'import sont invalides.")
    filename = value.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if len(filename) > 255 or not filename.casefold().endswith(".csv"):
        raise PersistenceValidationError("invalid_import", "Les métadonnées de l'import sont invalides.")
    return filename


def _prepare_import(value, selected_count):
    if not isinstance(value, dict):
        raise PersistenceValidationError("invalid_import", "Les métadonnées de l'import sont invalides.")
    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256.casefold()):
        raise PersistenceValidationError("invalid_import", "L'empreinte de l'import est invalide.")
    size_bytes = value.get("size_bytes")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 0 <= size_bytes <= 2 * 1024 * 1024:
        raise PersistenceValidationError("invalid_import", "La taille de l'import est invalide.")
    rows_received = value.get("rows_received", selected_count)
    if isinstance(rows_received, bool) or not isinstance(rows_received, int) or not selected_count <= rows_received <= MAX_ROWS:
        raise PersistenceValidationError("invalid_import", "Le nombre de lignes de l'import est invalide.")
    return {
        "filename": _clean_filename(value.get("filename")),
        "sha256": sha256.casefold(),
        "size_bytes": size_bytes,
        "rows_received": rows_received,
    }


def _prepare_prospect(value, filename, icp):
    if not isinstance(value, dict):
        raise PersistenceValidationError("invalid_prospect", "Un prospect sélectionné est invalide.")
    source_row = value.get("source_row")
    if isinstance(source_row, bool) or not isinstance(source_row, int) or not 2 <= source_row <= MAX_ROWS + 1:
        raise PersistenceValidationError("invalid_prospect", "La ligne source d'un prospect est invalide.")
    submitted_data = value.get("data")
    if not isinstance(submitted_data, dict) or set(submitted_data) - set(CANONICAL_FIELDS):
        raise PersistenceValidationError("invalid_prospect", "Les données d'un prospect sont invalides.")

    data, validation_errors = normalize_row({field: submitted_data.get(field) for field in CANONICAL_FIELDS})
    if not data.get("company_name") and not data.get("domain"):
        validation_errors.append({
            "field": "company_name",
            "code": "missing_company_identity",
            "message": "Un nom d'entreprise ou un domaine valide est requis.",
            "severity": "error",
            "blocking": True,
        })

    source_id = f"csv-row-{source_row}"
    facts = []
    fact_ids = {}
    for field in CANONICAL_FIELDS:
        field_value = data.get(field)
        if field_value is None:
            continue
        fact_id = f"{source_id}:{field}"
        fact_ids[field] = fact_id
        facts.append({
            "fact_id": fact_id,
            "field": field,
            "value": field_value,
            "status": "declared_unverified",
            "source_id": source_id,
            "source_column": field,
        })

    prospect = {
        "source_row": source_row,
        "data": data,
        "sources": [{
            "source_id": source_id,
            "type": "csv_import",
            "filename": filename,
            "row": source_row,
            "verification": "not_independently_verified",
        }],
        "facts": facts,
        "hypotheses": [],
        "unknowns": [field for field in CANONICAL_FIELDS if data.get(field) is None],
        "validation_errors": validation_errors,
        "score": score_prospect(data, fact_ids, icp),
        "duplicate": None,
    }
    return prospect


def prepare_selected_import(payload):
    if not isinstance(payload, dict):
        raise PersistenceValidationError("invalid_payload", "La sélection de prospects est invalide.")
    selected = payload.get("prospects")
    if not isinstance(selected, list) or not selected or len(selected) > MAX_ROWS:
        raise PersistenceValidationError("invalid_selection", "Sélectionnez entre 1 et 1 000 prospects.")

    import_meta = _prepare_import(payload.get("import"), len(selected))
    try:
        icp = validate_icp(payload.get("icp") if payload.get("icp") is not None else default_icp())
    except ValueError as exc:
        raise PersistenceValidationError("invalid_icp", str(exc)) from exc

    prospects = [_prepare_prospect(item, import_meta["filename"], icp) for item in selected]
    duplicate_counts = detect_duplicates(prospects)
    if duplicate_counts["exact"]:
        raise PersistenceValidationError(
            "duplicate_selection",
            "La sélection contient plusieurs fois le même contact.",
        )
    for prospect in prospects:
        if not prospect["data"].get("company_name") and not prospect["data"].get("domain"):
            raise PersistenceValidationError(
                "missing_company_identity",
                "Un nom d'entreprise ou un domaine valide est requis pour l'enregistrement.",
            )
        prospect["eligibility"] = assess_contact_eligibility(prospect)

    return {"import": import_meta, "icp": icp, "prospects": prospects}
