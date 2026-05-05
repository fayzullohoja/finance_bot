from decimal import Decimal
import math

def annuity(principal: float, annual_rate: float, months: int) -> float:
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 100 / 12
    return principal * r * (1 + r)**months / ((1 + r)**months - 1)

def build_schedule(principal: float, annual_rate: float, months: int, start_date: str, payment_day: int) -> list:
    from datetime import date
    from dateutil.relativedelta import relativedelta
    r = annual_rate / 100 / 12
    monthly = annuity(principal, annual_rate, months)
    balance = principal
    schedule = []
    sd = date.fromisoformat(start_date)
    for i in range(1, months + 1):
        pdate = (sd + relativedelta(months=i)).replace(day=min(payment_day, 28))
        interest = balance * r
        principal_part = monthly - interest
        if i == months:
            principal_part = balance
        balance -= principal_part
        if balance < 0: balance = 0
        schedule.append({
            "month": i,
            "date": pdate.isoformat(),
            "total": round(monthly if i < months else principal_part + interest, 2),
            "principal": round(principal_part, 2),
            "interest": round(interest, 2),
            "balance": round(balance, 2),
            "paid": False
        })
    return schedule

def remaining_balance(schedule: list) -> float:
    for row in reversed(schedule):
        if row["paid"]:
            return row["balance"]
    return schedule[0]["balance"] + schedule[0]["principal"] if schedule else 0

def next_payment(schedule: list):
    for row in schedule:
        if not row["paid"]:
            return row
    return None

def recalc_early(schedule: list, extra: float, annual_rate: float, reduce_term: bool, payment_day: int) -> list:
    paid_months = [r for r in schedule if r["paid"]]
    last_balance = schedule[len(paid_months)]["balance"] if paid_months else schedule[0]["balance"] + schedule[0]["principal"]
    new_balance = last_balance - extra
    if new_balance <= 0:
        return []
    remaining = len(schedule) - len(paid_months)
    if reduce_term:
        monthly = annuity(last_balance, annual_rate, remaining)
        r = annual_rate / 100 / 12
        if r == 0:
            new_term = int(new_balance / monthly) + 1
        else:
            val = monthly / (monthly - r * new_balance)
            new_term = math.ceil(math.log(val) / math.log(1 + r))
        new_term = max(1, new_term)
    else:
        new_term = remaining

    from datetime import date
    start = date.today().isoformat()
    new_sched = build_schedule(new_balance, annual_rate, new_term, start, payment_day)
    for i, row in enumerate(new_sched):
        row["month"] = len(paid_months) + i + 1
    return paid_months + new_sched
