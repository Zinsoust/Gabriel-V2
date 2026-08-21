# Gabriel Design System

> Extrait du code réel (`static/css/gabriel.css`, `docs/gabriel-design-language.html`) et des composants livrés cette session dans `templates/stratege.html` et `templates/psychologue.html`. Une décision explicite de direction a été prise en cours de route : **l'ivoire/blanc devient la surface principale**, pas seulement un thème alternatif — voir § Notes de migration en bas de fichier.

## 1. Atmosphere & Identity

Gabriel est une salle de conseil, pas un tableau de bord SaaS. La signature est un fond ivoire chaud plutôt que blanc pur, des surfaces en verre dépoli aux bords généreusement arrondis, et un seul accent — le champagne — réservé aux décisions, jamais généralisé en couleur de marque. Le sombre (noir chaud) reste un mode supporté, pas la valeur par défaut. Chaque écran répond à une seule question ; la confiance prime sur l'impression.

**Key Characteristics :**
- Ivoire comme surface par défaut ; le noir chaud n'apparaît qu'en bande volontaire (clôture d'une restitution, jamais en fond de page courant).
- Une seule couleur de marque à la fois : le champagne ne partage jamais l'écran avec une deuxième couleur chromatique décorative.
- La couleur arrive par la donnée (jauge, pastille de statut, écart de score), jamais par une surface d'UI colorée sans raison.
- Système globalement plat : la profondeur vient de l'alternance de surfaces et d'un filet fin, l'ombre est réservée aux cartes qui portent une vraie décision.
- Honnêteté structurelle : un composant vide ne se remplit jamais d'un placeholder inventé — il disparaît.

## 2. Color

### Palette

| Role | Token | Light (défaut) | Dark | Usage |
|---|---|---|---|---|
| Surface/primary | `--bg-main` | `#FCFBF9` | `#050403` | Fond de page |
| Surface/secondary | `--bg-card` | `#FFFFFF` | `#151514` | Cartes, panneaux |
| Surface/elevated | `--bg-card-hover` | `#FAF9F7` | `#1B1A18` | Survol, cartes soulevées |
| Surface/soft | `--bg-surface-soft` | `#F4F2EE` | `#211F1C` | Fonds internes discrets (badges, inputs) |
| Text/primary | `--text-primary` | `#111318` | `#F4F1EA` | Titres, corps |
| Text/secondary | `--text-secondary` | `#434951` | `#B8B1A6` | Sous-titres, descriptions |
| Text/tertiary | `--text-muted` | `#6D747D` | `#817A70` | Légendes, métadonnées |
| Text/disabled | `--text-disabled` | `#A0A5AC` | `#38383C` | États désactivés |
| Border/default | `--border-medium` | `rgba(17,19,24,.14)` | `rgba(244,241,234,.10)` | Séparations visibles |
| Border/subtle | `--border-soft` | `rgba(17,19,24,.08)` | `rgba(244,241,234,.055)` | Filets discrets |
| Accent/primary | `--champagne` | `#A5713F` | `#D8B982` | Décision, priorité, action principale — **rare**. Calibré sur une référence visuelle validée (caramel chaud, pas doré pâle). |
| Accent/hover | `--champagne-dark` | `#7A4D28` | `#F1D7A8` | Survol d'un élément déjà champagne ; bas de dégradé sur une carte champagne pleine |
| Accent/soft | `--champagne-soft` / `--champagne-light` | `#C99968` | `#C7A66B` | Icônes/texte à faible poids ; haut de dégradé sur une carte champagne pleine |
| Status/success | `--color-opportunity` | `#6BBF8A` | `#6BBF8A` | Invariant — indicateur atteint, opportunité |
| Status/error | `--color-risk` | `#D06A6A` | `#D06A6A` | Invariant — risque, écart, alerte |
| Status/warning | `--color-warning` *(nouveau)* | `#B8863A` | `#D9A441` | À utiliser pour les avertissements non bloquants — absent du code existant, ajouté ici pour combler un vrai manque |
| Status/info · interactif | `--accent-blue` | `#111111` (= encre) | `#5B8ED0` | **Asymétrique par design** : en clair, l'interactif reste monochrome (encre) pour ne jamais introduire une 2ᵉ couleur de marque ; en sombre, un bleu mat porte les liens/focus. |

### Accents de bureau (identité par agent, distincts du champagne)

| Bureau | Token | Hex | Rôle |
|---|---|---|---|
| Psychologue | `--psycho` | `#C9986B` | Cabinet d'analyse — chaud, organique |
| Stratège | `--stratege` | `#8A9099` | Salle de conseil — étain sobre |
| Créateur | `--createur` | `#D0895E` | Studio créatif — terracotta vif |
| Hall / Orchestrateur | `--hall` | `#D8B982` | Accueil — champagne discret (= accent principal) |

### Rules
- L'ivoire/blanc est la surface **par défaut** de toute nouvelle page ; le sombre reste accessible via `[data-theme="dark"]`, jamais l'inverse.
- Le champagne ne s'utilise que pour une décision, une priorité ou l'action principale d'un écran — jamais comme couleur de fond généralisée ni répétée sur chaque icône de section.
- L'accent d'un bureau (Psycho/Stratège/Créateur) sert à ses propres icônes de section ; il ne remplace jamais le champagne sur un vrai moment de décision, et le champagne ne remplace jamais l'accent du bureau sur une icône structurelle.
- `--accent-blue` n'est PAS une deuxième couleur de marque en thème clair : il y vaut l'encre. Ne pas "corriger" cette asymétrie sans décision explicite.
- Jamais de couleur hors de cette table. L'étendre d'abord si un besoin réel apparaît.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Police | Usage |
|---|---|---|---|---|---|---|
| Display | 48px | 300 | 1.0 | -0.02em | Fraunces | Titre de restitution, moment de décision |
| H1 | 36px | 400 | 1.05 | -0.015em | Fraunces | Ouverture de page |
| H2 | 27px | 500 | 1.15 | -0.01em | Inter | Titre de section (`.page-heading`) |
| H3 | 20px | 500 | 1.2 | 0 | Inter | Sous-section, carte mise en avant |
| Body/lg | 16px | 400 | 1.6 | 0 | Inter | Paragraphe d'intro |
| Body *(défaut réel)* | 13px | 400 | 1.6 | 0 | Inter | Texte courant — Gabriel tourne en base 13px, pas 16px |
| Body/sm | 12px | 400 | 1.5 | 0 | Inter | Descriptions secondaires |
| Caption | 10.5px | 600 | 1.4 | 0.03em | Inter | Libellés, métadonnées |
| Overline | 9–10px | 700 | 1.3 | 0.1–0.16em | Inter | Kickers, en-têtes de carte, tout en majuscules |
| Mono Label *(nouveau)* | 10.5px | 500 | 1.4 | 0.02em | IBM Plex Mono | Identifiants techniques, horodatage, noms de champ (`confidence_score`, `job_id`) |

### Font Stack
- Primaire (`--font-main`) : `'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- Serif éditoriale (`--font-serif`) : `'Fraunces', Georgia, 'Times New Roman', serif`
- Mono *(nouveau)* : `'IBM Plex Mono', 'SF Mono', ui-monospace, monospace` — comblait un vrai manque : Gabriel affiche déjà des identifiants et noms de champs techniques (traces de raisonnement, IDs d'analyse) sans police dédiée, en Inter par défaut. Réservé aux marqueurs techniques, jamais à un titre ou un corps de texte.

### Rules
- Deux familles maximum par écran (trois si un marqueur mono ponctuel apparaît, jamais plus) : Fraunces pour un seul moment fort (titre, citation de décision), Inter pour tout le reste.
- Le serif ne descend jamais sous 20px — en dessous, toujours Inter.
- Le corps de texte ne descend jamais sous 12px.
- Les chiffres qui s'alignent (pourcentages, prix, dates) utilisent `font-variant-numeric: tabular-nums`.
- Le mono reste discret : jamais en majuscules décoratives généralisées, réservé aux vrais identifiants techniques.

## 4. Spacing & Layout

### Base Unit
Échelle cible **8px** (`docs/gabriel-design-language.html`, déjà posée comme source de vérité) : le code existant tourne encore sur une échelle 6/12/20/32/48/72 en migration — tout nouveau composant utilise l'échelle ci-dessous, pas l'ancienne.

| Token | Value | Usage |
|---|---|---|
| `--space-1` | 8px | Icône-à-libellé, espacement minimal |
| `--space-2` | 16px | Groupes compacts, listes |
| `--space-3` | 24px | Padding intérieur de carte (défaut) |
| `--space-4` | 32px | Entre groupes de cartes |
| `--space-5` | 48px | Sections dans une page |
| `--space-6` | 64px | Rupture de section majeure |
| `--space-7` | 96px | Rythme vertical de page |
| `--space-8` | 128px | Séparation maximale, moments hero |

### Grid
- Largeur de contenu max : 1320px (restitutions), 810px (formulaires/composer)
- Colonnes : grille 12 colonnes pour les tableaux de bord (`repeat(12, minmax(0,1fr))`)
- Breakpoints réels : 560px, 640px, 700px, 860px, 980px — pas de grille fixe unique, adapter au composant

### Rules
- Aucun nombre magique : toute valeur d'espacement se mappe sur un token ci-dessus.
- Rayons : **20px** pour cartes/panneaux, **12px** pour pastilles/champs/boutons — cible déclarée par `docs/gabriel-design-language.html`. Le code existant utilise encore 3–8px par endroits (`--radius-sm/md/lg/xl`) ; tout nouveau composant suit 20/12, pas l'ancien.

## 5. Components

Composants réels, livrés dans `templates/stratege.html` et `templates/psychologue.html`.

### Confidence Gauge (jauge de confiance)
- **Structure** : `<svg>` — arc `stroke-dasharray="226.2"`, `stroke-dashoffset` calculé `226.2 × (1 − score)`. Nombre en `Inter` gras au centre.
- **Variants** : `--ok` (champagne, score du Stratège), `--risk` (rouge, relecture critique indépendante). Toujours affichées en paire quand les deux scores existent.
- **Spacing** : padding carte `--space-3` (24px), gap entre les deux jauges 1px (filet de séparation).
- **States** : n'apparaît QUE si les deux valeurs sources existent (`confidence_score` et `confidence_score_independant`) — jamais un chiffre inventé pour remplir l'espace.
- **Accessibility** : le pourcentage est aussi un texte lisible, pas seulement une forme.
- **Motion** : remplissage animé 1s `cubic-bezier(.2,.8,.2,1)` au premier affichage.

### Priority List (liste « Priorités »)
- **Structure** : lignes en grille `titre | signal | impact | délai`, alignement en colonnes.
- **Variants** : aucun — un seul style, volontairement sans cadre.
- **Spacing** : padding vertical 12px par ligne, filet `--border-soft` entre les lignes.
- **States** : liste vide → la carte entière ne s'affiche pas (pas de placeholder "aucune priorité").
- **Accessibility** : ordre de lecture = ordre d'impact, pas besoin d'aria-label supplémentaire.

### Status Pill (pastille de statut)
- **Structure** : point de 5–6px + libellé, fond teinté à 12–14 %.
- **Variants** : `--risk` (rouge, "à surveiller"), `--ok` (vert, "fait").
- **States** : couleur uniquement si l'état est réellement connu — jamais de pastille neutre coloriée par défaut.

### Price Position Scale (échelle de positionnement prix)
- **Structure** : barre 4–5px avec remplissage dégradé, 4 étapes fixes (Entrée / Milieu / Premium / Ultra-premium).
- **Variants** : aucun.
- **States** : ne s'affiche que si `pricing_logic.positionnement` correspond exactement à une des 4 étapes connues — sinon la carte reste sans échelle plutôt que d'inventer une position.
- **Motion** : largeur animée depuis 0 au premier affichage (1.1s).

### Editorial Numbered List (plan par phases)
- **Structure** : numéro (`01`/`02`/`03`) en colonne fixe 56px + contenu (titre, période, sous-listes Objectifs/Tâches/Livrables/KPIs/Décisions).
- **Variants** : aucun — toutes les phases à égalité, sans phase "active" simulée (aucun champ de statut réel dans les données).
- **Spacing** : padding vertical 22px par phase, filet `--border-soft` entre phases.

### Composer Bar (barre de saisie intégrée — Psychologue)
- **Structure** : bascule de vue (icônes rondes) + chips de mode (Analyser une audience / Cross-analyse) → champ central qui change selon la source → rangée de sources (pastilles) + bouton d'action.
- **Variants** : source active = `Commentaires` / `YouTube` / `Instagram` / `TikTok` / `Fichier` ; `Google` désactivé avec libellé explicite (pas de faux bouton actif).
- **States** : default, hover, active (pastille remplie), disabled (source pas encore branchée) — jamais un état "actif" sur une fonctionnalité qui ne fait rien.
- **Accessibility** : `aria-label` sur les boutons icône, `role="tablist"`/`role="tab"` sur le sélecteur de plateforme.

### Selection Chip (chip de sélection)
- **Structure** : pilule 8px/14px, coche à gauche si sélectionnée.
- **Variants** : sélectionné (fond `--champagne` plein, texte blanc, icône coche blanche) ; non sélectionné (fond blanc, bordure `--border-medium`, texte `--text-secondary`, icône `+`).
- **States** : le nombre de chips sélectionnées n'est jamais limité artificiellement ; l'ordre suit la pertinence, pas l'ordre alphabétique.
- **Usage réel** : sélection de signaux/plateformes à analyser (Psychologue), sélection de sources en Cross-analyse.

### Full-Gradient Badge Card (carte à dégradé plein)
- **Structure** : carte pleine largeur, dégradé `linear-gradient(150deg, --champagne-soft, --champagne, --champagne-dark)` + un halo radial blanc très doux (`rgba(255,224,190,.5)`) en haut à droite, radius 24px. Badge "Vérifié"/statut en pilule translucide (`rgba(255,255,255,.22)` + `backdrop-filter: blur(6px)`) en haut, texte blanc en bas.
- **Variants** : un seul — réservé à une carte par écran maximum, jamais plusieurs cartes pleines champagne côte à côte.
- **States** : le badge du haut n'affiche "Vérifié" que si un vrai statut de vérification existe côté données.
- **Usage réel** : moment de confiance/validation (ex. relecture critique validée, offre confirmée) — pas un simple habillage décoratif.

### Premium Card Frame (cadre de carte)
- **Structure** : fond `--bg-card` + léger dégradé interne (`color-mix` 1–3 % de `--text-primary`) + une seule ombre.
- **Variants** : `--priority` (bordure teintée champagne, réservée aux cartes de décision réelle).
- **States** : `:hover` révèle un halo radial très doux (opacity 0→1, 0.22s).

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|---|---|---|---|
| Micro | 150–220ms | ease | Survol de carte, halo au hover |
| Standard | 340ms | `cubic-bezier(.22,1,.36,1)` | Apparition de carte (`gb-slide-up`) |
| Reveal | 700ms | `cubic-bezier(.2,.7,.2,1)` | Entrée de section au scroll |
| Emphasis | 1000–1300ms | `cubic-bezier(.2,.8,.2,1)` | Remplissage de jauge, de barre de prix |

### Rules
- Seuls `transform` et `opacity` s'animent — jamais une propriété de layout.
- `prefers-reduced-motion: reduce` coupe systématiquement les animations non essentielles (déjà respecté dans le code de restitution Stratège).
- Les révélations au scroll utilisent `IntersectionObserver`, jamais un listener de scroll brut.
- GSAP est déjà chargé sur les pages de restitution — le réutiliser plutôt que d'ajouter une seconde librairie d'animation.

## 7. Depth & Surface

### Strategy
**Globalement plat, filet par défaut.** La profondeur vient d'abord de l'alternance de surfaces (`bg-main` → `bg-card` → `bg-card-hover`) et d'un filet fin, pas d'un empilement d'ombres. L'ombre n'apparaît que sur les cartes qui portent une vraie décision (`--priority`) — jamais comme habillage générique de "carte = ombre". Si un écran a plus d'une ombre visible à l'écran, c'est probablement trop.

| Level | Value | Usage |
|---|---|---|
| Filet | `1px solid var(--border-soft)` | Séparation par défaut entre blocs |
| Carte | `inset 0 1px 0 color-mix(in srgb, var(--text-primary) 3.5%, transparent)` | Reflet intérieur discret, toutes les cartes |
| Carte prioritaire | `0 10px 44px rgba(0,0,0,.2)` + dégradé interne champagne 6–8% | Réservée aux cartes `--priority` (décision réelle) |
| Verre *(exploration validée, pas encore câblée)* | fond blanc 50–65% + `backdrop-filter: blur(16–22px)` + bordure blanche 70% | Direction en cours de test — voir note de migration |

---

## Do's and Don'ts

### Do
- Utiliser l'ivoire comme surface par défaut de toute nouvelle page ; le noir chaud n'intervient qu'en bande volontaire et rare (ex. clôture d'une restitution).
- Réserver le champagne à une décision, une priorité ou l'action principale d'un écran — un seul par écran.
- Laisser la donnée porter la couleur (jauge, pastille, écart de score) plutôt que d'habiller l'UI elle-même.
- Faire disparaître un composant plutôt que d'inventer une valeur pour le remplir (voir Section 5, chaque composant).
- Garder les cartes plates par défaut ; n'ajouter une ombre qu'à une carte `--priority` qui porte une vraie décision.
- Utiliser le mono uniquement pour un identifiant technique réel, jamais pour styliser un simple libellé.

### Don't
- Ne pas introduire de deuxième couleur de marque en thème clair — `--accent-blue` y vaut l'encre, par choix.
- Ne pas empiler plusieurs ombres visibles sur un même écran.
- Ne pas répéter le champagne sur chaque icône de section — c'est l'accent du bureau (Psycho/Stratège/Créateur) qui les porte.
- Ne pas reproduire l'ancienne échelle d'espacement/rayons (6/12/20/32/48/72 · 3–8px) dans du code neuf.
- Ne pas fabriquer une phase "active", une position ou un score qui n'existe pas dans les données réelles pour combler un vide visuel.
- Ne pas ajouter une police sans un vrai besoin documenté ici — le mono a été ajouté parce qu'un besoin réel existait, pas par principe.

## Notes de migration (à lire avant de coder)

- **Direction actée cette session** : l'ivoire/blanc remplace le noir comme surface par défaut. Ce n'était pas le cas avant — `docs/gabriel-design-language.html` documentait un monde unique sombre. Ce fichier prime sur ce point précis ; le reste de `gabriel-design-language.html` (lois, voix, mouvement) reste valide.
- **Rayons et espacement** : le code livré utilise encore l'ancienne échelle (rayons 3–8px, espacement 6/12/20/32/48/72). Ne pas la reproduire dans du code neuf — suivre les tables des §3–4 ci-dessus. Migrer page par page, jamais tout d'un coup.
- **Verre (glassmorphism)** : exploré et validé visuellement dans une maquette (Space Grotesk, halos champagne/bleu/rouge très doux sur fond ivoire), mais pas encore implémenté dans le vrai code. À câbler composant par composant plutôt que de réécrire une page entière.
- **Space Grotesk** : accueilli favorablement en exploration mais pas encore adopté comme police de titre officielle — Fraunces reste la police serif documentée ici tant qu'une décision explicite ne la remplace pas.
- **Dégradé d'accueil (onboarding)** : le fond dégradé doux `--grad-1 #F3E3D5 → --grad-2 #E7CAAC` (validé sur référence visuelle) est réservé aux écrans d'accueil/onboarding avec cartes flottantes — jamais le fond des tableaux de bord Stratège/Psychologue, qui restent plats sur `--bg-main` par la règle de la Section 7.
- **Cartes blanches solides, pas de verre** : la référence validée pour l'onboarding montre des cartes blanches opaques avec ombre douce, pas de glassmorphism translucide. L'exploration verre dépoli précédente reste une piste distincte, non retenue pour ce pattern précis.
