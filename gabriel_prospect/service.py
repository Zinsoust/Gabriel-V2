"""Application service composing parsing, normalization, scoring and dedupe."""

import hashlib

from .deduplication import detect_duplicates
from .importer import parse_csv
from .normalization import normalize_row, normalize_text
from .schema import CANONICAL_FIELDS
from .scoring import default_icp, score_prospect, validate_icp


def _fact_value(field, raw_value, normalized_data):
    normalized_value = normalized_data.get(field)
    if normalized_value is not None:
        return normalized_value
    return normalize_text(raw_value)


def assess_contact_eligibility(prospect):
    """Assess structural outreach readiness independently from ICP fit."""
    blocking_reasons = [
        {
            "code": error["code"],
            "message": error["message"],
        }
        for error in prospect["validation_errors"]
        if error.get("blocking") is True
    ]

    data = prospect["data"]
    if not data.get("email") and not data.get("linkedin_url"):
        blocking_reasons.append({
            "code": "missing_professional_channel",
            "message": "Aucun email valide ni profil LinkedIn valide n'est disponible.",
        })

    duplicate = prospect.get("duplicate")
    if duplicate and duplicate.get("kind") == "exact":
        blocking_reasons.append({
            "code": "exact_duplicate",
            "message": "Ce contact est un doublon exact d'une autre ligne du fichier.",
        })

    return {
        "eligible_for_contact_preparation": not blocking_reasons,
        "status": "eligible" if not blocking_reasons else "ineligible",
        "blocking_reasons": blocking_reasons,
        "requires_human_review": True,
        "assessment_basis": "declared_unverified_data",
    }

def build_import_preview(filename, raw_bytes, mapping=None, icp=None):
    parsed = parse_csv(filename, raw_bytes, mapping=mapping)
    active_icp = validate_icp(icp if icp is not None else default_icp())
    prospects = []

    for row, row_number in zip(parsed.rows, parsed.row_numbers):
        data, validation_errors = normalize_row(row)
        if not data.get("company_name") and not data.get("domain"):
            validation_errors.append({
                "field": "company_name",
                "code": "missing_company_identity",
                "message": "Un nom d'entreprise ou un domaine valide est requis.",
                "severity": "error",
                "blocking": True,
            })
        source_id = f"csv-row-{row_number}"
        facts = []
        fact_ids = {}
        for field, raw_value in row.items():
            if normalize_text(raw_value) is None:
                continue
            fact_id = f"{source_id}:{field}"
            fact_ids[field] = fact_id
            facts.append({
                "fact_id": fact_id,
                "field": field,
                "value": _fact_value(field, raw_value, data),
                "status": "declared_unverified",
                "source_id": source_id,
                "source_column": parsed.mapping[field],
            })

        unknowns = [field for field in CANONICAL_FIELDS if data.get(field) is None]
        prospects.append({
            "source_row": row_number,
            "data": {field: data.get(field) for field in CANONICAL_FIELDS},
            "sources": [{
                "source_id": source_id,
                "type": "csv_import",
                "filename": parsed.filename,
                "row": row_number,
                "verification": "not_independently_verified",
            }],
            "facts": facts,
            "hypotheses": [],
            "unknowns": unknowns,
            "validation_errors": validation_errors,
            "score": score_prospect(data, fact_ids, active_icp),
            "duplicate": None,
        })

    duplicate_counts = detect_duplicates(prospects)
    for prospect in prospects:
        prospect["eligibility"] = assess_contact_eligibility(prospect)

    return {
        "import": {
            "filename": parsed.filename,
            "size_bytes": parsed.size_bytes,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "encoding": parsed.encoding,
            "delimiter": parsed.delimiter,
            "mapping": parsed.mapping,
            "unmapped_columns": parsed.unmapped_columns,
            "persisted": False,
        },
        "icp": active_icp,
        "summary": {
            "rows_received": len(prospects),
            "rows_valid": sum(not prospect["validation_errors"] for prospect in prospects),
            "rows_with_errors": sum(bool(prospect["validation_errors"]) for prospect in prospects),
            "exact_duplicates": duplicate_counts["exact"],
            "possible_duplicates": duplicate_counts["possible"],
            "contact_eligible": sum(
                prospect["eligibility"]["eligible_for_contact_preparation"]
                for prospect in prospects
            ),
            "contact_ineligible": sum(
                not prospect["eligibility"]["eligible_for_contact_preparation"]
                for prospect in prospects
            ),
        },
        "prospects": prospects,
    }
