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


def resolve_sports_provider() -> str:
    provider = (os.getenv("SPORTS_DATA_PROVIDER") or "").strip().lower()
    if provider in ("api-sports", "api_sports", "apisports", "api-football", "apifootball"):
        return "api-sports"
    if provider in ("sportsdataio", "sports-data-io", "sportsdata"):
        return "sportsdataio"
    if get_optional_api_sports_key():
        return "api-sports"
    if get_optional_sportsdataio_key():
        return "sportsdataio"
    raise RuntimeError("SPORTS_API_KEY vagy SPORTSDATAIO_API nincs beállítva (GitHub Secrets).")


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
