# Gabriel — Audit produit et technique

**Date d'observation :** 14 octobre 2026  
**Branche observée :** `V3_steph`  
**Nature :** audit en lecture, tests locaux ciblés et recherche documentaire publique  
**Interdictions respectées :** aucune migration, aucun appel IA payant, aucune prospection, aucun envoi, aucun déploiement, aucun commit ni push, aucune modification applicative.

## 1. Conclusion exécutive

Gabriel possède une proposition de valeur crédible et différenciante : relier une connaissance d'audience concrète à une décision stratégique puis à un livrable. Les trois spécialistes existent, leurs interfaces spécialisées sont substantielles et plusieurs mécanismes de traçabilité ou d'anti-hallucination sont déjà présents. Le module Prospect MVP 3 a par ailleurs franchi une étape réelle de persistance en environnement DEV.

Cependant, la chaîne premium n'est pas aujourd'hui certifiable de bout en bout. Deux défauts observables bloquent une affirmation de fiabilité :

1. l'adaptateur Psychologue → Ariane attend un ancien schéma et perd silencieusement une partie du brief et de la distribution émotionnelle actuels ;
2. l'environnement local testé ne contient pas `vaderSentiment`, dépendance pourtant déclarée, et le code échoue au lieu de dégrader proprement.

Une troisième rupture est d'expérience : le passage d'Ariane à Thomas navigue vers l'onglet Créateur, mais l'usage de la stratégie est désactivé par défaut. Enfin, le terme « quatre agents » masque une réalité hétérogène : trois spécialistes principaux et un module Prospect indépendant, tandis que l'exécuteur générique ne sait pas appeler le point d'entrée réel de Thomas.

La bêta privée du 21 octobre 2026 reste réaliste si son périmètre est réduit à un parcours guidé, si les P0 sont corrigés et si un test réel contrôlé de la chaîne entière est réussi avant la session. Elle ne doit pas dépendre de Prospect, de Stripe, des crédits ou d'automatisations futures.

## 2. Méthode et niveau de preuve

L'audit combine :

- lecture des documents d'architecture, déploiement, sécurité et Prospect existants ;
- inventaire du dépôt et inspection ciblée des routes, registres, adaptateurs, résolveurs et composants React ;
- exécution locale de tests sans appel payant ;
- vérification HTTP du serveur déjà lancé ;
- consultation de sources officielles et de pages produit concurrentes ;
- consultation limitée d'agrégats d'avis publics, traités comme signaux subjectifs et non comme faits universels.

### Niveaux utilisés

- **Prouvé :** observé dans le code, un test ou une réponse locale.
- **Fortement étayé :** plusieurs indices concordants, sans test réel complet.
- **Déclaré :** document ou historique de test existant, non rejoué pendant cet audit.
- **Hypothèse :** recommandation à valider avec des utilisateurs ou des mesures.

### Limites

- aucun appel aux modèles payants n'a été effectué ;
- aucune donnée de production ni projet Supabase historique n'a été consulté ;
- aucun test d'email ou de prospection réelle n'a été effectué ;
- les prix et offres concurrentes sont ceux consultés le 14 octobre 2026 et peuvent évoluer ;
- les avis G2/Capterra reflètent des utilisateurs auto-sélectionnés et des catégories larges ;
- les tests ciblés ne remplacent pas une installation propre et une campagne complète de non-régression.

## 3. État du dépôt et architecture réelle

### 3.1 État Git préservé

La branche active est `V3_steph`. Le dépôt contenait avant l'audit des modifications non commitées du MVP 3, notamment dans `app.py`, le dépôt Prospect, la migration, des tests et plusieurs nouveaux fichiers Prospect. Elles ont été conservées. Aucun reset, clean, commit ou push n'a été exécuté.

Un test ciblé a régénéré le fichier suivi `knowledge/_index/stratege.pkl`. Après vérification et autorisation explicite du propriétaire du dépôt, une restauration contrôlée de ce seul fichier a été effectuée depuis `HEAD`. Aucun autre fichier n'a été restauré, supprimé ou écrasé.

#### Chronologie et attribution de `stratege.pkl`

Les traces disponibles permettent d'établir la séquence suivante :

1. le premier `git status --short`, capturé avant la campagne ciblée, ne signalait pas `knowledge/_index/stratege.pkl` ;
2. la campagne a exécuté `tests/test_skill_strategy.py`, dont le test de pipeline appelle le vrai `Stratege.run()` sans neutraliser `_load_rag_rules` ;
3. `_load_rag_rules` appelle `core.rag.search_filtered`, puis `_load_or_build` ; quand le hash du cache ne correspond pas aux documents RAG, cette fonction ouvre `knowledge/_index/stratege.pkl` en mode `wb` et le sérialise avec `pickle.dump` ;
4. le premier état Git relevé après cette campagne a signalé le fichier comme modifié ;
5. son `LastWriteTime` est le 14 octobre 2026 à 19:08:37, soit le créneau de cette exécution ;
6. le blob `HEAD` mesure 75 190 octets et porte l'empreinte Git `46d059c2…`, contre 42 784 octets et `2e4f9407…` dans le worktree ;
7. les deux index contiennent 21 chunks. Celui de `HEAD` contient une matrice d'embeddings `(21, 384)`, tandis que la version régénérée contient `embeddings=None` ;
8. le hash de sources enregistré dans la version courante correspond exactement au hash actuel des 11 fichiers `agents/stratege/rag`, alors que le hash du cache `HEAD` est différent.

La causalité technique et temporelle avec le test est donc fortement établie : le cache était propre dans Git avant la campagne, obsolète par rapport aux sources actuelles, puis le vrai chemin RAG l'a reconstruit dans un environnement sans modèle d'embeddings disponible. Il n'existe toutefois pas de journal d'audit système permettant d'exclure formellement toute écriture concurrente par un autre processus à la même seconde ; l'audit ne qualifie donc pas cette attribution d'exclusivité forensique.

Avant restauration, la version régénérée a été copiée dans un dossier temporaire Windows hors du dépôt. La source et la sauvegarde mesuraient toutes deux 42 784 octets et partageaient le SHA-256 `D904C17B…B1B464`. Après restauration :

- l'empreinte Git du worktree est `46d059c2…`, identique au blob `HEAD` ;
- la taille est revenue à 75 190 octets ;
- le SHA-256 restauré est `B242479A…CB064A` ;
- l'index contient toujours 21 chunks et une matrice d'embeddings `(21, 384)` ;
- `knowledge/_index/stratege.pkl` n'apparaît plus dans `git status` ;
- toutes les autres modifications locales observées avant l'opération sont toujours présentes.

Une incompatibilité reste à traiter ultérieurement : le hash interne de l'index restauré est `6678f319…`, tandis que le hash des 11 sources RAG actuelles est `35fceb5b…`. Le chargeur considérera donc probablement le cache comme périmé et tentera de le reconstruire lors d'une recherche stratégique. Cette reconstruction ne doit être faite qu'après choix explicite du modèle d'embeddings, dans un environnement isolé, puis validée avant toute mise à jour éventuelle de l'artefact suivi.

Ce constat révèle également un défaut de conception des tests : un test unitaire peut modifier un artefact binaire suivi. Toute nouvelle exécution doit rediriger le répertoire d'index vers un dossier temporaire ou neutraliser la persistance avant l'import du pipeline.

### 3.2 Forme générale

- backend Flask concentré dans `app.py`, complété par `agents/`, `core/`, `services/`, `tools/`, `skills/`, `api/` et `gabriel_prospect/` ;
- frontend React dans `frontend-react/src/gabriel-v2` ;
- persistance principale via `api/db.py` et services associés ;
- module Prospect séparé avec client et repository dédiés ;
- environ 195 fichiers Python, 44 fichiers JavaScript/JSX, 75 fichiers de tests backend et 20 fichiers de tests frontend au moment de l'inventaire ;
- 94 décorateurs de routes Flask détectés.

Les documents [AUDIT_ARCHITECTURE.md](AUDIT_ARCHITECTURE.md) et [CAPABILITY_MAP.md](CAPABILITY_MAP.md) apportent un contexte historique utile mais contiennent des constats devenus obsolètes, notamment sur l'absence de registres d'outils et de compétences. Ils ne doivent pas être utilisés comme photographie actuelle sans revalidation.

## 4. Inventaire fonctionnel réel

| Domaine | État | Preuve synthétique | Limite majeure |
|---|---|---|---|
| Psychologue | Existant | routes d'analyse, sources multiples, personas, émotions, preuves, exports et historique | dépendances et chaîne réelle non validées en environnement propre |
| Analyse croisée | Existant | comparaison de 2 à 5 audiences, pack de preuves et contrôle de grounding | promesse UI surtout orientée YouTube ; coût et délai à mesurer |
| Ariane / Stratège | Existant | stratégie depuis analyse enregistrée ou cadrage, mémoire, critique, garde chiffrée | adaptateur de schéma Psycho obsolète |
| Thomas / Créateur | Existant via route spécialisée | génération, révision, sauvegarde, historique et plusieurs formats | `run()` non implémenté ; orchestration générique impossible |
| Chaîne Psychologue → Ariane → Thomas | Partielle | identifiants et résolveurs existent, chaque écran peut travailler | pertes de contexte, activation manuelle de stratégie, aucun E2E réel certifié |
| Mémoire | Partielle | historique, dossiers, contexte métier et cas stratégiques | gouvernance de fraîcheur, versions et consentement incomplète |
| Prospect MVP 3 | Existant en DEV | persistance, déduplication, statuts, historique, isolation et opposition testés | recherche Web, enrichissement massif, email et relances absents |
| Architecte | Planifié | déclaré dans le catalogue | pas d'accès direct ni parcours produit complet |
| Design Agent | Interne | point d'entrée interne disponible | non sélectionnable et non destiné à être vendu comme agent utilisateur |
| Conversations orchestrateur | Partiel | réponse via fournisseurs configurés | dépendance externe et coût ; ne prouve pas la chaîne métier |

### 4.1 Le Psychologue

Le code prévoit des analyses depuis YouTube, Instagram/TikTok via fournisseur tiers, saisie manuelle et imports CSV/XLS/XLSX/JSON/TXT. Les sorties couvrent émotions, éléments psychologiques, personas, indicateurs, recommandations, dashboard et interprétation. L'analyse croisée construit un ensemble de preuves et contrôle certaines références aux sources.

Le schéma actuel du brief émis par le cœur d'analyse utilise les clés `qui`, `insight` et `action`. La distribution émotionnelle courante expose notamment des comptes `positifs`, `negatifs` et `total`.

### 4.2 Ariane, la Stratège

Ariane peut partir d'une analyse enregistrée, d'une analyse croisée ou d'un entretien de cadrage. La route classique résout l'analyse depuis le cache puis la base avec filtrage par utilisateur, exige un contexte métier et relie la stratégie sauvegardée à l'analyse et au dossier. Une mémoire de cas peut être injectée.

Des garde-fous existent : règle de source dans le prompt, critique indépendante et filtre des faits chiffrés. Ils réduisent le risque mais ne transforment pas les conclusions sémantiques en faits vérifiés.

### 4.3 Thomas, le Créateur

L'interface propose notamment script court, YouTube, TikTok/Reels, LinkedIn, thread, séquence email et page de vente. Le pipeline spécialisé assemble intention, contexte, émotion, récupération documentaire, plan, rédaction, dialectique, optimisation, garde factuelle et qualité, avec un chemin historique de repli.

Le résolveur serveur est correctement orienté utilisateur. Le persona envoyé par le navigateur n'est pas accepté comme une vérité complète : son nom sert à sélectionner un persona dérivé côté serveur.

En revanche, `Createur.run()` lève explicitement `NotImplementedError`. Le Planner peut produire une étape Créateur, mais l'Executor rejette tout point d'entrée autre que `run`. La route spécialisée `/creator/generate` constitue donc le chemin réel ; l'orchestration générique des trois agents n'est pas opérationnelle.

### 4.4 Gabriel Prospect

Les preuves existantes de validation DEV indiquent :

- 1 import réel en environnement DEV isolé ;
- 5 agences exclusivement fictives ;
- 8 événements d'historique ;
- 1 opposition fictive conservée ;
- statuts observés : 3 `qualified`, 1 `replied`, 1 `to_enrich` ;
- persistance, rechargement, doublons, statuts, historique, isolation inter-utilisateurs et `do_not_contact` validés ;
- 186 tests backend ciblés et 234 tests React passés lors de la validation MVP 3 ;
- build React réussi.

Les détails techniques sont consignés dans [gabriel_prospect_mvp3_storage.md](gabriel_prospect_mvp3_storage.md) et le parcours dédié dans [gabriel_prospect_mvp3_demo.md](gabriel_prospect_mvp3_demo.md). Ces résultats ne permettent pas de revendiquer une recherche Web, un enrichissement industrialisé, un emailing ou des relances : ces fonctions ne sont pas présentes.

## 5. Audit de la transmission de contexte

### 5.1 Carte du flux

| Passage | Ce qui fonctionne | Rupture ou risque | Gravité |
|---|---|---|---|
| Source → Psychologue | sources, analyse et persistance | biais d'échantillon et autorisations à expliciter | Haute |
| Psychologue → Ariane | analyse résolue par ID et utilisateur ; analyse croisée adaptée | ancien schéma de brief et de distribution lu silencieusement | Critique |
| Navigation Psychologue → Ariane | transfert temporaire via `sessionStorage` | pas d'expiration, suppression ou liaison forte au dossier trouvée | Haute |
| Ariane → Thomas | stratégie retrouvable dans le dossier | navigation seule ; stratégie désactivée par défaut | Critique produit |
| Psychologue → Thomas | brief courant avec anciennes clés de repli | requête RAG et métadonnées lisent encore `insight_cle` uniquement | Haute |
| Persona → Thomas | persona résolu côté serveur | utilisateur peut croire qu'un autre persona est actif si l'état visuel est ambigu | Moyenne |
| Orchestrateur générique | Psychologue exécutable | Thomas incompatible avec l'Executor | Haute |

### 5.2 Perte silencieuse Psychologue → Ariane

L'adaptateur `_build_psycho_context` de `agents/stratege.py` lit `synthese`, `insight_cle` et `action_prioritaire`. Le producteur courant dans `core/analyzer.py` émet `qui`, `insight` et `action`. Un essai avec la fixture React réelle `psychologue-analyse-youtube.json` produit donc des chaînes vides pour `synthese_audience`, `insight_cle` et `action_prioritaire`, alors que d'autres champs psychologiques restent présents.

Le même adaptateur lit `distribution.positif` et `distribution.negatif`, tandis que le schéma courant expose `positifs` et `negatifs` comme comptes. Les proportions positives et négatives deviennent zéro au lieu d'être calculées à partir du total.

Les tests unitaires actuels de l'adaptateur utilisent les anciennes clés et ne détectent pas cette dérive. Il s'agit d'un défaut P0 : le système peut produire une stratégie apparemment valide avec un contexte central amputé, sans erreur visible.

### 5.3 Transfert temporaire non gouverné

Le frontend écrit `gabriel_for_stratege` dans `sessionStorage` avec l'identifiant d'analyse, le dossier et un brief condensé. Ariane le lit au montage. Aucun mécanisme d'expiration, d'effacement après consommation ou de vérification forte de cohérence avec le dossier actif n'a été trouvé.

L'accès serveur reste filtré par utilisateur, ce qui limite la fuite entre comptes. Le risque principal est une contamination de contexte à l'intérieur d'une même session : une ancienne analyse peut être réutilisée pour un nouveau dossier.

### 5.4 Passage Ariane → Thomas

Le bouton « Le Créateur → » change l'onglet. Il ne force pas l'activation de la stratégie courante. Dans Thomas, `useStrategy` vaut `false` par défaut alors que `usePsycho` vaut `true`.

Ce comportement contredit la promesse centrale : l'utilisateur peut croire que le contenu découle de la stratégie qu'il vient de valider alors que celle-ci n'est pas injectée. La correction doit être explicite et visible, pas seulement technique.

### 5.5 Perte partielle dans Thomas

Le brief final de Thomas accepte les nouvelles clés `qui`/`insight` avec repli vers l'ancien schéma. En revanche, la requête de récupération documentaire et certaines métadonnées lisent encore seulement `brief.insight_cle`. La génération peut donc recevoir l'insight dans une partie du pipeline mais pas dans la recherche documentaire ni la trace enregistrée.

### 5.6 Doublons et collisions

Le contexte est présent sous plusieurs formes : objet complet, résumé, stockage temporaire frontend, base, cache, mémoire stratégique et métadonnées de création. Cette redondance améliore parfois la résilience mais crée des sources concurrentes. Les règles de priorité existent localement, sans contrat global versionné ni signal clair de fraîcheur. Le risque est une sortie cohérente en apparence mais fondée sur une version périmée.

## 6. Tests exécutés et résultats

### 6.1 Vérification du serveur local

Le serveur local déjà lancé a répondu :

- endpoint de santé : HTTP 200 ;
- interface React : HTTP 200, `text/html`, build servi ;
- URL observée : `http://127.0.0.1:5050/orchestrateur?agent=prospect`.

Cette vérification confirme la disponibilité de l'interface, pas le bon fonctionnement d'un appel IA réel.

### 6.2 Tests ciblés de la chaîne principale

Commande exécutée sans appel payant :

```text
python -m pytest -q \
  tests/test_createur_contexte_psychologue.py \
  tests/test_strategy_guard.py \
  tests/test_agent_registry.py \
  tests/test_mission_composition.py \
  tests/test_executor.py \
  tests/test_creation_fact_guard.py \
  tests/test_persona_grounding.py \
  tests/test_skill_persona_immersion.py \
  tests/test_skill_strategy.py
```

**Résultat : 113 réussis, 3 échoués.**

Les trois échecs concernent la composition/exécution du Psychologue. `core/analyzer.py` utilise le singleton VADER alors qu'il vaut `None`, puis appelle `polarity_scores`. `vaderSentiment>=3.3.2` est déclaré dans `requirements.txt` mais absent du `venv` observé. L'import est intercepté, puis l'absence n'est pas gérée lors de l'usage.

Conséquences :

- l'environnement courant n'est pas reproductible à partir de son état supposé ;
- une dépendance manquante devient une erreur tardive et peu explicite ;
- la chaîne réelle Psychologue → Ariane n'a pas pu être certifiée localement.

Après cette campagne, aucun test susceptible d'écrire dans le dépôt n'a été relancé. Les vérifications complémentaires ont été strictement en lecture seule.

### 6.3 Ce qui n'a pas été testé

- aucune génération Mistral/OpenAI réelle ;
- aucune collecte YouTube/RapidAPI réelle ;
- aucun paiement Stripe ni consommation de crédits ;
- aucun parcours live complet reliant un même `analysis_id`, `strategy_id` et `creation_id` ;
- aucune charge simultanée ou reprise après crash ;
- aucune publication ni envoi externe.

## 7. Hallucinations, preuves et confiance

### Contrôles présents

- scoring déterministe et rattachement des personas aux clusters dans le Psychologue ;
- pack de preuves et suppression de références invalides dans l'analyse croisée ;
- garde des nombres et critique de stratégie dans Ariane ;
- réécriture ou suppression de chiffres non justifiés dans Thomas ;
- exposition de certains chiffres non vérifiés.

### Limites restantes

- une interprétation psychologique profonde reste une inférence de modèle, même si elle est plausible ;
- les relations causales, recommandations de prix et choix stratégiques ne sont pas systématiquement rattachés à une preuve individuelle ;
- les citations et identifiants de source sont inégalement visibles dans l'expérience ;
- le modèle peut transformer une majorité apparente dans l'échantillon en généralisation sur le marché ;
- la dérive de schéma actuelle peut amplifier l'hallucination en privant Ariane de contexte sans l'en avertir.

Recommandation : afficher et conserver quatre catégories — **observation**, **inférence**, **hypothèse**, **décision** — et exiger une référence pour toute observation structurante.

## 8. Sécurité, confidentialité et conformité

### Points positifs

- résolution de plusieurs ressources par utilisateur ;
- opposition Prospect persistante et non contournée ;
- environnement Prospect DEV indépendant ;
- précautions de journalisation ajoutées au MVP 3 ;
- documents de sécurité bêta existants.

### Risques à traiter

- l'authentification ne doit jamais être désactivée pendant la bêta réelle ;
- les données de commentaires peuvent contenir des données personnelles ou sensibles ;
- l'utilisateur doit attester qu'il est autorisé à importer et traiter les données ;
- les durées de conservation, suppressions, fournisseurs et transferts doivent être documentés ;
- toute future prospection email devra respecter information, droit d'opposition, identité de l'émetteur, lien de désinscription et pertinence professionnelle ;
- toute automatisation non autorisée de LinkedIn doit être exclue.

La CNIL rappelle que l'utilisateur d'une IA générative ne doit fournir que des données qu'il est autorisé à transmettre, doit éviter les données confidentielles dans des services grand public et doit vérifier les résultats. Pour la prospection B2B, l'intérêt légitime peut être pertinent sous conditions, mais l'information et l'opposition simple et gratuite restent nécessaires. Les conditions LinkedIn interdisent notamment le scraping et les bots non autorisés.

## 9. Marché français et attentes utilisateurs

### 9.1 Signaux de marché officiels

Le [Baromètre France Num 2026](https://www.francenum.gouv.fr/guides-et-conseils/strategie-numerique/comprendre-le-numerique/barometre-france-num-2026-le), publié fin septembre 2026, indique que 40 % des TPE/PME utilisent au moins une solution d'IA, contre 26 % un an plus tôt et 13 % en 2024. Le taux atteint 53 % pour les PME et 60 % dans les services spécialisés et techniques. La génération de contenu domine les usages cités à 34 %, loin devant l'analyse de données à 9 %. 68 % des utilisateurs de l'IA constatent un impact positif, proportion qui monte à 84 % chez les utilisateurs de solutions payantes. 84 % déclarent préférer des services numériques français ou européens et 42 % valorisent la proximité géographique.

L'[étude qualitative France Num 2025](https://www.francenum.gouv.fr/files/2025-12/Barom%C3%A8tre%20France%20Num%202025%20-%20Enquete%20qualitative.pdf), publiée le 4 décembre 2025 et fondée sur 32 entreprises, décrit des usages souvent étroits, gratuits ou peu coûteux, une méfiance envers la fiabilité et les données sensibles, ainsi qu'un besoin de formation accessible et d'accompagnement de bout en bout. Sa taille impose de la considérer comme qualitative.

L'[Insee](https://www.insee.fr/fr/statistiques/8721354) a compté 1 165 800 créations d'entreprises en 2025, dont 758 600 micro-entrepreneurs et 301 300 sociétés. Le panorama [Les entreprises en France, édition 2025](https://www.insee.fr/fr/statistiques/fichier/8679855/IA115.pdf), portant sur le tissu productif 2023, recense environ 5,2 millions d'entreprises marchandes non agricoles et non financières, dont 97 % de microentreprises. Ce volume ne constitue pas à lui seul un marché adressable : il renforce au contraire la nécessité de choisir un segment précis.

France Num cite le coût, le manque d'expertise interne et la compatibilité comme freins à l'adoption dans son [guide des aides IA](https://www.francenum.gouv.fr/aides-financieres/guides-et-conseils-financiers/quelles-sont-les-aides-financieres-pour-aider-les). Le programme [Diag Data IA](https://www.francenum.gouv.fr/guides-et-conseils/intelligence-artificielle/comprendre-et-adopter-lia/diag-data-ia-beneficiez-dun), mis à jour en juin 2026, illustre une demande institutionnelle pour un accompagnement expert structuré plutôt qu'un simple accès logiciel.

### 9.2 Attentes et frustrations publiques

Les avis agrégés doivent être lus comme des signaux subjectifs :

- la catégorie [Social Media Listening de G2](https://www.g2.com/categories/social-media-listening-tools), consultée en octobre 2026, met en avant la centralisation et les analyses, mais aussi le coût, la courbe d'apprentissage, le bruit, la personnalisation des tableaux de bord et les limites d'intégration ;
- le guide [Social Listening de G2](https://learn.g2.com/best-social-media-listening-tools), publié le 20 avril 2026, oppose outils simples mais bruyants et solutions profondes mais complexes, avec des limites liées aux API et à l'accès aux données ;
- la catégorie [CRM de G2](https://www.g2.com/categories/crm), consultée en octobre 2026, relève prix peu lisibles, apprentissage et intégrations comme irritants récurrents ;
- la catégorie [Sales Engagement de G2](https://www.g2.com/categories/sales-engagement), mise à jour le 3 juin 2026, montre une attente de visibilité du flux et de qualité de données avant les fonctions IA ;
- les avis [CRM sur Capterra France](https://www.capterra.fr/directory/2/customer-relationship-management/software), consultés le 14 octobre 2026, font ressortir le coût des licences, les fonctions essentielles réservées aux offres supérieures et les intégrations de messagerie, tout en indiquant une perception positive de la valeur pour une majorité d'avis.

Le besoin pertinent pour Gabriel n'est donc pas « davantage d'IA ». Il est : moins de bruit, moins de recopie, davantage de preuves, une chaîne compréhensible et un accompagnement crédible.

## 10. Analyse concurrentielle

### 10.1 Concurrents et substituts

| Catégorie | Exemples et prix publics consultés | Force | Espace pour Gabriel |
|---|---|---|---|
| Audience intelligence | [SparkToro](https://sparktoro.com/pricing) : offre gratuite, Business 150 USD/mois, Agency 300 USD/mois | données d'audience et activation | selon son [centre d'aide](https://sparktoro.com/support), couverture actuelle surtout anglophone États-Unis/Canada/Royaume-Uni et pas de contacts personnels ; angle français possible |
| Social listening entreprise | [Mention](https://mention.com/en/pricing/) à partir d'environ 599 USD/mois en annuel selon son [aide](https://en.support.mention.com/en/articles/7988097-mention-plans-explained), [Brandwatch](https://www.brandwatch.com/plans/) sur devis | collecte, monitoring, reporting | Gabriel peut privilégier la profondeur décisionnelle et la simplicité, pas le volume |
| Gestion sociale | [Agorapulse](https://www.agorapulse.com/pricing/) : Standard 79 USD/utilisateur/mois en annuel, autres plans supérieurs | publication, inbox, reporting | ne pas concurrencer la suite opérationnelle ; s'intégrer plus tard |
| Génération marketing | [Jasper](https://www.jasper.ai/pricing) : Pro 59 USD/mois en annuel, Business sur mesure | marque, audience, connaissances et agents marketing | différenciation par preuve d'audience et continuité stratégique |
| IA horizontale | [ChatGPT Business](https://openai.com/business/pricing/) : environ 20 USD/siège/mois en annuel ou 25 USD mensuel, minimum deux sièges selon [l'aide officielle](https://help.openai.com/en/articles/8801848) | polyvalence, connecteurs et agents | Gabriel doit être un workflow spécialisé, pas un chat habillé |
| CRM relationnel | [folk](https://www.folk.app/pricing) : Premium 43 EUR/utilisateur/mois en annuel ou 54 EUR mensuel | CRM flexible, séquences, historique | ne pas reconstruire un CRM généraliste |
| Outbound | [Lemlist](https://www.lemlist.com/pricing) : Email Pro 55 USD/mois en annuel, Multichannel Expert 87 USD | données, enrichissement et séquences | catégorie mature ; Prospect doit rester complémentaire |
| Prospection française | [Pharow](https://www.pharow.com/tarifs) : Essential 105 EUR/mois en annuel, données B2B françaises | recherche et enrichissement spécialisés | partenaire ou connecteur futur plus crédible qu'une reconstruction immédiate |

### 10.2 Position concurrentielle recommandée

Gabriel doit occuper la jonction peu servie entre outils d'écoute, conseil stratégique et génération de contenus :

> **L'atelier français de décision marketing fondé sur des preuves d'audience.**

Il ne doit pas chercher à égaler la largeur de collecte de Brandwatch, le CRM de folk, l'outbound de Lemlist ou la polyvalence de ChatGPT. La différenciation vient de la continuité, de la traçabilité, de la qualité de restitution et de l'accompagnement.

## 11. Cinq risques majeurs

1. **Dérive de schéma silencieuse.** Le cœur du brief et les émotions se perdent entre Psychologue et Ariane sans erreur.
2. **Reproductibilité et dépendances.** Une dépendance déclarée manque dans l'environnement et le code ne sait pas dégrader proprement.
3. **Promesse de chaîne non tenue.** La stratégie n'est pas activée par défaut dans Thomas et aucun E2E live complet n'est certifié.
4. **Fiabilité opérationnelle.** Tâches longues en processus, caches et threads locaux exposent à la perte de travail, aux blocages et aux temps de réponse difficiles à garantir.
5. **Dilution produit et sur-promesse.** « Quatre agents », CRM, prospection, social listening et création peuvent disperser l'équipe avant validation du cœur premium.

## 12. Cinq opportunités de différenciation

1. **Chaîne française preuve → décision → livrable**, là où les outils sont souvent spécialisés ou anglophones.
2. **Traçabilité de niveau conseil**, avec observations, preuves, contre-signaux et hypothèses visibles.
3. **Expérience premium accompagnée pour agences**, dossiers clients et restitutions prêtes à présenter.
4. **Comparaison multi-audiences et mémoire de décisions**, créant un actif cumulatif plutôt qu'une suite de prompts.
5. **Position responsable et sobre**, sans scraping opaque ni automatisation d'outbound prématurée, avec validation humaine et gouvernance des données.

## 13. Preuves principales

| Affirmation | Preuve | Niveau |
|---|---|---|
| Trois spécialistes principaux sont déclarés | `agents/catalog.py`, registre frontend | Prouvé |
| Prospect est un onglet/module, pas un spécialiste du catalogue backend | registre frontend et catalogue backend | Prouvé |
| Thomas ne fonctionne pas dans l'Executor générique | `Createur.run()` non implémenté, contrôle de l'Executor | Prouvé |
| Le schéma courant du brief diffère de celui lu par Ariane | `core/analyzer.py`, `agents/stratege.py`, fixture réelle | Prouvé |
| La stratégie est désactivée par défaut dans Thomas | composant React du Créateur | Prouvé |
| Les résolveurs principaux filtrent par utilisateur | routes et services de résolution | Fortement étayé |
| Les garde-fous chiffrés existent | `strategy_guard.py`, `creation/fact_guard.py`, tests | Prouvé |
| L'interface locale répond | contrôles HTTP 200 | Prouvé |
| Tests ciblés : 113 succès, 3 échecs | exécution pytest du 14 octobre 2026 | Prouvé |
| Prospect DEV a passé ses tests de persistance | rapport et traces de validation MVP 3 | Déclaré, validation antérieure récente |
| Les agences sont la meilleure cible initiale | données marché + adéquation workflow | Hypothèse à valider |

## 14. Avis de préparation au 21 octobre

**Statut : orange — démonstration guidée possible sous conditions, lancement public non recommandé.**

Conditions minimales : corriger les contrats de contexte, rendre l'environnement reproductible, effectuer un test live contrôlé de la chaîne, rendre visible l'usage de la stratégie dans Thomas, sécuriser la bêta privée et préparer un parcours de secours pré-calculé. La roadmap associée transforme ces conditions en portes de validation.

## 15. Sources réglementaires et plateformes

- CNIL, [La prospection commerciale par courrier électronique](https://www.cnil.fr/la-prospection-commerciale-par-courrier-electronique), 4 février 2022.
- CNIL, [Questions-réponses sur l'utilisation d'un système d'IA générative](https://www.cnil.fr/fr/les-questions-reponses-de-la-cnil-sur-lutilisation-dun-systeme-dia-generative), 18 juillet 2024.
- CNIL, [Fiche TPE/PME — les solutions d'IA](https://www.cnil.fr/sites/cnil/files/2025-03/tpe_pme_ficheia_3_les_solutions_d_ia_0.pdf), document diffusé en 2024/2025.
- CNIL, [Fiche TPE/PME — les précautions](https://www.cnil.fr/sites/cnil/files/2025-03/tpe_pme_ficheia_4_les_precautions_0.pdf), document diffusé en 2024/2025.
- LinkedIn, [User Agreement](https://www.linkedin.com/legal/user-agreement), version effective au 3 novembre 2025.
- LinkedIn, [Prohibited software and extensions](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software?lang=en), consulté le 14 octobre 2026.
