import json

import pytest

from gabriel_prospect.importer import ImportValidationError, parse_csv
from gabriel_prospect.service import build_import_preview


def _csv(*rows):
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_parse_csv_detects_semicolon_and_maps_french_headers():
    parsed = parse_csv(
        "agences.csv",
        _csv(
            "Entreprise;Type agence;Services;Prénom;Nom;Fonction;Email",
            "Studio Nord;Agence branding;Identité de marque;Alice;Martin;Fondatrice;alice@example.test",
        ),
    )

    assert parsed.delimiter == ";"
    assert parsed.mapping["company_name"] == "Entreprise"
    assert parsed.mapping["job_title"] == "Fonction"
    assert parsed.rows[0]["contact_first_name"] == "Alice"


def test_explicit_mapping_overrides_automatic_mapping():
    parsed = parse_csv(
        "custom.csv",
        _csv("Organisation,Role", "Agence Une,CEO"),
        mapping={"company_name": "Organisation", "job_title": "Role"},
    )

    assert parsed.rows[0]["company_name"] == "Agence Une"
    assert parsed.rows[0]["job_title"] == "CEO"


@pytest.mark.parametrize("filename", ["agences.xlsx", "agences.txt", "agences.csv.exe"])
def test_only_csv_extension_is_accepted(filename):
    with pytest.raises(ImportValidationError) as exc:
        parse_csv(filename, b"company_name\nAgence\n")
    assert exc.value.code == "unsupported_file_type"


def test_file_size_is_limited_to_two_megabytes():
    with pytest.raises(ImportValidationError) as exc:
        parse_csv("agences.csv", b"x" * (2 * 1024 * 1024 + 1))
    assert exc.value.code == "file_too_large"


def test_import_is_limited_to_one_thousand_data_rows():
    content = "company_name\n" + "\n".join(f"Agence {i}" for i in range(1001))
    with pytest.raises(ImportValidationError) as exc:
        parse_csv("agences.csv", content.encode("utf-8"))
    assert exc.value.code == "too_many_rows"


def test_malformed_rows_are_rejected_without_echoing_their_content():
    secret_cell = "do-not-leak-123"
    with pytest.raises(ImportValidationError) as exc:
        parse_csv("agences.csv", _csv("Entreprise,Email", f"Agence,{secret_cell},extra"))
    assert exc.value.code == "malformed_csv"
    assert secret_cell not in str(exc.value)


def test_preview_separates_declarations_sources_hypotheses_and_unknowns():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Type agence,Services,Prénom,Nom,Fonction,Email,Pays",
            "Studio Nord,Agence branding,Identité de marque,Alice,Martin,Fondatrice,alice@example.test,France",
        ),
    )
    prospect = result["prospects"][0]

    assert prospect["hypotheses"] == []
    assert "employee_count" in prospect["unknowns"]
    assert all(fact["status"] == "declared_unverified" for fact in prospect["facts"])
    assert all(fact["source_id"] == prospect["sources"][0]["source_id"] for fact in prospect["facts"])
    assert prospect["sources"][0]["type"] == "csv_import"
    assert "raw_csv" not in result


def test_normalization_canonicalizes_email_domain_linkedin_and_employee_count():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Site,Effectif,Email,LinkedIn",
            "  Studio   Nord  ,HTTPS://WWW.Studio-Nord.FR/a-propos/,12 personnes, Alice@Example.TEST ,https://fr.linkedin.com/in/alice-martin/?trk=x",
        ),
    )
    data = result["prospects"][0]["data"]

    assert data["company_name"] == "Studio Nord"
    assert data["domain"] == "studio-nord.fr"
    assert data["employee_count"] == 12
    assert data["email"] == "alice@example.test"
    assert data["linkedin_url"] == "https://www.linkedin.com/in/alice-martin"


def test_invalid_email_is_reported_and_not_treated_as_professional_channel():
    result = build_import_preview(
        "agences.csv",
        _csv("Entreprise,Email", "Studio Nord,not-an-email"),
    )
    prospect = result["prospects"][0]

    assert prospect["data"]["email"] is None
    assert any(error["field"] == "email" for error in prospect["validation_errors"])
    channel = next(item for item in prospect["score"]["criteria"] if item["criterion"] == "professional_channel")
    assert channel["points"] == 0


def test_blocking_data_error_does_not_erase_icp_score_but_blocks_contact_preparation():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Type agence,Services,Fonction,Effectif,Pays,Email",
            "Studio Nord,Agence marketing,Marketing digital,Responsable acquisition,4,France,not-an-email",
        ),
    )
    prospect = result["prospects"][0]

    assert prospect["score"]["total"] == 70
    assert prospect["eligibility"]["eligible_for_contact_preparation"] is False
    assert "missing_professional_channel" in {
        reason["code"] for reason in prospect["eligibility"]["blocking_reasons"]
    }


def test_low_icp_score_with_valid_data_can_remain_contact_eligible():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Type agence,Services,Fonction,Effectif,Pays,LinkedIn",
            "Maison Signal,Relations presse,Relations presse,Consultante,8,Allemagne,https://linkedin.com/in/lea-test",
        ),
    )
    prospect = result["prospects"][0]

    assert prospect["score"]["total"] == 25
    assert prospect["eligibility"]["eligible_for_contact_preparation"] is True


def test_row_without_company_name_or_domain_is_invalid_but_remains_in_preview():
    result = build_import_preview(
        "agences.csv",
        _csv("Prénom,Nom,Email", "Alice,Martin,alice@example.test"),
    )
    prospect = result["prospects"][0]
    identity_error = next(
        error for error in prospect["validation_errors"]
        if error["code"] == "missing_company_identity"
    )
    assert identity_error["blocking"] is True
    assert prospect["score"]["total"] == 10
    assert prospect["eligibility"]["eligible_for_contact_preparation"] is False
    assert result["summary"]["rows_with_errors"] == 1


def test_exact_duplicate_by_email_is_flagged_but_rows_are_kept():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Prénom,Nom,Email",
            "Studio Nord,Alice,Martin,alice@example.test",
            "Studio Nord,Alice,Martin,ALICE@example.test",
        ),
    )

    assert len(result["prospects"]) == 2
    assert result["summary"]["exact_duplicates"] == 1
    assert result["prospects"][1]["duplicate"]["kind"] == "exact"
    assert result["prospects"][1]["duplicate"]["matched_row"] == 2
    assert result["prospects"][1]["eligibility"]["eligible_for_contact_preparation"] is False


def test_two_contacts_at_same_company_are_never_exact_duplicates_from_domain_alone():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Site,Prénom,Nom,Email",
            "Studio Nord,https://studio.test,Alice,Martin,alice@studio.test",
            "Studio Nord,https://studio.test,Bob,Durand,bob@studio.test",
        ),
    )

    assert result["summary"]["exact_duplicates"] == 0
    assert result["summary"]["possible_duplicates"] == 1
    assert result["prospects"][1]["duplicate"]["kind"] == "possible"
    assert result["prospects"][1]["eligibility"]["eligible_for_contact_preparation"] is True
    assert result["prospects"][1]["eligibility"]["requires_human_review"] is True


def test_same_domain_and_same_contact_name_is_an_exact_duplicate():
    result = build_import_preview(
        "agences.csv",
        _csv(
            "Entreprise,Site,Prénom,Nom",
            "Studio Nord,https://studio.test,Alice,Martin",
            "Studio Nord,https://www.studio.test,Alice,Martin",
        ),
    )
    assert result["summary"]["exact_duplicates"] == 1


def test_blank_rows_are_ignored_and_source_rows_remain_physical_csv_rows():
    result = build_import_preview(
        "agences.csv",
        _csv("Entreprise,Email", "", "Studio Nord,hello@studio.test"),
    )
    assert result["summary"]["rows_received"] == 1
    assert result["prospects"][0]["source_row"] == 3


def test_mapping_rejects_unknown_canonical_field():
    with pytest.raises(ImportValidationError) as exc:
        parse_csv(
            "agences.csv",
            _csv("Entreprise", "Studio Nord"),
            mapping={"secret_internal_field": "Entreprise"},
        )
    assert exc.value.code == "invalid_mapping"


def test_mapping_rejects_non_string_source_columns_cleanly():
    with pytest.raises(ImportValidationError) as exc:
        parse_csv(
            "agences.csv",
            _csv("Entreprise", "Studio Nord"),
            mapping={"company_name": ["Entreprise"]},
        )
    assert exc.value.code == "invalid_mapping"


def test_preview_metadata_does_not_contain_file_content_or_personal_data():
    result = build_import_preview(
        "sensible.csv",
        _csv("Entreprise,Email", "Studio Secret,private@example.test"),
    )
    serialized_meta = json.dumps(result["import"], ensure_ascii=False)
    assert "Studio Secret" not in serialized_meta
    assert "private@example.test" not in serialized_meta
    assert result["import"]["filename"] == "sensible.csv"


def test_imported_declarations_are_never_labeled_as_verified_facts():
    result = build_import_preview(
        "agences.csv",
        _csv("Entreprise,Email", "Studio Nord,hello@studio.test"),
    )
    prospect = result["prospects"][0]

    assert prospect["facts"]
    assert {fact["status"] for fact in prospect["facts"]} == {"declared_unverified"}
    assert prospect["sources"][0]["verification"] == "not_independently_verified"
    assert prospect["eligibility"]["assessment_basis"] == "declared_unverified_data"
