# Tipster Sources Setup Guide

## ✅ IMPLEMENTED (A + C)

### A. Reddit Scraper ✅
**Status:** WORKING  
**Sources:** r/SoccerBetting, r/SoccerPredictions, r/sportsbetting  
**Requirements:** None (public JSON API)

**Files:**
- `bot/providers/reddit_tipsters.py`
- `scripts/reddit_consensus_alert.py` (old, single source)
- `scripts/combined_tipster_alert.py` (new, multi-source)

**Workflow:** `.github/workflows/reddit_consensus.yml` (runs daily 9:00 UTC)

---

### C. Telegram Channels ✅
**Status:** CODE READY (needs API setup)  
**Sources:** Free tipster channels (@FreeSuperTips, etc.)  
**Requirements:** Telegram API credentials

**Setup (5 minutes):**

1. **Get API credentials:**
   - Go to: https://my.telegram.org/apps
   - Login with your Telegram account
   - Create a new application
   - Copy API ID and API Hash

2. **Add to GitHub Secrets:**
   ```bash
   TELEGRAM_API_ID=12345678
   TELEGRAM_API_HASH=abc123def456...
   ```

3. **Test locally (optional):**
   ```bash
   pip install telethon
   export TELEGRAM_API_ID=12345678
   export TELEGRAM_API_HASH=abc123...
   python bot/providers/telegram_tipsters.py
   ```

4. **Run combined scraper:**
   ```bash
   python scripts/combined_tipster_alert.py
   ```

**Files:**
- `bot/providers/telegram_tipsters.py`

---

## 🔴 PENDING (B)

### B. BettingExpert.com
**Status:** BLOCKED (JS-heavy site, needs Selenium)  
**Alternative:** Oddsportal.com tips (might be easier)

**Why blocked:**
- BettingExpert uses React/Next.js (client-side rendering)
- 153 script tags → dynamic content
- Simple requests+BeautifulSoup doesn't work

**Solutions:**
1. **Selenium/Playwright** (30-40 min setup, slower scraping)
2. **Try Oddsportal instead** (might be simpler HTML)
3. **Skip for now** (Reddit + Telegram sufficient)

---

## 🚀 CURRENT WORKFLOW

**Daily tipster consensus:**
1. ✅ Reddit scraping (3 subs) - 9:00 UTC
2. 🟡 Telegram scraping (if API set up) - same time
3. 📊 Combined consensus alert → VIP channel

**Trigger manually:**
```bash
python scripts/combined_tipster_alert.py
```

---

## 📝 NEXT STEPS

**To enable Telegram:**
1. Get API credentials (5 min): https://my.telegram.org/apps
2. Add to GitHub Secrets:
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
3. Workflow will auto-enable Telegram scraping

**To add BettingExpert (later):**
1. Install Selenium: `pip install selenium webdriver-manager`
2. Update `bot/providers/bettingexpert_scraper.py` with Selenium
3. Add to `scripts/combined_tipster_alert.py`

---

## 🔧 TESTING

**Test Reddit only:**
```bash
python bot/providers/reddit_tipsters.py
```

**Test Telegram only:**
```bash
export TELEGRAM_API_ID=...
export TELEGRAM_API_HASH=...
python bot/providers/telegram_tipsters.py
```

**Test combined:**
```bash
python scripts/combined_tipster_alert.py
```

---

**STATUS:**
- ✅ A (Reddit): DONE
- 🔴 B (BettingExpert): Needs Selenium (deferred)
- ✅ C (Telegram): DONE (needs API setup to activate)
