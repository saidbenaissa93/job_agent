# 💼 Job Agent — Assistant de veille emploi automatisé

Pipeline automatisé de recherche d'emploi : scraping d'offres, filtrage selon des critères métier, scoring de pertinence par embeddings, et agent conversationnel local (LLM) pour interroger les résultats sans jamais halluciner de données.

## Fonctionnement en un coup d'œil

```
GitHub Actions (cron, 4x/jour)
        │
        ├── Scraping (France Travail API + HelloWork)
        ├── Filtrage (senior, expérience, secteurs exclus, stage/alternance...)
        ├── Scoring (embeddings CV ↔ offre + bonus/malus)
        └── Commit automatique de la base SQLite mise à jour
        │
        ▼
   (en local, à la demande)
   git pull + Streamlit + Ollama
        │
        └── Agent conversationnel (function calling) qui interroge la base
```

## ✨ Fonctionnalités

- **Collecte multi-sources** : API officielle France Travail (OAuth2) et scraping HelloWork (requests/BeautifulSoup en premier, Playwright en secours)
- **Filtrage intelligent** :
  - Détection des offres "senior" (titre + description, limites de mots, gestion des négations comme *"pas besoin d'être expert"*)
  - Extraction du nombre d'années d'expérience demandé (français et anglais, chiffres et nombres écrits en toutes lettres)
  - Exclusion des stages, alternances, thèses/doctorats
  - Exclusion de secteurs spécifiques (personnalisable)
  - Filtre de fraîcheur des offres (48h / 24h selon la source)
- **Scoring sémantique** : similarité cosinus entre le CV et chaque offre via `sentence-transformers`, avec bonus pour les signaux "junior/débutant" et malus proportionnel au nombre d'années d'expérience demandé
- **Agent conversationnel local** : Ollama + function calling, interroge la base SQLite via des outils dédiés (jamais de réponse inventée)
- **Automatisation complète** : GitHub Actions avec cache (pip, modèle d'embeddings, navigateur Playwright) pour des runs rapides, même PC éteint
- **Interface Streamlit** : chat avec l'agent + tableau de bord filtrable

## 🏗️ Structure du projet

```
job-agent/
├── .github/workflows/scrape.yml   # Workflow GitHub Actions (cron 4x/jour)
│
├── collectors/
│   ├── base.py                    # Structure JobOffer commune aux deux sources
│   ├── france_travail.py          # Scraper API France Travail (OAuth2)
│   └── hellowork.py                # Scraper HelloWork (requests/BeautifulSoup + Playwright en secours)
│
├── processing/
│   ├── filters.py                 # Filtres métier : senior, expérience, mots-clés/secteurs exclus
│   └── recency.py                 # Filtre de fraîcheur des offres
│
├── matching/
│   ├── embeddings.py              # Modèle de similarité sémantique (sentence-transformers)
│   └── scorer.py                  # Calcul des scores de pertinence + bonus/malus
│
├── storage/
│   └── db.py                      # Opérations SQLite (insertion, lecture, purge)
│
├── agent/
│   └── tools.py                   # Outils exposés à l'agent Ollama (function calling)
│
├── config.py                      # Profil de recherche, mots-clés, CV, exclusions
├── main.py                        # Orchestration du scraping (les deux sources)
├── refresh.py                     # Point d'entrée du workflow (scraping + scoring)
├── app.py                         # Interface Streamlit (chat + dashboard)
├── clean_db.py                    # Nettoyage manuel de la base selon les filtres actuels
├── start_app.bat                  # Lancement rapide (pull + activation venv + Streamlit)
├── jobs.db                        # Base SQLite, mise à jour automatiquement
└── requirements.txt
```

## 💬 Exemples de questions à l'agent

- *"Montre-moi les 5 meilleures offres"*
- *"Cherche des offres Data Engineer à Paris"*
- *"Combien d'offres as-tu en base ?"*

## ⚠️ Limites connues

- La base SQLite est committée directement dans Git : simple à mettre en place, mais pas une vraie base partagée (pas de gestion de concurrence, historique qui grossit avec les commits automatiques). Une évolution possible serait de migrer vers PostgreSQL hébergé.
- Le scraping HelloWork dépend de la structure HTML du site, qui peut changer et casser les sélecteurs.
- Le filtrage par règles/regex reste heuristique : certains faux positifs/négatifs restent possibles malgré les nombreux correctifs (négations, accents, limites de mots).

## 🛠️ Stack technique

**Langage** : Python

**IA / Machine Learning** : Ollama (Qwen2.5), function calling, sentence-transformers (embeddings), similarité cosinus

**Data collection** : requests, BeautifulSoup, Playwright, API REST (OAuth2)

**Stockage** : SQLite

**Interface** : Streamlit

**Automatisation / CI** : GitHub Actions (cron, cache de dépendances)