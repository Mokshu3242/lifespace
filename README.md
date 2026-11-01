# LifeSpace

**Design any space. Watch AI people live in it.**

Upload a home floor plan, an office layout or a street photo. Redesign it with real, common items only. Then a cast of AI people lives a day in the old space and the new one. A livability scorecard and each person's own words show what changed.

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026), Indie track. All code in this repo was written during the hackathon.

> LifeSpace gives design and livability signals only. It is not medical or health advice.

## What it does

1. **Read the plan.** Walls, doors (measured in inches), rooms, printed sizes and furniture. An **AI plan check** finds misreads and fixes them with you.
2. **Tell it who lives there.** "My mom is 72 and uses a walker." Each person gets a real body width and a daily routine. Add a dog, a toddler, a caregiver or a delivery.
3. **Redesign on a budget.** Real, common items only. Every idea is checked by code: does it fit, can it get through the door, does it block anyone? Compare 3 budgets side by side.
4. **Watch them live it.** The same day before and after, on the 2D map or in 3D (ride along, walk as them, night mode). Scores for safety, access, movement and energy are measured, not guessed.
5. **What if…** In 5 years (a walker becomes a wheelchair), a fire drill at 2 AM, talk to each person about their day, ask plain questions, a comic of their day, your own room photo with the redesign in it.
6. **Compare homes** and **check a street** from a photo.

**AI suggests. Code checks.** Every number is measured on your plan. When furniture can't fix something (a 19 in door), LifeSpace says so, and shows what a 32 in door would change.

Clean plans with printed room sizes read best. Busy plans with textured floors may need the AI plan check or a few hand fixes.

## Meta models used

| Job | Model |
| --- | --- |
| Read plans and photos, redesign, AI people | Muse Spark (`muse-spark-1.3`) via Meta Model API |
| Find furniture on plans; lights, benches, bins on street photos | SAM 3.1 |
| Room pictures, comics, your own photo with the redesign (edit) | Muse Image |
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

See [docs/SETUP.md](docs/SETUP.md) for local setup and [docs/DEPLOY.md](docs/DEPLOY.md) for the live site (Cloudflare Pages + Railway + Supabase + GitHub Actions).

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
  Dockerfile, railway.json  the backend on Railway
frontend/                React + Vite + Three.js
  functions/api/         Cloudflare Pages Function: /api → Railway
.github/workflows/       tests on every push; keepalive ping
docs/SETUP.md            local setup
docs/DEPLOY.md           live site
```
