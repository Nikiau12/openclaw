from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from bot.config import ACCESS_STATE_PATH
from bot.storage.access_store import JsonAccessStore


UTC = timezone.utc

FREE_TOTAL_LIMIT = 3
ANALYTICS_KEY = "analytics_total"


@dataclass
class AccessDecision:
    allowed: bool
    is_pro: bool
    remaining: int
    limit: int
    reason: str


class AccessService:
    def __init__(self, store: Optional[JsonAccessStore] = None) -> None:
        self.store = store or JsonAccessStore(ACCESS_STATE_PATH)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def _is_pro_active(self, user: dict) -> bool:
        if user.get("plan") != "pro":
            return False
        expires_at = self._parse_dt(user.get("expires_at"))
        if expires_at is None:
            return False
        return expires_at > self._now()

    def _ensure_period(self, user: dict) -> dict:
        today = self._now().date().isoformat()
        if user.get("usage_period_start") != today:
            user["usage_period_start"] = today
            user["usage"] = {ANALYTICS_KEY: 0}
        return user

    def get_user_state(self, user_id: int) -> dict:
        user = self.store.get_user(user_id)
        user = self._ensure_period(user)

        if user.get("plan") == "pro" and not self._is_pro_active(user):
            user["plan"] = "free"
            user["expires_at"] = None
            self.store.save_user(user_id, user)
            return user

        self.store.save_user(user_id, user)
        return user

    def check(self, user_id: int, feature: str) -> AccessDecision:
        user = self.get_user_state(user_id)

        if self._is_pro_active(user):
            return AccessDecision(
                allowed=True,
                is_pro=True,
                remaining=999999,
                limit=999999,
                reason="pro",
            )

        limit = FREE_TOTAL_LIMIT
        used = int(user.get("usage", {}).get(ANALYTICS_KEY, 0))
        remaining = max(0, limit - used)

        if used >= limit:
            return AccessDecision(
                allowed=False,
                is_pro=False,
                remaining=0,
                limit=limit,
                reason="limit_reached",
            )

        return AccessDecision(
            allowed=True,
            is_pro=False,
            remaining=remaining,
            limit=limit,
            reason="free_ok",
        )

    def consume(self, user_id: int, feature: str) -> None:
        user = self.get_user_state(user_id)
        if self._is_pro_active(user):
            return
        usage = user.setdefault("usage", {})
        usage[ANALYTICS_KEY] = int(usage.get(ANALYTICS_KEY, 0)) + 1
        self.store.save_user(user_id, user)

    def activate_pro(self, user_id: int, days: int = 30) -> None:
        user = self.get_user_state(user_id)
        expires_at = self._now() + timedelta(days=days)
        user["plan"] = "pro"
        user["expires_at"] = expires_at.isoformat()
        self.store.save_user(user_id, user)

    def deactivate_pro(self, user_id: int) -> None:
        user = self.get_user_state(user_id)
        user["plan"] = "free"
        user["expires_at"] = None
        self.store.save_user(user_id, user)
