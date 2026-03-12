import os

PAYMENT_BOT_TOKEN = os.getenv("PAYMENT_BOT_TOKEN", "").strip()
PAYMENT_ADMIN_ID = int(os.getenv("PAYMENT_ADMIN_ID", "0").strip() or "0")
PAYMENT_STATE_PATH = os.getenv("PAYMENT_STATE_PATH", "data/payment_requests.json").strip()
