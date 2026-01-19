# SZELVÉNYKIRÁLY – Telegram Tippmix Bot

Ez egy alap projekt, ami:
- GitHub Actions segítségével napi többször lefut
- OpenAI-t használ a meccsek elemzésére
- Telegram csatornákra küldi a tippeket (nyilvános + VIP)

Fontos:
- Minden API kulcsot (Telegram, OpenAI, sport API) **GitHub Secrets-ben** tárolj.
- A `bot/matches.py` több providerből is tud meccseket hozni, a kulcsokat env változókból olvassa.

## Több sport API támogatása

A meccsekhez több adatforrást is beállíthatsz, hogy stabilabb legyen a tipp-pool:

- `SPORTS_API_KEY`: API-Football / API-Sports kulcs (kötelező, ha `api_sports` provider aktív).
- `SPORTMONKS_API_TOKEN`: SportMonks kulcs (kötelező, ha `sportmonks` provider aktív).
- `TIPPMIX_FIXTURE_PROVIDERS`: vesszővel elválasztott lista, pl. `api_sports,sportmonks`.

Ha valamelyik provider kulcsa hiányzik, a rendszer automatikusan kihagyja azt.
