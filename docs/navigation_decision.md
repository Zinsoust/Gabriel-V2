# Navigation Gabriel — décision actée (2026-07-09)

Cette page existe parce que la navigation a changé de sens plusieurs fois dans la même
semaine (barre latérale simplifiée puis restaurée, génération ajoutée puis retirée de la
page Dossier). Ce document fige la décision actuelle pour éviter de refaire le même
débat à chaque session. À modifier seulement après un vrai retour d'usage, pas sur
une intuition ponctuelle.

## La règle

**Un dossier est le passage obligé pour accéder aux agents.**

- Sans dossier actif en session : `/psychologue`, `/stratege`, `/createur`,
  `/mes-analyses` et `/mes-strategies` redirigent vers `/dossiers`
  (voir `_requires_folder` dans `app.py`).
- Un dossier devient actif dès qu'on l'ouvre (`/dossiers/<id>`) ou qu'on arrive sur une
  page agent avec `?folder_id=...` dans l'URL. Une fois actif, l'accès aux 3 agents et à
  l'historique est immédiat et libre — pas de progression séquentielle imposée.
- La barre latérale n'affiche Analyse / Stratégie / Créateur / Mes Stratégies /
  Historique que si un dossier est actif (`has_active_folder`, injecté par un context
  processor Flask). Dossiers et En savoir plus restent toujours visibles.
- La page Dossiers elle-même reste un sas de sélection/mémoire — pas un espace de
  travail. Le travail réel (analyse, stratégie, création) se fait toujours sur les
  pages dédiées, qui reçoivent le contexte du dossier via `folder_id`.

## Ce qui n'est pas encore tranché

- Faut-il une barre latérale extensible (façon ChatGPT) donnant un accès rapide à la
  liste des dossiers sans passer par `/dossiers` ? Une maquette a été proposée mais
  rien n'est implémenté. À trancher après retour d'usage sur la version actuelle.
- Le Consultant Stratégique (chat intégré à la page Stratège) et l'Orchestrateur
  (widget flottant sur les 3 agents) coexistent. Fusion prévue mais pas planifiée.

## Pourquoi documenter plutôt que juste décider en conversation

Le code évolue aussi en dehors des sessions avec Claude (autre outil, édition directe).
Un fichier versionné survit aux sessions ; une décision seulement dite dans une
conversation ne survit pas au prochain redémarrage de contexte.
