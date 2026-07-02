from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = Path(cache_dir or os.getenv("TIPPMIX_CACHE_DIR", "data/pipeline_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            exp = payload.get("expires_at")
            if exp and datetime.now(timezone.utc) > datetime.fromisoformat(exp):
                return None
            return payload.get("value")
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 24 * 3600, match_start_ts: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(1, int(ttl_seconds)))
        if match_start_ts:
            try:
                dt = datetime.fromisoformat(str(match_start_ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                expires_at = min(expires_at, dt)
            except Exception:
                pass

        payload = {
            "cached_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "value": value,
        }
        self._path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
