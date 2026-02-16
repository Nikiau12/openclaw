import os
import aiohttp

API_URL = os.getenv("OPENCLAW_API_URL", "").rstrip("/")

class APIError(RuntimeError):
    pass

async def post(path: str, payload: dict) -> dict:
    if not API_URL:
        raise APIError("OPENCLAW_API_URL is empty (set Railway Variable).")
    url = f"{API_URL}{path}"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload) as r:
            text = await r.text()
            if r.status >= 400:
                raise APIError(f"{r.status}: {text[:300]}")
            return await r.json()
