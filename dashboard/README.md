# SZELVÉNYKIRÁLY Dashboard

Real-time betting performance analytics dashboard built with Next.js.

## Features

- 📊 Live ROI tracking (daily, weekly, monthly)
- 🎯 Hit rate analytics by tier (VIP vs FREE)
- 🏆 Top winning bets showcase
- 📈 ROI trend visualization
- ⚡ Real-time data updates
- 📱 Responsive design

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start the Flask API (from parent directory):
```bash
cd ..
pip install flask flask-cors
python api/stats_api.py
```

3. Start the Next.js dev server:
```bash
npm run dev
```

4. Open http://localhost:3000

## Environment Variables

Create `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:5000
```

## Production Deployment

### Vercel (Recommended)

1. Push to GitHub
2. Import project in Vercel
3. Set environment variables
4. Deploy!

### Docker

```bash
docker build -t tippmix-dashboard .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=https://api.yourdomain.com tippmix-dashboard
```

## API Integration

The dashboard connects to the Flask API (`api/stats_api.py`) which reads from the SQLite database.

Make sure the API is running and accessible before starting the dashboard.
