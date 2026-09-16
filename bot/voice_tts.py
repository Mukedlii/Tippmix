"""
bot/voice_tts.py

Hang-összefoglaló a napi VIP tippekről, Telegram hangüzenetként küldve.

Kizárólag ingyenes eszközöket használ:
  - gTTS (Google Translate TTS - ingyenes, nincs API kulcs)
  - Telegram Bot API (sendAudio) - ugyanaz a bot token, ami a szöveges
    üzenetekhez is megy

Nincs fizetős TTS/voice API a kódban (nincs ElevenLabs, OpenAI TTS, stb.)
"""

import os
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def build_voice_summary_text(vip_bets: List[Dict[str, Any]], max_tips: int = 5) -> str:
    """Rövid, magyar nyelvű, felolvasásra alkalmas szöveg a legjobb tippekről."""
    if not vip_bets:
        return "Ma nincs elég megbízható meccs a VIP tippekhez."

    lines = ["Szia! Íme a mai legjobb tippek a Szelvénykirály botól."]

    top = vip_bets[:max_tips]
    for i, bet in enumerate(top, start=1):
        home = bet.get("home_team") or bet.get("home") or ""
        away = bet.get("away_team") or bet.get("away") or ""
        pick = bet.get("pick") or bet.get("tip") or ""
        prob = bet.get("p") or bet.get("probability")

        conf = ""
        if isinstance(prob, (int, float)) and prob > 0:
            conf = f", {round(prob * 100)} százalék esély"

        lines.append(f"{i}. tipp: {home} kontra {away}. Javasolt tipp: {pick}{conf}.")

    lines.append("Sok sikert a mai tippekhez! Hajrá!")
    return " ".join(lines)


def synthesize_mp3(text: str, out_path: str, lang: str = "hu") -> bool:
    """Szöveg -> mp3 fájl, ingyenes gTTS-szel (nincs API kulcs).

    Visszatér True-val sikeres generálás esetén, False-szal ha a gTTS
    csomag nincs telepítve, vagy hiba történt (pl. nincs internet).
    """
    try:
        from gtts import gTTS  # type: ignore
    except ImportError:
        log.warning("[voice_tts] gTTS nincs telepítve (pip install gTTS) - hangüzenet kihagyva.")
        return False

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(out_path)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        log.warning(f"[voice_tts] gTTS generálási hiba: {e}")
        return False


def send_voice_summary_telegram(
    vip_bets: List[Dict[str, Any]],
    bot_token: str,
    chat_id: str,
    max_tips: int = 5,
    caption: Optional[str] = None,
) -> bool:
    """Legyártja a hang-összefoglalót és elküldi Telegram audio üzenetként.

    Csak a saját Telegram bot tokent és a meglévő ingyenes gTTS-t
    használja - nincs fizetős API.
    """
    import tempfile
    import requests

    text = build_voice_summary_text(vip_bets, max_tips=max_tips)

    with tempfile.TemporaryDirectory() as tmp_dir:
        mp3_path = os.path.join(tmp_dir, "tippek.mp3")
        ok = synthesize_mp3(text, mp3_path, lang="hu")
        if not ok:
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
        try:
            with open(mp3_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={
                        "chat_id": chat_id,
                        "title": "Napi tippek - hang összefoglaló",
                        "caption": caption or "🔊 A mai legjobb tippek felolvasva",
                    },
                    files={"audio": ("tippek.mp3", f, "audio/mpeg")},
                    timeout=30,
                )
            if resp.status_code == 200:
                log.info("[voice_tts] Hangüzenet sikeresen elküldve Telegramra.")
                return True
            log.warning(f"[voice_tts] Telegram sendAudio HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            log.warning(f"[voice_tts] Telegram küldési hiba: {e}")
            return False
