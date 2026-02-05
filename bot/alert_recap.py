import datetime
import json
import os
from typing import Any, Dict, List, Tuple

from bot.results import evaluate_bets


PENDING_PATH = os.getenv("TIPPMIX_ALERT_RECAP_STATE", os.path.join("data", "pending_alert_recaps.json"))


def _utc_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()


def _load() -> Dict[str, Any]:
    if not os.path.exists(PENDING_PATH):
        return {"items": []}
    try:
        with open(PENDING_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            return d
    except Exception:
        pass
    return {"items": []}


def _save(d: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PENDING_PATH), exist_ok=True)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _parse_ts(s: str) -> datetime.datetime:
    # expects isoformat with tz
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _format(summary: Dict[str, Any], title_hu: str, title_en: str) -> Tuple[str, str]:
    decided = int(summary.get("win", 0)) + int(summary.get("lose", 0))
    hitrate = (100.0 * float(summary.get("win", 0)) / decided) if decided else 0.0

    lines_hu: List[str] = []
    lines_hu.append(title_hu)
    lines_hu.append(f"✅ Nyert: {summary.get('win', 0)} | ❌ Bukó: {summary.get('lose', 0)} | ⏳ Függő: {summary.get('pending', 0)} | ⁉ Ismeretlen: {summary.get('unknown', 0)}")
    lines_hu.append(f"🎯 Találati arány (eldöntött): {hitrate:.1f}%")

    lines_en: List[str] = []
    lines_en.append(title_en)
    lines_en.append(f"✅ Win: {summary.get('win', 0)} | ❌ Lose: {summary.get('lose', 0)} | ⏳ Pending: {summary.get('pending', 0)} | ⁉ Unknown: {summary.get('unknown', 0)}")
    lines_en.append(f"🎯 Hit rate (decided): {hitrate:.1f}%")

    for i, d in enumerate(summary.get("details") or [], 1):
        match = d.get("match") or ""
        tip = d.get("tip") or ""
        res = d.get("result") or "unknown"
        score = d.get("score") or ""
        status = d.get("status") or ""

        if res == "win":
            hu_res = f"✅ Nyert ({score})" if score else "✅ Nyert"
            en_res = f"✅ Win ({score})" if score else "✅ Win"
        elif res == "lose":
            hu_res = f"❌ Bukó ({score})" if score else "❌ Bukó"
            en_res = f"❌ Lose ({score})" if score else "❌ Lose"
        elif res == "pending":
            hu_res = f"⏳ Függő ({status}) {score}".strip()
            en_res = f"⏳ Pending ({status}) {score}".strip()
        else:
            hu_res = "⁉ Nem értékelhető"
            en_res = "⁉ Unknown"

        lines_hu.append(f"{i}. {match}\nTipp: {tip}\nEredmény: {hu_res}")
        lines_en.append(f"{i}. {match}\nPick: {tip}\nResult: {en_res}")

    return "\n\n".join(lines_hu), "\n\n".join(lines_en)


def main() -> None:
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    st = _load()
    items = st.get("items") or []

    remaining: List[Dict[str, Any]] = []

    # Telegram config
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    vip_chat = (os.getenv("TELEGRAM_VIP_CHAT_ID") or "").strip()
    en_chat = (os.getenv("TELEGRAM_EN_CHAT_ID") or "").strip()

    def send(chat_id: str, text: str):
        import requests

        if not (token and chat_id and text):
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=25)

    for it in items:
        due = it.get("due_ts_utc")
        if not due:
            remaining.append(it)
            continue
        try:
            due_dt = _parse_ts(str(due))
        except Exception:
            remaining.append(it)
            continue

        if due_dt > now:
            remaining.append(it)
            continue

        bets = it.get("bets") or []
        if not isinstance(bets, list) or not bets:
            continue

        summary = evaluate_bets(bets)
        title_hu = "📌 VIP PRO – RIASZTÁS RECAP"
        title_en = "📌 VIP PRO – ALERT RECAP"
        txt_hu, txt_en = _format(summary, title_hu, title_en)

        send(vip_chat, txt_hu)
        send(en_chat, txt_en)

    st["items"] = remaining
    st["updated_ts_utc"] = _utc_iso()
    _save(st)


if __name__ == "__main__":
    main()
