"""Validation déterministe de la réponse, sans second appel LLM."""

import re


_FORBIDDEN = (
    (r"\bSuper\s*!", "Je comprends."),
    (r"\bExcellent point\s*!", "Ce point mérite d'être examiné."),
    (r"\bPas de souci\b", "Je comprends."),
    (r"\bGénial\s*!", "Je comprends."),
)


def validate_response(reply):
    text = (reply or "").strip()
    if not text:
        return {"valid": False, "reply": "", "issues": ["empty_response"]}

    issues = []
    # La conversation ne doit pas prendre la forme d'un rapport Markdown.
    cleaned = re.sub(r"(?m)^#{1,6}\s+", "", text)
    if cleaned != text:
        issues.append("markdown_heading_removed")
    for pattern, replacement in _FORBIDDEN:
        updated = re.sub(pattern, replacement, cleaned, flags=re.I)
        if updated != cleaned:
            issues.append("tone_adjusted")
            cleaned = updated
    return {"valid": True, "reply": cleaned.strip(), "issues": sorted(set(issues))}
