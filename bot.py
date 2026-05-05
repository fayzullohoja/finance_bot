import asyncio, os, logging
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import storage as db
import keyboards as kb
from loan_calc import annuity, build_schedule, remaining_balance, next_payment, recalc_early
from api_services import get_exchange_rates, get_gold_price, get_weather, ai_analyze, ai_chat
from excel_report import generate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("finance-bot")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
PORT = int(os.environ.get("PORT", "8080"))

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ── FSM States ────────────────────────────────────────────────────────────────
class Income(StatesGroup):
    amount = State(); category = State(); desc = State(); dt = State()

class Expense(StatesGroup):
    amount = State(); category = State(); desc = State(); dt = State()

class Loan(StatesGroup):
    bank = State(); name = State(); amount = State(); rate = State()
    months = State(); start = State(); pay_day = State()

class EarlyPay(StatesGroup):
    loan_idx = State(); amount = State()

class Transh(StatesGroup):
    loan_idx = State(); amount = State()

class Reminder(StatesGroup):
    title = State(); amount = State(); rem_date = State()

class AIChat(StatesGroup):
    chatting = State()

class ReportPeriod(StatesGroup):
    waiting = State()

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_amount(text):
    try:
        v = float(text.replace(",", ".").replace(" ", "").replace("_", ""))
        return v if v > 0 else None
    except: return None

def parse_date(text):
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(text.strip(), fmt).date().isoformat()
        except: pass
    return None

def get_period_dates(period: str):
    today = date.today()
    if period == "month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), "Текущий месяц"
    elif period == "3m":
        start = (today - timedelta(days=90))
        return start.isoformat(), today.isoformat(), "3 месяца"
    elif period == "6m":
        start = (today - timedelta(days=180))
        return start.isoformat(), today.isoformat(), "6 месяцев"
    elif period == "year":
        start = today.replace(month=1, day=1)
        return start.isoformat(), today.isoformat(), "Текущий год"
    else:
        return "2000-01-01", today.isoformat(), "Всё время"

def filter_by_period(items, start, end):
    return [x for x in items if start <= x.get("date", "9999") <= end]

def require_auth(user):
    return user.get("auth", False)

# ── /start & Auth ─────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    data = db.load()
    user = db.get_user(data, message.from_user.id)
    db.save(data)
    if not require_auth(user):
        await message.answer(
            "👋 Привет! Для доступа к боту нажмите кнопку ниже и поделитесь номером телефона:",
            reply_markup=kb.main_kb(authed=False)
        )
    else:
        await message.answer(f"👋 С возвращением! Ваш номер: {user['phone']}", reply_markup=kb.main_kb())

@dp.message(F.contact)
async def got_contact(message: Message):
    data = db.load()
    user = db.get_user(data, message.from_user.id)
    user["auth"] = True
    user["phone"] = message.contact.phone_number
    db.save(data)
    await message.answer(
        f"✅ Авторизация прошла успешно!\nНомер: {message.contact.phone_number}",
        reply_markup=kb.main_kb()
    )

@dp.message(F.text == "🔙 Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=kb.main_kb())

# ── ДОХОД ─────────────────────────────────────────────────────────────────────
@dp.message(F.text == "💰 Доход")
async def income_start(message: Message, state: FSMContext):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user):
        await message.answer("🔒 Сначала авторизуйтесь.", reply_markup=kb.main_kb(False)); return
    await message.answer("Введите сумму дохода:", reply_markup=kb.cancel_kb())
    await state.set_state(Income.amount)

@dp.message(Income.amount)
async def income_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите корректную сумму:"); return
    await state.update_data(amount=amt)
    data = db.load(); user = db.get_user(data, message.from_user.id)
    last = user.get("last_income_cat")
    await message.answer("Выберите категорию:", reply_markup=kb.cats_kb(config.INCOME_CATEGORIES, last))
    await state.set_state(Income.category)

@dp.message(Income.category)
async def income_cat(message: Message, state: FSMContext):
    cat = message.text.lstrip("↩️ ")
    if cat not in config.INCOME_CATEGORIES:
        await message.answer("Выберите категорию из списка:"); return
    await state.update_data(category=cat)
    await message.answer("Описание (необязательно):", reply_markup=kb.skip_cancel_kb())
    await state.set_state(Income.desc)

@dp.message(Income.desc)
async def income_desc(message: Message, state: FSMContext):
    desc = "" if message.text == "⏭ Пропустить" else message.text
    await state.update_data(desc=desc)
    await message.answer("Дата (ДД.ММ.ГГГГ) или пропустите:", reply_markup=kb.skip_cancel_kb())
    await state.set_state(Income.dt)

@dp.message(Income.dt)
async def income_dt(message: Message, state: FSMContext):
    if message.text == "⏭ Пропустить":
        dt = date.today().isoformat()
    else:
        dt = parse_date(message.text)
        if not dt: await message.answer("❌ Формат: ДД.ММ.ГГГГ"); return
    d = await state.get_data()
    data = db.load(); user = db.get_user(data, message.from_user.id)
    user["incomes"].append({"amount": d["amount"], "category": d["category"], "desc": d.get("desc",""), "date": dt})
    user["last_income_cat"] = d["category"]
    db.save(data)
    await state.clear()
    total = sum(x["amount"] for x in user["incomes"])
    await message.answer(
        f"✅ Доход добавлен!\n💰 {d['amount']:,.0f} — {d['category']}\n📅 {dt}\n\nВсего доходов: {total:,.0f} сум",
        reply_markup=kb.main_kb()
    )

# ── РАСХОД ────────────────────────────────────────────────────────────────────
@dp.message(F.text == "💸 Расход")
async def expense_start(message: Message, state: FSMContext):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Сначала авторизуйтесь.", reply_markup=kb.main_kb(False)); return
    await message.answer("Введите сумму расхода:", reply_markup=kb.cancel_kb())
    await state.set_state(Expense.amount)

@dp.message(Expense.amount)
async def expense_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите корректную сумму:"); return
    await state.update_data(amount=amt)
    data = db.load(); user = db.get_user(data, message.from_user.id)
    last = user.get("last_expense_cat")
    cats = config.EXPENSE_CATEGORIES[:]
    # Добавляем кредиты как отдельную опцию
    if user.get("loans"):
        cats = ["💳 Погашение по кредиту"] + cats
    await message.answer("Выберите категорию:", reply_markup=kb.cats_kb(cats, last))
    await state.set_state(Expense.category)

@dp.message(Expense.category)
async def expense_cat(message: Message, state: FSMContext):
    cat = message.text.lstrip("↩️ ")
    if cat == "💳 Погашение по кредиту":
        await state.update_data(category=cat, is_loan_payment=True)
        data = db.load(); user = db.get_user(data, message.from_user.id)
        active_loans = [l for l in user.get("loans",[]) if l.get("active", True)]
        if not active_loans:
            await message.answer("Нет активных кредитов."); return
        await message.answer("Выберите кредит:", reply_markup=kb.loans_inline(active_loans))
        return
    all_cats = config.EXPENSE_CATEGORIES + ["💳 Погашение по кредиту"]
    if cat not in all_cats:
        await message.answer("Выберите категорию из списка:"); return
    await state.update_data(category=cat, is_loan_payment=False)
    await message.answer("Описание (необязательно):", reply_markup=kb.skip_cancel_kb())
    await state.set_state(Expense.desc)

@dp.callback_query(F.data.startswith("loan:"), Expense.category)
async def expense_loan_select(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    await state.update_data(loan_idx=idx, category="💳 Погашение по кредиту")
    await callback.message.answer("Описание (необязательно):", reply_markup=kb.skip_cancel_kb())
    await state.set_state(Expense.desc)
    await callback.answer()

@dp.message(Expense.desc)
async def expense_desc(message: Message, state: FSMContext):
    desc = "" if message.text == "⏭ Пропустить" else message.text
    await state.update_data(desc=desc)
    await message.answer("Дата (ДД.ММ.ГГГГ) или пропустите:", reply_markup=kb.skip_cancel_kb())
    await state.set_state(Expense.dt)

@dp.message(Expense.dt)
async def expense_dt(message: Message, state: FSMContext):
    if message.text == "⏭ Пропустить":
        dt = date.today().isoformat()
    else:
        dt = parse_date(message.text)
        if not dt: await message.answer("❌ Формат: ДД.ММ.ГГГГ"); return
    d = await state.get_data()
    data = db.load(); user = db.get_user(data, message.from_user.id)
    exp = {"amount": d["amount"], "category": d["category"], "desc": d.get("desc",""), "date": dt}
    user["expenses"].append(exp)
    user["last_expense_cat"] = d["category"]

    # Взаиморасчёт с кредитом
    extra_msg = ""
    if d.get("is_loan_payment") and "loan_idx" in d:
        idx = d["loan_idx"]
        loan = user["loans"][idx]
        schedule = loan.get("schedule", [])
        nxt = next_payment(schedule)
        if nxt:
            diff = d["amount"] - nxt["total"]
            extra_msg = f"\n\n🏦 Кредит: {loan['name']}\nОжидался платёж: {nxt['total']:,.0f} сум\nВнесено: {d['amount']:,.0f} сум"
            if diff >= 0:
                nxt["paid"] = True
                extra_msg += f"\n✅ Транш закрыт! Остаток: {nxt['balance']:,.0f} сум"
            else:
                extra_msg += f"\n⚠️ Не доплачено: {abs(diff):,.0f} сум"
            db.save(data)

    db.save(data)
    await state.clear()
    total = sum(x["amount"] for x in user["expenses"])
    await message.answer(
        f"✅ Расход добавлен!\n💸 {d['amount']:,.0f} — {d['category']}\n📅 {dt}\n\nВсего расходов: {total:,.0f} сум{extra_msg}",
        reply_markup=kb.main_kb()
    )

# ── КРЕДИТЫ ───────────────────────────────────────────────────────────────────
@dp.message(F.text == "🏦 Кредиты")
async def loans_menu(message: Message, state: FSMContext):
    await state.clear()
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    loans = [l for l in user.get("loans",[]) if l.get("active",True)]
    btns = kb.loans_inline(loans)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    add_btn = [[InlineKeyboardButton(text="➕ Добавить кредит", callback_data="add_loan")],
               [InlineKeyboardButton(text="📋 Все кредиты", callback_data="loan_list")]]
    full = InlineKeyboardMarkup(inline_keyboard=add_btn + btns.inline_keyboard)
    await message.answer(f"🏦 Активных кредитов: {len(loans)}", reply_markup=full)

@dp.callback_query(F.data == "add_loan")
async def add_loan_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите банк:", reply_markup=kb.banks_kb(config.UZB_BANKS))
    await state.set_state(Loan.bank)
    await callback.answer()

@dp.message(Loan.bank)
async def loan_bank(message: Message, state: FSMContext):
    if message.text not in config.UZB_BANKS: await message.answer("Выберите банк из списка:"); return
    await state.update_data(bank=message.text)
    await message.answer("Введите название кредита (например: Авто, Ипотека):", reply_markup=kb.cancel_kb())
    await state.set_state(Loan.name)

@dp.message(Loan.name)
async def loan_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите сумму кредита:")
    await state.set_state(Loan.amount)

@dp.message(Loan.amount)
async def loan_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите сумму:"); return
    await state.update_data(amount=amt)
    await message.answer("Годовая ставка % (например: 22):")
    await state.set_state(Loan.rate)

@dp.message(Loan.rate)
async def loan_rate(message: Message, state: FSMContext):
    try:
        r = float(message.text.replace(",","."))
        if r <= 0 or r > 150: raise ValueError
    except: await message.answer("❌ Введите ставку 0-150%:"); return
    await state.update_data(rate=r)
    await message.answer("Срок в месяцах (например: 24):")
    await state.set_state(Loan.months)

@dp.message(Loan.months)
async def loan_months(message: Message, state: FSMContext):
    try:
        m = int(message.text.strip())
        if m <= 0: raise ValueError
    except: await message.answer("❌ Введите целое число:"); return
    await state.update_data(months=m)
    await message.answer("Дата выдачи кредита (ДД.ММ.ГГГГ):")
    await state.set_state(Loan.start)

@dp.message(Loan.start)
async def loan_start(message: Message, state: FSMContext):
    dt = parse_date(message.text)
    if not dt: await message.answer("❌ Формат: ДД.ММ.ГГГГ"); return
    await state.update_data(start=dt)
    await message.answer("День ежемесячного платежа (1-28):")
    await state.set_state(Loan.pay_day)

@dp.message(Loan.pay_day)
async def loan_pay_day(message: Message, state: FSMContext):
    try:
        day = int(message.text.strip())
        if day < 1 or day > 28: raise ValueError
    except: await message.answer("❌ Введите число 1-28:"); return
    d = await state.get_data()
    monthly = annuity(d["amount"], d["rate"], d["months"])
    schedule = build_schedule(d["amount"], d["rate"], d["months"], d["start"], day)
    data = db.load(); user = db.get_user(data, message.from_user.id)
    user["loans"].append({
        "bank": d["bank"], "name": d["name"], "amount": d["amount"],
        "rate": d["rate"], "months": d["months"], "start_date": d["start"],
        "payment_day": day, "schedule": schedule, "active": True
    })
    db.save(data)
    await state.clear()
    await message.answer(
        f"✅ Кредит добавлен!\n\n🏦 {d['bank']} — {d['name']}\n"
        f"💰 Сумма: {d['amount']:,.0f} сум\n📊 Ставка: {d['rate']}%\n"
        f"📅 Срок: {d['months']} мес. с {d['start']}\n"
        f"💳 Ежемесячный платёж: {monthly:,.0f} сум",
        reply_markup=kb.main_kb()
    )

@dp.callback_query(F.data == "loan_list")
async def loan_list(callback: CallbackQuery):
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    loans = user.get("loans", [])
    if not loans:
        await callback.message.edit_text("Нет кредитов."); return
    lines = ["🏦 <b>Все кредиты</b>\n"]
    for i, l in enumerate(loans):
        status = "✅" if l.get("active",True) else "❌"
        monthly = annuity(l["amount"], l["rate"], l["months"])
        lines.append(f"{status} {i+1}. {l['bank']} — {l['name']}\n   {l['amount']:,.0f} сум | {l['rate']}% | {monthly:,.0f}/мес")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.loans_inline(loans))
    await callback.answer()

@dp.callback_query(F.data.startswith("loan:"))
async def loan_detail(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    monthly = annuity(loan["amount"], loan["rate"], loan["months"])
    schedule = loan.get("schedule", [])
    nxt = next_payment(schedule)
    paid_count = sum(1 for s in schedule if s["paid"])
    lines = [
        f"🏦 <b>{loan['bank']} — {loan['name']}</b>\n",
        f"💰 Сумма: {loan['amount']:,.0f} сум",
        f"📊 Ставка: {loan['rate']}% годовых",
        f"📅 Срок: {loan['months']} мес. (с {loan['start_date']})",
        f"💳 Ежемесячный платёж: {monthly:,.0f} сум",
        f"✅ Оплачено траншей: {paid_count}/{loan['months']}",
    ]
    if nxt:
        lines.append(f"⏰ Следующий платёж: {nxt['date']} — {nxt['total']:,.0f} сум")
        lines.append(f"📉 Остаток долга: {nxt['balance']:,.0f} сум")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.loan_detail_inline(idx))
    await callback.answer()

@dp.callback_query(F.data.startswith("sched:"))
async def show_schedule(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    schedule = user["loans"][idx].get("schedule", [])
    lines = [f"📅 <b>График платежей</b>\n"]
    for s in schedule[:15]:
        icon = "✅" if s["paid"] else "⏳"
        lines.append(f"{icon} {s['month']:2d}. {s['date']} | {s['total']:>10,.0f} сум | ост: {s['balance']:,.0f}")
    if len(schedule) > 15:
        lines.append(f"... и ещё {len(schedule)-15} платежей")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.loan_detail_inline(idx))
    await callback.answer()

@dp.callback_query(F.data.startswith("transh:"))
async def transh_start(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    await state.update_data(loan_idx=idx)
    await state.set_state(Transh.amount)
    await callback.message.answer("Введите сумму транша (ежемесячного платежа):", reply_markup=kb.cancel_kb())
    await callback.answer()

@dp.message(Transh.amount)
async def transh_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите сумму:"); return
    d = await state.get_data()
    idx = d["loan_idx"]
    data = db.load(); user = db.get_user(data, message.from_user.id)
    loan = user["loans"][idx]
    schedule = loan.get("schedule", [])
    nxt = next_payment(schedule)
    if not nxt:
        await message.answer("✅ Все транши оплачены!"); await state.clear(); return
    diff = amt - nxt["total"]
    nxt["paid"] = True
    db.save(data)
    await state.clear()
    msg = f"✅ Транш оплачен!\n💳 {amt:,.0f} сум\n📅 Дата: {nxt['date']}\n📉 Остаток долга: {nxt['balance']:,.0f} сум"
    if diff > 0:
        msg += f"\n💡 Переплата: {diff:,.0f} сум (учтите в досрочном погашении)"
    elif diff < 0:
        msg += f"\n⚠️ Недоплата: {abs(diff):,.0f} сум"
    await message.answer(msg, reply_markup=kb.main_kb())

@dp.callback_query(F.data.startswith("early:"))
async def early_start(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    await state.update_data(loan_idx=idx)
    await state.set_state(EarlyPay.amount)
    await callback.message.answer("Введите сумму досрочного погашения:", reply_markup=kb.cancel_kb())
    await callback.answer()

@dp.message(EarlyPay.amount)
async def early_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите сумму:"); return
    d = await state.get_data()
    await state.update_data(amount=amt)
    await message.answer("Как пересчитать кредит?", reply_markup=kb.early_inline(d["loan_idx"]))
    await state.set_state(EarlyPay.loan_idx)

@dp.callback_query(F.data.startswith("early_term:"))
async def early_term(callback: CallbackQuery, state: FSMContext):
    await _do_early(callback, state, reduce_term=True)

@dp.callback_query(F.data.startswith("early_pay:"))
async def early_pay(callback: CallbackQuery, state: FSMContext):
    await _do_early(callback, state, reduce_term=False)

async def _do_early(callback, state, reduce_term):
    d = await state.get_data()
    idx, amt = d["loan_idx"], d["amount"]
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    new_sched = recalc_early(loan["schedule"], amt, loan["rate"], reduce_term, loan["payment_day"])
    loan["schedule"] = new_sched
    loan["months"] = len(new_sched)
    db.save(data)
    await state.clear()
    monthly = annuity(loan["amount"], loan["rate"], loan["months"])
    remaining = len([s for s in new_sched if not s["paid"]])
    await callback.message.edit_text(
        f"✅ Досрочное погашение проведено!\n💳 {amt:,.0f} сум\n"
        f"📅 Новый срок: {remaining} мес.\n💳 Платёж: {monthly:,.0f} сум",
        reply_markup=kb.loan_detail_inline(idx)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("close:"))
async def close_loan(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    user["loans"][idx]["active"] = False
    db.save(data)
    await callback.message.edit_text("✅ Кредит закрыт!")
    await callback.answer()

# ── БАЛАНС ────────────────────────────────────────────────────────────────────
@dp.message(F.text == "📊 Баланс")
async def balance(message: Message):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    today_str = today.isoformat()
    inc = filter_by_period(user["incomes"], month_start, today_str)
    exp = filter_by_period(user["expenses"], month_start, today_str)
    ti = sum(x["amount"] for x in inc)
    te = sum(x["amount"] for x in exp)
    bal = ti - te
    loans = [l for l in user.get("loans",[]) if l.get("active",True)]
    total_monthly = sum(annuity(l["amount"],l["rate"],l["months"]) for l in loans)
    lines = [
        "📊 <b>Баланс (текущий месяц)</b>\n",
        f"💰 Доходы: <b>{ti:,.0f} сум</b>",
        f"💸 Расходы: <b>{te:,.0f} сум</b>",
        f"{'✅' if bal>=0 else '⚠️'} Баланс: <b>{bal:,.0f} сум</b>",
    ]
    if loans:
        lines.append(f"\n🏦 Кредитная нагрузка: {total_monthly:,.0f} сум/мес")
        if ti > 0:
            pct = total_monthly/ti*100
            icon = "🟢" if pct<30 else "🟡" if pct<50 else "🔴"
            lines.append(f"{icon} Долг/Доход: {pct:.0f}%")
    cats = {}
    for e in exp:
        cats[e["category"]] = cats.get(e["category"],0) + e["amount"]
    if cats:
        lines.append("\n📂 <b>Топ расходов:</b>")
        for cat, amt in sorted(cats.items(), key=lambda x:-x[1])[:5]:
            lines.append(f"  • {cat}: {amt:,.0f}")
    await message.answer("\n".join(lines), parse_mode="HTML")

# ── AI АНАЛИТИКА ──────────────────────────────────────────────────────────────
@dp.message(F.text == "📈 AI Аналитика")
async def ai_analytics(message: Message):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    await message.answer("⏳ Анализирую...")
    result = await ai_analyze(user["incomes"], user["expenses"], user.get("loans",[]), config.OPENAI_API_KEY)
    await message.answer(f"📈 <b>AI Аналитика</b>\n\n{result}", parse_mode="HTML")

@dp.message(F.text == "🤖 AI Советник")
async def ai_advisor_start(message: Message, state: FSMContext):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    await state.set_state(AIChat.chatting)
    await message.answer("🤖 Задайте вопрос финансовому советнику:\n(нажмите 🔙 Отмена для выхода)", reply_markup=kb.cancel_kb())

@dp.message(AIChat.chatting)
async def ai_chat_msg(message: Message, state: FSMContext):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    ti = sum(x["amount"] for x in user["incomes"])
    te = sum(x["amount"] for x in user["expenses"])
    ctx = {"income": ti, "expense": te, "loans": len(user.get("loans",[]))}
    await message.answer("⏳ Думаю...")
    result = await ai_chat(message.text, ctx, config.OPENAI_API_KEY)
    await message.answer(result, reply_markup=kb.cancel_kb())

# ── ВАЛЮТА И ЗОЛОТО ───────────────────────────────────────────────────────────
@dp.message(F.text == "💱 Валюта и золото")
async def currency(message: Message):
    await message.answer("⏳ Получаю курсы...")
    rates = await get_exchange_rates()
    gold = await get_gold_price()
    lines = ["💱 <b>Курсы ЦБ Узбекистана</b>\n"]
    symbols = {"USD":"🇺🇸","EUR":"🇪🇺","RUB":"🇷🇺","CNY":"🇨🇳","KZT":"🇰🇿"}
    if rates:
        for cur in config.CURRENCIES:
            if cur in rates:
                r = rates[cur]
                diff_icon = "🔺" if r["diff"]>0 else "🔻" if r["diff"]<0 else "➡️"
                lines.append(f"{symbols.get(cur,'')} {cur}: {r['rate']:,.2f} сум {diff_icon}{abs(r['diff']):.2f}")
    else:
        lines.append("❌ Не удалось получить курсы")
    if gold:
        lines.append(f"\n🥇 Золото: ${gold:,.2f} / тр.унция")
    lines.append(f"\n🕐 Обновлено: {datetime.now().strftime('%H:%M %d.%m.%Y')}")
    await message.answer("\n".join(lines), parse_mode="HTML")

# ── ПОГОДА ────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🌤 Погода")
async def weather(message: Message):
    if not config.WEATHER_API_KEY:
        await message.answer("🌤 Для погоды добавьте WEATHER_API_KEY в config.py\n(Бесплатно на openweathermap.org)"); return
    await message.answer("⏳ Получаю погоду...")
    w = await get_weather(config.WEATHER_CITY, config.WEATHER_API_KEY)
    if w:
        await message.answer(
            f"🌤 <b>Погода: {w['city']}</b>\n\n"
            f"🌡 Температура: {w['temp']}°C (ощущается {w['feels']}°C)\n"
            f"☁️ {w['desc']}\n💧 Влажность: {w['humidity']}%\n💨 Ветер: {w['wind']} м/с",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Не удалось получить погоду")

# ── НАПОМИНАНИЯ ───────────────────────────────────────────────────────────────
@dp.message(F.text == "⏰ Напоминания")
async def reminders_menu(message: Message, state: FSMContext):
    await state.clear()
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rems = user.get("reminders",[])
    lines = ["⏰ <b>Напоминания о платежах</b>\n"]
    for i, r in enumerate(rems):
        status = "✅" if r.get("paid") else "⏳"
        lines.append(f"{status} {r['date']} | {r['title']} | {r['amount']:,.0f} сум")
    if not rems: lines.append("Нет напоминаний")
    btns = [[InlineKeyboardButton(text="➕ Добавить напоминание", callback_data="add_rem")]]
    for i, r in enumerate(rems):
        if not r.get("paid"):
            btns.append([InlineKeyboardButton(text=f"✅ Оплачено: {r['title']}", callback_data=f"rem_paid:{i}")])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "add_rem")
async def add_reminder(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Название напоминания (например: Аренда):", reply_markup=kb.cancel_kb())
    await state.set_state(Reminder.title)
    await callback.answer()

@dp.message(Reminder.title)
async def rem_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Сумма платежа:")
    await state.set_state(Reminder.amount)

@dp.message(Reminder.amount)
async def rem_amount(message: Message, state: FSMContext):
    amt = parse_amount(message.text)
    if not amt: await message.answer("❌ Введите сумму:"); return
    await state.update_data(amount=amt)
    await message.answer("Дата платежа (ДД.ММ.ГГГГ):")
    await state.set_state(Reminder.rem_date)

@dp.message(Reminder.rem_date)
async def rem_date(message: Message, state: FSMContext):
    dt = parse_date(message.text)
    if not dt: await message.answer("❌ Формат: ДД.ММ.ГГГГ"); return
    d = await state.get_data()
    data = db.load(); user = db.get_user(data, message.from_user.id)
    user.setdefault("reminders",[]).append({"title":d["title"],"amount":d["amount"],"date":dt,"paid":False})
    db.save(data)
    await state.clear()
    await message.answer(f"✅ Напоминание добавлено!\n📅 {dt} — {d['title']} — {d['amount']:,.0f} сум", reply_markup=kb.main_kb())

@dp.callback_query(F.data.startswith("rem_paid:"))
async def rem_paid(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    user["reminders"][idx]["paid"] = True
    db.save(data)
    await callback.answer("✅ Отмечено как оплачено!")
    await callback.message.delete()

# ── ОТЧЁТ ─────────────────────────────────────────────────────────────────────
@dp.message(F.text == "📋 Отчёт")
async def report_menu(message: Message):
    data = db.load(); user = db.get_user(data, message.from_user.id)
    if not require_auth(user): await message.answer("🔒 Авторизуйтесь."); return
    await message.answer("Выберите период:", reply_markup=kb.period_inline())

@dp.callback_query(F.data.startswith("period:"))
async def period_report(callback: CallbackQuery):
    period = callback.data.split(":")[1]
    data = db.load(); user = db.get_user(data, callback.from_user.id)
    start, end, label = get_period_dates(period if period != "excel" else "all")
    inc = filter_by_period(user["incomes"], start, end)
    exp = filter_by_period(user["expenses"], start, end)
    loans = user.get("loans",[])

    if period == "excel":
        report = generate(inc, exp, loans, label)
        await callback.message.answer_document(
            document=BufferedInputFile(report, filename=f"Отчёт_{label}.xlsx"),
            caption=f"📊 Excel отчёт: {label}"
        )
        await callback.answer()
        return

    ti = sum(x["amount"] for x in inc)
    te = sum(x["amount"] for x in exp)
    bal = ti - te
    cats = {}
    for e in exp:
        cats[e["category"]] = cats.get(e["category"],0) + e["amount"]
    lines = [
        f"📋 <b>Отчёт: {label}</b>\n",
        f"💰 Доходы: {ti:,.0f} сум",
        f"💸 Расходы: {te:,.0f} сум",
        f"{'✅' if bal>=0 else '⚠️'} Баланс: {bal:,.0f} сум\n",
        "<b>Расходы по категориям:</b>"
    ]
    for cat, amt in sorted(cats.items(), key=lambda x:-x[1])[:10]:
        pct = amt/te*100 if te else 0
        lines.append(f"  • {cat}: {amt:,.0f} ({pct:.0f}%)")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.period_inline())
    await callback.answer()

# ── СБРОС ДАННЫХ ──────────────────────────────────────────────────────────────
@dp.message(Command("reset"))
async def reset_cmd(message: Message):
    await message.answer("⚠️ Вы уверены? Все данные будут удалены!", reply_markup=kb.reset_inline())

@dp.callback_query(F.data == "reset_confirm")
async def reset_confirm(callback: CallbackQuery):
    data = db.load()
    uid = str(callback.from_user.id)
    if uid in data:
        phone = data[uid].get("phone")
        data[uid] = {"auth": True, "phone": phone, "incomes":[], "expenses":[], "loans":[], "reminders":[], "last_income_cat":None, "last_expense_cat":None}
        db.save(data)
    await callback.message.edit_text("✅ Все данные сброшены!")
    await callback.answer()

@dp.callback_query(F.data == "reset_cancel")
async def reset_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Сброс отменён.")
    await callback.answer()

@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

# ── ПЛАНИРОВЩИК НАПОМИНАНИЙ ───────────────────────────────────────────────────
async def check_reminders():
    while True:
        await asyncio.sleep(3600)  # Проверка раз в час
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        data = db.load()
        for uid, user in data.items():
            for rem in user.get("reminders",[]):
                if not rem.get("paid") and rem["date"] in [today, tomorrow]:
                    when = "сегодня" if rem["date"] == today else "завтра"
                    try:
                        await bot.send_message(
                            int(uid),
                            f"⏰ <b>Напоминание!</b>\n\n{rem['title']}\n💳 {rem['amount']:,.0f} сум\n📅 Платёж {when}!",
                            parse_mode="HTML"
                        )
                    except: pass

# ── ЗАПУСК ────────────────────────────────────────────────────────────────────
#
# Два режима:
#   webhook (production: Render/Vercel/любой PaaS)  — задан WEBHOOK_URL
#   polling (локалка / fallback при пустом WEBHOOK_URL)
# Фоновый таск check_reminders() запускается в обоих режимах.

async def _on_startup(bot: Bot):
    asyncio.create_task(check_reminders())
    full = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(full, drop_pending_updates=False,
                          allowed_updates=dp.resolve_used_update_types())
    me = await bot.me()
    log.info("Webhook установлен: %s (бот @%s)", full, me.username)


async def _on_shutdown(bot: Bot):
    # Не удаляем webhook при остановке: при rolling-deploy на Render
    # старый контейнер останавливается ПОСЛЕ того как новый уже поднял
    # webhook на тот же URL — delete тогда сотрёт работающий webhook.
    log.info("Shutdown: webhook оставлен как есть (избегаем race с новым деплоем)")


async def _health(_request):
    return web.Response(text="ok")


def run_webhook():
    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    log.info("Запускаю webhook-сервер на :%s%s", PORT, WEBHOOK_PATH)
    web.run_app(app, host="0.0.0.0", port=PORT)


async def _run_polling_with_health():
    """Polling + минимальный aiohttp на PORT (Render-health, пока не задан WEBHOOK_URL)."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    log.info("Health-сервер на :%s, polling запущен (WEBHOOK_URL не задан)", PORT)
    try:
        asyncio.create_task(check_reminders())
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()


async def run_polling():
    log.info("Запускаю polling (локальный режим)")
    asyncio.create_task(check_reminders())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    if WEBHOOK_URL:
        run_webhook()
    elif os.environ.get("PORT"):
        asyncio.run(_run_polling_with_health())
    else:
        asyncio.run(run_polling())
