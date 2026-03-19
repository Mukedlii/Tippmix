# Tippmix Project - Teljes Állapot

**Utolsó frissítés:** 2026-03-19 15:54

---

## 📦 Projekt Információk

### GitHub Repository
- **URL:** https://github.com/Mukedlii/Tippmix
- **Branch:** main
- **Latest commit:** 97d8cf4
- **Visibility:** Private

### Vercel Deployment
- **URL:** https://tippmix.vercel.app/
- **Dashboard:** https://tippmix.vercel.app/
- **VIP Landing:** https://tippmix.vercel.app/vip
- **Auto-deploy:** GitHub push → Vercel rebuild

### Local Paths
- **Repo:** `C:\Users\Muki\clawd\Tippmix`
- **DB:** `C:\Users\Muki\clawd\Tippmix\data\tippmix.db`

---

## 🔑 API Kulcsok & Secrets

### GitHub Secrets (beállítva)
```bash
# Telegram
TELEGRAM_BOT_TOKEN: (BotFather-től, beállítva a user által)
TELEGRAM_PUBLIC_CHAT_ID: (FREE csatorna ID)
TELEGRAM_VIP_CHAT_ID: (VIP csatorna ID)

# TheOddsAPI (FONTOS!)
ODDS_API_KEY: acf78bce7a7976c2bc4d028528d4cb2f
- Free tier: 500 requests/month
- Érvényes: 30 nap (2026-03-19-től)
- Lejárat: ~2026-04-18

# OpenAI (opcionális - jelenleg nincs kredit)
OPENAI_API_KEY: (insufficient quota - $0.51 balance)
- Típus: sk-admin-... vagy sk-proj-...
- Státusz: 429 insufficient_quota
- Megoldás: $5-10 top up VAGY használd Poisson engine-t
```

### Sport Data Providers
- **Free_scraper:** LiveScore, SofaScore (ingyenes, scraping)
- **TheOddsAPI:** Odds lekéréshez (beállítva)
- **API-Football:** (nincs kulcs)
- **SportMonks:** (nincs kulcs)

---

## ⚙️ Bot Konfiguráció

### Aktív Funkciók
✅ **Poisson Engine** (matematikai/statisztikai, API nélkül)
✅ **Marketing Format** (inline gombok + clean design)
✅ **Multi-Sport** (kosár 🏀, kézi 🤾, jégkorong 🏒)
✅ **TheOddsAPI** integráció (odds fetch)
✅ **Sports News Scraper** (Nemzeti Sport, BBC, Goal.com, Origo, Index, ESPN)
✅ **Injury Scraper** (API-Football, FBref, Transfermarkt, ESPN)
✅ **Weather API** (opcionális, OpenWeatherMap)
✅ **Betting Exchange** (sharp money tracking)
✅ **ROI Tracking** (SQLite DB)
✅ **Dashboard** (Next.js, Vercel)

### GitHub Actions Workflows
**Morning (06:00 UTC = 07:00 CET):**
- `tippmix_morning_full.yml`
- Full-day picks (DAY slot)
- TheOddsAPI: 20 req/run
- Marketing format: ON
- Multi-sport: ON

**Evening (19:00 UTC = 20:00 CET):**
- `tippmix_evening.yml`
- Evening picks (EVENING slot)
- TheOddsAPI: 20 req/run
- Marketing format: ON

**Nightly Recap (00:00 UTC):**
- `tippmix_nightly_recap.yml`
- Daily summary

**Weekly Report (Monday 09:00 UTC):**
- `weekly-report.yml`
- 7-day performance summary

---

## 📊 Költségek & Limitek

| Service | Free Tier | Jelenlegi Használat | Költség |
|---------|-----------|---------------------|---------|
| GitHub Actions | 2000 perc/hó | ~90 perc/hó (3x/nap) | $0 |
| TheOddsAPI | 500 req/hó | ~40 req/nap = ~1200/hó ⚠️ | FREE majd $0.01/req |
| Vercel | Unlimited deploys | Auto-deploy | $0 |
| OpenAI | - | N/A (no credit) | - |
| Poisson Engine | Unlimited | Aktív | $0 |
| **ÖSSZESEN** | | | **$0/hó** ✅ |

**⚠️ TheOddsAPI figyelem:**
- 500 req/hó = ~16 req/nap
- Jelenleg: 40 req/nap beállítva → **túllépés!**
- **Fix:** Csökkentsd 10-12 req/run-ra (vagy vásárolj creditet)

---

## 🗂️ Fájlstruktúra (Fontos)

```
Tippmix/
├── bot/
│   ├── main.py                     # Fő bot logika
│   ├── openai_logic.py             # AI tip generation (jelenleg nem használt)
│   ├── poisson_engine.py           # Matematikai engine (AKTÍV)
│   ├── telegram_marketing.py       # Marketing format üzenetek
│   ├── providers/
│   │   ├── multi_sport.py          # Kosár/kézi/jégkorong
│   │   ├── sports_news.py          # Hírek (8 forrás)
│   │   ├── injuries.py             # Sérülések (4 forrás)
│   │   ├── odds_scraper.py         # Odds (4 forrás)
│   │   └── web_context.py          # xG, forma, H2H
│   ├── storage/
│   │   ├── sqlite_store.py         # DB műveletek
│   │   └── poisson_stats.py        # Történelmi adatok
│   └── roi_tracker.py              # ROI kalkuláció
├── dashboard/                       # Next.js dashboard
│   ├── app/
│   ├── components/
│   └── public/data/                # Generált JSON-ok
├── scripts/
│   └── generate_dashboard_data.py  # Dashboard JSON generátor
├── data/
│   └── tippmix.db                  # SQLite adatbázis
├── .github/workflows/              # CI/CD
│   ├── tippmix_morning_full.yml
│   ├── tippmix_evening.yml
│   └── weekly-report.yml
├── .env.example                    # Config példa
├── requirements.txt                # Python deps
├── MARKETING.md                    # Marketing docs
├── MULTI_SPORT.md                  # Multi-sport docs
├── GITHUB_SETUP.md                 # Setup útmutató
└── ADD_SECRET_MOBIL.md             # Mobil útmutató
```

---

## 🚀 Következő Lépések (Priorizált)

### 1. TheOddsAPI Limit Fix (SÜRGŐS)
**Probléma:** 40 req/nap > 16 req/nap (500/hó limit)

**Fix:**
```yaml
# .github/workflows/tippmix_morning_full.yml
ODDS_MAX_REQUESTS_PER_RUN: "10"  # volt: 20
```

**Vagy:** Vásárolj kreditet ($10 = 1000 req)

### 2. OpenAI Credit Top-Up (Opcionális)
**Jelenleg:** Poisson engine (matematikai, működik)

**Ha jobb minőséget akarsz:**
1. Top up OpenAI: $5-10
   https://platform.openai.com/settings/organization/billing
2. **VAGY** használj Claude (Anthropic):
   - $5 ingyen kredit
   - https://console.anthropic.com/
   - Sokszor jobb minőség

### 3. Eredmények Tracking (Automatikus)
- Meccsek ma este: 17:45-20:00
- Eredmények automatikusan bekerülnek DB-be
- ROI stats frissül
- Dashboard mutatja teljesítményt

### 4. VIP Landing Page (Marketing)
**Jelenleg:** https://tippmix.vercel.app/vip → 404

**TODO:** Készíts landing page-et:
- 7 nap ingyen trial
- Teljesítmény stats
- Payment link (Stripe/PayPal)

### 5. Monitoring & Alerts
**Setup:**
- GitHub Actions notification Discord/Telegram-ra
- Uptime monitoring (UptimeRobot)
- Error alerting

---

## 🐛 Ismert Problémák & Megoldások

### 1. "Odds: TBA" vagy "n/a"
**OK:** TheOddsAPI nem fut / nincs találat

**Fix:**
- Ellenőrizd: `ODDS_API_KEY` secret beállítva ✅
- Check limit: 500 req/hó
- Sport keys: Europa League, Conference League

### 2. "Tipp:" üres
**OK:** Poisson engine nem tud generálni (nincs team_id/league_id)

**Fix:** Free_scraper → API-based provider (de kell API kulcs)

**Alternatíva:** Fallback az eredeti formátumra (már implementálva)

### 3. "Adatbiztonság: alacsony"
**OK:** Kevés történelmi adat az új ligákhoz

**Megoldás:** Idővel javul (ahogy több meccs eredmény gyűlik)

### 4. Datetime Import Error
**OK:** Dupla import (globális + lokális)

**Fix:** ✅ Javítva (commit 25b1ece)

### 5. GitHub Actions túllépés (TheOddsAPI)
**OK:** 40 req/nap > 16 req/nap limit

**Fix:** Csökkentsd 10 req/run-ra

---

## 📝 Fontos Fájlok (Backup)

### .env.example (Konfiguráció sablon)
```bash
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_PUBLIC_CHAT_ID=
TELEGRAM_VIP_CHAT_ID=

# AI Provider
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
TIPPMIX_USE_ENSEMBLE=0
TIPPMIX_ENGINE=poisson  # poisson or openai

# TheOddsAPI
ODDS_API_KEY=acf78bce7a7976c2bc4d028528d4cb2f
ODDS_MAX_REQUESTS_PER_RUN=20
ODDS_REGIONS=eu
ODDS_SPORT_KEYS=soccer_uefa_europa_league,soccer_uefa_europa_conference_league

# Marketing
TIPPMIX_USE_MARKETING_FORMAT=1
TIPPMIX_DASHBOARD_URL=https://tippmix.vercel.app
TIPPMIX_VIP_URL=https://tippmix.vercel.app/vip
TIPPMIX_BETTING_SITE=tippmix  # tippmix, bet365, unibet

# Multi-sport
TIPPMIX_ENABLE_MULTI_SPORT=1
TIPPMIX_EXTRA_SPORTS=basketball,handball

# Pool
TIPPMIX_MIN_POOL=15
TIPPMIX_MIN_VIP=6
TIPPMIX_MIN_FREE=3
```

---

## 🎯 Success Metrics (Tracking)

**KPI-k nyomon követése:**
- [ ] Hit rate > 60% (VIP)
- [ ] ROI > 10% (long-term)
- [ ] 100+ subscriber (1 hónap)
- [ ] $500/hó revenue (3 hónap)

**Aktuális (2026-03-19):**
- Bets: 26 (17 VIP, 9 FREE)
- Hit rate: 0% (pending results)
- ROI: 0% (pending)
- Subscribers: 0 (még nincs payment)

---

## 🔐 Biztonsági Megjegyzések

1. **GitHub tokens:** SOHA ne commitold a repo-ba
2. **API keys:** Csak GitHub Secrets-ben tárolva
3. **.env:** Gitignore-ban van (local only)
4. **Telegram token:** Revoke ha kompromittálódott (BotFather)
5. **TheOddsAPI key:** 30 nap érvényes → megújítani!

---

## 📚 Dokumentáció Linkek

**Belső docs (repo):**
- `README.md` - Áttekintés
- `MARKETING.md` - Marketing format
- `MULTI_SPORT.md` - Multi-sport támogatás
- `GITHUB_SETUP.md` - Secrets setup
- `ADD_SECRET_MOBIL.md` - Mobil útmutató
- `EXAMPLE_MESSAGE.md` - Üzenet példák

**External docs:**
- TheOddsAPI: https://the-odds-api.com/liveapi/guides/v4/
- GitHub Actions: https://docs.github.com/en/actions
- Vercel: https://vercel.com/docs
- Telegram Bot API: https://core.telegram.org/bots/api

---

## 💬 Support & Community

**Ha elakadsz:**
1. Check `GITHUB_SETUP.md` troubleshooting
2. GitHub Issues: https://github.com/Mukedlii/Tippmix/issues
3. Vercel logs: https://vercel.com/mukedlii/tippmix/logs

---

**Projekt státusz:** ✅ Működőképes (Poisson engine)  
**Következő milestone:** OpenAI credit + ROI tracking eredmények

**Mentve:** 2026-03-19 15:54
