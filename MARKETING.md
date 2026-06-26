# 📢 Marketing Format Telegram Üzenetek

## Áttekintés

A bot támogatja a **marketing-optimalizált** üzenet formátumot inline gombokkal, ami professzionális és felhasználóbarát élményt nyújt.

## Aktiválás

`.env` fájlban:

```bash
TIPPMIX_USE_MARKETING_FORMAT=1
```

## Funkciók

### ✅ VIP Üzenetek

**Formátum:**
```
👑⚽️ SZELVÉNYKIRÁLY VIP
📅 2026.03.19

📊 Teljesítmény: 68% találat | ROI: +12.5%

━━━━━━━━━━━━━━━━━━━━
🏆 MAI KIEMELT TIPPEK

1. Arsenal vs Liverpool
   🎯 Tipp: Hazai győzelem
   📊 Odds: 2.10 | 🟢 | ⭐⭐⭐⭐
   🏆 Premier League | ⏰ 15:00

...

━━━━━━━━━━━━━━━━━━━━
🎫 AJÁNLOTT KOMBÓK

KOMBÓ #1 (6 meccs)
💰 Odds: 12.45x
💵 1000 Ft tét → 12,450 Ft kifizetés (+11,450 Ft)
📌 Meccsek: #1, #2, #3, #4, #5, #6

...

━━━━━━━━━━━━━━━━━━━━
💡 Fontos:
• Felelősségteljesen fogadj!
• Csak olyan pénzt használj, amit megengedhetsz magadnak!

🎁 7 nap INGYEN próba → utána 3.990 Ft/hó
```

**Inline gombok:**
- 📊 Statisztikák (dashboard link)
- ⚽ Tippmix PRO (betting site link)
- 💎 VIP Előfizetés (CTA)

---

### ✅ FREE Üzenetek

**Formátum:**
```
⚽️ SZELVÉNYKIRÁLY - Napi Tippek
📅 2026.03.19

━━━━━━━━━━━━━━━━━━━━
🆓 INGYENES TIPPEK

1. Manchester City vs Chelsea
   🎯 Hazai győzelem
   📊 Odds: 1.75

...

━━━━━━━━━━━━━━━━━━━━
💎 Több tipp kell?

🎯 VIP tagjaink naponta 6-12 kiemelt tippet kapnak
📊 Élő statisztikák + ROI tracking
🏆 Profi elemzések sérülésekkel, formával

🎁 7 nap INGYEN kipróbálás!
```

**Inline gombok:**
- 💎 VIP előfizetés (7 nap ingyen) (top row CTA)
- 📊 Statisztikák
- ⚽ Tippmix PRO

---

### ✅ Alert Üzenetek

**Amikor:** Erős tipp azonnal (magas confidence + low risk + jó odds)

**Formátum:**
```
🚨 ERŐS TIPP ÉSZLELVE!

⚽️ Real Madrid vs Barcelona
🏆 La Liga | ⏰ 20:00

🎯 Tipp: Hazai győzelem
📊 Odds: 1.95
⭐ Bizalom: 4.8/5

💡 Miért?
Real Madrid otthon erős forma, Barcelona 3 kulcsjátékos hiányzik

━━━━━━━━━━━━━━━━━━━━
⏰ GYORS FOGADÁS AJÁNLOTT!
Odds változhat, ne késs!
```

**Inline gombok:**
- ⚡ Fogadás most (Tippmix PRO) (direct betting link)
- 📊 Részletek

---

## Konfiguráció

### Inline Gombok

`.env`:

```bash
# VIP gomb megjelenítése
TIPPMIX_SHOW_VIP_BUTTON=1

# VIP landing page URL
TIPPMIX_VIP_URL=https://tippmix.vercel.app/vip

# Dashboard URL
TIPPMIX_DASHBOARD_URL=https://tippmix.vercel.app

# Fogadóiroda kiválasztása (gomb link)
TIPPMIX_BETTING_SITE=tippmix  # tippmix, bet365, unibet
```

### Betting Site Opciók

- `tippmix` → https://www.tippmixpro.hu
- `bet365` → https://www.bet365.com
- `unibet` → https://www.unibet.hu

---

## API (Programmatic Use)

### VIP Üzenet Generálás

```python
from bot.telegram_marketing import format_marketing_vip

tips = [...]  # list of tip dicts
combos = [...]  # list of combo dicts
stats = {"win_rate": 68.0, "roi": 12.5}

message_text, inline_buttons = format_marketing_vip(
    tips=tips,
    combos=combos,
    date_str="2026.03.19.",
    stats=stats
)

# Send with python-telegram-bot
await context.bot.send_message(
    chat_id=chat_id,
    text=message_text,
    parse_mode="Markdown",
    reply_markup=InlineKeyboardMarkup(inline_buttons)
)
```

### FREE Üzenet Generálás

```python
from bot.telegram_marketing import format_marketing_free

tips = [...]  # list of tip dicts
combos = [...]  # optional combo dicts

message_text, inline_buttons = format_marketing_free(
    tips=tips,
    combos=combos,
    date_str="2026.03.19."
)
```

### Alert Üzenet

```python
from bot.telegram_marketing import format_alert_message

tip = {...}  # single tip dict

message_text, inline_buttons = format_alert_message(
    tip=tip,
    reason="Real Madrid otthon erős forma, Barcelona sérültek"
)
```

---

## Előnyök a Sima Formátumhoz Képest

| Funkció | Sima | Marketing |
|---------|------|-----------|
| Inline gombok | ❌ | ✅ |
| Direct betting link | ❌ | ✅ |
| VIP CTA | ❌ | ✅ |
| Teljesítmény stats | ❌ | ✅ |
| Emoji-optimalizált | ❌ | ✅ |
| Clean design | ❌ | ✅ |
| One-tap subscribe | ❌ | ✅ |

---

## Backward Compatibility

Ha kikapcsolod (`TIPPMIX_USE_MARKETING_FORMAT=0`), az eredeti formátum marad aktív. Nincs breaking change.

---

## Tesztelés

Lokális teszt (dry-run):

```bash
cd Tippmix
python -m bot.main
```

Check `public_bets_day.json` és `vip_bets_day.json` → ezek tartalmazzák a tip adatokat.

---

## Példa Screenshot

*(Később hozzáadható)*

---

**Készítette:** 2026-03-19
**Verzió:** 1.0.0
