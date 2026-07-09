"""
NLP Engine — couche prétraitement linguistique et statistique.

Pipeline :
  1. Vectorisation sémantique (sentence-transformers multilingue)
  2. Context Relevance Score — cosine similarity titre/commentaire
  3. Signaux lexicaux — TF-IDF, fréquences, cooccurrences, champ lexical
  4. Clustering comportemental — KMeans sur embeddings
  5. Diversité sémantique — dispersion de l'espace d'opinion
  6. Score de confiance — robustesse de chaque conclusion

Les sorties alimentent le pipeline d'interprétation IA :
  → Gabriel interprète À PARTIR des signaux, pas librement.
"""

import re
import math
import os
import time
from collections import Counter

# Limite les threads BLAS/OpenMP de PyTorch — évite un deadlock connu sur
# Windows quand sentence-transformers est appelé depuis un ThreadPoolExecutor.
# Doit être fait avant tout import de torch (transitif via sentence-transformers).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# scikit-learn (vcomp/MSVC OpenMP) et torch (Intel MKL/libiomp5md) chargent
# chacun leur propre runtime OpenMP dans le même process — sur Windows ça
# peut bloquer silencieusement au lieu de lever une erreur. On autorise
# explicitement la coexistence des deux runtimes.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ─── STOPWORDS FRANÇAIS ───────────────────────────────────────────────────────

STOPWORDS_FR = {
    "le","la","les","un","une","de","du","des","en","et","est","il","elle",
    "je","tu","nous","vous","ils","elles","on","que","qui","quand","ou",
    "mais","car","si","pas","ne","plus","tres","meme","alors","donc","bien",
    "tout","peut","etre","avoir","faire","cette","avec","pour","sur","par",
    "au","aux","ce","se","sa","son","ses","leur","leurs","dans","mon","ma",
    "mes","votre","notre","dont","ca","me","te","lui","eux","cet","ces",
    "sont","etait","sera","comme","quoi","ah","oh","wow","lol","haha",
    "oui","non","cela","ceci","ici","voila","voici","nan","bah","bon","ben",
    "donc","quand","sans","sous","trop","peu","aussi","encore","deja","rien",
    "quel","quelle","quels","quelles","dont","lors","meme","toute","tous",
    "toutes","entre","vers","apres","avant","pendant","depuis","jusqu",
    "sauf","sauf","selon","sinon","ainsi","puis","faut","doit","peut",
    "va","vais","allons","allez","vont","fait","fais","font","dire",
    "dit","dis","disent","voir","voit","voient","savoir","sait","savent",
    # Intensifieurs / fillers fréquents (bruit lexical)
    "vraiment","franchement","beaucoup","vachement","carrement","completement",
    "totalement","absolument","tellement","plutot","assez","quand-meme",
    "genre","truc","chose","gens","perso","grave","ouais","mdr","ptdr",
    "chez","autre","autres","ailleurs","partout","toujours","jamais",
    "moins","mieux","pire","mal","super","hyper","trop",
}


def _clean(text):
    """Nettoyage : URLs, mentions, ponctuation lourde."""
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#(\w+)', r'\1', text)
    text = re.sub(r'[^\w\s\'\-àâäéèêëîïôùûüœç]', ' ', text.lower())
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _tokenize(text):
    """Tokenisation — extrait les tokens significatifs (≥ 3 chars, hors stopwords)."""
    text = _clean(text)
    # Normalisation basique des accents pour le matching stopwords
    normalized = text
    for a, b in [('é','e'),('è','e'),('ê','e'),('ë','e'),('à','a'),('â','a'),
                  ('î','i'),('ï','i'),('ô','o'),('ù','u'),('û','u'),('ü','u'),('ç','c')]:
        normalized = normalized.replace(a, b)
    raw_tokens = re.findall(r"[a-zàâäéèêëîïôùûüœç]{3,}", text)
    norm_tokens = re.findall(r"[a-z]{3,}", normalized)
    result = []
    for orig, norm in zip(raw_tokens, norm_tokens):
        if norm not in STOPWORDS_FR and len(orig) >= 3:
            result.append(orig)
    return result


# ─── VECTORISATION ────────────────────────────────────────────────────────────

_model_cache = None
_model_status = "unloaded"   # unloaded | loaded | unavailable


def preload_model():
    """
    Charge le modèle sémantique dans le thread principal, au démarrage du
    serveur. Sur Windows, charger ce modèle pour la première fois depuis un
    thread de requête Flask (ThreadingMixIn) peut bloquer indéfiniment —
    le précharger ici l'évite : tous les appels suivants réutilisent le
    modèle déjà en cache, quel que soit le thread appelant.
    """
    _get_model()


def _get_model():
    global _model_cache, _model_status
    if _model_status == "loaded":
        return _model_cache
    if _model_status == "unavailable":
        return None
    try:
        import torch
        torch.set_num_threads(1)
        from sentence_transformers import SentenceTransformer
        print("[NLP] Chargement modèle sémantique multilingue (premier lancement)…")
        _model_cache = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        _model_status = "loaded"
        print("[NLP] Modèle prêt.")
        return _model_cache
    except Exception as e:
        print(f"[NLP] sentence-transformers indisponible : {e} — fallback TF-IDF")
        _model_status = "unavailable"
        return None


def _vectorize(texts):
    """Encode les textes → vecteurs normalisés. Retourne None si modèle absent."""
    model = _get_model()
    if model is None:
        return None
    try:
        import numpy as np
        return model.encode(texts, show_progress_bar=False, batch_size=32,
                            normalize_embeddings=True)
    except Exception as e:
        print(f"[NLP] Erreur vectorisation : {e}")
        return None


def _tfidf_cosine(query, docs):
    """
    Fallback : similarité cosinus via TF-IDF sklearn.
    Utilisé si sentence-transformers est absent.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        vect = TfidfVectorizer(min_df=1).fit([query] + docs)
        mat = vect.transform([query] + docs).toarray()
        q_vec = mat[0:1]
        d_vecs = mat[1:]
        sims = cosine_similarity(q_vec, d_vecs)[0]
        return sims.tolist()
    except Exception:
        return [0.5] * len(docs)


# ─── CONTEXT RELEVANCE SCORES ─────────────────────────────────────────────────

def compute_relevance_scores(title, texts):
    """
    Cosine similarity entre le titre/sujet et chaque commentaire.
    Retourne (scores: list[float], comment_vecs: ndarray|None).

    Si sentence-transformers absent → fallback TF-IDF.
    Si aucune lib → retourne des scores à 0.5 (neutral).

    Context Relevance Score interprétation :
      > 0.65  : commentaire directement lié au sujet
      0.35–0.65 : lien partiel
      < 0.35  : commentaire peu lié (bruit, hors-sujet)
    """
    if not title or not texts:
        return [0.5] * len(texts), None

    vecs = _vectorize([title] + texts)

    if vecs is not None:
        import numpy as np
        title_vec = vecs[0]
        comment_vecs = vecs[1:]
        # Cosine similarity = dot product (vecteurs normalisés)
        scores = [round(float(max(0.0, np.dot(title_vec, cv))), 3) for cv in comment_vecs]
        return scores, comment_vecs

    # Fallback TF-IDF
    scores = _tfidf_cosine(title, texts)
    scores = [round(max(0.0, min(1.0, s)), 3) for s in scores]
    return scores, None


# ─── SIGNAUX LEXICAUX ─────────────────────────────────────────────────────────

def extract_lexical_signals(texts, top_n=20):
    """
    Analyse lexicale complète :
    - Fréquence absolue (présence dans le corpus)
    - TF-IDF simplifié (pertinence distinctive)
    - Bigrams (cooccurrences de tokens)
    - Densité de commentaires

    Retourne un dict de signaux mesurables.
    """
    n = max(len(texts), 1)
    all_tokens = []
    all_bigrams = []
    doc_token_sets = []

    for text in texts:
        tokens = _tokenize(text)
        all_tokens.extend(tokens)
        doc_token_sets.append(set(tokens))
        for i in range(len(tokens) - 1):
            all_bigrams.append(f"{tokens[i]} {tokens[i+1]}")

    token_freq = Counter(all_tokens)
    bigram_freq = Counter(all_bigrams)

    # Document frequency (combien de docs contiennent ce token)
    doc_freq = Counter()
    for s in doc_token_sets:
        for t in s:
            doc_freq[t] += 1

    # TF-IDF simplifié : TF × log(N/DF)
    tfidf = {}
    for token, tf in token_freq.items():
        df = doc_freq.get(token, 1)
        idf = math.log(n / df) if df < n else 0.01
        tfidf[token] = round(tf * idf, 3)

    top_tokens = [
        {"token": t, "freq": f, "tfidf": tfidf.get(t, 0), "doc_freq": doc_freq.get(t, 0)}
        for t, f in token_freq.most_common(top_n)
    ]
    top_tfidf = sorted(tfidf.items(), key=lambda x: -x[1])[:top_n]
    top_bigrams = [{"bigram": b, "freq": f} for b, f in bigram_freq.most_common(12)]

    # Densité lexicale
    total_tokens = len(all_tokens)
    avg_tokens = round(total_tokens / n, 1)

    # Richesse vocabulaire (TTR — Type-Token Ratio sur un échantillon)
    vocab_size = len(token_freq)
    ttr = round(vocab_size / max(total_tokens, 1), 3)

    return {
        "top_tokens":    top_tokens,
        "top_tfidf":     [{"token": t, "score": s} for t, s in top_tfidf],
        "top_bigrams":   top_bigrams,
        "vocabulary_size":    vocab_size,
        "total_tokens":       total_tokens,
        "avg_tokens_per_comment": avg_tokens,
        "lexical_richness_ttr":   ttr,
    }


# ─── CLUSTERING COMPORTEMENTAL ────────────────────────────────────────────────

def cluster_comments(texts, comment_vecs=None, n_clusters=None):
    """
    KMeans sur embeddings sémantiques → groupes de commentaires similaires.
    Si vecs non fournis, vectorise ici.

    Retourne (labels, vecs, cluster_summary).
    labels         : list[int], un label par commentaire
    vecs           : ndarray ou None
    cluster_summary: list[dict] — description de chaque cluster
    """
    n = len(texts)
    if n < 5:
        return [0] * n, comment_vecs, [{"cluster_id": 0, "size": n, "pct": 100.0,
                                         "top_tokens": [], "samples": []}]

    vecs = comment_vecs
    if vecs is None:
        vecs = _vectorize(texts)

    if vecs is None:
        return [0] * n, None, []

    if n_clusters is None:
        n_clusters = min(max(2, n // 12), 5)

    try:
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto", max_iter=300)
        labels = kmeans.fit_predict(vecs).tolist()
    except ImportError:
        return [0] * n, vecs, []
    except Exception as e:
        print(f"[NLP] Clustering erreur : {e}")
        return [0] * n, vecs, []

    # Construction du résumé par cluster
    cluster_data = {}
    for i, (text, label) in enumerate(zip(texts, labels)):
        cl = int(label)
        cluster_data.setdefault(cl, {"texts": [], "indices": []})
        cluster_data[cl]["texts"].append(text)
        cluster_data[cl]["indices"].append(i)

    cluster_summary = []
    for cl_id, data in sorted(cluster_data.items()):
        tokens = []
        for t in data["texts"]:
            tokens.extend(_tokenize(t))
        top_toks = [t for t, _ in Counter(tokens).most_common(6)]
        pct = round(len(data["texts"]) / n * 100, 1)
        cluster_summary.append({
            "cluster_id":  cl_id,
            "size":        len(data["texts"]),
            "pct":         pct,
            "top_tokens":  top_toks,
            "samples":     [t[:90] for t in data["texts"][:3]],
        })

    return labels, vecs, cluster_summary


# ─── DIVERSITÉ SÉMANTIQUE ────────────────────────────────────────────────────

def compute_semantic_diversity(vecs):
    """
    Diversité sémantique = 1 - similarité pairwise moyenne.
    > 0.7  : opinions très dispersées
    0.4–0.7: diversité modérée
    < 0.4  : audience homogène sémantiquement
    """
    if vecs is None or len(vecs) < 2:
        return 0.5
    try:
        import numpy as np
        sims = vecs @ vecs.T
        n = len(vecs)
        off_diag_sum = float(sims.sum()) - n  # soustrait la diagonale (tous =1)
        mean_sim = off_diag_sum / max(n * (n - 1), 1)
        return round(max(0.0, 1.0 - mean_sim), 3)
    except Exception:
        return 0.5


# ─── SCORE DE CONFIANCE ───────────────────────────────────────────────────────

def compute_confidence(n_supporting, n_total, signal_strength=0.5, cluster_consistent=False):
    """
    Robustesse d'une conclusion ∈ [0.0, 1.0].

    n_supporting      : nb commentaires soutenant le signal
    n_total           : total commentaires analysés
    signal_strength   : intensité du signal (0–1, ex: tfidf score normalisé)
    cluster_consistent: le signal domine-t-il au moins un cluster ?

    Formule :
      C = (coverage × 0.60) + (signal_strength × 0.30) + (cluster_bonus × 0.10)

    Interprétation :
      ≥ 0.80 : conclusion forte — soutenue par données robustes
      0.55–0.79 : conclusion solide
      0.35–0.54 : hypothèse probable
      < 0.35 : signal faible — formuler comme hypothèse
    """
    coverage = n_supporting / max(n_total, 1)
    strength = min(1.0, signal_strength)
    bonus = 0.10 if cluster_consistent else 0.0
    score = coverage * 0.60 + strength * 0.30 + bonus
    return round(min(score, 1.0), 2)


# ─── LIVRABLES STATISTIQUES PURS ─────────────────────────────────────────────

def compute_pure_statistical_deliverables(layer1, nlp_data, comments):
    """
    Génère les livrables entièrement fondés sur des données mesurables.
    Aucun appel IA — tout est calculé depuis layer1 + nlp_data.

    Livrables produits :
      positionnement_audience
      carte_emotionnelle
      repartition_camps
      signaux_lexicaux_dominants
      clusters_comportementaux
      distribution_relevance
    """
    n = len(layer1)
    if n == 0:
        return {}

    # ── Positionnement de l'audience ─────────────────────────────────────────
    positions = [s.get("position", "neutre") for s in layer1]
    pos_counter = Counter(positions)
    pos_total = max(sum(pos_counter.values()), 1)
    pos_dist = {k: round(v / pos_total * 100, 1) for k, v in pos_counter.items()}

    dominant_pos = pos_counter.most_common(1)[0][0] if pos_counter else "neutre"
    dominant_pct = round(pos_counter.most_common(1)[0][1] / pos_total * 100, 1) if pos_counter else 0

    conf_pos = compute_confidence(
        n_supporting=pos_counter.most_common(1)[0][1] if pos_counter else 0,
        n_total=n,
        signal_strength=dominant_pct / 100,
        cluster_consistent=True
    )

    positionnement = {
        "conclusion": f"Audience majoritairement {dominant_pos} ({dominant_pct}%)",
        "distribution": pos_dist,
        "dominant": dominant_pos,
        "dominant_pct": dominant_pct,
        "indicateur_statistique": f"{dominant_pct}% des commentaires classés '{dominant_pos}' sur {n} analysés",
        "score_confiance": conf_pos,
    }

    # ── Carte émotionnelle ───────────────────────────────────────────────────
    emotions_l1 = [s.get("emotion", "") for s in layer1 if s.get("emotion")]
    emo_counter = Counter(emotions_l1)
    emo_total = max(sum(emo_counter.values()), 1)
    emo_dist = [
        {"emotion": e, "count": c, "pct": round(c / emo_total * 100, 1)}
        for e, c in emo_counter.most_common(6)
    ]

    # Intensité émotionnelle : proportion d'émotions fortes
    STRONG_EMO = {"frustration", "colere", "espoir", "enthousiasme", "admiration", "tristesse"}
    n_strong = sum(1 for e in emotions_l1 if e in STRONG_EMO)
    intensite_pct = round(n_strong / max(len(emotions_l1), 1) * 100, 1)

    if not emo_counter:
        carte_emotionnelle = {
            "conclusion": "Aucune émotion distincte détectée",
            "distribution": [],
            "intensite_forte_pct": 0,
            "indicateur_statistique": "Insuffisamment d'émotions étiquetées pour établir une carte émotionnelle",
            "score_confiance": 0.20,
        }
    else:
        dominant_emo = emo_counter.most_common(1)[0]
        conf_emo = compute_confidence(
            n_supporting=dominant_emo[1],
            n_total=n,
            signal_strength=dominant_emo[1] / emo_total,
            cluster_consistent=intensite_pct > 40
        )
        carte_emotionnelle = {
            "conclusion": f"Émotion dominante : {dominant_emo[0]} ({round(dominant_emo[1]/emo_total*100,1)}%)",
            "distribution": emo_dist,
            "intensite_forte_pct": intensite_pct,
            "indicateur_statistique": (
                f"{dominant_emo[0]} détectée dans {round(dominant_emo[1]/emo_total*100,1)}% des commentaires. "
                f"{intensite_pct}% des commentaires portent une émotion forte."
            ),
            "score_confiance": conf_emo,
        }

    # ── Répartition des camps ────────────────────────────────────────────────
    n_fav  = pos_counter.get("favorable", 0)
    n_def  = pos_counter.get("defavorable", 0)
    n_neu  = pos_counter.get("neutre", 0)
    n_nua  = pos_counter.get("nuance", 0)
    ratio_division = round(abs(n_fav - n_def) / max(n_fav + n_def, 1), 2)

    if max(n_fav, n_def) == 0:
        _conclusion_camps = "Audience principalement neutre ou ambivalente"
    elif abs(n_fav - n_def) < max(n_fav, n_def) * 0.4:
        _conclusion_camps = "Audience divisée"
    else:
        _conclusion_camps = f"Audience {'favorable' if n_fav > n_def else 'défavorable'} en majorité"

    repartition_camps = {
        "conclusion": _conclusion_camps,
        "camps": {
            "favorable":   {"count": n_fav,  "pct": round(n_fav / pos_total * 100, 1)},
            "oppose":      {"count": n_def,  "pct": round(n_def / pos_total * 100, 1)},
            "neutre":      {"count": n_neu,  "pct": round(n_neu / pos_total * 100, 1)},
            "nuance":      {"count": n_nua,  "pct": round(n_nua / pos_total * 100, 1)},
        },
        "ratio_division": ratio_division,
        "indicateur_statistique": (
            f"Favorables : {round(n_fav/pos_total*100,1)}% | "
            f"Opposés : {round(n_def/pos_total*100,1)}% | "
            f"Neutres : {round(n_neu/pos_total*100,1)}%"
        ),
        "score_confiance": compute_confidence(max(n_fav, n_def), n, ratio_division),
    }

    # ── Signaux lexicaux dominants ───────────────────────────────────────────
    texts = [c.get("text", "") for c in comments]
    lexical = nlp_data.get("lexical") or extract_lexical_signals(texts)
    top_tokens = lexical.get("top_tfidf") or [{"token": t["token"], "score": t["tfidf"]}
                                               for t in lexical.get("top_tokens", [])[:15]]

    # Normalise les scores TF-IDF pour l'affichage
    if top_tokens:
        max_score = max((t["score"] for t in top_tokens), default=1)
        for t in top_tokens:
            t["score_norm"] = round(t["score"] / max(max_score, 0.001), 3)

    signaux_lexicaux = {
        "conclusion": f"Champ lexical dominant autour de : {', '.join(t['token'] for t in top_tokens[:5])}",
        "top_tokens": top_tokens[:15],
        "top_bigrams": lexical.get("top_bigrams", [])[:8],
        "vocabulary_size": lexical.get("vocabulary_size", 0),
        "avg_tokens_per_comment": lexical.get("avg_tokens_per_comment", 0),
        "lexical_richness": lexical.get("lexical_richness_ttr", 0),
        "indicateur_statistique": (
            f"Vocabulaire : {lexical.get('vocabulary_size',0)} tokens uniques sur "
            f"{lexical.get('total_tokens',0)} total. "
            f"Densité moyenne : {lexical.get('avg_tokens_per_comment',0)} tokens/commentaire."
        ),
        "score_confiance": 0.95,  # purement mesurable
    }

    # ── Clusters comportementaux ─────────────────────────────────────────────
    cluster_summary = nlp_data.get("cluster_summary", [])

    clusters_comportementaux = {
        "conclusion": f"{len(cluster_summary)} groupes comportementaux détectés",
        "clusters": cluster_summary,
        "indicateur_statistique": " | ".join(
            f"Cluster {c['cluster_id']} : {c['pct']}% ({c['size']} commentaires) — "
            f"tokens : {', '.join(c['top_tokens'][:3])}"
            for c in cluster_summary
        ),
        "score_confiance": 0.80 if len(cluster_summary) >= 2 else 0.50,
    }

    # ── Distribution Context Relevance Score ─────────────────────────────────
    relevance_dist = nlp_data.get("relevance_distribution")
    if relevance_dist:
        distribution_relevance = {
            "conclusion": (
                f"{relevance_dist.get('haute',0)} commentaires fortement liés au sujet "
                f"({round(relevance_dist.get('haute',0)/n*100,1)}%)"
            ),
            "distribution": relevance_dist,
            "indicateur_statistique": (
                f"Lien fort (>0.65) : {relevance_dist.get('haute',0)} | "
                f"Partiel (0.35–0.65) : {relevance_dist.get('moyenne',0)} | "
                f"Faible (<0.35) : {relevance_dist.get('faible',0)} | "
                f"Mean CRS : {relevance_dist.get('mean',0)}"
            ),
            "score_confiance": 0.95,
        }
    else:
        distribution_relevance = None

    return {
        "positionnement_audience":     positionnement,
        "carte_emotionnelle":          carte_emotionnelle,
        "repartition_camps":           repartition_camps,
        "signaux_lexicaux_dominants":  signaux_lexicaux,
        "clusters_comportementaux":    clusters_comportementaux,
        "distribution_relevance":      distribution_relevance,
    }


# ─── PIPELINE PRINCIPAL ───────────────────────────────────────────────────────

def run_nlp_pipeline(comments, title=""):
    """
    Point d'entrée du moteur NLP.
    comments : list[{"text": str, "likes": int, ...}]
    title    : str — titre ou sujet analysé

    Retourne : dict de signaux mesurables alimentant le pipeline IA.
    """
    texts = [c.get("text", "") for c in comments]
    n = len(texts)

    print(f"[NLP] Pipeline NLP — {n} commentaires | sujet : '{(title or '')[:60]}'")
    _t = time.perf_counter()

    # 1. Vectorisation + Context Relevance Scores
    relevance_scores, comment_vecs = compute_relevance_scores(title, texts)
    _t_vec = time.perf_counter()
    print(f"[PSYCHO_TIMING] nlp_vectorization={_t_vec-_t:.2f}s")

    if relevance_scores:
        rs = relevance_scores
        mean_rel = round(sum(rs) / n, 3)
        print(f"[NLP] CRS mean={mean_rel} | mode: {'sémantique' if comment_vecs is not None else 'TF-IDF'}")
        relevance_dist = {
            "haute":   sum(1 for s in rs if s > 0.65),
            "moyenne": sum(1 for s in rs if 0.35 <= s <= 0.65),
            "faible":  sum(1 for s in rs if s < 0.35),
            "mean":    mean_rel,
            "max":     round(max(rs), 3),
            "min":     round(min(rs), 3),
        }
    else:
        relevance_dist = None

    # 2. Signaux lexicaux
    lexical = extract_lexical_signals(texts)
    print(f"[NLP] Lexical — vocab={lexical['vocabulary_size']} | density={lexical['avg_tokens_per_comment']} tok/cmnt")
    _t_lex = time.perf_counter()
    print(f"[PSYCHO_TIMING] nlp_lexical={_t_lex-_t_vec:.2f}s")

    # 3. Clustering sémantique
    cluster_labels, vecs_used, cluster_summary = cluster_comments(texts, comment_vecs)
    n_clusters = max(cluster_labels) + 1 if cluster_labels else 0
    print(f"[NLP] Clustering — {n_clusters} clusters")
    _t_clust = time.perf_counter()
    print(f"[PSYCHO_TIMING] clustering={_t_clust-_t_lex:.2f}s")

    # 4. Diversité sémantique
    diversity = compute_semantic_diversity(vecs_used)
    print(f"[NLP] Diversité sémantique : {diversity}")

    return {
        "relevance_scores":       relevance_scores,       # list[float] — par commentaire
        "cluster_labels":         cluster_labels,          # list[int]   — par commentaire
        "cluster_summary":        cluster_summary,         # list[dict]  — résumé clusters
        "lexical":                lexical,                 # dict        — signaux lexicaux
        "semantic_diversity":     diversity,               # float ∈ [0,1]
        "relevance_distribution": relevance_dist,          # dict | None
        "n_comments":             n,
    }


# ─── PREPROCESSING PAR COMMENTAIRE ────────────────────────────────────────────

def preprocess_comment(text):
    """
    Prétraitement d'un commentaire individuel.
    Retourne : {text, clean_text, tokens, is_spam, is_short, word_count}
    """
    if not text or not text.strip():
        return {
            "text":       text or "",
            "clean_text": "",
            "tokens":     [],
            "is_spam":    True,
            "is_short":   True,
            "word_count": 0,
        }
    clean      = _clean(text)
    tokens     = _tokenize(text)
    word_count = len(text.split())
    alpha_ratio = sum(1 for ch in text if ch.isalpha()) / max(len(text), 1)
    has_url    = bool(re.search(r'https?://', text))
    is_spam    = has_url or (word_count <= 2 and alpha_ratio < 0.3)
    is_short   = word_count <= 4
    return {
        "text":       text,
        "clean_text": clean,
        "tokens":     tokens,
        "is_spam":    is_spam,
        "is_short":   is_short,
        "word_count": word_count,
    }


def compute_engagement_weight(likes, relevance_score, emotion_intensity):
    """
    Poids d'engagement d'un commentaire.
    Formule : (1 + log(1+likes)) × max(relevance_score, 0.1) × (1 + emotion_intensity)
    Plafonné à 5.0.
    """
    weight = (1.0 + math.log1p(likes)) * max(relevance_score, 0.1) * (1.0 + emotion_intensity)
    return round(min(weight, 5.0), 3)
