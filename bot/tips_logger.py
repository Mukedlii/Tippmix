import os
import json
import datetime
from typing import Any, Dict, Iterable

LOG_DIR = os.getenv("TIPPMIX_LOG_DIR", "logs")

def _ensure_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

def log_tips(date: str, rows: Iterable[Dict[str, Any]]) -> str:
    """
    JSONL: 1 sor = 1 tipp log.
    date: 'YYYY-MM-DD'
    rows: dict tippek
    """
    _ensure_dir()
    path = os.path.join(LOG_DIR, f"tips_{date}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path

def today_str() -> str:
    return datetime.date.today().isoformat()
