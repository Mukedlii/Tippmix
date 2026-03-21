@echo off
REM Daily Reddit Picks Alert Runner
REM Run this via Windows Task Scheduler daily at 15:00 CET

cd /d C:\Users\Muki\clawd\Tippmix

REM Telegram credentials
set TELEGRAM_BOT_TOKEN=8238287955:AAEo87ADOjZx6qcCW1eEYN6YV1klAzZ_8bs
set TELEGRAM_VIP_CHAT_ID=-1003341312269

REM Run the script
python send_top_reddit_picks.py

REM Log result
echo.
echo [%date% %time%] Reddit alert run completed >> daily_reddit_log.txt
