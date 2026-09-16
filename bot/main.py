import os
import json
import time
import datetime
from typing import Any, Dict, Tuple, List, Optional

import requests
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
load_dotenv()

from bot.matches import fetch_matches_for_today
from bot.poisson_engine import generate_poisson_tips
from bot.providers.multi_sport import fetch_multi_sport_matches
from bot.telegram_marketing import (
    format_marketing_vip,
    format_marketing_free,
    format_alert_message,
    create_inline_buttons,
)
from bot.api_keys import resolve_sports_provider
from bot.storage.sqlite_store import insert_run, insert_bets, insert_fixtures
from bot.combo_builder import build_marketing_combos

# ── ÚJ modulok: minőség szűrés, meccs pontozás, torna detektálás, tanulás ──
from bot.filters import apply_quality_filters, get_filter_stats, apply_tiered_score_filter
from bot.match_scoring import score_and_filter
from bot.tournament_detector import enrich_with_tournament_info, sort_by_tournament_priority
from bot.match_learner import apply_learning_scores, get_avoid_leagues
from bot.storage.stats import dynamic_block_leagues, overall_hitrate

MARKETING_MIN_ODDS = 1.15
MARKETING_MAX_ODDS_FREE = 2.00
MARKETING_MAX_ODDS_VIP = 2.10
MARKETING_MIN_CONF_FREE = 3.8
MARKETING_MIN_CONF_VIP = 3.6
HIGH_RISK_TOKEN = "magas"


# -----------------------------
# Simple file logger (before/after send)
# -----------------------------

def _utc_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def log_event(event: Dict[str, Any]) -> None:
    _ensure_dir("logs")
    event = dict(event or {})
    event.setdefault("ts_utc", _utc_iso())
    try:
        with open("logs/send_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


# -----------------------------
# Telegram utils
# -----------------------------

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


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    label: str,
    meta: Optional[Dict[str, Any]] = None,
    inline_buttons: Optional[List[List[Dict[str, str]]]] = None,
) -> Tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split_telegram(text)

    log_event({
        "event": "telegram_send_start",
        "label": label,
        "chat_id": chat_id,
        "parts": len(parts),
        "meta": meta or {},
    })

    print(f"\n[{label}] Telegram küldés indul... üzenet részek: {len(parts)}")

    for idx, part in enumerate(parts, start=1):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        
        # Add inline buttons to the LAST part only
        if inline_buttons and idx == len(parts):
            payload["reply_markup"] = {
                "inline_keyboard": inline_buttons
            }

        print(f"[{label}] Part {idx}/{len(parts)} sendMessage...")
        try:
            resp = requests.post(url, json=payload, timeout=25)
        except Exception as e:
            err = f"Requests hiba: {repr(e)}"
            print(f"[{label}] {err}")
            log_event({
                "event": "telegram_send_error",
                "label": label,
                "chat_id": chat_id,
                "part": idx,
                "error": err,
                "meta": meta or {},
            })
            return False, err

        print(f"[{label}] HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            err = f"HTTP {resp.status_code}: {resp.text}"
            log_event({
                "event": "telegram_send_error",
                "label": label,
                "chat_id": chat_id,
                "part": idx,
                "error": err,
                "meta": meta or {},
            })
            return False, err

        try:
            data = resp.json()
        except Exception as e:
            err = f"JSON parse hiba: {repr(e)}"
            log_event({
                "event": "telegram_send_error",
                "label": label,
                "chat_id": chat_id,
                "part": idx,
                "error": err,
                "meta": meta or {},
            })
            return False, err

        if not data.get("ok"):
            err = f"Telegram API error: {data}"
            log_event({
                "event": "telegram_send_error",
                "label": label,
                "chat_id": chat_id,
                "part": idx,
                "error": err,
                "meta": meta or {},
            })
            return False, err

    print(f"[{label}] Üzenet(ek) sikeresen elküldve.")
    log_event({
        "event": "telegram_send_ok",
        "label": label,
        "chat_id": chat_id,
        "parts": len(parts),
        "meta": meta or {},
    })
    return True, ""


# -----------------------------
# Slot filtering
# -----------------------------

def _extract_kickoff_hour(match: Dict[str, Any]) -> Optional[int]:
    dt = match.get("kickoff_local") or match.get("kickoff") or match.get("datetime") or match.get("date")
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        return dt.hour
    if isinstance(dt, str):
        s = dt.strip()
        try:
            parsed = datetime.datetime.fromisoformat(s)
            return parsed.hour
        except Exception:
            pass
        try:
            return int(s.split("T")[1][:2])
        except Exception:
            return None
    return None


def _filter_matches_for_slot(matches: List[Dict[str, Any]], slot: str) -> List[Dict[str, Any]]:
    """Safety slot filter.

    Supports: DAY / EVENING / ALL.
    Uses the same configurable hours as bot.matches.

    Env:
      - TIPPMIX_DAY_START_HOUR (default 9)
      - TIPPMIX_DAY_END_HOUR_EXCL (default 19)
      - TIPPMIX_EVENING_START_HOUR (default 19)
      - TIPPMIX_EVENING_END_HOUR_INCL (default 23)

    If filtering yields fewer matches than (min_vip+min_free), returns the original list.
    """

    slot = (slot or "DAY").upper()
    if slot in ("ALL", "FULL", "WHOLE"):
        return matches

    day_start = int(os.getenv("TIPPMIX_DAY_START_HOUR", "9"))
    day_end_excl = int(os.getenv("TIPPMIX_DAY_END_HOUR_EXCL", "19"))
    eve_start = int(os.getenv("TIPPMIX_EVENING_START_HOUR", str(day_end_excl)))
    eve_end_incl = int(os.getenv("TIPPMIX_EVENING_END_HOUR_INCL", "23"))

    filtered: List[Dict[str, Any]] = []
    for m in matches:
        h = _extract_kickoff_hour(m)
        if h is None:
            filtered.append(m)
            continue

        if slot == "DAY":
            if day_start <= h < day_end_excl:
                filtered.append(m)
        else:
            if eve_start <= h <= eve_end_incl:
                filtered.append(m)

    min_vip = int(os.getenv("TIPPMIX_MIN_VIP", "6"))
    min_free = int(os.getenv("TIPPMIX_MIN_FREE", "3"))
    min_need = min_vip + min_free

    if len(filtered) < min_need:
        print(f"[DEBUG] Slot filter left too few matches ({len(filtered)} < {min_need}). Returning ALL.")
        return matches

    print(f"[DEBUG] Slot filtered matches slot={slot}: {len(filtered)} (orig: {len(matches)})")
    return filtered


def _match_key(m: Dict[str, Any]) -> str:
    fid = m.get("fixture_id")
    if fid:
        return f"fid:{fid}"
    home = (m.get("home_team") or "").strip()
    away = (m.get("away_team") or "").strip()
    ko = (m.get("kickoff_local") or m.get("kickoff") or "").strip()
    return f"key:{home}__{away}__{ko}"


# -----------------------------
# Grok (xAI) review (optional)
# -----------------------------

def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass

    try:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start:end + 1])
    except Exception:
        return None

    return None


# (A korábbi Grok/xAI VIP-audit funkció eltávolítva – nincs fizetős AI API a kódban.)


# -----------------------------
# Enrichment for JSON bets (backtest/recap-ready)
# -----------------------------

def _odds_pick_from_1x2(tip: str, odds: Dict[str, Any]) -> Optional[float]:
    if not isinstance(odds, dict):
        return None
    mapping = {"Hazai győzelem": "1", "Döntetlen": "X", "Vendég győzelem": "2"}
    k = mapping.get(tip)
    if not k:
        return None
    try:
        v = odds.get(k)
        return float(v) if v is not None else None
    except Exception:
        return None


def _outcome_key_for_tip(tip: str) -> Optional[str]:
    mapping = {"Hazai győzelem": "1", "Döntetlen": "X", "Vendég győzelem": "2"}
    return mapping.get(tip)


def _enrich_bets_for_storage(
    bets: List[Dict[str, Any]],
    slot_matches: List[Dict[str, Any]],
    run_date: str,
    slot: str,
) -> List[Dict[str, Any]]:
    by_fid = {int(m["fixture_id"]): m for m in slot_matches if m.get("fixture_id") is not None}

    out: List[Dict[str, Any]] = []
    for b in (bets or []):
        bb = dict(b)
        fid = bb.get("fixture_id")
        try:
            fid_int = int(fid) if fid is not None else None
        except Exception:
            fid_int = None

        m = by_fid.get(fid_int) if fid_int is not None else None

        tip = bb.get("tip") or bb.get("selection") or bb.get("pick")
        bb["tip"] = tip

        if m:
            bb["match_key"] = _match_key(m)
            bb["league_name"] = m.get("league_name")
            bb["country_name"] = m.get("country_name")
            bb["kickoff_local"] = m.get("kickoff_local")
            bb["home_team"] = m.get("home_team")
            bb["away_team"] = m.get("away_team")
            bb["odds_1x2"] = m.get("scraped_odds") or m.get("odds") or {}
            bb["odds_pick"] = _odds_pick_from_1x2(str(tip), bb["odds_1x2"])
            if bb["odds_pick"] is None:
                bb["odds_pick"] = _odds_pick_from_1x2(str(tip), m.get("odds") or {})
            outcome_key = _outcome_key_for_tip(str(tip))
            best_bookmakers = m.get("best_bookmakers") or {}
            bb["bookmaker"] = best_bookmakers.get(outcome_key) or ("Predicted" if m.get("used_predicted_odds") else "N/A")
        else:
            bb.setdefault("match_key", f"fid:{fid}" if fid is not None else None)
            bb.setdefault("odds_1x2", bb.get("odds_1x2") or {})

        bb["run_date"] = run_date
        bb["slot"] = slot

        out.append(bb)

    return out


# -----------------------------
# Safe fetch (RUN_DATE support)
# -----------------------------

def _fetch_matches(slot: str, date_obj: datetime.date) -> List[Dict[str, Any]]:
    try:
        return fetch_matches_for_today(slot=slot, date=date_obj.isoformat())  # type: ignore
    except TypeError:
        return fetch_matches_for_today(slot=slot)
    except Exception:
        raise


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    run_date_env = (os.getenv("RUN_DATE") or "").strip()
    today = datetime.date.fromisoformat(run_date_env) if run_date_env else datetime.date.today()
    run_date_str = today.isoformat()

    print(f"Meccsek lekérése erre a napra: {run_date_str}")

    slot = (os.getenv("TIPPMIX_SLOT") or "DAY").upper()
    print(f"Aktuális idősáv (TIPPMIX_SLOT): {slot}")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_chat_id = os.getenv("TELEGRAM_PUBLIC_CHAT_ID")
    vip_chat_id = os.getenv("TELEGRAM_VIP_CHAT_ID")
    en_chat_id = os.getenv("TELEGRAM_EN_CHAT_ID")

    print("\n=== TELEGRAM BEÁLLÍTÁSOK ===")
    print("TELEGRAM_BOT_TOKEN be van állítva:", bool(telegram_token))
    print("PUBLIC_CHAT_ID (használt) =", repr(public_chat_id))
    print("VIP_CHAT_ID    =", repr(vip_chat_id))
    print("EN_CHAT_ID     =", repr(en_chat_id))

    if not telegram_token:
        print("NINCS TELEGRAM_BOT_TOKEN - DRY-RUN mode (csak JSON/DB mentés).")
        # Not returning - allow bot to run and save to DB/JSON without Telegram send

    if not public_chat_id:
        print("[WARN] TELEGRAM_PUBLIC_CHAT_ID nincs beállítva! FREE üzenet nem fog kimenni.")
    if not vip_chat_id:
        print("[WARN] TELEGRAM_VIP_CHAT_ID nincs beállítva! VIP üzenet nem fog kimenni.")
    if not en_chat_id:
        print("[INFO] TELEGRAM_EN_CHAT_ID nincs beállítva! EN üzenet nem fog kimenni.")

    try:
        matches = _fetch_matches(slot=slot, date_obj=today)
        print(f"Talált meccsek száma (összes): {len(matches)}")
    except Exception as e:
        err = f"⚠️ SPORT API HIBA ⚠️\n\nNem tudtam meccseket lekérni.\n\nTechnikai info:\n{repr(e)}"
        print("Meccslekérés közben hiba:", repr(e))

        meta = {"slot": slot, "run_date": run_date_str, "stage": "fetch_matches"}
        if public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, err, f"PUBLIC_API_ERROR_{slot}", meta=meta)
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, err, f"VIP_API_ERROR_{slot}", meta=meta)
        return

    slot_matches = _filter_matches_for_slot(matches, slot)
    print(f"Idősávra szűrt meccsek száma: {len(slot_matches)}")
    
    # Multi-sport pool expansion (if football pool is small)
    enable_multi_sport = (os.getenv("TIPPMIX_ENABLE_MULTI_SPORT") or "1").strip() == "1"
    min_pool = int(os.getenv("TIPPMIX_MIN_POOL", "15"))
    
    if enable_multi_sport and len(slot_matches) < min_pool:
        print(f"[MultiSport] Foci pool kicsi ({len(slot_matches)}), bővítés kosár/kézi-vel...")
        slot_matches = fetch_multi_sport_matches(
            date_str=run_date_str,
            min_pool_size=min_pool,
            current_pool=slot_matches,
        )
        print(f"[MultiSport] Bővített pool: {len(slot_matches)} meccs")

    # Dynamic league blocking based on historical hitrate (prevents "kamu" leagues from polluting picks)
    if (os.getenv("TIPPMIX_DYNAMIC_BLOCK") or "1").strip() == "1":
        try:
            days = int(os.getenv("TIPPMIX_DYN_BLOCK_DAYS") or "60")
        except Exception:
            days = 60
        try:
            min_samples = int(os.getenv("TIPPMIX_DYN_BLOCK_MIN_SAMPLES") or "25")
        except Exception:
            min_samples = 25
        try:
            max_hitrate = float(os.getenv("TIPPMIX_DYN_BLOCK_MAX_HITRATE") or "0.48")
        except Exception:
            max_hitrate = 0.48

        bad_leagues = dynamic_block_leagues(days=days, min_samples=min_samples, max_hitrate=max_hitrate, tier="VIP")
        bad_set = {b.lower().strip() for b in bad_leagues}

        if bad_set:
            before = len(slot_matches)
            slot_matches = [m for m in slot_matches if (str(m.get("league_name") or "").lower().strip() not in bad_set)]
            after = len(slot_matches)
            if before != after:
                print(f"[DYN_BLOCK] Blocked leagues: {len(bad_leagues)} | matches {before} -> {after}")

    # ── ÚJ PIPELINE: minőség szűrés → torna detektálás → elemzésen alapú pontozás ──

    # 1. Minőség szűrés: csak top/közepes ligák, kizárja az egzotikusokat
    enable_quality_filter = (os.getenv("TIPPMIX_QUALITY_FILTER") or "1").strip() == "1"
    if enable_quality_filter:
        before_qf = len(slot_matches)
        slot_matches = apply_quality_filters(slot_matches, allow_odds_missing=True)
        after_qf = len(slot_matches)
        stats = get_filter_stats(slot_matches)
        print(
            f"[QualityFilter] {after_qf}/{before_qf} meccs maradt | "
            f"tier1={stats['tier1']} tier2={stats['tier2']} tier3={stats['tier3']} "
            f"ismeretlen={stats['unknown']}"
        )

    # 2. Torna detektálás (VB/EB/CL stb.) — extra prioritás + alacsonyabb küszöb
    slot_matches = enrich_with_tournament_info(slot_matches)
    tournament_count = sum(1 for m in slot_matches if m.get("is_tournament"))
    if tournament_count:
        print(f"[TournamentDetector] {tournament_count} torna meccs detektálva")

    # 3. Elemzésen alapú meccs pontozás (xG, forma, liga, torna)
    enable_scoring = (os.getenv("TIPPMIX_MATCH_SCORING") or "1").strip() == "1"
    if enable_scoring:
        # Tiered küszöböt külön alkalmazzuk (t1/t2/t3), ezért itt az alap szűrés lehet laza.
        base_min_score = float(os.getenv("TIPPMIX_BASE_MIN_SCORE", "0.0"))
        slot_matches = score_and_filter(slot_matches, min_score=base_min_score)
        slot_matches = apply_tiered_score_filter(slot_matches)
        avg_score = (
            sum(m.get("match_score", 0) for m in slot_matches) / len(slot_matches)
            if slot_matches else 0
        )
        print(f"[MatchScoring] Pool: {len(slot_matches)} meccs | átlag pontszám: {avg_score:.1f}/10")

    # 4. Tanulás alapú pontszám módosítás (liga megbízhatóság)
    enable_learning_scores = (os.getenv("TIPPMIX_LEARNING_SCORES") or "1").strip() == "1"
    if enable_learning_scores:
        slot_matches = apply_learning_scores(slot_matches)

    # 4b. Kerülendő ligák kiszűrése — ha egy liga historikusan alacsony
    # találati aránnyal teljesített (saját adatbázis alapján), kizárjuk.
    enable_avoid_leagues = (os.getenv("TIPPMIX_AVOID_BAD_LEAGUES") or "1").strip() == "1"
    if enable_avoid_leagues:
        try:
            avoid = get_avoid_leagues(
                days=int(os.getenv("TIPPMIX_AVOID_LEAGUES_DAYS", "60")),
                max_hitrate=float(os.getenv("TIPPMIX_AVOID_LEAGUES_MAX_HITRATE", "0.45")),
                min_samples=int(os.getenv("TIPPMIX_AVOID_LEAGUES_MIN_SAMPLES", "5")),
            )
            if avoid:
                before = len(slot_matches)
                slot_matches = [m for m in slot_matches if (m.get("league_name") or "").strip() not in avoid]
                after = len(slot_matches)
                print(f"[Learning] Kerülendő ligák ({len(avoid)} db) miatt kiszűrve: {before}->{after}")
        except Exception as e:
            print(f"[Learning] get_avoid_leagues hiba (ignorálva): {e}")

    # 5. Rendezés: torna meccsek előre, majd pontszám szerinti sorrend
    slot_matches = sort_by_tournament_priority(slot_matches)

    print(f"[Pipeline] Végleges meccs pool: {len(slot_matches)} meccs")

    # Engine: kizárólag a szabad, statisztikai Poisson-modell (Dixon-Coles
    # stílusú, hazai/vendég bontással, saját adatbázisból tanulva).
    # Nincs fizetős AI API a kódban.
    print("[ENGINE] Poisson (statisztikai modell, saját adatbázisból tanul - nincs fizetős API)")
    tips_data = generate_poisson_tips(slot_matches)

    # ALERT mode: send only very strong PRO picks (VIP + EN only).
    alert_only = (os.getenv("TIPPMIX_ALERT_ONLY") or "0").strip() == "1"
    if alert_only:
        def _is_alert_pick(b: Dict[str, Any]) -> bool:
            try:
                conf = float(b.get("confidence") or 0)
            except Exception:
                conf = 0
            try:
                odds = float(b.get("odds_pick") or b.get("odds") or 0)
            except Exception:
                odds = 0
            risk = (b.get("risk_level") or "").lower()
            shelf = (b.get("shelf") or b.get("pick_shelf") or "").upper()

            try:
                conf_thr = float(os.getenv("TIPPMIX_ALERT_CONF_MIN") or "4.2")
            except Exception:
                conf_thr = 4.2
            try:
                o_min = float(os.getenv("TIPPMIX_ALERT_ODDS_MIN") or "1.35")
            except Exception:
                o_min = 1.35
            try:
                o_max = float(os.getenv("TIPPMIX_ALERT_ODDS_MAX") or "1.90")
            except Exception:
                o_max = 1.90

            if shelf != "PRO":
                return False
            if "alacsony" not in risk:
                return False
            if conf < conf_thr:
                return False
            # If we have odds, enforce the odds window; if odds are missing, allow the pick.
            if odds and odds > 1.01:
                if odds < o_min or odds > o_max:
                    return False
            return True

        vip_bets = tips_data.get("vip_bets") or []
        vip_alerts = [b for b in vip_bets if _is_alert_pick(b)]

        # Dedup across runs
        import hashlib

        state_path = os.path.join("data", "alert_state.json")
        try:
            st = json.load(open(state_path, "r", encoding="utf-8")) if os.path.exists(state_path) else {}
        except Exception:
            st = {}
        sent = set(st.get("sent") or [])

        def _key(b: Dict[str, Any]) -> str:
            raw = f"{b.get('fixture_id')}|{b.get('tip')}|{b.get('odds_pick')}"
            return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

        new_alerts = []
        for b in vip_alerts:
            k = _key(b)
            if k in sent:
                continue
            new_alerts.append(b)
            sent.add(k)

        try:
            mx = int(os.getenv("TIPPMIX_ALERT_MAX_PER_RUN") or "6")
        except Exception:
            mx = 6
        new_alerts = new_alerts[: max(0, mx)]

        if not new_alerts:
            print("[ALERT] No new PRO picks; skipping send.")
            return

        # Build a short VIP-only alert message
        lines_hu = [
            "🚨🏆 VIP PRO RIASZTAS – KIMAGASLO LEHETOSEG",
            f"📅 {today.strftime('%Y.%m.%d.')}",
            f"🔔 Uj PRO tippek: {len(new_alerts)}",
            "",
        ]
        lines_en = [
            "🚨🏆 VIP PRO ALERT – TOP OPPORTUNITY",
            f"📅 {today.strftime('%Y.%m.%d.')}",
            f"🔔 New PRO picks: {len(new_alerts)}",
            "",
        ]

        for i, b in enumerate(new_alerts, 1):
            label = b.get("match") or f"fixture_id={b.get('fixture_id')}"
            tip = b.get("tip")
            odds = b.get("odds_pick")
            conf = b.get("confidence")
            lines_hu.append(f"{i}. 🏆 {label}\n🎯 Tipp: {tip} | 📊 Odds: {odds} | 💡 Bizalom: {conf}/5")
            lines_en.append(f"{i}. 🏆 {label}\nPick: {tip} | Odds: {odds} | Confidence: {conf}/5")

        # persist alert dedup state
        try:
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"sent": sorted(sent)[-2000:]}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # schedule a recap in N hours
        try:
            delay_h = float(os.getenv("TIPPMIX_ALERT_RECAP_DELAY_HOURS") or "3")
        except Exception:
            delay_h = 3.0
        due = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=delay_h)).isoformat()

        pending_path = os.path.join("data", "pending_alert_recaps.json")
        try:
            pend = json.load(open(pending_path, "r", encoding="utf-8")) if os.path.exists(pending_path) else {"items": []}
        except Exception:
            pend = {"items": []}
        if not isinstance(pend, dict):
            pend = {"items": []}
        items = pend.get("items") or []
        if not isinstance(items, list):
            items = []

        items.append({
            "created_ts_utc": datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat(),
            "due_ts_utc": due,
            "bets": new_alerts,
        })
        pend["items"] = items[-50:]
        try:
            os.makedirs(os.path.dirname(pending_path), exist_ok=True)
            with open(pending_path, "w", encoding="utf-8") as f:
                json.dump(pend, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception:
            pass

        # save to SQLite as a run
        # NOTE: sqlite_store helpers are imported at module level; do NOT re-import here
        # otherwise Python treats them as function-locals and later references can crash.
        try:
            provider = None
            try:
                provider = resolve_sports_provider()
            except Exception:
                provider = None
            run_id = insert_run(
                run_date=run_date_str,
                slot="ALERT",
                provider=provider,
                matches_total=len(matches),
                matches_slot=len(slot_matches),
                vip_count=len(new_alerts),
                public_count=0,
                meta={**base_meta, "alert_only": True, "due_ts_utc": due},
            )
            insert_fixtures(run_id, slot_matches)
            insert_bets(run_id, "VIP", new_alerts)
        except Exception:
            pass

        # force send only VIP + EN
        if vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, "\n\n".join(lines_hu), f"VIP_ALERT_{slot}", meta=base_meta)
        if en_chat_id:
            send_telegram_message(telegram_token, en_chat_id, "\n\n".join(lines_en), f"EN_VIP_ALERT_{slot}", meta={**base_meta, "lang": "en"})

        return

    suffix = "day" if slot == "DAY" else "evening"
    # (A korábbi Grok/xAI VIP-audit és újragenerálási kör eltávolítva – nincs fizetős AI API a kódban.
    #  A Poisson-modell egy menetben adja a végleges tippeket.)

    public_text = tips_data.get("telegram_public_text") or "⚠️ Hiba a FREE tippek generálásánál."
    vip_text = tips_data.get("telegram_vip_text") or "⚠️ Hiba a VIP tippek generálásánál."

    # Transparency footer: show recent real hitrate (anti-kamu)
    if (os.getenv("TIPPMIX_SHOW_PERF_FOOTER") or "1").strip() == "1":
        try:
            days = int(os.getenv("TIPPMIX_PERF_DAYS") or "30")
        except Exception:
            days = 30
        perf_vip = overall_hitrate(days=days, tier="VIP")
        if perf_vip and float(perf_vip.get("decided", 0)) >= 10:
            hit = float(perf_vip.get("hitrate", 0)) * 100.0
            decided = int(perf_vip.get("decided", 0))
            vip_text = (vip_text or "").rstrip() + f"\n\n<i>Transzparencia: utolsó {days} nap VIP találati arány (eldöntött, DB alapján): {hit:.1f}% ({decided} tipp)</i>"

    public_text_en = tips_data.get("telegram_public_text_en")
    vip_text_en = tips_data.get("telegram_vip_text_en")

    public_bets = tips_data.get("public_bets", []) or []
    vip_bets = tips_data.get("vip_bets", []) or []

    public_bets_enriched = _enrich_bets_for_storage(public_bets, slot_matches, run_date_str, slot)
    vip_bets_enriched = _enrich_bets_for_storage(vip_bets, slot_matches, run_date_str, slot)

    public_json_path = f"public_bets_{suffix}.json"
    vip_json_path = f"vip_bets_{suffix}.json"

    public_meta_path = f"public_bets_{suffix}_meta.json"
    vip_meta_path = f"vip_bets_{suffix}_meta.json"

    try:
        with open(public_json_path, "w", encoding="utf-8") as f:
            json.dump(public_bets_enriched, f, ensure_ascii=False, indent=2)
        with open(vip_json_path, "w", encoding="utf-8") as f:
            json.dump(vip_bets_enriched, f, ensure_ascii=False, indent=2)

        public_meta = {
            "run_date": run_date_str,
            "slot": slot,
            "bets_count": len(public_bets_enriched),
            "source": "poisson",
        }
        vip_meta = {
            "run_date": run_date_str,
            "slot": slot,
            "bets_count": len(vip_bets_enriched),
            "source": "poisson",
        }

        with open(public_meta_path, "w", encoding="utf-8") as f:
            json.dump(public_meta, f, ensure_ascii=False, indent=2)
        with open(vip_meta_path, "w", encoding="utf-8") as f:
            json.dump(vip_meta, f, ensure_ascii=False, indent=2)

        if (os.getenv("TIPPMIX_SAVE_DASHBOARD_JSON") or "1").strip() == "1":
            try:
                provider_name = resolve_sports_provider()
            except Exception:
                provider_name = None
            dashboard_data_dir = os.path.join("dashboard", "public", "data")
            _ensure_dir(dashboard_data_dir)
            with open(os.path.join(dashboard_data_dir, "latest_public_bets.json"), "w", encoding="utf-8") as f:
                json.dump(public_bets_enriched, f, ensure_ascii=False, indent=2)
            with open(os.path.join(dashboard_data_dir, "latest_vip_bets.json"), "w", encoding="utf-8") as f:
                json.dump(vip_bets_enriched, f, ensure_ascii=False, indent=2)
            with open(os.path.join(dashboard_data_dir, "latest_run_meta.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "run_date": run_date_str,
                        "slot": slot,
                        "provider": provider_name,
                        "public_bets_count": len(public_bets_enriched),
                        "vip_bets_count": len(vip_bets_enriched),
                        "updated_ts_utc": _utc_iso(),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        print(f"Napi tippek elmentve: {public_json_path}, {vip_json_path}")
        print(f"Meta elmentve: {public_meta_path}, {vip_meta_path}")

    except Exception as e:
        print("Nem sikerült JSON-ba menteni:", repr(e))

    base_meta = {
        "slot": slot,
        "run_date": run_date_str,
        "public_bets_count": len(public_bets_enriched),
        "vip_bets_count": len(vip_bets_enriched),
    }

    # --- Persist to SQLite (optional but default-on) ---
    try:
        provider = None
        try:
            provider = resolve_sports_provider()
        except Exception:
            provider = None

        run_id = insert_run(
            run_date=run_date_str,
            slot=slot,
            provider=provider,
            matches_total=len(matches),
            matches_slot=len(slot_matches),
            vip_count=len(vip_bets_enriched),
            public_count=len(public_bets_enriched),
            meta=base_meta,
        )
        # store the match pool we used (fixtures snapshot)
        insert_fixtures(run_id, slot_matches)

        insert_bets(run_id, "FREE", public_bets_enriched)
        insert_bets(run_id, "VIP", vip_bets_enriched)
        print(f"[DB] Saved run_id={run_id} + fixtures + bets to SQLite.")
    except Exception as e:
        print("[DB] SQLite save failed:", repr(e))

    send_public = (os.getenv("TIPPMIX_SEND_PUBLIC") or "1").strip() != "0"
    send_vip = (os.getenv("TIPPMIX_SEND_VIP") or "1").strip() != "0"
    send_en = (os.getenv("TIPPMIX_SEND_EN") or "1").strip() != "0"
    
    # Marketing format with inline buttons (optional; default ON for cleaner messages)
    use_marketing = (os.getenv("TIPPMIX_USE_MARKETING_FORMAT") or "1").strip() == "1"

    def _safe_float(x: Any) -> float:
        try:
            return float(x)
        except Exception:
            return 0.0

    def _sensible_marketing_tips(bets: List[Dict[str, Any]], tier: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        tier_u = (tier or "").upper()
        max_odds = MARKETING_MAX_ODDS_FREE if tier_u == "FREE" else MARKETING_MAX_ODDS_VIP
        min_conf = MARKETING_MIN_CONF_FREE if tier_u == "FREE" else MARKETING_MIN_CONF_VIP
        for b in bets or []:
            risk = str(b.get("risk_level") or "").lower()
            shelf = str(b.get("shelf") or "").upper()
            conf = _safe_float(b.get("confidence"))
            # Odds priority: enriched picked-odds → source odds field → model estimate fallback.
            odds = _safe_float(b.get("odds_pick") or b.get("odds") or b.get("odds_estimate"))

            if HIGH_RISK_TOKEN in risk or shelf == "BOLD":
                continue
            if odds > 0 and (odds < MARKETING_MIN_ODDS or odds > max_odds):
                continue
            if conf < min_conf:
                continue

            out.append(b)
        return out

    def _fallback_marketing_tips(bets: List[Dict[str, Any]], tier: str) -> List[Dict[str, Any]]:
        tier_u = (tier or "").upper()
        base: List[Dict[str, Any]] = []
        non_bold: List[Dict[str, Any]] = []
        for b in bets or []:
            if HIGH_RISK_TOKEN in str(b.get("risk_level") or "").lower():
                continue
            base.append(b)
            if str(b.get("shelf") or "").upper() != "BOLD":
                non_bold.append(b)
        if tier_u == "VIP":
            # Last-resort fallback: if everything is BOLD, still send best non-high-risk picks.
            base = non_bold if non_bold else base
        if not base:
            return []
        return sorted(base, key=lambda b: _safe_float(b.get("confidence")), reverse=True)

    if use_marketing and vip_bets_enriched and public_bets_enriched:
        # Generate marketing-optimized messages with inline buttons
        # ONLY if we have actual bets (not empty)
        date_today = datetime.date.today().strftime("%Y.%m.%d.")
        combos = build_marketing_combos(vip_bets_enriched[:10], public_bets_enriched[:8])
        vip_send = _sensible_marketing_tips(vip_bets_enriched, "VIP")
        free_send = _sensible_marketing_tips(public_bets_enriched, "FREE")
        if not vip_send:
            vip_send = _fallback_marketing_tips(vip_bets_enriched, "VIP")
        if not free_send:
            free_send = _fallback_marketing_tips(public_bets_enriched, "FREE")
        
        # Get stats for VIP header (if available)
        try:
            from bot.roi_tracker import ROITracker
            tracker = ROITracker()
            stats_7d = tracker.get_stats(days=7, tier="VIP")
        except Exception:
            stats_7d = None
        
        if send_vip and vip_chat_id:
            vip_text_marketing, vip_buttons = format_marketing_vip(
                tips=vip_send[:8],
                combos=combos.get("vip") or [],
                date_str=date_today,
                stats=stats_7d
            )
            send_telegram_message(telegram_token, vip_chat_id, vip_text_marketing, f"VIP_{slot}", meta=base_meta, inline_buttons=vip_buttons)
        
        if send_public and public_chat_id:
            free_text_marketing, free_buttons = format_marketing_free(
                tips=free_send[:3],
                combos=combos.get("free") or [],
                date_str=date_today
            )
            send_telegram_message(telegram_token, public_chat_id, free_text_marketing, f"PUBLIC_{slot}", meta=base_meta, inline_buttons=free_buttons)
    
    else:
        # Fallback to original format + add inline buttons
        buttons = create_inline_buttons() if use_marketing else None
        
        if send_public and public_chat_id:
            send_telegram_message(telegram_token, public_chat_id, public_text, f"PUBLIC_{slot}", meta=base_meta, inline_buttons=buttons)
        if send_vip and vip_chat_id:
            send_telegram_message(telegram_token, vip_chat_id, vip_text, f"VIP_{slot}", meta=base_meta, inline_buttons=buttons)

    # EN broadcast (optional)
    # Default: VIP-only for the EN channel/group.
    en_include_free = (os.getenv("TELEGRAM_EN_INCLUDE_FREE") or "").strip() == "1"
    if send_en and en_chat_id and (vip_text_en or (en_include_free and public_text_en)):
        meta_en = dict(base_meta)
        meta_en["lang"] = "en"
        if en_include_free and public_text_en:
            send_telegram_message(telegram_token, en_chat_id, public_text_en, f"EN_PUBLIC_{slot}", meta=meta_en)
        if vip_text_en:
            send_telegram_message(telegram_token, en_chat_id, vip_text_en, f"EN_VIP_{slot}", meta=meta_en)

    # Opcionális: hang-összefoglaló a legjobb VIP tippekről (ingyenes gTTS,
    # nincs fizetős voice API). Kapcsold be: TIPPMIX_SEND_VOICE_SUMMARY=1
    if (os.getenv("TIPPMIX_SEND_VOICE_SUMMARY") or "0").strip() == "1":
        try:
            from bot.voice_tts import send_voice_summary_telegram

            voice_target_chat = vip_chat_id or public_chat_id
            if telegram_token and voice_target_chat and vip_bets_enriched:
                sent = send_voice_summary_telegram(
                    vip_bets_enriched,
                    bot_token=telegram_token,
                    chat_id=voice_target_chat,
                    max_tips=int(os.getenv("TIPPMIX_VOICE_MAX_TIPS", "5")),
                )
                print(f"[Voice] Hang-összefoglaló elküldve: {sent}")
        except Exception as e:
            print(f"[Voice] Hang-összefoglaló hiba (ignorálva, a szöveges tippek elmentek): {e}")


if __name__ == "__main__":
    main()
