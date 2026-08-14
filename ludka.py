import os
import time
import random
import asyncio
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Диапазоны ID
MIN_ID = 1
MAX_ID = 482271
MAX_TRIES = 20

# Обычные подарки (выпадают при 777)
BASE_GIFTS = {
    "ChillFlame": "Chill Flame",
    "ViceCream": "Vice Cream"
}

# Единственный эксклюзивный подарок для улучшения
UPGRADED_GIFTS = {
    "SnoopDogg": "Snoop Dogg"
}

# Кулдауны пользователей: {user_id: timestamp}
user_cooldowns = {}
COOLDOWN_SECONDS = 3

# Проверка существования NFT на Fragment
async def nft_exists(session: aiohttp.ClientSession, gift_slug: str, nft_id: int) -> bool:
    url = f"https://t.me/nft/{gift_slug}-{nft_id}"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status != 200:
                return False
            text = await resp.text()
            return gift_slug in text and f"#{nft_id}" in text
    except Exception:
        return False

async def get_random_real_gift(pool: dict):
    async with aiohttp.ClientSession() as session:
        for _ in range(MAX_TRIES):
            nft_id = random.randint(MIN_ID, MAX_ID)
            gift_slug = random.choice(list(pool.keys()))
            
            if await nft_exists(session, gift_slug, nft_id):
                display_name = pool[gift_slug]
                return f"{display_name} #{nft_id}", f"https://t.me/nft/{gift_slug}-{nft_id}"
    
    # Fallback, если за MAX_TRIES ничего не нашлось
    fallback_slug = list(pool.keys())[0]
    return f"{pool[fallback_slug]} #1", f"https://t.me/nft/{fallback_slug}-1"


# --- ХЕНДЛЕР СЛОТОВ ---
@dp.message(F.dice)
async def handle_dice(message: Message):
    user_id = message.from_user.id
    current_time = time.time()

    # 1. Защита от пересылок
    if message.forward_origin is not None:
        return

    # 2. Защита от подмены эмодзи и проверка комбинации 777
    if message.dice.emoji != "🎰" or message.dice.value != 64:
        return

    # 3. Защита от старых сообщений (лаги/оффлайн пакеты)
    if current_time - message.date.timestamp() > 15:
        return

    # 4. Защита от спама (Кулдаун)
    if current_time - user_cooldowns.get(user_id, 0) < COOLDOWN_SECONDS:
        return
    user_cooldowns[user_id] = current_time

    # Базовый подарок (Chill Flame или Vice Cream)
    name, link = await get_random_real_gift(BASE_GIFTS)
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    # Инлайн-кнопка с привязкой к ID владельца
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ Улучшить до Snoop Dogg (Шанс 40%)", 
                    callback_data=f"upg:{user_id}"
                )
            ]
        ]
    )

    await message.answer(
        f"🎁 {username} выбил 777!\n\n"
        f"Подарок: {name}\n"
        f"🔗 {link}\n\n"
        f"✅ Подарок готов к отправке!\n"
        f"Ты можешь забрать его или рискнуть улучшить до Snoop Dogg (40% шанс на успех, 60% — сгорание).",
        reply_markup=keyboard
    )


# --- ХЕНДЛЕР АПГРЕЙДА ---
@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])

    # Защита от перехвата: кнопку жмет только автор броска
    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой выигрыш!", show_alert=True)
        return

    # Удаляем кнопку сразу, чтобы исключить двойное нажатие
    await callback.message.edit_reply_markup(reply_markup=None)

    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # Скрытый реальный шанс: 5% (1..5 из 100)
    is_success = random.randint(1, 100) <= 5
    if is_success:
        upg_name, upg_link = await get_random_real_gift(UPGRADED_GIFTS)
        await callback.message.answer(
            f"🔥 ДЖЕКПОТ! АПГРЕЙД УСПЕШЕН! (Шанс 40% сработал!)\n\n"
            f"👤 Игрок: {username}\n"
            f"✨ Эксклюзивный Подарок: **{upg_name}**\n"
            f"🔗 {upg_link}\n\n"
            f"🚀 Подарок отправлен автоматически!"
        )
    else:
        await callback.message.answer(
            f"💥 НЕУДАЧА! (Сработал шанс 60%)\n\n"
            f"👤 {username}, к сожалению, при попытке улучшения подарок сгорел!\n"
            f"Попробуй выбить 777 снова 🎰"
        )
    
    await callback.answer()


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER FREE WEB SERVICE ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    print("✅ Бот со Snoop Dogg и защитой запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())