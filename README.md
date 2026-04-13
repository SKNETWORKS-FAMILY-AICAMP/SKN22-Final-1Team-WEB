# MirrAI

MirrAI is a Django-based hairstyle recommendation platform with customer flows, partner/designer tools, a latest-trends feed, and a designer support chatbot.

## Runtime Overview

- Customer flow: survey, capture, face analysis, recommendations, consultation request
- Partner flow: dashboard, client lookup, designer assignment, consultation management
- Trend feed: latest hairstyle trend cards sourced from the trend RAG store
- Designer chatbot: local Chroma-backed retrieval over curated support documents

## Database Shape

The project currently contains two table families:

- Runtime Django tables such as `clients`, `designers`, `styles`, `surveys`, `capture_records`
- Legacy bridge tables such as `client`, `designer`, `hairstyle`, `client_survey`, `client_analysis`, `client_result`

When legacy bridge tables exist, several partner/recommendation paths read from those legacy tables through `app/services/model_team_bridge.py`.

## RAG Stores

The repository keeps only the Chroma stores needed in production:

- `data/rag/stores/chromadb_trends`
- `data/rag/stores/chromadb_ncs`
- `data/rag/stores/chromadb_chatbot`

Not included in the deployment payload:

- `data/rag/stores/chromadb_styles`

Important: Chroma persistence requires both `chroma.sqlite3` and companion binary/index files such as `*.bin`, `header.bin`, and `link_lists.bin`. Those files must stay together for the stores that are deployed.

## Local Setup

1. Create `.env` from `.env.example`

```powershell
Copy-Item .env.example .env
```

2. Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

3. Run migrations and start the server

```bash
python manage.py migrate
python manage.py runserver
```

## Trend Refresh

Refresh the production trend store locally before shipping updated trend data:

```bash
python manage.py refresh_trends --mode local --steps crawl,refine,llm_refine,vectorize
```

If you only need to rebuild the Chroma collection from already prepared data:

```bash
python manage.py refresh_trends --mode local --steps vectorize
```

## Scheduler

Key variables:

- `ENABLE_TREND_SCHEDULER`
- `TREND_SCHEDULER_TIMEZONE`
- `TREND_SCHEDULER_WEEKLY_DAY`
- `TREND_SCHEDULER_WEEKLY_HOUR`
- `TREND_SCHEDULER_WEEKLY_MINUTE`
- `TREND_SCHEDULER_STEPS`

Current default scheduler steps:

```text
crawl,refine,llm_refine,vectorize,rebuild_ncs
```

With the current code, setting `ENABLE_TREND_SCHEDULER=True` allows scheduler autostart in both Django `runserver` and Gunicorn web runtime.

Manual scheduler run:

```bash
python manage.py run_trend_scheduler
```

## Deployment Notes

Elastic Beanstalk builds the image from `Dockerfile` and `.github/workflows/deploy.yml`.

Deployment expectations:

- Build context excludes tests and non-production data
- Only `chromadb_trends`, `chromadb_ncs`, and `chromadb_chatbot` are shipped
- `chromadb_styles` is excluded from Docker build context

GitHub Actions deployment trigger:

- Deploy runs only on `push` to `main`
- Merging into `develop` does not deploy by itself
- Merging into `main` deploys only when the merge includes files matched by the workflow path filter:
  `app/**`, `mirrai_project/**`, `static/**`, `templates/**`, `data/**`, `Dockerfile`, `.dockerignore`, `docker-entrypoint.sh`, `manage.py`, `requirements.txt`, `requirements-deploy.txt`, `requirements-trends.txt`, `Dockerrun.aws.json`, `.github/workflows/deploy.yml`
- `README.md` or `.gitignore` changes alone do not trigger deployment

If trend data changes, make sure the refreshed `chromadb_trends` store is committed before pushing `main`.

## Useful Commands

```bash
python manage.py check
python manage.py test
python manage.py refresh_trends --mode local --steps vectorize
python manage.py run_trend_scheduler
```

## Tests

`app/tests/` stays version-controlled for development and regression coverage, and `.dockerignore` excludes it from the production build context.
