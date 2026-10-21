import os
import json
from agents.base import BaseAgent
from core import llm_client as _llm
from core.ai_json import parse_ai_json

# ── Système prompt — 3 postures de raisonnement ──────────────────────────────

_STRATEGE_SYSTEM = """Tu es LE STRATÈGE de Gabriel — moteur de décision marketing immédiate basé sur la psychologie réelle de l'audience.

FORMULE CENTRALE (ne jamais inverser l'ordre) :
Psychologie audience → Problème réel → Valeur à créer → Offre → Format réseau social → Action immédiate → Monétisation

TU NE PARS JAMAIS DE L'OFFRE. Tu pars toujours de la psychologie de l'audience.

━━━ LES 3 POSTURES DE RAISONNEMENT ━━━

POSTURE 1 — Simplification radicale :
• Quel est le VRAI problème de l'audience ? (pas le symptôme)
• Quelle action crée le plus d'impact cette semaine ?
• Qu'est-ce qui est inutile et ralentit ?
• Quelle décision peut aider l'utilisateur à gagner de l'argent maintenant ?
→ Supprimer le flou. Aller vers l'action rentable.

POSTURE 2 — Produit et usage réel :
• Pourquoi l'utilisateur paierait pour cette recommandation ?
• Quel résultat immédiat peut-il appliquer dès aujourd'hui ?
• Quelle tâche Gabriel fait 10x mieux qu'un conseil générique ?
→ Créer une recommandation utile, simple et actionnable.

POSTURE 3 — Fiabilité et raisonnement clair :
• Sur quels signaux observés repose cette décision ?
• Quel est le niveau de confiance ? (certain / probable / hypothèse)
• Quelles hypothèses ne doivent pas être inventées ?
→ Ne pas halluciner. Justifier chaque décision par un signal réel.

━━━ PIPELINE DE RAISONNEMENT ━━━
1. Lire l'analyse psychologique → identifier le problème réel (pas le symptôme)
2. Identifier ce que l'audience désire vraiment
3. Identifier ce que l'audience craint le plus
4. Identifier ce qui bloque sa décision
5. Identifier la valeur principale à créer (clarté / preuve / structure / soulagement / statut / appartenance)
6. Lire le contexte business → adapter la valeur à la réalité du créateur
7. Définir l'offre la plus directe entre cette valeur et ce contexte
8. Définir le meilleur format réseau social pour cette audience précise
9. Définir l'action à faire cette semaine pour générer des revenus
10. Définir la logique de prix ancrée dans la douleur marché
11. Définir un plan 90 jours réaliste et exécutable

RÈGLE ABSOLUE :
Chaque recommandation doit suivre : Signal psychologique → Problème réel → Valeur → Offre → Action → Mesure
Zéro conseil vague. Zéro généralité. Chaque décision ancrée dans un signal d'audience réel.

RÈGLE DE LANGAGE (CRITIQUE) :
Tu reçois des données brutes issues d'une base de connaissances interne (signaux, patterns, codes internes).
Tu dois TOUJOURS les traduire en langage naturel, humain et professionnel destiné à l'utilisateur final.
NE JAMAIS inclure dans les textes visibles :
- Des noms de signaux entre guillemets comme signal : 'confusion' ou signal : 'Limites techniques non résolues'
- Des noms de patterns comme pattern [confused_audience] ou [frustrated_creator]
- Des formules techniques comme valeur = clarté ou type = urgence
- Des crochets, deux-points de décodage, identifiants internes, codes de chunks RAG

Exemple INTERDIT : "L'audience montre un signal : 'confusion technique' (pattern [confused_audience] : valeur = clarté)."
Exemple CORRECT : "L'audience cherche de la clarté face à la complexité technique — c'est l'urgence principale à adresser."

FORMAT OBLIGATOIRE : JSON valide uniquement, sans markdown."""


# ── Extraction du contexte psychologique — format JSON structuré ─────────────
#
# Remplace l'ancien _build_psycho_summary() (texte plat, tronqué à quelques
# lignes) par un vrai objet JSON envoyé tel quel au Stratège. Corrige au
# passage 3 clés mortes trouvées en auditant la connexion Psychologue→
# Stratège — aucune ne levait d'erreur, chacune renvoyait silencieusement une
# valeur vide, donc invisible sans vérifier explicitement :
#   - psychologie.objections        n'existe pas dans le schéma Psychologue
#                                    → les vraies clés sont marketing.objections_visibles
#                                      et marketing.objections_invisibles
#   - aspirations.transformation_visee n'existe pas
#                                    → remplacé par les 9 vrais champs du schéma aspirations
#   - marketing.opportunites_cachees n'existe pas
#                                    → les vraies clés sont opportunites_offre / opportunites_contenu

_PERSONA_FIELDS_FOR_STRATEGE = [
    'nom', 'poids', 'emotion_dominante_mesuree',
    'frustrations', 'peurs', 'desirs', 'aspirations',
    'objection_principale', 'ce_qui_le_ferait_acheter',
    'message_a_lui_dire', 'histoire_interieure',
]


class PsychoContextContractError(ValueError):
    """Le rapport Psychologue reçu ne correspond à aucun contrat connu."""


def _normalise_brief(brief: dict) -> tuple[dict, str]:
    """Adapte le contrat courant et les analyses historiques sans perte muette."""
    if not isinstance(brief, dict):
        raise PsychoContextContractError("Le champ brief du Psychologue doit être un objet.")

    current_keys = ("qui", "insight", "action")
    legacy_keys = ("synthese", "insight_cle", "action_prioritaire")
    if brief and not any(brief.get(key) for key in (*current_keys, *legacy_keys)):
        raise PsychoContextContractError(
            "Le brief du Psychologue ne contient ni le contrat courant "
            "(qui/insight/action), ni le contrat historique compatible."
        )

    has_current = any(brief.get(key) for key in current_keys)
    has_legacy = any(brief.get(key) for key in legacy_keys)
    source_schema = (
        "psychologue.brief.v1+v2" if has_current and has_legacy
        else "psychologue.brief.v2" if has_current
        else "psychologue.brief.v1" if has_legacy
        else "empty"
    )
    return {
        # Les adaptateurs Cross fournissent volontairement les deux formes :
        # leurs champs historiques sont enrichis (audiences + convergences +
        # divergences) et doivent donc primer sur les alias compacts.
        "synthese_audience": brief.get("synthese") or brief.get("qui", ""),
        "insight_cle": brief.get("insight_cle") or brief.get("insight", ""),
        "action_prioritaire": brief.get("action_prioritaire") or brief.get("action", ""),
    }, source_schema


def _sentiment_percentages(distribution: dict, dashboard: dict) -> tuple[float, float]:
    measured = dashboard.get("sentiment_distribution") or {}
    if measured:
        return measured.get("positive", 0), measured.get("negative", 0)
    if "positif" in distribution or "negatif" in distribution:
        return distribution.get("positif", 0), distribution.get("negatif", 0)
    total = max(int(distribution.get("total") or 0), 0)
    if not total:
        return 0, 0
    positive = int(distribution.get("positifs") or 0) + int(distribution.get("tres_positifs") or 0)
    negative = int(distribution.get("negatifs") or 0) + int(distribution.get("tres_negatifs") or 0)
    return round(positive / total * 100, 1), round(negative / total * 100, 1)


def _dominant_emotions(emotions: dict, dashboard: dict) -> list[str]:
    # Le dashboard est la mesure déterministe issue des commentaires. La
    # répartition narrative historique reste le repli pour les rapports v1.
    measured = dashboard.get("emotion_distribution") or {}
    if measured:
        return [
            name for name, value in sorted(
                measured.items(), key=lambda item: item[1], reverse=True
            )[:4] if value
        ]
    legacy = [
        item.get("emotion", "")
        for item in (emotions.get("repartition") or [])[:4]
        if isinstance(item, dict) and item.get("emotion")
    ]
    return legacy


def _build_psycho_context(psycho_data: dict) -> dict:
    """Construit le contexte psychologique structuré transmis au Stratège :
    les 3 personas prioritaires, les peurs/douleurs/émotions de l'audience,
    et la dimension aspirations complète (rêves, ce qu'ils veulent construire,
    comment ils veulent que le problème soit résolu)."""
    psychologie    = psycho_data.get('psychologie') or {}
    emotions       = psycho_data.get('emotions') or {}
    aspirations    = psycho_data.get('aspirations') or {}
    marketing      = psycho_data.get('marketing') or {}
    brief          = psycho_data.get('brief') or {}
    kpis           = psycho_data.get('kpis') or {}
    distribution   = psycho_data.get('distribution') or {}
    personas       = psycho_data.get('personas') or []
    dashboard      = psycho_data.get('dashboard') or {}
    interpretation = psycho_data.get('interpretation') or {}
    normalized_brief, source_schema = _normalise_brief(brief)
    positive_pct, negative_pct = _sentiment_percentages(distribution, dashboard)

    personas_prioritaires = []
    for p in personas[:3]:
        if isinstance(p, dict) and p.get('nom'):
            personas_prioritaires.append({
                k: p[k] for k in _PERSONA_FIELDS_FOR_STRATEGE if p.get(k)
            })

    context = {
        "personas_prioritaires": personas_prioritaires,
        "contract": {
            "name": "psychologue_to_stratege",
            "version": 2,
            "source_schema": source_schema,
        },
        "emotions_audience": {
            "dominantes": _dominant_emotions(emotions, dashboard),
            "espoir_decu": emotions.get('espoir_decu', ''),
            "aspiration_nourrie": emotions.get('aspiration_nourrie', ''),
        },
        "peurs_et_douleurs": {
            "frustrations":         psychologie.get('frustrations', [])[:4],
            "peurs_implicites":     psychologie.get('peurs_implicites', [])[:4],
            "croyances_limitantes": psychologie.get('croyances_limitantes', [])[:3],
            "objections_visibles":  marketing.get('objections_visibles', [])[:3],
            "objections_invisibles":marketing.get('objections_invisibles', [])[:3],
        },
        "aspirations": {
            "ce_qu_ils_veulent_devenir":     aspirations.get('ce_qu_ils_veulent_devenir', ''),
            "ce_qu_ils_veulent_construire":  aspirations.get('ce_qu_ils_veulent_construire', ''),
            "ce_qu_ils_veulent_transmettre": aspirations.get('ce_qu_ils_veulent_transmettre', ''),
            "ce_qu_ils_veulent_proteger":    aspirations.get('ce_qu_ils_veulent_proteger', ''),
            "ce_qu_ils_veulent_eviter":      aspirations.get('ce_qu_ils_veulent_eviter', ''),
            "ambitions":              aspirations.get('ambitions', [])[:3],
            "freins_aux_aspirations": aspirations.get('freins_aux_aspirations', [])[:3],
            "appel_interieur":            aspirations.get('appel_interieur', ''),
            "vision_de_leur_meilleur_moi": aspirations.get('vision_de_leur_meilleur_moi', ''),
        },
        "motivations_profondes": psychologie.get('motivations_profondes', [])[:4],
        "desirs_caches":         psychologie.get('desirs_caches', [])[:4],
        "insights_cles": {
            **normalized_brief,
            "insight_psychologique": (interpretation.get('psychologique') or {}).get('main_insight', ''),
            "insight_socio_culturel":(interpretation.get('socio_culturelle') or {}).get('main_insight', ''),
        },
        "signaux_marketing": {
            "hooks_performants":         marketing.get('hooks_performants', [])[:3],
            "opportunites_offre":        marketing.get('opportunites_offre', [])[:3],
            "opportunites_contenu":      marketing.get('opportunites_contenu', [])[:3],
            "positionnement_recommande": marketing.get('positionnement_recommande', ''),
        },
        "kpis": {
            "engagement":   (kpis.get('engagement') or {}).get('score', 0),
            "opportunite":  (kpis.get('opportunite') or {}).get('score', 0),
            "polarisation": (kpis.get('polarisation') or {}).get('score', 0),
        },
        "distribution": {
            "positif_pct": positive_pct,
            "negatif_pct": negative_pct,
        },
    }
    if dashboard:
        if dashboard.get('dominant_emotion'):
            context["emotions_audience"]["dominante_dashboard"] = dashboard['dominant_emotion']
        if dashboard.get('dominant_stance'):
            context["posture_audience"] = dashboard['dominant_stance']

    return context


def _psycho_query_text(psycho_context: dict) -> str:
    """Résumé compact en texte, dérivé du contexte JSON — sert uniquement de
    requête pour la recherche RAG et pour le prompt de relecture critique
    (qui n'ont pas besoin de la fidélité complète, juste de la substance)."""
    parts = []
    peurs = psycho_context.get('peurs_et_douleurs', {})
    asp   = psycho_context.get('aspirations', {})
    insights = psycho_context.get('insights_cles', {})
    if peurs.get('frustrations'):
        parts.append('Frustrations : ' + ' | '.join(peurs['frustrations']))
    if peurs.get('peurs_implicites'):
        parts.append('Peurs : ' + ' | '.join(peurs['peurs_implicites']))
    if psycho_context.get('desirs_caches'):
        parts.append('Désirs : ' + ' | '.join(psycho_context['desirs_caches']))
    if asp.get('ce_qu_ils_veulent_devenir'):
        parts.append('Aspiration : ' + asp['ce_qu_ils_veulent_devenir'])
    if insights.get('insight_cle'):
        parts.append('Insight clé : ' + insights['insight_cle'])
    personas = psycho_context.get('personas_prioritaires', [])
    if personas:
        noms = ', '.join(p.get('nom', '') for p in personas if p.get('nom'))
        if noms:
            parts.append('Personas : ' + noms)
    return '\n'.join(parts)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt, max_tokens=5000, label=""):
    """Appelle le LLM via la couche fournisseur unifiée (``core.llm_client``).

    Timeout à 270 s : sous le timeout Gunicorn (300 s), pour garantir une erreur
    propre plutôt qu'un worker tué — ``/strategize`` est synchrone.
    ``throttled=False`` pour la même raison : mettre un appel synchrone en file
    d'attente n'ajouterait que de la latence dans la requête de l'utilisateur.
    """
    return _llm.complete_text(
        prompt,
        tier="deep",
        max_tokens=max_tokens,
        timeout_ms=270_000,
        retry=_llm.RETRY_SIMPLE,
        label=label,
        throttled=False,
    )




def _parse_json(text):
    """Contrat historique : lève en cas d'échec. Implémentation dans core.ai_json."""
    return parse_ai_json(text, on_error="raise", label="stratege")


# ── RAG stratégique ───────────────────────────────────────────────────────────
# router_rules.json existait déjà (max_rules_method, max_principles_business,
# max_patterns_market, query_triggers, priority_sources) mais aucun code ne le
# lisait jamais — et core/rag.py l'exclut explicitement de l'indexation. La
# recherche était un seul search(top_k=6) générique mélangeant tout. Ici : un
# vrai routeur — 3 catégories ciblées via search_filtered, budgets tirés du
# fichier de config lui-même (il devient enfin utile), + détection des
# query_triggers présents dans l'audience/le contexte pour orienter la requête.

_RAG_CATEGORIES = {
    # groupe : (sources = stems de fichiers sans extension, clé de config pour le top_k)
    "méthode stratégique":     (["audience_to_offer_rules", "immediate_decision_rules",
                                  "social_format_rules", "pricing_logic"], "max_rules_method"),
    "principes business":      (["offer_design", "conversion"], "max_principles_business"),
    "schémas de marché":       (["winning_patterns", "failed_patterns"], "max_patterns_market"),
}

_router_rules_cache = None


def _load_router_rules() -> dict:
    global _router_rules_cache
    if _router_rules_cache is None:
        try:
            path = os.path.join(os.path.dirname(__file__), "stratege", "rag", "router_rules.json")
            with open(path, "r", encoding="utf-8") as f:
                _router_rules_cache = json.load(f)
        except Exception as e:
            print(f"[STRATÈGE] router_rules.json illisible, valeurs par défaut utilisées : {e}")
            _router_rules_cache = {}
    return _router_rules_cache


def _load_rag_rules(psycho_summary: str, brain_context: str) -> str:
    """Recherche RAG routée par catégorie (méthode / principes / marché),
    au lieu d'un seul top_k générique. Non-bloquant : si le RAG est
    indisponible, le prompt principal continue sans (dégradation gracieuse
    déjà en place ailleurs dans le pipeline)."""
    try:
        from core import rag as _rag
    except Exception as e:
        print(f"[STRATÈGE] RAG non disponible : {e}")
        return ""

    rules = _load_router_rules()
    base_text = f"{psycho_summary[:400]} {brain_context[:150]}".lower()
    triggers  = [t for t in rules.get("query_triggers", []) if t.lower() in base_text]
    trigger_hint = " ".join(triggers[:8])

    sections = []
    for label, (sources, limit_key) in _RAG_CATEGORIES.items():
        top_k = rules.get(limit_key, 4)
        query = f"{psycho_summary[:300]} {brain_context[:100]} {trigger_hint}".strip()
        try:
            results = _rag.search_filtered(query, "stratege", sources, top_k=top_k)
        except Exception as e:
            print(f"[STRATÈGE] RAG catégorie '{label}' échouée (non bloquant) : {e}")
            continue
        if results:
            print(f"[STRATÈGE_RAG] catégorie={label} sources={sources} top_k={top_k} trouvés={len(results)}")
            sections.append(f"── {label.upper()} ──\n" + _rag.format_context(results, max_chars=900))

    # Base conceptuelle générale (Porter, SWOT, positionnement, Océan Bleu…) —
    # pas liée à une catégorie d'action précise, cherchée une seule fois.
    try:
        general = _rag.search_filtered(
            f"{psycho_summary[:200]} {brain_context[:100]}",
            "stratege", ["decision_strategique", "strategie_marketing"], top_k=2,
        )
        if general:
            sections.append("── CADRES CONCEPTUELS ──\n" + _rag.format_context(general, max_chars=700))
    except Exception as e:
        print(f"[STRATÈGE] RAG cadres conceptuels échoué (non bloquant) : {e}")

    if not sections:
        return ""
    if triggers:
        print(f"[STRATÈGE_RAG] triggers détectés : {triggers}")
    return "\n━━━ BASE DE CONNAISSANCES STRATÉGIQUES (routée) ━━━\n" + "\n\n".join(sections) + "\n"


# ── Relecture critique — 2ᵉ appel indépendant ─────────────────────────────────
# Corrige un vrai angle mort de l'audit : sans ce 2ᵉ appel, le confidence_score
# affiché est auto-déclaré par le même modèle qui vient d'inventer la stratégie
# — aucun contrôle indépendant. Ici, un appel séparé, qui ne voit que la
# stratégie déjà produite (pas le prompt qui l'a générée), doit trouver la
# faille : point faible principal, angle contrarien, risque non couvert, et
# sa PROPRE ré-estimation de la confiance — indépendante de celle du 1er appel.

def _summarize_strategy_for_critique(strat: dict) -> str:
    """Résumé compact de la stratégie déjà produite — juste ce qu'il faut
    pour challenger, pas le prompt en entier (sinon le 2e appel ne fait que
    confirmer ce qu'il vient de re-générer)."""
    ed     = strat.get('executive_decision') or {}
    offre  = strat.get('offer_recommendation') or strat.get('offre_recommandee') or {}
    pricing = strat.get('pricing_logic') or {}
    parts = [
        f"Décision : {ed.get('one_sentence_decision', strat.get('decision_centrale', '—'))}",
        f"Pourquoi maintenant : {ed.get('why_now', '—')}",
        f"Impact attendu : {ed.get('expected_business_impact', '—')}",
        f"Confiance auto-déclarée par la stratégie : {ed.get('confidence_score', '—')}",
        f"Offre : {offre.get('recommended_offer_name') or offre.get('nom', '—')} — {offre.get('promise') or offre.get('promesse', '—')}",
        f"Prix : {pricing.get('recommended_price_range') or pricing.get('fourchette', '—')}",
        f"Message central : {strat.get('message_central', '—')}",
    ]
    risques = strat.get('risques') or []
    if risques:
        parts.append("Risques déjà identifiés : " + "; ".join(r.get('risque', '') for r in risques if isinstance(r, dict)))
    return "\n".join(parts)


def _critique_strategie(strat: dict, psycho_summary: str, brain_context: str) -> dict:
    """2e appel indépendant : challenge la stratégie déjà produite. Non-bloquant
    — si l'appel échoue, la stratégie reste utilisable sans relecture plutôt que
    de faire échouer tout le Stratège pour un problème de contrôle qualité."""
    summary = _summarize_strategy_for_critique(strat)
    from agents.strategy_guard import SOURCE_RULE as _source_rule
    prompt = f"""Tu es un STRATÈGE SENIOR CONTRARIEN, spécialiste de la revue critique de décisions marketing.
On te soumet une stratégie DÉJÀ PRODUITE par un autre analyste. Tu ne l'as pas écrite — ton rôle est de la challenger, pas de la valider par réflexe.

━━━ PSYCHOLOGIE RÉELLE DE L'AUDIENCE (résumé) ━━━
{psycho_summary[:1200]}

━━━ CONTEXTE BUSINESS ━━━
{brain_context[:500] or '(non renseigné)'}

━━━ STRATÉGIE À CHALLENGER ━━━
{summary}

{_source_rule}
Pour cette relecture : tes contre-propositions décrivent des STRUCTURES (offre d'entrée, offre principale, palier premium) sans les chiffrer, et n'avancent aucune statistique.

MISSION : trouve la faille. Ne complimente pas la stratégie — un stratège senior cherche toujours ce qui pourrait la faire échouer.

Réponds UNIQUEMENT avec ce JSON valide (sans markdown) :
{{
  "point_faible_principal": "Le point le plus fragile de cette stratégie — sois précis, pas générique",
  "angle_contrarien": "Ce qu'un stratège qui ferait le pari inverse recommanderait à la place, et pourquoi ça pourrait marcher",
  "risque_non_couvert": "Un risque business réel que la liste de risques actuelle ne couvre pas",
  "ajustement_recommande": "Le changement concret le plus utile à apporter à cette stratégie avant de l'exécuter",
  "confidence_score_independant": 0.0,
  "verdict": "solide" | "à ajuster" | "fragile"
}}

Le confidence_score_independant est TA propre estimation (0 à 1), indépendante de celle affichée dans la stratégie — ne la recopie pas, ré-évalue depuis zéro à partir des signaux d'audience et du contexte business ci-dessus."""

    from core.critic import critic
    from core.critiques import STRATEGY_CRITIQUE

    return critic.review(
        STRATEGY_CRITIQUE, prompt,
        call_llm=lambda p, max_tokens: _call_llm(p, max_tokens=max_tokens,
                                                 label="critique"),
        parse_json=_parse_json, max_tokens=1500,
    ).data


# ── Agent ─────────────────────────────────────────────────────────────────────

def _strategy_reasoning() -> str:
    """Raisonnement stratégique — voir skills/strategy.py.

    Le texte reste défini une seule fois dans _STRATEGE_SYSTEM ; le Skill le
    référence, ne le recopie pas.
    """
    from skills import registry as skill_registry
    return skill_registry.render('strategy.decision_reasoning', 'stratege').content


class Stratege(BaseAgent):
    AGENT_ID   = "stratege"
    AGENT_NAME = "Le Stratège"

    def run(self, ctx):
        psycho_data    = ctx.get('psychologue')
        brain_context  = ctx.brain_context
        memory_context = ctx.memory_context
        title          = ctx.title

        from tools import registry as tool_registry
        _adapted        = tool_registry.get('adaptation.psycho_to_strategy_context').run(
            psycho_data=psycho_data)
        psycho_context = _adapted['context']
        psycho_query   = _adapted['query_text']
        psycho_json    = json.dumps(psycho_context, ensure_ascii=False, indent=2)

        memory_section = ""
        if memory_context:
            # Les cas passés servent à retrouver des décisions, pas des prix : leurs montants ont
            # été produits par Gabriel, jamais fournis par l'utilisateur.
            from agents.strategy_guard import scrub_numbers
            memory_section = f"\nCAS SIMILAIRES PASSÉS :\n{scrub_numbers(memory_context)}\n"

        title_section = f"\nCONTENU ANALYSÉ : {title}\n" if title else ""

        rag_section = _load_rag_rules(psycho_query, brain_context)

        from agents.strategy_guard import SOURCE_RULE as _source_rule
        prompt = f"""{_strategy_reasoning()}

━━━ PROFIL BUSINESS DE L'UTILISATEUR ━━━
{brain_context or '(non renseigné — raisonner par hypothèse et lister les questions à clarifier)'}
{title_section}
━━━ RAPPORT DU PSYCHOLOGUE — PSYCHOLOGIE RÉELLE DE L'AUDIENCE (JSON) ━━━
{psycho_json}
{memory_section}{rag_section}
━━━ MISSION — DÉCISION MARKETING IMMÉDIATE ━━━

Question centrale à laquelle tu dois répondre :
"Quelle est la meilleure décision marketing à prendre MAINTENANT pour générer des revenus le plus rapidement possible, à partir de la psychologie réelle de cette audience ?"

RAPPELS :
1. Partir de la psychologie audience → problème réel → valeur → offre → format → action
2. Chaque recommandation : Signal → Lecture → Décision → Action → Mesure
3. L'offre découle de la valeur, pas du catalogue existant
4. L'action cette semaine doit être faisable ET générer les premiers signaux de revenus
5. Justifier chaque décision par un signal d'audience précis

Réponds UNIQUEMENT avec ce JSON valide (sans markdown, sans texte avant ou après) :

{{
  "strategie": {{
    "executive_decision": {{
      "one_sentence_decision": "La décision marketing la plus importante à prendre maintenant — en une phrase d'action",
      "what_to_do_this_week": "Action concrète et précise à réaliser dans les 7 prochains jours pour générer les premiers revenus",
      "why_now": "Pourquoi cette décision maintenant et pas dans 3 mois — ancré dans les signaux audience",
      "expected_business_impact": "Impact business attendu en 30-90 jours, en termes qualitatifs (aucun chiffre d'affaires ni pourcentage qui ne vienne pas du profil business)",
      "confidence_score": 0.8  // Score d'alignement stratégie ↔ audience : mesure à quel point la décision, l'offre et le message s'appuient sur les signaux psychologiques réellement détectés.
    }},
    "audience_psychology_used": {{
      "main_problem": "Le vrai problème de l'audience (cause racine, pas symptôme)",
      "main_desire": "Ce que l'audience désire vraiment (résultat final)",
      "main_fear": "La peur principale qui bloque la décision",
      "main_frustration": "La frustration la plus intense et récurrente",
      "main_objection": "L'objection principale qui empêche l'achat",
      "values_sought": ["valeur 1 que l'audience cherche dans une solution", "valeur 2", "valeur 3"],
      "decision_drivers": ["facteur 1 qui déclencherait l'achat", "facteur 2"]
    }},
    "value_to_create": {{
      "core_value": "La valeur principale à vendre (clarté / preuve / structure / soulagement / statut / appartenance)",
      "why_this_value_matters": "Pourquoi cette valeur spécifique correspond à cette audience — ancré dans les signaux",
      "what_the_audience_is_really_buying": "Ce que l'audience achète vraiment (pas le produit, la transformation)",
      "value_gap_in_current_business": "Ce qui manque actuellement dans le positionnement ou l'offre"
    }},
    "offer_recommendation": {{
      "recommended_offer_name": "Nom de l'offre recommandée",
      "offer_type": "Type d'offre (audit / diagnostic / formation / accompagnement / communauté / produit numérique...)",
      "promise": "La promesse principale — résultat concret et mesurable",
      "target_persona": "Le persona précis visé — pas 'tout le monde'",
      "deliverables": ["livrable 1", "livrable 2", "livrable 3"],
      "transformation": "De où → vers où ? État avant et état après",
      "why_this_offer_fits_the_psychology": "Pourquoi cette offre répond exactement à la psychologie détectée",
      "minimum_viable_offer": "Version minimale de l'offre lancable cette semaine sans infrastructure complexe",
      "risks": ["risque 1 de cette offre", "risque 2"]
    }},
    "social_media_decision": {{
      "best_platform": "La plateforme prioritaire pour atteindre cette audience précise",
      "best_content_format": "Format de contenu qui convertira le mieux cette audience",
      "main_content_angle": "L'angle principal — comment aborder le sujet pour captiver cette audience",
      "first_post_or_video_to_create": "Description précise du premier contenu à créer — titre, angle, structure",
      "posting_priority_this_week": ["contenu 1 à créer cette semaine", "contenu 2", "contenu 3"],
      "why_this_format_fits_the_audience": "Pourquoi ce format correspond à la psychologie et aux habitudes de cette audience"
    }},
    "pricing_logic": {{
      "recommended_price_range": "Logique de prix : positionnement (entrée / milieu / premium) et ancrage sur les offres et prix du profil business. Un montant en euros UNIQUEMENT s'il figure dans le profil business, sinon [montant à définir] et comment le fixer",
      "pricing_reasoning": "Raisonnement basé sur la douleur marché, la valeur créée, le profil audience — sans statistique ni montant inventés",
      "entry_offer_if_needed": "Offre d'entrée recommandée si l'audience est sceptique ou hésitante",
      "proof_needed_to_support_price": "Quel type de preuve est nécessaire pour soutenir ce prix",
      "comfort_level_for_audience": "Niveau de confort de l'audience avec ce niveau de prix (bas / acceptable / effort / élevé)"
    }},
    "immediate_monetization_plan": {{
      "next_24h_action": "Action précise à faire dans les prochaines 24h",
      "next_7_days_action": "Plan d'action sur les 7 prochains jours",
      "first_offer_to_test": "La première offre concrète à tester dès cette semaine",
      "first_call_to_action": "Le CTA exact à intégrer dans le prochain contenu",
      "metric_to_watch": "L'indicateur clé à surveiller pour valider que la stratégie fonctionne"
    }},
    "decision_centrale": "Reformulation de la décision principale — compatible avec l'ancienne structure",
    "objectif_utilisateur_reformule": "Reformulation de l'objectif utilisateur tel que compris",
    "raisonnement": "Raisonnement stratégique complet — pourquoi cette direction",
    "angle_positionnel": "Angle de positionnement unique basé sur les aspirations de l'audience",
    "message_central": "Le message que l'audience doit retenir — répond à leur appel intérieur",
    "opportunites_marche": [
      {{
        "signal": "signal détecté dans l'audience",
        "lecture_strategique": "ce que ce signal révèle",
        "recommandation": "décision recommandée",
        "action_concrete": "action à exécuter",
        "mesure_succes": "KPI de validation"
      }},
      {{
        "signal": "signal 2",
        "lecture_strategique": "lecture",
        "recommandation": "recommandation",
        "action_concrete": "action",
        "mesure_succes": "mesure"
      }},
      {{
        "signal": "signal 3",
        "lecture_strategique": "lecture",
        "recommandation": "recommandation",
        "action_concrete": "action",
        "mesure_succes": "mesure"
      }}
    ],
    "recommandations_prioritaires": [
      {{"action": "action prioritaire 1", "signal_source": "signal qui justifie", "impact": "impact attendu", "delai": "cette semaine"}},
      {{"action": "action 2", "signal_source": "signal", "impact": "impact", "delai": "ce mois"}},
      {{"action": "action 3", "signal_source": "signal", "impact": "impact", "delai": "ce mois"}},
      {{"action": "action 4", "signal_source": "signal", "impact": "impact", "delai": "dans 30-60 jours"}}
    ],
    "offre_recommandee": {{
      "nom": "nom de l'offre",
      "cible_precise": "segment exact",
      "probleme_traite": "problème central",
      "promesse": "promesse principale",
      "resultat_attendu": "résultat concret",
      "format": "format de livraison",
      "livrables": ["livrable 1", "livrable 2"],
      "prix_recommande": "montant du profil business, sinon [montant à définir]",
      "justification_prix": "justification qualitative, sans chiffre inventé",
      "message_de_vente": "accroche principale",
      "canaux_acquisition": ["canal 1", "canal 2"],
      "objections_a_traiter": ["objection 1", "objection 2"]
    }},
    "pricing_logic_legacy": {{
      "valeur_percue": "valeur perçue par le marché",
      "niveau_douleur": "faible / moyen / fort / critique",
      "capacite_paiement": "capacité de paiement en mots (limitée / moyenne / forte), sans budget chiffré",
      "fourchette": "fourchette du profil business, sinon [montant à définir]",
      "positionnement": "entrée / milieu / premium / ultra-premium",
      "justification": "raisonnement complet"
    }},
    "strategie_contenu": {{
      "format_prioritaire": "format de contenu prioritaire",
      "frequence": "cadence recommandée",
      "tonalite": "registre de communication",
      "sujets_a_eviter": ["sujet à éviter 1", "sujet 2"]
    }},
    "plan_90_jours": {{
      "phase_1": {{
        "titre": "Valider et lancer",
        "periode": "Jours 1-30",
        "objectifs": ["objectif mesurable 1", "objectif 2"],
        "taches": ["tâche concrète 1", "tâche 2", "tâche 3"],
        "livrables": ["livrable phase 1"],
        "kpis": ["KPI mesurable 1"],
        "decisions_cles": ["décision à prendre avant phase 2"]
      }},
      "phase_2": {{
        "titre": "Optimiser et convertir",
        "periode": "Jours 31-60",
        "objectifs": ["objectif 1", "objectif 2"],
        "taches": ["tâche 1", "tâche 2"],
        "livrables": ["livrable phase 2"],
        "kpis": ["KPI 1", "KPI 2"],
        "decisions_cles": ["décision clé fin phase 2"]
      }},
      "phase_3": {{
        "titre": "Scaler ce qui fonctionne",
        "periode": "Jours 61-90",
        "objectifs": ["objectif 1"],
        "taches": ["tâche 1", "tâche 2"],
        "livrables": ["livrable final"],
        "kpis": ["KPI final"],
        "decisions_cles": ["prochaine itération"]
      }}
    }},
    "risques": [
      {{"risque": "risque spécifique 1", "mitigation": "comment l'éviter"}},
      {{"risque": "risque 2", "mitigation": "mitigation"}},
      {{"risque": "risque 3", "mitigation": "mitigation"}}
    ],
    "indicateurs_succes": ["KPI 1 mesurable", "KPI 2", "KPI 3"],
    "reasoning_trace": {{
      "signals_used": ["signal audience qui a orienté la stratégie 1", "signal 2", "signal 3"],
      "strategic_patterns_used": ["pattern stratégique appliqué 1", "pattern 2"],
      "assumptions": ["hypothèse à valider 1 si données insuffisantes"],
      "questions_to_clarify": ["question à poser à l'utilisateur si contexte manquant"]
    }},
    "questions_a_clarifier": []
  }}
}}

{_source_rule}

RÈGLE FINALE : Si l'objectif utilisateur est flou, remplis questions_a_clarifier ET reasoning_trace.questions_to_clarify.
Si les données d'audience sont insuffisantes, marque les hypothèses avec '(à valider)' dans les champs concernés."""

        text = _call_llm(prompt, max_tokens=8000, label="strategie")
        data = _parse_json(text)

        # Normaliser : certains LLMs peuvent nommer le champ pricing_logic_legacy → pricing_logic
        strat = data.get('strategie', {})
        if strat and 'pricing_logic_legacy' in strat and 'pricing_logic' not in strat:
            strat['pricing_logic'] = strat.pop('pricing_logic_legacy')
        # Fusionner les deux niveaux de pricing si les deux existent
        elif strat and 'pricing_logic_legacy' in strat and 'pricing_logic' in strat:
            # Garder pricing_logic (enrichi), supprimer l'alias legacy
            strat.pop('pricing_logic_legacy', None)

        # Garde-fou : aucun montant ni pourcentage qui ne vienne des données réelles.
        from agents.strategy_guard import guard_strategy, sources_for
        _sources = sources_for(brain_context, psycho_json, title)

        def _rewrite(p):
            return _call_llm(p, max_tokens=4000, label="strategie_garde")

        retires = []
        if strat:
            strat, retires = guard_strategy(strat, _sources, _rewrite, _parse_json)
            data['strategie'] = strat

        # Relecture critique — 2e appel indépendant (non-bloquant)
        if strat:
            try:
                critique = _critique_strategie(strat, psycho_query, brain_context)
                critique, retires_critique = guard_strategy(critique, _sources, _rewrite, _parse_json)
                strat['critique_strategique'] = critique
                retires = sorted(set(retires) | set(retires_critique))
                print(f"[STRATÈGE] Critique OK — verdict={strat['critique_strategique'].get('verdict')}")
            except Exception as e:
                print(f"[STRATÈGE] Critique ERREUR (non bloquant) : {e}")
            if retires:
                strat['chiffres_retires'] = retires

        ctx.add(self.AGENT_ID, data)
        return ctx
