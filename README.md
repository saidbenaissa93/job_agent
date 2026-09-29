# 🤖 Agent IA de Recherche d'Emploi (Local)

Un agent IA autonome basé sur **Streamlit**, **Ollama (`Qwen2.5`)** et **SQLite** pour rechercher, filtrer et résumer des offres d'emploi collectées automatiquement.

## 🚀 Fonctionnalités

- **Agentic Loop** : L'IA décide de façon autonome quand et comment interroger la base SQLite (`jobs.db`).
- **Scraping automatisé** : Collecte automatique des offres via GitHub Actions.
- **Matching intelligent** : Filtrage par expérience, mots-clés et malus/bonus candidats (Junior/Senior).
- **100% Local & Gratuit** : Tourne sur votre machine avec Ollama.

## 🛠️ Configuration & Installation

### Préréquis

1. [Python 3.10+](https://www.python.org/downloads/)
2. [Git](https://git-scm.com/)
3. [Ollama](https://ollama.com/) avec le modèle `qwen2.5:7b` :
   ```bash
   ollama run qwen2.5:7b

```text
.
├── agent/            # Logique de l'agent IA et définition des outils (tools.py)
├── collectors/       # Scripts de scraping des offres d'emploi
├── matching/         # Logique de calcul du score d'adéquation
├── processing/       # Nettoyage et traitement NLP/texte des offres
├── storage/          # Gestion de la base de données SQLite
├── app.py            # Interface utilisateur Streamlit
├── jobs.db           # Base de données des offres d'emploi
└── requirements.txt  # Dépendances Python
```