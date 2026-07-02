# Render.com Setup - Lépésről Lépésre

## 🎯 Mi ez?
**Render.com** = ingyen 24/7 felhő → futtatja a Reddit alert-et automatikusan, minden nap 15:00-kor.

**Előnyök:**
- ✅ Teljesen INGYEN
- ✅ 24/7 fut (nem kell laptop)
- ✅ GitHub integráció
- ✅ 5 perc setup

---

## 📋 LÉPÉSEK (5 perc)

### 1. Account létrehozása

1. Menj: **https://render.com**
2. Kattints: **"Get Started"** vagy **"Sign Up"**
3. Válaszd: **"Sign up with GitHub"**
4. GitHub authorize → **"Authorize Render"**
5. Kész! Bejelentkezve vagy ✅

---

### 2. Cron Job létrehozása

1. Dashboard → **"New +"** gomb (jobb felső sarok)
2. Válaszd: **"Cron Job"**
3. **Connect Repository:**
   - Kattints: **"Connect account"** (ha kell)
   - Keresd: **"Tippmix"** repo
   - Kattints: **"Connect"**

---

### 3. Beállítások

**Name:** `tippmix-daily-reddit-alert`

**Region:** `Frankfurt (EU Central)` (vagy bármi EU)

**Branch:** `main`

**Build Command:**
```bash
pip install -r requirements.txt
```

**Command (Start Command):**
```bash
python scripts/combined_tipster_alert.py
```

**Schedule (Cron Expression):**
```
0 14 * * *
```
_(Minden nap 14:00 UTC = 15:00 CET)_

---

### 4. Environment Variables (FONTOS!)

Kattints: **"Add Environment Variable"**

**Változó 1:**
- Key: `TELEGRAM_BOT_TOKEN`
- Value: `<your_telegram_bot_token>`

**Változó 2:**
- Key: `TELEGRAM_VIP_CHAT_ID`  
- Value: `-1003341312269`

Kattints: **"Add"** mindkettőnél ✅

---

### 5. Deploy!

1. Scroll le
2. Kattints: **"Create Cron Job"**
3. Várj 1-2 percet (build process)
4. ✅ Kész!

---

## ✅ ELLENŐRZÉS

**Render Dashboard:**
- Látod: `tippmix-daily-reddit-alert` job
- Status: "Live" (zöld)
- Next run: Tomorrow 14:00 UTC

**Manual test:**
- Kattints a job-ra
- **"Trigger Deploy"** gomb → Azonnali futtatás
- Logs → Látod a Reddit scraping-et
- **1-2 perc múlva:** Telegram VIP-be érkezik alert! 📱

---

## 🔧 TROUBLESHOOTING

**Build failed?**
- Ellenőrizd: van `requirements.txt` a repo-ban
- Szükséges package-ek: `requests`, `beautifulsoup4`, `lxml`

**Script error?**
- Logs → nézd meg a hibaüzenetet
- Reddit 403? → Render IP is blokkolva lehet (ritka)

**Telegram error?**
- Environment variables jók?
- Bot admin a channel-ben?

---

## 🎊 SIKER!

Ha minden OK:
- ✅ Holnap 15:00-kor automatikusan fut
- ✅ Reddit scraping → TOP PICKS
- ✅ Telegram VIP alert
- ✅ 24/7, laptop-tól függetlenül!

**INGYEN, MINDÖRÖKRE!** 🚀
