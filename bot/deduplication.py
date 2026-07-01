"""
bot/deduplication.py

De-duplicate tips: keep only BEST tip per match.
"""

from typing import List, Dict, Any


def _norm_team_name(raw: Any) -> str:
    return " ".join(str(raw or "").strip().lower().split())


def _match_key(tip: Dict[str, Any]) -> str:
    fixture_id = tip.get("fixture_id")
    if fixture_id is not None and str(fixture_id).strip() != "":
        return f"fid:{fixture_id}"

    home = _norm_team_name(tip.get("home_team"))
    away = _norm_team_name(tip.get("away_team"))
    if home or away:
        return f"{home} vs {away}"

    league = _norm_team_name(tip.get("league_name"))
    kickoff = str(tip.get("kickoff_local") or "").strip().lower()
    selection = _norm_team_name(tip.get("selection") or tip.get("tip"))
    return f"fallback:{league}|{kickoff}|{selection}"


def _score_for_keep(tip: Dict[str, Any]) -> tuple[float, float, float]:
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _normalize_probability(raw: Any) -> float:
        p = _to_float(raw, -1.0)
        if p < 0:
            return -1.0
        if p > 1.0 and p <= 100.0:
            p = p / 100.0
        return max(0.0, min(1.0, p))

    try:
        conf_raw = _to_float(tip.get("confidence", 0) or 0, 0.0)
    except Exception:
        conf_raw = 0.0
    conf_norm = max(0.0, min(1.0, conf_raw / 5.0))

    prob = _normalize_probability(tip.get("p"))
    chance = prob if prob >= 0 else conf_norm

    try:
        odds = float(
            tip.get("best_odds")
            or tip.get("odds_pick")
            or tip.get("odds_estimate")
            or 0
        )
    except Exception:
        odds = 0.0
    # "Best chance" priority: highest chance first, then confidence.
    # Final tie-break prefers lower odds (typically safer / higher implied chance).
    odds_tiebreak = -odds if odds > 0 else 0.0
    return (chance, conf_raw, odds_tiebreak)


def deduplicate_tips(tips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group tips by match, keep only the highest confidence/probability pick per match.
    
    Args:
        tips: List of tip dictionaries with home_team, away_team, confidence, p (probability)
    
    Returns:
        Deduplicated list (1 tip per match)
    """
    if not tips:
        return []
    
    by_match: Dict[str, Dict[str, Any]] = {}
    
    for tip in tips:
        match_key = _match_key(tip)
        
        if match_key not in by_match:
            by_match[match_key] = tip
        else:
            # Compare: prefer higher confidence, then higher probability, then higher odds
            current_score = _score_for_keep(by_match[match_key])
            new_score = _score_for_keep(tip)
            if new_score > current_score:
                by_match[match_key] = tip
    
    return list(by_match.values())
