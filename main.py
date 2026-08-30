# -*- coding: utf-8 -*-
"""
Telegram Universal MenuBuilder-style Bot
Python 3.11+
python-telegram-bot 21.x
Flask webhook / Render or polling-friendly local mode
SQLite

IMPORTANT:
- Put BOT_TOKEN and ADMIN_ID in Environment Variables.
- Never put your BotFather token directly in this file.
"""

import os
import asyncio
import threading
import html
import sqlite3
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# معرف الأدمن الأساسي
ADMIN_ID = 5734654153

def is_admin(user_id):
    """True only for the configured administrator."""
    try:
        return int(user_id) == ADMIN_ID
    except (TypeError, ValueError):
        return False

PORT = int(os.getenv("PORT", "10000") or 10000)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")

DB_FILE = os.getenv("DB_FILE", "bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("universal-menu-bot")


def repair_mojibake(value):
    """Repair common UTF-8 -> Latin-1/Windows-1252 mojibake safely."""
    if not isinstance(value, str) or not value:
        return value

    markers = ("Ø", "Ù", "Ð", "Ã", "Â", "â", "ð", "ï", "")
    if not any(ch in value for ch in markers):
        return value

    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value

    old_score = sum(value.count(ch) for ch in markers)
    new_score = sum(repaired.count(ch) for ch in markers)
    return repaired if new_score < old_score else value


def repair_database_text():
    """Fix legacy mojibake stored in settings/buttons/content titles."""
    conn = db()
    cur = conn.cursor()
    for table, column in (("settings", "value"), ("buttons", "title"),
                          ("contents", "title")):
        try:
            rows = cur.execute(f"SELECT rowid, {column} FROM {table}").fetchall()
            for row in rows:
                fixed = repair_mojibake(row[1])
                if fixed != row[1]:
                    cur.execute(
                        f"UPDATE {table} SET {column}=? WHERE rowid=?",
                        (fixed, row[0]),
                    )
        except sqlite3.Error:
            logger.exception("Unicode repair failed for %s.%s", table, column)
    conn.commit()
    conn.close()


app = Flask(__name__)
telegram_app = None


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        username TEXT DEFAULT '',
        joined_at TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        visits INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        notifications INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER,
        title TEXT NOT NULL,
        action_type TEXT NOT NULL DEFAULT 'section',
        action_value TEXT DEFAULT '',
        position INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(parent_id) REFERENCES buttons(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS contents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        button_id INTEGER NOT NULL,
        source_chat_id INTEGER NOT NULL,
        source_message_id INTEGER NOT NULL,
        content_type TEXT DEFAULT 'message',
        title TEXT DEFAULT '',
        published INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(button_id) REFERENCES buttons(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS favorites (
        user_id INTEGER NOT NULL,
        button_id INTEGER NOT NULL,
        PRIMARY KEY(user_id, button_id),
        FOREIGN KEY(button_id) REFERENCES buttons(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        button_id INTEGER,
        rating INTEGER NOT NULL,
        comment TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT DEFAULT '',
        source_chat_id INTEGER,
        source_message_id INTEGER,
        created_at TEXT NOT NULL,
        answered INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER,
        source_chat_id INTEGER,
        source_message_id INTEGER,
        title TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        button_id INTEGER,
        created_at TEXT NOT NULL
    );
    """)

    defaults = {
        "bot_name": "🤖 المساعد الذكي",
        "home_title": "🏠 الرئيسية",
        "home_text": "👋 أهلاً بك!\n\n✨ اختر من القائمة أدناه:",
        "about_text": "ℹ️ <b>حول البوت</b>\n\nبوت عام قابل للتخصيص بالكامل من لوحة الإدارة.",
        "maintenance": "0",
        "maintenance_text": "🛠 البوت حالياً تحت الصيانة.\n\n⏳ حاول لاحقاً.",
        "notifications_text": "🔔 هل تريد استقبال إشعارات عند إضافة محتوى جديد؟",
        "announcement_text": "📢 إعلان جديد",
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, value),
        )

    root_count = cur.execute(
        "SELECT COUNT(*) AS c FROM buttons WHERE parent_id IS NULL"
    ).fetchone()["c"]

    if root_count == 0:
        roots = [
            ("📚 الأقسام", "menu"),
            ("⭐ المفضلة", "favorites"),
            ("🔎 البحث", "search"),
            ("🔔 الإشعارات", "notifications"),
            ("⭐ تقييم البوت", "rating"),
            ("💬 مراسلة الإدارة", "contact"),
            ("ℹ️ حول البوت", "about"),
        ]
        for pos, (title, action) in enumerate(roots):
            cur.execute("""
                INSERT INTO buttons
                (parent_id,title,action_type,action_value,position,created_at)
                VALUES(NULL,?,?,?,?,?)
            """, (title, action, "", pos, now()))

    conn.commit()
    conn.close()


# ============================================================
# SETTINGS / DB HELPERS
# ============================================================

def get_setting(key, default=""):
    conn = db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = db()
    conn.execute("""
        INSERT INTO settings(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()
    conn.close()


def save_user(user):
    conn = db()
    stamp = now()
    exists = conn.execute(
        "SELECT user_id FROM users WHERE user_id=?", (user.id,)
    ).fetchone()

    if exists:
        conn.execute("""
            UPDATE users
            SET first_name=?, last_name=?, username=?, last_seen=?, visits=visits+1
            WHERE user_id=?
        """, (
            user.first_name or "",
            user.last_name or "",
            user.username or "",
            stamp,
            user.id,
        ))
    else:
        conn.execute("""
            INSERT INTO users
            (user_id,first_name,last_name,username,joined_at,last_seen,visits)
            VALUES(?,?,?,?,?,?,1)
        """, (
            user.id,
            user.first_name or "",
            user.last_name or "",
            user.username or "",
            stamp,
            stamp,
        ))
    conn.commit()
    conn.close()


def is_banned(user_id):
    conn = db()
    row = conn.execute(
        "SELECT banned FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row and row["banned"])


def set_banned(user_id, value):
    conn = db()
    conn.execute(
        "UPDATE users SET banned=? WHERE user_id=?",
        (1 if value else 0, user_id),
    )
    conn.commit()
    conn.close()


def set_notifications(user_id, enabled):
    conn = db()
    conn.execute(
        "UPDATE users SET notifications=? WHERE user_id=?",
        (1 if enabled else 0, user_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# BUTTON / CONTENT HELPERS
# ============================================================

def get_button(button_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM buttons WHERE id=?", (button_id,)
    ).fetchone()
    conn.close()
    return row


def get_buttons(parent_id=None, enabled_only=True):
    conn = db()
    if enabled_only:
        rows = conn.execute("""
            SELECT * FROM buttons
            WHERE parent_id IS ? AND enabled=1
            ORDER BY position,id
        """, (parent_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM buttons
            WHERE parent_id IS ?
            ORDER BY position,id
        """, (parent_id,)).fetchall()
    conn.close()
    return rows


def all_buttons():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM buttons ORDER BY parent_id,position,id"
    ).fetchall()
    conn.close()
    return rows


def next_position(parent_id):
    conn = db()
    value = conn.execute(
        "SELECT COALESCE(MAX(position),-1)+1 AS p FROM buttons WHERE parent_id IS ?",
        (parent_id,),
    ).fetchone()["p"]
    conn.close()
    return value


def add_button(title, parent_id, action_type="menu", action_value=""):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO buttons
        (parent_id,title,action_type,action_value,position,enabled,created_at)
        VALUES(?,?,?,?,?,1,?)
    """, (
        parent_id, title, action_type, action_value,
        next_position(parent_id), now()
    ))
    bid = cur.lastrowid
    conn.commit()
    conn.close()
    return bid


def update_button(button_id, **fields):
    allowed = {
        "title", "parent_id", "action_type",
        "action_value", "position", "enabled"
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    sql = ", ".join(f"{k}=?" for k in clean)
    values = list(clean.values()) + [button_id]
    conn = db()
    conn.execute(f"UPDATE buttons SET {sql} WHERE id=?", values)
    conn.commit()
    conn.close()


def descendants(button_id):
    found = set()
    queue = [button_id]
    while queue:
        current = queue.pop()
        for row in get_buttons(current, enabled_only=False):
            if row["id"] not in found:
                found.add(row["id"])
                queue.append(row["id"])
    return found


def delete_button_tree(button_id):
    conn = db()
    ids = [button_id]
    queue = [button_id]
    while queue:
        current = queue.pop()
        children = conn.execute(
            "SELECT id FROM buttons WHERE parent_id=?", (current,)
        ).fetchall()
        for child in children:
            ids.append(child["id"])
            queue.append(child["id"])

    marks = ",".join("?" for _ in ids)
    conn.execute(f"DELETE FROM buttons WHERE id IN ({marks})", ids)
    conn.commit()
    conn.close()


def move_button(button_id, new_parent):
    if button_id == new_parent:
        return False
    if new_parent is not None and new_parent in descendants(button_id):
        return False
    update_button(
        button_id,
        parent_id=new_parent,
        position=next_position(new_parent),
    )
    return True


def add_content(button_id, message, title=""):
    ctype = detect_content_type(message)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contents
        (button_id,source_chat_id,source_message_id,content_type,title,published,created_at)
        VALUES(?,?,?,?,?,?,?)
    """, (
        button_id,
        message.chat_id,
        message.message_id,
        ctype,
        title or default_title(message, ctype),
        1,
        now(),
    ))
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_contents(button_id, published_only=True):
    conn = db()
    if published_only:
        rows = conn.execute("""
            SELECT * FROM contents
            WHERE button_id=? AND published=1
            ORDER BY id
        """, (button_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM contents WHERE button_id=? ORDER BY id
        """, (button_id,)).fetchall()
    conn.close()
    return rows


def get_content(content_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM contents WHERE id=?", (content_id,)
    ).fetchone()
    conn.close()
    return row


def delete_content(content_id):
    conn = db()
    conn.execute("DELETE FROM contents WHERE id=?", (content_id,))
    conn.commit()
    conn.close()


def toggle_favorite(user_id, button_id):
    conn = db()
    exists = conn.execute("""
        SELECT 1 FROM favorites WHERE user_id=? AND button_id=?
    """, (user_id, button_id)).fetchone()

    if exists:
        conn.execute(
            "DELETE FROM favorites WHERE user_id=? AND button_id=?",
            (user_id, button_id),
        )
        result = False
    else:
        conn.execute(
            "INSERT INTO favorites(user_id,button_id) VALUES(?,?)",
            (user_id, button_id),
        )
        result = True

    conn.commit()
    conn.close()
    return result


def is_favorite(user_id, button_id):
    conn = db()
    row = conn.execute("""
        SELECT 1 FROM favorites WHERE user_id=? AND button_id=?
    """, (user_id, button_id)).fetchone()
    conn.close()
    return bool(row)


def detect_content_type(message):
    if message.document:
        return "document"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.animation:
        return "animation"
    if message.text:
        return "text"
    return "message"


def default_title(message, ctype):
    if message.text:
        text = message.text.strip().replace("\n", " ")
        return text[:80] or "محتوى نصي"
    return {
        "document": "📄 ملف",
        "photo": "🖼 صورة",
        "video": "🎥 فيديو",
        "audio": "🎵 صوت",
        "voice": "🎙 رسالة صوتية",
        "animation": "🎞 GIF",
    }.get(ctype, "📦 محتوى")


# ============================================================
# KEYBOARDS
# ============================================================

def reply_kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def home_keyboard():
    rows = []
    for b in get_buttons(None):
        rows.append([KeyboardButton(b["title"])])
    return reply_kb(rows)


def admin_keyboard():
    return reply_kb([
        ["⚙️ إعدادات البوت", "🎛 محرر الأزرار"],
        ["📝 محرر المحتوى", "📢 الإعلان"],
        ["📣 رسالة جماعية", "🔔 الإشعارات"],
        ["💬 المراسلات", "⭐ التقييمات"],
        ["👥 المستخدمون", "📊 الإحصائيات"],
        ["🛠 الصيانة", "👁 المعاينة"],
        ["🏠 واجهة المستخدم"],
    ])


def cancel_keyboard():
    return reply_kb([["❌ إلغاء"]])


def admin_button_selector(prefix="BTN"):
    rows = []
    for b in all_buttons():
        rows.append([
            KeyboardButton(f"{b['title']} 〔{b['id']}〕")
        ])
    rows.append([KeyboardButton("🏠 الرئيسية")])
    rows.append([KeyboardButton("❌ إلغاء")])
    return reply_kb(rows)


def parse_id_from_button_text(text):
    if "〔" not in text or "〕" not in text:
        return None
    try:
        return int(text.rsplit("〔", 1)[1].split("〕", 1)[0])
    except (ValueError, IndexError):
        return None


# ============================================================
# HOME / USER CONTENT
# ============================================================

async def show_home(update):
    await update.effective_message.reply_text(
        get_setting("home_text"),
        parse_mode=ParseMode.HTML,
        reply_markup=home_keyboard(),
    )


async def show_button(update, button_id):
    button = get_button(button_id)
    if not button or not button["enabled"]:
        await update.effective_message.reply_text("❌ هذا الزر غير متاح.")
        return

    user_id = update.effective_user.id

    conn = db()
    conn.execute(
        "INSERT INTO visits(user_id,button_id,created_at) VALUES(?,?,?)",
        (user_id, button_id, now()),
    )
    conn.commit()
    conn.close()

    action = button["action_type"]

    if action == "search":
        context = update._context
        context.user_data["state"] = "USER_SEARCH"
        await update.effective_message.reply_text(
            "🔎 أرسل كلمة البحث:",
            reply_markup=cancel_keyboard(),
        )
        return

    if action == "favorites":
        await show_favorites(update)
        return

    if action == "notifications":
        await show_notification_settings(update)
        return

    if action == "rating":
        await start_rating(update)
        return

    if action == "contact":
        update._context.user_data["state"] = "USER_CONTACT"
        await update.effective_message.reply_text(
            "💬 أرسل رسالتك للإدارة:",
            reply_markup=cancel_keyboard(),
        )
        return

    if action == "about":
        await update.effective_message.reply_text(
            get_setting("about_text"),
            parse_mode=ParseMode.HTML,
            reply_markup=home_keyboard(),
        )
        return

    if action == "url" and button["action_value"]:
        await update.effective_message.reply_text(
            f"🔗 {html.escape(button['action_value'])}",
            parse_mode=ParseMode.HTML,
            reply_markup=home_keyboard(),
        )
        return

    if action == "content":
        for c in get_contents(button_id):
            try:
                await telegram_app.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=c["source_chat_id"],
                    message_id=c["source_message_id"],
                )
            except Exception:
                logger.exception("copy content failed")
        await section_actions(update, button_id)
        return

    children = get_buttons(button_id)
    contents = get_contents(button_id)

    rows = [[KeyboardButton(child["title"])] for child in children]

    for c in contents:
        rows.append([
            KeyboardButton(f"📄 {c['title'][:60]} 〔C{c['id']}〕")
        ])

    fav = is_favorite(user_id, button_id)
    rows.append([
        KeyboardButton("💔 إزالة من المفضلة" if fav else "⭐ إضافة للمفضلة")
    ])
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 الرئيسية")])

    await update.effective_message.reply_text(
        f"📚 <b>{html.escape(button['title'])}</b>\n\nاختر:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb(rows),
    )


async def section_actions(update, button_id):
    fav = is_favorite(update.effective_user.id, button_id)
    await update.effective_message.reply_text(
        "✨ ماذا تريد أن تفعل؟",
        reply_markup=reply_kb([
            ["💔 إزالة من المفضلة" if fav else "⭐ إضافة للمفضلة"],
            ["⭐ تقييم المحتوى"],
            ["⬅️ رجوع", "🏠 الرئيسية"],
        ]),
    )


async def show_favorites(update):
    conn = db()
    rows = conn.execute("""
        SELECT b.* FROM favorites f
        JOIN buttons b ON b.id=f.button_id
        WHERE f.user_id=? AND b.enabled=1
        ORDER BY b.position,b.id
    """, (update.effective_user.id,)).fetchall()
    conn.close()

    if not rows:
        await update.effective_message.reply_text(
            "⭐ لا توجد عناصر في المفضلة بعد.",
            reply_markup=home_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        "⭐ <b>المفضلة</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb(
            [[KeyboardButton(r["title"])] for r in rows] +
            [["🏠 الرئيسية"]]
        ),
    )


async def show_notification_settings(update):
    conn = db()
    row = conn.execute(
        "SELECT notifications FROM users WHERE user_id=?",
        (update.effective_user.id,),
    ).fetchone()
    conn.close()
    enabled = bool(row and row["notifications"])

    await update.effective_message.reply_text(
        get_setting("notifications_text"),
        reply_markup=reply_kb([
            ["🔕 إيقاف الإشعارات" if enabled else "🔔 تفعيل الإشعارات"],
            ["🏠 الرئيسية"],
        ]),
    )


async def start_rating(update):
    update._context.user_data["state"] = "USER_RATING"
    await update.effective_message.reply_text(
        "⭐ اختر تقييمك من 1 إلى 5:",
        reply_markup=reply_kb([
            ["⭐ 1", "⭐⭐ 2"],
            ["⭐⭐⭐ 3"],
            ["⭐⭐⭐⭐ 4", "⭐⭐⭐⭐⭐ 5"],
            ["❌ إلغاء"],
        ]),
    )


# ============================================================
# ADMIN PANEL
# ============================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            await update.effective_message.reply_text("⛔ غير مسموح.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def show_admin(update):
    await update.effective_message.reply_text(
        "👑 <b>لوحة الإدارة</b>\n\n"
        "🎛 من هنا تتحكم بكل واجهة البوت ومحتواه وإعداداته.",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_settings(update, context):
    context.user_data["state"] = "ADMIN_SETTINGS"
    await update.effective_message.reply_text(
        "⚙️ <b>إعدادات البوت</b>\n\n"
        "اختر ما تريد تغييره:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["✏️ اسم البوت", "🏠 اسم الرئيسية"],
            ["📝 نص الرئيسية", "ℹ️ نص حول البوت"],
            ["🛠 نص الصيانة", "🔔 نص الإشعارات"],
            ["📢 نص الإعلان"],
            ["⬅️ رجوع"],
        ]),
    )


async def admin_buttons(update, context):
    context.user_data["state"] = "ADMIN_BUTTONS"
    await update.effective_message.reply_text(
        "🎛 <b>محرر الأزرار</b>\n\n"
        "الإضافة والتعديل والحذف والنقل كلها من هنا.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["➕ إضافة زر", "✏️ تعديل زر"],
            ["🗑 حذف زر", "🔄 نقل زر"],
            ["📋 عرض الأزرار"],
            ["⬅️ رجوع"],
        ]),
    )


async def admin_content(update, context):
    context.user_data["state"] = "ADMIN_CONTENT"
    await update.effective_message.reply_text(
        "📝 <b>محرر المحتوى</b>\n\n"
        "أضف أي رسالة/صورة/فيديو/ملف داخل أي زر.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["➕ إضافة محتوى", "✏️ تعديل محتوى"],
            ["🗑 حذف محتوى", "👁 عرض المحتوى"],
            ["⬅️ رجوع"],
        ]),
    )


async def admin_preview(update, context):
    await update.effective_message.reply_text(
        "👁 <b>نظام المعاينة</b>\n\n"
        "المعاينة تظهر للمستخدم بنفس أسلوب العرض قبل اعتماد النشر.",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_stats(update, context):
    conn = db()
    values = {
        "users": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "buttons": conn.execute("SELECT COUNT(*) c FROM buttons").fetchone()["c"],
        "contents": conn.execute("SELECT COUNT(*) c FROM contents").fetchone()["c"],
        "favorites": conn.execute("SELECT COUNT(*) c FROM favorites").fetchone()["c"],
        "ratings": conn.execute("SELECT COUNT(*) c FROM ratings").fetchone()["c"],
        "messages": conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"],
    }
    conn.close()

    await update.effective_message.reply_text(
        "📊 <b>الإحصائيات</b>\n\n"
        f"👥 المستخدمون: <b>{values['users']}</b>\n"
        f"🔘 الأزرار: <b>{values['buttons']}</b>\n"
        f"📝 المحتوى: <b>{values['contents']}</b>\n"
        f"⭐ المفضلة: <b>{values['favorites']}</b>\n"
        f"🌟 التقييمات: <b>{values['ratings']}</b>\n"
        f"💬 المراسلات: <b>{values['messages']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


# ============================================================
# BROADCAST / NOTIFICATIONS
# ============================================================

async def admin_broadcast_start(update, context):
    context.user_data["state"] = "ADMIN_BROADCAST"
    await update.effective_message.reply_text(
        "📣 أرسل الرسالة الآن.\n\n"
        "تقدر ترسل نص أو صورة أو فيديو أو ملف.\n"
        "قبل التنفيذ سيظهر لك تأكيد.",
        reply_markup=cancel_keyboard(),
    )


async def broadcast_preview(update, context):
    context.user_data["broadcast_chat_id"] = update.effective_chat.id
    context.user_data["broadcast_message_id"] = update.effective_message.message_id
    context.user_data["state"] = "ADMIN_BROADCAST_CONFIRM"

    await update.effective_message.reply_text(
        "👁 تمت المعاينة.\n\n"
        "⚠️ هل تريد إرسال هذه الرسالة إلى المستخدمين؟",
        reply_markup=reply_kb([
            ["✅ تأكيد الإرسال", "❌ إلغاء"],
        ]),
    )


async def execute_broadcast(update, context):
    conn = db()
    users = conn.execute(
        "SELECT user_id FROM users WHERE banned=0"
    ).fetchall()
    conn.close()

    chat_id = context.user_data.get("broadcast_chat_id")
    message_id = context.user_data.get("broadcast_message_id")

    ok = fail = 0
    for row in users:
        try:
            await telegram_app.bot.copy_message(
                chat_id=row["user_id"],
                from_chat_id=chat_id,
                message_id=message_id,
            )
            ok += 1
        except Exception:
            fail += 1

    context.user_data.clear()
    await update.effective_message.reply_text(
        f"📣 <b>اكتملت الرسالة الجماعية</b>\n\n"
        f"✅ تم الإرسال: {ok}\n"
        f"❌ تعذر الإرسال: {fail}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def send_new_content_notifications(button_id, content_title):
    conn = db()
    users = conn.execute(
        "SELECT user_id FROM users WHERE banned=0 AND notifications=1"
    ).fetchall()
    conn.close()

    button = get_button(button_id)
    if not button:
        return

    for row in users:
        try:
            await telegram_app.bot.send_message(
                row["user_id"],
                f"🔔 <b>محتوى جديد</b>\n\n"
                f"📚 {html.escape(button['title'])}\n"
                f"📄 {html.escape(content_title)}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# ============================================================
# ADMIN BUTTON OPERATIONS
# ============================================================

async def add_button_start(update, context):
    context.user_data["state"] = "ADD_BUTTON_TITLE"
    await update.effective_message.reply_text(
        "➕ أرسل اسم الزر الجديد:",
        reply_markup=cancel_keyboard(),
    )


async def edit_button_start(update, context):
    context.user_data["state"] = "EDIT_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "✏️ اختر الزر الذي تريد تعديله:",
        reply_markup=admin_button_selector(),
    )


async def delete_button_start(update, context):
    context.user_data["state"] = "DELETE_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "🗑 اختر الزر الذي تريد حذفه:",
        reply_markup=admin_button_selector(),
    )


async def move_button_start(update, context):
    context.user_data["state"] = "MOVE_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "🔄 اختر الزر الذي تريد نقله:",
        reply_markup=admin_button_selector(),
    )


async def handle_admin_text(update, context, state, text):
    if state == "ADMIN_SETTINGS":
        mapping = {
            "✏️ اسم البوت": "bot_name",
            "🏠 اسم الرئيسية": "home_title",
            "📝 نص الرئيسية": "home_text",
            "ℹ️ نص حول البوت": "about_text",
            "🛠 نص الصيانة": "maintenance_text",
            "🔔 نص الإشعارات": "notifications_text",
            "📢 نص الإعلان": "announcement_text",
        }
        if text in mapping:
            context.user_data["state"] = "SETTING_VALUE"
            context.user_data["setting_key"] = mapping[text]
            await update.effective_message.reply_text(
                "✍️ أرسل القيمة الجديدة:",
                reply_markup=cancel_keyboard(),
            )
            return True

    if state == "SETTING_VALUE":
        key = context.user_data.get("setting_key")
        if key:
            set_setting(key, text)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "✅ تم حفظ الإعداد بنجاح.",
            reply_markup=admin_keyboard(),
        )
        return True

    if state == "ADD_BUTTON_TITLE":
        context.user_data["new_button_title"] = text
        context.user_data["state"] = "ADD_BUTTON_PARENT"
        await update.effective_message.reply_text(
            "📁 أين تريد وضع الزر؟\n\n"
            "أرسل ID الزر الأب، أو اكتب 0 ليكون في الرئيسية.",
            reply_markup=cancel_keyboard(),
        )
        return True

    if state == "ADD_BUTTON_PARENT":
        try:
            parent_id = None if text == "0" else int(text)
            if parent_id is not None and not get_button(parent_id):
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                "❌ ID غير صحيح. أرسل رقم زر موجود أو 0."
            )
            return True

        bid = add_button(
            context.user_data.get("new_button_title", "🔘 زر جديد"),
            parent_id,
            "menu",
            "",
        )
        context.user_data.clear()

        await update.effective_message.reply_text(
            f"✅ تم إنشاء الزر.\n🆔 ID: <code>{bid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return True

    if state == "EDIT_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("❌ اختر زرًا صحيحًا.")
            return True
        context.user_data["edit_button_id"] = bid
        context.user_data["state"] = "EDIT_BUTTON_MENU"
        await update.effective_message.reply_text(
            "✏️ ماذا تريد تعديل؟",
            reply_markup=reply_kb([
                ["📝 الاسم", "🔗 الرابط"],
                ["🎯 نوع الإجراء"],
                ["🔘 تفعيل/تعطيل"],
                ["⬅️ رجوع"],
            ]),
        )
        return True

    if state == "EDIT_BUTTON_MENU":
        bid = context.user_data["edit_button_id"]
        if text == "📝 الاسم":
            context.user_data["state"] = "EDIT_BUTTON_NAME"
            await update.effective_message.reply_text(
                "✍️ أرسل الاسم الجديد:", reply_markup=cancel_keyboard()
            )
            return True
        if text == "🔗 الرابط":
            context.user_data["state"] = "EDIT_BUTTON_URL"
            await update.effective_message.reply_text(
                "🔗 أرسل الرابط:", reply_markup=cancel_keyboard()
            )
            return True
        if text == "🎯 نوع الإجراء":
            context.user_data["state"] = "EDIT_BUTTON_ACTION"
            await update.effective_message.reply_text(
                "اختر النوع:",
                reply_markup=reply_kb([
                    ["📂 قائمة", "📄 محتوى"],
                    ["🔎 بحث", "⭐ مفضلة"],
                    ["🔔 إشعارات", "⭐ تقييم"],
                    ["💬 مراسلة", "ℹ️ حول"],
                    ["🔗 رابط"],
                    ["❌ إلغاء"],
                ]),
            )
            return True
        if text == "🔘 تفعيل/تعطيل":
            b = get_button(bid)
            update_button(bid, enabled=0 if b["enabled"] else 1)
            context.user_data.clear()
            await update.effective_message.reply_text(
                "✅ تم تغيير حالة الزر.",
                reply_markup=admin_keyboard(),
            )
            return True

    if state == "EDIT_BUTTON_NAME":
        update_button(context.user_data["edit_button_id"], title=text)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "✅ تم تعديل اسم الزر.", reply_markup=admin_keyboard()
        )
        return True

    if state == "EDIT_BUTTON_URL":
        update_button(
            context.user_data["edit_button_id"],
            action_type="url",
            action_value=text,
        )
        context.user_data.clear()
        await update.effective_message.reply_text(
            "✅ تم حفظ الرابط.", reply_markup=admin_keyboard()
        )
        return True

    if state == "EDIT_BUTTON_ACTION":
        mapping = {
            "📂 قائمة": ("menu", ""),
            "📄 محتوى": ("content", ""),
            "🔎 بحث": ("search", ""),
            "⭐ مفضلة": ("favorites", ""),
            "🔔 إشعارات": ("notifications", ""),
            "⭐ تقييم": ("rating", ""),
            "💬 مراسلة": ("contact", ""),
            "ℹ️ حول": ("about", ""),
            "🔗 رابط": ("url", ""),
        }
        if text in mapping:
            action, value = mapping[text]
            update_button(
                context.user_data["edit_button_id"],
                action_type=action,
                action_value=value,
            )
            context.user_data.clear()
            await update.effective_message.reply_text(
                "✅ تم تعديل وظيفة الزر.",
                reply_markup=admin_keyboard(),
            )
            return True

    if state == "DELETE_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("❌ اختر زرًا صحيحًا.")
            return True

        context.user_data["delete_button_id"] = bid
        context.user_data["state"] = "DELETE_CONFIRM"
        await update.effective_message.reply_text(
            f"⚠️ <b>تأكيد الحذف</b>\n\n"
            f"سيتم حذف الزر وكل الأزرار الموجودة تحته.\n\n"
            f"هل أنت متأكد؟",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb([
                ["✅ تأكيد الحذف", "❌ إلغاء"],
            ]),
        )
        return True

    if state == "DELETE_CONFIRM":
        if text == "✅ تأكيد الحذف":
            delete_button_tree(context.user_data["delete_button_id"])
            context.user_data.clear()
            await update.effective_message.reply_text(
                "🗑 تم الحذف بنجاح.",
                reply_markup=admin_keyboard(),
            )
            return True

    if state == "MOVE_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("❌ اختر زرًا صحيحًا.")
            return True
        context.user_data["move_button_id"] = bid
        context.user_data["state"] = "MOVE_BUTTON_PARENT"
        await update.effective_message.reply_text(
            "🔄 أرسل ID الزر الأب الجديد، أو 0 للرئيسية:",
            reply_markup=cancel_keyboard(),
        )
        return True

    if state == "MOVE_BUTTON_PARENT":
        bid = context.user_data["move_button_id"]
        try:
            parent = None if text == "0" else int(text)
            if parent is not None and not get_button(parent):
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("❌ ID غير صحيح.")
            return True

        context.user_data["state"] = "MOVE_CONFIRM"
        context.user_data["move_parent"] = parent
        await update.effective_message.reply_text(
            "⚠️ تأكيد النقل؟",
            reply_markup=reply_kb([
                ["✅ تأكيد النقل", "❌ إلغاء"],
            ]),
        )
        return True

    if state == "MOVE_CONFIRM":
        if text == "✅ تأكيد النقل":
            ok = move_button(
                context.user_data["move_button_id"],
                context.user_data["move_parent"],
            )
            context.user_data.clear()
            await update.effective_message.reply_text(
                "✅ تم النقل بنجاح." if ok else "❌ تعذر النقل.",
                reply_markup=admin_keyboard(),
            )
            return True

    if state == "ADD_CONTENT_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("❌ اختر زرًا صحيحًا.")
            return True
        context.user_data["content_button_id"] = bid
        context.user_data["state"] = "ADD_CONTENT_WAIT"
        await update.effective_message.reply_text(
            "📨 أرسل المحتوى الآن.\n\n"
            "سيتم حفظ الرسالة الحالية كما هي.",
            reply_markup=cancel_keyboard(),
        )
        return True

    if state == "DELETE_CONTENT_SELECT":
        if not text.startswith("📄") or "〔C" not in text:
            await update.effective_message.reply_text("❌ اختر محتوى صحيحًا.")
            return True
        try:
            cid = int(text.split("〔C", 1)[1].split("〕", 1)[0])
        except ValueError:
            await update.effective_message.reply_text("❌ ID غير صحيح.")
            return True

        context.user_data["delete_content_id"] = cid
        context.user_data["state"] = "DELETE_CONTENT_CONFIRM"
        await update.effective_message.reply_text(
            "⚠️ تأكيد حذف المحتوى؟",
            reply_markup=reply_kb([
                ["✅ تأكيد الحذف", "❌ إلغاء"],
            ]),
        )
        return True

    if state == "DELETE_CONTENT_CONFIRM":
        if text == "✅ تأكيد الحذف":
            delete_content(context.user_data["delete_content_id"])
            context.user_data.clear()
            await update.effective_message.reply_text(
                "🗑 تم حذف المحتوى.",
                reply_markup=admin_keyboard(),
            )
            return True

    return False


# ============================================================
# ADMIN MEDIA / USER MEDIA ROUTER
# ============================================================

async def route_media(update, context):
    if update.message and update.message.text is not None:
        await handle_text(update, context)
        return

    user = update.effective_user
    if not user:
        return

    save_user(user)

    if is_banned(user.id) and user.id != ADMIN_ID:
        return

    state = context.user_data.get("state")

    if user.id == ADMIN_ID and state == "ADD_CONTENT_WAIT":
        bid = context.user_data.get("content_button_id")
        if not bid:
            context.user_data.clear()
            return

        cid = add_content(bid, update.effective_message)
        c = get_content(cid)
        title = c["title"] if c else "محتوى جديد"

        context.user_data.clear()
        await update.effective_message.reply_text(
            f"👁 <b>معاينة المحتوى</b>\n\n"
            f"📚 الزر: {html.escape(get_button(bid)['title'])}\n"
            f"📄 {html.escape(title)}\n\n"
            f"⚠️ تم الحفظ والنشر.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )

        await send_new_content_notifications(bid, title)
        return

    if state == "USER_CONTACT":
        mid = add_user_message(update)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "✅ وصلت رسالتك إلى الإدارة ❤️",
            reply_markup=home_keyboard(),
        )
        try:
            await telegram_app.bot.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
            )
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"💬 رسالة جديدة من المستخدم\n🆔 <code>{user.id}</code>\nرقم: {mid}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return


def add_user_message(update):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages
        (user_id,text,source_chat_id,source_message_id,created_at)
        VALUES(?,?,?,?,?)
    """, (
        update.effective_user.id,
        update.effective_message.text or "",
        update.effective_chat.id,
        update.effective_message.message_id,
        now(),
    ))
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


# ============================================================
# MAIN TEXT ROUTER
# ============================================================

async def handle_text(update, context):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    text = (update.message.text or "").strip()
    save_user(user)

    if is_banned(user.id) and user.id != ADMIN_ID:
        await update.message.reply_text("🚫 لا يمكنك استخدام البوت.")
        return

    if user.id == ADMIN_ID:
        if text == "/admin":
            await show_admin(update)
            return

        if text == "⚙️ إعدادات البوت":
            await admin_settings(update, context); return
        if text == "🎛 محرر الأزرار":
            await admin_buttons(update, context); return
        if text == "📝 محرر المحتوى":
            await admin_content(update, context); return
        if text == "📣 رسالة جماعية":
            await admin_broadcast_start(update, context); return
        if text == "👁 المعاينة":
            await admin_preview(update, context); return
        if text == "📊 الإحصائيات":
            await admin_stats(update, context); return
        if text == "🛠 الصيانة":
            current = get_setting("maintenance") == "1"
            set_setting("maintenance", "0" if current else "1")
            await update.message.reply_text(
                f"🛠 الصيانة الآن: {'🟢 متوقفة' if current else '🔴 مفعلة'}",
                reply_markup=admin_keyboard(),
            )
            return
        if text == "🏠 واجهة المستخدم":
            await show_home(update); return

        if text == "➕ إضافة زر":
            await add_button_start(update, context); return
        if text == "✏️ تعديل زر":
            await edit_button_start(update, context); return
        if text == "🗑 حذف زر":
            await delete_button_start(update, context); return
        if text == "🔄 نقل زر":
            await move_button_start(update, context); return
        if text == "📋 عرض الأزرار":
            rows = []
            for b in all_buttons():
                rows.append(
                    f"🔘 <code>{b['id']}</code> — {html.escape(b['title'])} "
                    f"— {b['action_type']} — {'🟢' if b['enabled'] else '🔴'}"
                )
            await update.message.reply_text(
                "📋 <b>الأزرار</b>\n\n" + ("\n".join(rows) or "لا توجد."),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(),
            )
            return

        if text == "➕ إضافة محتوى":
            context.user_data["state"] = "ADD_CONTENT_SELECT"
            await update.message.reply_text(
                "📚 اختر الزر الذي سيحتوي على المحتوى:",
                reply_markup=admin_button_selector(),
            )
            return

        if text == "🗑 حذف محتوى":
            contents = []
            for b in all_buttons():
                for c in get_contents(b["id"], False):
                    contents.append([KeyboardButton(
                        f"📄 {c['title'][:50]} 〔C{c['id']}〕"
                    )])
            contents.append([KeyboardButton("❌ إلغاء")])
            context.user_data["state"] = "DELETE_CONTENT_SELECT"
            await update.message.reply_text(
                "🗑 اختر المحتوى:",
                reply_markup=reply_kb(contents),
            )
            return

        if text == "👥 المستخدمون":
            conn = db()
            rows = conn.execute("""
                SELECT user_id,first_name,username,banned,notifications
                FROM users ORDER BY last_seen DESC LIMIT 30
            """).fetchall()
            conn.close()
            lines = ["👥 <b>المستخدمون</b>\n"]
            for r in rows:
                lines.append(
                    f"{'🚫' if r['banned'] else '🟢'} "
                    f"<code>{r['user_id']}</code> "
                    f"{html.escape(r['first_name'] or '-')}"
                )
            await update.message.reply_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(),
            )
            return

        if text == "📢 الإعلان":
            context.user_data["state"] = "ADMIN_ANNOUNCEMENT"
            await update.message.reply_text(
                "📢 أرسل الإعلان. ستظهر لك المعاينة قبل النشر.",
                reply_markup=cancel_keyboard(),
            )
            return

        state = context.user_data.get("state")
        if state == "ADMIN_BROADCAST":
            await broadcast_preview(update, context); return
        if state == "ADMIN_BROADCAST_CONFIRM":
            if text == "✅ تأكيد الإرسال":
                await execute_broadcast(update, context)
            elif text == "❌ إلغاء":
                context.user_data.clear()
                await show_admin(update)
            return

        if state == "ADMIN_ANNOUNCEMENT":
            context.user_data["state"] = "ADMIN_BROADCAST_CONFIRM"
            context.user_data["broadcast_chat_id"] = update.effective_chat.id
            context.user_data["broadcast_message_id"] = update.message.message_id
            await update.message.reply_text(
                "👁 معاينة الإعلان جاهزة.\n\n⚠️ تأكيد النشر؟",
                reply_markup=reply_kb([
                    ["✅ تأكيد الإرسال", "❌ إلغاء"]
                ]),
            )
            return

        if state and await handle_admin_text(update, context, state, text):
            return

        if text == "⬅️ رجوع" or text == "❌ إلغاء":
            context.user_data.clear()
            await show_admin(update)
            return

    if get_setting("maintenance") == "1":
        await update.message.reply_text(
            get_setting("maintenance_text"),
            reply_markup=reply_kb([["🔄 تحديث"]]),
        )
        return

    state = context.user_data.get("state")

    if state == "USER_SEARCH":
        query = text
        conn = db()
        rows = conn.execute("""
            SELECT DISTINCT b.id,b.title
            FROM buttons b
            LEFT JOIN contents c ON c.button_id=b.id
            WHERE b.enabled=1
            AND (b.title LIKE ? OR c.title LIKE ?)
            ORDER BY b.position,b.id
            LIMIT 30
        """, (f"%{query}%", f"%{query}%")).fetchall()
        conn.close()

        context.user_data.clear()
        if not rows:
            await update.message.reply_text(
                "🔎 لم أجد نتائج.",
                reply_markup=home_keyboard(),
            )
            return

        await update.message.reply_text(
            "🔎 <b>نتائج البحث</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb(
                [[KeyboardButton(r["title"])] for r in rows] +
                [["🏠 الرئيسية"]]
            ),
        )
        return

    if state == "USER_CONTACT":
        mid = add_user_message(update)
        context.user_data.clear()
        try:
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"💬 <b>رسالة جديدة #{mid}</b>\n"
                f"👤 {html.escape(user.full_name)}\n"
                f"🆔 <code>{user.id}</code>\n\n"
                f"{html.escape(text)}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        await update.message.reply_text(
            "✅ وصلت رسالتك للإدارة.",
            reply_markup=home_keyboard(),
        )
        return

    if state == "USER_RATING":
        if text.startswith("⭐"):
            rating = min(5, text.count("⭐"))
            context.user_data["rating"] = rating
            context.user_data["state"] = "USER_RATING_COMMENT"
            await update.message.reply_text(
                "✍️ اكتب ملاحظتك أو اكتب «بدون ملاحظة»:",
                reply_markup=cancel_keyboard(),
            )
        return

    if state == "USER_RATING_COMMENT":
        rating = context.user_data.get("rating", 5)
        comment = "" if text == "بدون ملاحظة" else text
        conn = db()
        conn.execute("""
            INSERT INTO ratings(user_id,rating,comment,created_at)
            VALUES(?,?,?,?)
        """, (user.id, rating, comment, now()))
        conn.commit()
        conn.close()
        context.user_data.clear()
        await update.message.reply_text(
            "❤️ شكراً على تقييمك!",
            reply_markup=home_keyboard(),
        )
        return

    if text in ("🏠 الرئيسية", "🏠 القائمة الرئيسية", "/start"):
        context.user_data.clear()
        await show_home(update)
        return

    if text == "🔄 تحديث":
        await show_home(update)
        return

    if text == "🔔 تفعيل الإشعارات":
        set_notifications(user.id, True)
        await update.message.reply_text(
            "🔔 تم تفعيل الإشعارات. ستصلك تحديثات المحتوى الجديد.",
            reply_markup=home_keyboard(),
        )
        return

    if text == "🔕 إيقاف الإشعارات":
        set_notifications(user.id, False)
        await update.message.reply_text(
            "🔕 تم إيقاف الإشعارات.",
            reply_markup=home_keyboard(),
        )
        return

    if text in ("⭐ إضافة للمفضلة", "💔 إزالة من المفضلة"):
        state_button = context.user_data.get("last_button_id")
        if state_button:
            added = toggle_favorite(user.id, state_button)
            await update.message.reply_text(
                "⭐ تمت الإضافة للمفضلة." if added else "💔 تمت الإزالة من المفضلة.",
                reply_markup=home_keyboard(),
            )
        else:
            await show_favorites(update)
        return

    if "〔C" in text and text.startswith("📄"):
        try:
            cid = int(text.split("〔C", 1)[1].split("〕", 1)[0])
            c = get_content(cid)
            if c:
                context.user_data["last_button_id"] = c["button_id"]
                await telegram_app.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=c["source_chat_id"],
                    message_id=c["source_message_id"],
                )
                await section_actions(update, c["button_id"])
                return
        except Exception:
            pass

    conn = db()
    row = conn.execute("""
        SELECT id FROM buttons
        WHERE title=? AND enabled=1
        ORDER BY id DESC LIMIT 1
    """, (text,)).fetchone()
    conn.close()

    if row:
        context.user_data["last_button_id"] = row["id"]
        await show_button(update, row["id"])
        return

    await update.message.reply_text(
        "🤔 ما فهمت اختيارك.\n\nجرّب أحد الأزرار الظاهرة.",
        reply_markup=home_keyboard(),
    )


# ============================================================
# START / WEBHOOK
# ============================================================

async def start(update, context):
    save_user(update.effective_user)

    if is_banned(update.effective_user.id) and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 تم حظرك من استخدام البوت.")
        return

    if update.effective_user.id != ADMIN_ID:
        if get_setting("maintenance") == "1":
            await update.message.reply_text(get_setting("maintenance_text"))
            return

    await show_home(update)


@app.get("/")
def health():
    return "Telegram bot is running", 200


@app.post(f"/{WEBHOOK_PATH}")
def webhook():
    global telegram_app
    if telegram_app is None:
        return "Application not ready", 503

    try:
        update = Update.de_json(
            request.get_json(force=True),
            telegram_app.bot,
        )
        telegram_app.update_queue.put_nowait(update)
        return "OK", 200
    except Exception:
        logger.exception("Webhook error")
        return "Bad Request", 400


async def post_init(application):
    global telegram_app
    telegram_app = application


def build_application():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود. أضفه في Environment Variables على Render."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", show_admin))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, route_media)
    )
    return application


def telegram_worker(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def start_bot():
        global telegram_app
        await application.initialize()
        telegram_app = application
        await application.start()

        if WEBHOOK_URL:
            url = WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH
            await application.bot.set_webhook(
                url=url,
                drop_pending_updates=False,
                allowed_updates=Update.ALL_TYPES,
            )
            logger.info("Webhook configured: %s", url)
        else:
            await application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
            )
            logger.info("Polling started successfully.")

    try:
        loop.run_until_complete(start_bot())
        loop.run_forever()
    except Exception:
        logger.exception("Telegram worker stopped.")
    finally:
        async def stop_bot():
            try:
                if application.updater and application.updater.running:
                    await application.updater.stop()
            except Exception:
                logger.exception("Failed to stop updater.")

            try:
                if application.running:
                    await application.stop()
            except Exception:
                logger.exception("Failed to stop application.")

            try:
                await application.shutdown()
            except Exception:
                logger.exception("Failed to shutdown application.")

        try:
            loop.run_until_complete(stop_bot())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def run():
    init_db()
    repair_database_text()
    application = build_application()

    t = threading.Thread(
        target=telegram_worker,
        args=(application,),
        name="TelegramWorker",
        daemon=True,
    )
    t.start()

    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True,
        use_reloader=False,
    )

if __name__ == "__main__":
    run()
