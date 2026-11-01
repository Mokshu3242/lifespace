# Deploy guide

Live setup: **Cloudflare Pages** (the website) → **Railway** (the backend) → **Supabase** (saved data).
**GitHub Actions** runs the tests on every push and keeps the demo awake.

```
browser ── https://lifespace.pages.dev ──┬── the React app (static files)
                                         └── /api/*  → Pages Function → Railway backend → Meta models
                                                                              │
                                                                              └── mirror of .data and .cache → Supabase Storage
```

The browser only talks to the Pages address, so there is no CORS to set up.

Time: about 45 minutes. Cost: Cloudflare, Supabase and GitHub Actions are free; Railway is a one-time $5
trial credit, then Hobby at $5 a month.

## 1. Supabase (5 min)

1. Create a project at https://supabase.com (free plan, any region near you).
2. **Storage → New bucket**: name `lifespace`, **private** (leave "Public bucket" off).
3. **Project Settings → API**: copy the **Project URL** and the **service_role** key.
   The service key can read and write everything. It goes only into Railway's variables, never into the
   repo, the frontend or a chat.

## 2. Railway: the backend (15 min)

1. https://railway.com → **New Project → Deploy from GitHub repo** → pick `lifespace`.
2. In the service **Settings**:
   - **Root Directory**: `backend`
   - Railway finds `backend/Dockerfile` and `backend/railway.json` by itself.
3. **Variables** (copy from your local `.env`, without quotes):

   | Name | Value |
   | --- | --- |
   | `MODE` | `prod` |
   | `META_API_KEY` | your Meta key |
   | `META_CHAT_MODEL`, `META_IMAGE_MODEL` | same as in your `.env` |
   | `BASETEN_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | optional backups, same as `.env` |
   | `SUPABASE_URL` | the Project URL |
   | `SUPABASE_SERVICE_KEY` | the service_role key |
   | `SUPABASE_BUCKET` | `lifespace` |

4. **Settings → Networking → Generate Domain**. You get something like
   `https://lifespace-production.up.railway.app`.
5. Open `<that address>/api/health`. You should see `"mode":"prod"`. The first deploy takes a few minutes
   (OpenCV and the OCR model are large).
6. If the free plan's 0.5 GB of memory isn't enough (the service restarts while reading a plan), switch
   the project to **Hobby** ($5 a month).

## 3. Cloudflare Pages: the website (10 min)

1. https://dash.cloudflare.com → **Workers & Pages → Create → Pages → Connect to Git** → `lifespace`.
2. Build settings:

   | Setting | Value |
   | --- | --- |
   | Framework preset | Vite |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |

3. **Settings → Variables and secrets**: add `BACKEND_URL` = your Railway address (no slash at the end).
   This is read by `frontend/functions/api/[[path]].js`, which passes every `/api/...` call to Railway.
4. Deploy. Open `https://<project>.pages.dev`, click a sample plan. It should open.

## 4. GitHub Actions (5 min)

- `tests.yml` runs the backend tests and the frontend build on every push. Nothing to set up.
- `keepalive.yml` pings the live site every 6 hours, so Railway is warm and Supabase stays active
  (free Supabase projects pause after a week with no activity).
  Add a repo secret: **Settings → Secrets and variables → Actions → New repository secret**:
  `LIVE_URL` = `https://<project>.pages.dev`.
  Then run it once by hand: **Actions → keepalive → Run workflow**.

## 5. Load the demo once (5 min)

On the live site, click each sample plan once and run the demo flow on the terrace home. Each answer is
saved (and mirrored to Supabase), so after that the samples open instantly and judges' clicks on them
cost nothing.

## 6. Check from another device

Open the Pages address in a private window on your phone or another laptop and run: sample plan →
redesign → people → 3D. If anything fails, Railway → **Deployments → View logs** shows why.

## Limits that protect your credits

In prod, each visitor gets 15 plan or photo reads and 60 AI actions a day (`RATE_READS_PER_DAY`,
`RATE_ACTIONS_PER_DAY`). Opening a sample or a plan read before costs no tokens.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Pages shows "BACKEND_URL is not set" | Add the variable in Pages settings, then redeploy |
| `/api/health` works on Railway but the site says backend not reachable | `BACKEND_URL` has a typo or a trailing slash |
| Saved plans vanish after a Railway redeploy | Supabase variables missing or wrong; the logs say "Supabase not set" |
| "Daily limit reached" | The per-visitor limit; raise it in Railway variables if you need |
| Service restarts during a plan read | Out of memory: move Railway to Hobby |
