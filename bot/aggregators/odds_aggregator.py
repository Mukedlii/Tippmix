from __future__ import annotations

from typing import Any, Dict, List, Optional

from .confidence_scorer import source_confidence


class OddsAggregator:
    def merge(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        clean = [r for r in rows if r]
        if not clean:
            return {"found": False, "sources": []}

        outcomes = {"1": [], "X": [], "2": []}
        for row in clean:
            src = row.get("source") or row.get("bookmaker") or "unknown"
            weight = source_confidence(str(src))
            outcomes["1"].append((_to_float(row.get("odds_1")), weight, src))
            outcomes["X"].append((_to_float(row.get("odds_x")), weight, src))
            outcomes["2"].append((_to_float(row.get("odds_2")), weight, src))

        avg_1 = _weighted_avg(outcomes["1"])
        avg_x = _weighted_avg(outcomes["X"])
        avg_2 = _weighted_avg(outcomes["2"])
        best_1, src_1 = _best(outcomes["1"])
        best_x, src_x = _best(outcomes["X"])
        best_2, src_2 = _best(outcomes["2"])

        if not best_1 or not best_2:
            return {"found": False, "sources": list({str(r.get('source')) for r in clean if r.get('source')})}

        return {
            "found": True,
            "sources": list({str(r.get("source") or r.get("bookmaker") or "unknown") for r in clean}),
            "odds_1_avg": avg_1,
            "odds_x_avg": avg_x,
            "odds_2_avg": avg_2,
            "odds_1_best": best_1,
            "odds_x_best": best_x,
            "odds_2_best": best_2,
            "best_bookmakers": {"1": src_1, "X": src_x, "2": src_2},
        }


def _to_float(value: Any) -> Optional[float]:
    try:
        v = float(value)
        if 1.01 <= v <= 50.0:
            return round(v, 3)
    except Exception:
        return None
    return None


def _weighted_avg(values: List[tuple[Optional[float], float, str]]) -> Optional[float]:
    nums = [(v, w) for v, w, _ in values if v is not None]
    if not nums:
        return None
    sw = sum(w for _, w in nums)
    if sw <= 0:
        return None
    return round(sum(v * w for v, w in nums) / sw, 3)


def _best(values: List[tuple[Optional[float], float, str]]) -> tuple[Optional[float], Optional[str]]:
    valid = [(v, src) for v, _, src in values if v is not None]
    if not valid:
        return None, None
    return max(valid, key=lambda x: x[0])
