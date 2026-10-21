"""Dette de méthodologie — la part unifiable, et celle qui ne l'est pas.

La consigne « ne pas laisser fuiter les identifiants techniques » existait en
trois textes distincts dans le dépôt, dont deux copies strictement
identiques. Seules ces deux-là sont unifiées : le texte injecté ne bouge pas
d'un octet. Les deux autres sont laissées telles quelles, et ce fichier
mesure l'écart restant pour qu'il ne redevienne pas invisible.
"""

import hashlib
import pathlib
import re

import pytest

import skills
from core.analyzer import _NO_TECHNICAL_LEAKAGE, _no_technical_leakage


ANALYZER = pathlib.Path(__file__).resolve().parent.parent / 'core' / 'analyzer.py'
STRATEGE = pathlib.Path(__file__).resolve().parent.parent / 'agents' / 'stratege.py'


class TestUnificationSansChangementDeTexte:
    """La règle qui rendait cette unification sûre : les deux copies étaient
    strictement identiques. Une unification qui changerait le texte serait une
    décision produit, pas un nettoyage."""

    def test_le_skill_rend_exactement_la_constante(self):
        assert skills.registry.render(
            'writing.no_technical_leakage', 'gabriel').content == _NO_TECHNICAL_LEAKAGE

    def test_le_texte_fait_toujours_434_caracteres(self):
        """Taille relevée sur la version d'origine, avant unification. Elle
        change si quelqu'un retouche la consigne — ce qui doit rester un acte
        conscient."""
        assert len(_NO_TECHNICAL_LEAKAGE) == 434

    def test_la_consigne_porte_ses_trois_composants(self):
        """Interdiction, exemple interdit, exemple correct — c'est le contraste
        entre les deux exemples qui fait la méthode, pas la règle seule."""
        texte = _no_technical_leakage()
        assert 'NE JAMAIS' in texte
        assert 'INTERDIT' in texte
        assert 'CORRECT' in texte

    def test_lancienne_duplication_a_bien_disparu(self):
        """Le corps de la consigne ne doit plus apparaître littéralement deux
        fois dans l'analyzer : une seule source, deux interpolations."""
        source = ANALYZER.read_text(encoding='utf-8')
        signature = "NE JAMAIS les reproduire dans tes textes."
        assert source.count(signature) == 1
        assert source.count('{_no_technical_leakage()}') == 2


class TestDetteRestanteMesuree:
    """Deux autres formulations de la même règle subsistent. Elles ne sont pas
    corrigées ici — les unifier changerait le texte envoyé au modèle. Ce test
    fige leur nombre pour que la dette reste visible et chiffrée.
    """

    @staticmethod
    def _empreintes(chemin, lignes=5):
        """Empreintes des formulations trouvées, hors source unifiée.

        La constante `_NO_TECHNICAL_LEAKAGE` correspond elle-même au motif :
        l'inclure ferait compter la solution parmi les problèmes.
        """
        lignes_src = pathlib.Path(chemin).read_text(encoding='utf-8').splitlines()
        vues = set()
        for i, l in enumerate(lignes_src):
            if re.match(r'RÈGLE DE LANGAGE', l):
                bloc = '\n'.join(lignes_src[i:i + lignes])
                # La définition de la constante correspond au motif : elle
                # est la source unifiée, pas une formulation de plus. On la
                # repère par la ligne qui la déclare, pas par comparaison de
                # texte — la barre de continuation de la chaîne littérale
                # empêche l'égalité stricte.
                if i >= 1 and '_NO_TECHNICAL_LEAKAGE = ' in lignes_src[i - 1]:
                    continue
                vues.add(hashlib.md5(bloc.encode()).hexdigest())
        return vues

    def test_il_reste_exactement_deux_formulations_non_unifiees(self):
        restantes = self._empreintes(ANALYZER) | self._empreintes(STRATEGE)
        assert len(restantes) == 2, (
            f"{len(restantes)} formulations distinctes de la règle de langage — "
            "attendu 2 (analyse principale et Stratège). Si ce nombre baisse, "
            "quelqu'un a unifié un texte : vérifier que la sortie du modèle "
            "n'en souffre pas. S'il monte, une nouvelle variante est apparue.")

    def test_la_fiche_du_skill_declare_cette_dette(self):
        limitations = skills.registry.get('writing.no_technical_leakage').spec.limitations
        assert 'Stratège' in limitations


class TestPipelineReel:
    def test_les_deux_interpretations_recoivent_bien_la_consigne(self, monkeypatch):
        """Preuve de bout en bout : les deux prompts qui portaient chacun leur
        copie reçoivent maintenant la même source unique."""
        import core.analyzer as analyzer

        prompts = {}

        def _capture(prompt, max_tokens=1500, label='', fast=False):
            prompts[label] = prompt
            return '{"placeholder": true}'

        monkeypatch.setattr(analyzer, 'call_llm', _capture)
        monkeypatch.setattr(analyzer, '_NLP_AVAILABLE', False)

        analyzer.analyze_comments(
            [{'text': 'Merci beaucoup, très utile', 'likes': 8},
             {'text': 'Pas convaincu du tout', 'likes': 3}],
            title='Structurer une offre')

        for label in ('interp_psycho', 'interp_socio'):
            assert label in prompts, f"appel {label} non capturé"
            assert _NO_TECHNICAL_LEAKAGE in prompts[label], (
                f"le prompt « {label} » a perdu la consigne de langage")
