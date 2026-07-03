#!/usr/bin/env python3
"""
Build script — Psychologue RAGs (psychologie + socioculturel)
=============================================================
Transforme le corpus de 43 livres académiques en extraits ciblés
et reconstruit les index PKL pour les deux RAG spécialisés.

Utilisation :
    python scripts/build_psychologue_rags.py
    python scripts/build_psychologue_rags.py --force   # reforce même si déjà à jour

Ce script s'exécute UNE SEULE FOIS en offline. Il ne tourne pas à l'analyse.
"""

import os
import re
import sys
import json
import pickle
import hashlib
import argparse
from pathlib import Path

# ── Chemins ───────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent.parent
BOOKS_DIR  = Path("/Users/easycash/Downloads/rag_livres_psycho_socio_marketing_43/markdown_books")
AGENTS_DIR = BASE_DIR / "agents"
INDEX_DIR  = BASE_DIR / "knowledge" / "_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

PSYCHO_RAW  = AGENTS_DIR / "psychologue" / "rag" / "psychologie" / "raw_sources"
SOCIO_RAW   = AGENTS_DIR / "psychologue" / "rag" / "socioculturel" / "raw_sources"
PSYCHO_CARDS = AGENTS_DIR / "psychologue" / "rag" / "psychologie" / "concept_cards"
SOCIO_CARDS  = AGENTS_DIR / "psychologue" / "rag" / "socioculturel" / "concept_cards"

# ── Sources par domaine ───────────────────────────────────────────────────────

PSYCHO_BOOKS = [
    "001_psychology_2e.md",
    "002_introduction_to_psychology_the_full_noba_collection.md",
    "003_introduction_to_psychology_1st_canadian_edition.md",
    "006_the_principles_of_psychology_vol_1.md",
    "007_the_principles_of_psychology_vol_2.md",
    "016_the_balance_of_personality.md",
    "017_theories_of_personality_open_course_text.md",
    "018_how_we_think.md",
    "019_talks_to_teachers_on_psychology.md",
    "033_behavioral_economics_in_context.md",
    "035_the_behavioral_economics_guide.md",
    "030_organizational_behavior.md",
]

SOCIO_BOOKS = [
    "008_human_nature_and_conduct.md",
    "010_the_crowd_a_study_of_the_popular_mind.md",
    "011_psychologie_des_foules.md",
    "012_group_psychology_and_the_analysis_of_the_ego.md",
    "013_extraordinary_popular_delusions_and_the_madness_of_crowds.md",
    "020_introduction_to_sociology_3e.md",
    "022_le_suicide_etude_de_sociologie.md",
    "023_education_et_sociologie.md",
    "024_the_elementary_forms_of_religious_life.md",
    "025_introduction_to_the_science_of_sociology.md",
    "029_introduction_to_consumer_behaviour.md",
    "036_public_opinion.md",
]

# ── Patterns de sélection de passages pertinents ─────────────────────────────

PSYCHO_PATTERNS = [
    r"bias|biais|cognitive bias",
    r"emotion|émotion|feeling|affect",
    r"schema|schéma|mental model|modèle mental",
    r"motivation|drive|desire|désir",
    r"fear|peur|anxiety|anxiété",
    r"frustrat",
    r"belief|croyance|conviction",
    r"decision|décision|choice|choix",
    r"identity|identité|self.concept|self.esteem",
    r"attention|memory|mémoire|recall",
    r"defense mechanism|mécanisme de défense",
    r"persuasion|influence|manipulation",
    r"reinforcement|reward|renforcement|récompense",
    r"dissonance|contradiction|conflict",
]

SOCIO_PATTERNS = [
    r"crowd|foule|mob|masse",
    r"group|groupe|community|communauté",
    r"norm|norme|rule|règle",
    r"identity|identité|belonging|appartenance",
    r"conform|conformi",
    r"polariz|polaris",
    r"culture|cultural|culturel",
    r"social pressure|pression sociale",
    r"institution|authority|autorité",
    r"trust|confiance|méfiance",
    r"contagion|spread|propagation",
    r"belief|croyance|myth|mythe",
    r"social proof|preuve sociale",
    r"socialization|socialisation",
]

CHUNK_SIZE    = 350  # mots
CHUNK_OVERLAP = 60
MIN_CHUNK_LEN = 80  # caractères


def extract_relevant_passages(text: str, patterns: list, max_passages: int = 200) -> list:
    """Extrait les passages du texte qui contiennent des termes pertinents."""
    paragraphs = re.split(r'\n{2,}', text)
    relevant = []
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    for para in paragraphs:
        para = para.strip()
        if len(para) < MIN_CHUNK_LEN:
            continue
        if any(rx.search(para) for rx in compiled):
            relevant.append(para)
        if len(relevant) >= max_passages:
            break
    return relevant


def chunk_text(text: str, source: str) -> list:
    """Découpe en chunks avec overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        window = words[i:i + CHUNK_SIZE]
        chunk_text_str = " ".join(window).strip()
        if len(chunk_text_str) >= MIN_CHUNK_LEN:
            chunks.append({"text": chunk_text_str, "source": source, "start": i})
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def process_books(book_list: list, patterns: list, raw_dir: Path, domain: str) -> list:
    """Lit les livres, extrait les passages pertinents, les stocke dans raw_dir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    all_chunks = []

    for book_name in book_list:
        book_path = BOOKS_DIR / book_name
        if not book_path.exists():
            print(f"  [SKIP] {book_name} non trouvé")
            continue

        text = book_path.read_text(encoding="utf-8", errors="ignore")
        if len(text.strip()) < 500:
            print(f"  [SKIP] {book_name} trop court ({len(text)} chars)")
            continue

        passages = extract_relevant_passages(text, patterns)
        if not passages:
            print(f"  [0 passages] {book_name}")
            continue

        # Sauvegarde des extraits bruts
        slug = book_name.replace(".md", "")
        out_file = raw_dir / f"extracted_{slug}.md"
        out_text = f"# Extraits pertinents — {book_name}\n\n" + "\n\n---\n\n".join(passages)
        out_file.write_text(out_text, encoding="utf-8")
        print(f"  [OK] {book_name} → {len(passages)} passages → {out_file.name}")

        # Chunking pour l'index
        chunks = chunk_text("\n\n".join(passages), slug)
        all_chunks.extend(chunks)

    print(f"\n  Total chunks {domain} : {len(all_chunks)}")
    return all_chunks


def load_concept_cards(cards_dir: Path) -> list:
    """Charge les cartes de concept et les convertit en chunks indexables."""
    chunks = []
    if not cards_dir.exists():
        return chunks
    for path in sorted(cards_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "id" not in data:
                continue
            parts = [f"CONCEPT [{data['id']}] : {data.get('title', '')}"]
            if data.get("definition"):
                parts.append(f"Définition : {data['definition']}")
            for key in ("use_when", "dashboard_triggers", "what_to_observe", "warnings"):
                val = data.get(key)
                if isinstance(val, list) and val:
                    parts.append(f"{key} : " + " | ".join(str(v) for v in val))
            if data.get("interpretation_rule"):
                parts.append(f"Règle : {data['interpretation_rule']}")
            if data.get("example_interpretation"):
                parts.append(f"Exemple : {data['example_interpretation']}")
            text = "\n".join(parts)
            chunks.append({"text": text, "source": path.stem, "start": 0})
        except Exception as e:
            print(f"  [ERR] Carte {path.name} : {e}")
    print(f"  Cartes de concept chargées : {len(chunks)}")
    return chunks


def build_embeddings(chunks: list) -> object:
    """Calcule les embeddings pour la liste de chunks."""
    if not chunks:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        texts = [c["text"] for c in chunks]
        print(f"  Calcul des embeddings ({len(texts)} chunks)...")
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)
        print(f"  Embeddings calculés : {embeddings.shape}")
        return embeddings
    except ImportError:
        print("  [WARN] sentence-transformers non installé — index sans embeddings")
        return None
    except Exception as e:
        print(f"  [ERR] Embeddings : {e}")
        return None


def save_index(agent_name: str, chunks: list, embeddings, dir_hash: str):
    """Sauvegarde l'index PKL."""
    idx_path = INDEX_DIR / f"{agent_name}.pkl"
    idx = {"chunks": chunks, "embeddings": embeddings, "hash": dir_hash}
    with open(idx_path, "wb") as f:
        pickle.dump(idx, f)
    print(f"  Index sauvegardé : {idx_path} ({len(chunks)} chunks)")


def hash_agent_dir(agent_dir: Path) -> str:
    """Hash du dossier agent complet — DOIT correspondre exactement à core/rag.py._hash_dir()."""
    h = hashlib.md5()
    if not agent_dir.exists():
        return ""
    for f in sorted(agent_dir.glob("**/*")):
        if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".epub", ".json"):
            h.update(f.name.encode())
            h.update(str(f.stat().st_mtime).encode())
    return h.hexdigest()


def build_rag(domain: str, book_list: list, patterns: list,
              raw_dir: Path, cards_dir: Path, agent_name: str, force: bool = False):
    """Pipeline complet pour un RAG spécialisé."""
    print(f"\n{'='*60}")
    print(f"  RAG {domain.upper()} — {agent_name}")
    print(f"{'='*60}")

    # Le dossier agent = parent de raw_dir et cards_dir (ex: agents/psychologue/rag/psychologie)
    agent_dir = raw_dir.parent
    idx_path  = INDEX_DIR / f"{agent_name}.pkl"

    # Hash AVANT extraction pour détecter si on doit refaire
    pre_hash = hash_agent_dir(agent_dir)
    if not force and idx_path.exists():
        try:
            with open(idx_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("hash") == pre_hash:
                print(f"  Index à jour — rien à faire (--force pour forcer)")
                return
        except Exception:
            pass

    print(f"\n  1. Extraction depuis {len(book_list)} livres...")
    book_chunks = process_books(book_list, patterns, raw_dir, domain)

    print(f"\n  2. Chargement des cartes de concept...")
    card_chunks = load_concept_cards(cards_dir)

    all_chunks = card_chunks + book_chunks
    print(f"\n  3. Total : {len(all_chunks)} chunks ({len(card_chunks)} cartes + {len(book_chunks)} livres)")

    print(f"\n  4. Calcul des embeddings...")
    embeddings = build_embeddings(all_chunks)

    # Hash APRÈS extraction — c'est ce hash que rag.py calculera au prochain lancement
    post_hash = hash_agent_dir(agent_dir)

    print(f"\n  5. Sauvegarde de l'index (hash post-extraction)...")
    save_index(agent_name, all_chunks, embeddings, post_hash)

    print(f"\n  ✓ RAG {domain} construit avec succès.")


def main():
    parser = argparse.ArgumentParser(description="Build psychologue RAGs from book corpus")
    parser.add_argument("--force", action="store_true", help="Forcer la reconstruction même si déjà à jour")
    parser.add_argument("--only", choices=["psychologie", "socioculturel"], help="Construire seulement un RAG")
    args = parser.parse_args()

    if not BOOKS_DIR.exists():
        print(f"[ERREUR] Dossier livres introuvable : {BOOKS_DIR}")
        sys.exit(1)

    print(f"Corpus livres : {BOOKS_DIR}")
    print(f"Index dir    : {INDEX_DIR}")

    if args.only != "socioculturel":
        build_rag(
            domain="psychologie",
            book_list=PSYCHO_BOOKS,
            patterns=PSYCHO_PATTERNS,
            raw_dir=PSYCHO_RAW,
            cards_dir=PSYCHO_CARDS,
            agent_name="psychologue_psycho",
            force=args.force,
        )

    if args.only != "psychologie":
        build_rag(
            domain="socioculturel",
            book_list=SOCIO_BOOKS,
            patterns=SOCIO_PATTERNS,
            raw_dir=SOCIO_RAW,
            cards_dir=SOCIO_CARDS,
            agent_name="psychologue_socio",
            force=args.force,
        )

    print(f"\n{'='*60}")
    print(f"  BUILD TERMINÉ")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
