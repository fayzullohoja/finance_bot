import json, os, math, logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("finance-bot")

# ══════════════════════════════════════════════════════════════
#  КОНФИГ — берётся из переменных окружения
#    BOT_TOKEN     — токен от BotFather (обязательно)
#    WEBHOOK_URL   — публичный https URL сервиса (для webhook-режима)
#    WEBHOOK_PATH  — путь, куда Telegram шлёт обновления (default /webhook)
#    PORT          — порт http-сервера (Render задаёт сам)
#    DATA_DIR      — куда писать data.json (default — рядом с bot.py)
# ══════════════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)) or ".")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Положите его в переменные окружения.")

DATA_FILE = os.path.join(DATA_DIR, "data.json")

# ══════════════════════════════════════════════════════════════
#  КАТЕГОРИИ
# ══════════════════════════════════════════════════════════════
INCOME_CATS = [
    "💼 Зарплата",
    "🏢 Аванс",
    "📈 Премия / Бонус",
    "🏪 Доход от бизнеса",
    "🏠 Аренда недвижимости",
    "📦 Продажа товаров",
    "💻 Фриланс / Подработка",
    "💸 Перевод от родных",
    "🎁 Подарок / Помощь",
    "📊 Дивиденды / Инвестиции",
    "🎰 Выигрыш / Лотерея",
    "🏦 Возврат налога / Кэшбэк",
    "📚 Стипендия",
    "🌾 Пенсия / Пособие",
    "🔄 Прочий доход",
]

EXPENSE_CATS = [
    # Еда
    "🛒 Продукты / Супермаркет",
    "🍽️ Кафе / Ресторан",
    "🍕 Доставка еды",
    "☕ Кофе / Снэки",
    # Транспорт
    "🚇 Общественный транспорт",
    "🚕 Такси / Каршеринг",
    "⛽ Бензин",
    "🔧 Обслуживание авто",
    "✈️ Авиа / ЖД билеты",
    # Жильё
    "🏠 Аренда жилья",
    "💡 Коммунальные услуги",
    "📶 Интернет / Телефон",
    "🛋️ Мебель / Техника",
    "🔨 Ремонт / Стройматериалы",
    # Кредиты и финансы
    "🏦 Платёж по кредиту",
    "💳 Платёж по ипотеке",
    "📋 Страховка",
    "💰 Долг / Возврат",
    # Здоровье
    "💊 Лекарства / Аптека",
    "🏥 Врач / Клиника",
    "🏋️ Спортзал / Фитнес",
    # Образование
    "📚 Обучение / Курсы",
    "🎓 Школа / Детсад",
    "📖 Книги / Учебники",
    # Одежда и красота
    "👗 Одежда / Обувь",
    "💄 Красота / Салон",
    "🛍️ Аксессуары",
    # Развлечения
    "🎬 Кино / Театр",
    "🎮 Игры / Подписки",
    "🏖️ Отдых / Туризм",
    "🎉 Праздник / Подарки",
    # Дети
    "👶 Детские товары",
    "🧸 Игрушки / Развлечения детей",
    # Прочее
    "🐾 Животные / Корм",
    "📦 Маркетплейс / Интернет-магазин",
    "🔄 Прочий расход",
]

# ══════════════════════════════════════════════════════════════
#  ХРАНИЛИЩЕ
# ══════════════════════════════════════════════════════════════
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"incomes": [], "expenses": [], "loans": []}
    return data[uid]

# ══════════════════════════════════════════════════════════════
#  КРЕДИТНЫЕ РАСЧЁТЫ
# ══════════════════════════════════════════════════════════════
def calc_annuity(principal, annual_rate, months):
    if annual_rate == 0:
        return round(principal / months, 2)
    r = annual_rate / 100 / 12
    payment = principal * r * (1 + r)**months / ((1 + r)**months - 1)
    return round(payment, 2)

def build_schedule(principal, annual_rate, months, start_date_str, payment_day):
    """Возвращает список платежей по кредиту"""
    r = annual_rate / 100 / 12
    monthly = calc_annuity(principal, annual_rate, months)
    balance = principal
    schedule = []
    start = datetime.strptime(start_date_str, "%d.%m.%Y").date()

    for i in range(1, months + 1):
        pay_date = (start + relativedelta(months=i)).replace(day=min(payment_day, 28))
        interest = round(balance * r, 2)
        principal_part = round(monthly - interest, 2)
        if i == months:
            principal_part = balance
        balance = round(balance - principal_part, 2)
        if balance < 0:
            balance = 0
        schedule.append({
            "month": i,
            "date": str(pay_date),
            "total": round(principal_part + interest, 2),
            "principal": principal_part,
            "interest": interest,
            "balance": balance,
            "paid": False,
        })
    return schedule

def get_loan_remaining(loan):
    """Остаток долга — последний неоплаченный месяц из графика"""
    for s in reversed(loan.get("schedule", [])):
        if not s["paid"]:
            return s["balance"] + s["principal"]
    return 0

# ══════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════
class IncomeState(StatesGroup):
    amount = State()
    category = State()
    note = State()

class ExpenseState(StatesGroup):
    amount = State()
    category = State()
    note = State()

class LoanState(StatesGroup):
    name = State()
    amount = State()
    rate = State()
    months = State()
    start_date = State()
    payment_day = State()

class EarlyPayState(StatesGroup):
    loan_idx = State()
    amount = State()
    choice = State()

class TrancheState(StatesGroup):
    loan_idx = State()
    month_idx = State()

# ══════════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Доход"), KeyboardButton(text="💸 Расход")],
        [KeyboardButton(text="🏦 Кредиты"), KeyboardButton(text="📊 Баланс")],
        [KeyboardButton(text="📋 История")],
    ], resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Отмена")]], resize_keyboard=True)

def skip_cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Пропустить")],
        [KeyboardButton(text="🔙 Отмена")]
    ], resize_keyboard=True)

def loan_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Новый кредит")],
        [KeyboardButton(text="📋 Мои кредиты")],
        [KeyboardButton(text="🔙 Главное меню")],
    ], resize_keyboard=True)

def income_cats_kb():
    rows = []
    for i in range(0, len(INCOME_CATS), 2):
        row = [KeyboardButton(text=INCOME_CATS[i])]
        if i+1 < len(INCOME_CATS):
            row.append(KeyboardButton(text=INCOME_CATS[i+1]))
        rows.append(row)
    rows.append([KeyboardButton(text="🔙 Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def expense_cats_kb():
    rows = []
    for i in range(0, len(EXPENSE_CATS), 2):
        row = [KeyboardButton(text=EXPENSE_CATS[i])]
        if i+1 < len(EXPENSE_CATS):
            row.append(KeyboardButton(text=EXPENSE_CATS[i+1]))
        rows.append(row)
    rows.append([KeyboardButton(text="🔙 Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def loans_inline(loans):
    buttons = [[InlineKeyboardButton(text=f"🏦 {l['name']} — {l['amount']:,.0f}", callback_data=f"loan:{i}")] for i, l in enumerate(loans)]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def loan_detail_inline(idx):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 График платежей", callback_data=f"schedule:{idx}:0")],
        [InlineKeyboardButton(text="✅ Оплатить транш", callback_data=f"tranche:{idx}")],
        [InlineKeyboardButton(text="💳 Досрочное погашение", callback_data=f"early:{idx}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="loan_list")],
    ])

def early_options_inline(idx):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📉 Уменьшить срок", callback_data=f"early_term:{idx}")],
        [InlineKeyboardButton(text="💰 Уменьшить платёж", callback_data=f"early_pay:{idx}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"loan:{idx}")],
    ])

# ══════════════════════════════════════════════════════════════
#  БОТ
# ══════════════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я помогу вести учёт личных финансов.\n"
        "Выберите действие:",
        reply_markup=main_kb()
    )

@dp.message(F.text == "🔙 Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_kb())

@dp.message(F.text == "🔙 Главное меню")
async def go_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_kb())

# ══ ДОХОД ═════════════════════════════════════════════════════

@dp.message(F.text == "💰 Доход")
async def income_start(message: Message, state: FSMContext):
    await message.answer("Введите сумму дохода:", reply_markup=cancel_kb())
    await state.set_state(IncomeState.amount)

@dp.message(IncomeState.amount)
async def income_amount(message: Message, state: FSMContext):
    try:
        amt = float(message.text.replace(",", ".").replace(" ", ""))
        if amt <= 0: raise ValueError
    except:
        await message.answer("❌ Введите корректную сумму:"); return
    await state.update_data(amount=amt)
    await message.answer("Выберите категорию:", reply_markup=income_cats_kb())
    await state.set_state(IncomeState.category)

@dp.message(IncomeState.category, F.text.in_(INCOME_CATS))
async def income_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Добавьте заметку или пропустите:", reply_markup=skip_cancel_kb())
    await state.set_state(IncomeState.note)

@dp.message(IncomeState.category)
async def income_cat_wrong(message: Message):
    if message.text != "🔙 Отмена":
        await message.answer("Выберите категорию из списка:")

@dp.message(IncomeState.note)
async def income_note(message: Message, state: FSMContext):
    d = await state.get_data()
    note = "" if message.text == "⏭ Пропустить" else message.text
    data = load_data()
    user = get_user(data, message.from_user.id)
    user["incomes"].append({
        "amount": d["amount"], "category": d["category"],
        "note": note, "date": date.today().strftime("%d.%m.%Y")
    })
    save_data(data)
    total = sum(i["amount"] for i in user["incomes"])
    await state.clear()
    await message.answer(
        f"✅ Доход добавлен!\n"
        f"💰 {d['amount']:,.0f} — {d['category']}\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"Всего доходов: {total:,.0f}",
        reply_markup=main_kb()
    )

# ══ РАСХОД ════════════════════════════════════════════════════

@dp.message(F.text == "💸 Расход")
async def expense_start(message: Message, state: FSMContext):
    await message.answer("Введите сумму расхода:", reply_markup=cancel_kb())
    await state.set_state(ExpenseState.amount)

@dp.message(ExpenseState.amount)
async def expense_amount(message: Message, state: FSMContext):
    try:
        amt = float(message.text.replace(",", ".").replace(" ", ""))
        if amt <= 0: raise ValueError
    except:
        await message.answer("❌ Введите корректную сумму:"); return
    await state.update_data(amount=amt)
    await message.answer("Выберите категорию:", reply_markup=expense_cats_kb())
    await state.set_state(ExpenseState.category)

@dp.message(ExpenseState.category, F.text.in_(EXPENSE_CATS))
async def expense_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("Добавьте заметку или пропустите:", reply_markup=skip_cancel_kb())
    await state.set_state(ExpenseState.note)

@dp.message(ExpenseState.category)
async def expense_cat_wrong(message: Message):
    if message.text != "🔙 Отмена":
        await message.answer("Выберите категорию из списка:")

@dp.message(ExpenseState.note)
async def expense_note(message: Message, state: FSMContext):
    d = await state.get_data()
    note = "" if message.text == "⏭ Пропустить" else message.text
    data = load_data()
    user = get_user(data, message.from_user.id)
    user["expenses"].append({
        "amount": d["amount"], "category": d["category"],
        "note": note, "date": date.today().strftime("%d.%m.%Y")
    })
    save_data(data)
    total = sum(e["amount"] for e in user["expenses"])
    await state.clear()
    await message.answer(
        f"✅ Расход добавлен!\n"
        f"💸 {d['amount']:,.0f} — {d['category']}\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"Всего расходов: {total:,.0f}",
        reply_markup=main_kb()
    )

# ══ КРЕДИТЫ ═══════════════════════════════════════════════════

@dp.message(F.text == "🏦 Кредиты")
async def loans_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏦 Управление кредитами:", reply_markup=loan_menu_kb())

@dp.message(F.text == "➕ Новый кредит")
async def loan_new(message: Message, state: FSMContext):
    await message.answer(
        "Введите название кредита:\n"
        "Например: Ипотека, Автокредит, Потребительский",
        reply_markup=cancel_kb()
    )
    await state.set_state(LoanState.name)

@dp.message(LoanState.name)
async def loan_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите сумму кредита (сомони/рублей/сум):")
    await state.set_state(LoanState.amount)

@dp.message(LoanState.amount)
async def loan_amount(message: Message, state: FSMContext):
    try:
        amt = float(message.text.replace(",", ".").replace(" ", ""))
        if amt <= 0: raise ValueError
    except:
        await message.answer("❌ Введите корректную сумму:"); return
    await state.update_data(amount=amt)
    await message.answer("Введите годовую процентную ставку:\nНапример: 18 или 24.5")
    await state.set_state(LoanState.rate)

@dp.message(LoanState.rate)
async def loan_rate(message: Message, state: FSMContext):
    try:
        rate = float(message.text.replace(",", "."))
        if rate < 0 or rate > 200: raise ValueError
    except:
        await message.answer("❌ Введите ставку (например: 18.5):"); return
    await state.update_data(rate=rate)
    await message.answer("Введите срок кредита в месяцах:\nНапример: 12, 24, 36, 60")
    await state.set_state(LoanState.months)

@dp.message(LoanState.months)
async def loan_months(message: Message, state: FSMContext):
    try:
        months = int(message.text.strip())
        if months <= 0 or months > 600: raise ValueError
    except:
        await message.answer("❌ Введите число месяцев (например: 24):"); return
    await state.update_data(months=months)
    await message.answer(
        "Введите дату выдачи кредита:\n"
        "Формат: ДД.ММ.ГГГГ\n"
        "Например: 15.01.2024"
    )
    await state.set_state(LoanState.start_date)

@dp.message(LoanState.start_date)
async def loan_start_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except:
        await message.answer("❌ Формат: ДД.ММ.ГГГГ (например: 15.01.2024):"); return
    await state.update_data(start_date=message.text.strip())
    await message.answer("Введите день ежемесячного платежа (1-28):")
    await state.set_state(LoanState.payment_day)

@dp.message(LoanState.payment_day)
async def loan_payment_day(message: Message, state: FSMContext):
    try:
        day = int(message.text.strip())
        if day < 1 or day > 28: raise ValueError
    except:
        await message.answer("❌ Введите число от 1 до 28:"); return

    d = await state.get_data()
    schedule = build_schedule(d["amount"], d["rate"], d["months"], d["start_date"], day)
    monthly = schedule[0]["total"]

    data = load_data()
    user = get_user(data, message.from_user.id)
    user["loans"].append({
        "name": d["name"],
        "amount": d["amount"],
        "rate": d["rate"],
        "months": d["months"],
        "start_date": d["start_date"],
        "payment_day": day,
        "monthly": monthly,
        "schedule": schedule,
        "early_payments": [],
    })
    save_data(data)
    await state.clear()

    total_pay = sum(s["total"] for s in schedule)
    overpay = round(total_pay - d["amount"], 2)

    await message.answer(
        f"✅ Кредит добавлен!\n\n"
        f"🏦 {d['name']}\n"
        f"💰 Сумма: {d['amount']:,.0f}\n"
        f"📊 Ставка: {d['rate']}% годовых\n"
        f"📅 Срок: {d['months']} мес. (с {d['start_date']})\n"
        f"💳 Ежемесячный платёж: {monthly:,.0f}\n"
        f"💸 Переплата: {overpay:,.0f}",
        reply_markup=loan_menu_kb()
    )

# ── Список кредитов ───────────────────────────────────────────

@dp.message(F.text == "📋 Мои кредиты")
async def list_loans(message: Message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    loans = user.get("loans", [])
    if not loans:
        await message.answer("У вас нет кредитов.", reply_markup=loan_menu_kb()); return
    await message.answer("Выберите кредит:", reply_markup=loans_inline(loans))

@dp.callback_query(F.data == "loan_list")
async def cb_loan_list(callback):
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loans = user.get("loans", [])
    await callback.message.edit_text("Выберите кредит:", reply_markup=loans_inline(loans))

@dp.callback_query(F.data.startswith("loan:"))
async def cb_loan_detail(callback):
    idx = int(callback.data.split(":")[1])
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    schedule = loan.get("schedule", [])
    paid_count = sum(1 for s in schedule if s["paid"])
    remaining = get_loan_remaining(loan)
    next_pay = next((s for s in schedule if not s["paid"]), None)

    text = (
        f"🏦 <b>{loan['name']}</b>\n\n"
        f"💰 Сумма: {loan['amount']:,.0f}\n"
        f"📊 Ставка: {loan['rate']}% годовых\n"
        f"📅 Дата выдачи: {loan['start_date']}\n"
        f"⏳ Срок: {loan['months']} мес.\n"
        f"💳 Ежемес. платёж: {loan['monthly']:,.0f}\n"
        f"✅ Оплачено траншей: {paid_count}/{len(schedule)}\n"
        f"💵 Остаток долга: {remaining:,.0f}\n"
    )
    if next_pay:
        text += f"📌 Следующий платёж: {next_pay['date']} — {next_pay['total']:,.0f}"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=loan_detail_inline(idx))

# ── График платежей ───────────────────────────────────────────

@dp.callback_query(F.data.startswith("schedule:"))
async def cb_schedule(callback):
    parts = callback.data.split(":")
    idx = int(parts[1])
    page = int(parts[2])
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    schedule = loan.get("schedule", [])
    per_page = 6
    start = page * per_page
    end = min(start + per_page, len(schedule))
    total_pages = math.ceil(len(schedule) / per_page)

    lines = [f"📅 <b>График: {loan['name']}</b> (стр. {page+1}/{total_pages})\n"]
    for s in schedule[start:end]:
        status = "✅" if s["paid"] else "⏳"
        lines.append(
            f"{status} Мес.{s['month']} | {s['date']}\n"
            f"   💳 {s['total']:,.0f} (долг: {s['principal']:,.0f} + %: {s['interest']:,.0f})\n"
            f"   Остаток: {s['balance']:,.0f}"
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"schedule:{idx}:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"schedule:{idx}:{page+1}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        nav_buttons,
        [InlineKeyboardButton(text="🔙 К кредиту", callback_data=f"loan:{idx}")]
    ] if nav_buttons else [[InlineKeyboardButton(text="🔙 К кредиту", callback_data=f"loan:{idx}")]])

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)

# ── Оплата транша ─────────────────────────────────────────────

@dp.callback_query(F.data.startswith("tranche:"))
async def cb_tranche_start(callback, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    schedule = loan.get("schedule", [])
    unpaid = [(i, s) for i, s in enumerate(schedule) if not s["paid"]]

    if not unpaid:
        await callback.answer("Все транши оплачены!"); return

    next_i, next_s = unpaid[0]
    await state.update_data(loan_idx=idx, month_idx=next_i)
    await state.set_state(TrancheState.loan_idx)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Оплатить {next_s['total']:,.0f} (мес.{next_s['month']})", callback_data=f"pay_tranche:{idx}:{next_i}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"loan:{idx}")],
    ])
    await callback.message.edit_text(
        f"💳 <b>Оплата транша</b>\n\n"
        f"Кредит: {loan['name']}\n"
        f"Месяц: {next_s['month']} | Дата: {next_s['date']}\n"
        f"Сумма: {next_s['total']:,.0f}\n"
        f"  └ Основной долг: {next_s['principal']:,.0f}\n"
        f"  └ Проценты: {next_s['interest']:,.0f}\n"
        f"Остаток после оплаты: {next_s['balance']:,.0f}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.startswith("pay_tranche:"))
async def cb_pay_tranche(callback, state: FSMContext):
    parts = callback.data.split(":")
    loan_idx = int(parts[1])
    month_idx = int(parts[2])
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][loan_idx]
    loan["schedule"][month_idx]["paid"] = True
    paid_amount = loan["schedule"][month_idx]["total"]
    save_data(data)
    await state.clear()

    paid_count = sum(1 for s in loan["schedule"] if s["paid"])
    remaining = sum(s["total"] for s in loan["schedule"] if not s["paid"])

    await callback.message.edit_text(
        f"✅ <b>Транш оплачен!</b>\n\n"
        f"🏦 {loan['name']}\n"
        f"💳 Оплачено: {paid_amount:,.0f}\n"
        f"✅ Оплачено траншей: {paid_count}/{len(loan['schedule'])}\n"
        f"💵 Осталось выплатить: {remaining:,.0f}",
        parse_mode="HTML",
        reply_markup=loan_detail_inline(loan_idx)
    )

# ── Досрочное погашение ───────────────────────────────────────

@dp.callback_query(F.data.startswith("early:"))
async def cb_early_start(callback, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][idx]
    remaining = get_loan_remaining(loan)

    await state.update_data(loan_idx=idx)
    await state.set_state(EarlyPayState.amount)
    await callback.message.answer(
        f"💳 <b>Досрочное погашение</b>\n\n"
        f"Кредит: {loan['name']}\n"
        f"Остаток долга: {remaining:,.0f}\n\n"
        f"Введите сумму досрочного платежа:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@dp.message(EarlyPayState.amount)
async def early_amount(message: Message, state: FSMContext):
    try:
        amt = float(message.text.replace(",", ".").replace(" ", ""))
        if amt <= 0: raise ValueError
    except:
        await message.answer("❌ Введите корректную сумму:"); return

    d = await state.get_data()
    await state.update_data(amount=amt)
    await state.set_state(EarlyPayState.choice)

    data = load_data()
    user = get_user(data, message.from_user.id)
    loan = user["loans"][d["loan_idx"]]

    await message.answer(
        f"💰 Сумма досрочного платежа: {amt:,.0f}\n\n"
        f"Как пересчитать кредит?",
        reply_markup=early_options_inline(d["loan_idx"])
    )

@dp.callback_query(F.data.startswith("early_term:"))
async def early_reduce_term(callback, state: FSMContext):
    await _process_early(callback, state, reduce_term=True)

@dp.callback_query(F.data.startswith("early_pay:"))
async def early_reduce_pay(callback, state: FSMContext):
    await _process_early(callback, state, reduce_term=False)

async def _process_early(callback, state: FSMContext, reduce_term: bool):
    fsm = await state.get_data()
    if "amount" not in fsm:
        await callback.answer("Начните заново"); await state.clear(); return

    loan_idx = int(callback.data.split(":")[1])
    early_amt = fsm["amount"]
    data = load_data()
    user = get_user(data, callback.from_user.id)
    loan = user["loans"][loan_idx]
    schedule = loan["schedule"]

    paid_months = sum(1 for s in schedule if s["paid"])
    remaining_balance = get_loan_remaining(loan) - early_amt

    if remaining_balance <= 0:
        loan["schedule"] = [dict(s, paid=True) for s in schedule]
        loan["early_payments"].append({"amount": early_amt, "date": str(date.today()), "type": "full"})
        save_data(data)
        await state.clear()
        await callback.message.edit_text(
            f"🎉 <b>Кредит полностью погашен!</b>\n\n"
            f"🏦 {loan['name']}\n"
            f"✅ Досрочный платёж: {early_amt:,.0f}",
            parse_mode="HTML"
        )
        return

    remaining_months = loan["months"] - paid_months
    rate = loan["rate"]
    start = date.today()

    if reduce_term:
        # Тот же платёж — считаем новый срок
        old_monthly = loan["monthly"]
        r = rate / 100 / 12
        if r == 0:
            new_term = math.ceil(remaining_balance / old_monthly)
        else:
            val = old_monthly / (old_monthly - r * remaining_balance)
            if val <= 0: val = 1.0001
            new_term = math.ceil(math.log(val) / math.log(1 + r))
        new_term = max(1, new_term)
        new_monthly = calc_annuity(remaining_balance, rate, new_term)
    else:
        new_term = remaining_months
        new_monthly = calc_annuity(remaining_balance, rate, new_term)

    new_schedule = build_schedule(
        remaining_balance, rate, new_term,
        start.strftime("%d.%m.%Y"), loan["payment_day"]
    )
    for i, s in enumerate(new_schedule):
        s["month"] = paid_months + i + 1

    paid_part = [s for s in schedule if s["paid"]]
    loan["schedule"] = paid_part + new_schedule
    loan["months"] = paid_months + new_term
    loan["monthly"] = new_monthly
    loan["early_payments"].append({
        "amount": early_amt, "date": str(date.today()),
        "type": "reduce_term" if reduce_term else "reduce_pay"
    })
    save_data(data)
    await state.clear()

    option = "Срок уменьшен" if reduce_term else "Платёж уменьшен"
    await callback.message.edit_text(
        f"✅ <b>Досрочный платёж внесён!</b>\n\n"
        f"🏦 {loan['name']}\n"
        f"💳 Внесено: {early_amt:,.0f}\n"
        f"💵 Новый остаток: {remaining_balance:,.0f}\n"
        f"📊 {option}\n"
        f"📅 Новый срок: {new_term} мес.\n"
        f"💳 Новый платёж: {new_monthly:,.0f}/мес",
        parse_mode="HTML",
        reply_markup=loan_detail_inline(loan_idx)
    )

# ══ БАЛАНС ════════════════════════════════════════════════════

@dp.message(F.text == "📊 Баланс")
async def balance(message: Message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    total_inc = sum(i["amount"] for i in user["incomes"])
    total_exp = sum(e["amount"] for e in user["expenses"])
    bal = total_inc - total_exp
    emoji = "✅" if bal >= 0 else "⚠️"

    # По категориям расходов (топ-5)
    cats = {}
    for e in user["expenses"]:
        cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
    top_cats = sorted(cats.items(), key=lambda x: -x[1])[:5]

    lines = [
        "📊 <b>Ваш баланс</b>\n",
        f"💰 Доходы: <b>{total_inc:,.0f}</b>",
        f"💸 Расходы: <b>{total_exp:,.0f}</b>",
        f"{emoji} Баланс: <b>{bal:,.0f}</b>",
    ]
    if top_cats:
        lines.append("\n📂 <b>Топ расходов:</b>")
        for cat, amt in top_cats:
            pct = amt / total_exp * 100 if total_exp else 0
            lines.append(f"  {cat}: {amt:,.0f} ({pct:.0f}%)")

    loans = user.get("loans", [])
    if loans:
        total_monthly = sum(l["monthly"] for l in loans)
        lines.append(f"\n🏦 <b>Кредиты:</b>")
        for loan in loans:
            remaining = get_loan_remaining(loan)
            lines.append(f"  {loan['name']}: {loan['monthly']:,.0f}/мес | долг: {remaining:,.0f}")
        lines.append(f"  Итого платежей: <b>{total_monthly:,.0f}/мес</b>")
        if total_inc > 0:
            load_pct = total_monthly / total_inc * 100
            load_e = "🟢" if load_pct < 30 else "🟡" if load_pct < 50 else "🔴"
            lines.append(f"  {load_e} Долговая нагрузка: {load_pct:.0f}%")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_kb())

# ══ ИСТОРИЯ ═══════════════════════════════════════════════════

@dp.message(F.text == "📋 История")
async def history(message: Message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    lines = ["📋 <b>Последние операции</b>\n"]

    incomes = user["incomes"][-8:]
    if incomes:
        lines.append("💰 <b>Доходы:</b>")
        for i in reversed(incomes):
            note = f" ({i['note']})" if i.get("note") else ""
            lines.append(f"  {i['date']} | {i['amount']:,.0f}{note}\n  {i['category']}")

    expenses = user["expenses"][-8:]
    if expenses:
        lines.append("\n💸 <b>Расходы:</b>")
        for e in reversed(expenses):
            note = f" ({e['note']})" if e.get("note") else ""
            lines.append(f"  {e['date']} | {e['amount']:,.0f}{note}\n  {e['category']}")

    if not incomes and not expenses:
        lines.append("Нет операций.")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_kb())

# ══ ЗАПУСК ════════════════════════════════════════════════════
#
# Два режима:
#   1) Webhook (production, Render/Vercel/любой PaaS):
#         задайте WEBHOOK_URL в env → бот поднимет aiohttp-сервер
#         и попросит Telegram слать апдейты на этот URL.
#   2) Polling (локальная разработка):
#         WEBHOOK_URL не задан → бот сам опрашивает Telegram.
# ══════════════════════════════════════════════════════════════

async def _on_startup(bot: Bot):
    full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(full_url, drop_pending_updates=True,
                          allowed_updates=dp.resolve_used_update_types())
    me = await bot.me()
    log.info("Webhook установлен: %s (бот @%s)", full_url, me.username)


async def _on_shutdown(bot: Bot):
    log.info("Останавливаю webhook…")
    await bot.delete_webhook()


async def _health(_request):
    """Render и cron-job.org дёргают этот URL, чтобы сервис не засыпал."""
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
    """Polling + минимальный aiohttp на PORT (для Render-health, пока не задан WEBHOOK_URL)."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    log.info("Health-сервер на :%s, polling запущен (WEBHOOK_URL не задан)", PORT)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()


async def run_polling():
    log.info("Запускаю polling (локальный режим)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    if WEBHOOK_URL:
        run_webhook()
    elif os.environ.get("PORT"):
        # Render/Heroku-подобный хостинг без WEBHOOK_URL — даём health-эндпоинт + polling
        asyncio.run(_run_polling_with_health())
    else:
        asyncio.run(run_polling())
