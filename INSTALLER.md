# Installation de Gabriel sur un nouveau PC

## Prérequis

- Python 3.10 ou plus récent → https://www.python.org/downloads/
- Visual Studio Code → https://code.visualstudio.com/
- Extension VS Code : Python (Microsoft)

---

## Étapes d'installation

### 1. Ouvrir le projet dans VS Code

Fichier → Ouvrir le dossier → sélectionner le dossier `gabriel 2`

### 2. Créer l'environnement virtuel

Dans le terminal VS Code (Ctrl+ù ou Terminal → Nouveau terminal) :

```bash
python -m venv venv
```

### 3. Activer l'environnement virtuel

**Windows :**
```bash
venv\Scripts\activate
```

### 4. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 5. Configurer les clés API

- Copier le fichier `.env.example` et le renommer `.env`
- Ouvrir `.env` et remplir chaque valeur avec vos clés :
  - `ANTHROPIC_API_KEY` → votre clé Anthropic (claude.ai/settings/keys)
  - `YOUTUBE_API_KEY` → votre clé Google Cloud Console
  - `IG_USERNAME` / `IG_PASSWORD` → votre compte Instagram
  - `RAPIDAPI_KEY` → votre clé RapidAPI

### 6. Lancer Gabriel

**Option A — double-cliquer sur :**
```
LANCER_GABRIEL.bat
```

**Option B — depuis le terminal VS Code :**
```bash
python app.py
```

### 7. Ouvrir dans le navigateur

```
http://localhost:5050
```

---

## Structure du projet

```
gabriel/
├── app.py                  # Serveur Flask principal
├── analyzer.py             # Pipeline d'analyse des commentaires
├── nlp_engine.py           # Moteur NLP (TF-IDF, clustering, émotions)
├── orchestrator.py         # Orchestration des agents IA
├── memory.py               # Mémoire et contexte business
├── scraper.py              # Scraping YouTube / Instagram
├── build_landing.py        # Générateur de landing page
├── agents/
│   ├── psychologue.py      # Agent Psychologue
│   ├── stratege.py         # Agent Stratège
│   ├── architecte.py       # Agent Architecte
│   ├── createur.py         # Agent Créateur
│   ├── context.py          # Bus de contexte partagé
│   └── base.py             # Classe de base agents
├── templates/
│   └── index.html          # Interface complète (frontend)
├── static/
│   └── chess.webp          # Asset visuel
├── requirements.txt        # Dépendances Python
├── .env                    # Clés API (à créer depuis .env.example)
└── history.json            # Historique des analyses
```
