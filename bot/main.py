import os
import asyncio
from telegram import Bot
from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


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

    # 1) Mai meccsek lekérése API-FOOTBALL-ból
    matches = fetch_matches_for_today()
    print(f"Talált meccsek száma: {len(matches)}")

    # 2) Tipp generálás OpenAI-jal (FREE + VIP)
    tips_data = generate_tips(matches)

    public_text = tips_data.get("telegram_public_text")
    vip_text = tips_data.get("telegram_vip_text")

    # 3) Nyilvános csatorna – ha van beállítva ID (max 3 tipp szöveg)
    if public_chat_id and public_text:
        try:
            await bot.send_message(chat_id=public_chat_id, text=public_text)
            print("Nyilvános üzenet elküldve.")
        except Exception as e:
            print(f"Hiba a nyilvános csatornára küldésnél: {repr(e)}")

    # 4) VIP csatorna – több tipp (6–8 meccs)
    if vip_chat_id and vip_text:
        try:
            await bot.send_message(chat_id=vip_chat_id, text=vip_text)
            print("VIP üzenet elküldve.")
        except Exception as e:
            print(f"Hiba a VIP csatornára küldésnél: {repr(e)}")


if __name__ == "__main__":
    asyncio.run(main())
