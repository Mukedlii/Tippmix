#!/usr/bin/env python3
"""
Injury integration for Poisson engine

Adjusts lambda (goal expectation) based on team injuries.
"""

from typing import Dict, Optional
from bot.providers.injury_tracker import get_team_injuries, assess_injury_impact


_INJURY_CACHE = {}  # Simple in-memory cache


def get_injury_adjusted_lambda(
    team_name: str,
    base_lambda: float,
    is_attacking: bool = True
) -> float:
    """
    Adjust goal lambda based on injuries
    
    Args:
        team_name: Team name
        base_lambda: Base expected goals (from Poisson)
        is_attacking: True for offense lambda, False for defense
    
    Returns:
        Adjusted lambda
    """
    
    # Check cache (avoid repeated scraping)
    if team_name in _INJURY_CACHE:
        injury_data = _INJURY_CACHE[team_name]
    else:
        injury_data = get_team_injuries(team_name)
        if injury_data:
            _INJURY_CACHE[team_name] = injury_data
    
    if not injury_data or not injury_data.get("injuries"):
        return base_lambda  # No adjustment
    
    impact = assess_injury_impact(injury_data['injuries'])
    
    if is_attacking:
        # Attacking lambda: reduce if attack injuries
        penalty = impact['attack_penalty']
        # Max 30% reduction
        adjusted = base_lambda * (1.0 - (penalty * 0.3))
    else:
        # Defensive lambda: INCREASE if defense injuries (more goals conceded)
        penalty = impact['defense_penalty']
        # Max 30% increase in goals conceded
        adjusted = base_lambda * (1.0 + (penalty * 0.3))
    
    return max(0.05, adjusted)  # Floor at 0.05


def format_injury_context(home_team: str, away_team: str) -> Optional[str]:
    """
    Generate injury context text for match
    
    Returns:
        Formatted string or None if no significant injuries
    """
    
    home_data = _INJURY_CACHE.get(home_team) or get_team_injuries(home_team)
    away_data = _INJURY_CACHE.get(away_team) or get_team_injuries(away_team)
    
    lines = []
    
    if home_data and home_data.get("injuries"):
        impact = assess_injury_impact(home_data['injuries'])
        if impact['overall_severity'] in ['moderate', 'severe']:
            count = len(home_data['injuries'])
            lines.append(f"{home_team}: {count} injuries ({impact['overall_severity']})")
    
    if away_data and away_data.get("injuries"):
        impact = assess_injury_impact(away_data['injuries'])
        if impact['overall_severity'] in ['moderate', 'severe']:
            count = len(away_data['injuries'])
            lines.append(f"{away_team}: {count} injuries ({impact['overall_severity']})")
    
    return "\n".join(lines) if lines else None
