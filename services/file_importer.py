# ─── Gabriel — Import de fichiers commentaires (CSV / Excel / JSON / TXT) ─────
#
# Transforme un fichier uploadé en liste de commentaires au format standard
# Gabriel, prêt pour le pipeline Psychologue. Aucun fichier n'est écrit sur
# disque : tout le parsing se fait en mémoire.
#
# Sécurité :
#   - taille max 5 MB (vérifiée avant lecture complète)
#   - extensions et MIME types en liste blanche
#   - neutralisation des préfixes de formule Excel (=, +cmd, @…)
#   - aucun contenu exécuté, aucune évaluation de formule
#   - logs : uniquement type / count / status — jamais le contenu

import csv
import io
import json

FILE_MAX_BYTES  = 5 * 1024 * 1024   # 5 MB
COMMENTS_MAX    = 500                # aligné sur LIMITS['comments_max_count']
TEXT_MIN_CHARS  = 3                  # aligné sur parse_manual_comments (> 2)
TEXT_MAX_CHARS  = 2000               # tronquer les textes très longs
PREVIEW_COUNT   = 15

ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.json', '.txt'}

# MIME types tolérés (les navigateurs varient — l'extension + le parsing
# réussi restent la vraie validation)
ALLOWED_MIME_PREFIXES = (
    'text/csv', 'text/plain', 'application/csv',
    'application/json',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml',
    'application/octet-stream',
    '',  # certains navigateurs n'envoient rien
)

# Colonnes candidates (correspondance exacte, insensible à la casse)
CANDIDATE_COLUMNS = [
    'comment', 'comments', 'commentaire', 'commentaires',
    'text', 'texte', 'message', 'review', 'avis', 'feedback',
    'content', 'body', 'response', 'verbatim',
]

# Champs candidats dans les objets JSON
CANDIDATE_JSON_KEYS = CANDIDATE_COLUMNS

# Clés racines acceptées pour un objet JSON englobant
JSON_ROOT_KEYS = ['comments', 'reviews', 'data', 'items', 'results']

# Champs méta conservés lors de la normalisation
_META_FIELDS = {
    'author':  ('author', 'auteur', 'username', 'user', 'name', 'pseudo'),
    'likes':   ('likes', 'like_count', 'votes', 'upvotes'),
    'rating':  ('rating', 'note', 'stars', 'score'),
    'date':    ('date', 'created_at', 'published_at', 'timestamp', 'time'),
}


class FileImportError(Exception):
    """Erreur d'import avec message utilisateur affichable."""


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

def parse_comments_file(filename, raw_bytes, forced_column=None):
    """
    Parse un fichier (CSV/XLSX/XLS/JSON/TXT) et retourne :
      {file_type, detected_columns, selected_column, items, warning}
    items = liste de dicts bruts {'text': ..., méta éventuelle}.
    Lève FileImportError avec un message utilisateur en cas de problème.
    """
    ext = _extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise FileImportError("Format non supporté. Formats acceptés : CSV, Excel (.xlsx/.xls), JSON ou TXT.")
    if len(raw_bytes) > FILE_MAX_BYTES:
        raise FileImportError("Le fichier est trop lourd (maximum 5 MB).")
    if not raw_bytes:
        raise FileImportError("Le fichier est vide.")

    if ext == '.csv':
        result = _parse_csv(raw_bytes, forced_column)
        result['file_type'] = 'csv'
    elif ext in ('.xlsx', '.xls'):
        result = _parse_excel(raw_bytes, ext, forced_column)
        result['file_type'] = 'xlsx' if ext == '.xlsx' else 'xls'
    elif ext == '.json':
        result = _parse_json(raw_bytes, forced_column)
        result['file_type'] = 'json'
    else:
        result = _parse_txt(raw_bytes)
        result['file_type'] = 'txt'

    if not result.get('items'):
        raise FileImportError("Aucune colonne de commentaire détectée dans le fichier.")
    return result


def check_mime(mimetype):
    """MIME type toléré ? (liste blanche souple — l'extension reste le vrai filtre)."""
    mt = (mimetype or '').lower()
    return any(mt.startswith(p) for p in ALLOWED_MIME_PREFIXES if p) or mt == ''


# ══════════════════════════════════════════════════════════════════════════════
# CSV
# ══════════════════════════════════════════════════════════════════════════════

def _decode(raw_bytes):
    """utf-8 (avec BOM) d'abord, fallback latin-1."""
    for enc in ('utf-8-sig', 'utf-8'):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode('latin-1', errors='replace')


def _sniff_delimiter(text):
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
    except csv.Error:
        # Fallback simple : le séparateur le plus fréquent sur la 1ère ligne
        first = sample.splitlines()[0] if sample.splitlines() else ''
        return ';' if first.count(';') > first.count(',') else ','


def _parse_csv(raw_bytes, forced_column=None):
    text = _decode(raw_bytes)
    delimiter = _sniff_delimiter(text)
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = [r for r in reader if r]
    except csv.Error:
        raise FileImportError("Fichier CSV malformé — impossible de le lire.")
    if not rows or not reader.fieldnames:
        raise FileImportError("Aucune donnée exploitable dans le fichier CSV.")
    columns = [c for c in reader.fieldnames if c]
    return _extract_from_records(rows, columns, forced_column)


# ══════════════════════════════════════════════════════════════════════════════
# Excel
# ══════════════════════════════════════════════════════════════════════════════

def _parse_excel(raw_bytes, ext, forced_column=None):
    try:
        import pandas as pd
    except ImportError:
        raise FileImportError("Lecture Excel indisponible sur ce serveur. Exportez en CSV.")
    engine = 'openpyxl' if ext == '.xlsx' else None  # xlrd requis pour .xls
    try:
        sheets = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=None, engine=engine)
    except ImportError:
        raise FileImportError("Format .xls ancien non supporté sur ce serveur. Exportez en .xlsx ou CSV.")
    except Exception:
        raise FileImportError("Fichier Excel malformé — impossible de le lire.")
    if not sheets:
        raise FileImportError("Aucune donnée exploitable dans le fichier Excel.")

    # Choisir l'onglet avec le plus de lignes exploitables
    best_df = max(sheets.values(), key=lambda df: len(df.dropna(how='all')))
    best_df = best_df.dropna(how='all')
    if best_df.empty:
        raise FileImportError("Aucune donnée exploitable dans le fichier Excel.")

    columns = [str(c) for c in best_df.columns]
    records = []
    for _, row in best_df.iterrows():
        rec = {}
        for c in best_df.columns:
            v = row[c]
            rec[str(c)] = '' if v is None or (isinstance(v, float) and v != v) else v
        records.append(rec)
    return _extract_from_records(records, columns, forced_column)


# ══════════════════════════════════════════════════════════════════════════════
# JSON
# ══════════════════════════════════════════════════════════════════════════════

def _parse_json(raw_bytes, forced_column=None):
    try:
        data = json.loads(_decode(raw_bytes))
    except (json.JSONDecodeError, ValueError):
        raise FileImportError("Fichier JSON malformé — impossible de le lire.")

    # Objet englobant : {"reviews": [...]} etc.
    if isinstance(data, dict):
        for key in JSON_ROOT_KEYS:
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise FileImportError(
                "Structure JSON non reconnue. Attendu : un tableau, ou un objet "
                "avec une clé comments/reviews/data/items/results.")

    if not isinstance(data, list) or not data:
        raise FileImportError("Aucune donnée exploitable dans le fichier JSON.")

    # Tableau de strings
    if all(isinstance(x, str) for x in data):
        items = [{'text': x} for x in data]
        return {'detected_columns': [], 'selected_column': '', 'items': items, 'warning': ''}

    # Tableau d'objets
    records = [x for x in data if isinstance(x, dict)]
    if not records:
        raise FileImportError("Aucune donnée exploitable dans le fichier JSON.")
    columns = list({k for r in records for k in r.keys()})
    return _extract_from_records(records, columns, forced_column)


# ══════════════════════════════════════════════════════════════════════════════
# Texte brut — une ligne = un commentaire
# ══════════════════════════════════════════════════════════════════════════════

def _parse_txt(raw_bytes):
    items = [{'text': line.strip()} for line in _decode(raw_bytes).splitlines() if line.strip()]
    if not items:
        raise FileImportError("Aucun commentaire détecté dans le fichier texte.")
    return {
        'detected_columns': [],
        'selected_column': '',
        'items': items,
        'warning': '',
    }


# ══════════════════════════════════════════════════════════════════════════════
# Détection de colonnes + extraction
# ══════════════════════════════════════════════════════════════════════════════

def detect_comment_columns(records, columns):
    """Retourne les colonnes candidates, ordonnées par volume de texte exploitable."""
    candidates = []
    for col in columns:
        low = str(col).strip().lower()
        exact = low in CANDIDATE_COLUMNS
        fuzzy = any(tok in low for tok in CANDIDATE_COLUMNS)
        if exact or fuzzy:
            candidates.append((col, 0 if exact else 1))

    # Aucune colonne nommée → scoring par contenu : colonne avec le plus de texte
    if not candidates:
        scored = []
        for col in columns:
            texts = [str(r.get(col, '') or '') for r in records[:200]]
            usable = [t for t in texts if len(t.strip()) >= 15]
            if len(usable) >= max(2, len(texts) * 0.3):
                scored.append((col, sum(len(t) for t in usable)))
        scored.sort(key=lambda x: -x[1])
        return [c for c, _ in scored[:3]]

    # Trier : exact d'abord, puis volume de texte exploitable
    def text_volume(col):
        return sum(len(str(r.get(col, '') or '').strip()) for r in records[:200])
    candidates.sort(key=lambda t: (t[1], -text_volume(t[0])))
    return [c for c, _ in candidates]


def _extract_from_records(records, columns, forced_column=None):
    detected = detect_comment_columns(records, columns)
    if forced_column:
        if forced_column not in columns:
            raise FileImportError(f"Colonne « {forced_column} » introuvable dans le fichier.")
        selected = forced_column
    elif detected:
        selected = detected[0]
    else:
        raise FileImportError("Aucune colonne de commentaire détectée dans le fichier.")

    warning = ''
    if not forced_column and len(detected) > 1:
        warning = (f"Plusieurs colonnes candidates détectées — "
                   f"« {selected} » a été choisie automatiquement.")

    items = []
    for r in records:
        item = {'text': str(r.get(selected, '') or '')}
        for field, aliases in _META_FIELDS.items():
            for a in aliases:
                for k, v in r.items():
                    if str(k).strip().lower() == a and v not in (None, ''):
                        item[field] = v
                        break
                if field in item:
                    break
        items.append(item)

    return {
        'detected_columns': detected,
        'selected_column':  selected,
        'items':            items,
        'warning':          warning,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Normalisation → format standard Gabriel
# ══════════════════════════════════════════════════════════════════════════════

def _neutralize_formula(text):
    """Neutralise les préfixes de formule tableur (=SUM, +cmd, @…) —
    évite l'injection de formule si le texte est réexporté en CSV/Excel."""
    t = text.lstrip()
    while t[:1] in ('=', '+', '@'):
        t = t[1:].lstrip()
    return t


def normalize_comment_items(items, source_file=''):
    """
    Transforme les items bruts en format standard Gabriel :
      {text, author, likes, rating, date, source, source_file, metadata}
    Supprime vides, doublons exacts, textes trop courts ; tronque les très longs.
    Plafonné à COMMENTS_MAX éléments.
    """
    normalized = []
    seen = set()
    for item in items:
        if isinstance(item, str):
            item = {'text': item}
        if not isinstance(item, dict):
            continue
        text = str(item.get('text', '') or '').strip()
        text = _neutralize_formula(text)
        text = ' '.join(text.split())          # normaliser les espaces
        if len(text) < TEXT_MIN_CHARS:
            continue
        if len(text) > TEXT_MAX_CHARS:
            text = text[:TEXT_MAX_CHARS]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)

        likes = item.get('likes', 0)
        try:
            likes = max(0, int(float(likes)))
        except (TypeError, ValueError):
            likes = 0
        rating = item.get('rating')
        try:
            rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None

        normalized.append({
            'text':        text,
            'author':      str(item.get('author'))[:100] if item.get('author') else 'inconnu',
            'likes':       likes,
            'rating':      rating,
            'date':        str(item.get('date'))[:40] if item.get('date') else None,
            'source':      'file_upload',
            'source_file': str(source_file)[:120],
            'metadata':    {},
        })
        if len(normalized) >= COMMENTS_MAX:
            break
    return normalized


def sanitize_uploaded_comments(raw_list, source_file=''):
    """Re-valide une liste de commentaires renvoyée par le frontend (non fiable).
    Même normalisation que l'upload — garantit le format pipeline."""
    if not isinstance(raw_list, list):
        return []
    return normalize_comment_items(raw_list[:COMMENTS_MAX * 2], source_file)


def extract_texts_for_analysis(normalized_items):
    """Liste des textes seuls (pour aperçu ou pipeline texte)."""
    return [c['text'] for c in normalized_items if c.get('text')]


def _extension(filename):
    name = (filename or '').lower()
    dot = name.rfind('.')
    return name[dot:] if dot >= 0 else ''
