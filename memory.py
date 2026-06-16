# ─── Gabriel Memory ──────────────────────────────────────────────────────────
#
# Mémoire des cas passés. Gabriel mémorise pour mieux décider, pas pour raconter.
#
# Chaque cas stocke :
#   - fingerprint audience (signaux clés pour la comparaison)
#   - décision recommandée + scores
#   - contexte business
#   - feedback utilisateur (ajouté après)
#
# Logique de similarité :
#   - émotion dominante (30 pts)
#   - keywords aspirations / Jaccard (35 pts)
#   - keywords frustrations / Jaccard (25 pts)
#   - objectif business (10 pts)
#   Seuil d'activation : 45/100
#
# Pattern fiable : minimum 3 cas similaires avec feedback renseigné.

import os
import re
import json
import datetime

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_MEMORY_FILE = os.path.join(_BASE_DIR, 'gabriel_memory.json')

SIMILARITY_THRESHOLD  = 45   # score min pour considérer deux cas similaires
MIN_CASES_FOR_PATTERN = 3    # cas évalués minimum avant d'extraire un pattern
MAX_CASES             = 100  # taille max de la mémoire

_STOPWORDS = {
    'avec', 'dans', 'pour', 'mais', 'plus', 'leur', 'cette', 'sont', 'comme',
    'être', 'avoir', 'faire', 'tout', 'bien', 'très', 'aussi', 'that', 'they',
    'have', 'this', 'with', 'their', 'from', 'more', 'when', 'want', 'just',
    'dont', 'only', 'what', 'feel', 'they', 'been',
}


class GabrielMemory:

    def __init__(self):
        self.cases = self._load()

    # ── Persistance ──────────────────────────────────────────────────────────

    def _load(self):
        if os.path.exists(_MEMORY_FILE):
            try:
                with open(_MEMORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        with open(_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.cases, f, ensure_ascii=False, indent=2)

    # ── Fingerprint & similarité ─────────────────────────────────────────────

    def _keywords(self, text):
        """Mots significatifs (≥4 chars, hors stopwords)."""
        words = re.findall(r'[a-zA-ZÀ-ÿ]{4,}', (text or '').lower())
        return list({w for w in words if w not in _STOPWORDS})

    def _fingerprint(self, psycho_data, business_context=None):
        emotions    = psycho_data.get('emotions', {})
        aspirations = psycho_data.get('aspirations', {})
        psychologie = psycho_data.get('psychologie', {})

        asp_parts = [
            str(aspirations.get('ce_qu_ils_veulent_devenir', '')),
            str(aspirations.get('ambitions', '')),
        ]
        freins = aspirations.get('freins_aux_aspirations', [])
        if isinstance(freins, list):
            asp_parts += freins
        asp_text = ' '.join(asp_parts)

        fru = psychologie.get('frustrations', [])
        fru_text = ' '.join(fru if isinstance(fru, list) else [str(fru)])

        return {
            'emotion_dominante':  emotions.get('dominante', '').lower().strip(),
            'asp_keywords':       self._keywords(asp_text),
            'fru_keywords':       self._keywords(fru_text),
            'objectif_business':  (business_context or {}).get('objectif_principal', ''),
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
            score += 30
        score += self._jaccard(fp_a['asp_keywords'], fp_b['asp_keywords']) * 35
        score += self._jaccard(fp_a['fru_keywords'], fp_b['fru_keywords']) * 25
        if fp_a['objectif_business'] and fp_a['objectif_business'] == fp_b['objectif_business']:
            score += 10
        return round(score)

    # ── API publique ─────────────────────────────────────────────────────────

    def add_case(self, analysis_id, psycho_data, strategie_data, business_context=None):
        """Stocker un nouveau cas après génération de la stratégie."""
        dec = strategie_data.get('decision_recommandee', {})
        fru = psycho_data.get('psychologie', {}).get('frustrations', [])

        case = {
            'case_id':   analysis_id,
            'date':      datetime.datetime.now().strftime('%Y-%m-%d'),
            'fingerprint': self._fingerprint(psycho_data, business_context),
            'audience': {
                'emotion_dominante':    psycho_data.get('emotions', {}).get('dominante', ''),
                'aspirations_resume':   psycho_data.get('aspirations', {}).get('ce_qu_ils_veulent_devenir', ''),
                'frustrations':         (fru if isinstance(fru, list) else [])[:3],
                'transformation_visee': psycho_data.get('transformation', {}).get('etat_desire', {}).get('transformation_visee', ''),
            },
            'decision': {
                'recommandation':          dec.get('decision', ''),
                'pourquoi':                dec.get('pourquoi', ''),
                'confidence_score':        dec.get('confidence_score', 0),
                'decision_priority_score': dec.get('decision_priority_score', 0),
            },
            'contexte_business': {
                'objectif':  (business_context or {}).get('objectif_principal', ''),
                'activite':  (business_context or {}).get('activite', ''),
            },
            'feedback': None,
        }

        # Dédupliquer par case_id
        self.cases = [c for c in self.cases if c['case_id'] != analysis_id]
        self.cases.insert(0, case)
        self.cases = self.cases[:MAX_CASES]
        self._save()

    def record_feedback(self, analysis_id, feedback):
        """Enregistrer le feedback utilisateur (pertinente, va_appliquer, resultat)."""
        for case in self.cases:
            if case['case_id'] == analysis_id:
                case['feedback'] = {
                    'pertinente':    feedback.get('pertinente', ''),
                    'va_appliquer':  feedback.get('va_appliquer', ''),
                    'resultat':      feedback.get('resultat', ''),
                    'date_feedback': datetime.datetime.now().strftime('%Y-%m-%d'),
                }
                self._save()
                return True
        return False

    def find_similar(self, psycho_data, business_context=None, n=5):
        """Retourner les n cas les plus similaires (score ≥ seuil)."""
        fp = self._fingerprint(psycho_data, business_context)
        scored = []
        for case in self.cases:
            if 'fingerprint' not in case:
                continue
            score = self._similarity(fp, case['fingerprint'])
            if score >= SIMILARITY_THRESHOLD:
                scored.append({'case': case, 'score': score})
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:n]

    def get_memory_context(self, psycho_data, business_context=None):
        """
        Texte formaté injecté dans le prompt du Stratège.
        Retourne '' si aucun cas similaire trouvé.
        """
        similar = self.find_similar(psycho_data, business_context)
        if not similar:
            return ''

        lines = [f"━━━ MÉMOIRE — {len(similar)} CAS SIMILAIRES ━━━\n"]

        positive, negative = [], []

        for item in similar:
            c    = item['case']
            sc   = item['score']
            dec  = c['decision'].get('recommandation', '')[:120]
            emo  = c['audience'].get('emotion_dominante', '?')
            asp  = c['audience'].get('aspirations_resume', '')[:80]
            fb   = c.get('feedback') or {}

            if fb.get('resultat') == 'positif':
                positive.append(dec)
            elif fb.get('resultat') == 'negatif':
                negative.append(dec)

            fb_txt = ''
            if fb:
                parts = []
                if fb.get('pertinente'):   parts.append(f"pertinente:{fb['pertinente']}")
                if fb.get('va_appliquer'): parts.append(f"appliquée:{fb['va_appliquer']}")
                if fb.get('resultat'):     parts.append(f"résultat:{fb['resultat']}")
                fb_txt = ' · '.join(parts)

            lines.append(
                f"• [{c['date']}] similarité {sc}/100\n"
                f"  Audience : {emo}, aspire à {asp}\n"
                f"  Décision : {dec}\n"
                f"  Feedback : {fb_txt or 'non renseigné'}"
            )

        # Pattern si assez de cas évalués
        rated = [i for i in similar if (i['case'].get('feedback') or {}).get('resultat')]
        if len(rated) >= MIN_CASES_FOR_PATTERN:
            lines.append(f"\nPATTERNS ({len(rated)} cas évalués) :")
            if positive:
                lines.append(f"  ✓ Décisions à résultat POSITIF dans ce contexte : {' | '.join(positive[:2])}")
            if negative:
                lines.append(f"  ✗ Décisions à résultat NÉGATIF dans ce contexte : {' | '.join(negative[:2])}")
        elif len(rated) > 0:
            lines.append(f"\nPattern non encore fiable ({len(rated)}/{MIN_CASES_FOR_PATTERN} cas évalués requis).")

        lines.append("\nNote : ces patterns sont des signaux, pas des règles. Adapte à la situation présente.")
        return '\n'.join(lines)

    def get_similar_summary(self, psycho_data, business_context=None):
        """
        Résumé JSON léger pour le frontend (badge + aperçu des cas).
        """
        similar = self.find_similar(psycho_data, business_context, n=3)
        if not similar:
            return {'count': 0, 'cases': []}

        rated = [i for i in similar if (i['case'].get('feedback') or {}).get('resultat')]
        positive = sum(1 for i in rated if i['case']['feedback']['resultat'] == 'positif')
        pattern_ready = len(rated) >= MIN_CASES_FOR_PATTERN

        return {
            'count':         len(similar),
            'pattern_ready': pattern_ready,
            'positive_rate': round(positive / len(rated) * 100) if rated else None,
            'cases': [
                {
                    'date':        i['case']['date'],
                    'score':       i['score'],
                    'emotion':     i['case']['audience'].get('emotion_dominante', ''),
                    'decision':    i['case']['decision'].get('recommandation', '')[:100],
                    'resultat':    (i['case'].get('feedback') or {}).get('resultat', ''),
                }
                for i in similar
            ],
        }
