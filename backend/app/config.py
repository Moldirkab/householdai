"""Settings read from environment variables (or a .env file in the backend folder)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'householdai.db'}")
NATIONAL_DATA = BACKEND_DIR / "data" / "ce_monthly_2017_2024.csv"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

# LLM for recommendations. Leave LLM_API_KEY empty to use rule-based recommendations only.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()   # anthropic | openai | gemini
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini", "gemini": "gemini-2.0-flash"}
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "25"))

SEED_DEMO_ON_START = os.getenv("SEED_DEMO_ON_START", "1") == "1"
