# Historical Data Backfill

## Mi ez?

Ez a script letölti a historical match results-okat (befejezett meccsek eredményeit) a football-data.org API-ból és feltölti a Tippmix adatbázisba.

**Miért kell?**
- A Poisson modellhez kell historical data (team/league goal átlagok)
- Több adat = jobb predikciók
- Jelenleg NINCS elég historical data → gyenge accuracy

## Futtatás

### 1. Lokálisan (Windows)

```bash
cd C:\Users\Muki\clawd\Tippmix

# 1 liga, 1 szezon (teszt)
python scripts\backfill_historical_data.py --season 2023 --competitions PL

# Top 5 liga, utolsó 3 szezon (FULL backfill)
python scripts\backfill_historical_data.py --all
```

**Időigény:**
- 1 liga, 1 szezon: ~1 perc
- --all (7 liga, 3 szezon): ~15-20 perc (rate limit miatt)

### 2. GitHub Actions (távoli)

1. Nevezd át: `.github/workflows/backfill_historical.yml.disabled` → `.yml`
2. GitHub repo → Actions tab → "Backfill Historical Data"
3. Run workflow → hagyj üresen (--all mode)
4. Várj 20 percet
5. Rename vissza `.yml.disabled` (ne fusson véletlenül újra)

## API Key

A script a `FOOTBALLDATA_API_KEY` vagy `FOOTBALL_DATA_TOKEN` env változót használja.

**Lokális futtatáshoz:**

```bash
# PowerShell
$env:FOOTBALLDATA_API_KEY = "your_key_here"
python scripts\backfill_historical_data.py --all
```

GitHub Actions esetén már benne van a Secrets-ben.

## football-data.org Free Tier

**Limit:** 10 requests / minute
**Ligák (free tier):**
- Premier League (PL)
- La Liga (PD)
- Serie A (SA)
- Bundesliga (BL1)
- Ligue 1 (FL1)
- Eredivisie (DED)
- Primeira Liga (PPL)
- Champions League (CL)
- Europa League (EL)
- World Cup / Euros

**Historical data:** 10+ years vissza

## Ellenőrzés

```bash
# DB méret check
python scripts\backfill_historical_data.py --season 2023 --competitions PL
```

Várható output:
```
Found 380 finished matches
Stored 380/380 matches
```

## Mi történik utána?

1. **Poisson model automatikusan jobb lesz** (több historical data → jobb paraméterek)
2. **Következő tipp generálás:** accuracy ↑
3. **Manual tracking** után látod a javulást

## Troubleshooting

**Error: FOOTBALLDATA_API_KEY not set**
→ Nincs API kulcs beállítva (lásd fent)

**Error: HTTP 429 (Too Many Requests)**
→ Rate limit túllépve (10 req/min). Várj 1 percet.

**Error: HTTP 403 (Forbidden)**
→ Lejárt/hibás API kulcs. Új kulcs kell: https://www.football-data.org/client/register

**Stored 0/XXX matches**
→ Már benne vannak az adatbázisban (duplicate skip működik)
