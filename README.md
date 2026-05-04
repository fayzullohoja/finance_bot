# Finance Bot — Webhook + бесплатный хостинг на Render

Telegram-бот учёта финансов. Один файл (`bot.py`), хранение в `data.json`,
работает в **webhook-режиме** на бесплатном тарифе Render.

## Локальный запуск (polling, для отладки)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
BOT_TOKEN=ваш_токен python bot.py
```

Когда `WEBHOOK_URL` не задан — бот работает в polling и сам опрашивает Telegram.

## Деплой на Render (бесплатно, 24/7)

### 1. Залить код на GitHub
```bash
cd ~/Desktop/finance_bot_v2
git init && git add . && git commit -m "init"
gh repo create finance-bot --public --source=. --push   # или вручную
```

### 2. Создать сервис на Render
1. Открыть https://dashboard.render.com → **New** → **Web Service**
2. Подключить GitHub-репозиторий `finance-bot`
3. Render сам подхватит `render.yaml`. Подтвердить → **Create**

### 3. Задать переменные окружения
В Render Dashboard → **Environment**:
- `BOT_TOKEN` = ваш токен от BotFather
- `WEBHOOK_URL` = URL сервиса (например `https://finance-bot-xxxx.onrender.com`),
  он появится после первого деплоя

После сохранения Render передеплоит сервис. В логах должна быть строка:
```
Webhook установлен: https://finance-bot-xxxx.onrender.com/webhook (бот @имя_бота)
```

### 4. Не дать сервису заснуть (Render free спит после 15 мин простоя)
1. Открыть https://cron-job.org → зарегистрироваться → **Create cronjob**
2. URL: `https://finance-bot-xxxx.onrender.com/health`
3. Расписание: каждые 10 минут
4. Сохранить

Готово. Бот живёт 24/7 бесплатно.

## Важно про данные

`data.json` лежит на эфемерной файловой системе Render free — он сохраняется
во время работы, но **обнуляется при каждом передеплое или рестарте**.

Для надёжного хранения позже подключим Postgres на Supabase free —
структура простая, миграция займёт ~30 минут.
