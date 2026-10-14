"""Validate Gabriel Prospect MVP 3 against the dedicated Supabase DEV project.

This script is intentionally destructive only for the two validation-only user
scopes declared below. It keeps the five demo agencies for the local React demo
and never deletes the do-not-contact suppression fingerprint it creates.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gabriel_prospect.client import _create_client, _settings
from gabriel_prospect.persistence import prepare_selected_import
from gabriel_prospect.repository import (
    IMPORTS_TABLE,
    PROSPECTS_TABLE,
    SUPPRESSIONS_TABLE,
    ProspectConflict,
    ProspectNotFound,
    SupabaseProspectRepository,
)
from gabriel_prospect.service import build_import_preview

CSV_PATH = ROOT / "examples" / "gabriel_prospect_demo_5_agences.csv"

# Fingerprint pinned after the operator identified this endpoint as the
# independent gabriel-prospect-dev-steph project. It prevents an accidental
# execution against another Supabase endpoint without publishing the URL.
EXPECTED_DEV_ENDPOINT_SHA256 = (
    "f43eaba0dbca26c0d5f8ac5b763daa8a87b89ce7e914b2b3821eac17996dabfb"
)

DEMO_USER = "dec0de00-0000-4000-8000-000000000001"
ISOLATION_USER = "gabriel-mvp3-isolation-b-20261014"
DNC_USER = "gabriel-mvp3-dnc-validation-20261014"


class ValidationFailure(RuntimeError):
    pass


def require(condition: bool, label: str) -> None:
    if not condition:
        raise ValidationFailure(label)
    print(f"PASS - {label}")


def prepared_from_csv(filename: str, raw_bytes: bytes) -> dict:
    preview = build_import_preview(filename, raw_bytes)
    payload = {
        "import": preview["import"],
        "icp": preview["icp"],
        "prospects": preview["prospects"],
    }
    return prepare_selected_import(payload)


def delete_validation_scope(client, repository, user_id: str) -> None:
    rows = repository.list_prospects(user_id, limit=500)
    for row in rows:
        repository.delete_prospect(user_id, row["prospect_id"])
    client.table(IMPORTS_TABLE).delete().eq("user_id", user_id).execute()


def main() -> int:
    url, secret = _settings()
    require(bool(url and secret), "configuration Prospect dédiée présente")
    endpoint_hash = hashlib.sha256(url.rstrip("/").encode("utf-8")).hexdigest()
    require(
        endpoint_hash == EXPECTED_DEV_ENDPOINT_SHA256,
        "endpoint limité au projet DEV approuvé",
    )

    client = _create_client(url, secret)
    repository = SupabaseProspectRepository(client)

    for table in (
        IMPORTS_TABLE,
        PROSPECTS_TABLE,
        "gabriel_prospect_events",
        SUPPRESSIONS_TABLE,
    ):
        client.table(table).select("*", count="exact").limit(1).execute()
    require(True, "lecture des quatre tables")

    require(
        not repository.list_prospects(DEMO_USER, limit=500),
        "périmètre de démonstration initialement vide",
    )
    require(
        not repository.list_prospects(ISOLATION_USER, limit=500),
        "périmètre d'isolation initialement vide",
    )

    raw_csv = CSV_PATH.read_bytes()
    prepared = prepared_from_csv(CSV_PATH.name, raw_csv)
    require(len(prepared["prospects"]) == 5, "cinq agences fictives préparées")
    require(
        sum(
            item["eligibility"]["eligible_for_contact_preparation"] is False
            for item in prepared["prospects"]
        )
        == 1,
        "une agence classée à enrichir",
    )

    saved = repository.save_selected(DEMO_USER, prepared)
    require(saved["saved_count"] == 5, "sauvegarde réelle des cinq agences")
    demo_rows = repository.list_prospects(DEMO_USER, limit=50)
    require(len(demo_rows) == 5, "rechargement des cinq prospects")

    enrich_rows = [row for row in demo_rows if row["status"] == "to_enrich"]
    require(len(enrich_rows) == 1, "statut to_enrich persisté")
    qualified_rows = [row for row in demo_rows if row["status"] == "qualified"]
    require(len(qualified_rows) == 4, "quatre prospects qualifiés persistés")

    duplicate = repository.save_selected(DEMO_USER, prepared)
    require(
        duplicate["saved_count"] == 0
        and duplicate["duplicate_count"] == 5
        and {row["reason"] for row in duplicate["duplicates"]}
        == {"existing_contact"},
        "réimport détecté comme cinq doublons",
    )
    client.table(IMPORTS_TABLE).delete().eq("import_id", duplicate["import_id"]).eq(
        "user_id", DEMO_USER
    ).execute()

    commercial_id = qualified_rows[0]["prospect_id"]
    repository.update_status(DEMO_USER, commercial_id, "contact_ready")
    repository.update_status(DEMO_USER, commercial_id, "contacted")
    repository.update_status(DEMO_USER, commercial_id, "replied")
    commercial = repository.get_prospect(DEMO_USER, commercial_id)
    event_pairs = [
        (event["from_status"], event["to_status"])
        for event in commercial["events"]
        if event["event_type"] == "status_changed"
    ]
    require(commercial["status"] == "replied", "statut commercial rechargé")
    require(
        {("qualified", "contact_ready"), ("contact_ready", "contacted"), ("contacted", "replied")}
        <= set(event_pairs),
        "historique des transitions commerciales",
    )

    enrich_id = enrich_rows[0]["prospect_id"]
    blocked_ineligible = False
    try:
        repository.update_status(DEMO_USER, enrich_id, "contacted")
    except ProspectConflict as exc:
        blocked_ineligible = str(exc) == "contact_not_eligible"
    require(blocked_ineligible, "prise de contact refusée pour to_enrich")
    require(
        repository.get_prospect(DEMO_USER, enrich_id)["status"] == "to_enrich",
        "to_enrich inchangé après le refus",
    )

    isolated_save = repository.save_selected(ISOLATION_USER, prepared)
    require(isolated_save["saved_count"] == 5, "mêmes contacts autorisés pour un autre utilisateur")
    require(
        len(repository.list_prospects(ISOLATION_USER, limit=50)) == 5
        and len(repository.list_prospects(DEMO_USER, limit=50)) == 5,
        "listes utilisateurs isolées",
    )
    cross_read_blocked = False
    try:
        repository.get_prospect(ISOLATION_USER, commercial_id)
    except ProspectNotFound:
        cross_read_blocked = True
    require(cross_read_blocked, "lecture inter-utilisateur refusée par le repository")

    dnc_csv = (
        "Entreprise;Site;Type agence;Services;Prénom;Nom;Fonction;Effectif;Pays;Email;LinkedIn\n"
        "Agence Opposition Démo;https://opposition-gabriel.invalid;Agence branding;"
        "Identité de marque;Camille;Exemple;Fondatrice;10;France;"
        "camille@opposition-gabriel.invalid;\n"
    ).encode("utf-8")
    dnc_prepared = prepared_from_csv("agence-opposition-demo.csv", dnc_csv)
    dnc_first = repository.save_selected(DNC_USER, dnc_prepared)
    require(dnc_first["saved_count"] == 1, "prospect fictif d'opposition sauvegardé")
    dnc_id = dnc_first["saved"][0]["prospect_id"]
    repository.update_status(DNC_USER, dnc_id, "do_not_contact")
    dnc_row = repository.get_prospect(DNC_USER, dnc_id)
    require(
        dnc_row["status"] == "do_not_contact" and bool(dnc_row["do_not_contact_at"]),
        "opposition et horodatage persistés",
    )

    reactivation_blocked = False
    try:
        repository.update_status(DNC_USER, dnc_id, "qualified")
    except ProspectConflict:
        reactivation_blocked = True
    require(reactivation_blocked, "réactivation d'une opposition refusée")

    repository.delete_prospect(DNC_USER, dnc_id)
    suppression_count = (
        client.table(SUPPRESSIONS_TABLE)
        .select("suppression_id", count="exact")
        .eq("user_id", DNC_USER)
        .execute()
        .count
    )
    require(suppression_count == 1, "empreinte d'opposition conservée après suppression")

    dnc_reimport = repository.save_selected(DNC_USER, dnc_prepared)
    require(
        dnc_reimport["saved_count"] == 0
        and dnc_reimport["duplicate_count"] == 1
        and dnc_reimport["duplicates"][0]["reason"] == "do_not_contact",
        "réimport d'un contact opposé refusé",
    )

    direct_row = {key: value for key, value in dnc_row.items() if key != "events"}
    direct_row.update(
        {
            "prospect_id": str(uuid.uuid4()),
            "import_id": dnc_reimport["import_id"],
            "status": "qualified",
            "do_not_contact_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    database_guard_blocked = False
    try:
        client.table(PROSPECTS_TABLE).insert(direct_row).execute()
    except Exception as exc:  # SDK exception types vary by postgrest version.
        database_guard_blocked = "contact identifier is suppressed" in str(exc)
    require(database_guard_blocked, "trigger bloque le contournement direct de l'opposition")

    delete_validation_scope(client, repository, ISOLATION_USER)
    client.table(IMPORTS_TABLE).delete().eq("user_id", DNC_USER).execute()
    require(
        not repository.list_prospects(ISOLATION_USER, limit=50),
        "données temporaires d'isolation nettoyées",
    )
    require(
        not repository.list_prospects(DNC_USER, limit=50),
        "fiche d'opposition supprimée sans supprimer son empreinte",
    )
    require(
        len(repository.list_prospects(DEMO_USER, limit=50)) == 5,
        "cinq agences conservées pour la démonstration React",
    )

    print("RESULT - LIVE_DEV_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESULT - LIVE_DEV_VALIDATION_FAIL ({type(exc).__name__})")
        raise SystemExit(1)
