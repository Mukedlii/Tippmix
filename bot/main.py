
import os
from telegram import Bot
from bot.matches import fetch_matches_for_today
from bot.openai_logic import generate_tips


def main():
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")

    if not telegram_token:
        raise RuntimeError("Hiányzik a TELEGRAM_BOT_TOKEN környezeti változó.")

    bot = Bot(token=telegram_token)

    matches = fetch_matches_for_today()
    tips_data = generate_tips(matches)

    public_text = tips_data["telegram_public_text"]
    vip_text = tips_data["telegram_vip_text"]

    if public_chat_id:
        bot.send_message(chat_id=public_chat_id, text=public_text)

    if vip_chat_id:
        bot.send_message(chat_id=vip_chat_id, text=vip_text)


if __name__ == "__main__":
    main()
