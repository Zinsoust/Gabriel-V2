"""Conservative normalization without enrichment or network access."""

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(value):
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = _CONTROL_RE.sub("", text)
    text = " ".join(text.strip().split())
    return text or None


def comparison_text(value):
    text = normalize_text(value) or ""
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def normalize_email(value):
    text = normalize_text(value)
    if not text:
        return None
    candidate = text.casefold()
    if len(candidate) > 254 or not _EMAIL_RE.fullmatch(candidate):
        return None
    return candidate


def normalize_domain(value):
    text = normalize_text(value)
    if not text:
        return None
    candidate = text if "://" in text else f"//{text}"
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or " " in host:
        return None
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def normalize_website(value):
    text = normalize_text(value)
    if not text:
        return None
    candidate = text if "://" in text else f"https://{text}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    domain = normalize_domain(candidate)
    if not domain:
        return None
    scheme = parsed.scheme.casefold()
    if scheme not in ("http", "https"):
        return None
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, domain, path, "", ""))


def normalize_linkedin_url(value):
    text = normalize_text(value)
    if not text:
        return None
    candidate = text if "://" in text else f"https://{text}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    if host not in {"linkedin.com", "www.linkedin.com", "fr.linkedin.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() not in {"in", "company"}:
        return None
    return f"https://www.linkedin.com/{parts[0].casefold()}/{parts[1]}"


def normalize_employee_count(value):
    text = normalize_text(value)
    if not text:
        return None
    match = re.fullmatch(r"(\d[\d\s]*)\s*(?:personnes?|salari[eé]s?|employees?|employ[eé]s?)?", text, re.IGNORECASE)
    if not match:
        return None
    number = int(match.group(1).replace(" ", ""))
    return number if 0 <= number <= 10_000_000 else None


def normalize_phone(value):
    text = normalize_text(value)
    if not text:
        return None
    leading_plus = text.startswith("+")
    digits = "".join(char for char in text if char.isdigit())
    if not 7 <= len(digits) <= 15:
        return None
    return ("+" if leading_plus else "") + digits


def normalize_row(row):
    data = {key: None for key in row}
    errors = []

    for key, value in row.items():
        data[key] = normalize_text(value)

    validators = {
        "email": normalize_email,
        "website": normalize_website,
        "domain": normalize_domain,
        "linkedin_url": normalize_linkedin_url,
        "employee_count": normalize_employee_count,
        "phone": normalize_phone,
    }
    for field, validator in validators.items():
        if field not in row:
            continue
        original = normalize_text(row.get(field))
        normalized = validator(row.get(field))
        data[field] = normalized
        if original and normalized is None:
            errors.append({
                "field": field,
                "code": f"invalid_{field}",
                "message": f"La valeur déclarée pour « {field} » est invalide.",
                "severity": "warning",
                "blocking": False,
            })

    if not data.get("domain"):
        data["domain"] = normalize_domain(data.get("website"))

    if not data.get("contact_full_name"):
        data["contact_full_name"] = normalize_text(
            " ".join(filter(None, (data.get("contact_first_name"), data.get("contact_last_name"))))
        )

    return data, errors
