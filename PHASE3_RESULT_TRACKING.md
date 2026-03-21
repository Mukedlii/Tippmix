# Phase 3 - Result Tracking

## ✅ Scripts Created

### 1. `fetch_results.py` - Eredmények lekérése
**Funkció:**
- TheOddsAPI scores endpoint
- 3 nappal visszamenőleg
- 5 major league (EPL, La Liga, Bundesliga, Serie A, Ligue 1)
- Eredmények mentése `match_results` táblába

**Használat:**
```bash
python scripts/fetch_results.py
```

**Output példa:**
```
✅ Bournemouth 2-2 Manchester United
✅ RB Leipzig 5-0 TSG Hoffenheim
✅ 6 new results saved
```

---

### 2. `settle_tips.py` - Tippek settle-elése
**Funkció:**
- Összekapcsolja `tipster_tips` ↔ `match_results`
- Team matching (fuzzy, normalized)
- Selection evaluation (Home Win, BTTS, Over/Under, etc.)
- Auto-settle tips (won/lost)
- Tipster stats frissítés (win_rate, ROI)

**Használat:**
```bash
python scripts/settle_tips.py
```

**Output példa:**
```
✅ ramuo: Home Win - 2-1 (WON)
❌ ScubaSlavver: Over 2.5 - 1-1 (LOST)
✅ 5 tips settled

📊 UPDATED TIPSTER STATS:
🏆 ramuo: 3/5 (60.0%) ROI: +8.5%
   ScubaSlavver: 1/3 (33.3%) ROI: -15.2%
```

---

## 🔧 Match Logic

### Team Matching
**Normalization:**
- Lowercase
- Strip whitespace
- Remove common words (FC, AFC, United → Utd)
- Fuzzy matching (contains check)

**Példák:**
- "Man United" ↔ "Manchester United" ✅
- "Tottenham" ↔ "Spurs" ✅
- "RB Leipzig" ↔ "Leipzig" ✅

### Selection Evaluation
**Támogatott típusok:**
- ✅ Home Win / Away Win / Draw
- ✅ BTTS (Both Teams To Score) Yes/No
- ✅ Over/Under (2.5, 3.5, etc.)
- ⏳ Asian Handicap (később)
- ⏳ Correct Score (később)

---

## 🤖 Automation

### Daily Workflow
**Időzítés:**
```
01:00 - Aggregate tips (Reddit, Telegram, Nemzeti Sport)
03:00 - Fetch results (completed matches from yesterday)
03:15 - Settle tips (match tips with results)
```

**Windows Task Scheduler:**
```powershell
# Task 1: Aggregate tips
schtasks /create /tn "Tippmix Aggregator" /tr "python C:\Users\Muki\clawd\Tippmix\scripts\aggregate_tipsters.py" /sc daily /st 01:00

# Task 2: Fetch results
schtasks /create /tn "Tippmix Results" /tr "python C:\Users\Muki\clawd\Tippmix\scripts\fetch_results.py" /sc daily /st 03:00

# Task 3: Settle tips
schtasks /create /tn "Tippmix Settler" /tr "python C:\Users\Muki\clawd\Tippmix\scripts\settle_tips.py" /sc daily /st 03:15
```

---

## 📊 Database Schema Updates

### `match_results` table
```sql
CREATE TABLE match_results (
    id INTEGER PRIMARY KEY,
    match_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    sport TEXT,
    source TEXT DEFAULT 'theoddsapi',
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_date, home_team, away_team)
)
```

### Tipster stats auto-update
When `settle_tip()` called:
- ✅ `total_settled` ++
- ✅ `total_won` ++ (if won)
- ✅ `win_rate` recalculated
- ✅ `avg_roi` recalculated
- ✅ `is_qualified` checked (win_rate >= 55%, ROI >= 5%, sample >= 20)

---

## 🧪 Testing

### Manual test (tomorrow morning):
```bash
# 1. Aggregate today's tips
python scripts/aggregate_tipsters.py

# 2. Wait for matches to complete

# 3. Fetch results (next day)
python scripts/fetch_results.py

# 4. Settle tips
python scripts/settle_tips.py

# 5. Check stats
python scripts/view_db_stats.py
```

**Expected output:**
- Tips from today → settled tomorrow
- Tipster stats updated (win_rate, ROI)
- Qualified tipsters detected (🏆)

---

## ⚠️ Known Issues

### 1. Reddit Parser Improvements Needed
**Problem:** Some team names parsed incorrectly
- "9.02 (+802) vs ..." ❌
- "Combined odds vs 8.29" ❌

**Solution (Phase 2 fix later):**
- Better regex for team extraction
- Match pattern validation
- Skip invalid matches

### 2. Date Estimation
**Current logic:**
- Before 12:00 → today
- After 12:00 → tomorrow

**Issue:** Reddit threads are from yesterday, but scraped today morning
**Solution (later):**
- Extract date from Reddit thread title
- Parse relative dates ("Saturday, March 21")

### 3. Incomplete Selection Types
**Missing:**
- Asian Handicap (later)
- Correct Score (later)
- Custom parlays (later)

---

## 🎯 Phase 3 Status

### ✅ DONE
1. ✅ `fetch_results.py` - TheOddsAPI integration
2. ✅ `settle_tips.py` - Auto-settlement logic
3. ✅ `match_results` table created
4. ✅ Team matching (normalized, fuzzy)
5. ✅ Selection evaluation (Win/Draw/BTTS/O-U)
6. ✅ Tipster stats auto-update
7. ✅ Qualified tipster detection

### ⏳ TODO
1. ⚠️ Reddit parser improvements (Phase 2 fix)
2. ⚠️ Date extraction from thread titles
3. ⚠️ More selection types (Asian Handicap, Correct Score)
4. ⚠️ Multiple result sources (fallback if API fails)
5. ⚠️ Better fuzzy matching (Levenshtein distance)

---

## 🚀 Next: Phase 4 (AI Analysis)

**When Phase 3 complete:**
- 2-3 days of data collected
- Tipster stats calculated
- Qualified tipsters identified

**Then:**
- OpenAI GPT-4o-mini analysis
- TOP 6 match selection
- Confidence scoring
- Historical pattern analysis

---

**Created:** 2026-03-21 09:21  
**Status:** ✅ Phase 3 scripts ready, waiting for data accumulation
