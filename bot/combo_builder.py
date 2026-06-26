#!/usr/bin/env python3
"""
Combo Bet Builder

Automatically builds combo bets (accumulators) from daily picks.
Selects safest bets and calculates combined odds.

Marketing gold: big wins from small stakes!
"""

from typing import List, Dict, Optional, Any, Set
import random


def calculate_combo_odds(picks: List[Dict]) -> float:
    """
    Calculate combined odds for a combo bet
    
    Returns:
        Combined odds (multiplied)
    """
    odds = 1.0
    
    for pick in picks:
        # Try different odds fields
        pick_odds = (
            pick.get('best_odds') or 
            pick.get('odds_pick') or 
            pick.get('odds_estimate') or
            1.8  # Default fallback
        )
        
        odds *= pick_odds
    
    return round(odds, 2)


def select_safe_combo(picks: List[Dict], combo_size: int = 3) -> Optional[List[Dict]]:
    """
    Select safest picks for a combo bet
    
    Criteria:
    - High confidence (⭐⭐⭐⭐+)
    - Low risk level (safe/moderate)
    - Good odds (1.5-2.2 range)
    - Different leagues (diversification)
    
    Args:
        picks: All available picks
        combo_size: Number of picks in combo (3-5)
    
    Returns:
        List of selected picks or None
    """
    
    # Filter eligible picks
    eligible = []
    
    for pick in picks:
        confidence = pick.get('confidence', 0)
        risk = (pick.get('risk_level') or '').lower()
        odds = (
            pick.get('best_odds') or 
            pick.get('odds_pick') or 
            pick.get('odds_estimate') or 
            0
        )
        
        # Criteria
        is_high_confidence = confidence >= 3.5
        is_low_risk = risk in ['safe', 'alacsony', 'közepes', 'moderate']
        is_good_odds = 1.4 <= odds <= 2.5
        
        if is_high_confidence and is_low_risk and is_good_odds:
            pick['_combo_score'] = confidence + (odds * 0.5)  # Scoring
            eligible.append(pick)
    
    if len(eligible) < combo_size:
        return None  # Not enough safe picks
    
    # Sort by score
    eligible.sort(key=lambda x: x.get('_combo_score', 0), reverse=True)
    
    # Select top N from different leagues
    selected = []
    used_leagues = set()
    
    for pick in eligible:
        league = pick.get('league_name', '')
        
        # Prefer different leagues (diversification)
        if league in used_leagues and len(selected) < combo_size:
            continue
        
        selected.append(pick)
        used_leagues.add(league)
        
        if len(selected) >= combo_size:
            break
    
    # If not enough from different leagues, fill with best picks
    if len(selected) < combo_size:
        for pick in eligible:
            if pick not in selected:
                selected.append(pick)
                if len(selected) >= combo_size:
                    break
    
    return selected[:combo_size] if len(selected) >= combo_size else None


def select_risky_combo(picks: List[Dict], combo_size: int = 4) -> Optional[List[Dict]]:
    """
    Select picks for a risky combo (higher odds, bigger payout)
    
    Criteria:
    - Moderate-high confidence
    - Higher odds (1.8-3.5)
    - Mix of risk levels
    
    Args:
        picks: All available picks
        combo_size: Number of picks (4-6)
    
    Returns:
        List of selected picks or None
    """
    
    eligible = []
    
    for pick in picks:
        confidence = pick.get('confidence', 0)
        odds = (
            pick.get('best_odds') or 
            pick.get('odds_pick') or 
            pick.get('odds_estimate') or 
            0
        )
        
        # More relaxed criteria
        is_reasonable_confidence = confidence >= 2.5
        is_decent_odds = 1.7 <= odds <= 4.0
        
        if is_reasonable_confidence and is_decent_odds:
            pick['_combo_score'] = confidence * odds  # Higher odds preferred
            eligible.append(pick)
    
    if len(eligible) < combo_size:
        return None
    
    # Sort by score
    eligible.sort(key=lambda x: x.get('_combo_score', 0), reverse=True)
    
    # Select top N
    selected = eligible[:combo_size]
    
    return selected


def build_combos(picks: List[Dict]) -> Dict[str, Optional[List[Dict]]]:
    """
    Build both safe and risky combos
    
    Returns:
        {
            "safe": [picks] or None,
            "risky": [picks] or None
        }
    """
    
    return {
        "safe": select_safe_combo(picks, combo_size=3),
        "risky": select_risky_combo(picks, combo_size=4)
    }


def _pick_odds(pick: Dict[str, Any]) -> float:
    try:
        return float(
            pick.get("best_odds")
            or pick.get("odds_pick")
            or pick.get("odds_estimate")
            or 0.0
        )
    except Exception:
        return 0.0


def _pick_confidence(pick: Dict[str, Any]) -> float:
    try:
        return float(pick.get("confidence") or 0.0)
    except Exception:
        return 0.0


def _pick_id(pick: Dict[str, Any]) -> Any:
    return pick.get("fixture_id") or pick.get("match") or f"{pick.get('home_team')}-{pick.get('away_team')}-{pick.get('tip')}"


def _build_combo_group(
    picks: List[Dict[str, Any]],
    combo_size: int,
    max_groups: int,
    used_ids: Optional[Set[Any]] = None,
) -> List[List[Dict[str, Any]]]:
    used_ids = used_ids or set()
    ranked = sorted(
        [p for p in picks if _pick_odds(p) >= 1.2],
        key=lambda p: (_pick_confidence(p), _pick_odds(p)),
        reverse=True,
    )
    groups: List[List[Dict[str, Any]]] = []

    for _ in range(max_groups):
        current: List[Dict[str, Any]] = []
        local_ids: Set[Any] = set()
        for pick in ranked:
            pid = _pick_id(pick)
            if pid in used_ids or pid in local_ids:
                continue
            current.append(pick)
            local_ids.add(pid)
            if len(current) >= combo_size:
                break
        if len(current) >= combo_size:
            groups.append(current)
            used_ids.update(local_ids)
        else:
            break
    return groups


def _short_pick_name(pick: Dict[str, Any]) -> str:
    sel = (pick.get("selection") or pick.get("tip") or "").strip()
    mapping = {
        "Hazai győzelem": "H",
        "Vendég győzelem": "V",
        "Döntetlen": "X",
    }
    return mapping.get(sel, sel[:20] if sel else "Tip")


def _combo_to_marketing_dict(combo_picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_odds = calculate_combo_odds(combo_picks)
    return {
        "picks": combo_picks,
        "total_odds": total_odds,
        "label": " + ".join(
            f"{(p.get('home_team') or '').strip()} {_short_pick_name(p)}"
            for p in combo_picks
        ),
    }


def build_marketing_combos(vip_picks: List[Dict[str, Any]], free_picks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    VIP: minimum 2 kombó (ha van elég meccs), FREE: 1-2 kombó.
    """
    vip_groups = _build_combo_group(vip_picks, combo_size=2, max_groups=2)
    free_groups = _build_combo_group(free_picks, combo_size=2, max_groups=2)

    vip_combos = [_combo_to_marketing_dict(g) for g in vip_groups]
    free_combos = [_combo_to_marketing_dict(g) for g in free_groups]

    return {"vip": vip_combos, "free": free_combos}


def format_combo_for_telegram(
    combo_picks: List[Dict],
    combo_type: str = "SAFE",
    stake: int = 1000
) -> str:
    """
    Format combo bet for Telegram
    
    Args:
        combo_picks: Selected picks for combo
        combo_type: "SAFE" or "RISKY"
        stake: Bet amount in HUF
    
    Returns:
        Formatted string
    """
    
    if not combo_picks:
        return ""
    
    odds = calculate_combo_odds(combo_picks)
    potential_win = int(stake * odds)
    profit = potential_win - stake
    
    # Header
    emoji = "🎯" if combo_type == "SAFE" else "🎰"
    lines = [
        f"{emoji} *COMBO SZELVÉNY ({combo_type})*",
        "",
        f"💰 Tét: {stake:,} HUF",
        f"📊 Össz odds: *{odds:.2f}*",
        f"🏆 Potenciális nyeremény: *{potential_win:,} HUF*",
        f"💵 Profit: *+{profit:,} HUF* ({(profit/stake*100):.0f}%)",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 *MECCSEK:*",
        ""
    ]
    
    # Picks
    for i, pick in enumerate(combo_picks, 1):
        home = pick.get('home_team', '?')
        away = pick.get('away_team', '?')
        tip = pick.get('tip') or pick.get('selection', '?')
        
        pick_odds = (
            pick.get('best_odds') or 
            pick.get('odds_pick') or 
            pick.get('odds_estimate')
        )
        
        odds_str = f"@{pick_odds:.2f}" if pick_odds else ""
        
        # Shortened tip
        tip_short = tip.replace('győzelem', '').replace('Hazai', 'H').replace('Vendég', 'V').replace('Döntetlen', 'X').strip()
        
        lines.append(f"{i}. *{home}* vs {away}")
        lines.append(f"   🎯 {tip} {odds_str}")
        lines.append("")
    
    # Footer
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    
    if combo_type == "SAFE":
        lines.append("✅ Biztonságos kombó (3 tipp)")
        lines.append("📈 Várható esély: ~45-55%")
    else:
        lines.append("⚠️ Rizikós kombó (4+ tipp)")
        lines.append("📈 Várható esély: ~20-35%")
    
    lines.append("")
    lines.append("💡 *Felelős fogadás!*")
    lines.append("Csak annyit tégy, amennyit megengedhetsz!")
    
    return "\n".join(lines)


def format_combo_summary(safe_combo: Optional[List[Dict]], risky_combo: Optional[List[Dict]]) -> str:
    """
    Short summary for both combos
    
    Returns:
        2-3 line summary
    """
    
    lines = ["🎰 *MAI KOMBÓ SZELVÉNYEK:*", ""]
    
    if safe_combo:
        odds = calculate_combo_odds(safe_combo)
        lines.append(f"✅ SAFE: 3 tipp @ {odds:.2f} odds")
    
    if risky_combo:
        odds = calculate_combo_odds(risky_combo)
        lines.append(f"⚠️ RISKY: {len(risky_combo)} tipp @ {odds:.2f} odds")
    
    if not safe_combo and not risky_combo:
        lines.append("_(Ma nincs ajánlott kombó)_")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test with sample picks
    sample_picks = [
        {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "tip": "Hazai győzelem",
            "confidence": 4.5,
            "risk_level": "safe",
            "odds_estimate": 1.65,
            "league_name": "Premier League"
        },
        {
            "home_team": "Bayern",
            "away_team": "Dortmund",
            "tip": "Hazai győzelem",
            "confidence": 4.0,
            "risk_level": "közepes",
            "odds_estimate": 1.80,
            "league_name": "Bundesliga"
        },
        {
            "home_team": "Liverpool",
            "away_team": "Everton",
            "tip": "Hazai győzelem",
            "confidence": 4.2,
            "risk_level": "safe",
            "odds_estimate": 1.55,
            "league_name": "Premier League"
        },
        {
            "home_team": "Real Madrid",
            "away_team": "Atletico",
            "tip": "Hazai győzelem",
            "confidence": 3.8,
            "risk_level": "moderate",
            "odds_estimate": 2.10,
            "league_name": "La Liga"
        },
    ]
    
    combos = build_combos(sample_picks)
    
    print("SAFE COMBO:")
    print(format_combo_for_telegram(combos['safe'], "SAFE", 1000))
    
    print("\n" + "="*60 + "\n")
    
    print("RISKY COMBO:")
    print(format_combo_for_telegram(combos['risky'], "RISKY", 1000))
