import os
import random
import asyncio
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
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

async def main():
    await start_web_server()
    print("✅ Web-сервер и бот запущены...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())