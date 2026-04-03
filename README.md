# Gen AI Learning

This repository contains a Python-based movie search application in `movie-search/`.

## What this project does

The app can:
- Import popular movies from TMDB into a local SQLite database
- Search and filter imported movies from an interactive CLI
- Use embedding/vector dependencies for semantic-search related features

## Project location

Main runnable app:
- `movie-search/`

Entrypoint:
- `movie-search/main.py`

## Prerequisites

- Python 3.10+
- A TMDB API key (free): https://www.themoviedb.org/settings/api

## Setup

1. Clone the repository and move into it:

```bash
git clone <your-repo-url>
cd Gen_AI_Learning
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r movie-search/requirements.txt
```

4. Create environment file:

```bash
cp movie-search/.env.example movie-search/.env
```

If `.env.example` does not exist, create `movie-search/.env` manually with:

```env
TMDB_API_KEY=your_tmdb_api_key_here
TMDB_BASE_URL=https://api.themoviedb.org/3
DEBUG=false
```

## Run the app

From the app directory:

```bash
cd movie-search
python3 main.py
```

CLI options:

```bash
python3 main.py              # default flow: imports first if DB is empty, then interactive search
python3 main.py --import     # force import, then optionally enter interactive mode
python3 main.py --interactive  # interactive mode only
```

## Run tests

```bash
cd movie-search
pytest -q
```

## Data and database

- SQLite DB file is created under `movie-search/data/`
- Schema file: `movie-search/database/schema.sql`

## Troubleshooting

- `Configuration error` about TMDB key:
  - Verify `movie-search/.env` exists and `TMDB_API_KEY` is set to a real key.
- `ModuleNotFoundError` while running:
  - Ensure you are inside `movie-search/` when executing `python3 main.py`.
- Dependency/import issues:
  - Re-activate the venv and reinstall requirements:

```bash
source .venv/bin/activate
pip install -r movie-search/requirements.txt
```
