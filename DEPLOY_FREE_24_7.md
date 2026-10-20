# Deploy AlphaSniper Mobile 24/7 for ₹0

This guide deploys the FastAPI + PWA mobile layer to a **free Hugging Face Gradio Space** (2 vCPU / 16 GB RAM), bakes in your populated DuckDB, and keeps the Space awake with a free `cron-job.org` ping at **09:05 IST**.

The Streamlit desktop terminal (`ui/app.py`) is untouched. The mobile app lives in `mobile/`.

---

## 0. What gets deployed

| Piece | Path |
|---|---|
| Gradio SDK launcher | `app.py` |
| FastAPI backend + scheduler | `mobile/mobile_api.py` |
| PWA frontend | `mobile/static/index.html` |
| Manifest + service worker | `mobile/static/manifest.json`, `mobile/static/sw.js` |
| Pre-populated database | `local_data/alpha_terminal.duckdb` |
| Python dependencies | `requirements.txt` |
| Space metadata | `README.md` |

The Gradio SDK runs `app.py`, which starts:

```bash
uvicorn mobile.mobile_api:app --host 0.0.0.0 --port 7860
```

`app.py` honors `GRADIO_SERVER_PORT`, then `PORT`, then defaults to `7860`. No Gradio UI is mounted — the existing PWA and `/api/*` routes are served directly.

The in-process APScheduler runs `run_daily_eod_pipeline(days_back=2)` **Monday–Friday at 16:40 IST**, with a safety retry at **19:15 IST** because NSE sometimes publishes the final bhavcopy after 6 PM.

---

## 1. Prepare the database + Git LFS (one time)

Hugging Face Space repos use Git. The DuckDB file is small right now (~35 MB), but use LFS anyway so future growth does not hit normal Git limits.

```powershell
cd "D:\nishant tp\new market tool"

git lfs install
git lfs track "local_data/alpha_terminal.duckdb"

# Stage the whole project (the Gradio Space needs ai_brain/, data_engine/,
# quant_engine/, config.py, mobile/, app.py, requirements.txt, README.md,
# and the database too).
git add -A
git status --short
# .env must NOT appear in this list

git commit -m "Add mobile PWA + FastAPI multi-user backend + free Gradio deploy package"

git lfs ls-files
# must show: local_data/alpha_terminal.duckdb
```

> `.env` is intentionally excluded from Git and Docker (`Dockerfile` -> `.dockerignore`). Never commit your personal keys.

**Important:** verify the DB was uploaded as a real file, not a 3-line LFS pointer. On the Hugging Face file page it should show an LFS badge and the real ~35 MB size.

---

## 2. Create the free Hugging Face Space

1. Sign up / log in at <https://huggingface.co>.
2. Go to **New → Space**.
3. Fill in:
   - **Space name:** `alphasniper-mobile` (or anything).
   - **License:** private use is fine.
   - **SDK:** `Gradio`.
   - **Gradio template:** `Blank`.
   - **Hardware:** `CPU basic · 2 vCPU · 16 GB RAM · FREE`.
   - **Visibility:** Public (free tier) — the URL is unlisted in practice; do not share it.
4. Click **Create Space**.

The free Gradio SDK is sufficient. Do **not** choose Docker — Docker Spaces require a paid plan; the `Dockerfile` in this repo is optional and is not used by the Space.

---

## 3. Push the project to the Space

Get a **Write** token from <https://huggingface.co/settings/tokens> (name it `alphasniper-deploy`).

```powershell
cd "D:\nishant tp\new market tool"

git remote add space https://huggingface.co/spaces/<YOUR_HF_USERNAME>/alphasniper-mobile

# If your local branch is master:
git push space master:main --force

# If your local branch is main:
git push space main --force
```

> **First push only:** use `--force` because the Space starts with an unrelated auto-generated README commit. Our root `README.md` already contains the required Gradio metadata:
>
> ```yaml
> sdk: gradio
> sdk_version: 5.0.0
> app_file: app.py
> ```
>
> Replacing that initial commit is safe. Do not force-push after the Space is live.

When prompted:
- **Username:** your Hugging Face username
- **Password:** the `hf_...` write token (NOT your account password)

The Space starts building automatically. First build takes ~2–5 minutes (litellm + pandas + DuckDB wheels).

Watch the **Logs** tab. You want to see:

```text
[scheduler] EOD sync armed Mon-Fri 16:40 IST and safety retry 19:15 IST — next runs: ...
Uvicorn running on http://0.0.0.0:7860
```

---

## 4. Smoke-test the cloud backend

Replace `<SPACE_URL>` with your Space URL, e.g. `https://yourname-alphasniper-mobile.hf.space`.

```powershell
Invoke-RestMethod "<SPACE_URL>/api/health" | ConvertTo-Json -Depth 6
Invoke-RestMethod "<SPACE_URL>/api/picks?mode=MASTER&top_n=5&risk_rupees=2000" | ConvertTo-Json -Depth 4
```

Expected: `status: "ok"`, a real `latest_score_date`, and 5 picks.

Also check the PWA alias:

```powershell
Invoke-WebRequest "<SPACE_URL>/sniper" -UseBasicParsing | Select-Object StatusCode
```

Open `<SPACE_URL>` on your phone. The UI should show the **9:20 Action** tab with traffic-light cards.

---

## 5. Keep it awake at 09:05 IST for ₹0

Hugging Face free Spaces sleep after a period of inactivity (currently 48 hours). A daily ping prevents that and guarantees the 16:40 IST scheduler stays alive.

1. Create a free account at <https://cron-job.org>.
2. **Create cronjob**:
   - **Title:** `AlphaSniper wake-up`
   - **URL:** `<SPACE_URL>/api/health`
   - **Schedule:** every day at **09:05**
   - **Timezone:** `Asia/Kolkata` (IST)
   - **Execution:** every day
   - Enable **Save responses** so you can confirm HTTP 200.
3. (Recommended) Create a second job:
   - **Title:** `AlphaSniper pre-EOD wake-up`
   - **URL:** `<SPACE_URL>/api/health`
   - **Schedule:** every weekday at **16:35 IST**
   - This guarantees the container is warm before the internal 16:40 IST EOD job fires.
4. (Recommended) Create a third job:
   - **Title:** `AlphaSniper late bhavcopy retry wake-up`
   - **URL:** `<SPACE_URL>/api/health`
   - **Schedule:** every weekday at **19:10 IST**
   - This keeps the Space warm for the built-in 19:15 IST safety retry, which catches NSE bhavcopies published after 6 PM.

Free Spaces cold-start in roughly 30–90 seconds. The 09:05 ping means the app is hot by 09:20.

> Optional: cron-job.org can also hit `/api/live-refresh`, but that needs your private Upstox token in the URL/header, so keep the public ping on `/api/health` only.

---

## 6. Install the PWA on both phones

**Android / Chrome**
1. Open `<SPACE_URL>`.
2. Menu (⋮) → **Install app** / **Add to Home screen**.
3. Launch it from the home screen — standalone full-screen, no browser bar.

**iPhone / Safari**
1. Open `<SPACE_URL>` in Safari.
2. Share → **Add to Home Screen** → Add.
3. Launch from the home screen.

**Per-user setup (each phone, independently):**
1. Go to **🔐 My Vault**.
2. Paste **your own Upstox access token**.
3. Set your **risk per trade** (default ₹2,000).
4. Choose **Gemini or Groq**, paste **your own API key**.
5. Tap **✅ Save My Keys to Phone**.
6. Return to **🎯 9:20 Action** and tap **⚡ 9:20 Live**.

Keys are stored only in that phone's `localStorage` and sent only as headers on that phone's requests. They are never written to DuckDB or shared between users.

---

## 7. Optional: server-side secrets

Each phone brings its own keys, so no secrets are required. **Mobile chat intentionally never falls back to a server-side LLM key** — if the vault has no key, the app serves the deterministic quant plan instead. This guarantees one user can never consume another user's LLM quota.

The only optional server-side fallback is a shared Upstox token for live refresh when a phone leaves its token blank:

**Settings → Variables and secrets → New secret**

| Name | Value |
|---|---|
| `UPSTOX_ACCESS_TOKEN` | optional shared fallback Upstox token |
| `DEFAULT_LLM_MODEL` | optional, e.g. `gemini/gemini-3.5-flash-lite` |
| `DEFAULT_LLM_PROVIDER` | optional, e.g. `gemini` |

`GEMINI_API_KEY` / `GROQ_API_KEY` secrets are not used by mobile chat; they are only relevant if you also run the desktop Streamlit app. Restart the Space after adding secrets.

---

## 8. Updating the deployed data

- **Automatic:** the in-container scheduler updates the DB every weekday at 16:40 IST, then retries at 19:15 IST to catch late NSE bhavcopies. Either phone can also trigger **🔄 Run EOD Sync** from the AI tab.
- **Manual rebuild:** if you backfilled a lot of history locally, re-track and push the new DB:

```powershell
git add local_data/alpha_terminal.duckdb
git commit -m "Update DuckDB snapshot"
git push space master:main
```

### Free-tier storage reality

Hugging Face free Spaces have **ephemeral disk**. The baked DuckDB is part of the image and always comes back after a restart, but writes made at runtime (live quotes, EOD rescoring) are lost if the Space restarts or rebuilds. The daily cron ping keeps it alive, so in normal daily use the data stays current. For long-term persistence, either:

- upgrade the Space to persistent storage, or
- periodically download/export the updated DB and commit it back to the repo (manual), or
- keep your laptop as the source of truth for backfills and push a fresh snapshot when needed.

---

## 9. Local Gradio-SDK test (no Docker)

Run the same entrypoint Hugging Face uses:

```powershell
.venv\Scripts\python.exe app.py
```

Open <http://localhost:7860>. The PWA is at `/`, the alias is at `/sniper`, and the API is under `/api/*`.

If port `7860` is already in use, stop the old process first:

```powershell
$conn = Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```

The legacy Docker recipe remains in `Dockerfile` for optional local use only:

```powershell
docker build -t alphasniper-mobile .
docker run --rm -p 7860:7860 --env-file .env alphasniper-mobile
```

Do not use Docker as the Hugging Face SDK — the free Space uses Gradio.

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails on `duckdb` | Check the Space is on the **Gradio** SDK, not Docker/Static, and that root `requirements.txt` is present. |
| Build ignores `app.py` | Verify `README.md` frontmatter has `sdk: gradio` and `app_file: app.py`, then restart the Space. |
| Port / startup timeout | `app.py` must bind `0.0.0.0` on `GRADIO_SERVER_PORT` (or `7860`). Check the Logs for the actual Uvicorn line. |
| `/api/health` returns 503 / Space sleeping | Open the Space URL once, or wait for the 09:05 cron ping; cold start is 30–90 s. |
| DB is a 3-line pointer | Git LFS did not upload. Run `git lfs ls-files`, then `git lfs push space --all`. |
| `/api/picks` is slow or Space runs out of memory | Confirm picks/live use the 48 MB DuckDB connection cap; restart the Space after a large EOD run. |
| `No Upstox token` in app | Save the token in **My Vault**; it is per-phone. |
| Upstox 502 | Token expired (Upstox tokens expire daily). Generate a fresh one and re-save in My Vault. |
| AI says LLM unavailable | Free quota exhausted or wrong key. The deterministic quant plan still renders instantly. |
| Scheduler not updating | Free Space slept before 16:35. Add the recommended 16:35 and 19:10 wake-up crons. |
| Install button missing on Android | Chrome requires HTTPS + valid manifest + service worker; the HF Space URL is HTTPS, so reload once. |
| iPhone has no install prompt | iOS uses Share → Add to Home Screen (the app shows this hint). |

---

## 11. Security notes

- The Space URL is public. Anyone who knows it can read picks (no orders can be placed). Keep it private / unlisted.
- Upstox and LLM keys are never stored server-side unless you add the optional Space secrets. They travel per-request in headers. Mobile chat requires the phone's own LLM key and never reuses a server-side LLM key.
- This app places **no orders**. It only reads quotes and computes levels.
- If you ever leak a Space secret, rotate it in HF Settings immediately.
