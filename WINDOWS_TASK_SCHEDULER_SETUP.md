# Windows Task Scheduler Setup - Daily Reddit Picks Alert

## Miért kell ez?

GitHub Actions IP-jét **Reddit blokkolta** (HTTP 403) → workflow nem tud scrape-elni.

**Megoldás:** Futtatás a saját gépedről Windows Task Scheduler-rel.

---

## Setup (5 perc)

### 1. Telegram Credentials megszerzése

Ha még nincs meg:

**Bot Token:**
1. Telegram app → @BotFather
2. `/newbot`
3. Név: "Tippmix VIP Bot"
4. Username: `TippmixVIP_bot` (vagy unique)
5. **Copy token:** `123456789:ABC...`

**VIP Chat ID:**
1. VIP Telegram channel-ed (ha nincs: create new private channel)
2. Add bot-ot admin-nak
3. Forward message → @userinfobot
4. Copy "Forwarded from chat" ID: `-1001234567890`

### 2. Batch file módosítása

Edit: `C:\Users\Muki\clawd\Tippmix\run_daily_reddit_alert.bat`

Cseréld le:
```bat
set TELEGRAM_BOT_TOKEN=123456789:ABC...
set TELEGRAM_VIP_CHAT_ID=-1001234567890
```

### 3. Windows Task Scheduler beállítása

**Option A: GUI (egyszerűbb)**

1. Win + R → `taskschd.msc`
2. Create Basic Task
3. Name: "Tippmix Daily Reddit Alert"
4. Trigger: Daily, 15:00 (3 PM)
5. Action: Start a program
6. Program: `C:\Users\Muki\clawd\Tippmix\run_daily_reddit_alert.bat`
7. Finish

**Option B: Command Line**

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\Muki\clawd\Tippmix\run_daily_reddit_alert.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At 3PM
Register-ScheduledTask -TaskName "Tippmix Reddit Alert" -Action $action -Trigger $trigger
```

### 4. Manual teszt

```powershell
cd C:\Users\Muki\clawd\Tippmix

# Set credentials
$env:TELEGRAM_BOT_TOKEN="123456789:ABC..."
$env:TELEGRAM_VIP_CHAT_ID="-1001234567890"

# Run
python send_top_reddit_picks.py
```

Ha működik → Task Scheduler is működni fog!

---

## Működés

**Minden nap 15:00-kor:**
1. Reddit scraping (r/SoccerBetting Daily Picks)
2. Portfolios + Top Picks kiszedése
3. Telegram VIP alert küldése
4. Log: `daily_reddit_log.txt`

**Előny GitHub Actions-höz képest:**
- ✅ Nem blokkolja Reddit
- ✅ Futás garantált (ha a gép BE van kapcsolva)
- ❌ Gép kell online legyen

---

## Troubleshooting

**Script nem fut?**
- Ellenőrizd: Python path (`python --version`)
- Batch file-ban full path: `C:\Python314\python.exe`

**Telegram error?**
- Ellenőrizd credentials (BotFather token, Chat ID)
- Bot admin-e a channel-ben?

**Reddit 403?**
- Lokálisan nem fog előfordulni (csak GitHub Actions-nél)
