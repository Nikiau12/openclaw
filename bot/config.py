import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENCLAW_API_URL = os.getenv("OPENCLAW_API_URL", "").strip().rstrip("/")

TRC20_ADDRESS = os.getenv("TRC20_ADDRESS", "YOUR_TRC20_ADDRESS").strip()
ACCESS_STATE_PATH = os.getenv("ACCESS_STATE_PATH", "data/access_state.json").strip()

ADMIN_USER_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_USER_IDS", "").split(",")
    if x.strip()
}
