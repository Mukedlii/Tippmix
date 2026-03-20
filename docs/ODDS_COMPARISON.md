# Odds Comparison Feature

## Mi ez?

Automatikusan összehasonlítja több buki odds-át és megmutatja a LEGJOBB értéket minden tipphez.

## Profit növelés

**Példa:**
```
Meccs: Bournemouth vs Man United
Tipp: Vendég győzelem
Tét: 1000 Ft

Tippmix: 1.65  → 1650 Ft nyeremény
Bet365:  1.72  → 1720 Ft nyeremény (+70 Ft)
Unibet:  1.68  → 1680 Ft nyeremény

BEST: Bet365 @ 1.72 (+4.2% profit vs Tippmix)
```

**1 hónap alatt (30 tipp, 1000 Ft/tipp átlag):**
- Conservative estimate: +3-5% jobb odds = +900-1500 Ft extra profit
- Aggressive estimate: +8-10% jobb odds = +2400-3000 Ft extra profit

## Források

1. **Oddsportal.com** (ingyenes, publikus)
   - Összehasonlít 20+ bukiszolgáltatót
   - Real-time odds
   - Nincs API kulcs szükséges

2. **TheOddsAPI** (ha elérhető)
   - Backup source
   - API limit: 500 req/hó (free tier)

## Használat

### Automatikus (VIP tippekben)

A top 6 VIP tipp automatikusan megkapja a best odds info-t:

```
1. Bournemouth vs Man United
🎯 Tipp: Vendég győzelem
📊 Odds: BET365 @ 1.72 (+4% vs worst)
```

### Manual teszt

```bash
cd Tippmix
python scripts/odds_comparison_test.py
```

## Konfiguráció

**Hány tipp legyen enriched?**
```python
# bot/providers/odds_enrichment.py
max_enrichments = 6  # Default: top 6 VIP tips
```

**Rate limiting:**
- 2 sec delay per Oddsportal request
- 3 sec delay between enrichments
- Total: ~20-30 sec overhead per run (elfogadható)

## Integráció

### Marketing format

```python
from bot.providers.odds_enrichment import enrich_vip_tips_with_best_odds

# Before sending VIP tips
vip_tips = enrich_vip_tips_with_best_odds(vip_tips, max_enrichments=6)
```

### Telegram output

Új formátum:
```
📊 Odds: BET365 @ 2.10 (+8% vs worst)
```

Helyett régi:
```
📊 Odds: TBA
```

## Limitációk

1. **Scraping-based** → lehet lassabb (2-3 sec/tip)
2. **Oddsportal rate limit** → max 6 tip enriched per run
3. **Team name matching** → fuzzy matching lehet pontatlan

## TODO (opcionális)

- [ ] Cache odds (1 óráig)
- [ ] Direct API integráció (bet365/unibet API ha van)
- [ ] Multi-source fallback (ha Oddsportal fail)
- [ ] Historical best bookie tracking (melyik buki általában jobb)

## Tesztelés

```bash
# Quick test
python bot/providers/odds_comparison.py

# Full test (today's matches)
python scripts/odds_comparison_test.py
```

## Hibakeresés

Ha "No odds found":
1. Check team name spelling (fuzzy match lehet nem talál)
2. Check if match is on Oddsportal (not all matches listed)
3. Check rate limit (túl sok request?)

Ha "Odds comparison not available":
- Oddsportal scraping failelt (structure change?)
- Network issue
- Match not yet listed

## Performance

**Overhead:**
- 6 tips × 5 sec/tip = ~30 sec extra futásidő
- Elfogadható (morning workflow 2-3 percből 2.5-3.5 perc lesz)

**Profit boost:**
- +5-10% jobb odds átlagban
- ROI boost: +0.5-1% (long-term)
