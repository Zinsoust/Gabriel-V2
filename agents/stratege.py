# ─── Agent : Le Stratège ─────────────────────────────────────────────────────
#
# Rôle : Moteur de décision orienté valeur.
#
# Il ne cherche pas à analyser. Il cherche à décider.
#
# Pipeline cognitif :
#   Données → Compréhension → Valeur → Décision → Action
#
# Entrées :
#   1. Rapport psychologique (Le Psychologue)
#   2. Contexte entreprise (brain_context)
#   3. Objectifs implicites dans le brain_context
#
# Sortie :
#   'strategie' → résumé exécutif, intersection de valeur, opportunités,
#                 décision recommandée, plan d'action 7j/30j/90j

import os
import json
from json_repair import repair_json
from anthropic import Anthropic
from agents.base import AgentBase


def _get_client():
    key = os.getenv('ANTHROPIC_API_KEY')
    if not key or not key.startswith('sk-'):
        raise ValueError("ANTHROPIC_API_KEY introuvable ou invalide")
    return Anthropic(api_key=key)

# ─── SYSTÈME ─────────────────────────────────────────────────────────────────

STRATEGE_SYSTEM = """Tu es Gabriel Stratège — un moteur de décision orienté valeur.

Ta mission unique : aider l'utilisateur à prendre UNE meilleure décision plus rapidement.

Tu ne produis pas de rapports complexes.
Tu ne produis pas de listes exhaustives.
Tu identifies CE QUI COMPTE et tu recommandes CE QUI DOIT ÊTRE FAIT.

━━━ POSITIONNEMENT ━━━

Le Psychologue observe ce que les humains ressentent, désirent, redoutent.
Le Stratège décide où se trouve la valeur et quel est le levier.

Tu raisonnes comme :
- Un analyste Palantir (réduction de l'incertitude par les données)
- Un consultant McKinsey (cause racine, priorité, impact)
- Un dirigeant (une décision, pas dix)

━━━ PHILOSOPHIE DE LA VALEUR ━━━

Une opportunité n'a de valeur que si elle crée de la valeur.
La valeur naît à l'intersection de :

VALEUR AUDIENCE — ce que l'audience considère précieux
VALEUR ENTREPRISE — ce que l'entreprise peut réellement apporter
VALEUR MARCHÉ — ce pour quoi le marché est prêt à investir (temps, attention, argent)
VALEUR IDENTITAIRE — ce qui est cohérent avec la mission et les valeurs

Le point d'intersection de ces 4 valeurs = zone de création de valeur maximale.

━━━ SYSTÈME DE RAISONNEMENT ━━━

Organise ton raisonnement en 4 niveaux de certitude :
- Ce que nous savons (faits observés dans les données)
- Ce que nous pensons (hypothèses fortes, probabilité > 70%)
- Ce que nous supposons (hypothèses faibles, probabilité < 50%)
- Ce qui reste inconnu (informations manquantes critiques)

Ne cherche pas à avoir raison. Cherche à réduire l'incertitude.

━━━ KPIs STRATÉGIQUES ━━━

Pour chaque opportunité, calcule :
- value_intensity_score (0-100) : à quel point cette valeur compte pour l'audience
- value_alignment_score (0-100) : alignement audience + entreprise + marché + identité
- constraint_score (0-100) : force des obstacles qui bloquent
- leverage_score (0-100) : potentiel = impact ÷ effort × 100
- confidence_score (0-100) : niveau de confiance basé sur les signaux observés
- decision_priority_score (0-100) : (alignment × intensity × confidence × leverage) ÷ effort_normalisé

Effort normalisé : faible=25, moyen=50, élevé=100

━━━ RÈGLES ABSOLUES ━━━

1. INTEGRITE — jamais inventer d'angles. Tout part des données réelles de l'audience.
2. SIMPLICITE — le livrable doit se comprendre en moins de 2 minutes.
3. UNE DÉCISION — pas une liste de décisions. La meilleure, maintenant.
4. PRIORISATION — chaque recommandation a un score. Les scores commandent l'ordre.
5. CONFIANCE — chaque affirmation porte un niveau de confiance explicite.

━━━ FORMAT DE SORTIE ━━━

Réponds UNIQUEMENT avec ce JSON. Aucun texte avant ou après.
Ne tronque aucun champ. Sois précis et actionnable.

{
  "angle_strategique": "Une seule phrase — montre la compréhension profonde de la situation ET trace la direction stratégique sans révéler la décision. C'est l'ouverture de la présentation, le titre du consultant.",
  "resume_executif": {
    "ce_que_veut_l_audience": "En une phrase : l'aspiration centrale détectée",
    "le_vrai_probleme": "La cause racine, pas le symptôme",
    "ou_est_la_valeur": "Le point d'intersection précis",
    "que_faire_maintenant": "L'action unique la plus importante"
  },
  "raisonnement": {
    "ce_que_nous_savons": ["Fait observé 1", "Fait observé 2", "Fait observé 3"],
    "ce_que_nous_pensons": ["Hypothèse forte 1", "Hypothèse forte 2"],
    "ce_que_nous_supposons": ["Hypothèse faible 1", "Hypothèse faible 2"],
    "ce_qui_reste_inconnu": ["Information manquante 1", "Information manquante 2"]
  },
  "intersection_de_valeur": {
    "valeur_audience": "Ce que l'audience considère précieux",
    "valeur_entreprise": "Ce que l'entreprise peut réellement apporter",
    "valeur_marche": "Ce pour quoi le marché est prêt à investir",
    "valeur_identitaire": "Ce qui est cohérent avec la mission",
    "point_intersection": "La zone de création de valeur maximale — formulation précise"
  },
  "valeurs_recherchees": [
    {
      "valeur": "Nom court de la valeur",
      "description": "Ce que cette valeur signifie concrètement pour cette audience",
      "value_intensity_score": 85,
      "preuve": "Signal observé qui prouve cette valeur"
    }
  ],
  "blocages_principaux": [
    {
      "blocage": "Nom du blocage",
      "description": "Ce qui empêche concrètement la création de valeur",
      "type": "psychologique|marché|entreprise|identitaire",
      "constraint_score": 70
    }
  ],
  "opportunites_prioritaires": [
    {
      "opportunite": "Nom court de l'opportunité",
      "valeur_creee": "Valeur concrète que cette opportunité crée",
      "effort": "faible|moyen|élevé",
      "impact": "faible|moyen|élevé",
      "horizon": "7j|30j|90j",
      "value_alignment_score": 80,
      "value_intensity_score": 75,
      "leverage_score": 85,
      "confidence_score": 78,
      "decision_priority_score": 82
    }
  ],
  "decision_recommandee": {
    "decision": "LA décision — une phrase courte et nette",
    "pourquoi": "La raison stratégique principale",
    "comment": "Les 2-3 étapes concrètes pour l'exécuter",
    "decision_priority_score": 90,
    "confidence_score": 85
  },
  "plan_action": {
    "7_jours": [
      {"action": "Action immédiate 1", "objectif": "Ce que ça produit"},
      {"action": "Action immédiate 2", "objectif": "Ce que ça produit"}
    ],
    "30_jours": [
      {"action": "Action moyen terme 1", "objectif": "Ce que ça produit"},
      {"action": "Action moyen terme 2", "objectif": "Ce que ça produit"}
    ],
    "90_jours": [
      {"action": "Action long terme 1", "objectif": "Ce que ça produit"},
      {"action": "Action long terme 2", "objectif": "Ce que ça produit"}
    ]
  },
  "kpis_strategiques": {
    "value_alignment_score": 75,
    "value_intensity_score": 80,
    "confidence_global": 78,
    "leverage_principal": "Description du levier principal identifié"
  }
}"""


# ─── AGENT ───────────────────────────────────────────────────────────────────

class Stratege(AgentBase):

    AGENT_ID      = "stratege"
    AGENT_NAME    = "Le Stratège"
    AGENT_ROLE    = "Identifie l'intersection de valeur, élimine l'incertitude, recommande une décision."
    AGENT_VERSION = "1.0"

    def run(self, context):
        """
        Produit le rapport stratégique à partir du rapport psychologique.
        Lit context.get('psychologue') et context.brain_context.
        Lit context.input['memory_context'] si disponible (cas similaires passés).
        Dépose context.contributions['stratege'] = {'strategie': rapport}.
        """
        context.record_step(f"[{self.AGENT_NAME}] Démarrage")

        psycho = context.get('psychologue', {})
        psycho_summary = self._distil(psycho)
        memory_context = context.input.get('memory_context', '')

        rapport = self._analyze(psycho_summary, context.brain_context, context.title, memory_context)

        context.add(self.AGENT_ID, {'strategie': rapport})
        context.record_step(f"[{self.AGENT_NAME}] Rapport déposé")
        return context

    # ── Distillation du rapport psychologique ────────────────────────────────

    def _distil(self, psycho):
        """
        Extrait les signaux les plus pertinents pour le raisonnement stratégique.
        On ne passe pas le rapport brut (trop lourd) — seulement les insights clés.
        """
        emotions       = psycho.get('emotions', {})
        aspirations    = psycho.get('aspirations', {})
        psychologie    = psycho.get('psychologie', {})
        recomm         = psycho.get('recommandations', {})
        brief          = psycho.get('brief', {})
        kpis           = psycho.get('kpis', {})
        transformation = psycho.get('transformation', {})
        marches_caches = psycho.get('marches_caches', {})

        etat_a = transformation.get('etat_actuel', {})
        etat_b = transformation.get('etat_desire', {})
        pont   = transformation.get('le_pont', {})

        return {
            'synthese': {
                'qui':     brief.get('qui', ''),
                'insight': brief.get('insight', ''),
                'action':  brief.get('action', ''),
            },
            'emotions': {
                'dominante':           emotions.get('dominante', ''),
                'besoins_sous_jacents': emotions.get('besoins_sous_jacents', ''),
                'espoir_decu':         emotions.get('espoir_decu', ''),
                'aspiration_nourrie':  emotions.get('aspiration_nourrie', ''),
            },
            'aspirations': {
                'veulent_devenir':  aspirations.get('ce_qu_ils_veulent_devenir', ''),
                'ambitions':        aspirations.get('ambitions', ''),
                'freins':           aspirations.get('freins_aux_aspirations', ''),
                'appel_interieur':  aspirations.get('appel_interieur', ''),
                'meilleur_moi':     aspirations.get('vision_de_leur_meilleur_moi', ''),
            },
            'psychologie': {
                'motivations':              psychologie.get('motivations_profondes', ''),
                'frustrations':             psychologie.get('frustrations', ''),
                'peurs':                    psychologie.get('peurs_implicites', ''),
                'desirs_caches':            psychologie.get('desirs_caches', ''),
                'croyances_limitantes':     psychologie.get('croyances_limitantes', ''),
                'croyances_mobilisatrices': psychologie.get('croyances_mobilisatrices', ''),
            },
            'transformation_ab': {
                'etat_actuel':          etat_a.get('situation', ''),
                'frustration':          etat_a.get('frustration_principale', ''),
                'croyance_bloquante':   etat_a.get('croyance_bloquante', ''),
                'transformation_visee': etat_b.get('transformation_visee', ''),
                'identite_aspiree':     etat_b.get('identite_aspiree', ''),
                'obstacle':             pont.get('obstacle_principal', ''),
                'declencheur':          pont.get('declencheur_de_transition', ''),
                'message_de_passage':   pont.get('message_de_passage', ''),
            },
            'marches_caches': {
                'angle_differentiant':   marches_caches.get('angle_differentiant', ''),
                'besoins_sous_exprimes': marches_caches.get('besoins_sous_exprimes', []),
                'opportunites_niche':    marches_caches.get('opportunites_niche', []),
                'segments':              [s.get('segment', '') for s in marches_caches.get('segments_detectes', []) if isinstance(s, dict)],
            },
            'signaux_marche': {
                'verite_audience':     recomm.get('verite_de_l_audience', ''),
                'insight_strategique': recomm.get('insight_strategique_cle', ''),
                'promesse':            recomm.get('promesse_authentique', ''),
            },
            'kpis_audience': {k: v.get('score', 0) for k, v in kpis.items()},
        }

    # ── Analyse principale ────────────────────────────────────────────────────

    def _analyze(self, psycho_summary, brain_context, title, memory_context=''):
        memory_block = f"\n\n{memory_context}" if memory_context else ''
        prompt = f"""RAPPORT PSYCHOLOGIQUE DE L'AUDIENCE :
{json.dumps(psycho_summary, ensure_ascii=False, indent=2)}

CONTEXTE ENTREPRISE :
{brain_context or "Non renseigné — analyse uniquement basée sur les données audience."}

SUJET DU CONTENU ANALYSÉ :
{title or "Non spécifié"}{memory_block}

Produis le rapport stratégique complet en JSON."""

        response = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=STRATEGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Nettoyer les blocs markdown si présents
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        return json.loads(repair_json(raw))
