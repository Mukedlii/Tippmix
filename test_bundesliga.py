import os
os.environ['ODDS_API_KEY'] = 'acf78bce7a7976c2bc4d028528d4cb2f'

from bot.providers import theoddsapi

events = theoddsapi.fetch_odds_for_sport_key('soccer_germany_bundesliga')
print(f'Bundesliga events: {len(events)}')

for e in events[:10]:
    print(f'  {e["home_team"]} vs {e["away_team"]}')
