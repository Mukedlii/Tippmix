@echo off
REM Daily Reddit Picks Alert Runner
REM Run this via Windows Task Scheduler daily at 15:00 CET

cd /d C:\Users\Muki\clawd\Tippmix

REM Telegram credentials
if "%TELEGRAM_BOT_TOKEN%"=="" (
  echo ERROR: TELEGRAM_BOT_TOKEN is not set
  exit /b 1
)
set TELEGRAM_VIP_CHAT_ID=-1003341312269

REM Run the script
python send_top_reddit_picks.py

REM Log result
echo.
echo [%date% %time%] Reddit alert run completed >> daily_reddit_log.txt
