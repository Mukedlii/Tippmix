#!/usr/bin/env python3
import os
os.environ["ODDS_API_KEY"] = "<your_odds_api_key>"

from bot.providers.theoddsapi import fetch_odds_for_sport_key, match_event_to_fixture

events = fetch_odds_for_sport_key('soccer_germany_bundesliga')

for ev in events:
    if match_event_to_fixture(ev, 'RB Leipzig', 'TSG Hoffenheim'):
        print(f"MATCH FOUND: {ev.get('home_team')} vs {ev.get('away_team')}")
        print(f"Bookmakers: {len(ev.get('bookmakers', []))}")
        
        line_options = {}
        
        for bm in ev.get('bookmakers', []):
            bm_name = bm.get('key')
            
            for mkt in bm.get('markets', []):
                mkt_key = mkt.get('key')
                
                if mkt_key == 'totals':
                    print(f"\n  Bookmaker '{bm_name}' has totals market:")
                    print(f"    Outcomes: {len(mkt.get('outcomes', []))}")
                    
                    for out in mkt.get('outcomes', []):
                        print(f"      - {out.get('name')} @ point {out.get('point')} = {out.get('price')}")
                        
                        point = out.get('point')
                        if point:
                            if point not in line_options:
                                line_options[point] = {}
                            
                            name = out.get('name', '').lower()
                            price = out.get('price')
                            
                            if 'over' in name:
                                line_options[point]['over'] = max(line_options[point].get('over', 0), price)
                            elif 'under' in name:
                                line_options[point]['under'] = max(line_options[point].get('under', 0), price)
        
        print(f"\n  Collected lines: {sorted(line_options.keys())}")
        print(f"  Line 2.5 available: {2.5 in line_options}")
        print(f"  Closest to 2.5: {min(line_options.keys(), key=lambda x: abs(x-2.5)) if line_options else 'None'}")
        
        break
