import aiohttp
from datetime import datetime

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

async def get_exchange_rates():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(CBU_URL, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
        rates = {}
        wanted = {"USD": "USD", "EUR": "EUR", "RUB": "RUB", "CNY": "CNY", "KZT": "KZT"}
        for item in data:
            code = item.get("Ccy", "")
            if code in wanted:
                rates[code] = {"rate": float(item["Rate"]), "diff": float(item.get("Diff", 0))}
        return rates
    except Exception as e:
        return {}

async def get_gold_price():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.metals.live/v1/spot/gold",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                data = await r.json()
        return data[0].get("gold") if data else None
    except:
        return None

async def get_weather(city: str, api_key: str):
    if not api_key:
        return None
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ru"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
        if data.get("cod") == 200:
            return {
                "city": data["name"],
                "temp": round(data["main"]["temp"]),
                "feels": round(data["main"]["feels_like"]),
                "desc": data["weather"][0]["description"].capitalize(),
                "humidity": data["main"]["humidity"],
                "wind": round(data["wind"]["speed"])
            }
    except:
        return None

async def ai_analyze(incomes: list, expenses: list, loans: list, api_key: str) -> str:
    if not api_key:
        total_i = sum(x["amount"] for x in incomes)
        total_e = sum(x["amount"] for x in expenses)
        bal = total_i - total_e
        cats = {}
        for e in expenses:
            cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
        top = sorted(cats.items(), key=lambda x: -x[1])[:3]
        lines = [
            f"📊 Доходы: {total_i:,.0f} сум",
            f"💸 Расходы: {total_e:,.0f} сум",
            f"💰 Баланс: {bal:,.0f} сум",
            f"\nТоп расходов:"
        ]
        for cat, amt in top:
            pct = amt / total_e * 100 if total_e else 0
            lines.append(f"  • {cat}: {amt:,.0f} ({pct:.0f}%)")
        if bal < 0:
            lines.append("\n⚠️ Расходы превышают доходы!")
        elif bal < total_i * 0.1:
            lines.append("\n⚠️ Сбережения менее 10% дохода.")
        else:
            lines.append(f"\n✅ Норма сбережения: {bal/total_i*100:.0f}%")
        return "\n".join(lines)

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        total_i = sum(x["amount"] for x in incomes)
        total_e = sum(x["amount"] for x in expenses)
        cats = {}
        for e in expenses:
            cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
        prompt = f"""Ты финансовый аналитик. Проанализируй данные пользователя из Узбекистана:
Доходы: {total_i:,.0f} сум
Расходы: {total_e:,.0f} сум  
Расходы по категориям: {dict(sorted(cats.items(), key=lambda x:-x[1]))}
Кредитов: {len(loans)}
Дай краткий анализ (3-4 предложения) и 3 конкретных совета. Отвечай на русском."""
        r = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка AI: {e}"

async def ai_chat(question: str, context: dict, api_key: str) -> str:
    if not api_key:
        return "🤖 AI советник требует OpenAI API ключ. Добавьте OPENAI_API_KEY в config.py"
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        r = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Ты финансовый советник. Контекст: доходы {context.get('income',0):,.0f} сум, расходы {context.get('expense',0):,.0f} сум, кредитов {context.get('loans',0)}. Отвечай кратко на русском."},
                {"role": "user", "content": question}
            ],
            max_tokens=400
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка AI: {e}"
