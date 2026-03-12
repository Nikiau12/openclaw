from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional


class JsonPaymentStore:
    def __init__(self, path: str = "data/payment_requests.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self._write({"requests": [], "sessions": {}})

    def _read(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {"requests": [], "sessions": {}}
            return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def set_session_target(self, submitter_user_id: int, source_user_id: int) -> None:
        data = self._read()
        data.setdefault("sessions", {})[str(submitter_user_id)] = source_user_id
        self._write(data)

    def get_session_target(self, submitter_user_id: int) -> Optional[int]:
        data = self._read()
        raw = data.get("sessions", {}).get(str(submitter_user_id))
        return int(raw) if raw is not None else None

    def tx_hash_exists(self, tx_hash: str) -> bool:
        data = self._read()
        tx = tx_hash.strip().lower()
        for item in data.get("requests", []):
            if str(item.get("tx_hash", "")).strip().lower() == tx:
                return True
        return False

    def add_request(self, payload: Dict[str, Any]) -> None:
        data = self._read()
        data.setdefault("requests", []).append(payload)
        self._write(data)
