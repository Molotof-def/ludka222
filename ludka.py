import os
import random
import asyncio
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

# Загружаем переменные из .env, если запускаем локально
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная BOT_TOKEN не установлена!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

MIN_ID = 1
MAX_ID = 482271
MAX_TRIES = 25

GIFTS_POOL = {
    "ChillFlame": "Chill Flame",
    "ViceCream": "Vice Cream"
}

async def nft_exists(session: aiohttp.ClientSession, gift_slug: str, nft_id: int) -> bool:
    url = f"https://t.me/nft/{gift_slug}-{nft_id}"
    try:
        async with session.get(url, timeout=7) as resp:
            if resp.status != 200:
                return False
            text = await resp.text()
            display_name = GIFTS_POOL[gift_slug]
            return gift_slug in text and f"{display_name} #{nft_id}" in text
    except Exception:
        return False

async def get_random_real_gift():
    async with aiohttp.ClientSession() as session:
        for _ in range(MAX_TRIES):
            nft_id = random.randint(MIN_ID, MAX_ID)
            gift_slug = random.choice(list(GIFTS_POOL.keys()))
            
            if await nft_exists(session, gift_slug, nft_id):
                display_name = GIFTS_POOL[gift_slug]
                return f"{display_name} #{nft_id}", f"https://t.me/nft/{gift_slug}-{nft_id}"
    return None, None

@dp.message(F.dice)
async def handle_dice(message: Message):
    # Игнорируем пересылки и не-777
    if message.forward_origin is not None or message.dice.value != 64:
        return

    name, link = await get_random_real_gift()
    if not link:
        return

    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    await message.answer(
        f"🎁 {username} выбил 777!\n\n"
        f"Подарок: {name}\n"
        f"🔗 {link}\n\n"
        f"✅ Подарок отправлен автоматически!"
    )

# --- Вспомогательный веб-сервер для прохождения проверок Render ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render автоматически передает порт через переменную окружения PORT
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Веб-сервер запущен на порту {port}")

async def main():
    await start_web_server()
    print("✅ Бот готов и слушает сообщения...")
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())