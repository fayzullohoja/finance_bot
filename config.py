import os

# Секреты — из переменных окружения (Render → Environment).
# Не коммитьте реальные значения в git.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "").strip()
WEATHER_CITY = os.environ.get("WEATHER_CITY", "Tashkent").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Положите его в переменные окружения.")

INCOME_CATEGORIES = [
    "Зарплата", "Аванс", "Премия", "Бонус", "Командировочные",
    "Бизнес доход", "Дивиденды", "Аренда", "Фриланс",
    "Продажа имущества", "Подарок", "Перевод от родных",
    "Возврат долга", "Кэшбэк", "Проценты по вкладу", "Прочее"
]

EXPENSE_CATEGORIES = [
    # Еда и продукты
    "Продукты питания", "Рестораны и кафе", "Фастфуд", "Доставка еды",
    # Транспорт
    "Такси", "Общественный транспорт", "Бензин", "Парковка", "Авиабилеты",
    # Жильё
    "Аренда жилья", "Коммунальные услуги", "Электричество", "Газ", "Интернет",
    # Кредиты и финансы
    "Погашение кредита", "Страховка", "Банковские комиссии",
    # Здоровье
    "Медицина и врачи", "Аптека", "Спортзал",
    # Семья и дети
    "Детский сад / школа", "Репетитор", "Детские товары",
    # Одежда
    "Одежда и обувь", "Аксессуары",
    # Развлечения
    "Кино / театр", "Подписки (Netflix, Spotify)", "Игры", "Хобби",
    # Образование
    "Курсы и обучение", "Книги",
    # Техника
    "Электроника", "Ремонт техники",
    # Другое
    "Подарки", "Благотворительность", "Штрафы", "Прочее"
]

UZB_BANKS = [
    "Kapitalbank", "Ipak Yo'li Bank", "Hamkorbank",
    "Asaka Bank", "Uzpromstroybank", "Xalq Bank",
    "Agrobank", "Ziraat Bank Uzbekistan", "Aloqabank",
    "Microcreditbank", "Turonbank", "Universal Bank",
    "Davr Bank", "Savdogarbank", "Madad Invest Bank",
    "Tenge Bank", "Orient Finance Bank", "Apex Bank",
    "Anorbank", "TBC Bank Uzbekistan", "OTP Bank Uzbekistan",
    "Другой банк"
]

CURRENCIES = ["USD", "EUR", "RUB", "CNY", "KZT"]
