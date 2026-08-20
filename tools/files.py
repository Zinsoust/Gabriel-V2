"""Outils de lecture de fichiers.

Pipeline réel déjà en place côté route d'upload (``app.py``) : parser le
fichier, puis normaliser les items obtenus vers le contrat commentaire
commun. Ce module déclare exactement cette chaîne, pas seulement le parsing
brut — c'est ce qu'un appelant veut réellement en sortie.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _parse_comments_file(filename, raw_bytes, forced_column=None):
    from services.file_importer import normalize_comment_items, parse_comments_file
    parsed = parse_comments_file(filename, raw_bytes, forced_column=forced_column)
    normalized = normalize_comment_items(parsed['items'], source_file=filename)
    return {
        'items': normalized,
        'file_type': parsed['file_type'],
        'detected_columns': parsed.get('detected_columns', []),
        'selected_column': parsed.get('selected_column', ''),
        'warning': parsed.get('warning', ''),
    }


PARSE_COMMENTS_FILE = ToolSpec(
    id='files.parse_comments',
    name='Lecture de fichier de commentaires',
    description=(
        "Lit un fichier CSV, Excel, JSON ou TXT et en extrait des "
        "commentaires normalisés — même chaîne que la route d'upload."),
    category='files',
    inputs=(
        ToolInput('filename', "Nom du fichier, pour en déduire le format"),
        ToolInput('raw_bytes', "Contenu brut du fichier (5 Mo maximum)"),
        ToolInput('forced_column', "Colonne à utiliser si l'auto-détection ne suffit pas",
                  required=False),
    ),
    output="{items: [...], file_type, detected_columns, selected_column, warning}",
    deterministic=True,    # mêmes octets → même résultat, aucun réseau
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,        # local, borné par la limite de taille déjà appliquée
)


def register_all() -> None:
    registry.register(FunctionTool(PARSE_COMMENTS_FILE, _parse_comments_file))


register_all()
