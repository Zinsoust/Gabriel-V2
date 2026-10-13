import copy

import pytest

from gabriel_prospect.persistence import (
    PersistenceValidationError,
    prepare_selected_import,
)
from gabriel_prospect.service import build_import_preview


def _preview(*rows):
    content = (
        "Entreprise,Site,Type agence,Services,Prénom,Nom,Fonction,Effectif,Pays,Email,LinkedIn\n"
        + "\n".join(rows)
        + "\n"
    ).encode("utf-8")
    return build_import_preview("agences.csv", content)


def _payload(preview, indexes=None):
    selected = preview["prospects"] if indexes is None else [preview["prospects"][i] for i in indexes]
    return {
        "import": preview["import"],
        "icp": preview["icp"],
        "prospects": copy.deepcopy(selected),
    }


def test_selected_prospects_are_revalidated_and_scores_are_recomputed():
    preview = _preview(
        "Studio Nord,https://studio.test,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,alice@studio.test,",
    )
    payload = _payload(preview)
    payload["prospects"][0]["score"]["total"] = 0
    payload["prospects"][0]["facts"] = [{"status": "verified", "value": "inventé"}]

    prepared = prepare_selected_import(payload)
    prospect = prepared["prospects"][0]

    assert prospect["score"]["total"] == 100
    assert prospect["hypotheses"] == []
    assert {fact["status"] for fact in prospect["facts"]} == {"declared_unverified"}
    assert prospect["sources"][0]["verification"] == "not_independently_verified"


def test_company_without_contact_is_saved_for_enrichment_not_outreach():
    preview = _preview(
        "Studio Nord,https://studio.test,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,,",
    )

    prepared = prepare_selected_import(_payload(preview))

    assert len(prepared["prospects"]) == 1
    assert prepared["prospects"][0]["eligibility"]["eligible_for_contact_preparation"] is False


def test_missing_company_identity_remains_rejected():
    preview = _preview(
        ",,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,alice@studio.test,",
    )

    with pytest.raises(PersistenceValidationError) as exc:
        prepare_selected_import(_payload(preview))

    assert exc.value.code == "missing_company_identity"


def test_two_contacts_at_same_company_remain_distinct():
    preview = _preview(
        "Studio Nord,https://studio.test,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,alice@studio.test,",
        "Studio Nord,https://studio.test,Agence branding,Branding,Bob,Durand,Directeur,12,France,bob@studio.test,",
    )

    prepared = prepare_selected_import(_payload(preview))

    assert len(prepared["prospects"]) == 2
    assert prepared["prospects"][0]["data"]["domain"] == prepared["prospects"][1]["data"]["domain"]
    assert prepared["prospects"][0]["data"]["email"] != prepared["prospects"][1]["data"]["email"]


def test_duplicate_contacts_inside_selection_are_rejected():
    preview = _preview(
        "Studio Nord,https://studio.test,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,alice@studio.test,",
    )
    payload = _payload(preview)
    duplicate = copy.deepcopy(payload["prospects"][0])
    duplicate["source_row"] = 3
    payload["prospects"].append(duplicate)

    with pytest.raises(PersistenceValidationError) as exc:
        prepare_selected_import(payload)

    assert exc.value.code == "duplicate_selection"


@pytest.mark.parametrize("mutation", [
    lambda payload: payload.update({"prospects": []}),
    lambda payload: payload["import"].update({"sha256": "not-a-sha"}),
    lambda payload: payload["prospects"][0].update({"source_row": "2"}),
])
def test_save_payload_rejects_malformed_input(mutation):
    preview = _preview(
        "Studio Nord,https://studio.test,Agence branding,Branding,Alice,Martin,Fondatrice,12,France,alice@studio.test,",
    )
    payload = _payload(preview)
    mutation(payload)

    with pytest.raises(PersistenceValidationError):
        prepare_selected_import(payload)
