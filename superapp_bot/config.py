import os
from pathlib import Path
from groq import Groq

BASE_DIR = Path(__file__).parent
LAKE_DIR = BASE_DIR / "data" / "datalake_json"
USERS_FILE = BASE_DIR / "users.json"   # только для первичной миграции

DATABASE_URL = os.environ.get("DATABASE_URL", "")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", f"https://your-app.onrender.com/{BOT_TOKEN}")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_ID = 933916297

_GROQ_KEYS = [k.strip() for k in os.environ.get("GROQ_API_KEYS", GROQ_KEY).split(",") if k.strip()]
groq_clients = [Groq(api_key=k, max_retries=0) for k in _GROQ_KEYS] if _GROQ_KEYS else []
