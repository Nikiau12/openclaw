import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENCLAW_API_URL   = os.getenv("OPENCLAW_API_URL", "").strip().rstrip("/")
