# Gabriel — Guide d'installation

Intelligence de marché · Analyse psychologique et stratégique d'audience

---

## Ce qu'il faut pour faire tourner Gabriel

- **Python 3.10 ou plus récent** — https://python.org/downloads
- **Clés API** (voir section ci-dessous)
- Un terminal (PowerShell sur Windows, Terminal sur Mac/Linux)

---

## Installation — étape par étape

### 1. Copier le dossier Gabriel

Placez le dossier `gabriel` où vous le souhaitez (Bureau, Documents, etc.).

### 2. Installer les dépendances Python

Ouvrez un terminal dans le dossier gabriel et tapez :

```
pip install -r requirements.txt
```

### 3. Créer le fichier `.env`

Créez un fichier nommé `.env` à la racine du dossier gabriel (même niveau que `app.py`).
Copiez-collez ce contenu et remplissez vos clés :

```
ANTHROPIC_API_KEY=sk-ant-...
YOUTUBE_API_KEY=AIza...
IG_USERNAME=votre_username_instagram
IG_PASSWORD=votre_mot_de_passe_instagram
RAPIDAPI_KEY=votre_cle_rapidapi
```

#### Où obtenir ces clés :

| Clé | Où la trouver |
|-----|---------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `YOUTUBE_API_KEY` | console.cloud.google.com → API & Services → YouTube Data API v3 |
| `IG_USERNAME` / `IG_PASSWORD` | Vos identifiants Instagram (compte dédié recommandé) |
| `RAPIDAPI_KEY` | rapidapi.com → Dashboard → Apps → votre app → Authorization |

> **Note :** Les clés Instagram et RapidAPI sont pour le scraping Instagram/TikTok. Si vous n'utilisez que YouTube et texte libre, vous pouvez laisser ces champs vides.

### 4. Lancer Gabriel

**Sur Windows :** Double-cliquez sur `LANCER_GABRIEL.bat`

**Ou via terminal :**
```
python app.py
```

### 5. Ouvrir dans le navigateur

Gabriel est accessible sur :
```
http://localhost:5050
```

---

## Structure du projet

```
gabriel/
├── app.py                  # Serveur Flask (point d'entrée)
├── orchestrator.py         # Pipeline IA (Psychologue + Stratège)
├── scraper.py              # Scraping YouTube / Instagram / TikTok
├── memory.py               # Mémoire des analyses passées
├── analyzer.py             # Utilitaires d'analyse
├── agents/                 # Agents IA spécialisés
│   ├── psychologue.py      # Le Psychologue (analyse audience)
│   ├── stratege.py         # Le Stratège (décision business)
│   ├── architecte.py       # Architecte de contenu
│   ├── createur.py         # Créateur
│   └── context.py          # Contexte partagé
├── templates/
│   ├── index.html          # Application principale (~3800 lignes)
│   └── landing.html        # Page d'accueil
├── static/
│   └── chess.webp          # Image de fond
├── requirements.txt        # Dépendances Python
├── LANCER_GABRIEL.bat      # Lanceur Windows
└── .env                    # Clés API (à créer — NE PAS partager)
```

---

## En cas de problème

**"Module not found"** → Relancez `pip install -r requirements.txt`

**"Port 5050 already in use"** → Un autre process tourne déjà. Redémarrez ou changez le port dans `app.py` (dernière ligne).

**Erreur API Anthropic** → Vérifiez que votre `ANTHROPIC_API_KEY` est valide et que vous avez du crédit.

**Erreur YouTube** → Vérifiez que l'API YouTube Data v3 est activée dans Google Cloud Console.

---

## Notes

- L'analyse YouTube traite jusqu'à 100 commentaires — durée normale : 2 à 5 minutes
- L'historique des analyses est sauvegardé dans `history.json` (local)
- Le profil business est sauvegardé dans `brain_profile.json` (local)
- Gabriel tourne entièrement en local — vos données ne quittent pas votre machine (sauf les appels API Anthropic/YouTube)
