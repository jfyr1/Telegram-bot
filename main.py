# -*- coding: utf-8 -*-
"""
Telegram Universal MenuBuilder-style Bot
Python 3.11+
python-telegram-bot 21.x
Flask webhook / Render or polling-friendly local mode
SQLite

IMPORTANT:
- Put BOT_TOKEN and ADMIN_ID in Environment Variables.
- Optional REQUIRED_CHANNEL = @channel_username
- Optional REQUIRED_CHANNEL_URL = https://t.me/channel_username
- Never put your BotFather token directly in this file.
"""

import os
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ÙØ¹Ø±Ù Ø§ÙØ£Ø¯ÙÙ Ø§ÙØ£Ø³Ø§Ø³Ù
# ÙÙÙÙ ØªØºÙÙØ±Ù ÙÙ Render Ø¹Ø¨Ø± ADMIN_IDØ ÙØ¥Ø°Ø§ ÙÙ ÙÙÙ ÙÙØ¬ÙØ¯Ø§Ù
# Ø³ÙØ³ØªØ®Ø¯Ù ÙØ°Ø§ Ø§ÙÙØ¹Ø±Ù ØªÙÙØ§Ø¦ÙØ§Ù.
ADMIN_ID = 5734654153
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", str(ADMIN_ID)) or ADMIN_ID)
except (TypeError, ValueError):
    ADMIN_ID = 5734654153

PORT = int(os.getenv("PORT", "10000") or 10000)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")

DB_FILE = os.getenv("DB_FILE", "bot.db")

# Example: @my_channel
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
# Example: https://t.me/my_channel
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("universal-menu-bot")

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
        "bot_name": "ð¤ Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØ°ÙÙ",
        "home_title": "ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©",
        "home_text": "ð Ø£ÙÙØ§Ù Ø¨Ù!\n\nâ¨ Ø§Ø®ØªØ± ÙÙ Ø§ÙÙØ§Ø¦ÙØ© Ø£Ø¯ÙØ§Ù:",
        "about_text": "â¹ï¸ <b>Ø­ÙÙ Ø§ÙØ¨ÙØª</b>\n\nØ¨ÙØª Ø¹Ø§Ù ÙØ§Ø¨Ù ÙÙØªØ®ØµÙØµ Ø¨Ø§ÙÙØ§ÙÙ ÙÙ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©.",
        "maintenance": "0",
        "maintenance_text": "ð  Ø§ÙØ¨ÙØª Ø­Ø§ÙÙØ§Ù ØªØ­Øª Ø§ÙØµÙØ§ÙØ©.\n\nâ³ Ø­Ø§ÙÙ ÙØ§Ø­ÙØ§Ù.",
        "subscription_text": "ð ÙÙÙØµÙÙ Ø¥ÙÙ Ø§ÙØ¨ÙØªØ ÙØ±Ø¬Ù Ø§ÙØ§Ø´ØªØ±Ø§Ù Ø¨Ø§ÙÙÙØ§Ø© Ø£ÙÙØ§Ù Ø«Ù Ø§ÙØ¶ØºØ· Ø¹ÙÙ Ø²Ø± Ø§ÙØªØ­ÙÙ.",
        "notifications_text": "ð ÙÙ ØªØ±ÙØ¯ Ø§Ø³ØªÙØ¨Ø§Ù Ø¥Ø´Ø¹Ø§Ø±Ø§Øª Ø¹ÙØ¯ Ø¥Ø¶Ø§ÙØ© ÙØ­ØªÙÙ Ø¬Ø¯ÙØ¯Ø",
        "announcement_text": "ð¢ Ø¥Ø¹ÙØ§Ù Ø¬Ø¯ÙØ¯",
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, value),
        )

    # Default root buttons. Admin can rename/delete/reorder them.
    root_count = cur.execute(
        "SELECT COUNT(*) AS c FROM buttons WHERE parent_id IS NULL"
    ).fetchone()["c"]

    if root_count == 0:
        roots = [
            ("ð Ø§ÙØ£ÙØ³Ø§Ù", "menu"),
            ("â­ Ø§ÙÙÙØ¶ÙØ©", "favorites"),
            ("ð Ø§ÙØ¨Ø­Ø«", "search"),
            ("ð Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª", "notifications"),
            ("â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª", "rating"),
            ("ð¬ ÙØ±Ø§Ø³ÙØ© Ø§ÙØ¥Ø¯Ø§Ø±Ø©", "contact"),
            ("â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª", "about"),
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
        return text[:80] or "ÙØ­ØªÙÙ ÙØµÙ"
    return {
        "document": "ð ÙÙÙ",
        "photo": "ð¼ ØµÙØ±Ø©",
        "video": "ð¥ ÙÙØ¯ÙÙ",
        "audio": "ðµ ØµÙØª",
        "voice": "ð Ø±Ø³Ø§ÙØ© ØµÙØªÙØ©",
        "animation": "ð GIF",
    }.get(ctype, "ð¦ ÙØ­ØªÙÙ")


# ============================================================
# SUBSCRIPTION
# ============================================================

async def subscription_required(user_id):
    if not REQUIRED_CHANNEL:
        return False
    try:
        member = await telegram_app.bot.get_chat_member(
            REQUIRED_CHANNEL, user_id
        )
        return member.status in ("creator", "administrator", "member")
    except Exception as exc:
        logger.warning("Subscription check failed: %s", exc)
        # Fail closed for configured mandatory channel.
        return True


async def send_subscription_gate(update):
    buttons = []
    if REQUIRED_CHANNEL_URL:
        buttons.append([
            InlineKeyboardButton(
                "ð¢ Ø§ÙØ§Ø´ØªØ±Ø§Ù Ø¨Ø§ÙÙÙØ§Ø©",
                url=REQUIRED_CHANNEL_URL
            )
        ])
    buttons.append([
        InlineKeyboardButton("â ØªØ­ÙÙ ÙÙ Ø§ÙØ§Ø´ØªØ±Ø§Ù", callback_data="SUB:CHECK")
    ])
    await update.effective_message.reply_text(
        get_setting("subscription_text"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


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
        ["âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª", "ð ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±"],
        ["ð ÙØ­Ø±Ø± Ø§ÙÙØ­ØªÙÙ", "ð¢ Ø§ÙØ¥Ø¹ÙØ§Ù"],
        ["ð£ Ø±Ø³Ø§ÙØ© Ø¬ÙØ§Ø¹ÙØ©", "ð Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª"],
        ["ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª", "â­ Ø§ÙØªÙÙÙÙØ§Øª"],
        ["ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ", "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª"],
        ["ð  Ø§ÙØµÙØ§ÙØ©", "ð Ø§ÙÙØ¹Ø§ÙÙØ©"],
        ["ð  ÙØ§Ø¬ÙØ© Ø§ÙÙØ³ØªØ®Ø¯Ù"],
    ])


def cancel_keyboard():
    return reply_kb([["â Ø¥ÙØºØ§Ø¡"]])


def admin_button_selector(prefix="BTN"):
    rows = []
    for b in all_buttons():
        rows.append([
            KeyboardButton(f"{b['title']} ã{b['id']}ã")
        ])
    rows.append([KeyboardButton("ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©")])
    rows.append([KeyboardButton("â Ø¥ÙØºØ§Ø¡")])
    return reply_kb(rows)


def parse_id_from_button_text(text):
    if "ã" not in text or "ã" not in text:
        return None
    try:
        return int(text.rsplit("ã", 1)[1].split("ã", 1)[0])
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
        await update.effective_message.reply_text("â ÙØ°Ø§ Ø§ÙØ²Ø± ØºÙØ± ÙØªØ§Ø­.")
        return

    user_id = update.effective_user.id

    if await subscription_required(user_id):
        await send_subscription_gate(update)
        return

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
            "ð Ø£Ø±Ø³Ù ÙÙÙØ© Ø§ÙØ¨Ø­Ø«:",
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
            "ð¬ Ø£Ø±Ø³Ù Ø±Ø³Ø§ÙØªÙ ÙÙØ¥Ø¯Ø§Ø±Ø©:",
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
            f"ð {html.escape(button['action_value'])}",
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

    # Default menu action.
    children = get_buttons(button_id)
    contents = get_contents(button_id)

    rows = [[KeyboardButton(child["title"])] for child in children]

    for c in contents:
        rows.append([
            KeyboardButton(f"ð {c['title'][:60]} ãC{c['id']}ã")
        ])

    fav = is_favorite(user_id, button_id)
    rows.append([
        KeyboardButton("ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©" if fav else "â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©")
    ])
    rows.append([KeyboardButton("â¬ï¸ Ø±Ø¬ÙØ¹"), KeyboardButton("ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©")])

    await update.effective_message.reply_text(
        f"ð <b>{html.escape(button['title'])}</b>\n\nØ§Ø®ØªØ±:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb(rows),
    )


async def section_actions(update, button_id):
    fav = is_favorite(update.effective_user.id, button_id)
    await update.effective_message.reply_text(
        "â¨ ÙØ§Ø°Ø§ ØªØ±ÙØ¯ Ø£Ù ØªÙØ¹ÙØ",
        reply_markup=reply_kb([
            ["ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©" if fav else "â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©"],
            ["â­ ØªÙÙÙÙ Ø§ÙÙØ­ØªÙÙ"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹", "ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
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
            "â­ ÙØ§ ØªÙØ¬Ø¯ Ø¹ÙØ§ØµØ± ÙÙ Ø§ÙÙÙØ¶ÙØ© Ø¨Ø¹Ø¯.",
            reply_markup=home_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        "â­ <b>Ø§ÙÙÙØ¶ÙØ©</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb(
            [[KeyboardButton(r["title"])] for r in rows] +
            [["ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]
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
            ["ð Ø¥ÙÙØ§Ù Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª" if enabled else "ð ØªÙØ¹ÙÙ Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª"],
            ["ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
        ]),
    )


async def start_rating(update):
    update._context.user_data["state"] = "USER_RATING"
    await update.effective_message.reply_text(
        "â­ Ø§Ø®ØªØ± ØªÙÙÙÙÙ ÙÙ 1 Ø¥ÙÙ 5:",
        reply_markup=reply_kb([
            ["â­ 1", "â­â­ 2"],
            ["â­â­â­ 3"],
            ["â­â­â­â­ 4", "â­â­â­â­â­ 5"],
            ["â Ø¥ÙØºØ§Ø¡"],
        ]),
    )


# ============================================================
# ADMIN PANEL
# ============================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            await update.effective_message.reply_text("â ØºÙØ± ÙØ³ÙÙØ­.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def show_admin(update):
    await update.effective_message.reply_text(
        "ð <b>ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n\n"
        "ð ÙÙ ÙÙØ§ ØªØªØ­ÙÙ Ø¨ÙÙ ÙØ§Ø¬ÙØ© Ø§ÙØ¨ÙØª ÙÙØ­ØªÙØ§Ù ÙØ¥Ø¹Ø¯Ø§Ø¯Ø§ØªÙ.",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_settings(update, context):
    context.user_data["state"] = "ADMIN_SETTINGS"
    await update.effective_message.reply_text(
        "âï¸ <b>Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª</b>\n\n"
        "Ø§Ø®ØªØ± ÙØ§ ØªØ±ÙØ¯ ØªØºÙÙØ±Ù:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["âï¸ Ø§Ø³Ù Ø§ÙØ¨ÙØª", "ð  Ø§Ø³Ù Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
            ["ð ÙØµ Ø§ÙØ±Ø¦ÙØ³ÙØ©", "â¹ï¸ ÙØµ Ø­ÙÙ Ø§ÙØ¨ÙØª"],
            ["ð ÙØµ Ø§ÙØ§Ø´ØªØ±Ø§Ù", "ð  ÙØµ Ø§ÙØµÙØ§ÙØ©"],
            ["ð ÙØµ Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª", "ð¢ ÙØµ Ø§ÙØ¥Ø¹ÙØ§Ù"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def admin_buttons(update, context):
    context.user_data["state"] = "ADMIN_BUTTONS"
    await update.effective_message.reply_text(
        "ð <b>ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±</b>\n\n"
        "Ø§ÙØ¥Ø¶Ø§ÙØ© ÙØ§ÙØªØ¹Ø¯ÙÙ ÙØ§ÙØ­Ø°Ù ÙØ§ÙÙÙÙ ÙÙÙØ§ ÙÙ ÙÙØ§.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["â Ø¥Ø¶Ø§ÙØ© Ø²Ø±", "âï¸ ØªØ¹Ø¯ÙÙ Ø²Ø±"],
            ["ð Ø­Ø°Ù Ø²Ø±", "ð ÙÙÙ Ø²Ø±"],
            ["ð Ø¹Ø±Ø¶ Ø§ÙØ£Ø²Ø±Ø§Ø±"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def admin_content(update, context):
    context.user_data["state"] = "ADMIN_CONTENT"
    await update.effective_message.reply_text(
        "ð <b>ÙØ­Ø±Ø± Ø§ÙÙØ­ØªÙÙ</b>\n\n"
        "Ø£Ø¶Ù Ø£Ù Ø±Ø³Ø§ÙØ©/ØµÙØ±Ø©/ÙÙØ¯ÙÙ/ÙÙÙ Ø¯Ø§Ø®Ù Ø£Ù Ø²Ø±.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb([
            ["â Ø¥Ø¶Ø§ÙØ© ÙØ­ØªÙÙ", "âï¸ ØªØ¹Ø¯ÙÙ ÙØ­ØªÙÙ"],
            ["ð Ø­Ø°Ù ÙØ­ØªÙÙ", "ð Ø¹Ø±Ø¶ Ø§ÙÙØ­ØªÙÙ"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def admin_preview(update, context):
    await update.effective_message.reply_text(
        "ð <b>ÙØ¸Ø§Ù Ø§ÙÙØ¹Ø§ÙÙØ©</b>\n\n"
        "Ø§ÙÙØ¹Ø§ÙÙØ© ØªØ¸ÙØ± ÙÙÙØ³ØªØ®Ø¯Ù Ø¨ÙÙØ³ Ø£Ø³ÙÙØ¨ Ø§ÙØ¹Ø±Ø¶ ÙØ¨Ù Ø§Ø¹ØªÙØ§Ø¯ Ø§ÙÙØ´Ø±.",
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
        "ð <b>Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª</b>\n\n"
        f"ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ: <b>{values['users']}</b>\n"
        f"ð Ø§ÙØ£Ø²Ø±Ø§Ø±: <b>{values['buttons']}</b>\n"
        f"ð Ø§ÙÙØ­ØªÙÙ: <b>{values['contents']}</b>\n"
        f"â­ Ø§ÙÙÙØ¶ÙØ©: <b>{values['favorites']}</b>\n"
        f"ð Ø§ÙØªÙÙÙÙØ§Øª: <b>{values['ratings']}</b>\n"
        f"ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª: <b>{values['messages']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


# ============================================================
# BROADCAST / NOTIFICATIONS
# ============================================================

async def admin_broadcast_start(update, context):
    context.user_data["state"] = "ADMIN_BROADCAST"
    await update.effective_message.reply_text(
        "ð£ Ø£Ø±Ø³Ù Ø§ÙØ±Ø³Ø§ÙØ© Ø§ÙØ¢Ù.\n\n"
        "ØªÙØ¯Ø± ØªØ±Ø³Ù ÙØµ Ø£Ù ØµÙØ±Ø© Ø£Ù ÙÙØ¯ÙÙ Ø£Ù ÙÙÙ.\n"
        "ÙØ¨Ù Ø§ÙØªÙÙÙØ° Ø³ÙØ¸ÙØ± ÙÙ ØªØ£ÙÙØ¯.",
        reply_markup=cancel_keyboard(),
    )


async def broadcast_preview(update, context):
    context.user_data["broadcast_chat_id"] = update.effective_chat.id
    context.user_data["broadcast_message_id"] = update.effective_message.message_id
    context.user_data["state"] = "ADMIN_BROADCAST_CONFIRM"

    await update.effective_message.reply_text(
        "ð ØªÙØª Ø§ÙÙØ¹Ø§ÙÙØ©.\n\n"
        "â ï¸ ÙÙ ØªØ±ÙØ¯ Ø¥Ø±Ø³Ø§Ù ÙØ°Ù Ø§ÙØ±Ø³Ø§ÙØ© Ø¥ÙÙ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙØ",
        reply_markup=reply_kb([
            ["â ØªØ£ÙÙØ¯ Ø§ÙØ¥Ø±Ø³Ø§Ù", "â Ø¥ÙØºØ§Ø¡"],
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
        f"ð£ <b>Ø§ÙØªÙÙØª Ø§ÙØ±Ø³Ø§ÙØ© Ø§ÙØ¬ÙØ§Ø¹ÙØ©</b>\n\n"
        f"â ØªÙ Ø§ÙØ¥Ø±Ø³Ø§Ù: {ok}\n"
        f"â ØªØ¹Ø°Ø± Ø§ÙØ¥Ø±Ø³Ø§Ù: {fail}",
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
                f"ð <b>ÙØ­ØªÙÙ Ø¬Ø¯ÙØ¯</b>\n\n"
                f"ð {html.escape(button['title'])}\n"
                f"ð {html.escape(content_title)}",
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
        "â Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙØ²Ø± Ø§ÙØ¬Ø¯ÙØ¯:",
        reply_markup=cancel_keyboard(),
    )


async def edit_button_start(update, context):
    context.user_data["state"] = "EDIT_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "âï¸ Ø§Ø®ØªØ± Ø§ÙØ²Ø± Ø§ÙØ°Ù ØªØ±ÙØ¯ ØªØ¹Ø¯ÙÙÙ:",
        reply_markup=admin_button_selector(),
    )


async def delete_button_start(update, context):
    context.user_data["state"] = "DELETE_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "ð Ø§Ø®ØªØ± Ø§ÙØ²Ø± Ø§ÙØ°Ù ØªØ±ÙØ¯ Ø­Ø°ÙÙ:",
        reply_markup=admin_button_selector(),
    )


async def move_button_start(update, context):
    context.user_data["state"] = "MOVE_BUTTON_SELECT"
    await update.effective_message.reply_text(
        "ð Ø§Ø®ØªØ± Ø§ÙØ²Ø± Ø§ÙØ°Ù ØªØ±ÙØ¯ ÙÙÙÙ:",
        reply_markup=admin_button_selector(),
    )


async def handle_admin_text(update, context, state, text):
    # Settings editor
    if state == "ADMIN_SETTINGS":
        mapping = {
            "âï¸ Ø§Ø³Ù Ø§ÙØ¨ÙØª": "bot_name",
            "ð  Ø§Ø³Ù Ø§ÙØ±Ø¦ÙØ³ÙØ©": "home_title",
            "ð ÙØµ Ø§ÙØ±Ø¦ÙØ³ÙØ©": "home_text",
            "â¹ï¸ ÙØµ Ø­ÙÙ Ø§ÙØ¨ÙØª": "about_text",
            "ð ÙØµ Ø§ÙØ§Ø´ØªØ±Ø§Ù": "subscription_text",
            "ð  ÙØµ Ø§ÙØµÙØ§ÙØ©": "maintenance_text",
            "ð ÙØµ Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª": "notifications_text",
            "ð¢ ÙØµ Ø§ÙØ¥Ø¹ÙØ§Ù": "announcement_text",
        }
        if text in mapping:
            context.user_data["state"] = "SETTING_VALUE"
            context.user_data["setting_key"] = mapping[text]
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§ÙÙÙÙØ© Ø§ÙØ¬Ø¯ÙØ¯Ø©:",
                reply_markup=cancel_keyboard(),
            )
            return True

    if state == "SETTING_VALUE":
        key = context.user_data.get("setting_key")
        if key:
            set_setting(key, text)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "â ØªÙ Ø­ÙØ¸ Ø§ÙØ¥Ø¹Ø¯Ø§Ø¯ Ø¨ÙØ¬Ø§Ø­.",
            reply_markup=admin_keyboard(),
        )
        return True

    # Add button
    if state == "ADD_BUTTON_TITLE":
        context.user_data["new_button_title"] = text
        context.user_data["state"] = "ADD_BUTTON_PARENT"
        await update.effective_message.reply_text(
            "ð Ø£ÙÙ ØªØ±ÙØ¯ ÙØ¶Ø¹ Ø§ÙØ²Ø±Ø\n\n"
            "Ø£Ø±Ø³Ù ID Ø§ÙØ²Ø± Ø§ÙØ£Ø¨Ø Ø£Ù Ø§ÙØªØ¨ 0 ÙÙÙÙÙ ÙÙ Ø§ÙØ±Ø¦ÙØ³ÙØ©.",
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
                "â ID ØºÙØ± ØµØ­ÙØ­. Ø£Ø±Ø³Ù Ø±ÙÙ Ø²Ø± ÙÙØ¬ÙØ¯ Ø£Ù 0."
            )
            return True

        bid = add_button(
            context.user_data.get("new_button_title", "ð Ø²Ø± Ø¬Ø¯ÙØ¯"),
            parent_id,
            "menu",
            "",
        )
        context.user_data.clear()

        await update.effective_message.reply_text(
            f"â ØªÙ Ø¥ÙØ´Ø§Ø¡ Ø§ÙØ²Ø±.\nð ID: <code>{bid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return True

    # Edit button select
    if state == "EDIT_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("â Ø§Ø®ØªØ± Ø²Ø±ÙØ§ ØµØ­ÙØ­ÙØ§.")
            return True
        context.user_data["edit_button_id"] = bid
        context.user_data["state"] = "EDIT_BUTTON_MENU"
        await update.effective_message.reply_text(
            "âï¸ ÙØ§Ø°Ø§ ØªØ±ÙØ¯ ØªØ¹Ø¯ÙÙØ",
            reply_markup=reply_kb([
                ["ð Ø§ÙØ§Ø³Ù", "ð Ø§ÙØ±Ø§Ø¨Ø·"],
                ["ð¯ ÙÙØ¹ Ø§ÙØ¥Ø¬Ø±Ø§Ø¡"],
                ["ð ØªÙØ¹ÙÙ/ØªØ¹Ø·ÙÙ"],
                ["â¬ï¸ Ø±Ø¬ÙØ¹"],
            ]),
        )
        return True

    if state == "EDIT_BUTTON_MENU":
        bid = context.user_data["edit_button_id"]
        if text == "ð Ø§ÙØ§Ø³Ù":
            context.user_data["state"] = "EDIT_BUTTON_NAME"
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§ÙØ§Ø³Ù Ø§ÙØ¬Ø¯ÙØ¯:", reply_markup=cancel_keyboard()
            )
            return True
        if text == "ð Ø§ÙØ±Ø§Ø¨Ø·":
            context.user_data["state"] = "EDIT_BUTTON_URL"
            await update.effective_message.reply_text(
                "ð Ø£Ø±Ø³Ù Ø§ÙØ±Ø§Ø¨Ø·:", reply_markup=cancel_keyboard()
            )
            return True
        if text == "ð¯ ÙÙØ¹ Ø§ÙØ¥Ø¬Ø±Ø§Ø¡":
            context.user_data["state"] = "EDIT_BUTTON_ACTION"
            await update.effective_message.reply_text(
                "Ø§Ø®ØªØ± Ø§ÙÙÙØ¹:",
                reply_markup=reply_kb([
                    ["ð ÙØ§Ø¦ÙØ©", "ð ÙØ­ØªÙÙ"],
                    ["ð Ø¨Ø­Ø«", "â­ ÙÙØ¶ÙØ©"],
                    ["ð Ø¥Ø´Ø¹Ø§Ø±Ø§Øª", "â­ ØªÙÙÙÙ"],
                    ["ð¬ ÙØ±Ø§Ø³ÙØ©", "â¹ï¸ Ø­ÙÙ"],
                    ["ð Ø±Ø§Ø¨Ø·"],
                    ["â Ø¥ÙØºØ§Ø¡"],
                ]),
            )
            return True
        if text == "ð ØªÙØ¹ÙÙ/ØªØ¹Ø·ÙÙ":
            b = get_button(bid)
            update_button(bid, enabled=0 if b["enabled"] else 1)
            context.user_data.clear()
            await update.effective_message.reply_text(
                "â ØªÙ ØªØºÙÙØ± Ø­Ø§ÙØ© Ø§ÙØ²Ø±.",
                reply_markup=admin_keyboard(),
            )
            return True

    if state == "EDIT_BUTTON_NAME":
        update_button(context.user_data["edit_button_id"], title=text)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "â ØªÙ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙØ²Ø±.", reply_markup=admin_keyboard()
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
            "â ØªÙ Ø­ÙØ¸ Ø§ÙØ±Ø§Ø¨Ø·.", reply_markup=admin_keyboard()
        )
        return True

    if state == "EDIT_BUTTON_ACTION":
        mapping = {
            "ð ÙØ§Ø¦ÙØ©": ("menu", ""),
            "ð ÙØ­ØªÙÙ": ("content", ""),
            "ð Ø¨Ø­Ø«": ("search", ""),
            "â­ ÙÙØ¶ÙØ©": ("favorites", ""),
            "ð Ø¥Ø´Ø¹Ø§Ø±Ø§Øª": ("notifications", ""),
            "â­ ØªÙÙÙÙ": ("rating", ""),
            "ð¬ ÙØ±Ø§Ø³ÙØ©": ("contact", ""),
            "â¹ï¸ Ø­ÙÙ": ("about", ""),
            "ð Ø±Ø§Ø¨Ø·": ("url", ""),
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
                "â ØªÙ ØªØ¹Ø¯ÙÙ ÙØ¸ÙÙØ© Ø§ÙØ²Ø±.",
                reply_markup=admin_keyboard(),
            )
            return True

    # Delete confirmation
    if state == "DELETE_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("â Ø§Ø®ØªØ± Ø²Ø±ÙØ§ ØµØ­ÙØ­ÙØ§.")
            return True

        context.user_data["delete_button_id"] = bid
        context.user_data["state"] = "DELETE_CONFIRM"
        await update.effective_message.reply_text(
            f"â ï¸ <b>ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù</b>\n\n"
            f"Ø³ÙØªÙ Ø­Ø°Ù Ø§ÙØ²Ø± ÙÙÙ Ø§ÙØ£Ø²Ø±Ø§Ø± Ø§ÙÙÙØ¬ÙØ¯Ø© ØªØ­ØªÙ.\n\n"
            f"ÙÙ Ø£ÙØª ÙØªØ£ÙØ¯Ø",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb([
                ["â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù", "â Ø¥ÙØºØ§Ø¡"],
            ]),
        )
        return True

    if state == "DELETE_CONFIRM":
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù":
            delete_button_tree(context.user_data["delete_button_id"])
            context.user_data.clear()
            await update.effective_message.reply_text(
                "ð ØªÙ Ø§ÙØ­Ø°Ù Ø¨ÙØ¬Ø§Ø­.",
                reply_markup=admin_keyboard(),
            )
            return True

    # Move
    if state == "MOVE_BUTTON_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("â Ø§Ø®ØªØ± Ø²Ø±ÙØ§ ØµØ­ÙØ­ÙØ§.")
            return True
        context.user_data["move_button_id"] = bid
        context.user_data["state"] = "MOVE_BUTTON_PARENT"
        await update.effective_message.reply_text(
            "ð Ø£Ø±Ø³Ù ID Ø§ÙØ²Ø± Ø§ÙØ£Ø¨ Ø§ÙØ¬Ø¯ÙØ¯Ø Ø£Ù 0 ÙÙØ±Ø¦ÙØ³ÙØ©:",
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
            await update.effective_message.reply_text("â ID ØºÙØ± ØµØ­ÙØ­.")
            return True

        context.user_data["state"] = "MOVE_CONFIRM"
        context.user_data["move_parent"] = parent
        await update.effective_message.reply_text(
            "â ï¸ ØªØ£ÙÙØ¯ Ø§ÙÙÙÙØ",
            reply_markup=reply_kb([
                ["â ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ", "â Ø¥ÙØºØ§Ø¡"],
            ]),
        )
        return True

    if state == "MOVE_CONFIRM":
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ":
            ok = move_button(
                context.user_data["move_button_id"],
                context.user_data["move_parent"],
            )
            context.user_data.clear()
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙÙÙÙ Ø¨ÙØ¬Ø§Ø­." if ok else "â ØªØ¹Ø°Ø± Ø§ÙÙÙÙ.",
                reply_markup=admin_keyboard(),
            )
            return True

    # Content editor
    if state == "ADD_CONTENT_SELECT":
        bid = parse_id_from_button_text(text)
        if not bid or not get_button(bid):
            await update.effective_message.reply_text("â Ø§Ø®ØªØ± Ø²Ø±ÙØ§ ØµØ­ÙØ­ÙØ§.")
            return True
        context.user_data["content_button_id"] = bid
        context.user_data["state"] = "ADD_CONTENT_WAIT"
        await update.effective_message.reply_text(
            "ð¨ Ø£Ø±Ø³Ù Ø§ÙÙØ­ØªÙÙ Ø§ÙØ¢Ù.\n\n"
            "Ø³ÙØªÙ Ø­ÙØ¸ Ø§ÙØ±Ø³Ø§ÙØ© Ø§ÙØ­Ø§ÙÙØ© ÙÙØ§ ÙÙ.",
            reply_markup=cancel_keyboard(),
        )
        return True

    if state == "DELETE_CONTENT_SELECT":
        if not text.startswith("ð") or "ãC" not in text:
            await update.effective_message.reply_text("â Ø§Ø®ØªØ± ÙØ­ØªÙÙ ØµØ­ÙØ­ÙØ§.")
            return True
        try:
            cid = int(text.split("ãC", 1)[1].split("ã", 1)[0])
        except ValueError:
            await update.effective_message.reply_text("â ID ØºÙØ± ØµØ­ÙØ­.")
            return True

        context.user_data["delete_content_id"] = cid
        context.user_data["state"] = "DELETE_CONTENT_CONFIRM"
        await update.effective_message.reply_text(
            "â ï¸ ØªØ£ÙÙØ¯ Ø­Ø°Ù Ø§ÙÙØ­ØªÙÙØ",
            reply_markup=reply_kb([
                ["â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù", "â Ø¥ÙØºØ§Ø¡"],
            ]),
        )
        return True

    if state == "DELETE_CONTENT_CONFIRM":
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù":
            delete_content(context.user_data["delete_content_id"])
            context.user_data.clear()
            await update.effective_message.reply_text(
                "ð ØªÙ Ø­Ø°Ù Ø§ÙÙØ­ØªÙÙ.",
                reply_markup=admin_keyboard(),
            )
            return True

    return False


# ============================================================
# ADMIN MEDIA / USER MEDIA ROUTER
# ============================================================

async def route_media(update, context):
    # Text messages are handled by the dedicated text router.
    # This handler is intentionally registered before it so media can be
    # captured, but text must be delegated explicitly.
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
        title = c["title"] if c else "ÙØ­ØªÙÙ Ø¬Ø¯ÙØ¯"

        context.user_data.clear()
        await update.effective_message.reply_text(
            f"ð <b>ÙØ¹Ø§ÙÙØ© Ø§ÙÙØ­ØªÙÙ</b>\n\n"
            f"ð Ø§ÙØ²Ø±: {html.escape(get_button(bid)['title'])}\n"
            f"ð {html.escape(title)}\n\n"
            f"â ï¸ ØªÙ Ø§ÙØ­ÙØ¸ ÙØ§ÙÙØ´Ø±.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )

        await send_new_content_notifications(bid, title)
        return

    if state == "USER_CONTACT":
        mid = add_user_message(update)
        context.user_data.clear()
        await update.effective_message.reply_text(
            "â ÙØµÙØª Ø±Ø³Ø§ÙØªÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø© â¤ï¸",
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
                f"ð¬ Ø±Ø³Ø§ÙØ© Ø¬Ø¯ÙØ¯Ø© ÙÙ Ø§ÙÙØ³ØªØ®Ø¯Ù\nð <code>{user.id}</code>\nØ±ÙÙ: {mid}",
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
        await update.message.reply_text("ð« ÙØ§ ÙÙÙÙÙ Ø§Ø³ØªØ®Ø¯Ø§Ù Ø§ÙØ¨ÙØª.")
        return

    # Admin bypasses subscription and maintenance.
    if user.id == ADMIN_ID:
        if text == "/admin":
            await show_admin(update)
            return

        if text == "âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª":
            await admin_settings(update, context); return
        if text == "ð ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±":
            await admin_buttons(update, context); return
        if text == "ð ÙØ­Ø±Ø± Ø§ÙÙØ­ØªÙÙ":
            await admin_content(update, context); return
        if text == "ð£ Ø±Ø³Ø§ÙØ© Ø¬ÙØ§Ø¹ÙØ©":
            await admin_broadcast_start(update, context); return
        if text == "ð Ø§ÙÙØ¹Ø§ÙÙØ©":
            await admin_preview(update, context); return
        if text == "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª":
            await admin_stats(update, context); return
        if text == "ð  Ø§ÙØµÙØ§ÙØ©":
            current = get_setting("maintenance") == "1"
            set_setting("maintenance", "0" if current else "1")
            await update.message.reply_text(
                f"ð  Ø§ÙØµÙØ§ÙØ© Ø§ÙØ¢Ù: {'ð¢ ÙØªÙÙÙØ©' if current else 'ð´ ÙÙØ¹ÙØ©'}",
                reply_markup=admin_keyboard(),
            )
            return
        if text == "ð  ÙØ§Ø¬ÙØ© Ø§ÙÙØ³ØªØ®Ø¯Ù":
            await show_home(update); return

        if text == "â Ø¥Ø¶Ø§ÙØ© Ø²Ø±":
            await add_button_start(update, context); return
        if text == "âï¸ ØªØ¹Ø¯ÙÙ Ø²Ø±":
            await edit_button_start(update, context); return
        if text == "ð Ø­Ø°Ù Ø²Ø±":
            await delete_button_start(update, context); return
        if text == "ð ÙÙÙ Ø²Ø±":
            await move_button_start(update, context); return
        if text == "ð Ø¹Ø±Ø¶ Ø§ÙØ£Ø²Ø±Ø§Ø±":
            rows = []
            for b in all_buttons():
                rows.append(
                    f"ð <code>{b['id']}</code> â {html.escape(b['title'])} "
                    f"â {b['action_type']} â {'ð¢' if b['enabled'] else 'ð´'}"
                )
            await update.message.reply_text(
                "ð <b>Ø§ÙØ£Ø²Ø±Ø§Ø±</b>\n\n" + ("\n".join(rows) or "ÙØ§ ØªÙØ¬Ø¯."),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(),
            )
            return

        if text == "â Ø¥Ø¶Ø§ÙØ© ÙØ­ØªÙÙ":
            context.user_data["state"] = "ADD_CONTENT_SELECT"
            await update.message.reply_text(
                "ð Ø§Ø®ØªØ± Ø§ÙØ²Ø± Ø§ÙØ°Ù Ø³ÙØ­ØªÙÙ Ø¹ÙÙ Ø§ÙÙØ­ØªÙÙ:",
                reply_markup=admin_button_selector(),
            )
            return

        if text == "ð Ø­Ø°Ù ÙØ­ØªÙÙ":
            contents = []
            for b in all_buttons():
                for c in get_contents(b["id"], False):
                    contents.append([KeyboardButton(
                        f"ð {c['title'][:50]} ãC{c['id']}ã"
                    )])
            contents.append([KeyboardButton("â Ø¥ÙØºØ§Ø¡")])
            context.user_data["state"] = "DELETE_CONTENT_SELECT"
            await update.message.reply_text(
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ­ØªÙÙ:",
                reply_markup=reply_kb(contents),
            )
            return

        if text == "ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ":
            conn = db()
            rows = conn.execute("""
                SELECT user_id,first_name,username,banned,notifications
                FROM users ORDER BY last_seen DESC LIMIT 30
            """).fetchall()
            conn.close()
            lines = ["ð¥ <b>Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ</b>\n"]
            for r in rows:
                lines.append(
                    f"{'ð«' if r['banned'] else 'ð¢'} "
                    f"<code>{r['user_id']}</code> "
                    f"{html.escape(r['first_name'] or '-')}"
                )
            await update.message.reply_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(),
            )
            return

        if text == "ð¢ Ø§ÙØ¥Ø¹ÙØ§Ù":
            context.user_data["state"] = "ADMIN_ANNOUNCEMENT"
            await update.message.reply_text(
                "ð¢ Ø£Ø±Ø³Ù Ø§ÙØ¥Ø¹ÙØ§Ù. Ø³ØªØ¸ÙØ± ÙÙ Ø§ÙÙØ¹Ø§ÙÙØ© ÙØ¨Ù Ø§ÙÙØ´Ø±.",
                reply_markup=cancel_keyboard(),
            )
            return

        # Admin state processing.
        state = context.user_data.get("state")
        if state == "ADMIN_BROADCAST":
            await broadcast_preview(update, context); return
        if state == "ADMIN_BROADCAST_CONFIRM":
            if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ¥Ø±Ø³Ø§Ù":
                await execute_broadcast(update, context)
            elif text == "â Ø¥ÙØºØ§Ø¡":
                context.user_data.clear()
                await show_admin(update)
            return

        if state == "ADMIN_ANNOUNCEMENT":
            context.user_data["state"] = "ADMIN_BROADCAST_CONFIRM"
            context.user_data["broadcast_chat_id"] = update.effective_chat.id
            context.user_data["broadcast_message_id"] = update.message.message_id
            await update.message.reply_text(
                "ð ÙØ¹Ø§ÙÙØ© Ø§ÙØ¥Ø¹ÙØ§Ù Ø¬Ø§ÙØ²Ø©.\n\nâ ï¸ ØªØ£ÙÙØ¯ Ø§ÙÙØ´Ø±Ø",
                reply_markup=reply_kb([
                    ["â ØªØ£ÙÙØ¯ Ø§ÙØ¥Ø±Ø³Ø§Ù", "â Ø¥ÙØºØ§Ø¡"]
                ]),
            )
            return

        if state and await handle_admin_text(update, context, state, text):
            return

        if text == "â¬ï¸ Ø±Ø¬ÙØ¹" or text == "â Ø¥ÙØºØ§Ø¡":
            context.user_data.clear()
            await show_admin(update)
            return

    # Maintenance for normal users.
    if get_setting("maintenance") == "1":
        await update.message.reply_text(
            get_setting("maintenance_text"),
            reply_markup=reply_kb([["ð ØªØ­Ø¯ÙØ«"]]),
        )
        return

    # Subscription check on EVERY normal interaction.
    if await subscription_required(user.id):
        await send_subscription_gate(update)
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
                "ð ÙÙ Ø£Ø¬Ø¯ ÙØªØ§Ø¦Ø¬.",
                reply_markup=home_keyboard(),
            )
            return

        await update.message.reply_text(
            "ð <b>ÙØªØ§Ø¦Ø¬ Ø§ÙØ¨Ø­Ø«</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb(
                [[KeyboardButton(r["title"])] for r in rows] +
                [["ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]
            ),
        )
        return

    if state == "USER_CONTACT":
        mid = add_user_message(update)
        context.user_data.clear()
        try:
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"ð¬ <b>Ø±Ø³Ø§ÙØ© Ø¬Ø¯ÙØ¯Ø© #{mid}</b>\n"
                f"ð¤ {html.escape(user.full_name)}\n"
                f"ð <code>{user.id}</code>\n\n"
                f"{html.escape(text)}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        await update.message.reply_text(
            "â ÙØµÙØª Ø±Ø³Ø§ÙØªÙ ÙÙØ¥Ø¯Ø§Ø±Ø©.",
            reply_markup=home_keyboard(),
        )
        return

    if state == "USER_RATING":
        if text.startswith("â­"):
            rating = min(5, text.count("â­"))
            context.user_data["rating"] = rating
            context.user_data["state"] = "USER_RATING_COMMENT"
            await update.message.reply_text(
                "âï¸ Ø§ÙØªØ¨ ÙÙØ§Ø­Ø¸ØªÙ Ø£Ù Ø§ÙØªØ¨ Â«Ø¨Ø¯ÙÙ ÙÙØ§Ø­Ø¸Ø©Â»:",
                reply_markup=cancel_keyboard(),
            )
        return

    if state == "USER_RATING_COMMENT":
        rating = context.user_data.get("rating", 5)
        comment = "" if text == "Ø¨Ø¯ÙÙ ÙÙØ§Ø­Ø¸Ø©" else text
        conn = db()
        conn.execute("""
            INSERT INTO ratings(user_id,rating,comment,created_at)
            VALUES(?,?,?,?)
        """, (user.id, rating, comment, now()))
        conn.commit()
        conn.close()
        context.user_data.clear()
        await update.message.reply_text(
            "â¤ï¸ Ø´ÙØ±Ø§Ù Ø¹ÙÙ ØªÙÙÙÙÙ!",
            reply_markup=home_keyboard(),
        )
        return

    if text in ("ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©", "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©", "/start"):
        context.user_data.clear()
        await show_home(update)
        return

    if text == "ð ØªØ­Ø¯ÙØ«":
        await show_home(update)
        return

    if text == "ð ØªÙØ¹ÙÙ Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª":
        set_notifications(user.id, True)
        await update.message.reply_text(
            "ð ØªÙ ØªÙØ¹ÙÙ Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª. Ø³ØªØµÙÙ ØªØ­Ø¯ÙØ«Ø§Øª Ø§ÙÙØ­ØªÙÙ Ø§ÙØ¬Ø¯ÙØ¯.",
            reply_markup=home_keyboard(),
        )
        return

    if text == "ð Ø¥ÙÙØ§Ù Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª":
        set_notifications(user.id, False)
        await update.message.reply_text(
            "ð ØªÙ Ø¥ÙÙØ§Ù Ø§ÙØ¥Ø´Ø¹Ø§Ø±Ø§Øª.",
            reply_markup=home_keyboard(),
        )
        return

    if text in ("â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©", "ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©"):
        state_button = context.user_data.get("last_button_id")
        if state_button:
            added = toggle_favorite(user.id, state_button)
            await update.message.reply_text(
                "â­ ØªÙØª Ø§ÙØ¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©." if added else "ð ØªÙØª Ø§ÙØ¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©.",
                reply_markup=home_keyboard(),
            )
        else:
            await show_favorites(update)
        return

    # Content button selection: ð ... ãCidã
    if "ãC" in text and text.startswith("ð"):
        try:
            cid = int(text.split("ãC", 1)[1].split("ã", 1)[0])
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

    # Match dynamic button by exact title.
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
        "ð¤ ÙØ§ ÙÙÙØª Ø§Ø®ØªÙØ§Ø±Ù.\n\nØ¬Ø±ÙØ¨ Ø£Ø­Ø¯ Ø§ÙØ£Ø²Ø±Ø§Ø± Ø§ÙØ¸Ø§ÙØ±Ø©.",
        reply_markup=home_keyboard(),
    )


# ============================================================
# CALLBACKS
# ============================================================

async def callback_router(update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "SUB:CHECK":
        if not REQUIRED_CHANNEL:
            await query.edit_message_text("â ÙØ§ ÙÙØ¬Ø¯ Ø§Ø´ØªØ±Ø§Ù Ø¥Ø¬Ø¨Ø§Ø±Ù Ø­Ø§ÙÙØ§Ù.")
            return

        if await subscription_required(user.id):
            await query.edit_message_text(
                "â ÙÙ ÙØªÙ Ø§ÙØªØ­ÙÙ ÙÙ Ø§Ø´ØªØ±Ø§ÙÙ Ø¨Ø¹Ø¯.\n"
                "Ø§Ø´ØªØ±Ù Ø¨Ø§ÙÙÙØ§Ø© Ø«Ù Ø§Ø¶ØºØ· ØªØ­ÙÙ ÙØ±Ø© Ø£Ø®Ø±Ù."
            )
        else:
            await query.edit_message_text(
                "â ØªÙ Ø§ÙØªØ­ÙÙ ÙÙ Ø§Ø´ØªØ±Ø§ÙÙ Ø¨ÙØ¬Ø§Ø­!\n"
                "Ø§Ø±Ø¬Ø¹ ÙÙØ¨ÙØª ÙØ§Ø®ØªØ± ÙØ§ ØªØ±ÙØ¯."
            )
        return


# ============================================================
# START / WEBHOOK
# ============================================================

async def start(update, context):
    save_user(update.effective_user)

    if is_banned(update.effective_user.id) and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("ð« ØªÙ Ø­Ø¸Ø±Ù ÙÙ Ø§Ø³ØªØ®Ø¯Ø§Ù Ø§ÙØ¨ÙØª.")
        return

    if update.effective_user.id != ADMIN_ID:
        if get_setting("maintenance") == "1":
            await update.message.reply_text(get_setting("maintenance_text"))
            return

        if await subscription_required(update.effective_user.id):
            await send_subscription_gate(update)
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

    if WEBHOOK_URL:
        url = WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH
        await application.bot.set_webhook(url=url)
        logger.info("Webhook configured: %s", url)


def build_application():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", show_admin))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, route_media)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    return application


def run():
    init_db()
    application = build_application()

    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH,
            drop_pending_updates=False,
        )
    else:
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )


if __name__ == "__main__":
    run()
