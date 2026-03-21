# Phase 4 - AI Consensus Analysis

## ✅ Script Created

### `ai_consensus.py` - AI elemzés + TOP 6 kiválasztás

**Funkció:**
1. **Consensus számítás** - Match+selection szerint csoportosítás
2. **Qualified tipster detection** - Ki a "jó" tipster?
3. **Strength scoring** - 0-100 skála (qualified count + win rate + ROI)
4. **OpenAI GPT-4o-mini analysis** - AI elemzi a konszenzust
5. **TOP 6 selection** - Legbiztosabb 6 pick kiválasztása
6. **DB mentés** - `ai_consensus` táblába

---

## 🧮 Consensus Logic

### Strength Calculation (0-100)
```
Base score:
  +30 per qualified tipster (max 90 for 3+)
  +10 if qualified win rate > 60%
  +10 if qualified ROI > 10%
  -20 if NO qualified tipsters

Min 0, Max 100
```

### Filter Criteria
**Minimum:**
- 2+ tipsters VAGY
- 1+ qualified tipster

**Ideal:**
- 3+ qualified tipsters
- Win rate >= 60%
- ROI >= 5%
- Consensus strength >= 70/100

---

## 🤖 AI Analysis (OpenAI GPT-4o-mini)

### Prompt Structure
```
Task: Select TOP 6 most reliable picks

Criteria:
1. Qualified Tipster Agreement (multiple qualified tipsters)
2. Historical Performance (avg win rate, ROI)
3. Consensus Strength (how many agree)
4. Odds Value (1.50-2.50 sweet spot)
5. Risk Balance (mix safe + value picks)

Data: [Match-by-match analysis]

Response: JSON with TOP 6 + confidence + reasoning
```

### AI Output
```json
{
  "top_6": [
    {
      "rank": 1,
      "match": "Liverpool vs Arsenal",
      "selection": "Over 2.5",
      "ai_confidence": 0.85,
      "reasoning": "3 qualified tipsters (68% win rate, +15% ROI). Odds 1.85 = good value."
    },
    ...
  ]
}
```

### Fallback (no API key)
**Simple consensus ranking:**
- Sort by: qualified_count DESC, consensus_strength DESC
- Pick top 6

---

## 📊 Database Schema

### `ai_consensus` table
**Fields added by script:**
- `analysis_date` - When analysis ran
- `match_date`, `home_team`, `away_team`, `selection`
- `tipster_count`, `qualified_tipster_count`
- `avg_tipster_roi`, `avg_tipster_winrate`
- `consensus_strength` (0-1)
- `ai_confidence` (0-1)
- `ai_reasoning` (text)
- `is_top6` (1 for TOP 6)
- `rank_position` (1-6)

**Usage:**
```sql
-- Get today's TOP 6
SELECT * FROM ai_consensus
WHERE analysis_date = '2026-03-21'
AND is_top6 = 1
ORDER BY rank_position ASC
```

---

## 🚀 Usage

### Manual Run
```bash
# Set API key (optional, uses fallback if not set)
export OPENAI_API_KEY="sk-proj-..."

# Run analysis
python scripts/ai_consensus.py
```

### Expected Output
```
🤖 AI CONSENSUS ANALYSIS

📊 Found 25 unique match+selection combinations
✅ 12 picks meet minimum criteria

🤖 Running AI analysis...

🎯 TOP 6 AI CONSENSUS PICKS:

1. Liverpool vs Arsenal
   Selection: Over 2.5
   Tipsters: 5 (3 qualified)
   Consensus: 85/100
   AI Confidence: 82%
   Reasoning: Strong qualified agreement...

2. ...

✅ Saved 6 TOP 6 picks to database
```

---

## ⚙️ Automation

### Daily Workflow (Updated)
```
01:00 - aggregate_tipsters.py  (scrape Reddit/Telegram/NS)
03:00 - fetch_results.py       (completed matches)
03:15 - settle_tips.py         (auto-settle, update stats)
14:00 - ai_consensus.py        (AI analysis, TOP 6 selection)
15:00 - send_top6_alert.py     (Phase 5 - Telegram alert)
```

### Task Scheduler (Phase 5)
```powershell
schtasks /create /tn "Tippmix AI Analysis" ^
  /tr "python C:\Users\Muki\clawd\Tippmix\scripts\ai_consensus.py" ^
  /sc daily /st 14:00
```

---

## 🧪 Testing

### Bootstrap Period (2-4 weeks)
**Why?**
- Need qualified tipsters (20+ settled tips per tipster)
- Need historical data (win rates, ROI)
- Need consensus patterns

**Timeline:**
```
Week 1: Data collection (no qualified tipsters yet)
Week 2: First qualified tipsters emerge (20+ tips settled)
Week 3: Meaningful consensus (multiple qualified per match)
Week 4: AI analysis ready (reliable TOP 6 selection)
```

### Current Status (2026-03-21)
```
✅ Script working
⚠️  0 qualified tipsters (no settled tips yet)
⚠️  11 tips (1 per match - Reddit parser needs fix)

Expected tomorrow:
  → Tips settle (yesterday's matches)
  → Tipster stats update
  → Qualified detection starts
```

---

## 💰 Cost Estimate

### OpenAI GPT-4o-mini Pricing
- **Input:** $0.150 / 1M tokens
- **Output:** $0.600 / 1M tokens

### Daily Usage
- **Prompt:** ~2,000 tokens (25 matches × 80 tokens)
- **Response:** ~500 tokens (TOP 6 × 80 tokens)
- **Total:** ~2,500 tokens/day

### Monthly Cost
```
Daily: 2,500 tokens × $0.375 / 1M = $0.00094
Monthly: $0.00094 × 30 = $0.028 (~$0.03/month)

Annual: ~$0.35/year
```

**Compare:**
- Claude Haiku: ~$0.40/month
- GPT-4o-mini: ~$0.03/month ✅ **14x CHEAPER!**

---

## 🐛 Known Issues

### 1. Reddit Parser (Phase 2 fix needed)
**Problem:** Bad team names → no consensus
- "9.02 (+802) vs ..." ❌
- Only 1 tipster per match

**Solution:**
- Fix Reddit parser (better team extraction)
- Validate match format
- Skip invalid matches

### 2. Bootstrap Period
**Problem:** No qualified tipsters yet (need 20+ settled tips)

**Solution:**
- Wait 2-4 weeks for data accumulation
- Use fallback ranking meanwhile (consensus only)

### 3. Odds Extraction
**Problem:** Some tips missing odds

**Solution:**
- Better Reddit parsing (odds regex)
- Fetch current odds from TheOddsAPI (if missing)

---

## 📈 Future Improvements

### Phase 4.1 - Enhanced AI
- Historical pattern analysis (similar matches)
- League-specific insights
- Team form analysis
- Injury/lineup impact

### Phase 4.2 - Multiple AI Models
- Compare GPT-4o-mini vs Claude Haiku
- Ensemble predictions (combine models)
- Confidence calibration

### Phase 4.3 - Live Odds Integration
- Fetch current bookmaker odds
- Value betting detection (overpriced picks)
- Arbitrage opportunities

---

## 🎯 Phase 4 Status

### ✅ DONE (09:24)
1. ✅ `ai_consensus.py` script (12 KB)
2. ✅ Consensus strength calculation
3. ✅ OpenAI GPT-4o-mini integration
4. ✅ TOP 6 selection logic
5. ✅ Fallback mode (no API key)
6. ✅ DB saving (`ai_consensus` table)
7. ✅ Documentation (this file)

### ⏳ TODO
1. ⚠️ Wait for bootstrap data (2-4 weeks)
2. ⚠️ Fix Reddit parser (Phase 2)
3. ⚠️ Add OpenAI API key (TOOLS.md)
4. ⚠️ Test with real qualified tipsters
5. ⚠️ Optimize prompt (better AI decisions)

---

## 🚀 Next: Phase 5 (Alert System)

**When Phase 4 works:**
- TOP 6 picks selected
- AI confidence calculated
- Saved to DB

**Then:**
- Format Telegram message
- Generate combo bets (6-way, 5-way, 4-way)
- Send to VIP channel (15:00 daily)
- Show tipster stats + AI reasoning

---

**Created:** 2026-03-21 09:24  
**Status:** ✅ Phase 4 script ready, waiting for bootstrap data (2-4 weeks)
