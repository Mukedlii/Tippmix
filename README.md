# SZELVÉNYKIRÁLY – Telegram Tippmix Bot

Ez egy alap projekt, ami:
- GitHub Actions segítségével napi többször lefut
- OpenAI-t használ a meccsek elemzésére
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
