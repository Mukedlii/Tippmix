import json

d = json.load(open('vip_bets_evening.json'))

print(f'Total bets: {len(d)}\n')
print('First 6 with odds_estimate:')

for i, b in enumerate(d[:6]):
    tip = b.get('tip', '')[:40]
    odds_est = b.get('odds_estimate')
    market = b.get('market')
    selection = b.get('selection', '')[:30]
    
    print(f"{i+1}. {tip:40s} market={str(market):5s} odds_estimate={odds_est}")
