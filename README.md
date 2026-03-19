# SZELVÉNYKIRÁLY – Telegram Tippmix Bot

Ez egy alap projekt, ami:
- GitHub Actions segítségével napi többször lefut
- **Claude Sonnet 4.6-ot** (Anthropic) használ a meccsek elemzésére
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

## Odds (opcionális)
Ha SportsDataIO-t használsz, de szeretnél oddsokat (1X2), beköthető a The Odds API:
- Secret: `ODDS_API_KEY`
- Régió: `ODDS_REGIONS` (pl. `eu`)
- Limit / futás: `ODDS_MAX_REQUESTS_PER_RUN` (free csomaghoz ajánlott 4–8)
- (opcionális) sport kulcsok: `ODDS_SPORT_KEYS` (comma-separated)
