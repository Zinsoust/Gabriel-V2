#!/usr/bin/env python3
"""
Revue des manques du Design Agent — mode DESIGN_DEVELOPMENT
=============================================================
Lit `data/design_recipe_gaps.json` (les formes de contenu rencontrées en
production pour lesquelles aucune recette validée n'existe — voir
`agents/design_recipes.py`), et pour chacune, appelle
`agents.design_agent.draft_recipe_with_llm` pour proposer un brouillon de
recette.

Ce script ne modifie jamais `agents/design_recipes.py` tout seul. Il propose ;
un humain relit chaque brouillon, décide si le composant recommandé existe
réellement ou doit d'abord être construit, puis ajoute la recette validée à la
main dans `agents/design_recipes.py` (nouveau couple match/build, ajouté au
tuple `_RECIPES`).

C'est un choix délibéré, pas un oubli : le Design Agent runtime ne doit jamais
pouvoir faire évoluer le Design System de lui-même suite à une requête
utilisateur. Ce script s'exécute UNE SEULE FOIS par lot, à la main, en
offline — il ne tourne jamais à l'analyse ni sur un déclencheur automatique.

Utilisation :
    python scripts/design_review_gaps.py                  # revoit tous les manques
    python scripts/design_review_gaps.py --signature XYZ   # un seul manque
    python scripts/design_review_gaps.py --mark-resolved XYZ  # retire un manque
                                                                # déjà traité (recette
                                                                # ajoutée à la main)
"""

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

GAPS_FILE = BASE_DIR / "data" / "design_recipe_gaps.json"


def _load_gaps() -> list:
    if not GAPS_FILE.exists():
        return []
    with open(GAPS_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def _save_gaps(gaps: list) -> None:
    with open(GAPS_FILE, "w", encoding="utf-8") as handle:
        json.dump(gaps, handle, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--signature", help="Ne revoir qu'un seul manque (par signature).")
    parser.add_argument("--mark-resolved", help="Retirer un manque de la file (recette déjà ajoutée à la main).")
    args = parser.parse_args()

    gaps = _load_gaps()

    if args.mark_resolved:
        remaining = [g for g in gaps if g.get("signature") != args.mark_resolved]
        if len(remaining) == len(gaps):
            print(f"Aucun manque avec la signature « {args.mark_resolved} ».")
            return
        _save_gaps(remaining)
        print(f"Manque « {args.mark_resolved} » retiré de la file.")
        return

    if not gaps:
        print("Aucun manque en attente — rien à revoir.")
        return

    if args.signature:
        gaps = [g for g in gaps if g.get("signature") == args.signature]
        if not gaps:
            print(f"Aucun manque avec la signature « {args.signature} ».")
            return

    from agents.design_agent import draft_recipe_with_llm

    for gap in gaps:
        print(f"\n{'=' * 70}")
        print(f"Signature : {gap['signature']}")
        print(f"Agent source : {gap.get('source_agent', '?')}  |  vu le : {gap.get('seen_at', '?')}")
        envelope = gap.get("example_envelope")
        if not envelope:
            print("(pas d'exemple de contenu enregistré — manque journalisé avant cet ajout)")
            continue

        result = draft_recipe_with_llm(envelope)
        print(json.dumps(result["decision"], ensure_ascii=False, indent=2))
        print(
            "\n→ Si ce brouillon est bon : ajouter une recette à la main dans "
            "agents/design_recipes.py (couple match/build, dans _RECIPES), "
            f"puis lancer : python scripts/design_review_gaps.py "
            f"--mark-resolved {gap['signature']!r}"
        )


if __name__ == "__main__":
    main()
