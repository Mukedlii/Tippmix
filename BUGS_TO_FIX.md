# Bugs to Fix - Morning Workflow

**Reported:** 2026-03-21 06:38 (User feedback)

---

## 🔴 CRITICAL BUGS:

### 1. **Odds: TBA** (4+ napja húzódik)
**Problem:** TheOddsAPI timing issue
```
📊 Odds: TBA | 🟢 | ⭐⭐⭐
```
**Fix:** Enable Poisson engine odds estimation
**File:** `bot/poisson_engine.py` - already has odds calculation!
**Action:** Ensure `odds_estimate` is populated and displayed

---

### 2. **DUPLICATE MATCHES** (Same match 3x!)
**Problem:** Same match appears 3 times with different selections
```
1. Darmstadt vs Schalke 04 (Vendég DNB) - 4.20
2. Darmstadt vs Schalke 04 (Vendég Win) - 4.20  
3. Darmstadt vs Schalke 04 (Over 2.5) - TBA
```
**Fix:** De-duplicate by match, select BEST tip per match
**File:** `bot/main.py` or marketing formatter
**Action:** Group by match → pick highest confidence/value selection

---

### 3. **SAME ODDS FOR DIFFERENT SELECTIONS**
**Problem:** DNB and Win have SAME odds (4.20)
```
Vendég (DNB): 4.20  ← WRONG!
Vendég Win: 4.20    ← Should be different!
```
**Reality:** DNB always LOWER odds than straight win
**Fix:** Poisson engine calculate odds per selection type
**File:** `bot/poisson_engine.py` - `get_draw_no_bet_odds()` etc.

---

### 4. **ROI: -100% BEFORE MATCHES**
**Problem:** Shows ROI/Win% when matches haven't played yet!
```
📊 Teljesítmény: 0% találat | ROI: -100.0%
```
**Timeline:** Alert sent 06:00, matches at 19:30/20:05
**Fix:** Hide ROI/Win% until results available
**File:** `bot/telegram_marketing.py` - conditional stats display
**Action:** 
```python
if has_results_for_today():
    show_stats()
else:
    lines.append("📊 Eredmények később")
```

---

### 5. **REDUNDANT SELECTIONS**
**Problem:** Why 3 selections for same match?
- Vendég (DNB)
- Vendég győzelem
- Over 2.5

**User expectation:** 1 match = 1 BEST tip
**Fix:** Poisson engine ranks selections by expected value
**Action:** Keep only TOP 1 selection per match

---

## 🎯 ROOT CAUSE:

**Workflow:** `tippmix_morning_full.yml`
- Poisson engine generates MULTIPLE picks per match
- No de-duplication logic
- No "best pick" selection
- Marketing formatter displays ALL picks

**Files involved:**
1. `bot/main.py` - main bot logic
2. `bot/poisson_engine.py` - tip generation
3. `bot/telegram_marketing.py` - message formatting
4. `.github/workflows/tippmix_morning_full.yml` - env vars

---

## ✅ FIXES NEEDED:

### Priority 1 (Critical):
1. ✅ De-duplicate matches (1 tip/match)
2. ✅ Hide ROI before results
3. ✅ Fix odds calculation (different per selection)

### Priority 2 (Nice to have):
4. ✅ Enable Poisson odds estimation (no TBA)
5. ✅ Smart "best pick" selection per match

---

## 🔧 IMPLEMENTATION PLAN:

**Step 1:** Add de-duplication logic
```python
# bot/main.py or telegram_marketing.py
def deduplicate_picks(tips):
    by_match = {}
    for tip in tips:
        match_key = f"{tip['home_team']} vs {tip['away_team']}"
        if match_key not in by_match:
            by_match[match_key] = tip
        else:
            # Keep higher confidence
            if tip['confidence'] > by_match[match_key]['confidence']:
                by_match[match_key] = tip
    return list(by_match.values())
```

**Step 2:** Conditional ROI display
```python
# bot/telegram_marketing.py
if stats and has_completed_matches_today():
    lines.append(f"📊 Teljesítmény: {win_rate:.0f}% találat | ROI: {roi:+.1f}%")
else:
    lines.append("📊 Eredmények később")
```

**Step 3:** Fix odds per selection type
```python
# bot/poisson_engine.py
if selection == "draw_no_bet_away":
    odds = calculate_dnb_odds(p_away, p_draw)
elif selection == "away_win":
    odds = 1.0 / p_away if p_away > 0 else None
elif selection == "over_2_5":
    odds = 1.0 / p_over_25 if p_over_25 > 0 else None
```

---

## 🧪 TESTING:

**When fixed, test:**
1. Run morning workflow manually
2. Check Telegram VIP message:
   - ✅ Each match appears ONCE
   - ✅ Different odds for DNB vs Win
   - ✅ No ROI shown (or "Eredmények később")
   - ✅ No TBA odds (Poisson estimation)

**User validation:** @Mukedlii confirms fix works

---

**Status:** DOCUMENTED, waiting for user to be home for testing

**ETA:** Fix when user available (later today/tomorrow)
