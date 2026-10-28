# LifeSpace

**Design any space. Watch AI people live in it.**

Upload a home floor plan, an office layout or a street photo. Redesign it with real, common items only. Then a cast of AI people lives a day in the old space and the new one. A livability scorecard and each person's own words show what changed.

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026), Indie track. All code in this repo was written during the hackathon.

> LifeSpace gives design and livability signals only. It is not medical or health advice.

## Meta models used

| Job | Model |
| --- | --- |
| Read plans and photos, redesign, AI people | Muse Spark (`muse-spark-1.3`) via Meta Model API |
| Outline walls, rooms, roads | SAM 3.1 |
| Before and after renders | Muse Image / Muse Wonder |
| Backup in production | Muse Spark Open on Baseten (`meta-models/muse-spark-open-1026`) |

## How it runs

Every AI call goes through one model router (`backend/app/router/model_router.py`). One setting picks the providers:

| `MODE` | Chat chain | Image chain | Use it for |
| --- | --- | --- | --- |
| `mock` | canned answers | grey PNG | tests, offline UI work |
| `local` | Ollama → Cloudflare | Cloudflare | daily development, free |
| `prod` | Meta → Baseten → Cloudflare | Meta → Cloudflare | demo and judging |

If a provider fails or returns bad JSON, the next one answers. Every answer is cached on disk, so repeat runs cost nothing.

## Run it

See [docs/SETUP.md](docs/SETUP.md) for the full step by step.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env                           # then fill in keys
uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

## Project layout

```
backend/
  app/
    main.py              FastAPI app
    config.py            settings from .env
    router/              model router, providers, disk cache
  data/packs/            home, office, street packs (catalog, people)
  scripts/smoke_test.py  call real providers with your keys
  tests/                 offline tests
frontend/                React + Vite (+ Three.js)
docs/SETUP.md            setup guide
```
