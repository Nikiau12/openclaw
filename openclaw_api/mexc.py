from __future__ import annotations

import time
import requests
from typing import Any, Dict, List, Optional, Tuple

MEXC_BASE = "https://api.mexc.com"

# простейший кэш, чтобы не дёргать /exchangeInfo на каждый запрос
_CACHE: Dict[str, Any] = {"ts": 0, "symbols": set(), "raw": None}
_CACHE_TTL_SEC = 60 * 30  # 30 минут

def _clean(s: str) -> str:
    return (
        s.strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

def load_symbols(force: bool = False) -> Tuple[set, Any]:
    now = int(time.time())
    if (not force) and _CACHE["raw"] is not None and (now - int(_CACHE["ts"])) < _CACHE_TTL_SEC:
        return _CACHE["symbols"], _CACHE["raw"]

    url = f"{MEXC_BASE}/api/v3/exchangeInfo"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    symbols = set()
    for it in data.get("symbols", []):
        sym = it.get("symbol")
        if sym:
            symbols.add(str(sym).upper())

    _CACHE["ts"] = now
    _CACHE["symbols"] = symbols
    _CACHE["raw"] = data
    return symbols, data

def resolve_symbol(user_input: str) -> str:
    """
    Принимает: btc, BTC_USDT, BTCUSDT, BTC/USDT, pepeusdt, sol-usdt
    Возвращает: BTCUSDT
    """
    s = _clean(user_input)

    symbols, _ = load_symbols(force=False)

    # 1) если уже точное совпадение
    if s in symbols:
        return s

    # 2) если пользователь дал только BASE (btc) -> пробуем BASEUSDT
    candidates = [s + "USDT", s + "USDC", s + "BTC"]
    for c in candidates:
        if c in symbols:
            return c

    # 3) если пользователь написал "PEPEUSDT" ок, иначе попробуем найти по префиксу/суффиксу
    #    (осторожно, может быть много совпадений)
    #    оставим как fallback: если есть единственный матч по startswith
    matches = [x for x in symbols if x.startswith(s)]
    if len(matches) == 1:
        return matches[0]

    raise ValueError(f"Symbol not found for input: {user_input}")

def ticker_24h(symbol: str) -> Dict[str, Any]:
    url = f"{MEXC_BASE}/api/v3/ticker/24hr"
    r = requests.get(url, params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return r.json()

def klines(symbol: str, interval: str = "1m", limit: int = 120) -> List[List[Any]]:
    url = f"{MEXC_BASE}/api/v3/klines"
    r = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": int(limit)}, timeout=10)
    r.raise_for_status()
    return r.json()
