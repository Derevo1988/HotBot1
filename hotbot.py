import os
import asyncio
import feedparser
import aiohttp
from aiohttp import web
from pathlib import Path
from telethon import TelegramClient, events
from datetime import datetime
from bs4 import BeautifulSoup
import re
from collections import Counter

# 1️⃣ Загружаем .env (если есть, для локального запуска)
from dotenv import load_dotenv
load_dotenv()

# 2️⃣ Функция безопасного получения переменных
def get_env_var(name, cast_type=str):
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"❌ Переменная {name} не найдена в окружении")
    try:
        return cast_type(value)
    except ValueError:
        raise ValueError(f"❌ Значение переменной {name} ('{value}') не соответствует типу {cast_type.__name__}")

# 3️⃣ Получаем переменные окружения
api_id = get_env_var("API_ID", int)
api_hash = get_env_var("API_HASH")
bot_token = get_env_var("BOT_TOKEN")
user_id = get_env_var("USER_ID", int)

# 4️⃣ Создаём Telegram клиента как БОТА
client = TelegramClient('monitor_session', api_id, api_hash)

# 5️⃣ Ключевые слова для поиска
keywords = [
    "умер", "умер актер", "усольцевы", "зеленская", "умер писатель", "туристка", "умер заслуженный",
    "умер певец", "умер артист", "мертвым", "тело", "скончался", "ушел из жизни",
    "dead", "passed away"
]

# 6️⃣ RSS фиды для мониторинга
rss_urls = [
    "https://www.tass.ru/rss/v2.xml",
    "https://ria.ru/export/rss2/index.xml",
    "https://www.interfax.ru/rss.asp",
    "https://russian.rt.com/rss",
    "https://lenta.ru/rss/news",
    "http://feeds.reuters.com/Reuters/worldNews",
    "https://apnews.com/apf-topnews?format=rss"
]

# 7️⃣ Хранилище уже отправленных ссылок
sent_links = set()

# 8️⃣ Функция проверки RSS с логированием
async def check_rss():
    new_links_count = 0
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.title.lower()
                if any(word in title for word in keywords):
                    if entry.link not in sent_links:
                        sent_links.add(entry.link)
                        new_links_count += 1
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔔 [RSS] Новость: {entry.title}")
                        await client.send_message(
                            user_id,
                            f"⚡ [RSS] {entry.title}\n{entry.link}"
                        )
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Ошибка при обработке RSS {url}: {e}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Проверка RSS завершена. Новых ссылок: {new_links_count}")

# 9️⃣ Слежение за страницей памяти на kino-teatr.ru
mourn_url = "https://www.kino-teatr.ru/mourn/y2025/m11/"
known_profiles = set()

async def check_mourn_page():
    global known_profiles
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(mourn_url) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")

                    profile_links = [
                        "https://www.kino-teatr.ru" + a["href"]
                        for a in soup.select("div.actor_list a")
                        if a.get("href") and a["href"].startswith("/kino/acter/")
                    ]

                    new_profiles = [link for link in profile_links if link not in known_profiles]

                    for link in new_profiles:
                        known_profiles.add(link)
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔔 [MOURN] Новая анкета: {link}")
                        await client.send_message(
                            user_id,
                            f"⚰️ [MOURN] Новая анкета опубликована:\n{link}"
                        )
                else:
                    print(f"❌ Ошибка загрузки {mourn_url}: HTTP {resp.status}")
    except Exception as e:
        print(f"❌ Ошибка при проверке {mourn_url}: {e}")

# 🔟 Проверка ключевых слов на tass.ru/feed
async def check_tass_keywords():
    url = "https://tass.ru/feed"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ Ошибка загрузки TASS: HTTP {resp.status}")
                    return

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                articles = soup.find_all("article")
                for article in articles:
                    title_tag = article.find("a")
                    if not title_tag:
                        continue

                    title = title_tag.get_text(" ", strip=True).lower()
                    link = title_tag["href"]

                    if not link.startswith("http"):
                        link = "https://tass.ru" + link

                    if any(word in title for word in keywords):
                        if link not in sent_links:
                            sent_links.add(link)
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔔 [TASS] Новость: {title}")
                            await client.send_message(
                                user_id,
                                f"⚡ [TASS] {title}\n{link}"
                            )
    except Exception as e:
        print(f"❌ Ошибка при проверке TASS: {e}")

# 1️⃣1️⃣ Цикл проверки
async def periodic_rss_check():
    while True:
        await check_rss()
        await check_mourn_page()
        await check_tass_keywords()
        await asyncio.sleep(60)

# 1️⃣2️⃣ Webhook сервер
async def webhook(request):
    try:
        data = await request.json()
        # Обрабатываем обновление через Telethon
        updates = [data] if isinstance(data, dict) else data.get('updates', [])
        for update in updates:
            event = events.NewMessage.Event(update)
            await client._handle_update(event)
        return web.Response(text="OK")
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return web.Response(text="Error", status=500)

# 1️⃣3️⃣ Установка webhook через Bot API
async def set_webhook_manually(bot_token, webhook_url):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}"
        async with session.get(url) as resp:
            result = await resp.json()
            if result.get("ok"):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Webhook установлен: {webhook_url}")
            else:
                print(f"❌ Ошибка установки webhook: {result}")

# 1️⃣4️⃣ Запуск бота
async def main():
    # Запускаем клиент
    await client.start(bot_token=bot_token)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Бот запущен")

    # Устанавливаем webhook
    webhook_url = os.getenv("WEBHOOK_URL", "https://hotbot1-4.onrender.com/webhook")
    await set_webhook_manually(bot_token, webhook_url)

    # Запускаем периодическую проверку
    asyncio.create_task(periodic_rss_check())

    # Запускаем aiohttp сервер
    app = web.Application()
    app.router.add_post('/webhook', webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Webhook сервер запущен на порту 10000")

    # Держим приложение активным
    await asyncio.Event().wait()

# 1️⃣5️⃣ Команда /ping
@client.on(events.NewMessage(pattern="/ping"))
async def ping_handler(event):
    await event.respond("pong ✅")

if __name__ == "__main__":
    client.loop.run_until_complete(main())
