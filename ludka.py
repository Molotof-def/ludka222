import os
import time
import json
import random
import asyncio
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

# Считываем список ID админов через запятую (например: "12345678,87654321,99999999")
raw_admins = os.getenv("ADMIN_IDS", "12345678,87654321,99999999")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in raw_admins.split(",") if admin_id.strip().isdigit()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DATA_FILE = "weekly_spins.json"

# Хранилище отправленных сообщений админам для синхронизации кнопок: {claim_key: [(admin_id, message_id)]}
pending_claims = {}

GIFTS_CONFIG = {
    "BASE": {
        "ChillFlame": {"name": "Chill Flame", "max_id": 50000},
        "ViceCream": {"name": "Vice Cream", "max_id": 15000}
    },
    "UPGRADE": {
        "SnoopDogg": {"name": "Snoop Dogg", "max_id": 10000}
    }
}

user_cooldowns = {}
COOLDOWN_SECONDS = 2


# --- РАБОТА С БАЗОЙ ТОПА ---
def get_current_week_key() -> str:
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
        text += "🎰 На этой неделе еще никто не крутил!\n"
        return text

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

def get_random_gift(pool_type="BASE"):
    pool = GIFTS_CONFIG[pool_type]
    slug = random.choice(list(pool.keys()))
    config = pool[slug]
    nft_id = random.randint(1, config["max_id"])
    
    gift_name = f"{config['name']} #{nft_id}"
    gift_link = f"https://t.me/nft/{slug}-{nft_id}"
    return gift_name, gift_link


# --- ПРОВЕРКА НА АДМИНИСТРАТОРА ---
async def is_user_admin(chat_id: int, user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False# --- ОТПРАВКА УВЕДОМЛЕНИЯ ВСЕМ АДМИНАМ ---
async def notify_all_admins(text: str, reply_markup: InlineKeyboardMarkup, claim_key: str):
    pending_claims[claim_key] = []
    for admin_id in ADMIN_IDS:
        try:
            sent_msg = await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            pending_claims[claim_key].append((admin_id, sent_msg.message_id))
        except Exception as e:
            print(f"Не удалось отправить админу {admin_id}: {e}")


# --- КОМАНДЫ И КНОПКИ ТОПА ---
@dp.message(Command("top"))
async def cmd_top(message: Message):
    text = generate_top_text()
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "show_top")
async def handle_show_top(callback: CallbackQuery):
    text = generate_top_text()
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# --- ХЕНДЛЕР СЛОТ-МАШИНЫ ---
@dp.message(F.dice)
async def handle_dice(message: Message):
    user_id = message.from_user.id
    current_time = time.time()

    if message.forward_origin is not None or message.dice.emoji != "🎰":
        return

    if current_time - message.date.timestamp() > 15:
        return

    if current_time - user_cooldowns.get(user_id, 0) < COOLDOWN_SECONDS:
        return
    user_cooldowns[user_id] = current_time

    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    # Все 3 админа и админы чата исключены из топа
    is_admin = await is_user_admin(message.chat.id, user_id)
    if not is_admin:
        add_spin(user_id, username)

    if message.dice.value != 64:
        return

    name, link = get_random_gift("BASE")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ Улучшить до Snoop Dogg (Шанс 40%)", 
                    callback_data=f"upg:{user_id}:{message.chat.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 Забрать подарок", 
                    callback_data=f"claim:{user_id}:{message.chat.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Лидерборд", 
                    callback_data="show_top"
                )
            ]
        ]
    )

    await message.answer(
        f"🎁 {username} выбил 777!\n\n"
        f"Подарок: **{name}**\n"
        f"🔗 {link}\n\n"
        f"Выбери действие:\n"
        f"• Нажми Забрать, чтобы отправить заявку админам на вывод.\n"
        f"• Нажми Улучшить, чтобы рискнуть получить Snoop Dogg (40% шанс / 60% сгорание).",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# --- ЗАБРАТЬ ОБЫЧНЫЙ ПОДАРОК ---
@dp.callback_query(F.data.startswith("claim:"))
async def handle_claim(callback: CallbackQuery):
    _, owner_id, chat_id = callback.data.split(":")
    owner_id, chat_id = int(owner_id), int(chat_id)

    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой подарок!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    await callback.message.answer(
        f"⏳ {username} отправил заявку на вывод подарка!\nАдминистрация проверяет отправку."
    )

    claim_key = f"{owner_id}_{int(time.time())}"
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_ok:{owner_id}:{chat_id}:{claim_key}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_no:{owner_id}:{chat_id}:{claim_key}")
            ]
        ]
    )

    text = f"🔔 **Новая заявка на вывод!**\n\n👤 Игрок: {username} (ID: `{owner_id}`)\n💬 Чат ID: `{chat_id}`"
    await notify_all_admins(text, admin_kb, claim_key)
    await callback.answer()


# --- АПГРЕЙД ДО SNOOP DOGG ---
@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade(callback: CallbackQuery):
    _, owner_id, chat_id = callback.data.split(":")
    owner_id, chat_id = int(owner_id), int(chat_id)

    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой выигрыш!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # Реальный шанс: 5%
    is_success = random.randint(1, 100) <= 5

    if is_success:
        upg_name, upg_link = get_random_gift("UPGRADE")
        await callback.message.answer(
            f"🔥 ДЖЕКПОТ! АПГРЕЙД УСПЕШЕН! (Шанс 40% сработал!)\n\n"
            f"👤 Игрок: {username}\n"
            f"✨ Эксклюзивный Подарок: **{upg_name}**\n"
            f"🔗 {upg_link}\n\n"
            f"⏳ Заявка передана администрации на подтверждение!",
            parse_mode="Markdown"
        )

        claim_key = f"{owner_id}_{int(time.time())}"
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Одобрить NFT Snoop Dogg", callback_data=f"adm_ok:{owner_id}:{chat_id}:{claim_key}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_no:{owner_id}:{chat_id}:{claim_key}")
                ]
            ]
        )

        text = f"🚨 **КРУПНЫЙ ВЫИГРЫШ (Snoop Dogg)!**\n\n👤 Игрок: {username} (ID: `{owner_id}`)\nПодарок: {upg_name}\nСсылка: {upg_link}"
        await notify_all_admins(text, admin_kb, claim_key)

    else:
        await callback.message.answer(
            f"💥 НЕУДАЧА! (Сработал шанс 60%)\n\n"
            f"👤 {username}, к сожалению, при попытке улучшения подарок сгорел!\n"
            f"Попробуй выбить 777 снова 🎰",
            parse_mode="Markdown"
        )
    
    await callback.answer()


# --- ДЕЙСТВИЯ АДМИНИСТРАТОРОВ (ОДОБРИТЬ / ОТКЛОНИТЬ) ---
@dp.callback_query(F.data.startswith("adm_ok:"))
async def handle_admin_approve(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return

    _, player_id, chat_id, claim_key = callback.data.split(":")
    player_id, chat_id = int(player_id), int(chat_id)
    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # Обновляем сообщения у всех 3 админов
    if claim_key in pending_claims:
        for adm_id, msg_id in pending_claims[claim_key]:
            try:
                await bot.edit_message_text(
                    chat_id=adm_id,
                    message_id=msg_id,
                    text=f"{callback.message.text}\n\n✅ **ОДОБРЕНО администратором {admin_name}**"
                )
            except Exception:
                pass
        del pending_claims[claim_key]

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ Подарок для игрока [ID: {player_id}] успешно подтвержден администрацией и передан!",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await callback.answer("Одобрено!")


@dp.callback_query(F.data.startswith("adm_no:"))
async def handle_admin_reject(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return

    _, player_id, chat_id, claim_key = callback.data.split(":")
    player_id, chat_id = int(player_id), int(chat_id)
    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # Обновляем сообщения у всех 3 админов
    if claim_key in pending_claims:
        for adm_id, msg_id in pending_claims[claim_key]:
            try:
                await bot.edit_message_text(chat_id=adm_id,
                    message_id=msg_id,
                    text=f"{callback.message.text}\n\n❌ **ОТКЛОНЕНО администратором {admin_name}**"
                )
            except Exception:
                pass
        del pending_claims[claim_key]

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Заявка на вывод для игрока [ID: {player_id}] отклонена администратором.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await callback.answer("Отклонено!")


# --- ХЕЛСЧЕК ДЛЯ RENDER ---
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
    print(f"✅ Бот запущен. Администраторов: {len(ADMIN_IDS)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())