# bot/daily_recap_main.py
import os
import json
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.tips_logger import read_tips


def _split_telegram(text: str, max_len: int = 3900) -> List[str]:
    text = text or ""
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    cur = ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 <= max_len:
            cur = (cur + "\n\n" + block).strip()
        else:
            if cur:
                parts.append(cur)
            cur = block
    if cur:
        parts.append(cur)
    return parts


def send_telegram_message(token: str, chat_id: str, text: str, label: str) -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split_telegram(text)
    print(f"\n[{label}] Telegram küldés indul... üzenet részek: {len(parts)}")

    for idx, part in enumerate(parts, start=1):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        print(f"[{label}] Part {idx}/{len(parts)} sendMessage...")
        try:
            resp = requests.post(url, json=payload, timeout=25)
        except Exception as e:
            err = f"Requests hiba: {repr(e)}"
            print(f"[{label}] {err}")
            return False, err

        print(f"[{label}] HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}"

        try:
            data = resp.json()
        except Exception as e:
            return False, f"JSON parse hiba: {repr(e)}"

        if not data.get("ok"):
            return False, f"Telegram API error: {data}"

    print(f"[{label}] Üzenet(ek) sikeresen elküldve.")
    return True, ""


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def odds_band(o: float) -> str:
    if o < 1.30:
        return "<1.30"
    if o < 1.60:
        return "1.30-1.59"
    if o < 2.00:
        return "1.60-1.99"
    if o < 3.00:
        return "2.00-2.99"
    return "3.00+"


def _fetch_fixture(api_key: str, fixture_id: int) -> Optional[Dict[str, Any]]:
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}
    try:
        r = requests.get(url, headers=headers, params={"id": fixture_id}, timeout=25)
        if r.status_code != 200:
            return None
        data = r.json()
        resp = (data or {}).get("response") or []
        if not resp:
            return None
        return resp[0]
    except Exception:
        return None


def _fixture_outcome_1x2(f: Dict[str, Any]) -> Optional[str]:
    """
    returns "1" | "X" | "2" if finished, else None
    """
    fixture = f.get("fixture") or {}
    status = (fixture.get("status") or {}).get("short") or ""
    # FT, AET, PEN -> eldöntött
    if status not in ("FT", "AET", "PEN"):
        return None

    goals = f.get("goals") or {}
    hg = goals.get("home")
    ag = goals.get("away")
    if hg is None or ag is None:
        return None
    try:
        hg = int(hg)
        ag = int(ag)
    except Exception:
        return None

    if hg > ag:
        return "1"
    if hg < ag:
        return "2"
    return "X"


def _sel_to_1x2(sel_hu: str) -> Optional[str]:
    if sel_hu == "Hazai győzelem":
        return "1"
    if sel_hu == "Döntetlen":
        return "X"
    if sel_hu == "Vendég győzelem":
        return "2"
    return None


def main() -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")

    api_key = os.getenv("SPORTS_API_KEY")
    stake = int(os.getenv("TIPPMIX_STAKE_HUF", "1000"))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN, kilépek.")
        return
    if not api_key:
        msg = "⚠️ Nincs SPORTS_API_KEY beállítva, recap nem tud eredményt lekérni."
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, msg, "VIP_RECAP_ERR")
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, msg, "PUBLIC_RECAP_ERR")
        return

    # Tegnapi nap recap
    yday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    tips = read_tips(yday)
    if not tips:
        msg = f"ℹ️ Nincs log a tegnapi napról ({yday})."
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, msg, "VIP_RECAP_NOLOG")
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, msg, "PUBLIC_RECAP_NOLOG")
        return

    # Csak az eldönthető tippekhez kell fixture_id
    fixture_ids = sorted({int(t["fixture_id"]) for t in tips if t.get("fixture_id") is not None})

    fixtures: Dict[int, Dict[str, Any]] = {}
    for fid in fixture_ids:
        f = _fetch_fixture(api_key, fid)
        if f:
            fixtures[fid] = f
        time.sleep(float(os.getenv("TIPPMIX_RECAP_SLEEP_SEC", "0.15")))

    decided_rows: List[Dict[str, Any]] = []
    pending = 0

    for t in tips:
        fid = t.get("fixture_id")
        if fid is None:
            pending += 1
            continue
        fid = int(fid)
        f = fixtures.get(fid)
        if not f:
            pending += 1
            continue

        outcome = _fixture_outcome_1x2(f)
        if outcome is None:
            pending += 1
            continue

        sel = _sel_to_1x2(t.get("selection") or "")
        if not sel:
            pending += 1
            continue

        win = (sel == outcome)
        o = _safe_float(t.get("odds"))

        decided_rows.append(
            {
                "tier": t.get("tier"),
                "slot": t.get("slot"),
                "league": (t.get("league") or "Unknown"),
                "is_highlighted": bool(t.get("is_highlighted")),
                "odds": o,
                "win": win,
            }
        )

    wins = sum(1 for r in decided_rows if r["win"])
    losses = sum(1 for r in decided_rows if not r["win"])
    total_decided = wins + losses
    hit_rate = (wins / total_decided * 100.0) if total_decided else 0.0

    # League hit rates
    by_league: Dict[str, Dict[str, int]] = {}
    for r in decided_rows:
        lg = r["league"]
        by_league.setdefault(lg, {"w": 0, "l": 0})
        if r["win"]:
            by_league[lg]["w"] += 1
        else:
            by_league[lg]["l"] += 1

    # Odds band hit rates
    by_band: Dict[str, Dict[str, int]] = {}
    for r in decided_rows:
        o = r["odds"]
        if not o:
            continue
        b = odds_band(o)
        by_band.setdefault(b, {"w": 0, "l": 0})
        if r["win"]:
            by_band[b]["w"] += 1
        else:
            by_band[b]["l"] += 1

    # ROI highlighted vs non-highlighted (csak ahol van odds)
    def roi_calc(rows: List[Dict[str, Any]]) -> Tuple[int, int]:
        total_stake = 0
        profit = 0
        for r in rows:
            o = r.get("odds")
            if not o:
                continue
            total_stake += stake
            if r["win"]:
                profit += int(round((float(o) - 1.0) * stake))
            else:
                profit -= stake
        return profit, total_stake

    hl_rows = [r for r in decided_rows if r["is_highlighted"]]
    nh_rows = [r for r in decided_rows if not r["is_highlighted"]]

    hl_profit, hl_stake = roi_calc(hl_rows)
    nh_profit, nh_stake = roi_calc(nh_rows)

    def roi_pct(profit: int, st: int) -> float:
        return (profit / st * 100.0) if st else 0.0

    msg_lines = [
        "📊 SZELVÉNYKIRÁLY – NAPI RECAP",
        f"Dátum (log): {yday}",
        "",
        f"✅ Nyertes: {wins}",
        f"❌ Vesztes: {losses}",
        f"⏳ Függő/nem kiértékelt: {pending}",
        f"🎯 Találati arány (csak eldöntött): {hit_rate:.1f}%",
        "",
        "🏆 ROI (csak ahol van odds):",
        f"💎 KIEMELT: profit {hl_profit:,} Ft | tét {hl_stake:,} Ft | ROI {roi_pct(hl_profit, hl_stake):.1f}%".replace(",", " "),
        f"📌 NEM KIEMELT: profit {nh_profit:,} Ft | tét {nh_stake:,} Ft | ROI {roi_pct(nh_profit, nh_stake):.1f}%".replace(",", " "),
        "",
        "📌 Hit rate liga szerint (csak eldöntött):",
    ]

    # top ligák (min 2 tipp)
    league_items = []
    for lg, wl in by_league.items():
        n = wl["w"] + wl["l"]
        if n < int(os.getenv("TIPPMIX_RECAP_MIN_LEAGUE_N", "2")):
            continue
        hr = wl["w"] / n * 100.0
        league_items.append((n, hr, lg, wl["w"], wl["l"]))
    league_items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for n, hr, lg, w, l in league_items[: int(os.getenv("TIPPMIX_RECAP_TOP_LEAGUES", "12"))]:
        msg_lines.append(f"• {lg}: {w}-{l} ({hr:.0f}%)")

    msg_lines.append("")
    msg_lines.append("🎲 Hit rate odds sáv szerint (csak ahol van odds):")
    band_items = []
    for b, wl in by_band.items():
        n = wl["w"] + wl["l"]
        if n < int(os.getenv("TIPPMIX_RECAP_MIN_BAND_N", "2")):
            continue
        hr = wl["w"] / n * 100.0
        band_items.append((n, hr, b, wl["w"], wl["l"]))
    band_items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for n, hr, b, w, l in band_items:
        msg_lines.append(f"• {b}: {w}-{l} ({hr:.0f}%)")

    recap_text = "\n".join(msg_lines)

    if vip_chat_id:
        send_telegram_message(telegram_token, vip_chat_id, recap_text, "VIP_RECAP")
    if public_chat_id and os.getenv("TIPPMIX_RECAP_SEND_PUBLIC", "0") == "1":
        send_telegram_message(telegram_token, public_chat_id, recap_text, "PUBLIC_RECAP")


if __name__ == "__main__":
    main()
