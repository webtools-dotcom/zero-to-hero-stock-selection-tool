---
title: AlphaSniper Terminal
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
---

# AlphaSniper — NSE/BSE 9:20 Mobile Terminal

Zero-chart, installable mobile PWA backed by a multi-user FastAPI service.

Hugging Face runs the root `app.py` launcher, which binds the existing FastAPI app directly to Uvicorn on port `7860`. Gradio is only the free Space runtime; no Gradio UI is mounted, so the mobile PWA and all API routes stay identical. The PWA is available at `/` and `/sniper`.

- **9:20 Action** — point-in-time conviction cards with entry, max chase, structural SL, T1/T2, and a full fundamental X-Ray.
- **AI Chat** — per-phone Gemini/Groq/OpenRouter key, with a deterministic quant fallback when no key is saved.
- **My Vault** — Upstox token, LLM key, and risk budget stored only in that phone's `localStorage`.
- **Automatic EOD sync** — weekdays at 16:40 IST, with a 19:15 IST late-bhavcopy retry.

Run locally with the same launcher used by Hugging Face:

```powershell
.venv\Scripts\python.exe app.py
```

Open <http://localhost:7860> or <http://localhost:7860/sniper>. Deployment instructions are in [DEPLOY_FREE_24_7.md](DEPLOY_FREE_24_7.md).

The desktop Streamlit terminal remains in `ui/app.py` and is unchanged by the mobile layer.
