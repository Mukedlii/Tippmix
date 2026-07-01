from __future__ import annotations

from typing import Any, Dict, List

from bot.scrapers.base_scraper import BaseScraper

from .base_expert import BaseExpertSource


class TwitterExpertSource(BaseExpertSource):
    source_name = "twitter"

    def __init__(self) -> None:
        self.scraper = BaseScraper("twitter_signals")

    def fetch_picks(self, max_items: int = 20) -> List[Dict[str, Any]]:
        query = "soccer betting tips"
        feed_url = "https://nitter.net/search/rss"
        data = self.scraper.request_text(feed_url, params={"f": "tweets", "q": query}, cache_ttl_seconds=2 * 3600)
        if not data:
            return []

        out: List[Dict[str, Any]] = []
        items = data.split("<item>")
        for chunk in items[1 : max_items + 1]:
            title = _extract_xml(chunk, "title")
            author = _extract_xml(chunk, "creator") or _extract_xml(chunk, "author")
            pub = _extract_xml(chunk, "pubDate")
            if not title:
                continue
            out.append(
                {
                    "source": "twitter",
                    "pick": title,
                    "confidence": 0.45,
                    "reasoning": title,
                    "author": author or "unknown",
                    "fixture_hint": title,
                    "timestamp": pub or "",
                }
            )
        return out


def _extract_xml(chunk: str, tag: str) -> str:
    start = f"<{tag}>"
    end = f"</{tag}>"
    if start in chunk and end in chunk:
        return chunk.split(start, 1)[1].split(end, 1)[0].strip()
    return ""
