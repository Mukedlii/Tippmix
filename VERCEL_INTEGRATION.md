# ML Feedback Loop - VERCEL Integration

## Vercel Pages Setup

```bash
# 1. Install dependencies
npm install next react vercel

# 2. Create pages/api/stats.js
```

## API Endpoints (Vercel Functions)

### GET /api/stats/feedback
```json
{
  "last_7_days": {
    "bets_matched": 45,
    "correct": 28,
    "hitrate": 0.622,
    "by_league": {...}
  }
}
```

### GET /api/stats/league?name=Premier%20League
```json
{
  "league": "Premier League",
  "total_bets": 120,
  "correct": 87,
  "hitrate": 0.725,
  "trend": "↑ +5.2%"
}
```

### GET /api/model/confidence
```json
{
  "model_version": "v1.2",
  "features": ["league_tier", "team_form", "odds_value", "recent_accuracy"],
  "last_retrain": "2026-06-27T18:00:00Z"
}
```

## Dashboard Pages

- `/dashboard` - Overall stats
- `/league-stats` - By league breakdown
- `/tips-history` - Recent tips + results
- `/model-info` - ML model details

## Database Connection

```python
# From Vercel:
import os
TIPPMIX_DB_URL = os.getenv("TIPPMIX_DB_URL")  # SQLite file in /data
```

Integráció után:
```
https://tippmix.vercel.app/dashboard
```
