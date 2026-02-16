import os
import aiohttp
from typing import Any, Dict, Optional

from bot.config import OPENCLAW_API_URL


class APIError(RuntimeError):
    pass


def _base_url() -> str:
    base = (OPENCLAW_API_URL or "").strip().rstrip("/")
    if not base:
        raise APIError("OPENCLAW_API_URL is empty")

    # если забыли схему — добавим https://
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "https://" + base

    return base


def _join(path: str) -> str:
    base = _base_url()
    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return base + p


async def get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    url = _join(path)
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t) as s:
        async with s.get(url, params=params) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise APIError(f"GET {url} -> {r.status}: {data}")
            return data


async def post(path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    url = _join(path)
    t = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=t) as s:
        async with s.post(url, json=(payload or {})) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise APIError(f"POST {url} -> {r.status}: {data}")
            return data
