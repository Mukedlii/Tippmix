import os


def get_api_sports_key() -> str:
    key = (os.getenv("SPORTS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("SPORTS_API_KEY nincs beállítva (GitHub Secrets).")
    return key


def get_sportsdataio_key() -> str:
    key = (os.getenv("SPORTSDATAIO_API") or "").strip()
    if not key:
        raise RuntimeError("SPORTSDATAIO_API nincs beállítva (GitHub Secrets).")
    return key


def get_optional_api_sports_key() -> str:
    return (os.getenv("SPORTS_API_KEY") or "").strip()


def get_optional_sportsdataio_key() -> str:
    return (os.getenv("SPORTSDATAIO_API") or "").strip()


def get_optional_sportmonks_token() -> str:
    return (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()


def get_optional_football_data_token() -> str:
    return (os.getenv("FOOTBALLDATA_API_KEY") or os.getenv("FOOTBALL_DATA_TOKEN") or "").strip()


def get_optional_allsportsapi_key() -> str:
    return (os.getenv("ALLSPORTSAPI_KEY") or "").strip()


def resolve_sports_provider() -> str:
    provider = (os.getenv("SPORTS_DATA_PROVIDER") or "").strip().lower()
    prefer_scraping = (os.getenv("TIPPMIX_PREFER_SCRAPING") or "1").strip() == "1"

    # ÚJ: teljesen ingyenes scraper (SofaScore/LiveScore/Flashscore) — nincs key
    if provider == "free_scraper":
        return "free_scraper"

    # football-data.org (free)
    if provider in ("footballdata", "football-data", "football_data", "footballdata.org"):
        return "footballdata"

    if provider in ("api-sports", "api_sports", "apisports", "api-football", "apifootball"):
        return "api-sports"
    if provider in ("sportsdataio", "sports-data-io", "sportsdata"):
        return "sportsdataio"
    if provider in ("sportmonks", "sport-monks"):
        return "sportmonks"
    if provider in ("allsportsapi", "all-sports-api", "allsports"):
        return "allsportsapi"

    # scraping-first mode (default): avoid paid APIs unless explicitly configured
    if prefer_scraping:
        return "free_scraper"

    # auto-pick preference order
    if get_optional_api_sports_key():
        return "api-sports"
    if get_optional_sportmonks_token():
        return "sportmonks"
    if get_optional_allsportsapi_key():
        return "allsportsapi"
    if get_optional_sportsdataio_key():
        return "sportsdataio"
    if get_optional_football_data_token():
        return "footballdata"

    raise RuntimeError("SPORTS_API_KEY / SPORTMONKS_API_TOKEN / ALLSPORTSAPI_KEY / SPORTSDATAIO_API / FOOTBALLDATA_API_KEY nincs beállítva (GitHub Secrets).")


def get_sports_api_key() -> str:
    key = get_optional_api_sports_key()
    if key:
        return key
    key = get_optional_sportsdataio_key()
    if key:
        return key
    raise RuntimeError("SPORTS_API_KEY vagy SPORTSDATAIO_API nincs beállítva (GitHub Secrets).")


def get_optional_sports_api_key() -> str:
    key = get_optional_api_sports_key()
    if key:
        return key
    return get_optional_sportsdataio_key()
