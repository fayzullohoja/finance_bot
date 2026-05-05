"""
Хранилище данных бота.

Если заданы переменные окружения SUPABASE_URL и SUPABASE_KEY —
работает через Supabase REST API (постоянное хранение).
Иначе — fallback на data.json рядом со скриптом (для локальной разработки).

API остаётся прежним: load() / save(data) / get_user(data, uid) / fmt(amount)
"""
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import logging
from datetime import datetime, date

log = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
TABLE = os.environ.get("SUPABASE_TABLE", "users")

_BASE = os.environ.get("DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_BASE, "data.json")

USE_REMOTE = bool(SUPABASE_URL and SUPABASE_KEY)


# ───────────────────────────── REST helpers ─────────────────────────────

def _http(method: str, path: str, body: object | None = None, timeout: int = 10) -> object:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if method in ("POST", "PATCH", "PUT"):
        req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


# ─────────────────────────── public API ─────────────────────────────────

def load() -> dict:
    if not USE_REMOTE:
        return _file_load()
    try:
        rows = _http("GET", f"{TABLE}?select=id,data") or []
        return {str(r["id"]): r["data"] for r in rows}
    except Exception as e:
        log.error("Supabase load failed: %s — fallback to local file", e)
        return _file_load()


def save(data: dict) -> None:
    if not USE_REMOTE:
        return _file_save(data)
    try:
        rows = [{"id": int(uid), "data": user} for uid, user in data.items()]
        if rows:
            _http("POST", TABLE, rows)
    except Exception as e:
        log.error("Supabase save failed: %s — writing local file as backup", e)
        _file_save(data)


def get_user(data: dict, uid) -> dict:
    uid = str(uid)
    if uid not in data:
        data[uid] = {
            "auth": False,
            "phone": None,
            "incomes": [],
            "expenses": [],
            "loans": [],
            "reminders": [],
            "last_income_cat": None,
            "last_expense_cat": None,
        }
    return data[uid]


def fmt(amount) -> str:
    return f"{float(amount):,.0f}"


# ─────────────────────────── file fallback ──────────────────────────────

def _file_load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _file_save(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
