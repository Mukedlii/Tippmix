import os


def get_sports_api_key() -> str:
    key = (os.getenv("SPORTS_API_KEY") or "").strip()
    if key:
        return key

    key = (os.getenv("SPORTSDATAIO_API") or "").strip()
    if key:
        return key

    raise RuntimeError("SPORTS_API_KEY vagy SPORTSDATAIO_API nincs beállítva (GitHub Secrets).")


def get_optional_sports_api_key() -> str:
    key = (os.getenv("SPORTS_API_KEY") or "").strip()
    if key:
        return key
    key = (os.getenv("SPORTSDATAIO_API") or "").strip()
    return key
