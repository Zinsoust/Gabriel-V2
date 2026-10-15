# Gabriel — Cahier des charges produit V1

**Version :** 1.0 — 14 octobre 2026  
**Statut :** proposition de cadrage pour la bêta privée accompagnée du 21 octobre 2026  
**Portée :** produit Gabriel, avec Gabriel Prospect comme module complémentaire  

## 1. Résumé du produit

Gabriel est une plateforme premium d'intelligence d'audience qui transforme des conversations et signaux d'audience autorisés en décisions marketing traçables, puis en livrables prêts à produire.

La promesse centrale n'est pas « quatre agents IA ». Elle est :

> **Partir de preuves issues d'une audience réelle, décider quoi dire et pourquoi, puis produire un contenu cohérent — dans un même dossier, en français, avec validation humaine.**

Le produit est présenté autour de quatre agents ou composantes visibles, avec des responsabilités distinctes :

| Agent ou composante | Responsabilité produit | État V1 |
|---|---|---|
| **Le Psychologue** | analyser les signaux d'audience, émotions, tensions, objections et personas | existant, à fiabiliser de bout en bout |
| **Ariane, la Stratège** | convertir les preuves d'audience en décisions, positionnement et plan d'action | existant, transmission de contexte partielle |
| **Thomas, le Créateur** | convertir l'audience et la stratégie en livrables éditoriaux | existant via son parcours spécialisé, orchestration générique partielle |
| **Gabriel Prospect** | organiser le développement commercial et la relation avec des prospects | MVP 3 persistant en DEV ; automatisations futures absentes |

Cette présentation produit ne signifie pas que les quatre éléments partagent aujourd'hui la même architecture technique : Gabriel Prospect est un module complémentaire indépendant du registre backend des trois spécialistes principaux.

La chaîne prioritaire est :

1. **Le Psychologue** analyse les signaux d'audience et fait émerger tensions, motivations, objections, émotions et personas.
2. **Ariane, la Stratège** transforme ces éléments en choix marketing : positionnement, offre, message, canaux et plan d'action.
3. **Thomas, le Créateur** transforme la stratégie et la connaissance d'audience en un livrable éditorial exploitable.

**Gabriel Prospect** est un module complémentaire de développement commercial. Son MVP 3 dispose d'une persistance DEV validée, mais la recherche Web, l'enrichissement à grande échelle, l'emailing et les relances automatiques sont des fonctionnalités futures. Elles ne font pas partie de la promesse V1.

## 2. Objectifs de la bêta privée

La bêta du 21 octobre 2026 est une validation produit guidée, pas une commercialisation publique.

Elle doit vérifier quatre hypothèses :

- un utilisateur comprend rapidement la continuité **preuve → insight → décision → livrable** ;
- la chaîne apporte une qualité supérieure à un assemblage manuel de chatbots généralistes ;
- la traçabilité des sources et la validation humaine créent de la confiance ;
- une agence ou un consultant réutiliserait ce flux sur plusieurs clients et accepterait de payer pour le gain de temps et la qualité obtenue.

La bêta ne doit pas chercher à valider simultanément un CRM complet, une plateforme de social listening exhaustive, un outil d'outbound automatisé et une usine à contenus.

## 3. Cible initiale proposée

### 3.1 Recommandation

La meilleure cible initiale à tester est celle des **petites agences de stratégie, contenu, acquisition ou branding, de 2 à 20 personnes**, avec les consultants marketing indépendants comme cohorte secondaire.

Cette recommandation est une hypothèse à valider, pas une décision définitive.

### 3.2 Justification

| Critère | Agences | Indépendants | Créateurs | PME généralistes |
|---|---:|---:|---:|---:|
| Répétition du besoin | 5/5 | 3/5 | 3/5 | 4/5 |
| Adéquation à la chaîne Gabriel | 5/5 | 4/5 | 4/5 | 3/5 |
| Disposition à payer présumée | 4/5 | 2/5 | 2/5 | 4/5 |
| Simplicité d'onboarding | 4/5 | 5/5 | 5/5 | 2/5 |
| Facilité d'accès au segment | 3/5 | 4/5 | 4/5 | 2/5 |

Les agences ont un travail récurrent, plusieurs dossiers clients, un besoin de livrables présentables et une douleur tangible liée à l'assemblage de plusieurs outils. Elles peuvent mesurer le temps économisé à chaque mission. Les indépendants sont utiles pour accélérer les boucles de retour, mais leur panier moyen probable est inférieur. Les créateurs ont un accès direct à leur audience mais disposent de nombreux substituts gratuits ou peu coûteux. Les PME représentent un marché plus vaste, mais leur hétérogénéité, leurs contraintes d'intégration et leur besoin d'accompagnement allongent le cycle d'adoption.

Cette orientation est cohérente avec le Baromètre France Num 2026 : l'adoption de l'IA est particulièrement élevée dans les services spécialisés et techniques, tandis que les utilisateurs payants déclarent plus fréquemment un impact positif. L'étude qualitative France Num 2025 souligne aussi le besoin d'accompagnement de bout en bout, de formation accessible et de cas d'usage concrets. Les sources et leurs limites sont détaillées dans [l'audit](GABRIEL_AUDIT_PRODUIT_ET_TECHNIQUE.md).

### 3.3 Validation requise

Avant d'en faire l'ICP officiel, mener :

- 12 à 15 entretiens avec décideurs et opérateurs d'agences ;
- 6 à 8 observations d'une mission réelle, depuis les données brutes jusqu'au livrable client ;
- 3 tests de volonté de payer avec une offre et un prix explicites ;
- une comparaison chronométrée avec leur méthode actuelle.

## 4. Utilisateurs et tâches prioritaires

### Persona A — Dirigeant ou directeur conseil d'une petite agence

**Objectif :** produire une recommandation convaincante et différenciante sans mobiliser plusieurs jours d'analyse.  
**Douleurs :** informations dispersées, synthèses génériques, difficulté à relier recommandations et verbatims, multiplication des outils, restitution client chronophage.  
**Résultat attendu :** une décision défendable et un livrable de qualité, réutilisables dans le dossier client.

### Persona B — Stratège ou consultant marketing indépendant

**Objectif :** augmenter la profondeur de ses recommandations sans sacrifier sa vitesse.  
**Douleurs :** recherche manuelle, prompts réécrits, perte de contexte, contrôle fastidieux des chiffres et affirmations.  
**Résultat attendu :** un flux structuré qui conserve les preuves, le contexte métier et les arbitrages.

### Persona C — Créateur ou responsable de contenu

**Objectif :** produire un contenu qui ressemble réellement à l'audience et respecte la stratégie.  
**Douleurs :** contenus IA génériques, personas décoratifs, ton interchangeable, rupture entre recherche et rédaction.  
**Résultat attendu :** un brief fiable et un contenu dont les choix sont explicables.

### Persona D — Responsable marketing de PME

**Objectif :** comprendre ses clients et aligner ses actions.  
**Statut V1 :** cible d'exploration ultérieure, à aborder verticalement plutôt que comme un segment uniforme.

## 5. Principes produit

1. **La preuve avant la génération.** Toute recommandation importante doit être rattachable à une source, un signal ou une hypothèse explicitement marquée.
2. **Une chaîne, pas trois formulaires.** Le dossier, l'audience, la stratégie et le livrable doivent rester liés sans recopie manuelle.
3. **Le contrôle humain est une fonction, pas une mention légale.** L'utilisateur doit pouvoir voir, corriger, accepter ou rejeter les hypothèses.
4. **La qualité prime sur le volume.** Gabriel n'est pas une fabrique de contenus en masse.
5. **La simplicité visible masque la sophistication interne.** Les étapes techniques et agents secondaires ne doivent pas encombrer l'expérience.
6. **Aucune promesse de données non disponibles.** Les sources, leur fraîcheur, leur couverture et leurs limites doivent être affichées.
7. **Le français est un avantage de conception.** Le vocabulaire, les nuances culturelles, les exemples et les livrables doivent être conçus pour ce marché, pas simplement traduits.

## 6. Parcours produit cible

### Étape 1 — Créer un dossier de décision

L'utilisateur nomme le client ou le projet, formule la décision à prendre et renseigne le contexte métier minimal : offre, audience supposée, objectif, contraintes et ton.

**Exigence :** afficher la finalité et la durée de conservation des données ; ne collecter que ce qui est utile.

### Étape 2 — Ajouter une source autorisée

Sources cibles V1 : commentaires fournis par l'utilisateur, fichiers importés et collectes via intégrations officiellement autorisées.

**Exigences :**

- montrer la provenance, la date, le volume et les limites de l'échantillon ;
- interdire toute collecte non autorisée ou contournement de plateforme ;
- permettre d'exclure des données sensibles ou hors sujet avant analyse.

### Étape 3 — Explorer l'audience avec le Psychologue

Présenter d'abord les observations robustes, puis les interprétations, puis les hypothèses. Les personas doivent être reliés aux clusters et verbatims qui les fondent.

**Sorties minimales :**

- synthèse de l'audience ;
- tensions, motivations, objections et émotions ;
- segments/personas avec degré de confiance ;
- verbatims ou références probantes ;
- limites et contre-signaux ;
- brief normalisé transmis à la stratégie.

### Étape 4 — Décider avec Ariane

Ariane reçoit automatiquement le même dossier, l'analyse sélectionnée et le contexte métier. Elle doit expliciter ce qui vient des données, ce qui relève d'une inférence et ce qui constitue un choix stratégique.

**Sorties minimales :**

- décision centrale et renoncements associés ;
- positionnement, promesse et message ;
- offre ou angle prioritaire ;
- canaux et actions à court terme ;
- risques, hypothèses à tester et métriques ;
- traçabilité vers les insights utilisés.

### Étape 5 — Produire avec Thomas

Le passage depuis Ariane doit activer explicitement et automatiquement la stratégie courante, tout en laissant l'utilisateur la désactiver. Le persona et le format choisis doivent être visibles.

**Sorties minimales :**

- un livrable adapté au canal ;
- un lien visible vers la stratégie et les insights mobilisés ;
- un contrôle des chiffres et affirmations sensibles ;
- des options de révision ciblées plutôt qu'une régénération opaque.

### Étape 6 — Valider et capitaliser

L'utilisateur approuve, corrige ou rejette les éléments. Le dossier conserve les décisions, versions, retours et résultats observés afin d'améliorer les missions futures.

## 7. Périmètre fonctionnel

### 7.1 Fonctionnalités existantes et démontrables sous conditions

- analyse de commentaires et fichiers par le Psychologue ;
- analyses simples et comparatives, personas, émotions et recommandations ;
- création d'une stratégie à partir d'une analyse enregistrée ou d'un entretien de cadrage ;
- génération et révision de plusieurs formats de contenu par Thomas ;
- historique et persistance des analyses, stratégies et créations ;
- contrôles de chiffres non sourcés dans les étapes Stratégie et Création ;
- module Prospect MVP 3 en DEV : import, persistance, déduplication, statuts, historique, isolation utilisateur et opposition.

Ces capacités ne constituent pas encore une preuve que le parcours complet fonctionne de bout en bout : l'audit a identifié des ruptures P0 détaillées dans le document technique.

### 7.2 Fonctionnalités partielles

- orchestration transverse : les routes spécialisées fonctionnent, mais l'exécuteur générique ne peut pas exécuter Thomas ;
- transmission Psychologue → Ariane : résolution sécurisée de l'analyse, mais perte silencieuse de champs du schéma actuel ;
- transmission Ariane → Thomas : stratégie disponible mais non activée par défaut après navigation ;
- traçabilité : forte sur certains contrôles, inégale sur les affirmations sémantiques ;
- mémoire : historique et contexte existent, sans gouvernance produit complète de la fraîcheur, du consentement et des versions ;
- Prospect : CRM DEV fonctionnel, sans recherche Web, enrichissement généralisé, emailing ou relances automatiques.

### 7.3 Vision future, non existante

- recherche d'entreprises et contacts via fournisseurs autorisés ;
- enrichissement contrôlé et documenté ;
- campagnes email et relances avec conformité, consentement/base légale, désinscription et limites de fréquence ;
- rapports clients en marque blanche et collaboration multi-utilisateur aboutie ;
- apprentissage mesuré à partir des résultats de campagnes ;
- connecteurs métiers et API publique ;
- traitement asynchrone durable et reprise après incident à grande échelle.

## 8. Exigences fonctionnelles V1

### F1 — Contrat de contexte unique

Un objet versionné doit relier `workspace`, `analysis`, `strategy`, `creation`, `persona`, `business_context` et leurs sources. Toute étape doit refuser un contexte incompatible plutôt que continuer silencieusement.

### F2 — Continuité visible

Chaque écran doit afficher : dossier actif, source active, analyse active, stratégie active et persona actif. Un changement de dossier doit invalider les transferts temporaires obsolètes.

### F3 — Traçabilité

Les affirmations clés doivent avoir un statut : **observé**, **inféré**, **hypothèse**, **décidé**. L'utilisateur doit pouvoir remonter jusqu'à la preuve disponible.

### F4 — Robustesse des schémas

Les échanges inter-agents utilisent des schémas versionnés et validés. Une clé manquante, renommée ou de type inattendu doit produire une erreur explicite et testée.

### F5 — Validation humaine

Aucune stratégie ou création n'est présentée comme vérité. L'utilisateur valide le livrable final et les contenus pouvant être publiés ou envoyés.

### F6 — Gestion des limites

L'interface expose taille d'échantillon, dates, biais possibles, langue, sources exclues, confiance et données manquantes.

### F7 — Historique et versions

Chaque transformation conserve ses références amont et son numéro de version. Les modifications de l'utilisateur ne doivent pas écraser la provenance initiale.

### F8 — Prospect responsable

Le module Prospect conserve les oppositions, applique l'isolation entre utilisateurs et bloque les actions interdites. Aucune automatisation d'envoi n'est activée dans la bêta.

## 9. Exigences non fonctionnelles

- **Sécurité :** authentification obligatoire en bêta, liste d'accès privée, séparation stricte DEV/production, secrets hors dépôt et journaux.
- **Confidentialité :** minimisation, information utilisateur, durée de conservation, suppression maîtrisée, interdiction de verser des données confidentielles non autorisées dans un fournisseur d'IA.
- **Fiabilité :** démarrage en environnement propre, dépendances verrouillées, reprise explicite des tâches longues et absence d'échec silencieux.
- **Performance :** un état d'avancement honnête pour toute tâche supérieure à dix secondes ; objectifs de délai établis après mesures réelles.
- **Accessibilité :** navigation clavier, contrastes, libellés explicites, retours d'erreur compréhensibles.
- **Observabilité :** identifiants de corrélation sans données sensibles, temps par étape, échecs, coûts de modèles et qualité perçue.
- **Réversibilité :** export des données et absence de verrouillage indu.

## 10. Critères de succès de la bêta

La bêta est concluante si, sur un jeu de données autorisé :

- 80 % des testeurs terminent le parcours sans intervention opérateur après une première démonstration ;
- 80 % identifient correctement la décision recommandée et ses preuves ;
- 70 % jugent le livrable de Thomas utilisable après moins de deux révisions ciblées ;
- aucune perte silencieuse de contexte n'est observée ;
- aucune affirmation chiffrée non sourcée n'est publiée comme un fait ;
- le temps total et le coût modèle sont mesurés et acceptables pour la valeur perçue ;
- au moins 3 utilisateurs sur 8 demandent à réutiliser Gabriel sur un autre dossier ;
- au moins 2 acceptent un test payant ou un engagement conditionnel à un prix explicite.

Les métriques de volume de contenu et de nombre d'agents invoqués ne sont pas des critères de succès.

## 11. Parcours de démonstration premium — cinq minutes

Ce parcours est la cible après correction et validation des P0. À la date de l'audit, il ne doit pas être présenté comme entièrement certifié.

1. **0:00–0:40 — La décision.** Ouvrir un dossier client fictif et poser une question concrète : « Quel angle d'offre et quel message cette audience est-elle prête à entendre ? » Montrer source, date, volume et autorisation.
2. **0:40–1:50 — La preuve.** Dans le Psychologue, montrer une tension, un verbatim relié, deux personas et une limite de l'échantillon.
3. **1:50–3:10 — Le choix.** Passer à Ariane avec le même identifiant d'analyse. Montrer la décision, le renoncement, le message et l'action recommandée cette semaine.
4. **3:10–4:30 — Le livrable.** Passer à Thomas avec la stratégie activée et un persona sélectionné. Ouvrir un script de 60 secondes ou un post LinkedIn pré-calculé, puis montrer une phrase directement reliée à l'insight.
5. **4:30–5:00 — La valeur.** Comparer visuellement : commentaire brut → insight → décision → phrase finale. Demander au testeur ce qu'il utiliserait, modifierait et paierait.

Pour la bêta guidée, utiliser un jeu de données fictif ou autorisé et des sorties « golden » pré-calculées. Une génération en direct peut être montrée uniquement après validation des dépendances, du contrat de contexte, des coûts et des délais. Prospect peut faire l'objet d'une seconde démonstration séparée ; il ne doit pas diluer cette histoire principale.

## 12. Hors périmètre recommandé

À reporter ou supprimer de la V1 :

- recherche Web générique et scraping non autorisé ;
- automatisation LinkedIn ;
- emailing et relances automatiques ;
- scoring prédictif de leads sans données suffisantes ;
- multiplication de nouveaux agents visibles ;
- marketplace de prompts ;
- social listening exhaustif en temps réel ;
- paiement public, crédits et packaging complexe avant validation de la valeur ;
- personnalisation graphique lourde avant fiabilité du flux principal.

## 13. Décisions ouvertes

Les dix arbitrages structurants sont formalisés dans [la roadmap priorisée](GABRIEL_ROADMAP_PRIORISEE.md). L'état réel, les preuves et les limites se trouvent dans [l'audit produit et technique](GABRIEL_AUDIT_PRODUIT_ET_TECHNIQUE.md).
