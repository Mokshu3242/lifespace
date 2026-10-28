# Setup guide

Do these in order. Total time: about 45 minutes.

## 1. Tools on your laptop

- Python 3.11 or newer: `python --version`
- Node 20 or newer: `node --version`
- Git: `git --version`

## 2. Get the code into your own public GitHub repo

1. On GitHub, create a new **public** repo named `lifespace`. Leave it empty (no README, no .gitignore).
2. Unzip `lifespace.zip` and open a terminal in that folder.
3. Run:

```bash
git init -b main
git add .
git commit -m "Project setup, model router, frontend shell"
git remote add origin https://github.com/<your-username>/lifespace.git
git push -u origin main
```

## 3. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example ../.env       # Windows: copy ..\.env.example ..\.env
pytest -q                        # should say 7 passed
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/api/health. You should see your mode.

## 4. Frontend

New terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The status card shows the mode and provider chain.

## 5. Free models for local dev

You need at least one of these. Both is best, so one backs up the other.

### Option A: Ollama (runs on your RTX 4060, offline)

1. Install from https://ollama.com/download
2. Pull the models:

```bash
ollama pull llama3.2
ollama pull qwen2.5vl:7b
```

3. Ollama runs on `http://localhost:11434`. Nothing to add to `.env`.

### Option B: Cloudflare Workers AI (free daily allowance)

1. Sign in at https://dash.cloudflare.com
2. Copy your **Account ID** (right side of the dashboard home).
3. Go to **My Profile → API Tokens → Create Token**, use the **Workers AI** template.
4. Put both in `.env`:

```
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
```

Cloudflare also does the free image renders in local mode.

## 6. Check that it works

With `MODE=local` in `.env`:

```bash
cd backend
python -m scripts.smoke_test
python -m scripts.smoke_test path/to/any-floor-plan.png   # tests vision too
```

You should see an answer and `answered by: ollama` or `cloudflare`. In the browser, the "Ask the model" button should work too.

## 7. Later: switch to production

When the Meta credits land:

```
MODE=prod
META_API_KEY=...
BASETEN_API_KEY=...
```

Restart the backend. Same code, official models. Until Muse Image is wired in, renders fall back to Cloudflare.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Frontend says backend not reachable | Start uvicorn on port 8000 first |
| `All providers failed` | Ollama not running, or Cloudflare keys missing in `.env` |
| Ollama vision is slow | Normal on first call while the model loads; later calls are faster |
| Old answer keeps coming back | That's the cache. Delete the `.cache` folder to clear it |
