# Fly.io Setup - 100% Ingyen, Örökre

## 🎯 Miért Fly.io?

**✅ Garantáltan ingyen:**
- 3 VM ingyen (Shared CPU, 256MB RAM)
- 160 GB/hó forgalom
- **NINCS credit card kell!**
- **NINCS trial - örökre ingyen!**

---

## 📋 SETUP (10 perc)

### 1. Sign Up

1. https://fly.io/app/sign-up
2. **Sign up with GitHub** ✅
3. Authorize Fly.io
4. **NEM kér credit card-ot!** ✅

---

### 2. Install Fly CLI (NEM kötelező, de könnyebb)

**Option A: Windows (egyszerű):**
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

**Option B: Web Dashboard használata** (CLI nélkül is megy!)

---

### 3. Project létrehozása (Web Dashboard)

**Ha CLI-vel:**
```bash
cd C:\Users\Muki\clawd\Tippmix
fly launch
```

**Ha Web UI-val:**
1. Dashboard → **"Create an app"**
2. Name: `tippmix-reddit-cron`
3. Region: **Frankfurt** (EU)

---

### 4. Dockerfile létrehozása

**Fájl:** `Tippmix/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Run cron script
CMD ["python", "scripts/combined_tipster_alert.py"]
```

---

### 5. fly.toml konfiguráció

**Fájl:** `Tippmix/fly.toml`

```toml
app = "tippmix-reddit-cron"
primary_region = "fra"

[build]
  dockerfile = "Dockerfile"

[env]
  TELEGRAM_BOT_TOKEN = "<your_telegram_bot_token>"
  TELEGRAM_VIP_CHAT_ID = "-1003341312269"

[experimental]
  auto_rollback = true

[[services]]
  internal_port = 8080
  protocol = "tcp"

  [[services.ports]]
    port = 80

# Cron schedule (runs daily at 14:00 UTC)
[processes]
  cron = "while true; do python scripts/combined_tipster_alert.py; sleep 86400; done"
```

---

### 6. Deploy

**CLI:**
```bash
fly deploy
```

**Web UI:**
1. Push to GitHub
2. Fly.io Dashboard → Connect GitHub repo
3. Auto-deploy on push ✅

---

## ⏰ CRON SETUP

**Option A: Fly Machines API (hivatalos cron):**

```bash
fly machines run . --schedule "0 14 * * *" --region fra
```

**Option B: Egyszerű loop (a fly.toml-ban már benne van):**
- Sleep 24 óra között
- Futtatás naponta egyszer

---

## ✅ ELLENŐRZÉS

```bash
fly status
fly logs
```

**Web UI-n:**
- Dashboard → `tippmix-reddit-cron`
- Logs tab → Látod a kimenet-et
- Success → Telegram VIP-be alert! 📱

---

## 💰 KÖLTSÉG

**INGYEN!**
- VM: Free tier (Shared CPU, 256MB)
- Forgalom: ~1 MB/nap = 30 MB/hó << 160 GB limit
- **0 Ft/hó, örökre!** ✅

---

## 🆘 HELP

Ha elakadsz, írj! Végigvezetlek lépésről lépésre! 👨‍🏫
