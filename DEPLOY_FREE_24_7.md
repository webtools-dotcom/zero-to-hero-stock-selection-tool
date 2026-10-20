# Free Hugging Face deployment

Use a **Gradio Space on ZeroGPU**. AlphaSniper itself uses CPU only; a one-second `@spaces.GPU` probe is registered on a hidden Gradio button because ZeroGPU checks for that event during startup. The probe is not called on page load or by normal app traffic, so the app does not request GPU time. `app.py` lets Gradio own the single listener, then attaches the FastAPI routes to Gradio's server.

## Space settings

- SDK: **Gradio**
- Hardware: **ZeroGPU (Free)**
- Visibility: **Public** (free tier)

The repository's `README.md` frontmatter already selects Gradio and `app.py`. Do not change it to Docker or Static. Static cannot run the FastAPI API or scheduler. Do not add `gradio` or `spaces` to `requirements.txt`; Hugging Face supplies them for this SDK/runtime.

## Deploy the code

After signing in with a newly created Hugging Face Write token, push the current branch to the Space's `main` branch:

```powershell
git push origin HEAD:main
```

Check `git remote -v` first to make sure `origin` points to `https://huggingface.co/spaces/Nishant-vib/alphasniper-terminal`. Use the token as your Git password locally; never paste it into source files or chat. Do not force-push.

Wait for the Space to rebuild. The logs should show the Gradio server and the scheduler startup message. Then check:

```powershell
Invoke-RestMethod "https://nishant-vib-alphasniper-terminal.hf.space/api/health" | ConvertTo-Json -Depth 6
Invoke-WebRequest "https://nishant-vib-alphasniper-terminal.hf.space/sniper" -UseBasicParsing | Select-Object StatusCode
```

The health endpoint should return `status: ok` (or `degraded` with a database diagnostic); `/sniper` should return HTTP 200.

## Keep the scheduled sync best-effort

Free Spaces can sleep after inactivity, and the scheduler only runs while the app process is awake. If using a free external ping service, schedule requests to `/api/health` every day at **09:05 IST**, and weekdays at **16:35 IST** and **19:10 IST**. Those latter pings aim to wake the app before its 16:40 EOD sync and 19:15 retry. A wake-up request cannot guarantee a job will run on time after a cold start or platform restart.

## Free-tier limits

- Free ZeroGPU hosting is subject to Hugging Face account eligibility and capacity. The app does not use GPU, but it still has to satisfy the ZeroGPU Gradio startup check.
- Space disk is not persistent. The checked-in DuckDB snapshot returns on rebuild; writes made while running may disappear after a restart. Keep a separate database backup.
- ZeroGPU/free Space availability and wake-up timing are not a 24/7 service guarantee. This is the no-charge option, with best-effort scheduled updates.

## Local run

```powershell
.venv\Scripts\python.exe -m uvicorn mobile.mobile_api:app --host 0.0.0.0 --port 7860
```
