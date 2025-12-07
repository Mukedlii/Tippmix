import os
import json
import asyncio
from pathlib import Path

from telegram import Bot

from bot.results import evaluate_bets, build_daily_report_text


DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_bets_from_json(filename: str):
    """
    Beolvassa a public_bets.json / vip_bets.json fájlokat.
    Visszaad: (date_str, bets_list)
    """
    path = DATA_DIR / filename
    if not path.exists():
        print(f"Figyelem: {filename} nem található ({path}).")
        return None, []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("date")
        bets = data.get("bets", [])
        return date_str, bets
    except Exception as e:
        print(f"Hiba a {filename} beolvasásakor:", repr(e))
        return None, []


async def main():
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    # Döntsd el, hova menjen a napi mérleg – VIP csatornába pl.:
    recap_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID") or os.getenv("TELEGRAM_PUBLIC_CHAT_ID")

    if not telegram_token:
        raise RuntimeError("Hiányzik a TELEGRAM_BOT_TOKEN környezeti változó.")
    if not recap_chat_id:
        raise RuntimeError("Hiányzik a TELEGRAM_VIP_CHAT_ID vagy TELEGRAM_PUBLIC_CHAT_ID a recaphez.")

    bot = Bot(token=telegram_token)

    # 1) Public + VIP tippek beolvasása
    date_public, public_bets = _load_bets_from_json("public_bets.json")
    date_vip, vip_bets = _load_bets_from_json("vip_bets.json")

    # Ha az egyiknél nincs dátum, próbáljuk a másikból venni
    date_str = date_public or date_vip
    if not date_str:
        raise RuntimeError("Nem található dátum egyik JSON-ban sem – valószínűleg még nem futott a main.py.")

    # 2) Kiértékelés (win/lose/pending/unknown)
    public_summary = evaluate_bets(public_bets)
    vip_summary = evaluate_bets(vip_bets)

    # 3) Napi mérleg szöveg generálása
    recap_text = build_daily_report_text(date_str, public_summary, vip_summary)

    # 4) Üzenet küldése Telegramra
    try:
        await bot.send_message(chat_id=recap_chat_id, text=recap_text)
        print("Napi mérleg üzenet elküldve.")
    except Exception as e:
        print("Hiba a napi mérleg üzenet küldésekor:", repr(e))


if __name__ == "__main__":
    asyncio.run(main())
