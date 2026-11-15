import asyncio
import html
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus as S, ParseMode
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, ChatMemberUpdated, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# ============================================================ SOZLAMALAR
BOT_TOKEN = os.getenv("BOT_TOKEN") or "BU_YERGA_TOKEN_YOZING"
ADMIN_ID = int(os.getenv("ADMIN_ID", "7676544759"))
DB_PATH = os.getenv("DB_PATH", "battle.db")      # Render: Disk ulab /data/battle.db
DAILY_BONUS = 5
REF_BONUS = 15
TZ = timezone(timedelta(hours=5))                 # Toshkent vaqti

base = Router()
admin = Router()
router = Router()
admin.message.filter(F.from_user.id == ADMIN_ID)
admin.callback_query.filter(F.from_user.id == ADMIN_ID)

UNAME = ""
LINKS: dict[int, str] = {}
TASKS: set = set()

# ============================================================ MATNLAR (uz / ru)
TX = {
    "uz": {
        "welcome": (
            "🎉 <b>Botimizga xush kelibsiz!</b>\n\n"
            "📌 <b>Ushbu Bot Orqali Siz:</b>\n\n"
            "📢 Kanallaringizda Ovozli Konkurslar Qilishingiz Mumkin!\n\n"
            "🤝 Botni Kanalga Admin Qiling\n"
            "🎖 Kanalga #batl deb yozib yuboring tayyor ⭐️\n\n"
            "📌 <b>Foydali Taraflar</b>\n\n"
            "👥 Ovoz Beruvchilar Kanalingizga Obuna Bo'lishadi ⭐️\n\n"
            "❗️ Agar Ovoz beruvchi kanaldan chiqib ketsa, ovozi avtomatik real vaqtda ayriladi ⭐️\n\n"
            "👇 Quyidagi menyudan birini tanlang:"),
        "b_battle": "🥊 Battle yaratish", "b_my": "📅 Mening battlelarim",
        "b_profile": "👤 Profil", "b_support": "✉️ Murojaat",
        "b_guide": "📖 Qo'llanma", "b_lang": "🌐 Til", "b_menu": "📋 Menyu",
        "b_bonus": "🎁 Kunlik bonus", "b_shop": "🛍 Ball do'koni",
        "b_invite": "👥 Do'stlarga ulashib ball olish", "b_back": "⬅️ Orqaga",
        "b_cancel": "❌ Bekor qilish",
        "add_ch": "➕ Botni kanalga qo'shish", "share_btn": "📤 Do'stlarga ulashish",
        "battle_info": (
            "🥊 <b>Battle yaratish</b>\n\n"
            "1️⃣ Pastdagi tugma orqali botni kanalingizga <b>admin</b> qiling "
            "(post yozish va o'chirish huquqi bilan).\n"
            "2️⃣ Kanalda <code>#batl</code> deb yozib yuboring.\n"
            "3️⃣ Bot yozuvingizni o'chirib, battle postini chiqaradi ✅"),
        "guide": (
            "📖 <b>Qo'llanma</b>\n\n"
            "1️⃣ «🥊 Battle yaratish» orqali botni kanalingizga <b>admin</b> qiling.\n"
            "2️⃣ Kanalda <code>#batl</code> deb yozing — bot uni o'chirib, battle postini chiqaradi.\n"
            "3️⃣ Ishtirokchilar postdagi «➕ Qatnashish» tugmasini bosib botga o'tadi va "
            "kanalga obuna bo'lsa ro'yxatga qo'shiladi.\n"
            "4️⃣ Do'stlar ishtirokchi tugmasini bosib ovoz beradi (kanalga obuna bo'lish shart, bitta ovoz).\n"
            "5️⃣ Ovoz bergan odam kanaldan chiqsa, ovozi avtomatik o'chadi.\n"
            "6️⃣ Kanal admini «🗳 Ovoz berganlar» orqali kim kimga ovoz berganini ko'radi.\n"
            "7️⃣ «📊 Natijalar» ni bosib battleni tugatadi — g'olib e'lon qilinadi.\n\n"
            "💰 <b>Ball tizimi:</b>\n"
            "• Kunlik bonus: <b>+5 ball</b>\n"
            "• Do'st taklif qilish: <b>+15 ball</b> (do'stingiz majburiy kanallarga obuna bo'lsa)\n"
            "• Ballarga «🛍 Ball do'koni»dan sovg'a olasiz."),
        "profile": ("👤 <b>Profil</b>\n\n🆔 ID: <code>{id}</code>\n👤 Ism: {name}\n"
                    "💰 Ball: <b>{b}</b>\n👥 Taklif qilganlar: <b>{n}</b>\n🌐 Til: {l}"),
        "support_ask": "✉️ Murojaatingizni yozing (matn, rasm yoki video).",
        "support_sent": "✅ Murojaatingiz adminga yuborildi. Javob shu yerga keladi.",
        "cancelled": "❌ Bekor qilindi.",
        "bonus_ok": "✅ Hisobingizga <b>+{x} ball</b> qo'shildi!\n💰 Jami: <b>{b}</b>",
        "bonus_no": "⏳ Bugungi bonusni olgansiz. Ertaga qaytib keling!",
        "shop_head": "🛍 <b>Ball do'koni</b>\n\n💰 Ballingiz: <b>{b}</b>\nSovg'ani tanlang 👇",
        "shop_empty": "🛍 <b>Ball do'koni</b>\n\n💰 Ballingiz: <b>{b}</b>\n\nHozircha sovg'alar yo'q.",
        "bought": "✅ Siz «{g}» sovg'asini oldingiz! Admin siz bilan bog'lanadi.",
        "no_balls": "❌ Ballingiz yetmaydi. Sizda {b} ball bor.",
        "sold_out": "😔 Bu sovg'a tugagan.",
        "invite": ("👥 <b>Do'stlarga ulashib ball oling</b>\n\n"
                   "Har bir taklif uchun <b>+{r} ball</b>! Do'stingiz majburiy kanallarga "
                   "obuna bo'lgach ball beriladi.\n\n🔗 Sizning havolangiz:\n<code>{link}</code>\n\n"
                   "👥 Taklif qilganlar: <b>{n}</b>"),
        "share_text": "Ovozli konkurs botiga qo'shiling! 🏆",
        "lang_pick": "🌐 Tilni tanlang / Выберите язык:", "lang_set": "✅ Til o'zgartirildi.",
        "menu2": "📋 <b>Menyu</b>\n\nQuyidagilardan birini tanlang 👇",
        "sub_need": "📢 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
        "sub_btn": "✅ Tekshirish", "sub_fail": "❌ Hali hamma kanalga obuna bo'lmadingiz!",
        "sub_ok": "✅ Rahmat! Endi botdan foydalanishingiz mumkin.",
        "banned": "🚫 Siz botdan bloklangansiz.",
        "my_none": "📅 Sizda hali battle yo'q. «🥊 Battle yaratish» ni bosing.",
        "my_head": "📅 <b>Mening battlelarim</b>\n\n",
        "added": "✅ Bot «{t}» kanaliga admin bo'ldi. Endi kanalda <code>#batl</code> deb yozing!",
        "ref_ok": "🎉 Do'stingiz obuna bo'ldi! Hisobingizga <b>+{n} ball</b> qo'shildi.",
    },
    "ru": {
        "welcome": (
            "🎉 <b>Добро пожаловать!</b>\n\n"
            "📌 <b>С помощью этого бота вы можете:</b>\n\n"
            "📢 Проводить конкурсы с голосованием в своих каналах!\n\n"
            "🤝 Сделайте бота админом канала\n"
            "🎖 Напишите в канале #batl — и всё готово ⭐️\n\n"
            "📌 <b>Преимущества</b>\n\n"
            "👥 Голосующие подписываются на ваш канал ⭐️\n\n"
            "❗️ Если голосующий выйдет из канала, его голос автоматически снимается в реальном времени ⭐️\n\n"
            "👇 Выберите пункт меню:"),
        "b_battle": "🥊 Создать батл", "b_my": "📅 Мои батлы",
        "b_profile": "👤 Профиль", "b_support": "✉️ Обращение",
        "b_guide": "📖 Инструкция", "b_lang": "🌐 Язык", "b_menu": "📋 Меню",
        "b_bonus": "🎁 Ежедневный бонус", "b_shop": "🛍 Магазин баллов",
        "b_invite": "👥 Пригласить друзей и получить баллы", "b_back": "⬅️ Назад",
        "b_cancel": "❌ Отмена",
        "add_ch": "➕ Добавить бота в канал", "share_btn": "📤 Поделиться с друзьями",
        "battle_info": (
            "🥊 <b>Создать батл</b>\n\n"
            "1️⃣ Кнопкой ниже сделайте бота <b>админом</b> канала "
            "(с правом публиковать и удалять сообщения).\n"
            "2️⃣ Напишите в канале <code>#batl</code>.\n"
            "3️⃣ Бот удалит ваше сообщение и опубликует пост батла ✅"),
        "guide": (
            "📖 <b>Инструкция</b>\n\n"
            "1️⃣ Через «🥊 Создать батл» сделайте бота <b>админом</b> канала.\n"
            "2️⃣ Напишите в канале <code>#batl</code> — бот удалит его и опубликует пост батла.\n"
            "3️⃣ Участники жмут «➕ Qatnashish» под постом, переходят в бота и, если подписаны на канал, добавляются в список.\n"
            "4️⃣ Друзья голосуют, нажимая на кнопку участника (нужна подписка на канал, один голос).\n"
            "5️⃣ Если проголосовавший выйдет из канала, его голос удаляется автоматически.\n"
            "6️⃣ Админ канала через «🗳 Ovoz berganlar» видит, кто за кого голосовал.\n"
            "7️⃣ Кнопка «📊 Natijalar» завершает батл — объявляется победитель.\n\n"
            "💰 <b>Баллы:</b>\n"
            "• Ежедневный бонус: <b>+5 баллов</b>\n"
            "• Приглашение друга: <b>+15 баллов</b> (если друг подписался на обязательные каналы)\n"
            "• Баллы можно обменять на подарки в «🛍 Магазин баллов»."),
        "profile": ("👤 <b>Профиль</b>\n\n🆔 ID: <code>{id}</code>\n👤 Имя: {name}\n"
                    "💰 Баллы: <b>{b}</b>\n👥 Приглашено: <b>{n}</b>\n🌐 Язык: {l}"),
        "support_ask": "✉️ Напишите ваше обращение (текст, фото или видео).",
        "support_sent": "✅ Обращение отправлено админу. Ответ придёт сюда.",
        "cancelled": "❌ Отменено.",
        "bonus_ok": "✅ На ваш счёт зачислено <b>+{x} баллов</b>!\n💰 Всего: <b>{b}</b>",
        "bonus_no": "⏳ Сегодняшний бонус уже получен. Приходите завтра!",
        "shop_head": "🛍 <b>Магазин баллов</b>\n\n💰 Ваши баллы: <b>{b}</b>\nВыберите подарок 👇",
        "shop_empty": "🛍 <b>Магазин баллов</b>\n\n💰 Ваши баллы: <b>{b}</b>\n\nПодарков пока нет.",
        "bought": "✅ Вы получили подарок «{g}»! Админ свяжется с вами.",
        "no_balls": "❌ Не хватает баллов. У вас {b}.",
        "sold_out": "😔 Этот подарок закончился.",
        "invite": ("👥 <b>Приглашайте друзей — получайте баллы</b>\n\n"
                   "За каждого друга <b>+{r} баллов</b>! Баллы начисляются после подписки друга "
                   "на обязательные каналы.\n\n🔗 Ваша ссылка:\n<code>{link}</code>\n\n"
                   "👥 Приглашено: <b>{n}</b>"),
        "share_text": "Присоединяйся к боту конкурсов с голосованием! 🏆",
        "lang_pick": "🌐 Tilni tanlang / Выберите язык:", "lang_set": "✅ Язык изменён.",
        "menu2": "📋 <b>Меню</b>\n\nВыберите 👇",
        "sub_need": "📢 Чтобы пользоваться ботом, подпишитесь на каналы:",
        "sub_btn": "✅ Проверить", "sub_fail": "❌ Вы подписались не на все каналы!",
        "sub_ok": "✅ Спасибо! Теперь можно пользоваться ботом.",
        "banned": "🚫 Вы заблокированы в боте.",
        "my_none": "📅 У вас пока нет батлов. Нажмите «🥊 Создать батл».",
        "my_head": "📅 <b>Мои батлы</b>\n\n",
        "added": "✅ Бот стал админом канала «{t}». Теперь напишите в канале <code>#batl</code>!",
        "ref_ok": "🎉 Ваш друг подписался! Вам начислено <b>+{n} баллов</b>.",
    },
}


def lang(uid) -> str:
    r = q("SELECT lang FROM users WHERE id=?", uid)
    return r[0]["lang"] if r else "uz"


def T(uid, key, **kw):
    s = TX[lang(uid)].get(key) or TX["uz"][key]
    return s.format(**kw) if kw else s


def ALL(key):
    return [TX["uz"][key], TX["ru"][key]]


# ============================================================ DB
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS battles(
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, message_id INTEGER DEFAULT 0,
  finished INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS participants(
  battle_id INTEGER, user_id INTEGER, name TEXT, PRIMARY KEY(battle_id, user_id));
CREATE TABLE IF NOT EXISTS votes(
  battle_id INTEGER, voter_id INTEGER, voter_name TEXT, participant_id INTEGER,
  PRIMARY KEY(battle_id, voter_id));
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT, username TEXT, lang TEXT DEFAULT 'uz',
  balls INTEGER DEFAULT 0, ref_by INTEGER DEFAULT 0, rewarded INTEGER DEFAULT 0,
  joined TEXT, banned INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0, bonus_date TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS req_channels(chat_id INTEGER PRIMARY KEY, title TEXT, link TEXT);
CREATE TABLE IF NOT EXISTS chats(chat_id INTEGER PRIMARY KEY, title TEXT, username TEXT, owner_id INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER, qty INTEGER);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, gift_id INTEGER,
  gift_name TEXT, price INTEGER, ts TEXT);
CREATE TABLE IF NOT EXISTS support(msg_id INTEGER PRIMARY KEY, user_id INTEGER);
""")


def ex(sql, *args):
    cur = db.execute(sql, args)
    db.commit()
    return cur


def q(sql, *args):
    return ex(sql, *args).fetchall()


def today() -> str:
    return datetime.now(TZ).date().isoformat()


def battle(bid):
    r = q("SELECT * FROM battles WHERE id=?", bid)
    return r[0] if r else None


def standings(bid):
    return q("""SELECT p.user_id, p.name,
                (SELECT COUNT(*) FROM votes v WHERE v.battle_id=p.battle_id
                 AND v.participant_id=p.user_id) AS c
                FROM participants p WHERE p.battle_id=? ORDER BY c DESC, p.rowid""", bid)


def reg_user(user, ref=0):
    if q("SELECT 1 FROM users WHERE id=?", user.id):
        ex("UPDATE users SET name=?, username=? WHERE id=?", user.full_name, user.username or "", user.id)
        return
    if ref == user.id or not q("SELECT 1 FROM users WHERE id=?", ref):
        ref = 0
    ex("INSERT INTO users(id,name,username,joined,ref_by) VALUES(?,?,?,?,?)",
       user.id, user.full_name, user.username or "", today(), ref)


def mention(uid, name, username="") -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={uid}">{html.escape(name or str(uid))}</a>'


# ============================================================ UMUMIY YORDAMCHILAR
async def is_member(bot: Bot, chat_id, uid, default=False) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, uid)
    except TelegramBadRequest:
        return default
    if m.status in (S.CREATOR, S.ADMINISTRATOR, S.MEMBER):
        return True
    return m.status == S.RESTRICTED and getattr(m, "is_member", False)


async def is_chan_admin(bot: Bot, chat_id, uid) -> bool:
    if uid == ADMIN_ID:
        return True
    try:
        m = await bot.get_chat_member(chat_id, uid)
    except TelegramBadRequest:
        return False
    return m.status in (S.CREATOR, S.ADMINISTRATOR)


async def chat_link(bot: Bot, chat_id) -> str:
    if chat_id in LINKS:
        return LINKS[chat_id]
    chat = await bot.get_chat(chat_id)
    link = f"https://t.me/{chat.username}" if chat.username else \
        (await bot.create_chat_invite_link(chat_id)).invite_link
    LINKS[chat_id] = link
    return link


def msg_link(chat_id, username, mid):
    if username:
        return f"https://t.me/{username}/{mid}"
    return f"https://t.me/c/{str(chat_id)[4:]}/{mid}"


def ib(text, data=None, url=None):
    return InlineKeyboardButton(text=text, callback_data=data, url=url)


def main_kb(uid) -> ReplyKeyboardMarkup:
    L = TX[lang(uid)]
    rows = [[KeyboardButton(text=L["b_battle"])],
            [KeyboardButton(text=L["b_my"]), KeyboardButton(text=L["b_profile"])],
            [KeyboardButton(text=L["b_guide"]), KeyboardButton(text=L["b_lang"])],
            [KeyboardButton(text=L["b_support"])]]
    if uid == ADMIN_ID:
        rows.append([KeyboardButton(text="🛠 Admin panel")])
    rows.append([KeyboardButton(text=L["b_menu"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu2_kb(uid) -> ReplyKeyboardMarkup:
    L = TX[lang(uid)]
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text=L["b_bonus"]), KeyboardButton(text=L["b_shop"])],
        [KeyboardButton(text=L["b_invite"])],
        [KeyboardButton(text=L["b_back"])]])


def cancel_kb(uid) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True,
                               keyboard=[[KeyboardButton(text=T(uid, "b_cancel"))]])


# ============================================================ MAJBURIY OBUNA + REFERAL
async def missing_channels(bot: Bot, uid):
    out = []
    for r in q("SELECT * FROM req_channels"):
        if not await is_member(bot, r["chat_id"], uid, default=True):
            out.append(r)
    return out


async def send_sub_prompt(bot: Bot, chat_id, uid, miss):
    kb = InlineKeyboardBuilder()
    for r in miss:
        kb.row(ib(f"📢 {r['title']}", url=r["link"]))
    kb.row(ib(T(uid, "sub_btn"), "subchk"))
    await bot.send_message(chat_id, T(uid, "sub_need"), reply_markup=kb.as_markup())


async def maybe_reward(bot: Bot, uid):
    u = q("SELECT ref_by, rewarded FROM users WHERE id=?", uid)
    if not u or not u[0]["ref_by"] or u[0]["rewarded"]:
        return
    ex("UPDATE users SET rewarded=1 WHERE id=?", uid)
    ref = u[0]["ref_by"]
    ex("UPDATE users SET balls=balls+? WHERE id=?", REF_BONUS, ref)
    try:
        await bot.send_message(ref, T(ref, "ref_ok", n=REF_BONUS))
    except Exception:
        pass


class Gate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        bot: Bot = data["bot"]
        user = event.from_user
        msg = event if isinstance(event, Message) else event.message
        if not user or not msg or msg.chat.type != "private":
            return await handler(event, data)
        ref = 0
        if isinstance(event, Message):
            mm = re.match(r"^/start r(\d+)", event.text or "")
            if mm:
                ref = int(mm.group(1))
        reg_user(user, ref)
        ex("UPDATE users SET blocked=0 WHERE id=? AND blocked=1", user.id)
        if user.id == ADMIN_ID:
            return await handler(event, data)
        if q("SELECT banned FROM users WHERE id=?", user.id)[0]["banned"]:
            await bot.send_message(msg.chat.id, T(user.id, "banned"))
            if isinstance(event, CallbackQuery):
                await event.answer()
            return
        if isinstance(event, Message) and re.match(r"^/start b\d+", event.text or ""):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and (event.data == "subchk" or event.data.startswith("chk:")):
            return await handler(event, data)
        miss = await missing_channels(bot, user.id)
        if miss:
            await send_sub_prompt(bot, msg.chat.id, user.id, miss)
            if isinstance(event, CallbackQuery):
                await event.answer()
            return
        await maybe_reward(bot, user.id)
        return await handler(event, data)


# ============================================================ BATTLE POSTI
def post_text(b) -> str:
    if not b["finished"]:
        return (
            "🏆 <b>OVOZ BATL BOSHLANDI</b> 🥱\n\n"
            f"@{UNAME} dan qilindi\n"
            "❗️ <b>Konkurs shartlari:</b> shu kanalga obuna bo'lish va do'stlaringiz "
            "sizga ovoz berishini so'rashdan iborat.\n\n"
            "⚠️ Agar ovoz beruvchi kanaldan chiqib ketsa, ovozi avtomatik olib tashlanadi ⛔️\n\n"
            "🎁 <b>Konkursga qo'yilgan yutuqlar:</b> — Hozircha Sir 🤫\n\n"
            "➕ Konkursga qo'shilish uchun quyidagi tugmani bosing 👇"
        )
    rows = standings(b["id"])
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else str(i + 1) + '.'} {html.escape(r['name'])} — <b>{r['c']}</b>"
             for i, r in enumerate(rows)]
    win = f"\n\n🏆 <b>G'olib:</b> {html.escape(rows[0]['name'])}" if rows and rows[0]["c"] else ""
    return ("🏁 <b>OVOZ BATL TUGADI</b>\n\n" + ("\n".join(lines) or "Ishtirokchilar bo'lmadi.") + win +
            f"\n\n@{UNAME} dan qilindi")


def keyboard(b) -> InlineKeyboardMarkup:
    bid = b["id"]
    kb = InlineKeyboardBuilder()
    if not b["finished"]:
        kb.row(ib("➕ Qatnashish", url=f"https://t.me/{UNAME}?start=b{bid}"))
    for r in standings(bid):
        kb.row(ib(f"{r['name'][:30]} ({r['c']})", f"v:{bid}:{r['user_id']}"))
    if b["finished"]:
        kb.row(ib("🏁 Battle tugagan", f"done:{bid}"))
    else:
        kb.row(ib("📊 Natijalar (battleni tugatish)", f"end:{bid}"))
    kb.row(ib("🗳 Ovoz berganlar", f"who:{bid}"))
    return kb.as_markup()


async def refresh(bot: Bot, bid: int):
    b = battle(bid)
    if not b or not b["message_id"]:
        return
    try:
        if b["finished"]:
            await bot.edit_message_text(post_text(b), chat_id=b["chat_id"],
                                        message_id=b["message_id"], reply_markup=keyboard(b))
        else:
            await bot.edit_message_reply_markup(chat_id=b["chat_id"], message_id=b["message_id"],
                                                reply_markup=keyboard(b))
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            logging.warning("refresh: %s", e)


@router.channel_post()
async def on_channel_post(m: Message, bot: Bot):
    txt = m.text or m.caption or ""
    if not re.match(r"(?i)^\s*#batl\b", txt):
        return
    try:
        await m.delete()
    except TelegramBadRequest:
        pass
    ex("""INSERT INTO chats(chat_id,title,username) VALUES(?,?,?)
          ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, username=excluded.username""",
       m.chat.id, m.chat.title or "", m.chat.username or "")
    bid = ex("INSERT INTO battles(chat_id) VALUES(?)", m.chat.id).lastrowid
    sent = await bot.send_message(m.chat.id, post_text(battle(bid)), reply_markup=keyboard(battle(bid)))
    ex("UPDATE battles SET message_id=? WHERE id=?", sent.message_id, bid)


async def try_join(bot: Bot, user, bid: int):
    b = battle(bid)
    if not b or b["finished"]:
        return "Bu battle tugagan yoki topilmadi.", None
    if not await is_member(bot, b["chat_id"], user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [ib("📢 Kanalga obuna bo'lish", url=await chat_link(bot, b["chat_id"]))],
            [ib("✅ Tekshirish", f"chk:{bid}")]])
        return "Qatnashish uchun avval kanalga obuna bo'ling 👇", kb
    name = f"@{user.username}" if user.username else user.full_name
    ex("INSERT OR REPLACE INTO participants(battle_id,user_id,name) VALUES(?,?,?)", bid, user.id, name)
    await refresh(bot, bid)
    return "✅ Siz battlega qo'shildingiz! Do'stlaringizdan ovoz so'rang 🔥", None


@router.callback_query(F.data.startswith("chk:"))
async def check(c: CallbackQuery, bot: Bot):
    text, kb = await try_join(bot, c.from_user, int(c.data.split(":")[1]))
    await c.message.edit_text(text, reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("v:"))
async def vote(c: CallbackQuery, bot: Bot):
    _, bid, pid = c.data.split(":")
    bid, pid = int(bid), int(pid)
    b = battle(bid)
    if not b or b["finished"]:
        return await c.answer("Battle tugagan 🏁", show_alert=True)
    if not q("SELECT 1 FROM participants WHERE battle_id=? AND user_id=?", bid, pid):
        return await c.answer("Ishtirokchi topilmadi", show_alert=True)
    if not await is_member(bot, b["chat_id"], c.from_user.id):
        return await c.answer("Ovoz berish uchun avval kanalga obuna bo'ling!", show_alert=True)
    if q("SELECT 1 FROM votes WHERE battle_id=? AND voter_id=?", bid, c.from_user.id):
        return await c.answer("Siz allaqachon ovoz bergansiz ✅", show_alert=True)
    ex("INSERT INTO votes VALUES(?,?,?,?)", bid, c.from_user.id, c.from_user.full_name, pid)
    await c.answer("✅ Ovozingiz qabul qilindi!")
    await refresh(bot, bid)


@router.callback_query(F.data.startswith("done:"))
async def done(c: CallbackQuery):
    await c.answer("Battle tugagan 🏁", show_alert=True)


@router.callback_query(F.data.startswith("end:"))
async def end(c: CallbackQuery, bot: Bot):
    bid = int(c.data.split(":")[1])
    b = battle(bid)
    if not b:
        return await c.answer()
    if not await is_chan_admin(bot, b["chat_id"], c.from_user.id):
        return await c.answer("Faqat kanal admini tugata oladi", show_alert=True)
    if b["finished"]:
        return await c.answer("Battle allaqachon tugagan 🏁", show_alert=True)
    ex("UPDATE battles SET finished=1 WHERE id=?", bid)
    await refresh(bot, bid)
    await c.answer("🏁 Battle tugadi!")


@router.callback_query(F.data.startswith("who:"))
async def who(c: CallbackQuery, bot: Bot):
    bid = int(c.data.split(":")[1])
    b = battle(bid)
    if not b:
        return await c.answer()
    if not await is_chan_admin(bot, b["chat_id"], c.from_user.id):
        return await c.answer("Bu tugma faqat kanal admini/egasi uchun 🔒", show_alert=True)
    out = []
    for p in standings(bid):
        voters = q("SELECT voter_id, voter_name FROM votes WHERE battle_id=? AND participant_id=?",
                   bid, p["user_id"])
        names = ", ".join(f'<a href="tg://user?id={v["voter_id"]}">{html.escape(v["voter_name"])}</a>'
                          for v in voters) or "—"
        out.append(f"<b>{html.escape(p['name'])}</b> ({p['c']}):\n{names}")
    text = "🗳 <b>Ovoz berganlar</b>\n\n" + ("\n\n".join(out) or "Hali ishtirokchi yo'q")
    try:
        for i in range(0, len(text), 3800):
            await bot.send_message(c.from_user.id, text[i:i + 3800])
        await c.answer("Ro'yxat shaxsiy xabarga yuborildi ✉️")
    except Exception:
        await c.answer("Avval botga o'tib /start bosing, so'ng qayta urining", show_alert=True)


@router.chat_member()
async def on_member(u: ChatMemberUpdated, bot: Bot):
    if u.new_chat_member.status not in (S.LEFT, S.KICKED):
        return
    uid = u.new_chat_member.user.id
    rows = q("""SELECT v.battle_id FROM votes v JOIN battles b ON b.id=v.battle_id
                WHERE v.voter_id=? AND b.chat_id=? AND b.finished=0""", uid, u.chat.id)
    for r in rows:
        ex("DELETE FROM votes WHERE battle_id=? AND voter_id=?", r["battle_id"], uid)
        await refresh(bot, r["battle_id"])


@router.my_chat_member()
async def on_my_member(u: ChatMemberUpdated, bot: Bot):
    st = u.new_chat_member.status
    if u.chat.type == "private":
        ex("UPDATE users SET blocked=? WHERE id=?", 1 if st == S.KICKED else 0, u.from_user.id)
        return
    if u.chat.type == "channel" and st == S.ADMINISTRATOR:
        ex("""INSERT INTO chats(chat_id,title,username,owner_id) VALUES(?,?,?,?)
              ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,
              username=excluded.username, owner_id=excluded.owner_id""",
           u.chat.id, u.chat.title or "", u.chat.username or "", u.from_user.id)
        try:
            await bot.send_message(u.from_user.id, T(u.from_user.id, "added", t=html.escape(u.chat.title or "")))
        except Exception:
            pass


async def sweeper(bot: Bot):
    while True:
        await asyncio.sleep(600)
        for b in q("SELECT * FROM battles WHERE finished=0"):
            changed = False
            for v in q("SELECT voter_id FROM votes WHERE battle_id=?", b["id"]):
                if not await is_member(bot, b["chat_id"], v["voter_id"], default=True):
                    ex("DELETE FROM votes WHERE battle_id=? AND voter_id=?", b["id"], v["voter_id"])
                    changed = True
                await asyncio.sleep(0.1)
            if changed:
                await refresh(bot, b["id"])


# ============================================================ /cancel (hamma uchun)
class Sup(StatesGroup):
    msg = State()


class Req(StatesGroup):
    ch = State()


class Bc(StatesGroup):
    msg = State()


class Gift(StatesGroup):
    name = State()
    price = State()
    qty = State()


@base.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(T(m.from_user.id, "cancelled"), reply_markup=main_kb(m.from_user.id))


# ============================================================ ADMIN PANEL
def admin_kb():
    kb = InlineKeyboardBuilder()
    kb.row(ib("📊 Statistika", "adm:stats"), ib("🏆 Ovoz battlelar", "adm:battles"))
    kb.row(ib("➕ Kanal qo'shish", "adm:chans"), ib("📢 Reklama tarqatish", "adm:bc"))
    kb.row(ib("🛍 Ball do'koni", "adm:shop"))
    return kb.as_markup()


ADMIN_TEXT = ("🛠 <b>Admin panel</b>\n\n"
              "Buyruqlar:\n<code>/ban ID</code> · <code>/unban ID</code> · <code>/ball ID soni</code>\n"
              "Murojaatga javob: xabarga <b>reply</b> qiling.")


async def show(c: CallbackQuery, text, kb=None):
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@admin.message(Command("admin"))
@admin.message(F.text == "🛠 Admin panel")
async def admin_panel(m: Message):
    await m.answer(ADMIN_TEXT, reply_markup=admin_kb())


# ---- state handlers (avval!) ----
@admin.message(Req.ch)
async def req_add(m: Message, state: FSMContext, bot: Bot):
    x = (m.text or "").strip()
    if m.forward_origin and getattr(m.forward_origin, "chat", None):
        x = m.forward_origin.chat.id
    else:
        x = re.sub(r"^https?://t\.me/", "", x).lstrip("@")
        x = int(x) if x.lstrip("-").isdigit() else "@" + x
    try:
        chat = await bot.get_chat(x)
        me = await bot.get_chat_member(chat.id, bot.id)
        if me.status != S.ADMINISTRATOR:
            return await m.answer("❌ Bot bu kanalda admin emas. Avval admin qiling, so'ng qayta yuboring.")
        link = f"https://t.me/{chat.username}" if chat.username else \
            (await bot.create_chat_invite_link(chat.id)).invite_link
    except Exception as e:
        return await m.answer(f"❌ Kanal topilmadi yoki bot admin emas.\n<code>{html.escape(str(e))}</code>")
    ex("INSERT OR REPLACE INTO req_channels VALUES(?,?,?)", chat.id, chat.title, link)
    await state.clear()
    await m.answer(f"✅ «{html.escape(chat.title)}» majburiy obunaga qo'shildi.", reply_markup=main_kb(m.from_user.id))
    text, kb = chans_view()
    await m.answer(text, reply_markup=kb)


@admin.message(Bc.msg)
async def bc_run(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    t = asyncio.create_task(broadcast(bot, m))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)


@admin.message(Gift.name)
async def gift_name(m: Message, state: FSMContext):
    await state.update_data(name=(m.text or "").strip()[:60])
    await state.set_state(Gift.price)
    await m.answer("💰 Necha ball? (masalan: 200)")


@admin.message(Gift.price)
async def gift_price(m: Message, state: FSMContext):
    n = re.search(r"\d+", m.text or "")
    if not n:
        return await m.answer("Raqam yozing, masalan: 200")
    await state.update_data(price=int(n.group()))
    await state.set_state(Gift.qty)
    await m.answer("📦 Nechta bor? (masalan: 5)")


@admin.message(Gift.qty)
async def gift_qty(m: Message, state: FSMContext):
    n = re.search(r"\d+", m.text or "")
    if not n:
        return await m.answer("Raqam yozing, masalan: 5")
    d = await state.get_data()
    await state.clear()
    ex("INSERT INTO gifts(name,price,qty) VALUES(?,?,?)", d["name"], d["price"], int(n.group()))
    await m.answer(f"✅ Qo'shildi: 🎁 {html.escape(d['name'])} — {d['price']} ball ({n.group()} ta)\n"
                   "Endi barcha foydalanuvchilar do'konda ko'radi.")


# ---- buyruqlar ----
@admin.message(Command("ban", "unban"))
async def ban(m: Message, command: CommandObject):
    if not (command.args or "").strip().isdigit():
        return await m.answer("Foydalanish: /ban ID")
    ex("UPDATE users SET banned=? WHERE id=?", 1 if command.command == "ban" else 0, int(command.args))
    await m.answer("✅ Bajarildi.")


@admin.message(Command("ball"))
async def give_ball(m: Message, command: CommandObject):
    a = (command.args or "").split()
    if len(a) != 2 or not re.fullmatch(r"\d+", a[0]) or not re.fullmatch(r"-?\d+", a[1]):
        return await m.answer("Foydalanish: /ball ID soni")
    ex("UPDATE users SET balls=MAX(0,balls+?) WHERE id=?", int(a[1]), int(a[0]))
    await m.answer("✅ Bajarildi.")


# ---- inline panel ----
def chans_view():
    rows = q("SELECT * FROM req_channels")
    kb = InlineKeyboardBuilder()
    text = "➕ <b>Majburiy obuna kanallari</b>\n\n"
    text += "\n".join(f"• {html.escape(r['title'])}" for r in rows) or "Hozircha yo'q."
    for r in rows:
        kb.row(ib(f"🗑 {r['title'][:30]}", f"adm:cdel:{r['chat_id']}"))
    kb.row(ib("➕ Kanal qo'shish", "adm:cadd"))
    kb.row(ib("⬅️ Orqaga", "adm:home"))
    return text, kb.as_markup()


def shop_admin_view():
    rows = q("SELECT * FROM gifts ORDER BY id")
    kb = InlineKeyboardBuilder()
    text = "🛍 <b>Ball do'koni</b>\n\n"
    text += "\n".join(f"🎁 {html.escape(g['name'])} — {g['price']} ball ({g['qty']} ta)" for g in rows) \
        or "Hozircha sovg'a yo'q."
    for g in rows:
        kb.row(ib(f"🗑 {g['name'][:30]}", f"adm:gdel:{g['id']}"))
    kb.row(ib("➕ Gift qo'shish", "adm:gadd"))
    kb.row(ib("⬅️ Orqaga", "adm:home"))
    return text, kb.as_markup()


@admin.callback_query(F.data.startswith("adm:"))
async def adm_cb(c: CallbackQuery, state: FSMContext):
    act = c.data[4:]
    await c.answer()
    back = InlineKeyboardMarkup(inline_keyboard=[[ib("⬅️ Orqaga", "adm:home")]])
    if act == "home":
        await state.clear()
        await show(c, ADMIN_TEXT, admin_kb())
    elif act == "stats":
        def n(sql, *a):
            return q(sql, *a)[0]["n"]
        await show(c, (
            "📊 <b>Statistika</b>\n\n"
            f"👥 Jami foydalanuvchi: <b>{n('SELECT COUNT(*) n FROM users')}</b>\n"
            f"🆕 Bugun qo'shilgan: <b>{n('SELECT COUNT(*) n FROM users WHERE joined=?', today())}</b>\n"
            f"🚫 Banlangan: <b>{n('SELECT COUNT(*) n FROM users WHERE banned=1')}</b>\n"
            f"⛔️ Botni bloklaganlar: <b>{n('SELECT COUNT(*) n FROM users WHERE blocked=1')}</b>"), back)
    elif act == "battles":
        rows = q("""SELECT b.chat_id, COUNT(DISTINCT b.id) bn, COUNT(v.voter_id) vn
                    FROM battles b LEFT JOIN votes v ON v.battle_id=b.id
                    GROUP BY b.chat_id ORDER BY vn DESC, bn DESC LIMIT 10""")
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            ch = q("SELECT title FROM chats WHERE chat_id=?", r["chat_id"])
            title = html.escape(ch[0]["title"]) if ch and ch[0]["title"] else str(r["chat_id"])
            lines.append(f"{medals[i] if i < 3 else str(i + 1) + '.'} <b>{title}</b>\n"
                         f"   🥊 {r['bn']} ta battle · 🗳 {r['vn']} ta ovoz")
        tb = q("SELECT COUNT(*) n FROM battles")[0]["n"]
        tv = q("SELECT COUNT(*) n FROM votes")[0]["n"]
        await show(c, f"🏆 <b>Ovoz battlelar</b>\n\nJami: 🥊 {tb} ta battle · 🗳 {tv} ta ovoz\n\n" +
                   ("\n\n".join(lines) or "Hali battle yo'q."), back)
    elif act == "chans":
        text, kb = chans_view()
        await show(c, text, kb)
    elif act == "cadd":
        await state.set_state(Req.ch)
        await c.message.answer("📢 Kanal <b>@username</b> yoki ID sini yuboring (yoki kanaldan post forward qiling).\n"
                               "Bot o'sha kanalda <b>admin</b> bo'lishi shart. Bekor qilish: /cancel")
    elif act.startswith("cdel:"):
        ex("DELETE FROM req_channels WHERE chat_id=?", int(act[5:]))
        text, kb = chans_view()
        await show(c, text, kb)
    elif act == "bc":
        await state.set_state(Bc.msg)
        await c.message.answer("📢 Yuboriladigan xabarni yuboring (matn, rasm, video...). "
                               "Hamma foydalanuvchiga boradi.\nBekor qilish: /cancel")
    elif act == "shop":
        text, kb = shop_admin_view()
        await show(c, text, kb)
    elif act == "gadd":
        await state.set_state(Gift.name)
        await c.message.answer("🎁 Gift nomi? (masalan: Gift)\nBekor qilish: /cancel")
    elif act.startswith("gdel:"):
        ex("DELETE FROM gifts WHERE id=?", int(act[5:]))
        text, kb = shop_admin_view()
        await show(c, text, kb)


async def broadcast(bot: Bot, m: Message):
    ids = [r["id"] for r in q("SELECT id FROM users WHERE banned=0")]
    ok = fail = 0
    status = await m.answer(f"📤 Yuborilmoqda... 0/{len(ids)}")
    for i, uid in enumerate(ids, 1):
        try:
            await bot.copy_message(uid, m.chat.id, m.message_id)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(uid, m.chat.id, m.message_id)
                ok += 1
            except Exception:
                fail += 1
        except TelegramForbiddenError:
            ex("UPDATE users SET blocked=1 WHERE id=?", uid)
            fail += 1
        except Exception:
            fail += 1
        if i % 50 == 0:
            try:
                await status.edit_text(f"📤 Yuborilmoqda... {i}/{len(ids)}")
            except TelegramBadRequest:
                pass
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ <b>Reklama tugadi</b>\n\n👥 Jami: {len(ids)}\n"
                           f"✅ Yuborildi: <b>{ok}</b>\n❌ Yuborilmadi: <b>{fail}</b>")


# murojaatga admin javobi (eng oxirida)
@admin.message(F.reply_to_message)
async def admin_reply(m: Message, bot: Bot):
    r = q("SELECT user_id FROM support WHERE msg_id=?", m.reply_to_message.message_id)
    if not r:
        return
    try:
        await bot.copy_message(r[0]["user_id"], m.chat.id, m.message_id)
        await m.answer("✅ Javob yuborildi.")
    except Exception:
        await m.answer("❌ Yuborib bo'lmadi (foydalanuvchi botni bloklagan bo'lishi mumkin).")


# ============================================================ FOYDALANUVCHI
@router.message(Sup.msg)
async def sup_msg(m: Message, state: FSMContext, bot: Bot):
    uid = m.from_user.id
    await state.clear()
    if m.text in ALL("b_cancel"):
        return await m.answer(T(uid, "cancelled"), reply_markup=main_kb(uid))
    head = await bot.send_message(
        ADMIN_ID, f"✉️ <b>Yangi murojaat</b>\n👤 {mention(uid, m.from_user.full_name, m.from_user.username or '')}\n"
                  f"🆔 <code>{uid}</code>\n\n↩️ Javob berish uchun shu xabarga <b>reply</b> qiling.")
    cp = await bot.copy_message(ADMIN_ID, m.chat.id, m.message_id)
    for mid in (head.message_id, cp.message_id):
        ex("INSERT OR REPLACE INTO support VALUES(?,?)", mid, uid)
    await m.answer(T(uid, "support_sent"), reply_markup=main_kb(uid))


@router.message(CommandStart())
async def start(m: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    uid = m.from_user.id
    arg = command.args or ""
    if re.fullmatch(r"b\d+", arg):
        text, kb = await try_join(bot, m.from_user, int(arg[1:]))
        return await m.answer(text, reply_markup=kb)
    await m.answer(T(uid, "welcome"), reply_markup=main_kb(uid))


@router.callback_query(F.data == "subchk")
async def subchk(c: CallbackQuery, bot: Bot):
    uid = c.from_user.id
    if await missing_channels(bot, uid):
        return await c.answer(T(uid, "sub_fail"), show_alert=True)
    await maybe_reward(bot, uid)
    try:
        await c.message.delete()
    except TelegramBadRequest:
        pass
    await c.message.answer(T(uid, "sub_ok"), reply_markup=main_kb(uid))
    await c.answer()


@router.message(F.text.in_(ALL("b_battle")))
async def b_battle(m: Message):
    uid = m.from_user.id
    url = (f"https://t.me/{UNAME}?startchannel&admin=post_messages+edit_messages"
           "+delete_messages+invite_users")
    await m.answer(T(uid, "battle_info"),
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib(T(uid, "add_ch"), url=url)]]))


@router.message(F.text.in_(ALL("b_my")))
async def b_my(m: Message):
    uid = m.from_user.id
    rows = q("""SELECT b.id,b.chat_id,b.message_id,b.finished,c.title,c.username,
                (SELECT COUNT(*) FROM participants p WHERE p.battle_id=b.id) pn,
                (SELECT COUNT(*) FROM votes v WHERE v.battle_id=b.id) vn
                FROM battles b JOIN chats c ON c.chat_id=b.chat_id
                WHERE c.owner_id=? ORDER BY b.id DESC LIMIT 10""", uid)
    if not rows:
        return await m.answer(T(uid, "my_none"))
    kb = InlineKeyboardBuilder()
    text = T(uid, "my_head")
    for r in rows:
        text += (f"{'🏁' if r['finished'] else '🟢'} <b>#{r['id']}</b> — {html.escape(r['title'] or '')}\n"
                 f"👥 {r['pn']} · 🗳 {r['vn']}\n\n")
        if r["message_id"]:
            kb.row(ib(f"#{r['id']} → {(r['title'] or '')[:25]}",
                      url=msg_link(r["chat_id"], r["username"], r["message_id"])))
    await m.answer(text, reply_markup=kb.as_markup())


@router.message(F.text.in_(ALL("b_profile")))
async def b_profile(m: Message):
    uid = m.from_user.id
    u = q("SELECT balls FROM users WHERE id=?", uid)[0]
    n = q("SELECT COUNT(*) n FROM users WHERE ref_by=? AND rewarded=1", uid)[0]["n"]
    await m.answer(T(uid, "profile", id=uid, name=html.escape(m.from_user.full_name),
                     b=u["balls"], n=n, l="🇺🇿 O'zbekcha" if lang(uid) == "uz" else "🇷🇺 Русский"))


@router.message(F.text.in_(ALL("b_guide")))
async def b_guide(m: Message):
    await m.answer(T(m.from_user.id, "guide"))


@router.message(F.text.in_(ALL("b_lang")))
async def b_lang(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[ib("🇺🇿 O'zbekcha", "lang:uz"), ib("🇷🇺 Русский", "lang:ru")]])
    await m.answer(T(m.from_user.id, "lang_pick"), reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(c: CallbackQuery):
    uid = c.from_user.id
    ex("UPDATE users SET lang=? WHERE id=?", c.data[5:], uid)
    await c.answer()
    await c.message.answer(T(uid, "lang_set"), reply_markup=main_kb(uid))


@router.message(F.text.in_(ALL("b_support")))
async def b_support(m: Message, state: FSMContext):
    await state.set_state(Sup.msg)
    await m.answer(T(m.from_user.id, "support_ask"), reply_markup=cancel_kb(m.from_user.id))


@router.message(F.text.in_(ALL("b_menu")))
async def b_menu(m: Message):
    await m.answer(T(m.from_user.id, "menu2"), reply_markup=menu2_kb(m.from_user.id))


@router.message(F.text.in_(ALL("b_back")))
async def b_back(m: Message):
    await m.answer(T(m.from_user.id, "welcome"), reply_markup=main_kb(m.from_user.id))


@router.message(F.text.in_(ALL("b_bonus")))
async def b_bonus(m: Message):
    uid = m.from_user.id
    u = q("SELECT bonus_date FROM users WHERE id=?", uid)[0]
    if u["bonus_date"] == today():
        return await m.answer(T(uid, "bonus_no"))
    ex("UPDATE users SET balls=balls+?, bonus_date=? WHERE id=?", DAILY_BONUS, today(), uid)
    b = q("SELECT balls FROM users WHERE id=?", uid)[0]["balls"]
    await m.answer(T(uid, "bonus_ok", x=DAILY_BONUS, b=b))


def shop_view(uid):
    bal = q("SELECT balls FROM users WHERE id=?", uid)[0]["balls"]
    gifts = q("SELECT * FROM gifts WHERE qty>0 ORDER BY id")
    if not gifts:
        return T(uid, "shop_empty", b=bal), None
    kb = InlineKeyboardBuilder()
    for g in gifts:
        kb.row(ib(f"🎁 {g['name']} — {g['price']} 💰 ({g['qty']})", f"buy:{g['id']}"))
    return T(uid, "shop_head", b=bal), kb.as_markup()


@router.message(F.text.in_(ALL("b_shop")))
async def b_shop(m: Message):
    text, kb = shop_view(m.from_user.id)
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery, bot: Bot):
    uid = c.from_user.id
    g = q("SELECT * FROM gifts WHERE id=?", int(c.data[4:]))
    if not g or g[0]["qty"] <= 0:
        await c.answer(T(uid, "sold_out"), show_alert=True)
    else:
        g = g[0]
        if ex("UPDATE users SET balls=balls-? WHERE id=? AND balls>=?", g["price"], uid, g["price"]).rowcount == 0:
            b = q("SELECT balls FROM users WHERE id=?", uid)[0]["balls"]
            return await c.answer(T(uid, "no_balls", b=b), show_alert=True)
        if ex("UPDATE gifts SET qty=qty-1 WHERE id=? AND qty>0", g["id"]).rowcount == 0:
            ex("UPDATE users SET balls=balls+? WHERE id=?", g["price"], uid)
            await c.answer(T(uid, "sold_out"), show_alert=True)
        else:
            ex("INSERT INTO orders(user_id,gift_id,gift_name,price,ts) VALUES(?,?,?,?,?)",
               uid, g["id"], g["name"], g["price"], datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
            await c.answer(T(uid, "bought", g=g["name"]), show_alert=True)
            await bot.send_message(
                ADMIN_ID, f"🛍 <b>Yangi buyurtma</b>\n\n🎁 Sovg'a: <b>{html.escape(g['name'])}</b>\n"
                          f"💰 Narx: {g['price']} ball\n👤 Kim: {mention(uid, c.from_user.full_name, c.from_user.username or '')}\n"
                          f"🆔 <code>{uid}</code>\n"
                          f"🔗 <a href=\"tg://user?id={uid}\">Profilni ochish</a>")
    text, kb = shop_view(uid)
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.message(F.text.in_(ALL("b_invite")))
async def b_invite(m: Message):
    uid = m.from_user.id
    link = f"https://t.me/{UNAME}?start=r{uid}"
    n = q("SELECT COUNT(*) n FROM users WHERE ref_by=? AND rewarded=1", uid)[0]["n"]
    share = f"https://t.me/share/url?url={link}&text={T(uid, 'share_text')}"
    await m.answer(T(uid, "invite", r=REF_BONUS, link=link, n=n),
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib(T(uid, "share_btn"), url=share)]]))


# ============================================================ MAIN
async def main():
    global UNAME
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                                      link_preview_is_disabled=True))
    UNAME = (await bot.get_me()).username
    dp = Dispatcher()
    dp.message.outer_middleware(Gate())
    dp.callback_query.outer_middleware(Gate())
    dp.include_routers(base, admin, router)

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080"))).start()

    asyncio.create_task(sweeper(bot))
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
