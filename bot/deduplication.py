"""
bot/deduplication.py

De-duplicate tips: keep only BEST tip per match.
"""

from typing import List, Dict, Any


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
        home = tip.get("home_team", "")
        away = tip.get("away_team", "")
        match_key = f"{home} vs {away}"
        
        if match_key not in by_match:
            by_match[match_key] = tip
        else:
            # Compare: prefer higher confidence, then higher probability
            current_conf = by_match[match_key].get("confidence", 0) or 0
            new_conf = tip.get("confidence", 0) or 0
            
            current_p = by_match[match_key].get("p", 0) or 0
            new_p = tip.get("p", 0) or 0
            
            # Higher confidence wins
            if new_conf > current_conf:
                by_match[match_key] = tip
            elif new_conf == current_conf and new_p > current_p:
                # Same confidence, higher probability wins
                by_match[match_key] = tip
    
    return list(by_match.values())
