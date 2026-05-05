import json, os
from datetime import datetime, date

# DATA_DIR можно переопределить через env (для будущего перехода
# на персистентный диск). По умолчанию — рядом со storage.py.
_BASE = os.environ.get("DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(_BASE, "data.json")

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
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

def fmt(amount):
    return f"{float(amount):,.0f}"
