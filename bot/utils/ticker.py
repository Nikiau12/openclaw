import re

_TICKER_RE = re.compile(r"\b([A-Z]{2,10})[_\-/ ]?(USDT|USD)\b", re.IGNORECASE)

def extract_ticker(text: str) -> str:
    if not text:
        return "BTC_USDT"
    m = _TICKER_RE.search(text.upper())
    if not m:
        return "BTC_USDT"
    base = m.group(1).upper()
    quote = m.group(2).upper()
    return f"{base}_{quote}"

def clamp_user_text(text: str, max_len: int = 400) -> str:
    text = (text or "").strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text
