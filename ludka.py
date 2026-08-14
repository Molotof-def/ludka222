import os
import random
import asyncio
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Используем токен из .env или тот, что был жестко прописан в твоем коде
if not BOT_TOKEN:


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

MIN_ID = 1
MAX_ID = 482271
MAX_TRIES = 25

# Словарь с доступными коллекциями: slug для ссылки и корректное отображение имени
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
            
            # Получаем красивое имя для проверки в тексте страницы
            display_name = GIFTS_POOL[gift_slug]
            return gift_slug in text and f"{display_name} #{nft_id}" in text
    except Exception:
        return False

async def get_random_real_gift():
    async with aiohttp.ClientSession() as session:
        for _ in range(MAX_TRIES):
            nft_id = random.randint(MIN_ID, MAX_ID)
            # Случайно выбираем, какой подарок проверять: ChillFlame или ViceCream
            gift_slug = random.choice(list(GIFTS_POOL.keys()))
            
            if await nft_exists(session, gift_slug, nft_id):
                display_name = GIFTS_POOL[gift_slug]
                gift_name = f"{display_name} #{nft_id}"
                gift_link = f"https://t.me/nft/{gift_slug}-{nft_id}"
                return gift_name, gift_link
    return None, None

# Хендлер реагирует только на анимированный кубик (слот-машину)
@dp.message(F.dice)
async def handle_dice(message: Message):
    # ИГНОРИРУЕМ ПЕРЕСЛАННЫЕ СООБЩЕНИЯ
    if message.forward_origin is not None:
        return

    # Если выпало не три семерки (для слотов это значение 64) — бот молчит
    if message.dice.value != 64:
        return

    # Ищем случайный существующий подарок (Chill Flame или Vice Cream)
    name, link = await get_random_real_gift()
    
    if not link:
        return

    # Формируем юзернейм или имя
    if message.from_user.username:
        username = f"@{message.from_user.username}"
    else:
        username = message.from_user.full_name

    # Отправляем сообщение об успешном выигрыше
    await message.answer(
        f"🎁 {username} выбил 777!\n\n"
        f"Подарок: {name}\n"
        f"🔗 {link}\n\n"
        f"✅ Подарок отправлен автоматически!"
    )

async def main():
    print("✅ Bot started")
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())