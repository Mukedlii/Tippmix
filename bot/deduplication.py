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
    try:
        conf = float(tip.get("confidence", 0) or 0)
    except Exception:
        conf = 0.0
    try:
        prob = float(tip.get("p", 0) or 0)
    except Exception:
        prob = 0.0
    try:
        odds = float(
            tip.get("best_odds")
            or tip.get("odds_pick")
            or tip.get("odds_estimate")
            or 0
        )
    except Exception:
        odds = 0.0
    return (conf, prob, odds)


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
