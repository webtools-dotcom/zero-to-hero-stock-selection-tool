---
title: AlphaSniper Terminal
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
---

# AlphaSniper — NSE/BSE 9:20 Mobile Terminal

Zero-chart, installable mobile PWA backed by a multi-user FastAPI service.

The app is a CPU-only FastAPI service hosted through the free Hugging Face Gradio + ZeroGPU runtime. Gradio owns the single server and the FastAPI routes are attached to it; the ZeroGPU probe is registered for the platform but never runs automatically. No GPU is used by the app. The PWA is available at `/` and `/sniper`.

- **9:20 Action** — point-in-time conviction cards with entry, max chase, structural SL, T1/T2, and a full fundamental X-Ray.
- **AI Chat** — per-phone Gemini/Groq/OpenRouter key, with a deterministic quant fallback when no key is saved.
- **My Vault** — Upstox token, LLM key, and risk budget stored only in that phone's `localStorage`.
- **Automatic EOD sync** — weekdays at 16:40 IST, with a 19:15 IST late-bhavcopy retry.

Run locally:

```powershell
.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 7860
```

Open <http://localhost:7860> or <http://localhost:7860/sniper>. Hugging Face deployment instructions are in [DEPLOY_FREE_24_7.md](DEPLOY_FREE_24_7.md). Free hosting can sleep and has ephemeral storage, so the scheduler is best-effort rather than guaranteed 24/7.

The desktop Streamlit terminal remains in `ui/app.py` and is unchanged by the mobile layer.
