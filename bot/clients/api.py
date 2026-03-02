import os
import aiohttp


# Keep-alive session (reuse across requests)
_SESSION: aiohttp.ClientSession | None = None

def _timeout(timeout: int) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=timeout)

async def _get_session(timeout: int) -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        return _SESSION
    _SESSION = aiohttp.ClientSession(timeout=_timeout(timeout))
    return _SESSION
_SESSION: aiohttp.ClientSession | None = None

async def _session(timeout: int) -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        return _SESSION
    t = aiohttp.ClientTimeout(total=timeout)
    _SESSION = aiohttp.ClientSession(timeout=t)
    return _SESSION
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
    s = await _session(timeout)
    async with s.get(url, params=params) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise APIError(f"GET {url} -> {r.status}: {data}")
            return data


async def post(path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    url = _join(path)
    s = await _session(timeout)
    async with s.post(url, json=(payload or {})) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise APIError(f"POST {url} -> {r.status}: {data}")
            return data
