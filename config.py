import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "local_data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = str(DATA_DIR / "alpha_terminal.duckdb")

# Upstox Configuration
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_INSTRUMENTS_URL = "[https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz](https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz)"
UPSTOX_BASE_URL = "[https://api.upstox.com/v2](https://api.upstox.com/v2)"

# LLM Configuration
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "gemini")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini/gemini-2.5-flash")

SUPPORTED_MODELS = {
    "Gemini 2.5 Pro (Deep Reasoning)": ("gemini", "gemini/gemini-2.5-pro"),
    "Gemini 2.5 Flash (Fast Daily Scan)": ("gemini", "gemini/gemini-2.5-flash"),
    "Groq Llama-3.3-70B Versatile": ("groq", "groq/llama-3.3-70b-versatile"),
    "Groq DeepSeek-R1 Distill 70B": ("groq", "groq/deepseek-r1-distill-llama-70b"),
    "OpenRouter Auto": ("openrouter", "openrouter/auto"),
}

# Mode A & Mode B Liquidity & Safety Thresholds
MODE_A_MIN_60D_TURNOVER_CR = 0.15   # ₹15 Lakhs 60d median floor (catches dormant small-caps)
MODE_A_MIN_3D_TURNOVER_CR = 0.75    # ₹75 Lakhs 3d ignition floor (ensures tradable wakeup)
MODE_B_MIN_20D_TURNOVER_CR = 3.00   # ₹3 Crore 20d median floor for high-velocity compounders

MAX_CIRCUIT_DAYS_IN_20D = 10        # Reject operator-locked circuit stocks
MAX_PROMOTER_PLEDGE_PCT = 25.0      # Reject high pledge unless actively reducing