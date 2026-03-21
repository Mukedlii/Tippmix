@echo off
REM Daily Reddit Picks Alert Runner
REM Run this via Windows Task Scheduler daily at 15:00 CET

cd /d C:\Users\Muki\clawd\Tippmix

REM Set Telegram credentials (get from GitHub Secrets or create new bot)
REM REPLACE THESE WITH YOUR ACTUAL VALUES:
set TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
set TELEGRAM_VIP_CHAT_ID=YOUR_VIP_CHAT_ID_HERE

REM Run the script
python send_top_reddit_picks.py

REM Log result
echo.
echo [%date% %time%] Reddit alert run completed >> daily_reddit_log.txt
