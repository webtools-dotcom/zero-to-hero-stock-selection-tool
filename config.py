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
UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
UPSTOX_BASE_URL = "https://api.upstox.com/v2"

# Secret required to trigger POST /api/eod-sync manually (unset = manual sync disabled; the scheduler still runs)
EOD_SYNC_TOKEN = os.getenv("EOD_SYNC_TOKEN", "")

# LLM Configuration (3.6/3.5-flash = only 20 req/day free tier; flash-lite has a separate, larger pool)
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "gemini")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini/gemini-3.5-flash-lite")

SUPPORTED_MODELS = {
    "Gemini 3.5 Flash-Lite (Free Tier Daily Scan)": ("gemini", "gemini/gemini-3.5-flash-lite"),
    "Gemini 3.6 Flash (20 req/day Free Tier)": ("gemini", "gemini/gemini-3.6-flash"),
    "Gemini 3.1 Flash-Lite (Backup)": ("gemini", "gemini/gemini-3.1-flash-lite"),
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