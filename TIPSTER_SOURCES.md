# Tipster & Football Info Sources

## 🟢 IMPLEMENTED

### Reddit
- ✅ **r/SoccerBetting** (`bot/providers/reddit_tipsters.py`)
- Status: Daily Picks Thread scraper
- Issue: Thread finding needs fix
- Workflow: `.github/workflows/reddit_consensus.yml` (9:00 daily)

---

## 🟡 EASY TO ADD (10-15 min each)

### Reddit (more subs)
1. **r/SoccerPredictions**
   - Similar to r/SoccerBetting
   - More structured tips
   - Just add subreddit to existing scraper

2. **r/sportsbetting**
   - General betting sub
   - Filter for soccer posts

### Twitter/X FREE API
- **Free tier:** 1,500 tweets/month (read-only)
- **Setup:** https://developer.twitter.com/en/portal/dashboard
- **Accounts to follow:**
  - @FootySuperTips (230K followers)
  - @BettingExpert (150K)
  - @Statsbet (analytics)
  - @FreeSuperTips
  - @bettingexpertEN

**Implementation:**
```python
# pip install tweepy
import tweepy

client = tweepy.Client(bearer_token="YOUR_TOKEN")
tweets = client.get_users_tweets(
    id="FootySuperTips_ID",
    max_results=10
)
```

### BettingExpert.com
- **Free public tips** (no API, scraping needed)
- URL: `https://www.bettingexpert.com/tips/football`
- Structure: HTML tables (easy to parse)
- Data: Match, Tip, Odds, Tipster rating

### Oddsportal.com
- **Public tips section**
- URL: `https://www.oddsportal.com/tips/football/`
- Scraping needed (BeautifulSoup)

---

## 🔴 HARDER (require more work)

### Paid Tipster Sites
- **Tipstrr.com** - aggregator (API available, paid)
- **BlogaBet.com** - community tips (scraping)

### Telegram Channels
- Many free tipster channels
- Scraping possible via Telethon/Pyrogram
- Examples: "Free Football Tips", "Soccer Predictions"

---

## 📊 RECOMMENDED NEXT STEPS

**Priority 1: Twitter/X (BEST ROI)**
1. Get free API key (5 min signup)
2. Add `bot/providers/twitter_tipsters.py` (15 min)
3. Follow top 5-10 accounts
4. Parse daily tips → consensus

**Priority 2: Fix Reddit**
1. Improve thread finding (flexible title matching)
2. Add r/SoccerPredictions
3. Increase coverage

**Priority 3: BettingExpert scraper**
1. Simple HTML scraping
2. High-quality tips (verified tipsters)
3. 20-30 min implementation

---

## 🚀 QUICK START: Twitter

**Step 1:** Get API key
- Go to: https://developer.twitter.com/en/portal/dashboard
- Create app → get Bearer Token
- Free tier: 1,500 tweets/month

**Step 2:** Add to GitHub Secrets
```bash
TWITTER_BEARER_TOKEN=<your_token>
```

**Step 3:** Run scraper
```python
# Already prepared: bot/providers/twitter_tipsters.py (if we create it)
```

---

**VÁLASZT VÁROK:**
- Twitter API-t akarod? (5 perc setup + 15 perc kód)
- Reddit fix-et? (10 perc)
- BettingExpert scraper? (20 perc)
- Mindhárom? (45 perc összesen)
