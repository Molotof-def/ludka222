import os
import time
import json
import random
import asyncio
import aiohttp
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Файл локальной базы данных
DATA_FILE = "weekly_spins.json"

MIN_ID = 1
MAX_ID = 482271
MAX_TRIES = 20

BASE_GIFTS = {
    "ChillFlame": "Chill Flame",
    "ViceCream": "Vice Cream"
}

UPGRADED_GIFTS = {
    "SnoopDogg": "Snoop Dogg"
}

user_cooldowns = {}
COOLDOWN_SECONDS = 3


# --- РАБОТА С НЕДЕЛЬНОЙ БАЗОЙ ДАННЫХ ---
def get_current_week_key() -> str:
    """Возвращает ключ текущей недели в формате 'ГОД-НЕДЕЛЯ' (например, '2026-33')"""
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_spin(user_id: int, name: str):
    data = load_data()
    week_key = get_current_week_key()
    
    # Инициализация недели, если наступила новая
    if week_key not in data:
        data[week_key] = {}
        
    uid = str(user_id)
    if uid not in data[week_key]:
        data[week_key][uid] = {"name": name, "spins": 0}
        
    data[week_key][uid]["name"] = name
    data[week_key][uid]["spins"] += 1
    save_data(data)

def generate_top_text() -> str:
    data = load_data()
    week_key = get_current_week_key()
    current_week_data = data.get(week_key, {})

    text = "🏆 **НЕДЕЛЬНЫЙ ТОП ПО ПРОКРУТАМ**\n"
    text += f"📅 *Сезон недели: {week_key}*\n"
    text += "────────────────────\n"
    text += "🎁 **Призы за топ недели:**\n"
    text += "🥇 1 место — **NFT Vice Cream 🍦**\n"
    text += "🥈 2 место — **50 ⭐ Stars**\n"
    text += "🥉 3 место — **15 ⭐ Stars**\n"
    text += "────────────────────\n\n"

    if not current_week_data:
        text += "🎰 На этой неделе еще никто не крутил!\nБудь первым!"
        return text

    # Сортировка участников по убыванию количества прокрутов
    sorted_players = sorted(current_week_data.values(), key=lambda x: x["spins"], reverse=True)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for idx, player in enumerate(sorted_players[:10]):
        rank_icon = medals[idx] if idx < len(medals) else f"#{idx+1}"
        prize_tag = ""
        if idx == 0:
            prize_tag = " — `[NFT Ice Cream]`"
        elif idx == 1:
            prize_tag = " — `[50 ⭐]`"
        elif idx == 2:
            prize_tag = " — `[15 ⭐]`"

        text += f"{rank_icon} {player['name']}: {player['spins']} спинов{prize_tag}\n"

    text += "\n🔄 *Топ обновляется каждое воскресенье в 23:59 UTC*"
    return text


# --- ПРОВЕРКА NFT НА FRAGMENT ---
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
    
    fallback_slug = list(pool.keys())[0]
    return f"{pool[fallback_slug]} #1", f"https://t.me/nft/{fallback_slug}-1"


# --- КОМАНДА /TOP ---
@dp.message(Command("top"))
async def cmd_top(message: Message):
    text = generate_top_text()
    await message.answer(text, parse_mode="Markdown")


# --- ОБРАБОТЧИК КНОПКИ ТОПА ---
@dp.callback_query(F.data == "show_top")
async def handle_show_top(callback: CallbackQuery):
    text = generate_top_text()
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# --- ХЕНДЛЕР СЛОТОВ ---
@dp.message(F.dice)
async def handle_dice(message: Message):
    user_id = message.from_user.id
    current_time = time.time()

    # 1. Защита от пересылок
    if message.forward_origin is not None:
        return

    # 2. Проверяем, что это слот-машина 🎰
    if message.dice.emoji != "🎰":
        return

    # 3. Защита от старых пакетов
    if current_time - message.date.timestamp() > 15:
        return

    # 4. Защита от флуда/спама
    if current_time - user_cooldowns.get(user_id, 0) < COOLDOWN_SECONDS:
        return
    user_cooldowns[user_id] = current_time

    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    # Засчитываем спин в текущую неделю
    add_spin(user_id, username)

    # Если не 777 (значение 64) — выходим
    if message.dice.value != 64:
        return

    # Выбиты 777
    name, link = await get_random_real_gift(BASE_GIFTS)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ Улучшить до Snoop Dogg (Шанс 40%)", 
                    callback_data=f"upg:{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Недельный лидерборд", 
                    callback_data="show_top"
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
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# --- ХЕНДЛЕР АПГРЕЙДА ---
@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])

    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой выигрыш!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # Скрытый реальный шанс: 5%
    is_success = random.randint(1, 100) <= 5

    if is_success:
        upg_name, upg_link = await get_random_real_gift(UPGRADED_GIFTS)
        await callback.message.answer(
            f"🔥 ДЖЕКПОТ! АПГРЕЙД УСПЕШЕН! (Шанс 40% сработал!)\n\n"
            f"👤 Игрок: {username}\n"
            f"✨ Эксклюзивный Подарок: **{upg_name}**\n"
            f"🔗 {upg_link}\n\n"
            f"🚀 Подарок отправлен автоматически!",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(
            f"💥 НЕУДАЧА! (Сработал шанс 60%)\n\n"
            f"👤 {username}, к сожалению, при попытке улучшения подарок сгорел!\n"
            f"Попробуй выбить 777 снова 🎰",
            parse_mode="Markdown"
        )
    
    await callback.answer()


# --- ХЕЛСЧЕК ВЕБ-СЕРВЕРА ДЛЯ RENDER ---
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

async def main():await start_web_server()
    print("✅ Бот запущен с недельным топом (Vice Cream + Звезды)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())