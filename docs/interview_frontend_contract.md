# Entretien stratégique : contrat frontend

La refonte de l'entretien conserve les routes et la logique métier existantes.
Le navigateur consomme aujourd'hui les champs suivants :

- `reply`
- `updated_context`
- `progression`
- `completion_score`
- `is_ready`
- `current_dimension`
- `rejected_vague`
- `session_id`

Un adaptateur local accepte également une réponse structurée, soit à la racine,
soit sous `reply` ou `utterance` :

```json
{
  "state": "waiting_for_answer",
  "display_text": "Texte complet affiché",
  "speech_text": "Version courte destinée à la synthèse vocale",
  "stance": "challenge",
  "tone": "direct",
  "strategic_observation": "Constat réellement produit par Gabriel",
  "next_question": "Question suivante"
}
```

L'ancien contrat texte reste compatible. `reply: "..."` sert alors à la fois
à l'affichage et à la synthèse vocale.

## Données non reconstruites dans le navigateur

Le frontend regroupe visuellement `progression` en « Déjà compris » et
« À éclaircir » selon les statuts renvoyés par le serveur. Il ne déduit aucun
fait business et ne recalcule pas la complétude.

Pour piloter une vraie synthèse intermédiaire avec des actions spécifiques, le
backend devra fournir un état ou un événement dédié ainsi que le contenu
validé. Aucun contenu stratégique fictif n'est généré côté client en
attendant.

`context_progress.understood` et `context_progress.remaining` sont désormais
exposés par `/context-chat` et `/business-context` (agents/context_builder/
orchestrator.py, `_context_progress()`) : deux listes de libellés de
dimension, dérivées de `progression` côté serveur — le frontend peut les
utiliser directement au lieu de regrouper lui-même les statuts.

## Contrat backend complet (agents/context_builder/, brief vocal)

`reply` (sur `/context-chat` et sur l'ouverture d'une nouvelle session via
`/business-context`) est désormais toujours l'objet structuré ci-dessus, avec
en plus une clé `state` (`waiting_for_answer` | `completed`, dérivée de
`is_ready`) et `speech_profile: {pace, emphasis, pause_after}` — `pace` ∈
`slow | measured | standard`, dérivé de `stance` (contradict/recommend →
slow, challenge/caution → measured, validate/clarify → standard).

`/voice/speak` accepte désormais un champ optionnel `pace` (même valeurs) en
plus de `text` et `voice_id` — il module le débit ElevenLabs réel pour cette
réponse précise (`agents/context_builder/voice_provider.py`,
`speed_for_pace`). Absent ou inconnu, il retombe sur le débit par défaut du
compte.
