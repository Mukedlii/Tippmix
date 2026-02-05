import datetime
import os

from bot.api_keys import resolve_sports_provider
from bot.matches import fetch_matches_for_today


def main():
    provider = None
    try:
        provider = resolve_sports_provider()
    except Exception as e:
        print("PROVIDER_ERROR", repr(e))
        return

    today = datetime.date.today().isoformat()
    print("provider=", provider)
    print("date=", today)

    try:
        ms = fetch_matches_for_today(slot=os.getenv("TIPPMIX_SLOT", "ALL"), date=today)
        print("matches_total=", len(ms))
        if ms:
            m0 = ms[0]
            print("sample=", {k: m0.get(k) for k in ("fixture_id", "league_name", "country_name", "kickoff_local", "home_team", "away_team")})
    except Exception as e:
        print("FETCH_ERROR", repr(e))


if __name__ == "__main__":
    main()
