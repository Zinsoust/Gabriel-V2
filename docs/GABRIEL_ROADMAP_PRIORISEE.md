# Gabriel — Roadmap priorisée

**Version :** 1.0 — 14 octobre 2026  
**Horizon immédiat :** bêta privée accompagnée du 21 octobre 2026  
**Règle directrice :** fiabiliser la chaîne Psychologue → Ariane → Thomas avant d'élargir le produit.

## 1. Décision de cap proposée

Gabriel doit concentrer les six prochains mois sur un seul résultat : permettre à une petite agence ou à un consultant de transformer une audience autorisée en recommandation défendable puis en livrable, avec une trace claire des preuves et des choix.

Le module Prospect est maintenu comme complément utile et démonstrateur technique, mais il ne pilote pas la roadmap centrale. La recherche Web, l'enrichissement généralisé, les séquences email et les relances sont reportés tant que le cœur premium n'a pas obtenu de signal d'usage et de paiement.

## 2. Principes de priorisation

Une initiative avance si elle améliore au moins un de ces axes sans détériorer les autres :

1. fiabilité de la transmission de contexte ;
2. qualité et traçabilité du résultat ;
3. temps nécessaire pour obtenir une décision exploitable ;
4. compréhension et confiance de l'utilisateur ;
5. réutilisation du flux sur un second dossier.

Une initiative est reportée si elle ajoute principalement du volume, un nouvel agent, un nouveau canal ou une nouvelle intégration avant d'avoir prouvé l'usage du flux principal.

## 3. P0 — Avant la bêta du 21 octobre 2026

### P0.1 — Réparer et verrouiller le contrat Psychologue → Ariane

**Problème :** l'adaptateur lit l'ancien schéma du brief et de la distribution.  
**Action :** définir un schéma versionné, adapter les clés `qui`/`insight`/`action`, calculer les proportions à partir des comptes si nécessaire, et échouer explicitement sur une structure incompatible.  
**Validation :** test de contrat utilisant la fixture React réelle et une sortie produite par `core/analyzer.py`; aucune valeur centrale vide lorsque la source est renseignée.

### P0.2 — Rendre l'environnement reproductible et le démarrage explicite

**Problème :** `vaderSentiment` est déclaré mais absent du `venv`; l'erreur survient tardivement.  
**Action :** installation propre depuis les fichiers de dépendances, verrouillage des versions critiques, contrôle de démarrage et comportement de repli documenté.  
**Validation :** installation dans un environnement vierge, démarrage, analyse déterministe minimale et suite ciblée à 100 %. Tous les caches et index générés par les tests doivent être redirigés vers un dossier temporaire ; une exécution de tests ne doit jamais modifier le worktree.

### P0.3 — Garantir un contexte unique et visible dans l'interface

**Problème :** transfert `sessionStorage` potentiellement périmé et stratégie désactivée par défaut dans Thomas.  
**Action :** lier le transfert au dossier et à une version, le consommer/expirer, afficher les identifiants fonctionnels actifs, activer la stratégie lors du passage depuis Ariane et permettre une désactivation volontaire.  
**Validation :** tests frontend de changement de dossier, retour arrière, rafraîchissement et passage Ariane → Thomas ; aucun contexte ancien réutilisé silencieusement.

### P0.4 — Certifier une chaîne réelle contrôlée

**Problème :** aucun test live complet n'a été autorisé ou exécuté pendant l'audit.  
**Action :** après autorisation explicite des appels payants, exécuter un jeu de données fictif/autorisé et conserver la lignée `analysis_id → strategy_id → creation_id`, les temps, coûts, erreurs et contrôles de qualité.  
**Validation :** deux exécutions consécutives réussies, résultat relisible après redémarrage, stratégie réellement injectée dans Thomas et chiffres non sourcés signalés.

### P0.5 — Fermer la bêta et préparer le mode dégradé

**Problème :** une démonstration guidée ne doit pas dépendre d'un service externe instable.  
**Action :** authentification active, liste d'accès, environnement DEV identifié, jeu golden autorisé, sorties pré-calculées, message clair si un fournisseur est indisponible, aucune action Prospect externe.  
**Validation :** revue du protocole de sécurité, répétition de la démonstration deux fois, test hors connexion aux fournisseurs et procédure de retour documentée.

### Porte de sortie P0

La bêta peut démarrer uniquement si :

- tous les tests ciblés passent ;
- le contrat de contexte est couvert par tests ;
- un parcours complet réel a réussi avec traçabilité ;
- aucune donnée ou secret n'apparaît dans les journaux ;
- le parcours golden reste disponible sans nouvel appel payant ;
- les testeurs sont informés du caractère expérimental et valident l'usage de leurs données.

## 4. Séquence de bêta — 21 octobre au 15 novembre 2026

### P1.1 — Observer avant d'ajouter

Organiser 6 à 8 sessions guidées avec agences/consultants. Mesurer : temps par étape, demandes d'aide, éléments consultés, corrections, confiance, réutilisation et volonté de payer.

### P1.2 — Rendre la preuve navigable

Ajouter une représentation uniforme observation/inférence/hypothèse/décision et des liens vers les verbatims ou sources. Ne pas ajouter de nouveau type d'analyse avant que les utilisateurs comprennent celui-ci.

### P1.3 — Simplifier le dossier

Unifier la sélection du dossier, de l'analyse, de la stratégie et du persona. Réduire les états implicites, les caches concurrents et les transferts temporaires.

### P1.4 — Instrumenter valeur, qualité et coût

Mesurer coût modèle par mission, délai médian/P95, taux d'échec, nombre de révisions, part du livrable conservée et score utilisateur. Ne pas optimiser le nombre d'appels sans mesurer le résultat.

### P1.5 — Formaliser confidentialité et rétention

Présenter sources, fournisseurs, finalités, durée de conservation, export/suppression et règles d'import. Ajouter une procédure simple d'incident et de demande utilisateur.

### Porte de sortie P1

- au moins 80 % des testeurs terminent le flux après une première prise en main ;
- au moins 70 % utilisent le livrable après deux révisions ou moins ;
- aucune confusion mesurée sur la source active ou l'usage de la stratégie ;
- au moins 3 testeurs demandent un deuxième dossier ;
- au moins 2 signaux de paiement à prix explicite.

## 5. Validation du marché — novembre à décembre 2026

### P2.1 — Valider l'ICP agence

Réaliser 12 à 15 entretiens et 6 à 8 observations de missions. Tester une proposition destinée aux agences, puis comparer à une cohorte d'indépendants et une petite cohorte de créateurs.

### P2.2 — Tester le packaging, pas seulement le prix

Comparer :

- mission accompagnée facturée ;
- abonnement par équipe/dossiers ;
- forfait hybride logiciel + onboarding ;
- essai limité à un dossier complet plutôt qu'à des crédits opaques.

Stripe et les crédits ne redeviennent prioritaires qu'après choix du packaging.

### P2.3 — Livrables agence

Prioriser, si les entretiens le confirment : rapport client partageable, marque blanche légère, commentaires/validation, duplication contrôlée d'un dossier et export propre. Ne pas développer un éditeur de présentation généraliste.

### P2.4 — Architecture des tâches longues

Séparer les traitements longs du processus Web, ajouter reprise, idempotence et progression persistante. Évaluer les contraintes de latence et de coût avant toute montée en charge.

### P2.5 — Évaluation qualité continue

Construire un corpus de référence français couvrant plusieurs audiences et formats. Évaluer dérive de schéma, fidélité aux preuves, cohérence stratégique, conservation du ton et chiffres non justifiés.

## 6. Horizon ultérieur — à partir de 2027, sous conditions

### À envisager seulement si le cœur est validé

- connecteurs officiels supplémentaires ;
- collaboration multi-utilisateur aboutie ;
- API et intégrations avec CRM/outils sociaux existants ;
- apprentissage à partir des résultats réellement observés ;
- Prospect enrichi via fournisseurs autorisés ;
- workflows d'outbound limités, conformes et contrôlés humainement.

### Conditions spécifiques à Prospect

Avant toute recherche ou séquence :

- base légale et information documentées ;
- provenance et fraîcheur des données visibles ;
- opposition persistante et centralisée ;
- contrôle de fréquence, identité et désinscription ;
- aucun scraping ou bot LinkedIn non autorisé ;
- validation humaine avant chaque campagne ;
- métriques de qualité des données et de plaintes.

## 7. Fonctionnalités à reporter ou supprimer

| Initiative | Décision proposée | Motif |
|---|---|---|
| Nouveaux agents visibles | Reporter | augmente la complexité avant fiabilité des trois spécialistes |
| Recherche Web Prospect générique | Reporter | conformité, qualité et catégorie déjà dense |
| Scraping/automatisation LinkedIn | Exclure | risque contractuel et réputationnel majeur |
| Emailing et relances autonomes | Reporter | conformité et preuve de valeur du CRM insuffisantes |
| Scoring prédictif de prospects | Reporter | données d'entraînement et vérité terrain insuffisantes |
| Social listening exhaustif temps réel | Ne pas construire | affrontement frontal avec acteurs spécialisés et coûts de données élevés |
| CRM généraliste | Ne pas construire | folk et de nombreux concurrents couvrent déjà ce besoin |
| Crédits complexes | Reporter | masquent le prix de la valeur et ajoutent de la friction |
| Paiement public | Reporter après validation | la bêta est privée, pas commerciale |
| Personnalisation visuelle extensive | Reporter | impact faible sur la preuve de valeur initiale |

## 8. Dix décisions stratégiques à arbitrer

1. **ICP primaire :** adopter provisoirement les petites agences comme cible principale, ou privilégier les indépendants pour la vitesse d'acquisition ?
2. **Promesse :** vendre « intelligence d'audience jusqu'au livrable » ou une partie plus étroite du flux ?
3. **Unité de valeur :** facturer par siège, dossier client, mission accompagnée ou abonnement hybride ?
4. **Niveau de service :** assumer un onboarding premium humain comme partie du produit, ou viser immédiatement le libre-service ?
5. **Sources V1 :** limiter volontairement les sources aux imports autorisés et à quelques API officielles, ou investir tôt dans la couverture ?
6. **Traçabilité :** rendre les preuves obligatoires même si cela allonge et densifie l'expérience, ou offrir un mode simplifié ?
7. **Architecture :** stabiliser les routes spécialisées comme produit, ou financer l'unification de l'orchestrateur et du contrat inter-agents ?
8. **Prospect :** le garder comme module secondaire intégré, le transformer en produit séparé, ou suspendre son expansion ?
9. **Position de confiance :** faire de la souveraineté/proximité et de la validation humaine un axe commercial fort, avec les coûts associés ?
10. **Critère de lancement public :** quel seuil mesurable — réutilisation, paiement, qualité et fiabilité — doit être atteint avant Stripe, crédits et acquisition large ?

## 9. Proposition de décision pour chaque arbitrage

1. Petites agences en ICP provisoire ; indépendants comme cohorte d'apprentissage.
2. Promesse complète mais étroite : une seule chaîne de décision, pas une suite omnicanale.
3. Tester mission accompagnée puis abonnement par équipe/dossiers ; éviter les crédits au départ.
4. Assumer l'accompagnement premium jusqu'à preuve d'un onboarding autonome.
5. Limiter les sources et rendre leur provenance excellente.
6. Rendre la trace obligatoire pour les affirmations centrales, avec affichage progressif.
7. Unifier d'abord le contrat de contexte ; différer une réécriture globale de l'orchestrateur.
8. Maintenir Prospect secondaire sans nouvelles automatisations.
9. Faire de la confiance un différenciateur démontrable, sans promesse de souveraineté non prouvée.
10. Exiger réutilisation, paiement explicite et deux parcours E2E consécutifs sans incident critique.

## 10. Parcours de démonstration et checklist

Le scénario détaillé figure dans le [cahier des charges](GABRIEL_CAHIER_DES_CHARGES_PRODUIT_V1.md). Pour la répétition :

- dossier et jeu de données fictifs ou autorisés ;
- question métier unique et concrète ;
- source, date, volume et limites visibles ;
- un insight relié à un verbatim ;
- une décision et un renoncement explicites ;
- stratégie activée et visible dans Thomas ;
- livrable pré-calculé disponible ;
- plan B sans fournisseur externe ;
- chronomètre inférieur à cinq minutes ;
- aucune démonstration Prospect mélangée au récit principal.

**Statut actuel : non certifié.** La dépendance VADER, le contrat Psychologue → Ariane et le passage Ariane → Thomas doivent être résolus, puis la chaîne doit être testée réellement avant toute affirmation contraire.

## 11. Tableau de pilotage recommandé

| Résultat | Indicateur | Seuil initial |
|---|---|---:|
| Compréhension | utilisateur explique correctement la décision et sa preuve | ≥ 80 % |
| Continuité | missions sans erreur ou contexte périmé | 100 % en bêta guidée |
| Utilité | livrable utilisable après ≤ 2 révisions | ≥ 70 % |
| Réutilisation | testeur demande un second dossier | ≥ 3 sur 8 |
| Volonté de payer | engagement à prix explicite | ≥ 2 testeurs |
| Fiabilité | deux parcours E2E consécutifs complets | 100 % |
| Traçabilité | affirmations centrales reliées ou marquées hypothèse | 100 % |
| Maîtrise économique | coût et temps par mission connus | 100 % des runs |

## 12. Ordre d'exécution recommandé

1. contrat de schéma et dépendances ;
2. continuité visible du dossier et activation de stratégie ;
3. tests de non-régression et E2E contrôlé ;
4. sécurité et répétition de démonstration ;
5. sessions de bêta observées ;
6. synthèse des apprentissages et décision ICP ;
7. test de packaging et volonté de payer ;
8. amélioration de la preuve et des livrables ;
9. architecture de résilience ;
10. seulement ensuite, arbitrage d'expansion de Prospect et des connecteurs.

Les constats détaillés et les sources sont regroupés dans [GABRIEL_AUDIT_PRODUIT_ET_TECHNIQUE.md](GABRIEL_AUDIT_PRODUIT_ET_TECHNIQUE.md).
