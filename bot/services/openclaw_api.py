import os
import asyncio
import aiohttp
from typing import Any, Dict, Optional

OPENCLAW_API_URL = os.getenv("OPENCLAW_API_URL", "").rstrip("/")
TIMEOUT_PLAN_S = float(os.getenv("BOT_TIMEOUT_PLAN_S", "3.0"))
TIMEOUT_AI_S = float(os.getenv("BOT_TIMEOUT_AI_S", "15.0"))

class ApiError(Exception):
    pass

async def _get_json(url: str, timeout_s: float) -> Dict[str, Any]:
    t = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=t) as session:
        async with session.get(url) as resp:
            if resp.status >= 400:
                raise ApiError(f"HTTP {resp.status}")
            return await resp.json()

async def fetch_plan_structure(ticker: str) -> Dict[str, Any]:
    if not OPENCLAW_API_URL:
        raise ApiError("OPENCLAW_API_URL not set")
    # mode=structure (as you described)
    url = f"{OPENCLAW_API_URL}/plan/v3?mode=structure&ticker={ticker}"
    return await _get_json(url, TIMEOUT_PLAN_S)

async def fetch_dexter_ai(ticker_or_text: str) -> Dict[str, Any]:
    if not OPENCLAW_API_URL:
        raise ApiError("OPENCLAW_API_URL not set")
    # analysis=1
    url = f"{OPENCLAW_API_URL}/dexter/run?analysis=1&query={aiohttp.helpers.quote(ticker_or_text)}"
    return await _get_json(url, TIMEOUT_AI_S)
