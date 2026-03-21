# Tipster Aggregator + AI System - Teljes Design

**Cél:** Többforrásból gyűjtött tippek → AI elemzés → TOP 6 "biztos" meccs + kombináló

**Időzítés:**
- 01:00-03:00 - Adatgyűjtés
- 14:00 - AI elemzés
- 15:00 - Telegram alert

---

## 📊 ADATBÁZIS SÉMA

### 1. `tipsters` tábla
```sql
CREATE TABLE tipsters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- "ScubaSlavver", "ProTips", etc.
    source TEXT NOT NULL,            -- "reddit", "telegram", "poisson"
    source_identifier TEXT,          -- "@FreeSuperTips", "r/SoccerBetting"
    
    -- Statisztikák (auto-update)
    total_tips INTEGER DEFAULT 0,
    total_settled INTEGER DEFAULT 0,
    total_won INTEGER DEFAULT 0,
    win_rate REAL,                   -- Calculated: won / settled
    total_roi REAL,                  -- Sum of all ROI
    avg_roi REAL,                    -- total_roi / settled
    
    -- Quality metrics
    is_verified BOOLEAN DEFAULT 0,   -- Manual verification
    min_sample_reached BOOLEAN,      -- >= 20 tips
    is_qualified BOOLEAN,            -- win_rate >= 55% AND avg_roi >= 5%
    
    -- Timestamps
    first_tip_at TEXT,
    last_tip_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tipsters_qualified ON tipsters(is_qualified);
CREATE INDEX idx_tipsters_source ON tipsters(source);
```

### 2. `tipster_tips` tábla
```sql
CREATE TABLE tipster_tips (
    id INTEGER PRIMARY KEY,
    tipster_id INTEGER NOT NULL,
    
    -- Match info
    match_date TEXT NOT NULL,        -- YYYY-MM-DD
    match_time TEXT,                 -- HH:MM
    league TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    
    -- Tip details
    selection TEXT NOT NULL,         -- "away_win", "over_2_5", "btts_yes", etc.
    selection_display TEXT,          -- Human readable: "Vendég győzelem"
    odds REAL,
    confidence INTEGER,              -- 1-5 stars (if provided)
    
    -- Source metadata
    raw_text TEXT,                   -- Original post/comment
    source_url TEXT,                 -- Reddit permalink, Telegram message link
    
    -- Result tracking
    is_settled BOOLEAN DEFAULT 0,
    won BOOLEAN,
    actual_score TEXT,               -- "2-1"
    settled_at TEXT,
    roi REAL,                        -- (odds - 1) if won, else -1
    
    -- Timestamps
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (tipster_id) REFERENCES tipsters(id)
);

CREATE INDEX idx_tipster_tips_match ON tipster_tips(match_date, home_team, away_team);
CREATE INDEX idx_tipster_tips_tipster ON tipster_tips(tipster_id);
CREATE INDEX idx_tipster_tips_settled ON tipster_tips(is_settled);
```

### 3. `ai_consensus` tábla (AI döntések)
```sql
CREATE TABLE ai_consensus (
    id INTEGER PRIMARY KEY,
    analysis_date TEXT NOT NULL,     -- YYYY-MM-DD
    analysis_run_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Match
    match_date TEXT NOT NULL,
    match_time TEXT,
    league TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    
    -- Consensus
    selection TEXT NOT NULL,
    selection_display TEXT,
    recommended_odds REAL,
    
    -- AI metrics
    tipster_count INTEGER,           -- How many tipsters agree
    qualified_tipster_count INTEGER, -- How many GOOD tipsters
    avg_tipster_roi REAL,            -- Average ROI of agreeing tipsters
    avg_tipster_winrate REAL,
    consensus_strength REAL,         -- 0-100 (how unanimous)
    
    -- AI reasoning
    ai_confidence REAL,              -- 0-100 (AI's own assessment)
    ai_reasoning TEXT,               -- Why AI picked this (GPT/Claude explanation)
    
    -- Historical lookback
    similar_cases_count INTEGER,     -- How many similar tips in history
    similar_cases_winrate REAL,      -- Win rate of similar tips
    
    -- Ranking
    is_top6 BOOLEAN DEFAULT 0,       -- Selected for VIP alert
    rank_position INTEGER,           -- 1-6 if top6
    
    -- Result
    is_settled BOOLEAN DEFAULT 0,
    won BOOLEAN,
    actual_score TEXT,
    settled_at TEXT,
    roi REAL
);

CREATE INDEX idx_ai_consensus_date ON ai_consensus(analysis_date);
CREATE INDEX idx_ai_consensus_top6 ON ai_consensus(is_top6);
```

### 4. `combo_bets` tábla (Kombinálók)
```sql
CREATE TABLE combo_bets (
    id INTEGER PRIMARY KEY,
    analysis_date TEXT NOT NULL,
    
    -- Combo details
    combo_size INTEGER NOT NULL,     -- 6, 5, 4, 3
    combo_type TEXT,                 -- "top6_all", "safe_5", "risky_4"
    
    -- Matches (JSON array of ai_consensus IDs)
    matches_json TEXT NOT NULL,      -- [1, 2, 3, 4, 5, 6]
    
    -- Odds
    total_odds REAL NOT NULL,
    
    -- AI assessment
    ai_confidence REAL,
    ai_reasoning TEXT,
    
    -- Result
    is_settled BOOLEAN DEFAULT 0,
    won BOOLEAN,
    settled_count INTEGER DEFAULT 0,
    won_count INTEGER DEFAULT 0,
    roi REAL,
    settled_at TEXT,
    
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🤖 AI ELEMZÉS FOLYAMAT

### Script: `scripts/ai_consensus_analysis.py`

```python
#!/usr/bin/env python3
"""
AI Consensus Analysis - Napi futtatás 14:00-kor

1. Összegyűjti az összes mai tippet (tipster_tips)
2. Csoportosít meccs szerint
3. AI elemzi (Claude/GPT4):
   - Melyik meccsre hány JŐJJ tipster tippel?
   - Milyen a consensus erőssége?
   - Történelmi adatok (hasonló esetek)
   - Odds value assessment
4. Kiválaszt TOP 6 "legbiztosabbnak tűnő" meccset
5. Generál kombináló ajánlásokat
"""

import anthropic  # or openai
from bot.storage import get_tippmix_db

def analyze_daily_consensus():
    """
    Main AI analysis function
    """
    db = get_tippmix_db()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Get all tips for today
    tips = db.execute("""
        SELECT 
            tt.home_team, tt.away_team, tt.league,
            tt.selection, tt.odds, tt.confidence,
            t.name as tipster_name,
            t.win_rate, t.avg_roi, t.is_qualified
        FROM tipster_tips tt
        JOIN tipsters t ON tt.tipster_id = t.id
        WHERE tt.match_date = ?
        AND tt.is_settled = 0
    """, (today,)).fetchall()
    
    # 2. Group by match
    by_match = {}
    for tip in tips:
        key = f"{tip['home_team']} vs {tip['away_team']}"
        if key not in by_match:
            by_match[key] = {
                'home': tip['home_team'],
                'away': tip['away_team'],
                'league': tip['league'],
                'tips': []
            }
        by_match[key]['tips'].append(tip)
    
    # 3. For each match, analyze consensus
    consensus_results = []
    
    for match_key, match_data in by_match.items():
        tips = match_data['tips']
        
        # Filter only QUALIFIED tipsters
        qualified_tips = [t for t in tips if t['is_qualified']]
        
        if len(qualified_tips) < 2:
            continue  # Need at least 2 good tipsters
        
        # Group by selection
        by_selection = {}
        for tip in qualified_tips:
            sel = tip['selection']
            if sel not in by_selection:
                by_selection[sel] = []
            by_selection[sel].append(tip)
        
        # Find dominant selection
        dominant_sel = max(by_selection.items(), key=lambda x: len(x[1]))
        selection = dominant_sel[0]
        agreeing_tipsters = dominant_sel[1]
        
        if len(agreeing_tipsters) < 2:
            continue  # Need at least 2 agreeing
        
        # Calculate metrics
        avg_roi = sum(t['avg_roi'] for t in agreeing_tipsters) / len(agreeing_tipsters)
        avg_winrate = sum(t['win_rate'] for t in agreeing_tipsters) / len(agreeing_tipsters)
        consensus_strength = len(agreeing_tipsters) / len(qualified_tips) * 100
        
        # Get similar historical cases
        similar = get_similar_historical_cases(
            home=match_data['home'],
            away=match_data['away'],
            selection=selection,
            db=db
        )
        
        # AI prompt
        prompt = f"""
Analyze this betting consensus:

Match: {match_data['home']} vs {match_data['away']}
League: {match_data['league']}
Selection: {selection}

Agreeing tipsters: {len(agreeing_tipsters)}
- Average ROI: {avg_roi:.1f}%
- Average Win Rate: {avg_winrate:.1f}%
- Consensus strength: {consensus_strength:.0f}%

Historical similar cases: {len(similar)} tips
- Win rate: {similar['winrate']:.1f}% if similar else 'N/A'

Odds range: {min(t['odds'] for t in agreeing_tipsters if t['odds'])} - {max(t['odds'] for t in agreeing_tipsters if t['odds'])}

Rate this tip's confidence (0-100) and explain why it's good or risky.
Consider: tipster quality, consensus strength, historical data, odds value.

Response format:
{{
  "confidence": 85,
  "reasoning": "Strong consensus from 4 qualified tipsters...",
  "recommended": true
}}
"""
        
        # Call AI (Claude/GPT4)
        ai_response = call_ai_api(prompt)
        
        consensus_results.append({
            'match': match_data,
            'selection': selection,
            'agreeing_tipsters': agreeing_tipsters,
            'avg_roi': avg_roi,
            'avg_winrate': avg_winrate,
            'consensus_strength': consensus_strength,
            'ai_confidence': ai_response['confidence'],
            'ai_reasoning': ai_response['reasoning'],
            'recommended': ai_response['recommended']
        })
    
    # 4. Rank by AI confidence
    consensus_results.sort(key=lambda x: x['ai_confidence'], reverse=True)
    
    # 5. Select TOP 6
    top6 = consensus_results[:6]
    
    # 6. Save to DB
    for i, result in enumerate(top6, 1):
        db.execute("""
            INSERT INTO ai_consensus (
                analysis_date, match_date, home_team, away_team,
                selection, tipster_count, qualified_tipster_count,
                avg_tipster_roi, avg_tipster_winrate, consensus_strength,
                ai_confidence, ai_reasoning,
                is_top6, rank_position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            today, today, result['match']['home'], result['match']['away'],
            result['selection'], len(result['match']['tips']),
            len(result['agreeing_tipsters']),
            result['avg_roi'], result['avg_winrate'], result['consensus_strength'],
            result['ai_confidence'], result['ai_reasoning'], i
        ))
    
    # 7. Generate combo bets
    generate_combo_bets(top6, db, today)
    
    db.commit()
    
    return top6
```

---

## 📱 TELEGRAM ALERT FORMAT

```markdown
🎯 AI TIPSTER CONSENSUS
📅 2026.03.21. | 🤖 Claude Sonnet 4

━━━━━━━━━━━━━━━━━━━━

🏆 TOP 6 BIZTOSNAK TŰNŐ MECCS

1️⃣ Darmstadt vs Schalke 04
🎯 Vendég győzelem @ 4.20
👥 4 qualified tipster egyezik
📊 Átlag ROI: +14.2% | Win: 68%
🤖 AI confidence: 87%
💡 "Strong away form, home weakness..."

2️⃣ Nice vs Paris Saint-Germain
🎯 Vendég győzelem @ 1.85
👥 5 qualified tipster egyezik
📊 Átlag ROI: +18.1% | Win: 74%
🤖 AI confidence: 92%
💡 "PSG dominant, Nice injuries..."

... (4 more)

━━━━━━━━━━━━━━━━━━━━

💰 KOMBINÁLÓK

🎁 6-os (Top 6 all)
Total odds: 127.5
AI confidence: 68%
Expected value: +24%

🔥 5-ös (Top 5, skip lowest)
Total odds: 42.3
AI confidence: 78%
Expected value: +18%

✅ 4-es (Legszilárdabb 4)
Total odds: 18.7
AI confidence: 85%
Expected value: +12%

━━━━━━━━━━━━━━━━━━━━

📊 Forrás breakdown:
Reddit: 14 tips (5 qualified)
Telegram: 8 tips (3 qualified)
Poisson: 12 tips (all qualified)

🎁 VIP Előfizetés: 3.990 Ft/hó
```

---

## ⏰ WORKFLOW SETUP

### 1. Data Collection (01:00-03:00)

**New cron:** `data_collection.yml`
```yaml
schedule:
  - cron: "0 0 * * *"  # 01:00 CET

steps:
  - name: Scrape Reddit
    run: python scripts/scrape_reddit_daily.py
  
  - name: Scrape Telegram  
    run: python scripts/scrape_telegram_daily.py
  
  - name: Run Poisson
    run: python scripts/generate_poisson_tips.py
```

### 2. AI Analysis (14:00)

**New cron:** `ai_consensus.yml`
```yaml
schedule:
  - cron: "0 13 * * *"  # 14:00 CET

steps:
  - name: AI Consensus Analysis
    run: python scripts/ai_consensus_analysis.py
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

### 3. VIP Alert (15:00)

**Modified:** `reddit_consensus.yml` → `tipster_consensus_alert.yml`
```yaml
schedule:
  - cron: "0 14 * * *"  # 15:00 CET

steps:
  - name: Send AI Consensus Alert
    run: python scripts/send_ai_consensus_alert.py
```

---

## 💰 KÖLTSÉGBECSLÉS

**AI API:**
- Claude Sonnet 4: $3 / 1M input tokens
- Daily analysis: ~50k tokens
- **Cost:** ~$0.15/day = $4.5/month

**Alternatíva:**
- Claude Haiku: $0.25 / 1M tokens → $0.0125/day = $0.38/month! ✅

**Ajánlás:** Haiku az elemzésre (elég okos, olcsó!)

---

## ✅ IMPLEMENTATION STEPS

**Phase 1: Data Collection (1 nap)**
1. ✅ Reddit scraper már megvan!
2. ✅ Telegram scraper már megvan!
3. ⚠️ DB schema létrehozása (tipsters, tipster_tips)
4. ⚠️ Scraper-ek módosítása → DB-be mentés

**Phase 2: Tipster Tracking (1 nap)**
1. ⚠️ Result checker script (match results API)
2. ⚠️ Auto-update tipster stats (win rate, ROI)
3. ⚠️ Qualify/disqualify logic

**Phase 3: AI Analysis (1-2 nap)**
1. ⚠️ ai_consensus_analysis.py script
2. ⚠️ Claude/GPT integration
3. ⚠️ Combo bet generation logic

**Phase 4: Alert System (0.5 nap)**
1. ⚠️ New Telegram format (AI consensus)
2. ⚠️ Combo recommendations display

**Phase 5: Workflows (0.5 nap)**
1. ⚠️ 3 cron jobs (scrape, analyze, alert)
2. ⚠️ GitHub Actions setup

**Total:** 4-5 nap fejlesztés

---

## 🎯 SUCCESS METRICS

**After 1 month:**
- Tipster database: 50+ tracked tipsters
- Historical tips: 500+ tracked
- Qualified tipsters: 10-15
- AI top6 win rate: Target >= 60%
- Combo 6-os win rate: Target >= 5% (ritka, de nagy odds)
- Combo 4-es win rate: Target >= 20%

---

**Status:** DESIGN READY, waiting for approval to implement

**Next:** User confirms design → Start Phase 1 (DB + scraper integration)
