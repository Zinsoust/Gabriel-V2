# Validation réelle du cœur Gabriel — scénarios préparés

Ces scénarios ne doivent être exécutés qu'après autorisation explicite des appels IA et confirmation des modèles/tarifs actifs. Ils utilisent un compte de test et des données fictives ou dont l'utilisation est autorisée.

## Prérequis communs

- environnement de préproduction séparé de DEV et de la production ;
- `AUTH_ENABLED=true`, rate limiting actif et compte A / compte B créés ;
- migrations du cœur et politiques RLS vérifiées sur la préproduction ;
- Prospect absent de la navigation et ses routes en 404 ;
- journal de test contenant les identifiants techniques, durées, modèles et consommation, sans contenu sensible ;
- plafond de dépense temporaire défini avant le lancement.

Le coût maximal doit être calculé juste avant le test : somme, pour chaque appel, de `(tokens entrée × tarif entrée) + (tokens sortie × tarif sortie)`. Arrêter si le plafond validé est atteint. Aucun appel n'a été effectué lors de la préparation de ce document.

## Scénario A — chaîne neuve dans un seul dossier

1. Le compte A crée un dossier et importe un jeu autorisé de 100 à 150 commentaires.
2. Le Psychologue produit et sauvegarde une analyse.
3. Depuis cette analyse, l'utilisateur ouvre Ariane et génère une stratégie.
4. Depuis le rapport d'Ariane, il clique sur « Le Créateur » puis demande un script.
5. Il recharge chaque écran et rouvre le même dossier.
6. Le compte B tente d'ouvrir les identifiants produits par le compte A.

Critères d'acceptation :

- 100 % des réponses HTTP attendues sont en 2xx ; aucun 5xx ;
- `analysis_id`, `strategy_id` et `folder_id` restent associés au même dossier ;
- le rapport d'Ariane reprend les champs `qui`, `insight`, `action`, les mesures de sentiment et l'émotion dominante du Psychologue ;
- Thomas affiche « Activée depuis Ariane » et sa requête contient `use_strategy=true` avec le bon `strategy_id` ;
- le contenu produit reprend au moins deux décisions identifiables de la stratégie, vérifiées par un évaluateur humain, sans fait inventé ;
- après rechargement, analyse, stratégie et création sont retrouvées ;
- toutes les lectures du compte B répondent 401/403/404 et ne divulguent aucune donnée ;
- durée et consommation restent sous les seuils décidés avant le test.

## Scénario B — compatibilité, autonomie et erreur contrôlée

1. Le compte A recharge une analyse historique au contrat `brief.v1`, puis ouvre Ariane.
2. Il ouvre Thomas directement dans un autre dossier et génère sans Psychologue ni Ariane.
3. Il active manuellement une stratégie valide dans son dossier courant.
4. Le test envoie ensuite volontairement un couple `folder_id` / `strategy_id` incohérent.
5. Une interruption réseau simulée survient pendant une génération, puis l'écran est rechargé.

Critères d'acceptation :

- l'analyse historique est adaptée sans perdre synthèse, insight ni action ;
- Ariane fonctionne sans analyse si son entretien business est complet ;
- Thomas fonctionne seul avec `use_psycho=false` et `use_strategy=false` ;
- une stratégie ne s'active jamais automatiquement lors d'une ouverture directe de Thomas ;
- le couple incohérent est refusé en 409 avec `strategy_context_mismatch`, avant tout appel IA ;
- une coupure affiche une erreur actionnable et ne lance pas une seconde génération payante à l'insu de l'utilisateur ;
- aucun contexte du dossier précédent n'apparaît dans les prompts, journaux fonctionnels ou résultats.

## Preuves à conserver

- capture des écrans de sources actives de Thomas ;
- réponses API expurgées des contenus sensibles ;
- table de correspondance `folder_id → analysis_id → strategy_id → creator_output_id` ;
- résultats du contrôle d'isolation A/B ;
- métriques de durée, tokens et coût par étape ;
- version Git exacte et versions des dépendances.
