from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

def main_kb(authed=True):
    if not authed:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Войти (поделиться номером)", request_contact=True)]
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Доход"), KeyboardButton(text="💸 Расход")],
        [KeyboardButton(text="🏦 Кредиты"), KeyboardButton(text="📊 Баланс")],
        [KeyboardButton(text="📈 AI Аналитика"), KeyboardButton(text="🤖 AI Советник")],
        [KeyboardButton(text="💱 Валюта и золото"), KeyboardButton(text="🌤 Погода")],
        [KeyboardButton(text="📋 Отчёт"), KeyboardButton(text="⏰ Напоминания")],
    ], resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Отмена")]], resize_keyboard=True)

def skip_cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Пропустить"), KeyboardButton(text="🔙 Отмена")]
    ], resize_keyboard=True)

def cats_kb(cats: list, last: str = None):
    rows = []
    if last:
        rows.append([KeyboardButton(text=f"↩️ {last}")])
    for i in range(0, len(cats), 2):
        row = [KeyboardButton(text=cats[i])]
        if i+1 < len(cats):
            row.append(KeyboardButton(text=cats[i+1]))
        rows.append(row)
    rows.append([KeyboardButton(text="🔙 Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def banks_kb(banks: list):
    rows = []
    for i in range(0, len(banks), 2):
        row = [KeyboardButton(text=banks[i])]
        if i+1 < len(banks):
            row.append(KeyboardButton(text=banks[i+1]))
        rows.append(row)
    rows.append([KeyboardButton(text="🔙 Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def loans_inline(loans: list) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text=f"🏦 {l['name']} ({l['bank']})", callback_data=f"loan:{i}")]
            for i, l in enumerate(loans) if l.get("active", True)]
    return InlineKeyboardMarkup(inline_keyboard=btns or [[InlineKeyboardButton(text="Нет активных кредитов", callback_data="noop")]])

def loan_detail_inline(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 График", callback_data=f"sched:{idx}"),
         InlineKeyboardButton(text="💳 Транш", callback_data=f"transh:{idx}")],
        [InlineKeyboardButton(text="⚡ Досрочно", callback_data=f"early:{idx}"),
         InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close:{idx}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="loan_list")],
    ])

def early_inline(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📉 Уменьшить срок", callback_data=f"early_term:{idx}")],
        [InlineKeyboardButton(text="💰 Уменьшить платёж", callback_data=f"early_pay:{idx}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"loan:{idx}")],
    ])

def period_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Текущий месяц", callback_data="period:month"),
         InlineKeyboardButton(text="📅 3 месяца", callback_data="period:3m")],
        [InlineKeyboardButton(text="📅 6 месяцев", callback_data="period:6m"),
         InlineKeyboardButton(text="📅 Год", callback_data="period:year")],
        [InlineKeyboardButton(text="📊 Всё время", callback_data="period:all")],
        [InlineKeyboardButton(text="📥 Скачать Excel", callback_data="period:excel")],
    ])

def reminder_inline(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплачено", callback_data=f"rem_paid:{idx}"),
         InlineKeyboardButton(text="❌ Удалить", callback_data=f"rem_del:{idx}")],
    ])

def reset_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Сбросить ВСЕ данные", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="reset_cancel")],
    ])
