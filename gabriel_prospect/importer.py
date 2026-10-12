"""Bounded CSV parsing and explicit/automatic prospect column mapping."""

import csv
import io
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from .normalization import normalize_text
from .schema import (
    CANONICAL_FIELDS,
    FIELD_ALIASES,
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_FILE_BYTES,
    MAX_HEADER_CHARS,
    MAX_ROWS,
)


class ImportValidationError(ValueError):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedCsv:
    filename: str
    encoding: str
    delimiter: str
    headers: list
    mapping: dict
    unmapped_columns: list
    rows: list
    row_numbers: list
    size_bytes: int


def _fold_header(value):
    text = normalize_text(value) or ""
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(text.replace("_", " ").replace("-", " ").split())


_ALIASES_BY_FOLDED_HEADER = {
    _fold_header(alias): canonical
    for canonical, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def _safe_filename(filename):
    name = PurePosixPath(str(filename or "").replace("\\", "/")).name
    return normalize_text(name) or ""


def _decode(raw_bytes):
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    try:
        return raw_bytes.decode("cp1252"), "cp1252"
    except UnicodeDecodeError as exc:
        raise ImportValidationError("invalid_encoding", "Encodage CSV non pris en charge.") from exc


def _delimiter(text):
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {candidate: first_line.count(candidate) for candidate in (",", ";", "\t")}
        return max(counts, key=counts.get)


def _build_mapping(headers, explicit):
    if explicit is not None and not isinstance(explicit, dict):
        raise ImportValidationError("invalid_mapping", "Le mapping doit être un objet JSON.")

    mapping = {}
    if explicit:
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in explicit.items()):
            raise ImportValidationError("invalid_mapping", "Le mapping de colonnes est invalide.")
        unknown = set(explicit) - set(CANONICAL_FIELDS)
        invalid_headers = {value for value in explicit.values() if value not in headers}
        duplicate_sources = len(set(explicit.values())) != len(explicit.values())
        if unknown or invalid_headers or duplicate_sources:
            raise ImportValidationError("invalid_mapping", "Le mapping de colonnes est invalide.")
        mapping.update(explicit)

    already_used = set(mapping.values())
    for header in headers:
        if header in already_used:
            continue
        canonical = _ALIASES_BY_FOLDED_HEADER.get(_fold_header(header))
        if canonical and canonical not in mapping:
            mapping[canonical] = header
            already_used.add(header)
    return mapping


def parse_csv(filename, raw_bytes, mapping=None):
    safe_name = _safe_filename(filename)
    if not safe_name.casefold().endswith(".csv"):
        raise ImportValidationError(
            "unsupported_file_type", "Seuls les fichiers CSV sont acceptés.", 415
        )
    if not isinstance(raw_bytes, bytes) or not raw_bytes:
        raise ImportValidationError("empty_file", "Le fichier CSV est vide.")
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ImportValidationError(
            "file_too_large", "Le fichier dépasse la limite de 2 Mo.", 413
        )
    if b"\x00" in raw_bytes:
        raise ImportValidationError("malformed_csv", "Le fichier CSV est invalide.")

    text, encoding = _decode(raw_bytes)
    delimiter = _delimiter(text)
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        raw_headers = next(reader, None)
        if not raw_headers:
            raise ImportValidationError("empty_file", "Le fichier CSV ne contient pas d'en-tête.")
        headers = [normalize_text(header) or "" for header in raw_headers]
        if (
            len(headers) > MAX_COLUMNS
            or any(not header or len(header) > MAX_HEADER_CHARS for header in headers)
            or len(set(headers)) != len(headers)
        ):
            raise ImportValidationError("invalid_headers", "Les en-têtes du CSV sont invalides.")

        resolved_mapping = _build_mapping(headers, mapping)
        rows = []
        row_numbers = []
        for values in reader:
            physical_row = reader.line_num
            if not values or all(not normalize_text(value) for value in values):
                continue
            if len(values) != len(headers) or any(len(value) > MAX_CELL_CHARS for value in values):
                raise ImportValidationError("malformed_csv", "Une ligne du CSV est invalide.")
            if len(rows) >= MAX_ROWS:
                raise ImportValidationError(
                    "too_many_rows", "Le fichier dépasse la limite de 1 000 lignes.", 413
                )
            source_row = dict(zip(headers, values))
            rows.append({canonical: source_row.get(header) for canonical, header in resolved_mapping.items()})
            row_numbers.append(physical_row)
    except ImportValidationError:
        raise
    except (csv.Error, UnicodeError) as exc:
        raise ImportValidationError("malformed_csv", "Le fichier CSV est invalide.") from exc

    if not rows:
        raise ImportValidationError("empty_file", "Le fichier CSV ne contient aucune donnée.")
    if not resolved_mapping:
        raise ImportValidationError(
            "mapping_required",
            "Aucune colonne reconnue. Fournissez un mapping explicite.",
        )

    return ParsedCsv(
        filename=safe_name,
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        mapping=resolved_mapping,
        unmapped_columns=[header for header in headers if header not in resolved_mapping.values()],
        rows=rows,
        row_numbers=row_numbers,
        size_bytes=len(raw_bytes),
    )
