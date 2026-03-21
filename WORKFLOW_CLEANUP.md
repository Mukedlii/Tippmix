# Workflow Cleanup - AI Tipster System

## 🎯 ÚJ RENDSZER (1 workflow, 6 task)

### `ai_tipster_system.yml` - ÚJ, CLEAN workflow

**Schedule (6 futás/nap):**
```
01:00 CET → aggregate_tipsters.py  (Reddit/Telegram/Nemzeti Sport)
03:00 CET → fetch_results.py       (TheOddsAPI scores)
03:15 CET → settle_tips.py         (Auto-settlement + stats update)
14:00 CET → ai_consensus.py        (OpenAI GPT-4o-mini analysis)
15:00 CET → send_top6_alert.py     (Telegram TOP 6 + combos)
23:30 CET → daily_recap.py         (Evening results recap)
```

**Features:**
- ✅ Minden task külön job (parallel futás ahol lehet)
- ✅ DB persistence (GitHub Actions cache)
- ✅ Manual trigger support (workflow_dispatch, task selector)
- ✅ Minimális dependencies (csak ami kell)
- ✅ Clean, documented

**Cost:**
- 6 runs/day × ~1 min each = ~6 min/day
- ~180 min/month = **3 hours/month GitHub Actions**
- Free tier: 2000 min/month ✅ **BŐVEN ELÉG!**

---

## 🗑️ RÉGI WORKFLOWS (DISABLE AJÁNLOTT)

### Felesleges / Duplikált:
1. **`backfill_historical.yml`** - Egyszeri backfill (nem kell napi)
2. **`cron.yml`** - Régi generic cron (replaced by ai_tipster_system)
3. **`daily_recap_day_late.yml`** - Régi recap (replaced)
4. **`daily_recap_evening.yml`** - Régi recap (replaced)
5. **`news_alert.yml`** - Híreket küld (nem part of system)
6. **`reddit_consensus.yml`** - ✅ Már disabled (Reddit blocks GA IPs)
7. **`tippmix_day.yml`** - Régi Poisson alert (replaced by AI system)
8. **`tippmix_evening.yml`** - Régi Poisson alert (replaced)
9. **`tippmix_hourly_alert_recap.yml`** - Túl gyakori (óránként!)
10. **`tippmix_morning_free_only.yml`** - Régi morning alert
11. **`tippmix_morning_full.yml`** - Régi morning alert
12. **`tippmix_nightly_recap.yml`** - Régi recap (03:00, replaced by 23:30 recap)
13. **`tippmix_selftest_provider.yml`** - Test only (manual use)

### Megtarthatók (opcionális):
14. **`update-dashboard-data.yml`** - Vercel dashboard update
    - **Ha kell:** Keep enabled
    - **Ha nem:** Disable (manual trigger elérhető)
15. **`weekly-report.yml`** - Heti összefoglaló
    - **Ha kell:** Keep enabled
    - **Ha nem:** Disable
16. **`weekly_db_refresh.yml`** - Heti DB cleanup
    - **Ajánlott:** Keep enabled (DB maintenance)

---

## 🛠️ HOGYAN DISABLE-OLD?

### Opció 1: Rename (ajánlott)
```powershell
cd C:\Users\Muki\clawd\Tippmix
.\scripts\disable_old_workflows.ps1
```
→ Átnevezi: `*.yml` → `*.disabled.yml`  
→ GitHub Actions nem látja őket

### Opció 2: Manual (GitHub UI)
1. GitHub repo → Actions → Workflows
2. Minden workflow mellett: "..." → Disable workflow

### Opció 3: Edit schedule (megtartja history-t)
```yaml
on:
  # schedule:  # <-- Comment out
  #   - cron: '...'
  workflow_dispatch:  # Manual only
```

---

## ✅ MIT TARTUNK MEG?

**Active workflows (1-4 db):**
1. ✅ `ai_tipster_system.yml` - **MAIN SYSTEM** (6 tasks)
2. ⚠️ `update-dashboard-data.yml` - Vercel dashboard (opcionális)
3. ⚠️ `weekly-report.yml` - Heti report (opcionális)
4. ⚠️ `weekly_db_refresh.yml` - DB cleanup (ajánlott)

**Minden más:** Disable vagy delete

---

## 📊 ÖSSZEHASONLÍTÁS

### Régi rendszer (16 workflow)
- **Runs/day:** ~20-30 (hourly alerts, multiple recaps)
- **Minutes/month:** ~600-800 min
- **Complexity:** High (sok duplikáció, overlap)
- **Maintenance:** Nehéz (melyik mit csinál?)

### Új rendszer (1 workflow)
- **Runs/day:** 6 (clean schedule)
- **Minutes/month:** ~180 min (70% kevesebb!)
- **Complexity:** Low (1 file, 6 tasks)
- **Maintenance:** Egyszerű (mindent látunk)

---

## 🚀 DEPLOYMENT

### 1. Commit új workflow
```bash
git add .github/workflows/ai_tipster_system.yml
git add scripts/daily_recap.py
git commit -m "Add unified AI Tipster System workflow"
git push
```

### 2. Disable régi workflows
```bash
cd scripts
.\disable_old_workflows.ps1
git add .github/workflows/*.disabled.yml
git commit -m "Disable old workflows (replaced by ai_tipster_system)"
git push
```

### 3. Test manual trigger
- GitHub → Actions → "AI Tipster System"
- Run workflow → Select task: "all"
- Check logs

### 4. Monitor first scheduled run
- Wait for 01:00 CET (aggregate)
- Check Actions logs
- Verify Telegram alerts (15:00, 23:30)

---

## 🎯 EREDMÉNY

**Előtte:**
- 16 workflow
- Sok duplikáció
- Nehéz karbantartás
- 600+ min/month

**Utána:**
- 1 workflow (+ 2-3 optional)
- Clean, minimal
- Könnyű megértés
- 180 min/month ✅

**Megtakarítás:**
- 70% kevesebb GitHub Actions használat
- 90% kevesebb konfiguráció
- 100% tisztább architektúra

---

**Created:** 2026-03-21  
**Status:** Ready to deploy
