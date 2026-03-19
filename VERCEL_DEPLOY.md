# 🚀 Vercel Deploy Guide (100% INGYEN)

## Lépések

### 1. GitHub Repository Előkészítés

✅ Kész! A repo már tartalmazza:
- Dashboard kód: `dashboard/`
- GitHub Action: `.github/workflows/update-dashboard-data.yml`
- Static JSON files: `dashboard/public/data/`

### 2. Vercel Account

1. Menj: https://vercel.com
2. **Sign up with GitHub**
3. Authorize Vercel to access your repos

### 3. Import Project

1. Vercel Dashboard → **Add New Project**
2. **Import Git Repository**
3. Válaszd: `Mukedlii/Tippmix`
4. Configure:
   - **Framework Preset**: Next.js (auto-detected)
   - **Root Directory**: `dashboard`
   - **Build Command**: `npm run build`
   - **Output Directory**: `out` (static export)

### 4. Deploy!

1. Click **Deploy**
2. Várj ~2 percet
3. Kész! 🎉

**URL**: `https://tippmix-<random>.vercel.app`

### 5. Custom Domain (Opcionális)

1. Vercel Dashboard → Project Settings → **Domains**
2. Add domain: `tippmix.yourdomain.com`
3. Frissítsd DNS-t (Vercel ad instructionst)

### 6. Auto-Deploy Beállítás

✅ Már be van állítva!

Minden push után ami módosítja a `dashboard/` mappát → auto redeploy.

GitHub Actions naponta 2x frissíti a JSON-t → Vercel auto-deploy.

## Environment Variables

**Nincs szükség!** 🎉

A dashboard teljesen statikus, nincs API key vagy titkos adat.

## Korlátok (Free Tier)

- ✅ Unlimited deployments
- ✅ 100 GB bandwidth/month (bőven elég)
- ✅ Custom domain support
- ✅ Automatic HTTPS
- ✅ Global CDN

**Cost: $0/month** 💸

## Automatikus Frissítés

```
GitHub Actions (naponta 2x, 1:00 + 19:00 UTC)
    ↓ generates JSON files
    ↓ commits to GitHub
    ↓
Vercel detects push
    ↓ auto-builds
    ↓ deploys new version
    ↓
Live in ~30 seconds! 🚀
```

## Tesztelés Lokálisan

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:3000
```

## Troubleshooting

### "No data showing"

→ Futtasd le a data generátort egyszer:
```bash
python scripts/generate_dashboard_data.py
git add dashboard/public/data/
git commit -m "Add initial data"
git push
```

### "404 on /data/*.json"

→ Győződj meg hogy a `dashboard/public/data/` mappa létezik és tartalmazza a JSON-öket.

### "Build failed"

→ Ellenőrizd:
- Root Directory: `dashboard`
- Output Directory: `out`
- Build Command: `npm run build`

## Monitoring

Vercel Dashboard mutatja:
- Deploy history
- Build logs
- Bandwidth usage
- Error tracking (ha van)

---

**Support:** Ha bármi gond van, küldj screenshot-ot a Vercel error-ról.
