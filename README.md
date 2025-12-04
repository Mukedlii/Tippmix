# SZELVÉNYKIRÁLY – Telegram Tippmix Bot

Ez egy alap projekt, ami:
- GitHub Actions segítségével napi többször lefut
- OpenAI-t használ a meccsek elemzésére
- Telegram csatornákra küldi a tippeket (nyilvános + VIP)

Fontos:
- Minden API kulcsot (Telegram, OpenAI, sport API) **GitHub Secrets-ben** tárolj.
- A `bot/matches.py` fájl jelenleg csak MINTA adatokat ad vissza.
  Később ezt kell összekötni egy valódi sport/odds API-val.
