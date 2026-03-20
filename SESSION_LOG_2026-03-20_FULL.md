# Session Log: 2026-03-20 (TELJES) - Team & League Matching

**Időtartam:** 09:10 - 10:45 (1.5 óra)

---

## PROBLÉMA (09:00)

User jelentés:
- Historical data betöltve: 5,330 meccs
- Tippek gyengék: Under 2.5, ⭐⭐ confidence
- Fallback mode: historical data NEM használódik

**Okozat:**
```
football-data.org:  Arsenal = team_id 57
SofaScore:          Arsenal = team_id 42
→ Nincs match → fallback mode
```

---

## MEGOLDÁS 1: Team Name Matching (09:10-10:10) ✅

### Implementáció:

**Új fájl:** `bot/storage/team_matcher.py`
- Fuzzy name matching (SequenceMatcher)
- Normalizálás: FC/AFC/TSG eltávolítás, lowercase, számok eltávolítása
- Cache: 146 historical team betöltve
- Similarity threshold: 85%

**Módosítva:** `bot/storage/poisson_stats.py`
- `team_goal_rates(team_id=None, team_name=None)` - mostmár accept team_name
- Fallback logic: try team_id → name matching → historical ID

**Módosítva:** `bot/poisson_engine.py`
- Átadja team_name-et a team_goal_rates()-nek

### Bug Fix (10:30):

**Probléma:** "Manchester United" → "manchester" (de "Manchester United FC" → "manchester united")

**Ok:** "United" suffix eltávolítódik ha csak 2 szó van

**Fix:**
- TEAM_SUFFIXES: removed "united" (core name, not suffix)
- Added "TSG" to TEAM_PREFIXES (TSG 1899 Hoffenheim → Hoffenheim)
- Remove numbers from team names (1899, etc.)

### Teszt Eredmények:

**Előtte (run_id=16):**
```
Manchester United:  n_away=0 ❌
Hoffenheim:        n_away=0 ❌
used_team_defaults: True
data_quality: low
```

**Utána (run_id=17):**
```
Manchester United:  n_away=112 ✅
Hoffenheim:        n_away=94 ✅
used_team_defaults: False
data_quality: still low (league missing)
```

---

## PROBLÉMA 2: League ID Missing (10:40) ⚠️

### Felfedezés:

**Historical data:**
```sql
league_id = 2021 (Premier League, from football-data.org)
```

**Current matches (LiveScore scraper):**
```python
league_id = None ❌
league_name = "England Premier League" (csak név)
```

### Következmény:

- `league_goal_baseline(league_id=None)` → returns None
- Fallback: used_league_defaults = True
- Data quality: **still LOW**

### Root Cause:

free_scraper (LiveScore, FlashScore) csak league_name-et ad, nincs league_id

---

## MEGOLDÁS 2: League Name Matching (NEM IMPLEMENTÁLVA) ⏳

### Szükséges lépések:

1. **bot/storage/league_matcher.py** (új)
   - Similar to team_matcher
   - Map league_name → league_id from historical data
   - Examples:
     ```
     "England Premier League" → 2021
     "Germany Bundesliga" → 2002
     "Spain La Liga" → 2014
     ```

2. **bot/storage/poisson_stats.py** (módosítás)
   - `league_goal_baseline(league_id=None, league_name=None)`
   - Fallback: try league_id → name matching

3. **bot/poisson_engine.py** (módosítás)
   - Átadja league_name-et
   - `league_goal_baseline(league_id, league_name=m.get("league_name"))`

### Várható hatás:

**Előtte:**
```
n_league=0, used_league_defaults=True
data_quality: low
```

**Utána:**
```
n_league=1061 (PL), used_league_defaults=False
data_quality: HIGH ⭐⭐⭐⭐
```

---

## STÁTUSZ

### ✅ KÉSZ:
- Team name matching (146 teams)
- Team normalization (FC/TSG/numbers removal)
- Fallback: team_id → team_name
- Test scripts (4db)

### ⚠️ HIÁNYZIK:
- League name matching (6 ligák prioritás)
- League normalization
- Fallback: league_id → league_name

### 📊 JELENLEGI EREDMÉNY:

**Run 17 (team matching fix után):**
- 10 VIP + 3 FREE tip
- Team data: ✅ (home=106-112, away=94-112)
- League data: ❌ (n_league=0)
- used_team_defaults: False ✅
- used_league_defaults: True ❌
- data_quality: **low** (league hiányzik)

### 🎯 CÉLÁLLAPOT (league matching után):

- Team data: ✅ (100+ matches/team)
- League data: ✅ (1000+ matches/league)
- used_team_defaults: False ✅
- used_league_defaults: False ✅
- data_quality: **HIGH** ⭐⭐⭐⭐

---

## GIT COMMITS

```
b554d01 - Add team name matching for historical data
8d50576 - Improve team matching: fallback to name-based lookup if team_id fails
e0930d2 - Add test scripts for team matching + Poisson engine validation
adaf806 - Add session log: team name matching fix documentation
f007e54 - FIX team_matcher: improve normalization (keep 'united', remove numbers, add TSG)
```

---

## KÖVETKEZŐ LÉPÉS (10-15 perc munka)

**Implementáld a league_matcher.py-t:**

1. Copy team_matcher.py → league_matcher.py
2. LEAGUE_PREFIXES/SUFFIXES (remove "England", "Germany", etc.)
3. Load historical league_id + league_name from DB
4. Update poisson_stats.py: accept league_name param
5. Update poisson_engine.py: pass league_name
6. Test: "England Premier League" → league_id 2021

**Várható javulás:**
- low → HIGH data quality
- ⭐⭐ → ⭐⭐⭐⭐ confidence
- 40-50% → 65-75% win rate (estimated)

---

**Mentve:** 2026-03-20 10:45
