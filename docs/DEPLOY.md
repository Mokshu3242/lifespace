# Deploy guide

Live setup: **Cloudflare Pages** (the website) → **Render** (the backend) → **Supabase** (saved data).
**GitHub Actions** runs the tests on every push and keeps the demo awake.

```
browser ── https://lifespace.pages.dev ──┬── the React app (static files)
                                         └── /api/*  → Pages Function → Render backend → Meta models
                                                                              │
                                                                              └── mirror of .data and .cache → Supabase Storage
```

The browser only talks to the Pages address, so there is no CORS to set up.

Time: about 45 minutes. Cost: all free (Cloudflare, Render free plan, Supabase, GitHub Actions). Render Starter is $7 a month if
the free plan runs out of memory.

## 1. Supabase (5 min)

1. Create a project at https://supabase.com (free plan, any region near you).
2. **Storage → New bucket**: name `lifespace`, **private** (leave "Public bucket" off).
3. **Project Settings → API**: copy the **Project URL** and the **service_role** key.
   The service key can read and write everything. It goes only into Render's environment, never into the
   repo, the frontend or a chat.

## 2. Render: the backend (15 min)

1. https://render.com → **New → Blueprint** → connect GitHub → pick `lifespace`.
   Render reads `render.yaml`: a Docker web service named `lifespace-api`, built from `backend/`.
2. It asks for the secret values once. Copy them from your local `.env`, without quotes:

   | Name | Value |
   | --- | --- |
   | `META_API_KEY` | your Meta key |
   | `META_CHAT_MODEL`, `META_IMAGE_MODEL` | same as in your `.env` |
   | `SUPABASE_URL` | the Project URL |
   | `SUPABASE_SERVICE_KEY` | the service_role key |
   | `BASETEN_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | optional backups; leave empty if you don't use them |

   `MODE=prod` and `SUPABASE_BUCKET=lifespace` are already set by the Blueprint.
3. The first build takes 5 to 10 minutes (OpenCV and the OCR model are large).
4. You get an address like `https://lifespace-api.onrender.com`. Open `<that address>/api/health`.
   You should see `"mode":"prod"`.
5. **Free plan facts:** it sleeps after 15 minutes with no traffic and takes about a minute to wake
   (the keepalive workflow prevents that); its disk is wiped on every restart and redeploy (Supabase
   brings the data back); 750 free hours a month, enough for one service running all month.
6. If the service runs out of memory while reading a plan (it restarts in the logs), move it to
   **Starter** ($7 a month).

## 3. Cloudflare Pages: the website (10 min)

1. https://dash.cloudflare.com → **Workers & Pages → Create → Pages → Connect to Git** → `lifespace`.
2. Build settings:

   | Setting | Value |
   | --- | --- |
   | Framework preset | Vite |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |

3. **Settings → Variables and secrets**: add `BACKEND_URL` = your Render address (no slash at the end).
   This is read by `frontend/functions/api/[[path]].js`, which passes every `/api/...` call to Render.
4. Deploy. Open `https://<project>.pages.dev`, click a sample plan. It should open.

## 4. GitHub Actions (5 min)

- `tests.yml` runs the backend tests and the frontend build on every push. Nothing to set up.
- `keepalive.yml` pings the live site every 10 minutes, so Render never falls asleep and Supabase stays active
  (free Supabase projects pause after a week with no activity).
  Add a repo secret: **Settings → Secrets and variables → Actions → New repository secret**:
  `LIVE_URL` = `https://<project>.pages.dev`.
  Then run it once by hand: **Actions → keepalive → Run workflow**.

## 4b. Big jobs on GitHub (5 min)

Heavy background work runs in GitHub Actions, not on the 512 MB server:

| Workflow | When | What it does |
| --- | --- | --- |
| `backend image` | every push to `backend/` | builds the backend with OpenCV and OCR installed and keeps it in GitHub's free registry (`ghcr.io/mokshu3242/lifespace-backend`), so the jobs below start in seconds |
| `prepare demo` | nightly, or by hand | runs each sample's day on its latest designs and saves the results to Supabase (tick "all" for every saved plan) |
| `clean up storage` | Sundays, or by hand | removes saved AI answers not used for 14 days; plans, designs, pictures and lessons are never removed. By hand it only reports unless you untick "dry run" |

Add these repo secrets (**Settings → Secrets and variables → Actions**): `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, `META_API_KEY`, `META_CHAT_MODEL`, `META_IMAGE_MODEL`. Then run `backend image` once
by hand (Actions → backend image → Run workflow), and after it, `prepare demo`.

Each job starts on a fresh machine, so nothing stays running between jobs; the image is what makes them
start fast. Things people click (reading a plan, a redesign) stay on Render.

## 5. Load the demo once (5 min)

On the live site, click each sample plan once and run the demo flow on the terrace home. Each answer is
saved (and mirrored to Supabase), so after that the samples open instantly and judges' clicks on them
cost nothing.

## 6. Check from another device

Open the Pages address in a private window on your phone or another laptop and run: sample plan →
redesign → people → 3D. If anything fails, Render → **lifespace-api → Logs** shows why.

## Limits that protect your credits

In prod, each visitor gets 15 plan or photo reads and 60 AI actions a day (`RATE_READS_PER_DAY`,
`RATE_ACTIONS_PER_DAY`). Opening a sample or a plan read before costs no tokens.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Pages shows "BACKEND_URL is not set" | Add the variable in Pages settings, then redeploy |
| `/api/health` works on Render but the site says backend not reachable | `BACKEND_URL` has a typo or a trailing slash |
| Saved plans vanish after a Render restart | Supabase variables missing or wrong; the logs say "Supabase not set" |
| "Daily limit reached" | The per-visitor limit; raise it in Render environment if you need |
| Service restarts during a plan read | Out of memory: move the service to Starter ($7) |
| The site takes a minute to open | Render was asleep: check the keepalive workflow runs (Actions tab) |
