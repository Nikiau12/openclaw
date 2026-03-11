from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict


class JsonAccessStore:
    def __init__(self, path: str = "data/access_state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self._write({"users": {}})

    def _read(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {"users": {}}
            return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get_user(self, user_id: int) -> Dict[str, Any]:
        data = self._read()
        users = data.setdefault("users", {})
        key = str(user_id)
        user = users.get(key)
        if user is None:
            user = {
                "plan": "free",
                "expires_at": None,
                "usage_period_start": None,
                "usage": {
                    "plan": 0,
                    "scan": 0,
                    "top": 0,
                },
            }
            users[key] = user
            self._write(data)
        return user

    def save_user(self, user_id: int, user_data: Dict[str, Any]) -> None:
        data = self._read()
        data.setdefault("users", {})[str(user_id)] = user_data
        self._write(data)
