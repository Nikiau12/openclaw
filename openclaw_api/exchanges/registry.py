from __future__ import annotations

import httpx

from openclaw_api.exchanges.mexc.spot import MexcSpot


def get_mexc_spot(client: httpx.AsyncClient | None = None) -> MexcSpot:
    return MexcSpot(client=client)
