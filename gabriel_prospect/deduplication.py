"""Deterministic duplicate signals; preview rows are never merged."""

from .normalization import comparison_text


def _contact_name(data):
    return comparison_text(data.get("contact_full_name"))


def detect_duplicates(prospects):
    exact_indexes = {}
    company_indexes = {}
    exact_count = 0
    possible_count = 0

    for prospect in prospects:
        data = prospect["data"]
        row_number = prospect["source_row"]
        email = data.get("email")
        linkedin = data.get("linkedin_url")
        domain = data.get("domain")
        contact_name = _contact_name(data)
        company_name = comparison_text(data.get("company_name"))

        exact_keys = []
        if email:
            exact_keys.append(("email", email))
        if linkedin:
            exact_keys.append(("linkedin", linkedin.casefold()))
        if domain and contact_name:
            exact_keys.append(("domain_contact", domain, contact_name))

        matched_row = next(
            (exact_indexes[key] for key in exact_keys if key in exact_indexes),
            None,
        )
        if matched_row is not None:
            prospect["duplicate"] = {
                "kind": "exact",
                "matched_row": matched_row,
                "reason": "Un identifiant de contact exact est déjà présent dans ce fichier.",
            }
            exact_count += 1
        else:
            company_keys = []
            if domain:
                company_keys.append(("domain", domain))
            if company_name:
                company_keys.append(("company", company_name))
            possible_row = next(
                (company_indexes[key] for key in company_keys if key in company_indexes),
                None,
            )
            if possible_row is not None:
                prospect["duplicate"] = {
                    "kind": "possible",
                    "matched_row": possible_row,
                    "reason": "Même entreprise détectée ; les contacts restent distincts.",
                }
                possible_count += 1
            else:
                prospect["duplicate"] = None

        for key in exact_keys:
            exact_indexes.setdefault(key, row_number)
        for key in company_keys if matched_row is None else []:
            company_indexes.setdefault(key, row_number)
        if matched_row is not None:
            if domain:
                company_indexes.setdefault(("domain", domain), row_number)
            if company_name:
                company_indexes.setdefault(("company", company_name), row_number)

    return {"exact": exact_count, "possible": possible_count}
