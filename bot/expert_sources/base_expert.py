from __future__ import annotations

from typing import Any, Dict, List


class BaseExpertSource:
    source_name = "expert"

    def fetch_picks(self, max_items: int = 20) -> List[Dict[str, Any]]:
        return []
