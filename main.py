import asyncio
import html
import logging
import os
import re
import sqlite3
import time
import shutil
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
 
import aiohttp
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
ADMIN_ID = int(os.getenv("ADMIN_ID", "8327302562"))
# Doimiy saqlash: Render kabi hostingda /data diskini ulab DB_PATH=/data/battle.db qiling.
# /data mavjud bo'lsa shu joy tanlanadi; eski lokal battle.db bo'lsa birinchi ishga tushishda ko'chiriladi.
_default_db = "/data/battle.db" if os.path.isdir("/data") else "battle.db"
DB_PATH = os.getenv("DB_PATH", _default_db)
_db_parent = os.path.dirname(os.path.abspath(DB_PATH))
os.makedirs(_db_parent, exist_ok=True)
if os.path.abspath(DB_PATH) != os.path.abspath("battle.db") and not os.path.exists(DB_PATH) and os.path.isfile("battle.db"):
    shutil.copy2("battle.db", DB_PATH)
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
PENDING: dict[int, int] = {}      # obuna bo'lgach davom ettiriladigan battle qatnashuvi

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
