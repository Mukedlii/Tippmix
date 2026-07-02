# SZELVÉNYKIRÁLY – Telegram Tippmix Bot

Ez egy alap projekt, ami:
- GitHub Actions segítségével napi többször lefut
- **Ensemble AI-t** használ (Claude + GPT-4o + Gemini szavazás) a meccsek elemzésére
- Telegram csatornákra küldi a tippeket (nyilvános + VIP)

Fontos:
- Minden API kulcsot (Telegram, OpenAI, sport API) **GitHub Secrets-ben** tárolj.
- A sport API kulcsok a providerhez kötődnek:
  - API-FOOTBALL (API-Sports): `SPORTS_API_KEY`
  - SportsDataIO (soccer): `SPORTSDATAIO_API`
  - (opcionális, később bővíthető): SportMonks: `SPORTMONKS_API_TOKEN`

- A provider alapból scraping-first módban fut (`free_scraper`), hogy ne kelljen fizetős API.
- Felülírható expliciten: `SPORTS_DATA_PROVIDER=free_scraper|footballdata|api-sports|sportsdataio|sportmonks|allsportsapi`
- Ha automata API-választást szeretnél kulcsok alapján, állítsd: `TIPPMIX_PREFER_SCRAPING=0`

## Komprehenzív scraper pipeline (API kulcs nélkül)

Új multi-source adatgyűjtés került a botba:

- `bot/scrapers/`:
  - `flashscore.py` (fixture + odds)
  - `sofascore.py` (fixture + odds + xG/injury context)
  - `fotmob.py` (fixture feed)
  - `espn.py` (fixture + eredmények)
  - `betfair.py`, `oddschecker.py` (public odds scraping)
  - `base_scraper.py` (retry, 429 kezelés, User-Agent rotáció, proxy támogatás)
- `bot/aggregators/`:
  - `data_aggregator.py` (források merge + conflict kezelés)
  - `odds_aggregator.py` (weighted average + best odds)
  - `confidence_scorer.py` (forrás minőségi súlyok)
  - `cache_manager.py` (24 órás / meccskezdésig cache)
- `bot/expert_sources/`:
  - `reddit_scraper.py`, `twitter_scraper.py`
- `bot/prediction_markets/`:
  - `polymarket.py`, `manifold.py`, `betfair_market.py`

### SQLite bővített séma

Az alábbi táblák automatikusan létrejönnek `bot/storage/sqlite_store.py:init_db()` során:

- `data_sources`
- `odds_history`
- `expert_picks`
- `prediction_market`

### Ütemezés

Új workflow: `.github/workflows/tippmix_scraper.yml`  
Futás: **06:00, 12:00, 18:00 UTC** naponta.

Pipeline lépések:
1. Multi-source fixture gyűjtés
2. Odds aggregáció (best + weighted average)
3. Sérülés/forma/xG context enrichment
4. Expert + prediction market indikátorok
5. Mentés SQLite-ba + dashboard JSON frissítés

## Adatbázis (SQLite)
Alapból a futások és tippek mentésre kerülnek SQLite-ba:
- `data/tippmix.db`
- felülírható: `TIPPMIX_DB_PATH`

## Enhanced Data (Sérülések, H2H, Statisztikák)
A bot gazdagított adatokat használ jobb tippekhez:
- **Sérülések & felfüggesztések**: API-Football injuries endpoint
- **Head-to-head előzmények**: utolsó 5 meccs két csapat között
- **Fejlett csapat statisztikák**: gól átlag, clean sheets, stb.

Bekapcsolás (alapból BE van):
- `TIPPMIX_USE_ENHANCED_DATA=1`
- `TIPPMIX_USE_INJURIES=1`
- `TIPPMIX_USE_H2H=1`
- `TIPPMIX_USE_ADVANCED_STATS=1`

**Figyelem**: Ezek extra API hívásokat jelentenek (fixture-enként +3 hívás).
API-Football free tier: 100 hívás/nap → max ~30 meccs/nap enhanced adatokkal.

## Odds (opcionális)
Ha SportsDataIO-t használsz, de szeretnél oddsokat (1X2), beköthető a The Odds API:
- Secret: `ODDS_API_KEY`
- Régió: `ODDS_REGIONS` (pl. `eu`)
- Limit / futás: `ODDS_MAX_REQUESTS_PER_RUN` (free csomaghoz ajánlott 4–8)
- (opcionális) sport kulcsok: `ODDS_SPORT_KEYS` (comma-separated)
