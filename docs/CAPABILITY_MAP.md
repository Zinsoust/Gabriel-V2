# Carte des capacités Gabriel — Phase 1 (Capability Audit)

> Inventaire factuel des capacités réellement présentes dans le back-end, en vue
> de la Toolification. Aucune modification de code n'a été faite pour produire ce
> document. Règle appliquée : **on ne veut pas 300 fonctions → 300 tools**. Seules
> les capacités significatives et invocables de façon autonome sont retenues.

---

## 1. Ce qui doit rester tel quel (INTERNAL_FUNCTION)

Helpers triviaux, sous-étapes, formatage de prompt, prédicats purs. À laisser où
ils sont : les promouvoir créerait de l'abstraction décorative.

Exemples représentatifs : `_detect_emotion_lexical`, `_detect_stance`,
`_detect_signals_v2` (`core/analyzer.py`) · `_keywords`, `_jaccard`, `_row_to_case`
(`core/memory.py`) · `_normalize_emotion_key`, `_summarize_strategy_for_critique`
(`agents/`) · `is_valid_step`, `next_step` (`core/strategy_session.py`) ·
`detect_comment_columns`, `check_mime` (`services/file_importer.py`) ·
`rag.format_context` · `_static_version` (`app.py`).

---

## 2. Ce qui doit devenir un Tool

**~20 tools, pas 300.** Regroupés par famille.

### 2.1 Monde extérieur (I/O réseau — les plus évidents)

| Tool proposé | Source actuelle | Pourquoi |
|---|---|---|
| `FetchYouTubeCommentsTool` | `services/scraper.py:102` | **Contrat de référence** : schéma de sortie riche, taxonomie d'erreurs déjà typée (`commentsDisabled`, `quotaExceeded`…), timeout 15 s, retry avec backoff |
| `FetchInstagramCommentsTool` | `services/scraper.py:217` | ⚠ modèle d'erreur à corriger d'abord (voir §9) |
| `FetchTikTokCommentsTool` | `services/scraper.py:263` | idem |
| `ParseCommentsFileTool` | `services/file_importer.py:67` + `:367` | Pur, borné (5 Mo), exception typée, neutralisation des formules Excel, **déjà testé** |
| `GeneratePdfReportTool` | `services/gen_pdf.py:209` / `:353` | dict → bytes, ni réseau ni disque |
| `TranscribeAudioTool` / `SynthesizeSpeechTool` | `agents/context_builder/voice_provider.py:136` / `:188` | Contrats propres, repli de voix intégré ; sensibles (API payante) |
| `WebSearchTool` | **n'existe pas** | Aujourd'hui seulement un drapeau vers l'outil hébergé d'OpenAI (`app.py:3501`) |

### 2.2 Calcul déterministe (zéro IA — les plus sûrs à extraire)

| Tool proposé | Source actuelle | Pourquoi |
|---|---|---|
| `ScoreCommentsTool` | `core/analyzer.py:385` | Primitive dont tout le reste dépend ; pur ; **aucun test** |
| `ComputeAudienceKpisTool` | `core/analyzer.py:635` | 6 KPIs livrant leurs propres formules |
| `ComputeAudienceDashboardTool` | `core/analyzer.py:1960` | Plus grande surface sans IA du dépôt (~30 métriques) |
| `RunNlpPipelineTool` | `core/nlp_engine.py:566` | Embeddings + TF-IDF + clustering + diversité en un appel |
| `ComputeStatisticalDeliverablesTool` | `core/nlp_engine.py:379` | 6 livrables publiables, sans IA, avec score de confiance |
| `CompareSourcesTool` | `core/cross_analysis.py:733` | Comparaison N-sources avec seuils explicites ; **le mieux testé** |
| `FindSimilarStrategyCasesTool` | `core/memory.py:101` + `:136` + `:289` | Méthodologie chiffrée (émotion 20 / aspirations 25 / frustrations 20 / motivations 15 / positionnement 10 / objectif 10), pure, sans réseau |

### 2.3 Connaissance

| Tool proposé | Source actuelle |
|---|---|
| `SearchKnowledgeTool` | `core/rag.py:348` + `:387` (fusionner : `sources` devient un paramètre optionnel) |
| `RetrieveConceptCardsTool` | `core/rag.py:446` + `:465` |

### 2.4 Vérification / anti-hallucination

| Tool proposé | Source actuelle | Pourquoi |
|---|---|---|
| `GroundClaimsAgainstEvidenceTool` | `core/cross_interpreter.py:194` + `core/analyzer.py:1151` | Rejette toute affirmation de l'IA non adossée aux preuves mesurées ; utile à **tout** agent |
| `CheckContentQualityTool` | `agents/createur.py:948` | 7 critères déterministes dont un détecteur de style « IA » réutilisable |

### 2.5 Adaptation / rendu

| Tool proposé | Source actuelle |
|---|---|
| `RenderContentToTextTool` | `agents/createur.py:1255` — déjà appelé depuis 3 modules |
| `AdaptPsychoContextTool` | `agents/stratege.py:91` — adaptateur Psychologue → Stratège |
| `ResolveBusinessContextTool` | `app.py:1835` + `agents/context_builder/schema.py:210` — **existe en 3 formes incohérentes** |

### 2.6 Routage / contexte conversationnel

| Tool proposé | Source actuelle |
|---|---|
| `ClassifyIntentTool` | `agents/orchestrator/intent.py` — classifieur déterministe réel |
| `PlanContextAccessTool` | `agents/orchestrator/context_access.py:88` + sa moitié d'exécution `app.py:3328` |
| `BuildAgentHandoffTool` | `agents/orchestrator/intent.py` — contrat de passage inter-agents |
| `ExtractStructuredAnswerTool` | `agents/context_builder/answer_extractor.py:183` — extraction structurée générique (LLM) |
| `AdversarialReviewTool` | **fusion** de `agents/stratege.py:357` et `agents/creation/dialectic.py:26` |

### 2.7 Politique (pas invocable par l'IA, mais le registre doit la posséder)

| Primitive | Source |
|---|---|
| Portail crédits / quotas | `api/db.py:1319` `:1331`, appliqué **4×** dans `app.py` |
| Suppression RGPD | `api/db.py:1994` — rayon d'action élevé, permission explicite requise |

---

## 3. Ce qui doit devenir un Skill

### 3.1 Déjà énumérable — extraction quasi sans risque

| Skill | Source | Contenu |
|---|---|---|
| Corpus stratégique | `agents/stratege/rag/**` | **39 méthodes nommées avec identifiants en JSON** : pricing (formules + paliers 7 €→10 000 €+), audience→offre (6 profils), design d'offre (Hormozi), conversion, décision immédiate, formats sociaux, patterns gagnants/perdants |
| `ToneDisciplineSkill` | `agents/createur.py:73-202` | 10 disciplines nommées, gabarit constant (Inspiration / Intention / Règles / Séquence obligatoire) |
| `EmotionDirectiveSkill` | `agents/createur.py:226-392` | 16 émotions cibles, gabarit constant (ressenti / leviers / mouvement) |
| `ContentStructureSkill` | `agents/createur.py:477-643` | 12 formats + 4 alias — **à scinder** : structures rédactionnelles (skill) vs schémas de sortie (contrat de données) |

### 3.2 Blobs à extraire (méthodologie noyée dans du texte ou du code)

| Skill | Source | Difficulté |
|---|---|---|
| Grille psychologique | `core/analyzer.py:40-112` | Munroe, Jung, Kahneman, Maslow, Frankl, Girard, Haidt, Bourdieu, Durkheim, Godin, Miller, Sinek, Cialdini, Sutherland + « lois absolues » — un seul bloc |
| Raisonnement stratégique | `agents/stratege.py:10-51` | 3 postures + pipeline nommé en 11 étapes + règle anti-jargon — à séparer en 3 |
| Règle tripartite | `core/analyzer.py:886-907` | Observation → Interprétation → Implication (**répétée 3×** verbatim) |
| Immersion persona | `agents/createur.py:813-905` | Construite ligne à ligne en Python |
| Voix humaine / anti-IA | `agents/createur.py:1067-1086` + `:972-978` | **Seule méthodo implémentée deux fois** (prompt + regex) → meilleure candidate à un Skill *avec validateur* |
| Conseil stratégique | `app.py:3110-3250` | ~140 lignes de prompt (« senior partner McKinsey ») dans une route |

### 3.3 Absents du dépôt

**SEO** et **branding** : aucune source documentaire, aucun bloc de méthode. Cités
dans la vision, inexistants dans le code.

---

## 4. Ce qui doit devenir un Workflow

| Workflow | Source | Nature |
|---|---|---|
| `CrossAnalysisWorkflow` | `core/cross_pipeline.py:124` | Collecte → analyses parallèles bornées → comparaison ; étape d'analyse injectée |
| `ContentCreationWorkflow` | `agents/creation/pipeline.py:119` | 9 étapes, parallélisation de `knowledge`, boucle d'auto-amélioration (seuil 80) |
| `AudienceAnalysisWorkflow` | `core/orchestrator.py:25` | NLP → scoring → KPIs → dashboard → LLM |
| `StrategyWorkflow` | `core/orchestrator.py:54` | Injection psycho → RAG → LLM → critique |
| `BusinessInterviewWorkflow` | `agents/context_builder/orchestrator.py:92` `:135` | Entretien vocal multi-tours avec état persisté |

---

## 5. Duplications

**Dangereuses (contrats incompatibles)**
1. `_parse_json` — `agents/stratege.py:225` **lève** une exception ; `agents/createur.py:671` **renvoie** `{parse_error: True}`. Même nom, comportements opposés.
2. Trois formules de confiance sans rapport (`nlp_engine.py:352`, `analyzer.py:2072`, `cross_analysis.py:777`) présentées comme un seul indicateur à l'utilisateur.

**Structurelles**
3. Wrappers LLM ×2 (`stratege.py:201` 270 s non-throttlé / `createur.py:648` 120 s throttlé) + alias morts `_call_mistral` ×2, encore importés par les 6 moteurs de `creation/`.
4. Critique adverse ×2 (`stratege.py:357`, `creation/dialectic.py:26`) — même schéma, aucun code partagé.
5. Contexte business ×3 (`app.py:4519`, `context_builder/schema.py:210`, résolution à 3 niveaux `app.py:1835`).
6. Champs business requis ×2 (`app.py:4506` / `schema.py:196`).
7. Similarité cosinus ×3 (`nlp_engine.py:190`, `:146`, `analyzer.py:1920`).
8. Portail crédits ×4 (`app.py:666/1021/1561/1894`), avec des calculs de coût divergents.
9. Lancement de job d'arrière-plan ×4 (`app.py:874/1259/1722/2025`).
10. Contrat de réponse Créateur ×3 (`createur.py:1140`, `pipeline.py:292`, `:251`).

**Code recopié dont l'original n'est jamais appelé**
11. `nlp_engine.compute_engagement_weight` (:666) — 0 appelant, formule recopiée dans `analyzer.py:482`.
12. `nlp_engine.preprocess_comment` (:654) — 0 appelant, règle anti-spam recopiée dans `analyzer.py:397`.

---

## 6. Mauvais noms

| Nom | Réalité | Gravité |
|---|---|---|
| `planner.py` | Rend un gabarit de prompt (ton/structure). **Ne planifie rien.** | haute — occupe le nom du futur vrai Planner |
| `validator.py` | Supprime 4 formules et les titres markdown. **N'est pas un Critic.** | haute — idem |
| `mental_model.py` | Assemblage de contexte + arithmétique de confiance. 3 de ses 13 champs (`hypotheses`, `risques`, `opportunites`) sont **toujours vides** | moyenne |
| `missions.py` | Construit un panneau d'interface + un contrat d'exécution. **Ne lance aucune mission** | moyenne |
| `_call_mistral` (×2) | Alias morts d'une fonction renommée | basse |
| `YouTubeProvider` | Adaptateur de 20 lignes sur `scrape_youtube` | basse |
| `creation/knowledge.py` | Adaptateur de 8 lignes vers le RAG du Créateur | basse |
| suffixe « ENGINE » (×9) | Aplati Tool / Function / raisonnement LLM sous une seule étiquette | moyenne |

---

## 7. Dépendances structurantes

- **`agents/createur.py` n'est pas remplaçable** : c'est à la fois la bibliothèque de briques du nouveau pipeline (qui l'importe à chaque étape) **et** le repli d'exécution (`app.py:1988`). Le « legacy » est une dépendance vivante.
- **`core/llm_client.py`** est désormais le socle de tous les agents — sauf l'orchestrateur, qui garde son propre client OpenAI (`app.py:3473`), non migré.
- **`api/db.py`** (2089 lignes) est le service de persistance unique ; le groupe Cross Analyse (~380 lignes) mériterait son propre service.
- **`core/rag.py`** est partagé par les trois agents ; c'est le point d'entrée unique de la connaissance.
- **État global mutable** : `_psycho_cache` (`app.py:361`), `_indexes` (`core/rag.py`), `_router_rules_cache` (`stratege.py`) — **non sûrs en multi-worker**.

---

## 8. Ordre d'extraction recommandé

**Étape A — Suppression (risque nul, gain immédiat)**
Code mort confirmé par recherche exhaustive : `services/build_landing.py` (chemin
Windows en dur, illisible) · `brain_profile.json` + `contexte_business.json` à la
racine (les vrais vivent dans `data/`) · `templates/orchestrateur.html` (aucune
référence) · route publique orpheline `POST /create` + `Gabriel.run_createur` +
`Createur.create_content` · `Createur.run` (lève systématiquement) ·
`score_and_correlate` (réimplémentation LLM d'un calcul déterministe, maintenue
en vie par un seul test) · `nlp_engine.compute_engagement_weight` et
`preprocess_comment` (0 appelant) · `scrape_tiktok_meta`.

**Étape B — Unification des contrats (avant tout registre)**
1. Un seul parseur JSON (aujourd'hui deux comportements opposés — piège réel).
2. Un seul contexte business (trois formes divergentes ; l'orchestrateur lit la mauvaise).
3. Une seule critique adverse.
4. Retrait des alias `_call_mistral`.

**Étape C — Tool Registry + 3 premiers tools**
Commencer par la couche déterministe : `ScoreCommentsTool`,
`ComputeAudienceKpisTool`, `ComputeAudienceDashboardTool`. Sans réseau, sans IA,
testables sans clé d'API — le contrat se valide à coût nul. Puis
`FetchYouTubeCommentsTool` comme référence des tools réseau.

**Étape D — Skill Registry**
Commencer par ce qui est **déjà énumérable** : le corpus `agents/stratege/rag/**`
(39 entrées structurées), puis tons et émotions. Risque quasi nul : il s'agit de
déclarer ce qui existe, pas de réécrire.

**Étape E — Blobs méthodologiques**
`GABRIEL_SYSTEM`, `_STRATEGE_SYSTEM`, immersion persona, voix humaine. Plus
délicat : toucher à ces textes change la sortie des agents.

**Puis seulement** : Planner, Router, Execution Graph, Critic, Synthesis.

---

## 9. Défauts trouvés pendant l'audit (à traiter, indépendants de la Toolification)

1. **Variante Créateur silencieusement morte** — le pipeline expose `ctx.variant` mais **aucune étape ne le remplit** (`pipeline.py:65`, `:315`). Demander une variante ne produit rien, sans erreur. L'ancien chemin la produisait.
2. **Échec silencieux Instagram/TikTok** — `([], {})` est renvoyé aussi bien pour « API en panne » que pour « aucun commentaire ». Impossible de distinguer.
3. **Dégradation muette du RAG** — si le modèle d'embeddings est indisponible, `search` renvoie les premiers extraits **non classés** comme s'ils étaient pertinents (`core/rag.py:365`).
4. **Cache global non sûr en multi-worker** — `_psycho_cache` et consorts.
5. **Aucun test** sur Stratège, Créateur, pipeline de création, mémoire, voix.
