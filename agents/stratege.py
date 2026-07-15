import os
import json
from agents.base import BaseAgent

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


# ── Extraction du résumé psychologique enrichi ───────────────────────────────

def _build_psycho_summary(psycho_data):
    emotions     = psycho_data.get('emotions', {})
    psychologie  = psycho_data.get('psychologie', {})
    aspirations  = psycho_data.get('aspirations', {})
    marketing    = psycho_data.get('marketing', {})
    brief        = psycho_data.get('brief', {})
    kpis         = psycho_data.get('kpis', {})
    distribution = psycho_data.get('distribution', {})
    personas     = psycho_data.get('personas', [])
    dashboard    = psycho_data.get('dashboard', {})
    interpretation = psycho_data.get('interpretation', {})

    emo_rep  = [e.get('emotion', '') for e in emotions.get('repartition', [])[:4]]
    motiv    = psychologie.get('motivations_profondes', [])[:4]
    frustr   = psychologie.get('frustrations', [])[:4]
    desirs   = psychologie.get('desirs_caches', [])[:4]
    peurs    = psychologie.get('peurs_implicites', [])[:3]
    objec    = psychologie.get('objections', [])[:3]
    croyances = psychologie.get('croyances_limitantes', [])[:2]
    hooks    = marketing.get('hooks_performants', [])[:3]
    opps     = marketing.get('opportunites_cachees', [])[:3]

    lines = [
        f"ÉMOTIONS DOMINANTES : {', '.join(emo_rep)}",
        f"ESPOIR DÉÇU : {emotions.get('espoir_decu', '')}",
        f"ASPIRATION NOURRIE : {emotions.get('aspiration_nourrie', '')}",
        f"MOTIVATIONS PROFONDES : {' | '.join(motiv)}",
        f"FRUSTRATIONS CLÉS : {' | '.join(frustr)}",
        f"PEURS IMPLICITES : {' | '.join(peurs)}",
        f"DÉSIRS CACHÉS : {' | '.join(desirs)}",
        f"OBJECTIONS FRÉQUENTES : {' | '.join(objec)}",
        f"CROYANCES LIMITANTES : {' | '.join(croyances)}",
        f"APPEL INTÉRIEUR : {aspirations.get('appel_interieur', '')}",
        f"CE QU'ILS VEULENT DEVENIR : {aspirations.get('ce_qu_ils_veulent_devenir', '')}",
        f"TRANSFORMATION VISÉE : {aspirations.get('transformation_visee', '')}",
        f"POSITIONNEMENT RECOMMANDÉ : {marketing.get('positionnement_recommande', '')}",
        f"HOOKS PERFORMANTS : {' | '.join(hooks)}",
        f"OPPORTUNITÉS CACHÉES : {' | '.join(opps)}",
        f"ENGAGEMENT : {kpis.get('engagement', {}).get('score', 0)}/100",
        f"OPPORTUNITÉ : {kpis.get('opportunite', {}).get('score', 0)}/100",
        f"POLARISATION : {kpis.get('polarisation', {}).get('score', 0)}/100",
        f"DISTRIBUTION : {distribution.get('positif', 0)}% positif / {distribution.get('negatif', 0)}% negatif",
    ]

    if dashboard:
        dominant_emotion = dashboard.get('dominant_emotion', '')
        dominant_stance  = dashboard.get('dominant_stance', '')
        if dominant_emotion:
            lines.append(f"ÉMOTION DASHBOARD DOMINANTE : {dominant_emotion}")
        if dominant_stance:
            lines.append(f"POSTURE AUDIENCE : {dominant_stance}")

    if brief:
        lines.append(f"SYNTHÈSE AUDIENCE : {brief.get('synthese', '')}")
        lines.append(f"INSIGHT CLÉ : {brief.get('insight_cle', '')}")
        lines.append(f"ACTION PRIORITAIRE PSYCHOLOGUE : {brief.get('action_prioritaire', '')}")

    # Interprétations RAG spécialisées
    interp_psy = interpretation.get('psychologique') or {}
    interp_soc = interpretation.get('socio_culturelle') or {}
    if interp_psy.get('main_insight'):
        lines.append(f"INSIGHT PSYCHOLOGIQUE PROFOND : {interp_psy['main_insight']}")
    if interp_soc.get('main_insight'):
        lines.append(f"INSIGHT SOCIO-CULTUREL : {interp_soc['main_insight']}")

    if personas:
        persona_summary = []
        for p in personas[:3]:
            if isinstance(p, dict):
                nom = p.get('nom', '')
                emo = p.get('emotion_dominante', '')
                fru = (p.get('frustrations', []) or [])[:1]
                if nom:
                    persona_summary.append(f"{nom} ({emo}) — {fru[0] if fru else ''}")
        if persona_summary:
            lines.append(f"PERSONAS IDENTIFIÉS : {' | '.join(persona_summary)}")

    return '\n'.join(l for l in lines if l.split(': ', 1)[-1].strip())


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_mistral(prompt, max_tokens=5000, label=""):
    from mistralai import Mistral
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY manquante — configurez-la dans les variables d'environnement Render.")
    # 270s < timeout Gunicorn (300s) : garantit une erreur propre plutôt qu'un
    # worker tué par Gunicorn si l'appel Mistral traîne. /strategize est synchrone.
    client = Mistral(api_key=key, timeout_ms=270_000)
    for attempt in range(2):
        try:
            response = client.chat.complete(
                model="mistral-large-latest",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            choice = response.choices[0]
            usage  = response.usage
            finish_reason = getattr(choice, 'finish_reason', None)
            if usage:
                print(f"[STRAT_TOKENS] label={label or '?'} prompt_tokens={usage.prompt_tokens} "
                      f"completion_tokens={usage.completion_tokens} max_tokens={max_tokens} finish_reason={finish_reason}")
            if finish_reason in ('length', 'model_length'):
                print(f"[STRAT_TRUNCATION] label={label or '?'} max_tokens={max_tokens} "
                      f"completion_tokens={getattr(usage, 'completion_tokens', '?')} — réponse coupée avant la fin")
            return response.choices[0].message.content.strip()
        except Exception as e:
            status = getattr(e, 'status_code', None) or getattr(e, 'http_status', None)
            if attempt == 0 and status in (429, 529):
                import time; time.sleep(4); continue
            raise


def _parse_json(text):
    import re
    from json_repair import repair_json
    start = text.find('{')
    end   = text.rfind('}') + 1
    if start == -1:
        raise ValueError("Pas de JSON dans la réponse du Stratège")
    raw = text[start:end] if end > start else text[start:]
    for fn in [
        lambda r: json.loads(r),
        lambda r: repair_json(r, return_objects=True),
    ]:
        try:
            result = fn(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    raise ValueError("Impossible de parser la réponse JSON du Stratège")


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
    prompt = f"""Tu es un STRATÈGE SENIOR CONTRARIEN, spécialiste de la revue critique de décisions marketing.
On te soumet une stratégie DÉJÀ PRODUITE par un autre analyste. Tu ne l'as pas écrite — ton rôle est de la challenger, pas de la valider par réflexe.

━━━ PSYCHOLOGIE RÉELLE DE L'AUDIENCE (résumé) ━━━
{psycho_summary[:1200]}

━━━ CONTEXTE BUSINESS ━━━
{brain_context[:500] or '(non renseigné)'}

━━━ STRATÉGIE À CHALLENGER ━━━
{summary}

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

    text = _call_mistral(prompt, max_tokens=1500, label="critique")
    result = _parse_json(text)
    expected = ["point_faible_principal", "angle_contrarien", "risque_non_couvert",
                "ajustement_recommande", "confidence_score_independant", "verdict"]
    missing = [k for k in expected if not result.get(k) and result.get(k) != 0]
    if missing:
        print(f"[STRATÈGE] Critique incomplète — clefs manquantes={missing} (JSON probablement tronqué puis réparé)")
    return result


# ── Agent ─────────────────────────────────────────────────────────────────────

class Stratege(BaseAgent):
    AGENT_ID   = "stratege"
    AGENT_NAME = "Le Stratège"

    def run(self, ctx):
        psycho_data    = ctx.get('psychologue')
        brain_context  = ctx.brain_context
        memory_context = ctx.memory_context
        title          = ctx.title

        psycho_summary = _build_psycho_summary(psycho_data)

        memory_section = ""
        if memory_context:
            memory_section = f"\nCAS SIMILAIRES PASSÉS :\n{memory_context}\n"

        title_section = f"\nCONTENU ANALYSÉ : {title}\n" if title else ""

        rag_section = _load_rag_rules(psycho_summary, brain_context)

        prompt = f"""{_STRATEGE_SYSTEM}

━━━ PROFIL BUSINESS DE L'UTILISATEUR ━━━
{brain_context or '(non renseigné — raisonner par hypothèse et lister les questions à clarifier)'}
{title_section}
━━━ RAPPORT DU PSYCHOLOGUE — PSYCHOLOGIE RÉELLE DE L'AUDIENCE ━━━
{psycho_summary}
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
      "expected_business_impact": "Impact business réaliste attendu en 30-90 jours",
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
      "recommended_price_range": "Fourchette de prix recommandée avec justification",
      "pricing_reasoning": "Raisonnement complet basé sur la douleur marché, valeur créée, profil audience",
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
      "prix_recommande": "prix ou fourchette",
      "justification_prix": "justification",
      "message_de_vente": "accroche principale",
      "canaux_acquisition": ["canal 1", "canal 2"],
      "objections_a_traiter": ["objection 1", "objection 2"]
    }},
    "pricing_logic_legacy": {{
      "valeur_percue": "valeur perçue par le marché",
      "niveau_douleur": "faible / moyen / fort / critique",
      "capacite_paiement": "budget estimé de la cible",
      "fourchette": "fourchette de prix",
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

RÈGLE FINALE : Si l'objectif utilisateur est flou, remplis questions_a_clarifier ET reasoning_trace.questions_to_clarify.
Si les données d'audience sont insuffisantes, marque les hypothèses avec '(à valider)' dans les champs concernés."""

        text = _call_mistral(prompt, max_tokens=8000, label="strategie")
        data = _parse_json(text)

        # Normaliser : certains LLMs peuvent nommer le champ pricing_logic_legacy → pricing_logic
        strat = data.get('strategie', {})
        if strat and 'pricing_logic_legacy' in strat and 'pricing_logic' not in strat:
            strat['pricing_logic'] = strat.pop('pricing_logic_legacy')
        # Fusionner les deux niveaux de pricing si les deux existent
        elif strat and 'pricing_logic_legacy' in strat and 'pricing_logic' in strat:
            # Garder pricing_logic (enrichi), supprimer l'alias legacy
            strat.pop('pricing_logic_legacy', None)

        # Relecture critique — 2e appel indépendant (non-bloquant)
        if strat:
            try:
                strat['critique_strategique'] = _critique_strategie(strat, psycho_summary, brain_context)
                print(f"[STRATÈGE] Critique OK — verdict={strat['critique_strategique'].get('verdict')}")
            except Exception as e:
                print(f"[STRATÈGE] Critique ERREUR (non bloquant) : {e}")

        ctx.add(self.AGENT_ID, data)
        return ctx
