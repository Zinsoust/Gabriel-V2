"""Planification de réponse : structure et expérience de voix de Gabriel."""


def build_response_directive(decision, mental_model, context_access=None):
    action = decision.get("action")
    specialist = decision.get("specialist")
    action_rules = {
        "answer_directly": (
            "Répondez directement, prenez une position utile quand les éléments le permettent, "
            "puis donnez une prochaine action concrète."
        ),
        "research_then_answer": (
            "Appuyez les faits actuels sur la recherche Web. Distinguez les faits sourcés "
            "de votre recommandation et ne recherchez que ce qui change la décision."
        ),
        "synthesize_existing": (
            "Reliez les analyses existantes, signalez leurs convergences ou contradictions, "
            "puis formulez une recommandation propre à l'Orchestrateur."
        ),
        "recommend_specialist": (
            f"Donnez d'abord une première orientation utile, puis recommandez {specialist} "
            "avec une raison précise et le résultat supplémentaire que cet expert apportera. "
            "Ne renvoyez jamais l'utilisateur vers un agent comme substitut à une réponse."
        ),
    }
    context_access = context_access if isinstance(context_access, dict) else {}
    selected = context_access.get("agents") if isinstance(context_access.get("agents"), list) else []
    source_rule = (
        "Les sources spécialisées fournies pour cette réponse sont : "
        + ", ".join(selected)
        + ". Distinguez clairement ce qui vient de ces sources et votre propre recommandation."
        if selected else
        "Aucun rapport spécialisé n'est requis pour cette demande. N'en inventez pas et ne prétendez pas les avoir relus."
    )
    return (
        "\n\n━━━ PLAN DE RÉPONSE OBLIGATOIRE ━━━\n"
        "Suivez cet ordre sans afficher de titres artificiels : compréhension de "
        "l'intention, première réponse utile, nuance nécessaire, recommandation, action suivante. "
        "Posez au plus une question, uniquement si elle change réellement la décision.\n"
        + action_rules.get(action, action_rules["answer_directly"])
        + "\nLa voix reste calme, élégante, précise, humaine, pragmatique et chaleureuse. "
          "Parlez comme un consultant senior : aucune flatterie, aucune brutalité, aucun jargon d'IA. "
          "Ne dites jamais que vous êtes incapable ; valorisez les spécialistes comme des collègues experts.\n"
        + source_rule + "\n"
        f"Confiance interne : {mental_model.get('niveau_confiance', 0):.2f}. "
        "Ne présentez jamais cette valeur interne à l'utilisateur."
    )
