"""Configurable and fully deterministic ICP scoring on 100 points."""

import copy

from .normalization import comparison_text


CRITERIA = (
    "agency_type",
    "services_fit",
    "decision_maker",
    "employee_count",
    "geography",
    "professional_channel",
)


class IcpValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.status_code = 400


def default_icp():
    return {
        "name": "Agences B2B cibles Gabriel",
        "version": "1.0",
        "weights": {
            "agency_type": 25,
            "services_fit": 20,
            "decision_maker": 20,
            "employee_count": 15,
            "geography": 10,
            "professional_channel": 10,
        },
        "agency_types": [
            "agence marketing", "agence social media", "agence branding",
            "agence de communication", "studio branding", "studio créatif",
            "marketing agency", "social media agency", "branding agency",
        ],
        "target_services": [
            "identité de marque", "strategie de marque", "stratégie de marque",
            "branding", "social media", "marketing digital", "content marketing",
            "création de contenu", "creation de contenu", "communication digitale",
        ],
        "decision_maker_titles": [
            "fondateur", "fondatrice", "cofondateur", "cofondatrice", "ceo",
            "dirigeant", "dirigeante", "directeur", "directrice", "owner",
            "président", "president", "gérant", "gerant", "associé", "associe",
        ],
        "employee_range": {"min": 2, "max": 50},
        "target_geographies": ["France", "Belgique", "Suisse", "Luxembourg"],
    }

def _validate_string_list(value, field):
    if not isinstance(value, list) or not value or len(value) > 100:
        raise IcpValidationError("invalid_icp", f"Le champ ICP « {field} » est invalide.")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 120:
            raise IcpValidationError("invalid_icp", f"Le champ ICP « {field} » est invalide.")
        cleaned.append(item.strip())
    return cleaned


def validate_icp(value):
    if not isinstance(value, dict):
        raise IcpValidationError("invalid_icp", "Le profil ICP doit être un objet JSON.")
    allowed = {
        "name", "version", "weights", "agency_types", "target_services",
        "decision_maker_titles", "employee_range", "target_geographies",
    }
    if set(value) - allowed:
        raise IcpValidationError("invalid_icp", "Le profil ICP contient des champs inconnus.")

    icp = copy.deepcopy(value)
    weights = icp.get("weights")
    if not isinstance(weights, dict) or set(weights) != set(CRITERIA):
        raise IcpValidationError("invalid_icp_weights", "Les six pondérations ICP sont obligatoires.")
    if any(isinstance(weight, bool) or not isinstance(weight, int) or weight < 0 for weight in weights.values()):
        raise IcpValidationError("invalid_icp_weights", "Les pondérations ICP doivent être des entiers positifs.")
    if sum(weights.values()) != 100:
        raise IcpValidationError("invalid_icp_weights", "Les pondérations ICP doivent totaliser 100.")

    for field in ("agency_types", "target_services", "decision_maker_titles", "target_geographies"):
        icp[field] = _validate_string_list(icp.get(field), field)

    employee_range = icp.get("employee_range")
    if not isinstance(employee_range, dict) or set(employee_range) != {"min", "max"}:
        raise IcpValidationError("invalid_icp", "La plage d'effectif ICP est invalide.")
    minimum = employee_range["min"]
    maximum = employee_range["max"]
    if (
        isinstance(minimum, bool) or isinstance(maximum, bool)
        or not isinstance(minimum, int) or not isinstance(maximum, int)
        or minimum < 0 or maximum < minimum or maximum > 10_000_000
    ):
        raise IcpValidationError("invalid_icp", "La plage d'effectif ICP est invalide.")

    for field in ("name", "version"):
        if not isinstance(icp.get(field), str) or not icp[field].strip() or len(icp[field]) > 100:
            raise IcpValidationError("invalid_icp", f"Le champ ICP « {field} » est invalide.")
        icp[field] = icp[field].strip()
    return icp


def _contains_any(value, targets):
    haystack = comparison_text(value)
    padded_haystack = f" {haystack} "
    return bool(haystack) and any(
        f" {comparison_text(target)} " in padded_haystack for target in targets
    )


def _criterion(name, weight, matched, known, explanation, fact_ids):
    return {
        "criterion": name,
        "weight": weight,
        "points": weight if matched else 0,
        "matched": bool(matched),
        "status": "matched" if matched else ("not_matched" if known else "unknown"),
        "explanation": explanation,
        "fact_ids": list(dict.fromkeys(fact_ids)),
    }


def score_prospect(data, fact_ids, icp):
    icp = validate_icp(icp)
    weights = icp["weights"]
    criteria = []

    agency = data.get("agency_type")
    agency_match = _contains_any(agency, icp["agency_types"]) if agency else False
    criteria.append(_criterion(
        "agency_type", weights["agency_type"], agency_match, bool(agency),
        "Le type d'agence déclaré correspond à la cible." if agency_match else (
            "Le type d'agence déclaré ne correspond pas aux types configurés." if agency
            else "Le type d'agence n'est pas déclaré."
        ),
        [fact_ids["agency_type"]] if agency and "agency_type" in fact_ids else [],
    ))

    services = data.get("services")
    services_match = _contains_any(services, icp["target_services"]) if services else False
    criteria.append(_criterion(
        "services_fit", weights["services_fit"], services_match, bool(services),
        "Les prestations déclarées correspondent aux besoins couverts par Gabriel." if services_match else (
            "Les prestations déclarées ne correspondent pas aux prestations configurées." if services
            else "Les prestations ne sont pas déclarées."
        ),
        [fact_ids["services"]] if services and "services" in fact_ids else [],
    ))

    title = data.get("job_title")
    title_match = _contains_any(title, icp["decision_maker_titles"]) if title else False
    criteria.append(_criterion(
        "decision_maker", weights["decision_maker"], title_match, bool(title),
        "La fonction déclarée est décisionnaire." if title_match else (
            "La fonction déclarée ne correspond pas aux fonctions décisionnaires configurées." if title
            else "La fonction du contact n'est pas déclarée."
        ),
        [fact_ids["job_title"]] if title and "job_title" in fact_ids else [],
    ))

    employee_count = data.get("employee_count")
    employee_known = isinstance(employee_count, int) and not isinstance(employee_count, bool)
    employee_match = employee_known and icp["employee_range"]["min"] <= employee_count <= icp["employee_range"]["max"]
    criteria.append(_criterion(
        "employee_count", weights["employee_count"], employee_match, employee_known,
        "L'effectif déclaré est dans la plage cible." if employee_match else (
            "L'effectif déclaré est hors de la plage cible." if employee_known
            else "L'effectif n'est pas déclaré ou exploitable."
        ),
        [fact_ids["employee_count"]] if employee_known and "employee_count" in fact_ids else [],
    ))

    places = [data.get("country"), data.get("city")]
    places = [place for place in places if place]
    geography_match = any(_contains_any(place, icp["target_geographies"]) for place in places)
    geography_fact_ids = [fact_ids[field] for field in ("country", "city") if data.get(field) and field in fact_ids]
    criteria.append(_criterion(
        "geography", weights["geography"], geography_match, bool(places),
        "La zone géographique déclarée correspond à la cible." if geography_match else (
            "La zone géographique déclarée ne correspond pas aux zones configurées." if places
            else "La zone géographique n'est pas déclarée."
        ),
        geography_fact_ids,
    ))

    channels = [field for field in ("email", "linkedin_url") if data.get(field)]
    criteria.append(_criterion(
        "professional_channel", weights["professional_channel"], bool(channels), bool(channels),
        "Au moins un canal professionnel déclaré est disponible." if channels
        else "Aucun email valide ni profil LinkedIn valide n'est déclaré.",
        [fact_ids[field] for field in channels if field in fact_ids],
    ))

    return {
        "total": sum(item["points"] for item in criteria),
        "maximum": 100,
        "icp_name": icp["name"],
        "icp_version": icp["version"],
        "criteria": criteria,
    }
