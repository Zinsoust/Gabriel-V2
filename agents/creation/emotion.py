# ═══════════════════════════════════════════════════════════════════════════
# EMOTION ENGINE — L'expérience émotionnelle visée
#
# Mission (brief §3) : l'émotion devient une composante STRATÉGIQUE, pas un
# gadget. Deux rôles :
#   1. Respecter l'émotion CHOISIE par l'utilisateur (ctx.emotion) — jamais
#      l'écraser.
#   2. Quand aucune n'est choisie, PROPOSER les émotions les plus pertinentes
#      pour l'objectif et l'audience. L'utilisateur reste libre (accepter,
#      modifier, ignorer) — la proposition ne force rien.
#
# La proposition est heuristique (signaux du Psychologue + objectif) : rapide,
# gratuite, déterministe. Le moteur de directives (_EMOTION_DIRECTIVES, déjà
# construit et testé) traduit ensuite l'émotion retenue en règles d'écriture,
# côté Writing Engine. Ici on décide seulement LAQUELLE viser.
# ═══════════════════════════════════════════════════════════════════════════

# Objectif → émotions naturellement alignées (ordre = priorité).
_OBJECTIVE_EMOTIONS = {
    "conversion":  ["urgence", "confiance", "motivation"],
    "sales":       ["urgence", "confiance", "motivation"],
    "authority":   ["autorite", "admiration", "confiance"],
    "autorite":    ["autorite", "admiration", "confiance"],
    "education":   ["curiosite", "reflexion", "confiance"],
    "attention":   ["curiosite", "surprise", "inspiration"],
    "launch":      ["urgence", "curiosite", "inspiration"],
}
_DEFAULT_EMOTIONS = ["confiance", "curiosite", "inspiration"]


def run(ctx) -> None:
    # 1. Construire la recommandation (toujours, pour l'affichage « Reco Gabriel »).
    obj = (ctx.objective or "").lower().strip()
    reco = list(_OBJECTIVE_EMOTIONS.get(obj, _DEFAULT_EMOTIONS))

    # Signaux du Psychologue : une audience blessée/frustrée appelle l'empathie
    # avant tout le reste. On la place en tête si le signal est présent.
    psy = (ctx.psycho_data or {}).get("psychologie") or {}
    emo = (ctx.psycho_data or {}).get("emotions") or {}
    if (psy.get("frustrations") or emo.get("espoir_decu")) and "empathie" not in reco:
        reco = ["empathie"] + reco
    reco = reco[:3]

    ctx.recommended_emotions = reco

    # 2. Ne JAMAIS écraser le choix de l'utilisateur. S'il a choisi/écrit une
    #    émotion, on la garde telle quelle. S'il a passé l'étape (vide), on
    #    laisse vide : la recommandation est une proposition, pas une imposition.
    #    (ctx.emotion reste inchangé — respect de la liberté de l'utilisateur.)
