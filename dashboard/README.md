# SZELVÉNYKIRÁLY Dashboard

**100% FREE** static dashboard - no server required! 🎉

## Features

- 📊 ROI tracking (7/30 nap)
- 🎯 Hit rate analytics by tier (VIP vs FREE)
- 🏆 Top winning bets showcase
- 📈 ROI trend visualization
- 📱 Responsive design
- 💸 **Zero hosting costs** (Vercel free tier)

## How It Works

1. **GitHub Actions** generates static JSON files daily (1:00 + 19:00 UTC)
2. **Next.js** static export reads JSON files
3. **Vercel** hosts for free (no server needed!)

## Setup (Local Development)

1. Install dependencies:
```bash
npm install
```

2. Generate data locally (optional):
```bash
cd ..
python scripts/generate_dashboard_data.py
```

3. Start dev server:
```bash
npm run dev
```

4. Open http://localhost:3000

## Production Deployment (Vercel)

### Auto-Deploy (Recommended)

1. Push to GitHub
2. Connect repo to Vercel
3. Deploy! (zero config needed)

Every time GitHub Actions updates the JSON files, Vercel auto-redeploys.

### Manual Build

```bash
npm run build
npm run start
```

## Data Updates

- **Automatic**: GitHub Actions runs daily at 1:00 AM & 7:00 PM UTC
- **Manual**: Run `python scripts/generate_dashboard_data.py`
- **Files**: `dashboard/public/data/*.json`

## Cost Breakdown

- Vercel hosting: **FREE** ✅
- GitHub Actions: **FREE** ✅
- Data storage: **FREE** (JSON in repo)
- **Total: $0/month** 💰

## Data Files

- `stats_7d.json` - Overall 7-day stats
- `vip_7d.json` - VIP tier 7-day stats
- `free_7d.json` - FREE tier 7-day stats
- `top_wins.json` - Top 3 winning bets
- `roi_trend.json` - 30-day ROI trend
- `recent_bets.json` - Last 20 bets
- `metadata.json` - Last updated timestamp
