from __future__ import annotations

import hashlib
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests


DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class BaseScraper:
    def __init__(
        self,
        source_name: str,
        cache_dir: Optional[str] = None,
        min_delay_seconds: float = 1.0,
        max_delay_seconds: float = 3.0,
    ) -> None:
        self.source_name = source_name
        self.min_delay_seconds = max(0.0, float(min_delay_seconds))
        self.max_delay_seconds = max(self.min_delay_seconds, float(max_delay_seconds))
        self.cache_dir = Path(cache_dir or os.getenv("TIPPMIX_SCRAPER_CACHE_DIR", "data/scraper_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._proxy_pool = [p.strip() for p in (os.getenv("TIPPMIX_PROXY_LIST") or "").split(",") if p.strip()]

    def _random_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(DEFAULT_USER_AGENTS),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _delay(self) -> None:
        time.sleep(random.uniform(self.min_delay_seconds, self.max_delay_seconds))

    def _cache_key(self, url: str, params: Optional[Dict[str, Any]]) -> str:
        payload = json.dumps({"url": url, "params": params or {}}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{self.source_name}_{key}.json"

    def _read_cache(self, key: str, ttl_seconds: int = 24 * 3600) -> Optional[Any]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = payload.get("expires_at")
            if expires_at and datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
                return None
            if ttl_seconds > 0:
                ts = payload.get("cached_at")
                if ts:
                    cached_at = datetime.fromisoformat(ts)
                    if datetime.now(timezone.utc) - cached_at > timedelta(seconds=ttl_seconds):
                        return None
            return payload.get("data")
        except Exception:
            return None

    def _write_cache(self, key: str, data: Any, ttl_seconds: int = 24 * 3600) -> None:
        try:
            now = datetime.now(timezone.utc)
            payload = {
                "cached_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=max(1, ttl_seconds))).isoformat(),
                "data": data,
            }
            self._cache_path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return

    def request_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 20,
        retries: int = 3,
        cache_ttl_seconds: int = 24 * 3600,
    ) -> Optional[Any]:
        key = self._cache_key(url, params)
        cached = self._read_cache(key, ttl_seconds=cache_ttl_seconds)
        if cached is not None:
            return cached

        for attempt in range(1, retries + 1):
            self._delay()
            headers = self._random_headers()
            proxy = random.choice(self._proxy_pool) if self._proxy_pool else None
            proxies = {"http": proxy, "https": proxy} if proxy else None
            try:
                resp = self._session.get(url, params=params, headers=headers, timeout=timeout, proxies=proxies)
                if resp.status_code == 200:
                    data = resp.json()
                    self._write_cache(key, data, ttl_seconds=cache_ttl_seconds)
                    return data
                if resp.status_code == 429 and attempt < retries:
                    time.sleep(2 * attempt)
                    continue
                if 500 <= resp.status_code < 600 and attempt < retries:
                    continue
                return None
            except Exception:
                if attempt == retries:
                    return None
        return None

    def request_text(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 20,
        retries: int = 3,
        cache_ttl_seconds: int = 24 * 3600,
    ) -> Optional[str]:
        key = self._cache_key(url, params)
        cached = self._read_cache(key, ttl_seconds=cache_ttl_seconds)
        if isinstance(cached, str):
            return cached

        for attempt in range(1, retries + 1):
            self._delay()
            headers = self._random_headers()
            proxy = random.choice(self._proxy_pool) if self._proxy_pool else None
            proxies = {"http": proxy, "https": proxy} if proxy else None
            try:
                resp = self._session.get(url, params=params, headers=headers, timeout=timeout, proxies=proxies)
                if resp.status_code == 200:
                    text = resp.text
                    self._write_cache(key, text, ttl_seconds=cache_ttl_seconds)
                    return text
                if resp.status_code == 429 and attempt < retries:
                    time.sleep(2 * attempt)
                    continue
                if 500 <= resp.status_code < 600 and attempt < retries:
                    continue
                return None
            except Exception:
                if attempt == retries:
                    return None
        return None
