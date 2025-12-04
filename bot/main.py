import os
import asyncio
from telegram import Bot


async def main():
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    print(f"TELEGRAM_BOT_TOKEN be van állítva: {bool(telegram_token)}")
    print(f"PUBLIC_CHAT_ID = {public_chat_id!r}")
    print(f"VIP_CHAT_ID    = {vip_chat_id!r}")

    if not telegram_token:
        raise RuntimeError("Hiányzik a TELEGRAM_BOT_TOKEN környezeti változó.")

    bot = Bot(token=telegram_token)

    test_text = "Teszt üzenet a SZELVÉNYKIRÁLY bottól (GitHub Actions)."

    # Sima (public) csatorna teszt
    if public_chat_id:
        try:
            await bot.send_message(chat_id=public_chat_id, text="[PUBLIC] " + test_text)
            print("Public üzenet elküldve, nem volt hiba.")
        except Exception as e:
            print(f"Hiba a PUBLIC csatornára küldésnél: {repr(e)}")
    else:
        print("NINCS beállítva TELEGRAM_PUBLIC_CHAT_ID.")

    # VIP csatorna teszt
    if vip_chat_id:
        try:
            await bot.send_message(chat_id=vip_chat_id, text="[VIP] " + test_text)
            print("VIP üzenet elküldve, nem volt hiba.")
        except Exception as e:
            print(f"Hiba a VIP csatornára küldésnél: {repr(e)}")
    else:
        print("NINCS beállítva TELEGRAM_VIP_CHAT_ID.")


if __name__ == "__main__":
    asyncio.run(main())
