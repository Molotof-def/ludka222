import os
import time
import json
import random
import asyncio
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

# Список ID админов через запятую
raw_admins = os.getenv("ADMIN_IDS", "12345678,87654321,99999999")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

# ID вашей приватной группы (укажи свой -100xxxxxxxxxx)
ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "-1001234567890"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DATA_FILE = "weekly_spins.json"
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
user_spin_streak = {}
COOLDOWN_SECONDS = 1

# Фразы мотивации
NEAR_MISS_MOTIVATION = [
    "🔥 ОДИН ШАГ ДО ДЖЕКПОТА! Две семерки уже стоят, третий барабан подвел! Следующий точно твой!",
    "😱 МИЛЛИМЕТР ДО ПОБЕДЫ! Слот прогрет на максимум, крути еще!",
    "👀 7️⃣ 7️⃣ ➖ ПОЧТИ! Автомат уже сыпет, главное не останавливаться!",
    "⚡️ БАРАБАНЫ ГОРЯТ! Две семерки на месте — победа буквально на следующем спине!"
]

LONG_SPIN_MOTIVATION = [
    "💪 {username}, 99% лудоманов сдаются за секунду до крупного заноса! Жми дальше!",
    "⏳ {username}, ты уже сделал {count} прокрутов! Автомат просто обязан выплюнуть 777!",
    "🎰 {username}, слот заряжен по полной! Сейчас будет сочный занос, не сбавляй темп!",
    "👑 {username}, истинный чемпион крутит до победного конца! 777 уже на подходе!"
]


# --- ПРОВЕРКА ДОСТУПА К ЧАТУ ---
def is_allowed_chat(chat_id: int, user_id: int) -> bool:
    # Разрешаем работу в вашей целевой группе или в ЛС админов
    return chat_id == ALLOWED_CHAT_ID or (chat_id == user_id and user_id in ADMIN_IDS)


# --- АВТО-ВЫХОД ИЗ ЧУЖИХ ГРУПП ---
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def handle_bot_added(event: ChatMemberUpdated):
    if event.chat.id != ALLOWED_CHAT_ID:
        try:
            await bot.send_message(event.chat.id, "⛔️ Этот бот приватный и работает только в определенном сообществе!")
            await bot.leave_chat(event.chat.id)
        except Exception:
            pass


# --- БАЗА ДАННЫХ ---
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
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения БД: {e}")

def add_spin(user_id: int, name: str):
    data = load_data()
    week_key = get_current_week_key()
    if week_key not in data:
        data[week_key] = {}
    uid = str(user_id)
    if uid not in data[week_key]:
        data[week_key][uid] = {"name": name, "spins": 0, "wins": 0}
    data[week_key][uid]["name"] = name
    data[week_key][uid]["spins"] += 1
    save_data(data)
# --- ПРИВЕТСТВИЕ НОВЫХ УЧАСТНИКОВ ---
@dp.message(F.new_chat_members)
async def welcome_new_member(message: Message):
    # Проверяем, что это наш разрешенный чат
    if message.chat.id != ALLOWED_CHAT_ID:
        return

    for new_member in message.new_chat_members:
        # Игнорируем добавление самого бота
        if new_member.id == bot.id:
            continue

        username = f"@{new_member.username}" if new_member.username else new_member.full_name

        # Текст приветствия (можешь поменять под свой вкус)
        welcome_text = (
            f"👋 Привет, {username}! Добро пожаловать к нам 🎰\n\n"
            f"🎯 **Это приватный чат для игры в слоты и выбивания NFT!**\n"
            f"выбивай 777 🎰, соревнуйся в еженедельном топе и забирай крутые призы (Vice Cream, Snoop Dogg и Telegram Stars ⭐).\n\n"
            f"📌 **Полезные команды:**\n"
            f"🏆 /top — Лидерборд недели\n"
            f"👤 /me — Твой личный профиль и статистика\n\n"
            f"Отправляй 🎰 в чат и пусть тебе повезет! 🔥"
        )

        # Отправляем приветствие
        await message.answer(welcome_text, parse_mode="Markdown")

    # Удаляем системное сообщение "Пользователь присоединился к группе", чтобы чат был чистым
    try:
        await message.delete()
    except Exception:
        pass
def add_win(user_id: int, name: str):
    data = load_data()
    week_key = get_current_week_key()
    if week_key not in data:
        data[week_key] = {}
    uid = str(user_id)
    if uid not in data[week_key]:
        data[week_key][uid] = {"name": name, "spins": 1, "wins": 0}
    data[week_key][uid]["name"] = name
    data[week_key][uid]["wins"] = data[week_key][uid].get("wins", 0) + 1
    save_data(data)
def generate_profile_text(user_id: int, fallback_name: str) -> str:
    data = load_data()
    week_key = get_current_week_key()
    current_week_data = data.get(week_key, {})
    uid = str(user_id)
    user_info = current_week_data.get(uid, {"name": fallback_name, "spins": 0, "wins": 0})
    
    sorted_players = sorted(current_week_data.items(), key=lambda x: x[1]["spins"], reverse=True)
    rank = "—"
    spins_to_top3 = 0
    
    for idx, (p_uid, p_data) in enumerate(sorted_players):
        if p_uid == uid:
            rank = f"#{idx + 1}"
            break

    if len(sorted_players) >= 3 and uid in current_week_data:
        top_3_spins = sorted_players[2][1]["spins"]
        if user_info["spins"] <= top_3_spins:
            spins_to_top3 = (top_3_spins - user_info["spins"]) + 1

    text = "👤 **ЛИЧНЫЙ ПРОФИЛЬ ИГРОКА**\n"
    text += f"📅 Сезон: `{week_key}`\n"
    text += "────────────────────\n"
    text += f"🎮 Никнейм: **{user_info.get('name') or fallback_name}**\n"
    text += f"🎰 Спинов за неделю: **{user_info['spins']}**\n"
    text += f"🔥 Выбито 777: {user_info.get('wins', 0)} раз(а)\n"
    text += f"🏆 Место в топе: **{rank}**\n"
    
    if spins_to_top3 > 0:
        text += f"🎯 До ТОП-3 не хватает: {spins_to_top3} спинов\n"
    elif rank in ["#1", "#2", "#3"]:
        text += "👑 **Вы в призовой тройке!**\n"
        
    text += "────────────────────\n"
    text += "🎰 *Крути слот-машину в чате, чтобы повысить рейтинг!*"
    return text

def generate_top_text() -> str:
    data = load_data()
    week_key = get_current_week_key()
    current_week_data = data.get(week_key, {})

    text = "🏆 **НЕДЕЛЬНЫЙ ТОП ПО ПРОКРУТАМ**\n"
    text += f"📅 *Сезон: {week_key}*\n"
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

    text += "\n🔄 *Сброс лидерборда каждое воскресенье в 23:59 UTC*"
    return text
# --- КОМАНДА ДЛЯ СОЗЫВА ВСЕХ УЧАСТНИКОВ ---
@dp.message(Command("all"))
async def cmd_tag_all(message: Message):
    if not is_allowed_chat(message.chat.id, message.from_user.id):
        return

    data = load_data()
    week_key = get_current_week_key()
    current_week_data = data.get(week_key, {})

    # Формируем теги по юзернеймам или текстовым ссылкам на аккаунты
    mentions = []
    for uid, pdata in current_week_data.items():
        name = pdata.get("name", "Игрок")
        if name.startswith("@"):
            mentions.append(name)
        else:
            # Если юзернейма нет, тегаем через скрытую ссылку по ID
            mentions.append(f"[{name}](tg://user?id={uid})")

    if not mentions:
        await message.answer("👥 В базе пока нет активных игроков для созыва!")
        return

    # Разбиваем на пачки по 5 человек, чтобы Telegram гарантированно прислал пуши всем
    chunk_size = 5
    for i in range(0, len(mentions), chunk_size):
        chunk = mentions[i:i + chunk_size]
        tags_line = " ".join(chunk)
        await message.answer(
            f"🚨 **ОБЩИЙ СБОР!**\n\n🎰 Залетайте крутить слоты!\n{tags_line}",
            parse_mode="Markdown"
        )
        await asyncio.sleep(0.5)
def get_random_gift(pool_type="BASE"):
    pool = GIFTS_CONFIG[pool_type]
    slug = random.choice(list(pool.keys()))
    config = pool[slug]
    nft_id = random.randint(1, config["max_id"])
    return f"{config['name']} #{nft_id}", f"https://t.me/nft/{slug}-{nft_id}"

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
            print(f"⚠️ Админ {admin_id} не запустил бота в ЛС: {e}")


# --- КОМАНДЫ (ТОЛЬКО В РАЗРЕШЕННОМ ЧАТЕ) ---
@dp.message(Command("top"))
async def cmd_top(message: Message):
    if not is_allowed_chat(message.chat.id, message.from_user.id):
        return
    await message.answer(generate_top_text(), parse_mode="Markdown")

@dp.message(Command("profile", "me"))
async def cmd_profile(message: Message):
    if not is_allowed_chat(message.chat.id, message.from_user.id):
        return
    uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    await message.answer(generate_profile_text(message.from_user.id, uname), parse_mode="Markdown")

@dp.callback_query(F.data == "show_top")
async def handle_show_top(callback: CallbackQuery):
    if not is_allowed_chat(callback.message.chat.id, callback.from_user.id):
        return
    await callback.message.answer(generate_top_text(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "show_profile")
async def handle_show_profile(callback: CallbackQuery):
    if not is_allowed_chat(callback.message.chat.id, callback.from_user.id):
        return
    uname = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    await callback.message.answer(generate_profile_text(callback.from_user.id, uname), parse_mode="Markdown")
    await callback.answer()


# --- ХЕНДЛЕР СЛОТ-МАШИНЫ 🎰 ---
@dp.message(F.dice)
async def handle_dice(message: Message):
    # Жесткий фильтр на целевой чат
    if message.chat.id != ALLOWED_CHAT_ID:
        return

    if message.dice.emoji != "🎰":
        return

    if message.forward_origin is not None:
        return

    user_id = message.from_user.id
    current_time = time.time()
    dice_val = message.dice.value
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    # --- ЕСЛИ ВЫПАЛО НЕ 777 ---
    if dice_val != 64:
        # Включаем анти-спам (кулдаун) только для обычных прокрутов
        if current_time - user_cooldowns.get(user_id, 0) < COOLDOWN_SECONDS:
            return
        user_cooldowns[user_id] = current_time

        if user_id not in ADMIN_IDS:
            add_spin(user_id, username)

        user_spin_streak[user_id] = user_spin_streak.get(user_id, 0) + 1
        current_streak = user_spin_streak[user_id]

        # Мотивация: 2 семерки
        if dice_val in [61, 62, 63]:
            phrase = random.choice(NEAR_MISS_MOTIVATION)
            await message.reply(phrase, parse_mode="Markdown")
            return

        # Мотивация: длинный лузстрик (каждые 15 спинов)
        if current_streak % 15 == 0:
            template = random.choice(LONG_SPIN_MOTIVATION)
            text = template.format(username=username, count=current_streak)
            await message.reply(text, parse_mode="Markdown")
            return

        return # Выходим, так как это не 777

    # ==========================================
    # ЕСЛИ КОД ДОШЕЛ СЮДА — ЭТО 100% ВЫПАЛО 777!
    # Игнорируем анти-спам, чтобы не пропустить победу!
    # ==========================================
    user_cooldowns[user_id] = current_time # Обновляем таймер после победы
    user_spin_streak[user_id] = 0
    print(f"🎉 777 выбито игроком {username} (ID: {user_id})!")
    add_win(user_id, username)

    name, link = get_random_gift("BASE")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡️ Улучшить до Snoop Dogg (Шанс 35%)", 
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
                    text="👤 Мой профиль", 
                    callback_data="show_profile"
                ),
                InlineKeyboardButton(
                    text="🏆 Лидерборд", 
                    callback_data="show_top"
                )
            ]
        ]
    )

    try:
        win_msg = await message.reply(
            f"🎁 {username} выбил 777!\n\n"
            f"Подарок: **{name}**\n"
            f"🔗 {link}\n\n"
            f"Выбери действие:\n"
            f"• Нажми Забрать, чтобы отправить заявку админам на вывод.\n"
            f"• Нажми Улучшить, чтобы рискнуть улучшить до Snoop Dogg (35% шанс на успех / 65% сгорание).",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        try:
            await bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=win_msg.message_id,
                disable_notification=True
            )
        except Exception:
            pass

    except Exception as e:
        print(f"Ошибка отправки сообщения 777: {e}")
# --- ЗАБРАТЬ ПОДАРОК ---
@dp.callback_query(F.data.
startswith("claim:"))
async def handle_claim(callback: CallbackQuery):
    _, owner_id, chat_id = callback.data.split(":")
    owner_id, chat_id = int(owner_id), int(chat_id)

    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой подарок!", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

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


# --- АПГРЕЙД ДО SNOOP DOGG (ШАНС 35%) ---
@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade(callback: CallbackQuery):
    _, owner_id, chat_id = callback.data.split(":")
    owner_id, chat_id = int(owner_id), int(chat_id)

    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не твой выигрыш!", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

    # ШАНС: 35%
    is_success = random.randint(1, 100) <= 35

    if is_success:
        upg_name, upg_link = get_random_gift("UPGRADE")
        upg_msg = await callback.message.answer(
            f"🔥 ДЖЕКПОТ! АПГРЕЙД УСПЕШЕН! (Шанс 35% залетел!)\n\n"
            f"👤 Игрок: {username}\n"
            f"✨ Эксклюзивный Подарок: **{upg_name}**\n"
            f"🔗 {upg_link}\n\n"
            f"⏳ Заявка передана администрации на подтверждение!",
            parse_mode="Markdown"
        )

        try:
            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=upg_msg.message_id,
                disable_notification=False
            )
        except Exception:
            pass

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
            f"💥 НЕУДАЧА! (Сработал шанс 65% на сгорание)\n\n"
            f"👤 {username}, к сожалению, подарок сгорел!\n"
            f"Попробуй выбить 777 снова 🎰",
            parse_mode="Markdown"
        )
    
    await callback.answer()


# --- АДМИН-ПАНЕЛЬ ---
@dp.callback_query(F.data.startswith("adm_ok:"))
async def handle_admin_approve(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return

    _, player_id, chat_id, claim_key = callback.data.split(":")
    player_id, chat_id = int(player_id), int(chat_id)
    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name

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

    if claim_key in pending_claims:
        for adm_id, msg_id in pending_claims[claim_key]:
            try:
                await bot.edit_message_text(
                    chat_id=adm_id,
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
    print(f"✅ Бот запущен в приватном режиме для чата ID: {ALLOWED_CHAT_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())