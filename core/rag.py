"""
Gabriel RAG — Retrieval-Augmented Generation
============================================
Charge les fichiers Markdown des dossiers agents/{agent}/rag/ pour chaque agent,
les découpe en chunks, les encode avec le modèle sémantique déjà chargé
dans l'app, et expose search(query, agent, top_k) pour enrichir les prompts.

Structure attendue :
  agents/
    psychologue/rag/   *.md  *.txt  *.pdf
    stratege/rag/      *.md  *.txt  *.pdf
    createur/rag/      *.md  *.txt  *.pdf

Cache des index :
  knowledge/_index/   *.pkl

Ajout de nouveaux documents : déposer des fichiers .md, .txt ou .pdf dans
agents/{agent}/rag/ et appeler rag.reload(agent).
"""

import os
import re
import json
import pickle
import hashlib
import tempfile
import threading
from pathlib import Path
from typing import List, Dict, Tuple, Optional

_BASE_DIR       = Path(__file__).parent.parent
_AGENTS_DIR     = _BASE_DIR / "agents"
_DEFAULT_INDEX_DIR = _BASE_DIR / "knowledge" / "_index"
_INDEX_DIR_ENV = "GABRIEL_RAG_INDEX_DIR"
_index_dir_override: Optional[Path] = None
_cache_lock = threading.RLock()


class RAGError(RuntimeError):
    """Base class for explicit, user-safe RAG failures."""


class RAGCacheError(RAGError):
    """The on-disk cache is unusable or cannot be written safely."""


class RAGEmbeddingUnavailableError(RAGError):
    """Semantic search cannot run because embeddings are unavailable."""


class RAGSearchError(RAGError):
    """Semantic scoring failed after cache and model validation."""


def get_index_dir() -> Path:
    """Return the active cache directory without creating it."""
    if _index_dir_override is not None:
        return _index_dir_override
    configured = os.environ.get(_INDEX_DIR_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = _BASE_DIR / path
        return path.resolve()
    return _DEFAULT_INDEX_DIR


def configure_index_dir(path: Optional[Path]) -> Path:
    """Inject a cache directory and clear only the in-memory registry."""
    global _index_dir_override
    _index_dir_override = None if path is None else Path(path).expanduser().resolve()
    clear_runtime_cache()
    return get_index_dir()

# Sous-RAGs spécialisés : index séparés pointant vers des sous-dossiers
_CUSTOM_AGENT_DIRS: Dict[str, Path] = {
    "psychologue_psycho":  _AGENTS_DIR / "psychologue" / "rag" / "psychologie",
    "psychologue_socio":   _AGENTS_DIR / "psychologue" / "rag" / "socioculturel",
}

def _agent_rag_dir(agent: str) -> Path:
    """Retourne le dossier rag/ de l'agent (ou du sous-agent spécialisé)."""
    if agent in _CUSTOM_AGENT_DIRS:
        return _CUSTOM_AGENT_DIRS[agent]
    return _AGENTS_DIR / agent / "rag"

AGENTS = ["psychologue", "stratege", "createur", "psychologue_psycho", "psychologue_socio"]
CHUNK_SIZE    = 400   # mots par chunk
CHUNK_OVERLAP = 80    # mots de recouvrement


# ── Modèle sémantique ─────────────────────────────────────────────────────────

_model = None
_model_checked = False
_model_error = None

def _get_model():
    """Réutilise le modèle déjà chargé par nlp_engine (une seule copie en RAM —
    charger deux SentenceTransformer provoque un OOM sur Render 512 Mo)."""
    global _model, _model_checked, _model_error
    if _model is not None:
        _model_checked = True
        return _model
    if _model_checked:
        return None

    _model_checked = True
    errors = []
    try:
        from core.nlp_engine import _get_model as _nlp_get_model
        _model = _nlp_get_model()
    except Exception as exc:
        errors.append(f"nlp_engine:{type(exc).__name__}")
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        except Exception as exc:
            errors.append(f"sentence_transformers:{type(exc).__name__}")
    if _model is None:
        _model_error = ", ".join(errors) or "aucun modèle retourné"
        print(f"[RAG] Recherche sémantique indisponible ({_model_error}).")
    else:
        _model_error = None
    return _model


def embedding_status() -> Dict:
    """Expose a diagnostic without loading or downloading a model."""
    return {
        "checked": _model_checked,
        "available": _model is not None,
        "error": _model_error,
    }


# ── Lecture des documents ─────────────────────────────────────────────────────

def _json_concept_to_text(data: dict) -> str:
    """Convertit un concept_card JSON en texte indexable (nouveau et ancien schéma)."""
    parts = []
    # Nouveau schéma (cartes enrichies)
    if "id" in data and "title" in data:
        parts.append(f"CONCEPT [{data['id']}] : {data.get('title', '')}")
        if data.get("domain"):
            parts.append(f"Domaine : {data['domain']}")
        if data.get("concept"):
            parts.append(f"Concept : {data['concept']}")
        if data.get("definition"):
            parts.append(f"Définition : {data['definition']}")
        for list_key in ("use_when", "dashboard_triggers", "what_to_observe", "warnings", "avoid"):
            val = data.get(list_key)
            if isinstance(val, list) and val:
                parts.append(f"{list_key} : " + " | ".join(str(v) for v in val))
        if data.get("interpretation_rule"):
            parts.append(f"Règle d'interprétation : {data['interpretation_rule']}")
        if data.get("output_guidance"):
            parts.append(f"Guide de sortie : {data['output_guidance']}")
        if data.get("example_interpretation"):
            parts.append(f"Exemple : {data['example_interpretation']}")
        return "\n".join(parts)

    # Ancien schéma (rétrocompatibilité)
    concept = data.get("concept") or data.get("name") or ""
    if concept:
        parts.append(f"CONCEPT : {concept}")
    auteur = data.get("auteur") or data.get("author") or ""
    if auteur:
        parts.append(f"Source : {auteur}")
    definition = data.get("definition") or data.get("description") or ""
    if definition:
        parts.append(f"Définition : {definition}")
    for key in ("mecanismes_resolution", "formes", "strategies", "signaux_commentaires",
                "fonctions", "profils", "mecanismes", "distorsions_frequentes",
                "classement_adaptatif", "signaux_activation", "dimensions"):
        val = data.get(key)
        if isinstance(val, list):
            parts.append(f"{key} : " + " | ".join(str(v) for v in val))
        elif isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, dict):
                    parts.append(f"{k} : " + " | ".join(f"{sk}={sv}" for sk, sv in v.items()))
                elif isinstance(v, list):
                    parts.append(f"{k} : " + " | ".join(str(i) for i in v))
                else:
                    parts.append(f"{k} : {v}")
    impl = data.get("implication_createur") or data.get("implication") or ""
    if impl:
        parts.append(f"Implication créateur : {impl}")
    intensite = data.get("intensite_signal") or ""
    if intensite:
        parts.append(f"Intensité signal : {intensite}")
    return "\n".join(parts)


def _json_list_item_to_text(item: dict) -> str:
    """Converts a generic JSON dict rule/pattern/principle to readable text."""
    if not isinstance(item, dict):
        return ""
    # If it looks like a concept card, use the dedicated converter
    if "id" in item and "title" in item:
        return _json_concept_to_text(item)
    parts = []
    for k, v in item.items():
        if k == "id":
            parts.insert(0, f"[{v}]")
            continue
        label = k.replace("_", " ").capitalize()
        if isinstance(v, list):
            v_str = " | ".join(str(x) for x in v) if v else ""
        elif isinstance(v, dict):
            v_str = " | ".join(f"{dk}: {dv}" for dk, dv in v.items() if dv)
        else:
            v_str = str(v) if v else ""
        if v_str:
            parts.append(f"{label}: {v_str}")
    return "\n".join(parts)


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Ignorer les fichiers de règles de routage
                    if "rag_name" in data and "query_triggers" in data:
                        return ""
                    return _json_concept_to_text(data)
                if isinstance(data, list):
                    # Fichiers de règles stratégiques (tableaux d'objets)
                    texts = [_json_list_item_to_text(item) for item in data if isinstance(item, dict)]
                    return "\n\n---\n\n".join(t for t in texts if t.strip())
                return ""
            except Exception:
                return ""
        if suffix in (".md", ".txt"):
            return path.read_text(encoding="utf-8")
        if suffix == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    return "\n\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
            except ImportError:
                try:
                    import PyPDF2
                    with open(str(path), "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        return "\n\n".join(
                            page.extract_text() or "" for page in reader.pages
                        )
                except ImportError:
                    print(f"[RAG] PDF non lu (pdfplumber ou PyPDF2 requis) : {path.name}")
                    return ""
        if suffix in (".epub",):
            try:
                import ebooklib
                from ebooklib import epub
                from bs4 import BeautifulSoup
                book = epub.read_epub(str(path))
                texts = []
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_content(), "html.parser")
                        texts.append(soup.get_text())
                return "\n\n".join(texts)
            except Exception as e:
                print(f"[RAG] EPUB non lu : {path.name} ({e})")
                return ""
    except Exception as e:
        print(f"[RAG] Erreur lecture {path.name} : {e}")
    return ""


# ── Découpage en chunks ───────────────────────────────────────────────────────

def _chunk_text(text: str, source: str) -> List[Dict]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        window = words[i : i + CHUNK_SIZE]
        chunk_text = " ".join(window).strip()
        if len(chunk_text) > 60:
            chunks.append({
                "text":   chunk_text,
                "source": source,
                "start":  i,
            })
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Index par agent ───────────────────────────────────────────────────────────

_indexes: Dict[str, Dict] = {}


def clear_runtime_cache() -> None:
    """Forget loaded indexes without deleting or rewriting any file."""
    with _cache_lock:
        _indexes.clear()


def _index_path(agent: str) -> Path:
    return get_index_dir() / f"{agent}.pkl"


def _hash_dir(agent_dir: Path) -> str:
    """Hash basé sur le CONTENU des fichiers (et non le mtime).

    Sur Render, chaque déploiement fait un `git clone` frais : tous les mtimes
    valent la date du déploiement et ne correspondent jamais à ceux d'origine.
    Un hash basé sur mtime forcerait donc un rebuild complet de l'index à chaque
    redémarrage (chargement du modèle + ré-encodage → pic mémoire, lenteur).
    Le hash de contenu est déterministe entre machines : l'index .pkl committé
    est réutilisé tel quel sur Render.
    """
    h = hashlib.md5()
    for f in sorted(agent_dir.glob("**/*")):
        if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".epub", ".json"):
            h.update(f.name.encode())
            try:
                h.update(f.read_bytes())
            except Exception:
                h.update(str(f.stat().st_size).encode())
    return h.hexdigest()


def _build_index(agent: str) -> Dict:
    agent_dir = _agent_rag_dir(agent)
    if not agent_dir.exists():
        return {"chunks": [], "embeddings": None, "hash": ""}

    all_chunks = []
    for path in sorted(agent_dir.glob("**/*")):
        if path.is_file() and path.suffix.lower() in (".md", ".txt", ".pdf", ".epub", ".json"):
            text = _read_file(path)
            if text.strip():
                chunks = _chunk_text(text, path.stem)
                all_chunks.extend(chunks)
                print(f"[RAG] {agent}/{path.name} → {len(chunks)} chunks")

    if not all_chunks:
        return {"chunks": all_chunks, "embeddings": None, "hash": _hash_dir(agent_dir)}

    model = _get_model()
    if model is None:
        raise RAGEmbeddingUnavailableError(
            f"Modèle d'embeddings indisponible pour reconstruire l'index RAG '{agent}'."
        )
    try:
        texts = [c["text"] for c in all_chunks]
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    except Exception as exc:
        raise RAGEmbeddingUnavailableError(
            f"Calcul des embeddings impossible pour l'index RAG '{agent}' "
            f"({type(exc).__name__})."
        ) from exc
    if embeddings is None or len(embeddings) != len(all_chunks):
        raise RAGEmbeddingUnavailableError(
            f"Embeddings incomplets pour l'index RAG '{agent}'."
        )
    print(f"[RAG] {agent} : {len(all_chunks)} chunks indexés")

    return {
        "chunks":     all_chunks,
        "embeddings": embeddings,
        "hash":       _hash_dir(agent_dir),
        "schema_version": 1,
        "mode": "semantic",
    }


def _cache_condition(cached, current_hash: str) -> str:
    if not isinstance(cached, dict):
        return "corrupt"
    if cached.get("hash") != current_hash:
        return "stale"
    chunks = cached.get("chunks")
    if not isinstance(chunks, list):
        return "corrupt"
    embeddings = cached.get("embeddings")
    if chunks and embeddings is None:
        return "incomplete"
    if embeddings is not None:
        try:
            if len(embeddings) != len(chunks):
                return "corrupt"
        except TypeError:
            return "corrupt"
    return "valid"


def cache_status(agent: str) -> Dict:
    """Inspect an index without rebuilding or modifying it."""
    agent_dir = _agent_rag_dir(agent)
    idx_file  = _index_path(agent)
    current_hash = _hash_dir(agent_dir) if agent_dir.exists() else ""
    if not idx_file.exists():
        return {
            "agent": agent,
            "status": "missing",
            "file": idx_file.name,
            "source_hash": current_hash,
        }
    try:
        with open(idx_file, "rb") as handle:
            cached = pickle.load(handle)
        condition = _cache_condition(cached, current_hash)
        chunks = cached.get("chunks", []) if isinstance(cached, dict) else []
        embeddings = cached.get("embeddings") if isinstance(cached, dict) else None
        return {
            "agent": agent,
            "status": condition,
            "file": idx_file.name,
            "source_hash": current_hash,
            "cache_hash": cached.get("hash") if isinstance(cached, dict) else None,
            "chunks": len(chunks) if isinstance(chunks, list) else None,
            "has_embeddings": embeddings is not None,
        }
    except Exception as exc:
        return {
            "agent": agent,
            "status": "corrupt",
            "file": idx_file.name,
            "source_hash": current_hash,
            "error_type": type(exc).__name__,
        }


def _write_cache_atomically(idx_file: Path, idx: Dict) -> None:
    idx_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{idx_file.name}.", suffix=".tmp", dir=str(idx_file.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            pickle.dump(idx, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, idx_file)
    except Exception as exc:
        raise RAGCacheError(
            f"Écriture atomique impossible pour l'index RAG '{idx_file.stem}' "
            f"({type(exc).__name__})."
        ) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def _load_or_build(agent: str, force_rebuild: bool = False) -> Dict:
    agent_dir = _agent_rag_dir(agent)
    idx_file = _index_path(agent)
    current_hash = _hash_dir(agent_dir) if agent_dir.exists() else ""

    with _cache_lock:
        condition = "forced" if force_rebuild else "missing"
        if idx_file.exists() and not force_rebuild:
            try:
                with open(idx_file, "rb") as handle:
                    cached = pickle.load(handle)
                condition = _cache_condition(cached, current_hash)
                if condition == "valid":
                    return cached
            except Exception:
                condition = "corrupt"

        try:
            idx = _build_index(agent)
        except RAGEmbeddingUnavailableError as exc:
            raise RAGEmbeddingUnavailableError(
                f"Cache RAG '{agent}' {condition}; reconstruction annulée et "
                "cache existant préservé. " + str(exc)
            ) from exc

        rebuilt_condition = _cache_condition(idx, current_hash)
        if rebuilt_condition != "valid":
            raise RAGCacheError(
                f"Reconstruction invalide de l'index RAG '{agent}' "
                f"({rebuilt_condition}); cache existant préservé."
            )
        _write_cache_atomically(idx_file, idx)
        print(f"[RAG] Index '{agent}' reconstruit atomiquement (cause={condition}).")
        return idx


def load_all():
    for agent in AGENTS:
        _indexes[agent] = _load_or_build(agent)
    print("[RAG] Tous les index chargés.")


def ensure_loaded(agent: str) -> bool:
    """Force le chargement de l'index si pas déjà en cache mémoire.
    Retourne True si un chargement disque a eu lieu (utile pour le timing)."""
    if agent in _indexes:
        return False
    _indexes[agent] = _load_or_build(agent)
    return True


def reload(agent: str):
    """Recharger l'index d'un agent (après ajout de fichiers dans agents/{agent}/rag/)."""
    _indexes.pop(agent, None)
    _indexes[agent] = _load_or_build(agent, force_rebuild=True)
    print(f"[RAG] Index {agent} rechargé depuis agents/{agent}/rag/")


# ── Recherche sémantique ──────────────────────────────────────────────────────

def search(query: str, agent: str, top_k: int = 4) -> List[Dict]:
    """
    Retourne les top_k chunks les plus pertinents pour la requête.
    Chaque chunk : {"text": str, "source": str, "score": float}
    """
    if agent not in _indexes:
        _indexes[agent] = _load_or_build(agent)

    idx = _indexes[agent]
    chunks     = idx.get("chunks", [])
    embeddings = idx.get("embeddings")

    if not chunks:
        return []

    if embeddings is None:
        raise RAGEmbeddingUnavailableError(
            f"L'index RAG '{agent}' ne contient pas d'embeddings sémantiques."
        )
    model = _get_model()
    if model is None:
        raise RAGEmbeddingUnavailableError(
            f"Le modèle d'embeddings requis pour interroger l'index RAG '{agent}' "
            "est indisponible."
        )

    try:
        import numpy as np
        q_emb = model.encode([query])
        # Cosine similarity
        norms  = np.linalg.norm(embeddings, axis=1, keepdims=True)
        q_norm = np.linalg.norm(q_emb)
        sims   = (embeddings @ q_emb.T).flatten() / (norms.flatten() * q_norm + 1e-9)
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [
            {"text": chunks[i]["text"], "source": chunks[i]["source"], "score": float(sims[i])}
            for i in top_idx
            if float(sims[i]) > 0.1
        ]
    except Exception as exc:
        raise RAGSearchError(
            f"Recherche sémantique impossible pour l'index RAG '{agent}' "
            f"({type(exc).__name__})."
        ) from exc


def search_filtered(query: str, agent: str, sources: List[str], top_k: int = 4) -> List[Dict]:
    """
    Comme search() mais restreint aux chunks dont source est dans `sources`.
    `sources` = liste de noms de fichiers sans extension (ex: ["tiktok_script", "viral"]).
    """
    if agent not in _indexes:
        _indexes[agent] = _load_or_build(agent)

    idx    = _indexes[agent]
    chunks = idx.get("chunks", [])
    embs   = idx.get("embeddings")

    # Filtrer par source
    filtered_idx = [i for i, c in enumerate(chunks) if c["source"] in sources]
    if not filtered_idx:
        # Fallback : recherche globale
        return search(query, agent, top_k)

    f_chunks = [chunks[i] for i in filtered_idx]
    if embs is None:
        raise RAGEmbeddingUnavailableError(
            f"L'index RAG '{agent}' ne contient pas d'embeddings sémantiques."
        )
    model = _get_model()
    if model is None:
        raise RAGEmbeddingUnavailableError(
            f"Le modèle d'embeddings requis pour interroger l'index RAG '{agent}' "
            "est indisponible."
        )

    try:
        import numpy as np
        f_embs = embs[filtered_idx]
        q_emb  = model.encode([query])
        norms  = np.linalg.norm(f_embs, axis=1, keepdims=True)
        q_norm = np.linalg.norm(q_emb)
        sims   = (f_embs @ q_emb.T).flatten() / (norms.flatten() * q_norm + 1e-9)
        top    = np.argsort(sims)[::-1][:top_k]
        return [
            {"text": f_chunks[j]["text"], "source": f_chunks[j]["source"], "score": float(sims[j])}
            for j in top if float(sims[j]) > 0.05
        ]
    except Exception as exc:
        raise RAGSearchError(
            f"Recherche sémantique filtrée impossible pour l'index RAG '{agent}' "
            f"({type(exc).__name__})."
        ) from exc


def format_context(results: List[Dict], max_chars: int = 1800) -> str:
    """Formate les résultats RAG pour injection dans un prompt."""
    if not results:
        return ""
    parts = []
    total = 0
    for r in results:
        snippet = r["text"][:600]
        entry = f"[{r['source']}]\n{snippet}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n---\n\n".join(parts)


# ── Concept cards enrichies ───────────────────────────────────────────────────

def load_concept_cards(rag_name: str) -> List[Dict]:
    """
    Charge toutes les cartes de concept JSON d'un RAG spécialisé.
    rag_name: 'psychologie' ou 'socioculturel'
    """
    rag_dir = _AGENTS_DIR / "psychologue" / "rag" / rag_name / "concept_cards"
    cards = []
    if not rag_dir.exists():
        return cards
    for path in sorted(rag_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "id" in data:
                cards.append(data)
        except Exception as e:
            print(f"[RAG] Erreur lecture carte {path.name} : {e}")
    return cards


def filter_concept_cards_by_triggers(
    cards: List[Dict],
    dashboard_signals: List[str],
    max_cards: int = 4
) -> List[Dict]:
    """
    Sélectionne les cartes les plus pertinentes selon les signaux du dashboard.
    dashboard_signals: liste de mots-clés issus de l'analyse (émotion, signaux, thèmes)
    """
    if not cards or not dashboard_signals:
        return cards[:max_cards]

    signals_lower = [s.lower() for s in dashboard_signals]

    def score_card(card: Dict) -> int:
        score = 0
        triggers = card.get("dashboard_triggers", [])
        use_when = card.get("use_when", [])
        for trigger in triggers + use_when:
            t_lower = trigger.lower()
            for sig in signals_lower:
                if sig in t_lower or t_lower in sig:
                    score += 1
        return score

    scored = sorted(cards, key=score_card, reverse=True)
    return scored[:max_cards]


def format_concept_cards_context(cards: List[Dict], max_chars: int = 2000) -> str:
    """Formate les cartes de concept pour injection dans un prompt LLM."""
    if not cards:
        return ""
    parts = []
    total = 0
    for card in cards:
        cid   = card.get("id", "?")
        title = card.get("title", card.get("concept", ""))
        rule  = card.get("interpretation_rule", "")
        guide = card.get("output_guidance", "")
        entry = f"[{cid}] {title}\n{rule}"
        if guide:
            entry += f"\n→ {guide}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n---\n\n".join(parts)
