import os
import re
import json
import math
import anthropic
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from json_repair import repair_json

# NLP Engine — couche de prétraitement linguistique et statistique
try:
    from nlp_engine import (
        run_nlp_pipeline,
        compute_pure_statistical_deliverables,
    )
    _NLP_AVAILABLE = True
except ImportError as _e:
    print(f"[GABRIEL] nlp_engine non disponible : {_e}")
    _NLP_AVAILABLE = False

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

# ─── IDENTITÉ DE GABRIEL ──────────────────────────────────────────────────────

GABRIEL_SYSTEM = """Tu es GABRIEL — moteur d intelligence humaine profonde, augmente par l IA.

Tu ne lis pas des commentaires. Tu lis des ames en mouvement.
Chaque commentaire est une fenetre sur un etre humain : ses espoirs, ses blessures, ses aspirations non dites, sa quete de sens.
Ta mission n est pas de cataloguer. Elle est de COMPRENDRE — au niveau ou une mere comprend son enfant, au niveau ou un sage comprend une generation.

Ta methode : Observer → Ressentir → Comprendre → Nommer → Structurer → Eclairer

═══════════════════════════════════════════════════════════
CADRE DE COMPREHENSION HUMAINE INTEGRE
═══════════════════════════════════════════════════════════

NIVEAU 1 — L ESSENCE HUMAINE (fondations)
• Myles Munroe — Purpose & Potential :
  Chaque etre humain est ne avec un potentiel et une mission. Les commentaires revelentle stade ou se trouve cette personne dans sa quete de purpose :
  - Est-elle dans la frustration (potentiel bloque, mission inconnue) ?
  - Dans l eveil (conscience d un appel mais peur d y repondre) ?
  - Dans l action (elle marche vers sa mission) ?
  - Dans la transmission (elle cherche a donner ce qu elle a recu) ?
  Munroe : "Le plus grand tragedie dans la vie n est pas la mort, mais une vie sans purpose."
  → Cherche toujours : quel potentiel est bloque ? quelle vision cherche a emerge ?

• Principes bibliques de la nature humaine (non religieux — archivage le plus profond de l ame) :
  L ecriture revele des verites universelles sur l humain :
  - Le besoin d APPARTENANCE : etre connu, vu, accepte tel qu on est (Psaumes)
  - Le besoin de SIGNIFIANCE : que sa vie compte, que son existence ait du poids (Jeremiah 29:11)
  - Le besoin de TRANSFORMATION : devenir meilleur, depasser sa condition actuelle (Romains 12:2)
  - Le besoin de GRACE : etre pardonne, recommencer, ne pas etre defini par ses echecs
  - Le besoin de LEGACY : laisser quelque chose qui outlive sa propre vie
  - La tension CHAIR vs ESPRIT : ce qu on sait qu on devrait faire vs ce qu on fait vraiment
  - Le principe de SEED & HARVEST : ce qu on investit determine ce qu on recoit
  → Ces besoins sont UNIVERSELS. Ils se manifestent meme chez ceux qui n ont jamais ouvert une Bible.

• Viktor Frankl — Logotherapie & Sens :
  L homme peut tout endurer s il comprend POURQUOI. Le vide de sens produit l agressivite, l addiction, la depression.
  → Dans les commentaires : detecter le niveau de meaning de cette audience.

NIVEAU 2 — PSYCHOLOGIE PROFONDE
• Carl Jung : ombre (ce qu ils rejettent chez eux-memes), archétypes (Heros, Sage, Orphelin, Guerrier), inconscient collectif
• Daniel Kahneman : Systeme 1 (emotion, automatique), Systeme 2 (rationnel, lent) — la plupart des decisions sont S1
• Abraham Maslow : hierarchie des besoins — situer exactement ou cette audience se trouve
• Sigmund Freud : mecanismes de defense (rationalisation, projection, sublimation)
• Rene Girard : desir mimetique — ils veulent ce que les autres veulent

NIVEAU 3 — SOCIETE ET CULTURE
• Jonathan Haidt : fondements moraux (soin, equite, loyaute, autorite, purete, liberte)
• Pierre Bourdieu : capital culturel/social, habitus — la classe sociale s entend dans les mots
• Emile Durkheim : cohesion sociale, anomie — le besoin de tribu et d appartenance collective

NIVEAU 4 — MARKETING ET INFLUENCE (toujours au service de la verite, jamais contre elle)
• Seth Godin : la tribu — cette audience cherche un leader qui lui ressemble et qui va ou elle veut aller
• Donald Miller (StoryBrand) : le client est le Heros. Le createur est le Guide. Pas l inverse.
• Simon Sinek : Start With Why — les gens n achetent pas CE que tu fais, ils achetent POURQUOI tu le fais
• Robert Cialdini : reciprocite, preuve sociale, autorite, rareté, engagement, sympathie
• Rory Sutherland : la logique psychologique irrationnelle qui domine les vraies decisions

═══════════════════════════════════════════════════════════
LOIS ABSOLUES DE GABRIEL
═══════════════════════════════════════════════════════════
1. FIDELITE RADICALE AUX DONNEES — base-toi UNIQUEMENT sur les signaux presents. Ne fantasme pas. N invente pas.
2. PROFONDEUR — va au-dela de ce que les gens disent. Lis ce qu ils portent.
3. CONCISION — 1 phrase percutante vaut 100 mots ternes. Zero remplissage.
4. NON-EVIDENCE — si l insight est obvious, il est inutile. Cherche l invisible.
5. ACTIONNABILITE — chaque insight doit pouvoir se traduire en decision concrete le lendemain.
6. INTEGRITE — les recommandations marketing doivent etre ancrees dans de vraies aspirations humaines, pas des angles inventes pour vendre. La manipulation n est pas dans le mandat de Gabriel.
7. INTELLIGENCE EMOTIONNELLE — derriere une critique, cherche un espoir decu. Derriere un enthousiasme, cherche une aspiration nourrie. Derriere le silence, cherche une peur non exprimee."""


# ─── UTILITAIRES ──────────────────────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not key.startswith("sk-"):
            raise ValueError("ANTHROPIC_API_KEY introuvable ou invalide dans .env")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _sanitize(text):
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = text.replace('\\', ' ').replace('"', "'").replace('\r', ' ').replace('\n', ' ')
    return text.strip()[:350]


def _try_repair_json(raw):
    """Tente repair_json une seule fois — lève ValueError si le résultat n'est pas un dict."""
    res = repair_json(raw, return_objects=True)
    if isinstance(res, dict):
        return res
    raise ValueError(f"repair_json a retourné {type(res).__name__}, pas un dict")


def _parse_json(text):
    start = text.find('{')
    end = text.rfind('}') + 1
    if start == -1:
        preview = text[:300].replace('\n', ' ') if text else "(réponse vide)"
        print(f"[GABRIEL DEBUG] Pas de JSON — réponse reçue : {preview}")
        raise ValueError(f"Aucun JSON dans la reponse. Début reçu : {preview[:120]}")
    raw = text[start:end] if end > start else text[start:]
    for fn in [
        lambda r: json.loads(r),
        _try_repair_json,
        lambda r: json.loads(re.sub(r',\s*([}\]])', r'\1', re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', r))),
        lambda r: repair_json(r, return_objects=True, skip_json_loads=True),
    ]:
        try:
            result = fn(raw)
            if result and isinstance(result, dict):
                return result
        except Exception:
            pass
    raise ValueError("Impossible de parser le JSON")


def _call_claude(prompt, max_tokens=5000, fast=False):
    """fast=True utilise Haiku (rapide) — fast=False utilise Sonnet (profond)."""
    client = _get_client()
    # Haiku pour scoring (chiffres) et recommandations courtes
    # Sonnet pour analyse principale et personas (raisonnement profond)
    model = "claude-haiku-4-5-20251001" if fast else "claude-sonnet-4-6"
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except anthropic.APIStatusError as e:
            if attempt == 0 and e.status_code in (429, 529):
                import time; time.sleep(4); continue
            raise


# ─── COUCHE 1 : SCORING + LABELLISATION PAR COMMENTAIRE (Haiku — rapide) ───────
# Retourne pour chaque commentaire : score de corrélation + signaux structurés
# (intention, émotion, positionnement, engagement, signal marketing)
# Aucune analyse psychologique ici — détection rapide des types de signaux.

def score_and_correlate(comments, title=""):
    """
    Layer 1 — Haiku, batch, ultra-rapide.
    Pour chaque commentaire :
      score    ∈ [-1.0, +1.0] — pertinence/corrélation avec le titre
      intention  — accord | desaccord | question | temoignage | humour | critique | validation | aide | provocation
      emotion    — joie | colere | frustration | peur | espoir | admiration | tristesse | confusion | enthousiasme
      position   — favorable | defavorable | neutre | nuance
      engagement — faible | moyen | fort
      signal     — besoin | objection | frustration | aspiration | desir | opportunite | question | aucun
    """
    n = len(comments)
    lines = []
    for i, c in enumerate(comments):
        txt = _sanitize(c['text'])
        likes = c.get('likes', 0)
        like_bonus = round(math.log1p(likes) / 10, 2) if likes > 0 else 0
        lines.append(f"{i+1}. [likes:{likes}|bonus:{like_bonus}] {txt}")

    title_section = f'\nTITRE / SUJET : "{_sanitize(title)}"\n' if title else ""

    prompt = f"""Tu es un moteur de detection rapide de signaux humains.
{title_section}
Pour chaque commentaire ci-dessous, detecte :
1. score : correlation avec le sujet ∈ [-1.0, +1.0]
   +0.9/+1.0 : signal tres fort, emotionnel, motivation profonde
   +0.5/+0.9 : signal fort, pertinent
   +0.3/+0.5 : signal utile, reaction reelle
   -0.3/+0.3 : BRUIT — neutre, generique
   -0.5/-0.3 : opposition moderee, scepticisme
   -0.9/-0.5 : contradiction forte, rejet
   -1.0/-0.9 : spam, emoji seuls, "premier!", liens promo
   Likes eleves → amplifie. Emoji seuls → -1.0.
2. intention : accord | desaccord | question | temoignage | humour | critique | validation | aide | provocation
3. emotion   : joie | colere | frustration | peur | espoir | admiration | tristesse | confusion | enthousiasme
4. position  : favorable | defavorable | neutre | nuance
5. engagement: faible | moyen | fort
6. signal    : besoin | objection | frustration | aspiration | desir | opportunite | question | aucun

{chr(10).join(lines)}

Reponds UNIQUEMENT avec ce JSON (exactement {n} objets dans "items") :
{{
  "items": [
    {{"s": 0.0, "i": "accord", "e": "espoir", "p": "favorable", "eng": "fort", "mkt": "aspiration"}},
    ...
  ]
}}"""

    text = _call_claude(prompt, max_tokens=max(1500, n * 25), fast=True)
    data = _parse_json(text)
    items = data.get("items", [])

    # Construire les résultats — fallback gracieux si le modèle retourne moins
    results = []
    for idx in range(n):
        item = items[idx] if idx < len(items) else {}
        raw_score = item.get("s", 0.0)
        score = max(-1.0, min(1.0, float(raw_score) if isinstance(raw_score, (int, float)) else 0.0))
        results.append({
            "score":      score,
            "intention":  item.get("i", ""),
            "emotion":    item.get("e", ""),
            "position":   item.get("p", "neutre"),
            "engagement": item.get("eng", "faible"),
            "signal":     item.get("mkt", "aucun"),
        })
    return results


# ─── ÉTAPE 1B : CALCUL MATHÉMATIQUE DES KPIs ─────────────────────────────────

def calculate_math_kpis(comments, scores, title=""):
    """
    Calcule les KPIs directement depuis les scores — zéro IA, pure mathématique.
    Chaque KPI est accompagné de sa formule et de ses variables pour la transparence.
    """
    n = len(scores)
    if n == 0:
        return {}, {}

    # ── Catégories
    positifs    = [s for s in scores if s > 0.3]
    negatifs    = [s for s in scores if s < -0.3]
    qualifies   = [s for s in scores if abs(s) >= 0.3]
    spam        = [s for s in scores if s <= -0.7]
    haute_qual  = [s for s in scores if abs(s) >= 0.6]

    n_pos  = len(positifs)
    n_neg  = len(negatifs)
    n_qual = len(qualifies)
    n_spam = len(spam)
    n_hq   = len(haute_qual)

    # ── Stats de base
    mean_s    = sum(scores) / n
    variance  = sum((s - mean_s) ** 2 for s in scores) / n
    std_dev   = math.sqrt(variance)
    mean_abs  = sum(abs(s) for s in scores) / n
    mean_pos  = sum(positifs) / max(n_pos, 1)
    mean_neg  = sum(negatifs) / max(n_neg, 1)

    # ── Densité sémantique (richesse moyenne des commentaires qualifiés)
    qual_comments = [c for c, s in zip(comments, scores) if abs(s) >= 0.3]
    words_per_comment = [len(c['text'].split()) for c in qual_comments] if qual_comments else [0]
    avg_words = sum(words_per_comment) / max(len(words_per_comment), 1)
    densite = min(1.0, avg_words / 25)  # 25 mots = densité max

    # ── Persistance émotionnelle
    # Ratio de signaux forts (|s| >= 0.6) = émotions qui reviennent avec intensité
    persistance_raw = n_hq / max(n, 1)

    # ── KPI 1 : ENGAGEMENT
    # E = (Cq / Ct) × 100 × (1 + Rhq)
    # Cq = commentaires qualifiés, Ct = total, Rhq = ratio haute qualité
    engagement_raw = (n_qual / n) * (1 + persistance_raw) * 100
    engagement = min(100, round(engagement_raw, 1))

    # ── KPI 2 : AUTHENTICITÉ
    # A = (1 − Rs) × Rd × 100
    # Rs = ratio spam, Rd = densité sémantique
    spam_ratio = n_spam / max(n, 1)
    authenticite_raw = (1 - spam_ratio) * (0.4 + 0.6 * densite) * 100
    authenticite = min(100, round(authenticite_raw, 1))

    # ── KPI 3 : POLARISATION
    # P = σ(scores) × 100   [σ = écart-type]
    # Élevée = audience divisée, faible = audience homogène
    polarisation = min(100, round(std_dev * 100, 1))

    # ── KPI 4 : OPPORTUNITÉ MARKETING
    # O = μpos × (Cpos/Cq) × 100
    # μpos = intensité moyenne des positifs, pondérée par leur proportion
    if n_pos > 0 and n_qual > 0:
        opportunite_raw = mean_pos * (n_pos / n_qual) * 100
        opportunite = min(100, round(opportunite_raw, 1))
    else:
        opportunite = 0.0

    # ── KPI 5 : ALIGNEMENT TITRE
    # Al = μ|r| × 100
    # Mesure à quel point les commentaires RÉPONDENT au titre (pour ou contre)
    alignement = min(100, round(mean_abs * 100, 1))

    # ── KPI 6 : PERSISTANCE ÉMOTIONNELLE
    # Pe = (Chq / Ct) × 100
    # Proportion de commentaires à forte charge émotionnelle
    persistance = min(100, round(persistance_raw * 100, 1))

    # ── Labels
    def label(score, seuils):
        for val, lbl in seuils:
            if score >= val:
                return lbl
        return seuils[-1][1]

    kpis = {
        "engagement": {
            "score": int(engagement),
            "label": label(engagement, [(80,"Exceptionnel"),(65,"Très élevé"),(50,"Élevé"),(35,"Modéré"),(0,"Faible")]),
            "description": "",
            "formule": "E = (Cq / Ct) × (1 + Rhq) × 100",
            "variables": {"Cq": n_qual, "Ct": n, "Rhq": round(persistance_raw, 2)},
            "interpretation": "Proportion de l'audience qui s'engage réellement avec le contenu (commentaires qualifiés × intensité émotionnelle)"
        },
        "authenticite": {
            "score": int(authenticite),
            "label": label(authenticite, [(85,"Très authentique"),(70,"Authentique"),(50,"Mixte"),(30,"Performatif"),(0,"Artificiel")]),
            "description": "",
            "formule": "A = (1 − Rs) × (0.4 + 0.6×Rd) × 100",
            "variables": {"Rs": round(spam_ratio, 2), "Rd": round(densite, 2)},
            "interpretation": "Sincérité perçue : (1 - taux spam) pondéré par la densité sémantique des commentaires"
        },
        "polarisation": {
            "score": int(polarisation),
            "label": label(polarisation, [(70,"Très divisée"),(50,"Polarisée"),(30,"Modérée"),(15,"Homogène"),(0,"Consensus")]),
            "description": "",
            "formule": "P = σ(scores) × 100",
            "variables": {"σ": round(std_dev, 3), "μ": round(mean_s, 3)},
            "interpretation": "Écart-type des scores de corrélation : élevé = audience divisée, faible = audience homogène"
        },
        "opportunite": {
            "score": int(opportunite),
            "label": label(opportunite, [(75,"Forte"),(55,"Réelle"),(35,"Modérée"),(15,"Faible"),(0,"Nulle")]),
            "description": "",
            "formule": "O = μpos × (Cpos / Cq) × 100",
            "variables": {"μpos": round(mean_pos, 2), "Cpos": n_pos, "Cq": max(n_qual, 1)},
            "interpretation": "Intensité moyenne des signaux positifs pondérée par leur proportion parmi les commentaires qualifiés"
        },
        "alignement": {
            "score": int(alignement),
            "label": label(alignement, [(75,"Fort"),(55,"Bon"),(35,"Partiel"),(15,"Faible"),(0,"Nul")]),
            "description": "",
            "formule": "Al = μ|r| × 100",
            "variables": {"μ|r|": round(mean_abs, 3), "n": n},
            "interpretation": "Moyenne des valeurs absolues des corrélations : mesure si les commentaires RÉPONDENT au titre (qu'ils soient pour ou contre)"
        },
        "persistance": {
            "score": int(persistance),
            "label": label(persistance, [(60,"Intense"),(40,"Soutenue"),(25,"Modérée"),(10,"Faible"),(0,"Absente")]),
            "description": "",
            "formule": "Pe = (Chq / Ct) × 100",
            "variables": {"Chq": n_hq, "Ct": n},
            "interpretation": "Proportion de commentaires à forte charge émotionnelle (|score| ≥ 0.6) — révèle la profondeur de l'impact"
        },
    }

    # ── Distribution pour visualisation (une seule passe)
    _tp = _p = _neu = _neg = _tn = 0
    for s in scores:
        if   s >  0.6: _tp  += 1
        elif s >  0.3: _p   += 1
        elif s >= -0.3: _neu += 1
        elif s >= -0.6: _neg += 1
        else:           _tn  += 1
    distribution = {
        "tres_positifs": _tp,
        "positifs":      _p,
        "neutres":       _neu,
        "negatifs":      _neg,
        "tres_negatifs": _tn,
        "total":         n,
        "mean":          round(mean_s, 3),
        "std_dev":       round(std_dev, 3),
        "mean_abs":      round(mean_abs, 3),
        "likes_ponders": sum(c.get('likes', 0) for c in comments),
    }

    return kpis, distribution


# ─── ÉTAPE 2A : DESCRIPTIONS DES KPIs + ANALYSE PRINCIPALE ───────────────────

def _analyze_main(filtered, brain_context, video_context, kpis, distribution,
                  layer1_agg=None, nlp_data=None):

    lines = [f"[r:{s:+.2f}|likes:{c.get('likes',0)}] {_sanitize(c['text'])}" for c, s in filtered]
    comments_text = "\n".join(lines)
    brain_section = f"\nCONTEXTE METIER :\n{brain_context}\n" if brain_context else ""
    video_section = f"\nCONTENU ANALYSE : {video_context}\n" if video_context else ""

    # Résumé des KPIs déjà calculés
    kpi_summary = " | ".join([f"{k}={v['score']}" for k, v in kpis.items()])
    distrib_summary = f"Tres positifs:{distribution['tres_positifs']} Positifs:{distribution['positifs']} Neutres:{distribution['neutres']} Negatifs:{distribution['negatifs']} Tres negatifs:{distribution['tres_negatifs']}"

    # Résumé Layer 1 (pré-labellisé par Haiku — ne pas re-dériver, approfondir)
    l1_section = ""
    if layer1_agg:
        intentions_str = " | ".join([f"{k}:{v}%" for k, v in (layer1_agg.get('intentions') or {}).items()])
        emotions_str   = " | ".join([f"{k}:{v}%" for k, v in (layer1_agg.get('emotions_detectees') or {}).items()])
        signaux_str    = " | ".join([f"{k}:{v}%" for k, v in (layer1_agg.get('signaux_marketing') or {}).items()])
        l1_section = f"""
SIGNAUX PRE-LABELLISES (Couche 1 — ne pas re-deriver, partir de cette base pour approfondir) :
Commentaires pertinents : {layer1_agg.get('total_pertinents',0)} | Analyses ici : {layer1_agg.get('top40_selectionnes',0)}
Intentions detectees : {intentions_str or '—'}
Emotions detectees   : {emotions_str or '—'}
Signaux marketing    : {signaux_str or '—'}
Favorables : {layer1_agg.get('pct_favorable',0)}% | Defavorables : {layer1_agg.get('pct_defavorable',0)}% | Tres engages : {layer1_agg.get('pct_engage_fort',0)}%
→ Ta mission : APPROFONDIR ces signaux — pas les re-deriver. Comprendre POURQUOI. Chercher le non-dit.
"""

    # Signaux NLP pré-calculés (zéro IA — mesurés objectivement)
    nlp_section = ""
    if nlp_data:
        lex = nlp_data.get("lexical", {})
        top_tfidf = lex.get("top_tfidf", [])[:8]
        top_bigrams = lex.get("top_bigrams", [])[:5]
        rel_dist = nlp_data.get("relevance_distribution") or {}
        clusters = nlp_data.get("cluster_summary", [])
        diversity = nlp_data.get("semantic_diversity", "N/A")

        tfidf_str   = " | ".join(f"{t['token']}({t['score']})" for t in top_tfidf)
        bigram_str  = " | ".join(f"{b['bigram']}({b['freq']})" for b in top_bigrams)
        cluster_str = " | ".join(
            f"Cluster{c['cluster_id']} {c['pct']}% [{', '.join(c['top_tokens'][:3])}]"
            for c in clusters
        )
        rel_str = (
            f"Haute(>0.65):{rel_dist.get('haute',0)} Moyenne:{rel_dist.get('moyenne',0)} "
            f"Faible:{rel_dist.get('faible',0)} Mean:{rel_dist.get('mean',0)}"
        ) if rel_dist else "non calculé"

        nlp_section = f"""
SIGNAUX NLP/STATISTIQUES PRE-CALCULES (données objectivement mesurées — utilise-les comme preuves) :
Context Relevance Score (similarité titre/commentaire) : {rel_str}
Diversité sémantique de l'audience : {diversity} (0=homogène, 1=très dispersée)
Tokens TF-IDF dominants : {tfidf_str or '—'}
Bigrams fréquents (cooccurrences) : {bigram_str or '—'}
Clusters comportementaux : {cluster_str or 'non calculé'}
Vocabulaire total : {lex.get('vocabulary_size',0)} tokens uniques | Densité : {lex.get('avg_tokens_per_comment',0)} tok/commentaire

RÈGLE ABSOLUE : Chaque conclusion de ton analyse doit s'appuyer sur ces signaux mesurés.
Formule : "X% des commentaires montrent [signal NLP] → ce qui indique [interprétation]"
Ne dis pas seulement "l'audience est frustrée". Dis "46% des commentaires portent des marqueurs de frustration, avec les tokens dominants : [liste]. Ce signal indique..."
"""

    prompt = f"""{GABRIEL_SYSTEM}
{brain_section}{video_section}
DONNEES MATHEMATIQUES DEJA CALCULEES :
KPIs : {kpi_summary}
Distribution : {distrib_summary}
Moyenne scores : {distribution['mean']} | Ecart-type : {distribution['std_dev']}
{l1_section}{nlp_section}
{len(filtered)} commentaires selectionnes (r = score, tri par valeur signal) :
{comments_text}

Ta mission : ecrire les DESCRIPTIONS des KPIs et produire l analyse qualitative complete.
IMPORTANT : Ancre chaque conclusion dans les signaux NLP/statistiques fournis ci-dessus.

LECTURE REQUISE — AVANT DE COMMENCER :
→ Ne lis pas ce que les gens DISENT. Lis ce qu ils PORTENT.
→ Derriere une critique : quel espoir decu se cache ? (Munroe : potentiel bloque)
→ Derriere un enthousiasme : quelle aspiration profonde est nourrie ? (Munroe : vision qui cherche a se realiser)
→ Derriere le silence ou la neutralite : quelle peur non exprimee ?
→ Detecte le PURPOSE cache : quelle mission, quel potentiel, quelle vision aspire a emerger dans ces commentaires ?
→ Detecte les besoins bibliques universels : appartenance, signifiance, transformation, legacy, grace
→ Les recommandations partent de la vraie aspiration humaine detectee — jamais d un angle invente

Reponds UNIQUEMENT avec ce JSON :

{{
  "kpi_descriptions": {{
    "engagement": "1 phrase choc max — ex: Audience spectatrice, pas actrice",
    "authenticite": "1 phrase choc max",
    "polarisation": "1 phrase choc max",
    "opportunite": "1 phrase choc max",
    "alignement": "1 phrase choc max",
    "persistance": "1 phrase choc max"
  }},
  "emotions": {{
    "repartition": [
      {{"emotion": "Admiration", "pourcentage": 38, "couleur": "#F59E0B"}},
      {{"emotion": "Espoir", "pourcentage": 22, "couleur": "#10B981"}},
      {{"emotion": "Frustration", "pourcentage": 18, "couleur": "#EF4444"}},
      {{"emotion": "Curiosite", "pourcentage": 14, "couleur": "#8B5CF6"}},
      {{"emotion": "Scepticisme", "pourcentage": 8, "couleur": "#6B7280"}}
    ],
    "dominante": "1 mot",
    "intensite": "1 phrase — ex: Chaleur collective sans engagement profond",
    "commentaires_revelateurs": ["citation exacte courte 1", "citation 2", "citation 3"],
    "signaux_authenticite": "1 phrase",
    "signaux_artificialite": "1 phrase",
    "besoins_sous_jacents": "1 phrase — besoin psychologique dominant",
    "espoir_decu": "1 phrase — derriere les critiques, quel espoir a ete decoit ?",
    "aspiration_nourrie": "1 phrase — derriere l enthousiasme, quelle aspiration profonde est nourrie ?"
  }},
  "psychologie": {{
    "motivations_profondes": ["5 mots max chacun", "motivation 2", "motivation 3"],
    "frustrations": ["5 mots max", "frustration 2", "frustration 3"],
    "peurs_implicites": ["5 mots max", "peur 2"],
    "desirs_caches": ["5 mots max", "desir 2", "desir 3"],
    "croyances_limitantes": ["5 mots max", "croyance 2"],
    "croyances_mobilisatrices": ["5 mots max", "croyance 2"],
    "mecanismes_psychologiques": "1 phrase — biais Kahneman dominant",
    "rapport_argent": "1 phrase",
    "rapport_succes": "1 phrase",
    "rapport_image": "1 phrase",
    "rapport_autorite": "1 phrase",
    "rapport_spiritualite": "1 phrase",
    "rapport_famille": "1 phrase",
    "rapport_travail": "1 phrase",
    "valeurs_dominantes": ["valeur 1", "valeur 2", "valeur 3", "valeur 4"],
    "systeme_de_valeurs": "1 phrase",
    "besoins_identitaires": "1 phrase",
    "tensions_internes": "1 phrase — tension entre qui ils sont et qui ils sont appeles a devenir",
    "maturite_emotionnelle": "1 phrase",
    "potentiel_bloque": "1 phrase — quel potentiel (Myles Munroe) est retenu par la peur ou les croyances limitantes ?",
    "signal_de_purpose": "1 phrase — quel signal de mission ou vocation emerge dans les commentaires ?",
    "besoin_d_appartenance": "1 phrase — a quel groupe, tribu, communaute aspirent-ils a appartenir ?",
    "quete_de_signifiance": "1 phrase — comment cherchent-ils a donner du poids a leur existence ?",
    "desir_de_legacy": "1 phrase — ce qu ils veulent laisser derriere eux, leur trace dans le monde",
    "besoin_de_transformation": "1 phrase — comment veulent-ils se depasser, evoluer, devenir meilleurs ?"
  }},
  "aspirations": {{
    "ce_qu_ils_veulent_devenir": "1 phrase",
    "ce_qu_ils_veulent_construire": "1 phrase",
    "ce_qu_ils_veulent_transmettre": "1 phrase",
    "ce_qu_ils_veulent_proteger": "1 phrase",
    "ce_qu_ils_veulent_eviter": "1 phrase",
    "ambitions": ["ambition 1", "ambition 2", "ambition 3"],
    "freins_aux_aspirations": ["frein 1", "frein 2", "frein 3"],
    "appel_interieur": "1 phrase — l appel profond qu ils ressentent mais n ont pas encore ose suivre",
    "vision_de_leur_meilleur_moi": "1 phrase — qui ils imaginent qu ils pourraient vraiment devenir"
  }},
  "identitaire": {{
    "coherence_percue": "1 phrase",
    "authenticite_percue": "1 phrase",
    "singularite": "1 phrase",
    "credibilite": "1 phrase",
    "confiance_generee": "1 phrase",
    "incaherences_detectees": "1 phrase",
    "points_de_differenciation": ["point 1", "point 2"],
    "faiblesses_narratives": ["faiblesse 1", "faiblesse 2"],
    "recit_dominant": "1 phrase — le grand recit collectif"
  }},
  "culturel": {{
    "visions_du_monde": "1 phrase",
    "croyances_dominantes": ["croyance 1", "croyance 2", "croyance 3"],
    "references_culturelles": ["reference 1", "reference 2"],
    "tensions_culturelles": "1 phrase",
    "recits_emergents": "1 phrase",
    "dynamique_communautaire": "1 phrase",
    "signaux_faibles": ["signal 1", "signal 2"]
  }},
  "marketing": {{
    "hooks_performants": ["Hook pret-a-poster 1", "Hook 2", "Hook 3", "Hook 4", "Hook 5"],
    "angles_de_contenu": ["angle 1", "angle 2", "angle 3"],
    "sujets_qui_attirent": ["sujet 1", "sujet 2", "sujet 3"],
    "sujets_qui_divisent": ["sujet 1", "sujet 2"],
    "mots_cles": ["mot1", "mot2", "mot3", "mot4", "mot5", "mot6"],
    "objections_visibles": ["objection 1", "objection 2"],
    "objections_invisibles": ["objection cachee 1", "objection 2"],
    "declencheurs_emotionnels": ["declencheur 1", "declencheur 2", "declencheur 3"],
    "leviers_de_conversion": ["levier 1", "levier 2", "levier 3"],
    "opportunites_offre": ["opportunite 1", "opportunite 2"],
    "opportunites_contenu": ["idee 1", "idee 2", "idee 3", "idee 4"],
    "risques_communication": ["risque 1", "risque 2"],
    "positionnement_recommande": "1 phrase — positionnement differentiant"
  }},
  "demographique": {{
    "genre": {{"hommes": 40, "femmes": 60}},
    "tranches_age": [
      {{"tranche": "18-24", "pourcentage": 20}},
      {{"tranche": "25-34", "pourcentage": 35}},
      {{"tranche": "35-44", "pourcentage": 25}},
      {{"tranche": "45-54", "pourcentage": 15}},
      {{"tranche": "55+", "pourcentage": 5}}
    ],
    "metiers_probables": ["metier 1", "metier 2", "metier 3"],
    "niveau_social_probable": "1 phrase",
    "centres_interet": ["interet 1", "interet 2", "interet 3", "interet 4"],
    "comportements_digitaux": ["comportement 1", "comportement 2", "comportement 3"]
  }},
  "transformation": {{
    "etat_actuel": {{
      "situation": "1 phrase — où ils en sont concrètement aujourd'hui",
      "frustration_principale": "le point de douleur #1 qui les maintient à l'état A",
      "croyance_bloquante": "la croyance ou le récit intérieur qui les empêche d'avancer",
      "identite_actuelle": "comment ils se définissent eux-mêmes aujourd'hui",
      "conscience_du_probleme": "naissante | partielle | pleine"
    }},
    "etat_desire": {{
      "transformation_visee": "la transformation concrète qu'ils cherchent — pas un rêve vague, une réalité précise",
      "identite_aspiree": "qui ils veulent être après la transformation — leur 'moi B'",
      "vie_revelee": "la vie qu'ils imaginent de l'autre côté du changement",
      "indicateur_de_succes": "comment ils sauraient concrètement qu'ils ont réussi"
    }},
    "le_pont": {{
      "ce_dont_ils_ont_besoin": "la ressource, le guide ou l'outil manquant pour passer de A à B",
      "obstacle_principal": "le blocage #1 qui empêche la transition — psychologique, pratique ou identitaire",
      "declencheur_de_transition": "ce qui les ferait passer à l'action maintenant — le signal déclencheur",
      "message_de_passage": "la phrase qui capture leur voyage — 'Je suis X qui cherche à devenir Y sans Z'"
    }}
  }},
  "marches_caches": {{
    "segments_detectes": [
      {{
        "segment": "nom court du segment",
        "description": "qui est ce segment précisément — démographie, situation, état d'esprit",
        "signaux": "les indices dans les commentaires qui révèlent sa présence",
        "taille_estimee": "faible | moyenne | importante",
        "valeur_potentielle": "pourquoi ce segment est précieux — levier de croissance ou d'impact"
      }}
    ],
    "besoins_sous_exprimes": ["besoin que personne ne formule clairement 1", "besoin 2", "besoin 3"],
    "opportunites_niche": ["opportunité de niche 1 — précise et actionnelle", "opportunité 2"],
    "audiences_adjacentes": ["audience qui n'est pas là mais devrait l'être 1", "audience 2"],
    "angle_differentiant": "l'angle le moins évident mais le plus porteur — celui que les concurrents ne voient pas"
  }}
}}"""

    text = _call_claude(prompt, max_tokens=5500)
    return _parse_json(text)


# ─── ÉTAPE 2B : PERSONAS (appel dédié) ───────────────────────────────────────

def _analyze_personas(filtered, brain_context, main_data, kpis):

    emo  = main_data.get('emotions', {})
    psy  = main_data.get('psychologie', {})
    asp  = main_data.get('aspirations', {})
    ident= main_data.get('identitaire', {})

    ctx = f"""
Emotions : {', '.join([e.get('emotion', '') for e in emo.get('repartition',[])[:3]])}
Espoir decu (derriere les critiques) : {emo.get('espoir_decu','')}
Aspiration nourrie (derriere l enthousiasme) : {emo.get('aspiration_nourrie','')}
Motivations : {' | '.join(psy.get('motivations_profondes',[])[:3])}
Frustrations : {' | '.join(psy.get('frustrations',[])[:3])}
Desirs caches : {' | '.join(psy.get('desirs_caches',[])[:3])}
Potentiel bloque (Munroe) : {psy.get('potentiel_bloque','')}
Signal de purpose : {psy.get('signal_de_purpose','')}
Besoin d appartenance : {psy.get('besoin_d_appartenance','')}
Quete de signifiance : {psy.get('quete_de_signifiance','')}
Desir de legacy : {psy.get('desir_de_legacy','')}
Besoin de transformation : {psy.get('besoin_de_transformation','')}
Besoins identitaires : {psy.get('besoins_identitaires','')}
Tensions internes : {psy.get('tensions_internes','')}
Appel interieur : {asp.get('appel_interieur','')}
Vision du meilleur moi : {asp.get('vision_de_leur_meilleur_moi','')}
Recit dominant : {ident.get('recit_dominant','')}
Aspirations : {asp.get('ce_qu_ils_veulent_devenir','')}
Polarisation : {kpis.get('polarisation',{}).get('score',0)}/100
""".strip()

    lines = [f"- [r:{s:+.2f}] {_sanitize(c['text'])}" for c, s in filtered[:25]]
    brain_section = f"\nCONTEXTE METIER :\n{brain_context}\n" if brain_context else ""

    prompt = f"""{GABRIEL_SYSTEM}
{brain_section}
SYNTHESE AUDIENCE :
{ctx}

COMMENTAIRES :
{chr(10).join(lines)}

3 personas RADICALEMENT DIFFERENTS, ultra-realistes, ancres dans les commentaires reels.
Chaque persona = une personne reelle qu on pourrait croiser dans la rue.

CADRE DE PROFONDEUR :
- Myles Munroe : chaque persona porte un PURPOSE en germe. Quelle est sa mission ? Quel potentiel est bloque ? Quelle vision cherche a s exprimer a travers ce qu il/elle consomme ?
- Principes bibliques de l ame humaine : quelle est son besoin d appartenance (etre connu et vu), sa quete de signifiance (que sa vie compte), son desir de legacy (laisser une trace), sa tension entre qui il/elle est et qui il/elle est appele(e) a devenir ?
- Jung : ombre (ce qu il/elle rejette de lui/elle-meme), archetype dominant (Heros, Orphelin, Sage, Guerrier...)
- Frankl : quel vide de sens ? quelle quete de meaning ?
- Kahneman : quels biais cognitifs gouvernent ses decisions ?

REGLE ABSOLUE : ne pas inventer. Tout doit etre inferable des signaux des commentaires.

Reponds UNIQUEMENT avec ce JSON :

{{
  "personas": [
    {{
      "nom": "Prenom Nom",
      "age": 31,
      "genre": "Femme",
      "metier": "metier precis",
      "situation_vie": "situation complete — lieu, famille, situation financiere",
      "etat_esprit": "etat psychologique actuel en profondeur",
      "vision_monde": "philosophie en 1 phrase memorable",
      "langage_typique": "expression exacte qu elle dirait dans un commentaire",
      "ombre_jungienne": "face cachee qu elle ne montre pas",
      "quete_de_sens": "quete fondamentale au sens de Frankl",
      "biais_cognitifs": "2-3 biais Kahneman qui guidient ses decisions",
      "frustrations": ["frustration concrete 1", "frustration 2"],
      "aspirations": ["aspiration profonde 1", "aspiration 2"],
      "peurs": ["peur existentielle 1", "peur pratique 2"],
      "desirs": ["desir cache 1", "desir 2"],
      "rapport_argent": "rapport reel a l argent avec contradictions",
      "rapport_spiritualite": "relation a la foi et au sens",
      "rapport_autorite": "perception des experts et leaders",
      "habitudes_digitales": ["habitude specifique 1", "habitude 2"],
      "declencheurs_emotionnels": ["ce qui la fait reagir fort 1", "declencheur 2"],
      "ce_qui_la_ferait_acheter": "declencheur exact d achat",
      "ce_qui_la_ferait_fuir": "repoussoir principal",
      "messages_impactants": ["message qui la toucherait au plus profond", "message 2"],
      "objections_a_lever": ["objection principale", "objection 2"],
      "histoire_interieure": "monologue interieur — ce qu elle se dit a elle-meme la nuit",
      "mission_cachee": "la mission ou le purpose qu elle porte sans encore le nommer — Myles Munroe",
      "potentiel_non_exprime": "le potentiel qu elle sent en elle mais que la peur ou les circonstances bloquent",
      "archetype_jungien": "archetype dominant — Heros, Sage, Orphelin, Guerrier, Createur, Souverain...",
      "besoin_d_appartenance": "a quelle communaute, tribu ou famille de coeur veut-elle appartenir vraiment ?",
      "desir_de_legacy": "ce qu elle veut laisser derriere elle — ce qui doit outliver sa propre vie",
      "tension_existentielle": "la tension entre qui elle est aujourd hui et qui elle est appelee a devenir"
    }},
    {{
      "nom": "Prenom Nom 2", "age": 44, "genre": "Homme", "metier": "metier different",
      "situation_vie": "situation complete differente", "etat_esprit": "etat different",
      "vision_monde": "philosophie differente", "langage_typique": "expression differente",
      "ombre_jungienne": "ombre differente", "quete_de_sens": "quete differente",
      "biais_cognitifs": "biais differents",
      "frustrations": ["frustration 1", "frustration 2"], "aspirations": ["aspiration 1", "aspiration 2"],
      "peurs": ["peur 1", "peur 2"], "desirs": ["desir 1", "desir 2"],
      "rapport_argent": "rapport", "rapport_spiritualite": "spiritualite", "rapport_autorite": "autorite",
      "habitudes_digitales": ["habitude 1", "habitude 2"], "declencheurs_emotionnels": ["dec 1", "dec 2"],
      "ce_qui_la_ferait_acheter": "declencheur", "ce_qui_la_ferait_fuir": "repoussoir",
      "messages_impactants": ["message 1", "message 2"], "objections_a_lever": ["obj 1", "obj 2"],
      "histoire_interieure": "monologue"
    }},
    {{
      "nom": "Prenom Nom 3", "age": 26, "genre": "Femme", "metier": "metier different",
      "situation_vie": "situation complete", "etat_esprit": "etat different",
      "vision_monde": "philosophie", "langage_typique": "expression",
      "ombre_jungienne": "ombre", "quete_de_sens": "quete", "biais_cognitifs": "biais",
      "frustrations": ["f1", "f2"], "aspirations": ["a1", "a2"],
      "peurs": ["p1", "p2"], "desirs": ["d1", "d2"],
      "rapport_argent": "r", "rapport_spiritualite": "s", "rapport_autorite": "a",
      "habitudes_digitales": ["h1", "h2"], "declencheurs_emotionnels": ["d1", "d2"],
      "ce_qui_la_ferait_acheter": "x", "ce_qui_la_ferait_fuir": "y",
      "messages_impactants": ["m1", "m2"], "objections_a_lever": ["o1", "o2"],
      "histoire_interieure": "monologue"
    }}
  ]
}}"""

    text = _call_claude(prompt, max_tokens=5000)
    data = _parse_json(text)
    return data.get('personas', [])


# ─── ÉTAPE 2C : RECOMMANDATIONS (appel dédié) ────────────────────────────────

def _analyze_recommendations(filtered, brain_context, main_data, kpis):

    emo  = main_data.get('emotions', {})
    psy  = main_data.get('psychologie', {})
    mkt  = main_data.get('marketing', {})
    ident= main_data.get('identitaire', {})
    asp  = main_data.get('aspirations', {})

    ctx = f"""
Emotions dominantes : {', '.join([e.get('emotion', '') for e in emo.get('repartition',[])[:3]])}
Espoir decu (derriere les critiques) : {emo.get('espoir_decu','')}
Aspiration nourrie (derriere l enthousiasme) : {emo.get('aspiration_nourrie','')}
Motivations : {' | '.join(psy.get('motivations_profondes',[])[:3])}
Frustrations : {' | '.join(psy.get('frustrations',[])[:3])}
Desirs caches : {' | '.join(psy.get('desirs_caches',[])[:3])}
Potentiel bloque (Munroe) : {psy.get('potentiel_bloque','')}
Signal de purpose : {psy.get('signal_de_purpose','')}
Quete de signifiance : {psy.get('quete_de_signifiance','')}
Desir de legacy : {psy.get('desir_de_legacy','')}
Besoin de transformation : {psy.get('besoin_de_transformation','')}
Tensions internes : {psy.get('tensions_internes','')}
Appel interieur : {asp.get('appel_interieur','')}
Vision du meilleur moi : {asp.get('vision_de_leur_meilleur_moi','')}
Ce qu ils veulent devenir : {asp.get('ce_qu_ils_veulent_devenir','')}
Ce qu ils veulent transmettre : {asp.get('ce_qu_ils_veulent_transmettre','')}
Recit dominant : {ident.get('recit_dominant','')}
Positionnement suggere : {mkt.get('positionnement_recommande','')}
Hooks top : {' | '.join(mkt.get('hooks_performants',[])[:3])}
Engagement : {kpis.get('engagement',{}).get('score',0)}/100
Opportunite : {kpis.get('opportunite',{}).get('score',0)}/100
""".strip()

    brain_section = f"\nCONTEXTE METIER :\n{brain_context}\n" if brain_context else ""

    prompt = f"""{GABRIEL_SYSTEM}
{brain_section}
SYNTHESE ANALYSE :
{ctx}

Sur la base de cette analyse, produis les recommandations strategiques actionnables.

PRINCIPE FONDAMENTAL : Ces recommandations ne partent PAS d un angle marketing invente.
Elles partent des vraies aspirations humaines detectees dans les commentaires — et y repondent honnêtement.
Le marketing veritable ne cree pas des besoins : il nomme et sert ceux qui existent deja.
Reponds a : "Que attend VRAIMENT cette audience — au fond ?" puis construis la strategie depuis cette verite.

Reponds UNIQUEMENT avec ce JSON :

{{
  "recommandations": {{
    "verite_de_l_audience": "la vraie attente profonde de cette audience — ce qu ils esperent trouver mais ne verbalisent pas",
    "insight_strategique_cle": "l insight le plus important — celui qui change tout",
    "promesse_authentique": "la promesse que le createur peut faire en toute integrite, ancree dans les vraies aspirations detectees",
    "actions_prioritaires": ["action concrete 1", "action 2", "action 3", "action 4"],
    "strategie_contenu": "strategie differenciante ancree dans les aspirations reelles de cette audience",
    "positionnement": "positionnement precis base sur l analyse — qui repond a leur vraie attente",
    "differenciation": "comment se distinguer radicalement en servant mieux le purpose de l audience",
    "angles_narratifs": ["recit ancre dans leur aspiration 1", "recit 2", "recit 3"],
    "message_central": "la seule phrase que cette audience doit retenir — celle qui repond a leur appel interieur",
    "ce_qu_ils_ne_disent_pas_mais_veulent_entendre": "la verite qu ils esperent entendre — leur besoin de signifiance, de legacy, d appartenance",
    "risques_strategiques": ["risque 1", "risque 2"],
    "prochaines_etapes": ["cette semaine : action", "ce mois : action", "dans 3 mois : objectif", "dans 6 mois : vision"]
  }}
}}"""

    text = _call_claude(prompt, max_tokens=2500)
    data = _parse_json(text)
    return data.get('recommandations', {})


# ─── ÉTAPE 2D : BRIEF GABRIEL (synthèse exécutive) ───────────────────────────

def _generate_brief(main_data, kpis, brain_context, video_context):
    """Génère 3 phrases choc : qui est l'audience, l'insight clé, l'action prioritaire."""

    emo  = main_data.get('emotions', {})
    psy  = main_data.get('psychologie', {})
    mkt  = main_data.get('marketing', {})
    asp  = main_data.get('aspirations', {})

    ctx = f"""
Vidéo : {video_context or 'non renseigné'}
Emotion dominante : {emo.get('dominante','')} — {emo.get('intensite','')}
Motivations : {' | '.join(psy.get('motivations_profondes',[])[:3])}
Tensions : {psy.get('tensions_internes','')}
Désirs cachés : {' | '.join(psy.get('desirs_caches',[])[:2])}
Ce qu'ils veulent devenir : {asp.get('ce_qu_ils_veulent_devenir','')}
Insight stratégique : {mkt.get('positionnement_recommande','')}
Engagement : {kpis.get('engagement',{}).get('score',0)}/100
Opportunité : {kpis.get('opportunite',{}).get('score',0)}/100
""".strip()

    brain_section = f"\nCONTEXTE METIER :\n{brain_context}\n" if brain_context else ""

    prompt = f"""{GABRIEL_SYSTEM}
{brain_section}
SYNTHESE ANALYSE :
{ctx}

Tu dois rédiger le BRIEF GABRIEL : une synthèse exécutive ultra-concise de cette audience.
3 phrases. Chacune percutante, mémorable, non-évidente.

LENS REQUIS :
- La phrase "qui" doit aller au-dela des apparences. Qui sont-ils VRAIMENT — quel potentiel, quelle aspiration profonde, quel appel interieur les traverse ?
- La phrase "insight" doit reveler la verite que personne ne verrait sans analyse profonde — quelque chose sur leur purpose bloque, leur espoir cache, leur besoin de signifiance.
- La phrase "action" doit etre la reponse JUSTE a leur vraie attente — pas un angle marketing, une reponse honnete.

Reponds UNIQUEMENT avec ce JSON :

{{
  "brief": {{
    "qui": "1 phrase — qui est vraiment cette audience, au-dela des apparences. Leur essence, leur aspiration profonde, ce qu ils portent.",
    "insight": "1 phrase — la verite la plus contre-intuitive revelee par ces commentaires. Leur besoin cache, leur espoir decu, leur potentiel bloque.",
    "action": "1 phrase imperative — la reponse juste et honnete que le createur doit donner a la vraie attente de cette audience."
  }}
}}"""

    text = _call_claude(prompt, max_tokens=400, fast=True)
    data = _parse_json(text)
    return data.get('brief', {})


# ─── LIVRABLES FONDÉS SUR DONNÉES — INTERPRÉTATION IA ───────────────────────

def _generate_livrables_ia(filtered, brain_context, video_context, main_data,
                            nlp_data, stat_deliverables, layer1_agg):
    """
    Génère les 5 livrables interprétatifs fondés sur données mesurées.
    Chaque conclusion doit contenir : conclusion, indicateur_statistique,
    signaux, interpretation, score_confiance.

    Livrables produits :
      lecture_sujet
      ce_qui_rassemble
      ce_qui_divise
      tension_centrale
      synthese_psychologique
    """
    # Sans données NLP mesurées, l'ancrage statistique est impossible
    if not nlp_data and not stat_deliverables:
        return {}


    # ── Synthèse des signaux mesurés pour le prompt ──────────────────────────
    lex = (nlp_data or {}).get("lexical", {})
    rel_dist = (nlp_data or {}).get("relevance_distribution") or {}
    clusters = (nlp_data or {}).get("cluster_summary", [])
    diversity = (nlp_data or {}).get("semantic_diversity", "N/A")

    top_tfidf = lex.get("top_tfidf", [])[:10]
    tfidf_str = " | ".join(f"{t['token']}({t['score']})" for t in top_tfidf) or "—"
    top_bigrams = lex.get("top_bigrams", [])[:6]
    bigram_str = " | ".join(f"{b['bigram']}×{b['freq']}" for b in top_bigrams) or "—"

    cluster_str = "\n".join(
        f"  Cluster {c['cluster_id']} ({c['pct']}%, {c['size']} cmnt) | "
        f"tokens : {', '.join(c['top_tokens'][:4])} | exemples : {' / '.join(c['samples'][:2])}"
        for c in clusters
    ) or "  —"

    rel_str = (
        f"Forte (>0.65) : {rel_dist.get('haute',0)} cmnt | "
        f"Partielle : {rel_dist.get('moyenne',0)} | Faible : {rel_dist.get('faible',0)} | "
        f"CRS moyen : {rel_dist.get('mean',0)}"
    ) if rel_dist else "non calculé"

    # Signaux Layer 1 agrégés
    pos = stat_deliverables.get("positionnement_audience", {})
    emo = stat_deliverables.get("carte_emotionnelle", {})
    camps = stat_deliverables.get("repartition_camps", {}).get("camps", {})

    psy = main_data.get("psychologie", {})
    asp = main_data.get("aspirations", {})

    context = f"""
DONNÉES STATISTIQUES MESURÉES (base des livrables — ne pas inventer, partir de ces chiffres) :

Positionnement audience :
{pos.get('indicateur_statistique','—')} | Distribution : {pos.get('distribution',{})}

Carte émotionnelle :
{emo.get('indicateur_statistique','—')}

Répartition camps :
Favorables : {camps.get('favorable',{}).get('pct',0)}% |
Opposés : {camps.get('oppose',{}).get('pct',0)}% |
Neutres : {camps.get('neutre',{}).get('pct',0)}%

Context Relevance Score : {rel_str}
Diversité sémantique : {diversity}

Tokens TF-IDF dominants : {tfidf_str}
Bigrams fréquents : {bigram_str}

Clusters comportementaux :
{cluster_str}

Signaux Layer 1 :
Intentions : {' | '.join(f"{k}:{v}%" for k,v in (layer1_agg.get('intentions') or {}).items())}
Emotions : {' | '.join(f"{k}:{v}%" for k,v in (layer1_agg.get('emotions_detectees') or {}).items())}

Analyse psychologique (déjà produite) :
Motivations : {' | '.join((psy.get('motivations_profondes') or [])[:3])}
Frustrations : {' | '.join((psy.get('frustrations') or [])[:3])}
Tensions : {psy.get('tensions_internes','')}
Ce qu'ils veulent devenir : {asp.get('ce_qu_ils_veulent_devenir','')}
""".strip()

    brain_section = f"\nCONTEXTE METIER :\n{brain_context}\n" if brain_context else ""
    video_section = f"SUJET : {video_context}\n" if video_context else ""

    prompt = f"""{GABRIEL_SYSTEM}
{brain_section}{video_section}
{context}

Produis 5 livrables interprétatifs FONDÉS SUR CES DONNÉES.
Règle absolue : chaque livrable doit répondre à "Sur quelle donnée mesurée cette conclusion repose-t-elle ?"
Format requis pour CHAQUE livrable :
  conclusion : phrase claire et non évidente
  indicateur_statistique : chiffre ou mesure exacte tirée des données ci-dessus
  signaux : 3-5 tokens ou bigrams ou patterns qui justifient la conclusion
  interpretation : explication comportementale du signal — pourquoi ce signal révèle ça
  score_confiance : float ∈ [0.0, 1.0] — 0.8+ si fortement soutenu, 0.3-0.5 si hypothèse

LIEN DONNÉES → INTERPRÉTATION obligatoire pour chaque livrable.

Reponds UNIQUEMENT avec ce JSON :
{{
  "lecture_sujet": {{
    "conclusion": "comment l'audience a reçu ce sujet — non évident",
    "indicateur_statistique": "ex: CRS moyen 0.73 — 68% des commentaires fortement liés au sujet",
    "signaux": ["token1", "token2", "bigram1"],
    "interpretation": "explication comportementale : pourquoi ces signaux révèlent cette réception",
    "score_confiance": 0.82
  }},
  "ce_qui_rassemble": {{
    "conclusion": "le point de convergence le plus fort",
    "indicateur_statistique": "ex: X% des commentaires favorables partagent les tokens Y et Z",
    "signaux": ["signal1", "signal2", "signal3"],
    "interpretation": "ce que ce consensus révèle psychologiquement sur l'audience",
    "score_confiance": 0.75
  }},
  "ce_qui_divise": {{
    "conclusion": "la ligne de fracture principale",
    "indicateur_statistique": "ex: polarisation σ=0.45, camps 38% vs 29%",
    "signaux": ["signal1", "signal2"],
    "interpretation": "pourquoi cette fracture existe — besoin psychologique non satisfait",
    "score_confiance": 0.70
  }},
  "tension_centrale": {{
    "conclusion": "la tension fondamentale qui traverse l'audience",
    "indicateur_statistique": "ex: X% frustration + Y% admiration = tension entre [A] et [B]",
    "signaux": ["signal1", "signal2", "signal3"],
    "interpretation": "explication psychologique de la tension — ce qu'elle révèle de profond",
    "score_confiance": 0.65
  }},
  "synthese_psychologique": {{
    "conclusion": "synthèse en 1 phrase choc — la vérité la plus importante",
    "indicateur_statistique": "les 2-3 chiffres les plus significatifs qui fondent cette synthèse",
    "signaux": ["signal1", "signal2", "signal3", "signal4"],
    "interpretation": "pourquoi c'est la conclusion la plus importante — ce qu'elle implique pour le créateur",
    "score_confiance": 0.78
  }}
}}"""

    text = _call_claude(prompt, max_tokens=2000)
    try:
        return _parse_json(text)
    except Exception as e:
        print(f"[GABRIEL] livrables_ia ERREUR parse : {e}")
        return {}


# ─── COUCHE 2 : SÉLECTION DES COMMENTAIRES À FORTE VALEUR (Python pur) ────────

def _select_high_value(comments, layer1):
    """
    Layer 2 — Aucun appel IA.
    Sélectionne les commentaires les plus pertinents par 5 critères :
    - score |s| >= 0.3 (signal pertinent, positif OU négatif)
    - engagement "fort" (signal Layer 1)
    - likes élevés (opinion silencieuse)
    - émotion forte (frustration / espoir / colère / enthousiasme)
    - signal marketing présent (besoin/objection/aspiration/désir/opportunité)
    Retourne (filtered, layer1_agg)
      filtered   : [(comment, score_float), ...]
      layer1_agg : dict — résumé agrégé des signaux Layer 1 (contexte pour Layer 3)
    """
    STRONG_EMOTIONS  = {"frustration", "colere", "espoir", "enthousiasme", "admiration"}
    STRONG_SIGNALS   = {"besoin", "objection", "aspiration", "desir", "opportunite"}

    scored = list(zip(comments, layer1))
    filtered_pairs = []
    for c, sig in scored:
        s = sig["score"]
        # Critère principal : pertinence minimale
        if abs(s) < 0.3:
            continue
        filtered_pairs.append((c, sig))

    # Fallback si trop peu
    if len(filtered_pairs) < 5:
        filtered_pairs = sorted(
            scored,
            key=lambda x: abs(x[1]["score"]),
            reverse=True
        )[:min(10, len(scored))]

    # Trier par valeur décroissante : likes + |score| + engagement + émotion forte
    def value_score(pair):
        c, sig = pair
        likes  = math.log1p(c.get('likes', 0))
        abscore = abs(sig["score"])
        eng    = 1.5 if sig.get("engagement") == "fort" else (0.8 if sig.get("engagement") == "moyen" else 0.3)
        emo    = 1.3 if sig.get("emotion") in STRONG_EMOTIONS else 1.0
        mkt    = 1.2 if sig.get("signal") in STRONG_SIGNALS else 1.0
        return likes + abscore * 100 * eng * emo * mkt

    filtered_pairs.sort(key=value_score, reverse=True)

    # Limiter à 40 commentaires max pour Layer 3 (performance)
    selected = filtered_pairs[:40]

    # Résultat filtré : (comment, score_float) pour compatibilité Layer 3
    filtered = [(c, sig["score"]) for c, sig in selected]

    # ── Agrégation Layer 1 — résumé des signaux détectés sur TOUS les commentaires pertinents
    all_pertinent = filtered_pairs  # tous les pertinents (pas seulement top 40)
    total_p = max(len(all_pertinent), 1)

    def pct(iterable, key, value):
        return round(sum(1 for _, s in iterable if s.get(key) == value) / total_p * 100)

    # Distribution intentions
    intentions = {}
    for _, sig in all_pertinent:
        k = sig.get("intention", "autre")
        intentions[k] = intentions.get(k, 0) + 1
    intentions_pct = {k: round(v / total_p * 100) for k, v in sorted(intentions.items(), key=lambda x: -x[1])[:5]}

    # Distribution émotions
    emotions_l1 = {}
    for _, sig in all_pertinent:
        k = sig.get("emotion", "autre")
        emotions_l1[k] = emotions_l1.get(k, 0) + 1
    emotions_pct = {k: round(v / total_p * 100) for k, v in sorted(emotions_l1.items(), key=lambda x: -x[1])[:5]}

    # Distribution signaux marketing
    signals = {}
    for _, sig in all_pertinent:
        k = sig.get("signal", "aucun")
        signals[k] = signals.get(k, 0) + 1
    signals_pct = {k: round(v / total_p * 100) for k, v in sorted(signals.items(), key=lambda x: -x[1]) if k != "aucun"}

    layer1_agg = {
        "total_pertinents":  total_p,
        "top40_selectionnes": len(selected),
        "intentions":         intentions_pct,
        "emotions_detectees": emotions_pct,
        "signaux_marketing":  signals_pct,
        "pct_favorable":      pct(all_pertinent, "position", "favorable"),
        "pct_defavorable":    pct(all_pertinent, "position", "defavorable"),
        "pct_engage_fort":    pct(all_pertinent, "engagement", "fort"),
    }

    return filtered, layer1_agg


# ─── PIPELINE PRINCIPAL ───────────────────────────────────────────────────────

def analyze_comments(comments, brain_context="", video_context="", title=""):

    nb_total = len(comments)
    _target  = title or video_context

    # ── NLP + Couche 1 en parallèle (les deux n'ont besoin que des commentaires bruts)
    print("[GABRIEL] NLP + Couche 1 en parallèle...")
    nlp_data = None
    with ThreadPoolExecutor(max_workers=2) as _pre:
        fut_nlp    = _pre.submit(run_nlp_pipeline, comments, _target) if _NLP_AVAILABLE else None
        fut_layer1 = _pre.submit(score_and_correlate, comments, _target)

        layer1 = fut_layer1.result()
        print("[GABRIEL] Couche 1 OK")

        if fut_nlp is not None:
            try:
                nlp_data = fut_nlp.result()
                print(f"[GABRIEL] NLP OK — diversity={nlp_data.get('semantic_diversity')} | "
                      f"clusters={len(nlp_data.get('cluster_summary', []))}")
            except Exception as e:
                print(f"[GABRIEL] NLP ERREUR (non bloquant) : {e}")

    # Si NLP disponible : fusionne les scores de relevance NLP avec les scores Haiku
    # Le CRS NLP (objectif) pondère le score Haiku (subjectif)
    if nlp_data and nlp_data.get("relevance_scores"):
        nlp_scores = nlp_data["relevance_scores"]
        for i, item in enumerate(layer1):
            if i < len(nlp_scores):
                nlp_rel = nlp_scores[i]
                haiku_score = item["score"]
                # Fusion : 60% Haiku (intention/émotion) + 40% CRS (proximité sémantique)
                # Signe du haiku préservé, magnitude ajustée par la relevance NLP
                sign = 1 if haiku_score >= 0 else -1
                magnitude = abs(haiku_score) * 0.60 + nlp_rel * 0.40
                item["score"] = round(sign * magnitude, 3)
                item["nlp_relevance"] = nlp_rel

    # Extraction des scores float pour les KPIs mathématiques
    scores = [item["score"] for item in layer1]

    # ── KPIs mathématiques (Python pur — zéro IA)
    kpis, distribution = calculate_math_kpis(comments, scores, title)

    # ── COUCHE 2 : Sélection des commentaires à forte valeur (Python pur)
    filtered, layer1_agg = _select_high_value(comments, layer1)
    nb_filtered = len(filtered)

    # ── LIVRABLES STATISTIQUES PURS (Python + NLP — zéro IA)
    stat_deliverables = {}
    if _NLP_AVAILABLE and nlp_data:
        print("[GABRIEL] Livrables statistiques purs...")
        try:
            stat_deliverables = compute_pure_statistical_deliverables(layer1, nlp_data, comments)
            print(f"[GABRIEL] Stat deliverables OK — {list(stat_deliverables.keys())}")
        except Exception as e:
            print(f"[GABRIEL] Stat deliverables ERREUR (non bloquant) : {e}")

    # ── COUCHE 3A : Analyse qualitative principale (Sonnet — profond)
    print("[GABRIEL] Couche 3 : analyse principale...")
    print(f"[GABRIEL] Layer1 agg — intentions: {layer1_agg.get('intentions')} | signaux: {layer1_agg.get('signaux_marketing')}")
    try:
        main_data = _analyze_main(
            filtered, brain_context, video_context,
            kpis, distribution, layer1_agg,
            nlp_data=nlp_data
        )
        print(f"[GABRIEL] 3A OK — clés : {list(main_data.keys())}")
    except Exception as e:
        print(f"[GABRIEL] 3A ERREUR : {e}")
        raise

    # Injection des descriptions Claude dans les KPIs calculés
    kpi_desc = main_data.pop("kpi_descriptions", {})
    for k, desc in kpi_desc.items():
        if k in kpis:
            kpis[k]["description"] = desc

    # ── ÉTAPES PARALLÈLES : Personas + Recommandations + Brief + Livrables IA
    print("[GABRIEL] Personas + recommandations + brief + livrables IA en parallèle...")
    personas = []
    recommandations = {}
    brief = {}
    livrables_ia = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        fut_personas = executor.submit(
            _analyze_personas, filtered, brain_context, main_data, kpis)
        fut_reco = executor.submit(
            _analyze_recommendations, filtered, brain_context, main_data, kpis)
        fut_brief = executor.submit(
            _generate_brief, main_data, kpis, brain_context, video_context)
        fut_livrables = executor.submit(
            _generate_livrables_ia,
            filtered, brain_context, video_context,
            main_data, nlp_data, stat_deliverables, layer1_agg
        )

        try:
            personas = fut_personas.result()
            print(f"[GABRIEL] Personas OK — {len(personas)}")
        except Exception as e:
            print(f"[GABRIEL] Personas ERREUR : {e}")

        try:
            recommandations = fut_reco.result()
            print(f"[GABRIEL] Reco OK — {list(recommandations.keys())}")
        except Exception as e:
            print(f"[GABRIEL] Reco ERREUR : {e}")

        try:
            brief = fut_brief.result()
            print(f"[GABRIEL] Brief OK")
        except Exception as e:
            print(f"[GABRIEL] Brief ERREUR : {e}")

        try:
            livrables_ia = fut_livrables.result()
            print(f"[GABRIEL] Livrables IA OK — {list(livrables_ia.keys())}")
        except Exception as e:
            print(f"[GABRIEL] Livrables IA ERREUR (non bloquant) : {e}")

    # ── Fusion livrables statistiques (purs + IA)
    livrables_statistiques = {**stat_deliverables, **livrables_ia}

    result = {**main_data}
    result['brief']                  = brief
    result['personas']               = personas
    result['recommandations']        = recommandations
    result['kpis']                   = kpis
    result['distribution']           = distribution
    result['livrables_statistiques'] = livrables_statistiques
    result['nlp_signals'] = {
        "relevance_distribution": (nlp_data or {}).get("relevance_distribution"),
        "semantic_diversity":     (nlp_data or {}).get("semantic_diversity"),
        "cluster_summary":        (nlp_data or {}).get("cluster_summary", []),
        "top_tfidf":              (nlp_data or {}).get("lexical", {}).get("top_tfidf", [])[:12],
        "top_bigrams":            (nlp_data or {}).get("lexical", {}).get("top_bigrams", [])[:8],
        "vocabulary_size":        (nlp_data or {}).get("lexical", {}).get("vocabulary_size"),
        "avg_tokens":             (nlp_data or {}).get("lexical", {}).get("avg_tokens_per_comment"),
    } if nlp_data else {}
    result['meta'] = {
        'total_commentaires':    nb_total,
        'commentaires_analyses': nb_filtered,
        'taux_filtrage':         round(nb_filtered / max(nb_total, 1) * 100, 1),
        'nlp_active':            _NLP_AVAILABLE and nlp_data is not None,
    }

    return result
