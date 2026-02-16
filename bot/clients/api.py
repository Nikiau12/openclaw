import aiohttp
import re
from typing import Any, Dict, Optional

from bot.config import OPENCLAW_API_URL

def _normalize_base_url(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if not base:
        return base
    if not re.match(r"^https?://", base):
        base = "https://" + base
    return base

BASE_URL = _normalize_base_url(OPENCLAW_API_URL)

async def post(path: str, payload: Optional[Dict[str, Any]] = None, timeout_s: int = 30) -> Dict[str, Any]:
    if not BASE_URL:
        raise RuntimeError("OPENCLAW_API_URL is empty")

    path = "/" + path.lstrip("/")
    url = f"{BASE_URL}{path}"

    t = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=t) as s:
        async with s.post(url, json=(payload or {})) as r:
            # если API вернул ошибку — покажем тело
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"API {r.status}: {text}")
            try:
                return await r.json()
            except Exception:
                return {"ok": True, "raw": text}
