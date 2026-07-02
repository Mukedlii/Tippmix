from __future__ import annotations

from typing import Any, Dict, List

from bot.providers.reddit_tipsters import scrape_reddit_tipsters

from .base_expert import BaseExpertSource


class RedditExpertSource(BaseExpertSource):
    source_name = "reddit"

    def fetch_picks(self, max_items: int = 20) -> List[Dict[str, Any]]:
        picks = scrape_reddit_tipsters() or []
        out: List[Dict[str, Any]] = []
        for item in picks[:max_items]:
            out.append(
                {
                    "source": "reddit",
                    "pick": item.get("pick") or item.get("selection") or item.get("bet"),
                    "confidence": item.get("confidence") or item.get("score") or 0.5,
                    "reasoning": item.get("reasoning") or item.get("analysis") or "",
                    "author": item.get("author") or item.get("tipster") or "unknown",
                    "fixture_hint": item.get("match") or item.get("fixture") or "",
                    "timestamp": item.get("timestamp") or item.get("created_utc") or "",
                }
            )
        return out
