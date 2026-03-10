import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from bot.config import OPENCLAW_API_URL

log = logging.getLogger(__name__)


class APIError(RuntimeError):
    pass


def _base_url() -> str:
    base = (OPENCLAW_API_URL or "").strip().rstrip("/")
    if not base:
        raise APIError("OPENCLAW_API_URL is empty")

    if not base.startswith("http://") and not base.startswith("https://"):
        base = "https://" + base

    return base


def _join(path: str) -> str:
    base = _base_url()
    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def _timeout(timeout: int) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=timeout)


async def _read_json_or_text(r: aiohttp.ClientResponse) -> Dict[str, Any]:
    raw = await r.text()
    if not raw.strip():
        return {}

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {"raw": data}
    except Exception:
        return {"raw_text": raw[:2000]}


async def get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    url = _join(path)

    try:
        async with aiohttp.ClientSession(timeout=_timeout(timeout)) as s:
            async with s.get(url, params=params) as r:
                data = await _read_json_or_text(r)
                if r.status >= 400:
                    raise APIError(f"GET {url} -> {r.status}: {data}")
                return data
    except asyncio.TimeoutError as e:
        log.exception("API GET timeout url=%s timeout=%s params=%r", url, timeout, params)
        raise APIError(f"GET timeout {url} ({timeout}s)") from e
    except aiohttp.ClientError as e:
        log.exception("API GET client error url=%s params=%r", url, params)
        raise APIError(f"GET client error {url}: {e}") from e


async def post(path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    url = _join(path)
    body = payload or {}

    try:
        async with aiohttp.ClientSession(timeout=_timeout(timeout)) as s:
            async with s.post(url, json=body) as r:
                data = await _read_json_or_text(r)
                if r.status >= 400:
                    raise APIError(f"POST {url} -> {r.status}: {data}")
                return data
    except asyncio.TimeoutError as e:
        log.exception("API POST timeout url=%s timeout=%s payload=%r", url, timeout, body)
        raise APIError(f"POST timeout {url} ({timeout}s)") from e
    except aiohttp.ClientError as e:
        log.exception("API POST client error url=%s payload=%r", url, body)
        raise APIError(f"POST client error {url}: {e}") from e
