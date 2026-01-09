# bot/tips_logger.py
import json
import os
from typing import Any, Dict, List, Optional


def _safe_load_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _list_existing(paths: List[str]) -> List[str]:
    return [p for p in paths if os.path.isfile(p)]


def read_tips(slot: str, base_dir: str = ".") -> Dict[str, Any]:
    """
    Visszaadja a mentett tippeket a repo rootból.
    A te projektedben ezek a fájlok léteznek:
      - vip_bets_day.json / vip_bets_evening.json
      - public_bets_day.json / public_bets_evening.json
      - (opcionális) *_meta.json

    Return:
      {
        "vip_bets": [...],
        "public_bets": [...],
        "vip_meta": {...} | None,
        "public_meta": {...} | None,
      }
    """
    slot = (slot or "DAY").upper()
    suffix = "day" if slot == "DAY" else "evening"

    vip_path = os.path.join(base_dir, f"vip_bets_{suffix}.json")
    pub_path = os.path.join(base_dir, f"public_bets_{suffix}.json")

    vip_meta_path = os.path.join(base_dir, f"vip_bets_{suffix}_meta.json")
    pub_meta_path = os.path.join(base_dir, f"public_bets_{suffix}_meta.json")

    vip_bets = _safe_load_json(vip_path) or []
    public_bets = _safe_load_json(pub_path) or []

    vip_meta = _safe_load_json(vip_meta_path)
    public_meta = _safe_load_json(pub_meta_path)

    # mindig listát adjunk vissza
    if not isinstance(vip_bets, list):
        vip_bets = []
    if not isinstance(public_bets, list):
        public_bets = []

    return {
        "vip_bets": vip_bets,
        "public_bets": public_bets,
        "vip_meta": vip_meta,
        "public_meta": public_meta,
        "paths_found": _list_existing([vip_path, pub_path, vip_meta_path, pub_meta_path]),
    }

