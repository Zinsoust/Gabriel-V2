# ─── Gabriel Memory — Mémoire stratégique fonctionnelle ──────────────────────
#
# Ce module stocke et exploite les cas passés pour améliorer les futures
# décisions du Stratège. La mémoire est scopée par user_id.
#
# Chaque cas stocke :
#   - fingerprint audience (signaux comparables)
#   - stratégie complète (décision, offre, prix, angle, message)
#   - contexte business
#   - feedback utilisateur (ajouté après)
#
# Similarité (score /100) :
#   - émotion dominante          : 20 pts
#   - keywords aspirations Jaccard: 25 pts
#   - keywords frustrations Jaccard: 20 pts
#   - keywords motivations Jaccard : 15 pts
#   - positionnement marché        : 10 pts
#   - objectif business            : 10 pts
#   Seuil d'activation : 35/100 (abaissé pour couvrir plus de cas)
#
# Pattern fiable : minimum 2 cas similaires avec feedback.

import os
import re
import json
import datetime

_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR    = os.path.join(_BASE_DIR, 'data')

SIMILARITY_THRESHOLD  = 35
MIN_CASES_FOR_PATTERN = 2
MAX_CASES             = 200

_STOPWORDS = {
    'avec', 'dans', 'pour', 'mais', 'plus', 'leur', 'cette', 'sont', 'comme',
    'être', 'avoir', 'faire', 'tout', 'bien', 'très', 'aussi', 'that', 'they',
    'have', 'this', 'with', 'their', 'from', 'more', 'when', 'want', 'just',
    'dont', 'only', 'what', 'feel', 'been', 'les', 'des', 'une', 'est', 'qui',
    'par', 'sur', 'pas', 'nous', 'vous', 'ils', 'elle', 'cela', 'peut', 'fait',
}


def _memory_file(user_id=None):
    """Fichier mémoire : par user si user_id connu, sinon fichier global."""
    if user_id and user_id != 'global':
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', str(user_id))
        return os.path.join(_DATA_DIR, f'memory_{safe}.json')
    return os.path.join(_DATA_DIR, 'gabriel_memory.json')


class GabrielMemory:

    def __init__(self, user_id=None):
        self.user_id = user_id
        self.cases   = self._load()

    # ── Persistance ──────────────────────────────────────────────────────────

    def _load(self):
        path = _memory_file(self.user_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_memory_file(self.user_id), 'w', encoding='utf-8') as f:
            json.dump(self.cases, f, ensure_ascii=False, indent=2)

    # ── Fingerprint & similarité ─────────────────────────────────────────────

    def _keywords(self, text):
        """Mots significatifs (≥4 chars, hors stopwords)."""
        words = re.findall(r"[a-zA-ZÀ-ÿÀ-ž]{4,}", (text or '').lower())
        return list({w for w in words if w not in _STOPWORDS})

    def _emotion_dominante(self, psycho_data):
        """Lit l'émotion dominante depuis les deux variantes du schema."""
        emotions = psycho_data.get('emotions', {})
        # Schema v2 : repartition[]
        rep = emotions.get('repartition') or []
        if rep and isinstance(rep, list) and rep[0].get('emotion'):
            return rep[0]['emotion'].lower().strip()
        # Schema v1 : champ 'dominante'
        dom = emotions.get('dominante', '')
        if dom:
            return dom.lower().strip()
        return ''

    def _fingerprint(self, psycho_data, business_context=None):
        aspirations = psycho_data.get('aspirations', {})
        psychologie = psycho_data.get('psychologie', {})
        marketing   = psycho_data.get('marketing', {})

        asp_parts = [
            str(aspirations.get('ce_qu_ils_veulent_devenir', '')),
            str(aspirations.get('transformation_visee', '')),
            str(aspirations.get('appel_interieur', '')),
        ]
        fru   = psychologie.get('frustrations', [])
        motiv = psychologie.get('motivations_profondes', [])

        fru_text   = ' '.join(fru   if isinstance(fru,   list) else [str(fru)])
        motiv_text = ' '.join(motiv if isinstance(motiv, list) else [str(motiv)])

        pos = marketing.get('positionnement_recommande', '')

        return {
            'emotion_dominante':   self._emotion_dominante(psycho_data),
            'asp_keywords':        self._keywords(' '.join(asp_parts)),
            'fru_keywords':        self._keywords(fru_text),
            'motiv_keywords':      self._keywords(motiv_text),
            'positionnement':      pos.lower().strip() if pos else '',
            'objectif_business':   ((business_context or {}).get('objectif_principal', '') or '').lower().strip(),
        }

    def _jaccard(self, a, b):
        sa, sb = set(a), set(b)
        if not sa and not sb:
            return 0.0
        inter = len(sa & sb)
        union = len(sa | sb)
        return inter / union if union else 0.0

    def _similarity(self, fp_a, fp_b):
        score = 0.0
        if fp_a['emotion_dominante'] and fp_a['emotion_dominante'] == fp_b['emotion_dominante']:
            score += 20
        score += self._jaccard(fp_a['asp_keywords'],   fp_b['asp_keywords'])   * 25
        score += self._jaccard(fp_a['fru_keywords'],   fp_b['fru_keywords'])   * 20
        score += self._jaccard(
            fp_a.get('motiv_keywords', []),
            fp_b.get('motiv_keywords', [])
        ) * 15
        if fp_a.get('positionnement') and fp_a['positionnement'] == fp_b.get('positionnement'):
            score += 10
        if fp_a['objectif_business'] and fp_a['objectif_business'] == fp_b.get('objectif_business'):
            score += 10
        return round(score)

    # ── API publique ─────────────────────────────────────────────────────────

    def add_case(self, analysis_id, psycho_data, strategie_data, business_context=None, user_id=None):
        """
        Stocker un nouveau cas après génération de la stratégie.
        strategie_data = dict plat {decision_centrale, offre_recommandee, pricing_logic, ...}
        """
        uid = user_id or self.user_id or 'global'

        # ── Audience ──────────────────────────────────────────────────────────
        psycho_ctx = psycho_data.get('psychologie', {})
        emotions   = psycho_data.get('emotions', {})
        aspirations= psycho_data.get('aspirations', {})
        marketing  = psycho_data.get('marketing', {})
        brief      = psycho_data.get('brief', {})
        kpis       = psycho_data.get('kpis', {})

        fru = psycho_ctx.get('frustrations', [])
        desirs = psycho_ctx.get('desirs_caches', [])
        motiv  = psycho_ctx.get('motivations_profondes', [])

        # ── Stratégie ─────────────────────────────────────────────────────────
        offre   = strategie_data.get('offre_recommandee', {})
        pricing = strategie_data.get('pricing_logic', {})
        opps    = strategie_data.get('opportunites_marche', []) or []
        recs    = strategie_data.get('recommandations_prioritaires', []) or []
        plan    = strategie_data.get('plan_90_jours', {})

        case = {
            'case_id':    analysis_id,
            'user_id':    uid,
            'date':       datetime.datetime.now().strftime('%Y-%m-%d'),
            'fingerprint': self._fingerprint(psycho_data, business_context),

            # Audience profonde
            'audience': {
                'emotion_dominante':     self._emotion_dominante(psycho_data),
                'espoir_decu':           emotions.get('espoir_decu', ''),
                'aspiration_nourrie':    emotions.get('aspiration_nourrie', ''),
                'aspirations_resume':    (
                    aspirations.get('ce_qu_ils_veulent_devenir')
                    or aspirations.get('transformation_visee')
                    or brief.get('synthese', '')
                ),
                'frustrations':          (fru   if isinstance(fru,   list) else [])[:4],
                'motivations':           (motiv if isinstance(motiv, list) else [])[:3],
                'desirs_caches':         (desirs if isinstance(desirs, list) else [])[:3],
                'insight_cle':           brief.get('insight_cle', ''),
                'positionnement':        marketing.get('positionnement_recommande', ''),
                'opportunites_cachees':  (marketing.get('opportunites_cachees') or [])[:3],
                'engagement_score':      (kpis.get('engagement') or {}).get('score', 0),
                'opportunite_score':     (kpis.get('opportunite') or {}).get('score', 0),
            },

            # Stratégie générée — champs plats pour mémoire
            'strategie': {
                'decision_centrale':      strategie_data.get('decision_centrale', ''),
                'objectif_reformule':     strategie_data.get('objectif_utilisateur_reformule', ''),
                'angle_positionnel':      strategie_data.get('angle_positionnel', ''),
                'message_central':        strategie_data.get('message_central', ''),
                'offre_nom':              offre.get('nom', ''),
                'offre_cible':            offre.get('cible_precise', ''),
                'offre_promesse':         offre.get('promesse', ''),
                'offre_format':           offre.get('format', ''),
                'prix_recommande':        offre.get('prix_recommande', ''),
                'positionnement_prix':    pricing.get('positionnement', ''),
                'niveau_douleur':         pricing.get('niveau_douleur', ''),
                'canaux_acquisition':     offre.get('canaux_acquisition', []),
                'actions_prioritaires':   [r.get('action', '') for r in recs[:3]],
                'phase_1_titre':          (plan.get('phase_1') or {}).get('titre', ''),
                'phase_1_objectifs':      (plan.get('phase_1') or {}).get('objectifs', []),
                'indicateurs_succes':     strategie_data.get('indicateurs_succes', [])[:4],
            },

            # Contexte business
            'contexte_business': {
                'objectif':  ((business_context or {}).get('objectif_principal', '')
                              or (business_context or {}).get('main_objectives', '')),
                'activite':  (business_context or {}).get('activite', ''),
                'cible':     (business_context or {}).get('cible', ''),
                'offre':     (business_context or {}).get('offre', ''),
            },

            'feedback': None,
        }

        # Dédupliquer puis insérer
        self.cases = [c for c in self.cases if c['case_id'] != analysis_id]
        self.cases.insert(0, case)
        self.cases = self.cases[:MAX_CASES]
        self._save()
        return case

    def record_feedback(self, analysis_id, feedback):
        for case in self.cases:
            if case['case_id'] == analysis_id:
                case['feedback'] = {
                    'pertinente':    feedback.get('pertinente', ''),
                    'va_appliquer':  feedback.get('va_appliquer', ''),
                    'resultat':      feedback.get('resultat', ''),
                    'comment':       feedback.get('comment', ''),
                    'date_feedback': datetime.datetime.now().strftime('%Y-%m-%d'),
                }
                self._save()
                return True
        return False

    def record_satisfaction(self, analysis_id, satisfaction):
        for case in self.cases:
            if case['case_id'] == analysis_id:
                case['satisfaction'] = satisfaction
                self._save()
                return True
        return False

    def record_performance(self, analysis_id, performance):
        for case in self.cases:
            if case['case_id'] == analysis_id:
                case['performance'] = performance
                self._save()
                return True
        return False

    # ── Recherche de similarité ───────────────────────────────────────────────

    def find_similar(self, psycho_data, business_context=None, n=6, user_id=None):
        """Retourne les n cas les plus similaires (score ≥ seuil)."""
        fp   = self._fingerprint(psycho_data, business_context)
        pool = self.cases

        # Si user_id fourni et qu'il y a assez de ses cas, on les priorise
        uid = user_id or self.user_id
        if uid and uid != 'global':
            user_cases = [c for c in pool if c.get('user_id') == uid]
            if len(user_cases) >= 2:
                pool = user_cases

        scored = []
        for case in pool:
            if 'fingerprint' not in case:
                continue
            score = self._similarity(fp, case['fingerprint'])
            if score >= SIMILARITY_THRESHOLD:
                scored.append({'case': case, 'score': score})

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:n]

    # ── Contexte mémoire pour le prompt Stratège ─────────────────────────────

    def get_memory_context(self, psycho_data, business_context=None, user_id=None):
        """
        Bloc de mémoire injecté dans le prompt du Stratège.
        Retourne '' si aucun cas similaire.
        """
        similar = self.find_similar(psycho_data, business_context, user_id=user_id)
        if not similar:
            return ''

        lines = [f"━━━ MÉMOIRE STRATÉGIQUE — {len(similar)} CAS SIMILAIRES ━━━"]

        positives, negatives = [], []
        for item in similar:
            c  = item['case']
            sc = item['score']
            s  = c.get('strategie', {})
            a  = c.get('audience', {})
            fb = c.get('feedback') or {}

            # Collecter les patterns
            if (fb.get('resultat') or '').lower() == 'positif':
                if s.get('decision_centrale'):
                    positives.append(s['decision_centrale'][:120])
            elif (fb.get('resultat') or '').lower() == 'negatif':
                if s.get('decision_centrale'):
                    negatives.append(s['decision_centrale'][:120])

            # Formater le cas
            fb_parts = []
            if fb.get('pertinente'):   fb_parts.append(f"pertinente:{fb['pertinente']}")
            if fb.get('va_appliquer'): fb_parts.append(f"appliquée:{fb['va_appliquer']}")
            if fb.get('resultat'):     fb_parts.append(f"résultat:{fb['resultat']}")
            fb_txt = ' · '.join(fb_parts) or 'feedback non encore reçu'

            case_lines = [
                f"\n▸ Cas [{c['date']}] — similarité {sc}/100",
                f"  Audience : {a.get('emotion_dominante','?')} · aspire à {(a.get('aspirations_resume') or '')[:80]}",
            ]
            if a.get('frustrations'):
                case_lines.append(f"  Frustrations : {', '.join(a['frustrations'][:3])}")
            if s.get('decision_centrale'):
                case_lines.append(f"  Décision choisie : {s['decision_centrale'][:150]}")
            if s.get('offre_nom'):
                case_lines.append(f"  Offre : {s['offre_nom']} — {s.get('offre_cible','')} — {s.get('prix_recommande','')}")
            if s.get('positionnement_prix'):
                case_lines.append(f"  Positionnement prix : {s['positionnement_prix']}")
            if s.get('canaux_acquisition'):
                case_lines.append(f"  Canaux : {', '.join(s['canaux_acquisition'][:3])}")
            case_lines.append(f"  Feedback : {fb_txt}")

            lines.extend(case_lines)

        # Patterns agrégés
        rated = [i for i in similar if (i['case'].get('feedback') or {}).get('resultat')]
        if len(rated) >= MIN_CASES_FOR_PATTERN:
            lines.append(f"\n── PATTERNS OBSERVÉS ({len(rated)} cas évalués) ──")
            if positives:
                lines.append(f"  ✓ Décisions à succès dans ce type d'audience :")
                for p in positives[:2]:
                    lines.append(f"    → {p}")
            if negatives:
                lines.append(f"  ✗ Décisions qui n'ont pas fonctionné :")
                for n_item in negatives[:2]:
                    lines.append(f"    ✗ {n_item}")
        elif len(rated) == 1:
            lines.append(f"\n  (1 cas évalué — pattern en cours de construction)")
        else:
            lines.append(f"\n  (Aucun feedback reçu encore — patterns à venir)")

        lines.append("\n⚠ Ces patterns informent mais ne dictent pas — adapte à la situation présente.")
        return '\n'.join(lines)

    def get_memory_context_for_chat(self, analysis_id, user_id=None):
        """
        Résumé de la mémoire pour enrichir le chatbot (cas de l'utilisateur + patterns).
        """
        uid = user_id or self.user_id
        if not uid:
            return ''

        user_cases = [c for c in self.cases if c.get('user_id') == uid and c['case_id'] != analysis_id]
        if not user_cases:
            return ''

        lines = [f"HISTORIQUE DE L'UTILISATEUR ({len(user_cases)} analyse(s) précédente(s)) :"]
        for c in user_cases[:4]:
            s  = c.get('strategie', {})
            fb = c.get('feedback') or {}
            res = fb.get('resultat', 'feedback manquant')
            lines.append(
                f"  [{c['date']}] {s.get('decision_centrale','—')[:100]} → {res}"
            )
        return '\n'.join(lines)

    # ── Résumé JSON léger pour le frontend ───────────────────────────────────

    def get_similar_summary(self, psycho_data, business_context=None, user_id=None):
        similar = self.find_similar(psycho_data, business_context, n=3, user_id=user_id)
        if not similar:
            return {'count': 0, 'cases': []}

        rated    = [i for i in similar if (i['case'].get('feedback') or {}).get('resultat')]
        positive = sum(1 for i in rated if (i['case']['feedback'] or {}).get('resultat', '').lower() == 'positif')
        pattern_ready = len(rated) >= MIN_CASES_FOR_PATTERN

        return {
            'count':         len(similar),
            'pattern_ready': pattern_ready,
            'positive_rate': round(positive / len(rated) * 100) if rated else None,
            'cases': [
                {
                    'date':     i['case']['date'],
                    'score':    i['score'],
                    'emotion':  i['case']['audience'].get('emotion_dominante', ''),
                    'decision': i['case'].get('strategie', {}).get('decision_centrale', '')[:100],
                    'offre':    i['case'].get('strategie', {}).get('offre_nom', ''),
                    'prix':     i['case'].get('strategie', {}).get('prix_recommande', ''),
                    'resultat': (i['case'].get('feedback') or {}).get('resultat', ''),
                }
                for i in similar
            ],
        }

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self, user_id=None):
        uid   = user_id or self.user_id
        pool  = [c for c in self.cases if not uid or c.get('user_id') == uid] if uid else self.cases
        rated = [c for c in pool if (c.get('feedback') or {}).get('resultat')]
        pos   = sum(1 for c in rated if (c['feedback'] or {}).get('resultat', '').lower() == 'positif')
        return {
            'total_cases':    len(pool),
            'rated_cases':    len(rated),
            'positive_cases': pos,
            'active':         len(pool) > 0,
        }
