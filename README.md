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

- A provider automatikusan választ:
  - ha van `SPORTS_API_KEY` → API-FOOTBALL
  - ha van `SPORTSDATAIO_API` → SportsDataIO
  - felülírható `SPORTS_DATA_PROVIDER=api-sports|sportsdataio` env-vel

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
