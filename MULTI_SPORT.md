# 🏀🤾 Multi-Sport Támogatás

## Áttekintés

A bot automatikusan **kosárlabda** és **kézilabda** meccseket is feldolgoz, ha a foci pool túl kicsi.

## Funkció

**Automatikus bővítés:**
- Ha foci meccsek < 15 (TIPPMIX_MIN_POOL)
- → Kosár (NBA, Euroleague) + kézi (EHF) hozzáadása
- → Garantált minimum pool méret

## Támogatott Sportok

### ✅ Kosárlabda (Basketball)
- **Ligák:** NBA, Euroleague, NBL, NCAA
- **Piacok:** 
  - Moneyline (1X2)
  - Over/Under pontok
  - Spread (handicap)
- **Emoji:** 🏀

### ✅ Kézilabda (Handball)
- **Ligák:** EHF Champions League, válogatott meccsek
- **Piacok:**
  - 1X2
  - Handicap
  - Over/Under gólok
- **Emoji:** 🤾

### 🔜 Jégkorong (Hockey) - opcionális
- **Ligák:** NHL, KHL
- **Emoji:** 🏒

## Aktiválás

`.env`:
```bash
# Engedélyezés (alapból BE van)
TIPPMIX_ENABLE_MULTI_SPORT=1

# Sportok kiválasztása
TIPPMIX_EXTRA_SPORTS=basketball,handball

# Minimum pool méret (ha foci kevesebb → bővítés)
TIPPMIX_MIN_POOL=15
```

## Példa Output

### Telegram Üzenet

```
👑⚽️ SZELVÉNYKIRÁLY VIP
📅 2026.03.19

🏆 MAI KIEMELT TIPPEK

1. ⚽ Arsenal vs Liverpool
   🎯 Hazai győzelem
   📊 Odds: 2.10 | 🟢

2. 🏀 Lakers vs Celtics
   🎯 Lakers +5.5 ponttal
   📊 Odds: 1.85 | 🟢

3. 🤾 Veszprém vs Barcelona
   🎯 Over 55.5 gól
   📊 Odds: 1.75 | 🟡

...
```

### Sport Emoji-k

| Sport | Emoji | Példa |
|-------|-------|-------|
| Foci | ⚽ | ⚽ Arsenal vs Liverpool |
| Kosár | 🏀 | 🏀 Lakers vs Celtics |
| Kézi | 🤾 | 🤾 Veszprém vs Kiel |
| Jégkorong | 🏒 | 🏒 Rangers vs Bruins |

## Adatforrások

### Kosárlabda
- **FlashScore** (scraping, ingyenes)
- **ESPN** (scraping, ingyenes)
- TheOddsAPI (odds)

### Kézilabda
- **FlashScore** (scraping, ingyenes)
- TheOddsAPI (odds)

## API Integráció (Opcionális)

### The Odds API

`.env`:
```bash
ODDS_API_KEY=your_key_here
ODDS_SPORT_KEYS=basketball_nba,basketball_euroleague,handball_ehf
```

**Sport kulcsok:**
- `basketball_nba` - NBA
- `basketball_euroleague` - Euroleague
- `handball_ehf` - EHF Champions League

**Költség:** 500 req/hó ingyen, utána $10/1000 req

### API-Sports (Premium)

Támogatja NBA + EHF-et is:
```bash
SPORTS_API_KEY=your_key_here
```

## Logika

```python
# 1. Foci pool fetch
football_matches = fetch_football_matches(date)  # 8 meccs

# 2. Ellenőrzés
if len(football_matches) < MIN_POOL:  # 8 < 15
    # 3. Bővítés
    basketball_matches = fetch_basketball_matches(date)  # +5
    handball_matches = fetch_handball_matches(date)  # +3
    
    all_matches = football_matches + basketball_matches + handball_matches
    # 4. Eredmény: 16 meccs (8 foci + 5 kosár + 3 kézi)
```

## Konfiguráció Példák

### Csak kosár
```bash
TIPPMIX_EXTRA_SPORTS=basketball
```

### Csak kézi
```bash
TIPPMIX_EXTRA_SPORTS=handball
```

### Mind (kosár + kézi + jégkorong)
```bash
TIPPMIX_EXTRA_SPORTS=basketball,handball,hockey
```

### Multi-sport kikapcsolása
```bash
TIPPMIX_ENABLE_MULTI_SPORT=0
```

## Előnyök

✅ **Több tipp naponta** (akár foci szünetekben is)
✅ **Diverzifikáció** (más sport, más odds dinamika)
✅ **Nagyobb közönség** (kosár/kézi rajongók)
✅ **Stabil pool méret** (mindig min. 15 meccs)
✅ **Ingyenes** (scraping alapú)

## Hátrányok / Limitációk

⚠️ **Scraping instabilitás** (FlashScore blokkolhat)
⚠️ **Kevesebb adat** kosár/kézi-nél (nincs történeti DB)
⚠️ **Odds hiány** (ha nincs TheOddsAPI kulcs)
⚠️ **Más szabályok** (különböző piacok)

## Tesztelés

Lokális teszt:
```bash
cd Tippmix
python -c "from bot.providers.multi_sport import fetch_basketball_matches; print(len(fetch_basketball_matches()))"
```

Teljes bot teszt:
```bash
TIPPMIX_ENABLE_MULTI_SPORT=1 python -m bot.main
```

Check logs:
```
[MultiSport] Foci pool kicsi (8), bővítés: ['basketball', 'handball']
[Basketball] FlashScore: 5 meccs
[Handball] FlashScore: 3 meccs
[MultiSport] Végső pool: 16 meccs (foci: 8, egyéb: 8)
```

---

**Verzió:** 1.0.0
**Készítette:** 2026-03-19
