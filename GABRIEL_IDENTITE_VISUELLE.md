# Gabriel — Identité visuelle

Document de référence pour la production d'une vidéo motion design. Toutes les valeurs ci-dessous sont vérifiées directement dans le code de production de Gabriel (pas d'approximation).

---

## 1. Description de Gabriel

**Phrase unique**
Gabriel est le cabinet de conseil IA qui transforme les réactions brutes d'une audience — commentaires, avis, conversations — en décisions stratégiques claires.

**Version développée**
Gabriel n'est pas un outil d'analyse parmi d'autres : c'est un cabinet complet, avec trois experts spécialisés — le Psychologue, qui comprend en profondeur ce qu'une audience ressent et croit ; le Stratège, qui transforme cette compréhension en décision ; le Créateur, qui la transforme en contenu. Chaque bureau a sa personnalité, mais tous parlent le même langage visuel — sobre, précis, jamais tape-à-l'œil — pour que l'utilisateur sente qu'il traverse un même cabinet, pas une collection d'outils.

**Pour une agence marketing / publicité**
Présenter Gabriel comme un cabinet de conseil premium *incarné en logiciel* — pas un dashboard SaaS de plus. L'angle différenciant : il ne sort pas des graphiques, il rend des verdicts ("Décision recommandée", "Signal observé") — la sobriété visuelle est une promesse de sérieux, pas un choix esthétique gratuit.

---

## 2. Palette de couleurs

### Thème clair (défaut)

| Rôle | Hex |
|---|---|
| Fond principal | `#f5f5f7` |
| Fond cartes / surfaces | `#ffffff` |
| Fond "soft" (zones creuses) | `#fbfbfc` |
| Texte principal | `#1d1d1f` |
| Texte secondaire (body) | `#515154` |
| Texte muted / légendes | `#86868b` |
| Ligne / bordures | `#e5e5e7` |

### Couleur d'accent — champagne
*Rare, réservée aux décisions et CTA — jamais une surface pleine généralisée.*

| Variante | Hex |
|---|---|
| Champagne | `#b89563` |
| Champagne foncé (hover / texte sur fond clair) | `#765c42` |
| Champagne doux (fond de badge) | `#f5f1ea` |
| Variante "core" (certains CTA) | `#b08a52` |

### Couleurs d'identité par bureau / agent

| Bureau | Hex |
|---|---|
| Psychologue (sauge) | `#718078` |
| Stratège (ardoise) | `#66727d` |
| Créateur (terracotta) | `#b66f57` |
| Rose (accent démographique, genre) | `#e8b8c4` |

### États

| État | Hex |
|---|---|
| Succès | `#16a34a` |
| Erreur / danger | `#dc2626` |
| Sentiment positif (Psychologue) | `#3F6B4A` |
| Sentiment négatif (Psychologue) | `#96703A` |
| Sentiment neutre (Psychologue) | = champagne |

### Thème sombre
*Bascule complète, pas un simple filtre.*

| Rôle | Hex |
|---|---|
| Fond | `#090a08` |
| Cartes | `rgba(18,18,15,.86)` |
| Texte principal | `#f5f0e8` |
| Texte secondaire | `#d0c5b6` |
| Champagne (plus lumineux en sombre) | `#d2ab70` |

### Gradients

Très rares et toujours fonctionnels, jamais décoratifs.
Exemple réel (barre de progression) :
`linear-gradient(90deg, #b89563, #765c42)` — champagne → champagne foncé, direction horizontale.

---

## 3. Typographie

Deux couches distinctes à ne pas confondre :

### Dans l'application (dashboards, outils)

Pile de polices système — aucune police custom chargée, choix délibéré de légèreté et de rapidité :

```
"Helvetica Neue", "SF Pro Display"   → titres
"Helvetica Neue", "SF Pro Text"      → corps
-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif → fallback
```

Tailles réelles observées : titres d'écran ~20px, corps ~11-13px, labels/légendes ~9.5-10.5px. Interface dense, très fonctionnelle.

### Dans le langage de marque fondateur (pages éditoriales, documents de référence)

- **Titres : Fraunces** (serif éditoriale)
  - Display : 44-84px
  - H2 : 30-48px
  - H3 : 22px
- **Corps / interface : Inter**
  - Corps : 17-20px
  - Secondaire : 16px
  - Labels : 13px (majuscules, letter-spacing large)
- Règle stricte : jamais d'autre taille que **48 / 36 / 28 / 20 / 16 / 13**

### Usages

- **Gras** : réservé aux mots-clés dans une phrase — jamais un titre entier.
- **Italique** : citations et nuances de ton (`em` en champagne clair dans le document de marque).
- **Autres styles** : labels toujours en MAJUSCULES avec un espacement de lettres large (`letter-spacing: 0.1–0.16em`) ; légendes en `tabular-nums` pour aligner les chiffres.

---

## 4. Style général et ambiance

- **Style** : minimaliste, "clean SaaS" premium. Le CSS de production porte littéralement le commentaire : *« Langage visuel V2 — minimal, monochrome et légèrement translucide »*.
- **Mode** : les deux, avec bascule manuelle. Le clair est le défaut ; le sombre est une transposition complète, pas un simple inversement de contraste.
- **Border-radius** : légèrement arrondi, jamais anguleux ni très arrondi.
  - Cartes : 10-18px
  - Boutons : systématiquement en **pilule** (`border-radius: 999px`), vérifié sur des dizaines de composants
- **Ambiance recherchée** : la confiance avant tout. La sobriété est une promesse de sérieux. Le champagne doré est volontairement rare — règle du thème : *« une surface champagne attire l'œil comme un aimant, il ne peut donc y avoir qu'une seule raison de l'utiliser par écran »*.

---

## 5. Logo et éléments graphiques

### Logo (`gabriel_logo.png`)

Wordmark **"Gabriel.ai"** en lettres minuscules, script géométrique fin et fluide (pas une police standard).

Traitement visuel : **effet métal liquide / or rose-champagne**, avec reflets 3D — dégradé or clair → or profond, hautes lumières blanches façon métal poli.

**Détail distinctif à préserver dans toute animation** : les points des « i » sont remplacés par de petites **sphères / perles 3D** dans le même traitement métallique — signature graphique unique du logo.

### Icônes

Set maison cohérent, traits fins, un seul répertoire d'icônes (pas de mélange de styles). Monochromes — héritent la couleur du texte environnant. Jamais plus grandes que le texte qu'elles accompagnent.

### Motif récurrent

Petits points / puces circulaires pleins comme repères visuels (indicateur de statut, puce de liste, marqueur de progression). Toujours minuscules (5-8px), jamais décoratifs.

---

## 6. Autres détails utiles

### Boutons — trois registres seulement

| Registre | Style |
|---|---|
| Primaire (rare, 1 par écran) | Pilule pleine champagne ou encre selon le contexte, texte clair |
| Ghost / secondaire | Pilule à bordure fine (`1px solid` gris clair), fond transparent |
| Quiet / tertiaire | Texte seul, muted |

**Hover** : jamais d'effet spectaculaire — juste une opacité réduite (`.85`) ou une bordure qui s'assombrit légèrement, parfois un `translateY(-1px)` très subtil.

### Espacements

- Dans l'app : densité fonctionnelle, paddings 7-16px courants.
- Dans le langage de marque fondateur : échelle stricte **8 / 16 / 24 / 32 / 48 / 64 / 96 / 128px** — jamais de valeur improvisée.

### Règle d'or pour l'animation

Le mouvement est autorisé seulement en **opacity / blur léger / translation / scale très faible**.

**Jamais** de rotation, rebond ou zoom violent. Règle explicite de la charte : *« l'animation raconte, elle ne décore pas »*.
