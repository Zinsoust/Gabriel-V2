"""Registre des savoir-faire de Gabriel.

Pendant du registre d'outils, pour la couche méthodologique : le Core doit
pouvoir demander « que sait faire Gabriel en matière d'écriture ? » et obtenir
une réponse vérifiable, plutôt que de fouiller des dictionnaires privés
disséminés dans les agents.
"""

from typing import Dict, Optional, Tuple

from skills.base import Skill, SkillError, SkillFragment


class SkillNotFound(SkillError, KeyError):
    """Aucun skill sous cet identifiant."""


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> Skill:
        sid = skill.spec.id
        if sid in self._skills:
            raise ValueError(
                f"Skill « {sid} » déjà enregistré : deux méthodologies sous un "
                f"même identifiant se masqueraient silencieusement.")
        self._skills[sid] = skill
        return skill

    def get(self, skill_id: str) -> Skill:
        try:
            return self._skills[skill_id]
        except KeyError:
            connus = ', '.join(sorted(self._skills)) or '(aucun)'
            raise SkillNotFound(
                f"Skill inconnu : « {skill_id} ». Skills disponibles : {connus}."
            ) from None

    def render(self, skill_id: str, requested: str) -> SkillFragment:
        """Raccourci : consulter un skill et obtenir le fragment à injecter."""
        return self.get(skill_id).render(requested)

    def all(self) -> Tuple[Skill, ...]:
        return tuple(self._skills[k] for k in sorted(self._skills))

    def by_domain(self, domain: str) -> Tuple[Skill, ...]:
        return tuple(s for s in self.all() if s.spec.domain == domain)

    def domains(self) -> Tuple[str, ...]:
        return tuple(sorted({s.spec.domain for s in self.all()}))

    def describe(self, domain: Optional[str] = None) -> list:
        source = self.by_domain(domain) if domain else self.all()
        return [s.describe() for s in source]

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def __len__(self) -> int:
        return len(self._skills)


registry = SkillRegistry()
