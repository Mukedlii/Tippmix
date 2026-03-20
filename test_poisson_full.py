#!/usr/bin/env python3
"""
Full Poisson test with detailed calculation output
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.storage.poisson_stats import team_goal_rates, league_goal_baseline

def test_calculation():
    """Test Poisson calculation step by step"""
    
    print("\n" + "="*60)
    print("POISSON CALCULATION TEST")
    print("="*60)
    
    # Match: Arsenal vs Liverpool
    home_team = "Arsenal"
    away_team = "Liverpool"
    league_id = 2021
    
    # Get data
    print("\n[1] FETCH HISTORICAL DATA")
    home_data = team_goal_rates(team_id=42, team_name=home_team)
    away_data = team_goal_rates(team_id=43, team_name=away_team)
    league_data = league_goal_baseline(league_id=league_id)
    
    print(f"\nHome ({home_team}): {home_data}")
    print(f"Away ({away_team}): {away_data}")
    print(f"League (PL): {league_data}")
    
    # Calculate lambdas
    print("\n[2] CALCULATE EXPECTED GOALS (LAMBDA)")
    
    lg_home_for = league_data['home_for']
    lg_away_for = league_data['away_for']
    
    h_att = home_data['gf'] / lg_home_for
    h_def = home_data['ga'] / lg_away_for
    a_att = away_data['gf'] / lg_away_for
    a_def = away_data['ga'] / lg_home_for
    
    home_adv = 0.10
    
    lam_home = max(0.05, lg_home_for * h_att * a_def + home_adv)
    lam_away = max(0.05, lg_away_for * a_att * h_def)
    
    print(f"\nAttack/Defense factors:")
    print(f"  Home attack: {h_att:.3f}")
    print(f"  Home defense: {h_def:.3f}")
    print(f"  Away attack: {a_att:.3f}")
    print(f"  Away defense: {a_def:.3f}")
    
    print(f"\nExpected goals:")
    print(f"  Arsenal (home): {lam_home:.2f}")
    print(f"  Liverpool (away): {lam_away:.2f}")
    print(f"  Total: {lam_home + lam_away:.2f}")
    
    # Calculate probabilities
    print("\n[3] CALCULATE PROBABILITIES")
    import math
    
    def poisson_pmf(k, lam):
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    
    # 1X2
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    
    for i in range(9):
        for j in range(9):
            prob = poisson_pmf(i, lam_home) * poisson_pmf(j, lam_away)
            if i > j:
                p_home += prob
            elif i == j:
                p_draw += prob
            else:
                p_away += prob
    
    print(f"\n1X2 Probabilities:")
    print(f"  Home win: {p_home:.1%}")
    print(f"  Draw: {p_draw:.1%}")
    print(f"  Away win: {p_away:.1%}")
    
    # Over/Under 2.5
    lam_total = lam_home + lam_away
    def poisson_cdf(k, lam):
        return sum(poisson_pmf(i, lam) for i in range(k+1))
    
    p_under25 = poisson_cdf(2, lam_total)
    p_over25 = 1.0 - p_under25
    
    print(f"\nOver/Under 2.5:")
    print(f"  Under 2.5: {p_under25:.1%}")
    print(f"  Over 2.5: {p_over25:.1%}")
    
    # BTTS
    p_h0 = math.exp(-lam_home)
    p_a0 = math.exp(-lam_away)
    p_btts_yes = 1.0 - p_h0 - p_a0 + (p_h0 * p_a0)
    p_btts_no = 1.0 - p_btts_yes
    
    print(f"\nBoth Teams To Score:")
    print(f"  BTTS Yes: {p_btts_yes:.1%}")
    print(f"  BTTS No: {p_btts_no:.1%}")
    
    # Check thresholds
    print("\n[4] CHECK THRESHOLDS (default: 58% safe, 54% risk)")
    safe_thr = 0.58
    risk_thr = 0.54
    
    picks = []
    
    # 1X2
    best_1x2 = max([("Home win", p_home), ("Draw", p_draw), ("Away win", p_away)], key=lambda x: x[1])
    if best_1x2[1] >= safe_thr:
        picks.append(f"SAFE: {best_1x2[0]} ({best_1x2[1]:.1%})")
    elif best_1x2[1] >= risk_thr:
        picks.append(f"RISK: {best_1x2[0]} ({best_1x2[1]:.1%})")
    
    # O/U 2.5
    if p_over25 >= safe_thr:
        picks.append(f"SAFE: Over 2.5 ({p_over25:.1%})")
    elif p_over25 >= risk_thr:
        picks.append(f"RISK: Over 2.5 ({p_over25:.1%})")
    elif p_under25 >= safe_thr:
        picks.append(f"SAFE: Under 2.5 ({p_under25:.1%})")
    elif p_under25 >= risk_thr:
        picks.append(f"RISK: Under 2.5 ({p_under25:.1%})")
    
    # BTTS
    if p_btts_yes >= safe_thr:
        picks.append(f"SAFE: BTTS Yes ({p_btts_yes:.1%})")
    elif p_btts_yes >= risk_thr:
        picks.append(f"RISK: BTTS Yes ({p_btts_yes:.1%})")
    elif p_btts_no >= safe_thr:
        picks.append(f"SAFE: BTTS No ({p_btts_no:.1%})")
    elif p_btts_no >= risk_thr:
        picks.append(f"RISK: BTTS No ({p_btts_no:.1%})")
    
    print("\n[5] GENERATED PICKS:")
    if picks:
        for pick in picks:
            print(f"  {pick}")
    else:
        print("  (none - probabilities below threshold)")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    test_calculation()
