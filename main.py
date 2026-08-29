# -*- coding: utf-8 -*-
"""
Telegram Educational Bot - Render / Python 3.11+
Inspired by common MenuBuilder-style features:
- Nested menus / sections
- Dynamic button editor
- Add / rename / delete / move sections
- Store Telegram messages and media
- Search content
- Favorites
- Ratings + feedback
- User messages / support
- Statistics
- Broadcast to all users
- Referral/deep-link tracking
- User balance
- Ban/unban
- Admin panel
- Editable About text
- Automatic section index
- Back / Home navigation
- Flask webhook for Render
"""

import os
import html
import sqlite3
import logging
import threading
import asyncio
from datetime import datetime
from functools import wraps

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = 5734654153
# You can override the hard-coded admin with Render:
# ADMIN_ID=5734654153
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", str(ADMIN_ID)))
except ValueError:
    ADMIN_ID = 5734654153

PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")
DB_FILE = os.getenv("DB_FILE", "bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("educational-bot")

flask_app = Flask(__name__)
telegram_app = None
db_lock = threading.RLock()

# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = db()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            joined_at TEXT,
            last_seen TEXT,
            visits INTEGER DEFAULT 0,
            balance REAL DEFAULT 0,
            banned INTEGER DEFAULT 0,
            referrer_id INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            source_chat_id INTEGER NOT NULL,
            source_message_id INTEGER NOT NULL,
            content_type TEXT,
            title TEXT,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            PRIMARY KEY(user_id, section_id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT,
            created_at TEXT,
            answered INTEGER DEFAULT 0
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            value TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            section_id INTEGER,
            created_at TEXT
        )
        """)

        conn.commit()

        root = cur.execute(
            "SELECT id FROM sections WHERE parent_id IS NULL ORDER BY id LIMIT 1"
        ).fetchone()

        if not root:
            cur.execute(
                """INSERT INTO sections(parent_id,name,sort_order,created_at)
                   VALUES(NULL,?,?,?)""",
                ("ð ÙÙØ¯Ø³Ø© ØªÙÙÙØ§Øª Ø§ÙØ­Ø§Ø³ÙØ¨", 1, datetime.utcnow().isoformat()),
            )

        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES('about',?)",
            ("ð <b>Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØªØ¹ÙÙÙÙ Ø§ÙØ°ÙÙ</b>\n\n"
             "Ø¨ÙØª ØªØ¹ÙÙÙÙ ÙØªÙØ¸ÙÙ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙÙØ­Ø§Ø¶Ø±Ø§Øª ÙØ§ÙÙÙÙØ§Øª ÙØ§ÙØ±Ø³Ø§Ø¦Ù.\n\n"
             "Ø§Ø³ØªØ®Ø¯Ù Ø§ÙØ£Ø²Ø±Ø§Ø± ÙÙØªÙÙÙ Ø¨ÙÙ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙÙØ­ØªÙÙ.",),
        )

        conn.commit()
        conn.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_setting(key, default=""):
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = db()
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def create_section(parent_id, name):
    conn = db()
    order_no = conn.execute(
        "SELECT COALESCE(MAX(sort_order),0)+1 n FROM sections WHERE parent_id IS ?",
        (parent_id,),
    ).fetchone()["n"]
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sections(parent_id,name,sort_order,created_at) VALUES(?,?,?,?)",
        (parent_id, name, order_no, datetime.utcnow().isoformat()),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def get_section(section_id):
    conn = db()
    row = conn.execute("SELECT * FROM sections WHERE id=?", (section_id,)).fetchone()
    conn.close()
    return row


def get_children(parent_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM sections WHERE parent_id IS ? ORDER BY sort_order,id",
        (parent_id,),
    ).fetchall()
    conn.close()
    return rows


def get_contents(section_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM contents WHERE section_id=? ORDER BY id",
        (section_id,),
    ).fetchall()
    conn.close()
    return rows


def section_path(section_id):
    parts = []
    current = get_section(section_id)
    while current:
        parts.append(current["name"])
        pid = current["parent_id"]
        current = get_section(pid) if pid else None
    return "  âº  ".join(reversed(parts))


def add_content(section_id, chat_id, message_id, content_type, title):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO contents
           (section_id,source_chat_id,source_message_id,content_type,title,created_at)
           VALUES(?,?,?,?,?,?)""",
        (
            section_id,
            chat_id,
            message_id,
            content_type,
            title,
            datetime.utcnow().isoformat(),
        ),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def delete_content(content_id):
    conn = db()
    conn.execute("DELETE FROM contents WHERE id=?", (content_id,))
    conn.commit()
    conn.close()


def rename_section(section_id, name):
    conn = db()
    conn.execute("UPDATE sections SET name=? WHERE id=?", (name, section_id))
    conn.commit()
    conn.close()


def descendants(section_id):
    result = set()
    queue = [section_id]
    while queue:
        current = queue.pop()
        for row in get_children(current):
            result.add(row["id"])
            queue.append(row["id"])
    return result


def delete_section_tree(section_id):
    conn = db()
    queue = [section_id]
    ids = []
    while queue:
        current = queue.pop()
        ids.append(current)
        children = conn.execute(
            "SELECT id FROM sections WHERE parent_id=?", (current,)
        ).fetchall()
        queue.extend([x["id"] for x in children])

    marks = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM contents WHERE section_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM favorites WHERE section_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM sections WHERE id IN ({marks})", ids)
    conn.commit()
    conn.close()


def move_section(section_id, parent_id):
    if section_id == parent_id or parent_id in descendants(section_id):
        return False
    conn = db()
    conn.execute("UPDATE sections SET parent_id=? WHERE id=?", (parent_id, section_id))
    conn.commit()
    conn.close()
    return True


def add_user(user, referrer_id=None):
    now = datetime.utcnow().isoformat()
    conn = db()
    old = conn.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()

    if old:
        conn.execute(
            """UPDATE users SET first_name=?,last_name=?,username=?,
               last_seen=?,visits=visits+1 WHERE user_id=?""",
            (
                user.first_name or "",
                user.last_name or "",
                user.username or "",
                now,
                user.id,
            ),
        )
    else:
        valid_ref = referrer_id if referrer_id and referrer_id != user.id else None
        conn.execute(
            """INSERT INTO users
               (user_id,first_name,last_name,username,joined_at,last_seen,visits,referrer_id)
               VALUES(?,?,?,?,?,?,1,?)""",
            (
                user.id,
                user.first_name or "",
                user.last_name or "",
                user.username or "",
                now,
                now,
                valid_ref,
            ),
        )

    conn.commit()
    conn.close()
    return old is None


def is_banned(user_id):
    conn = db()
    row = conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row["banned"])


def set_banned(user_id, value):
    conn = db()
    conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if value else 0, user_id))
    conn.commit()
    conn.close()


def set_state(user_id, state, value=""):
    conn = db()
    conn.execute(
        """INSERT INTO user_state(user_id,state,value) VALUES(?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,value=excluded.value""",
        (user_id, state, value),
    )
    conn.commit()
    conn.close()


def get_state(user_id):
    conn = db()
    row = conn.execute(
        "SELECT state,value FROM user_state WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row


def clear_state(user_id):
    conn = db()
    conn.execute("DELETE FROM user_state WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def toggle_favorite(user_id, section_id):
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND section_id=?",
        (user_id, section_id),
    ).fetchone()

    if row:
        conn.execute(
            "DELETE FROM favorites WHERE user_id=? AND section_id=?",
            (user_id, section_id),
        )
        result = False
    else:
        conn.execute(
            "INSERT INTO favorites(user_id,section_id) VALUES(?,?)",
            (user_id, section_id),
        )
        result = True

    conn.commit()
    conn.close()
    return result


def add_rating(user_id, rating, comment):
    conn = db()
    conn.execute(
        "INSERT INTO ratings(user_id,rating,comment,created_at) VALUES(?,?,?,?)",
        (user_id, rating, comment, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def add_message(user_id, text):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages(user_id,text,created_at) VALUES(?,?,?)",
        (user_id, text, datetime.utcnow().isoformat()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


# ============================================================
# KEYBOARDS
# ============================================================

MAIN = [
    ["ð Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ¹ÙÙÙÙØ©"],
    ["ð Ø§ÙØ¨Ø­Ø«", "â­ Ø§ÙÙÙØ¶ÙØ©"],
    ["ð¥ Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù", "ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª"],
    ["â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª", "â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª"],
    ["ð¥ Ø§ÙØ¯Ø¹ÙØ§Øª", "ð° Ø±ØµÙØ¯Ù"],
]

ADMIN = [
    ["ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù", "ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª"],
    ["ð¢ Ø¥Ø±Ø³Ø§Ù Ø¬ÙØ§Ø¹Ù", "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª"],
    ["ð¥ Ø¥Ø¯Ø§Ø±Ø© Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ", "âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª"],
    ["ð ØªØ¹Ø¯ÙÙ Ø­ÙÙ Ø§ÙØ¨ÙØª", "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
]


def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def main_keyboard(user_id):
    rows = [x[:] for x in MAIN]
    if user_id == ADMIN_ID:
        rows.append(["ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©"])
    return kb(rows)


def back_kb():
    return kb([["â¬ï¸ Ø±Ø¬ÙØ¹"], ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]])


def admin_kb():
    return kb(ADMIN)


# ============================================================
# NAVIGATION
# ============================================================

async def show_main(update, text=None):
    user_id = update.effective_user.id
    if text is None:
        text = (
            "ð <b>Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØªØ¹ÙÙÙÙ Ø§ÙØ°ÙÙ</b>\n\n"
            "Ø§Ø®ØªØ± ÙÙ Ø§ÙÙØ§Ø¦ÙØ© Ø£Ø¯ÙØ§Ù:"
        )
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user_id)
    )


async def show_section(update, section_id):
    section = get_section(section_id)
    if not section:
        await show_main(update, "â Ø§ÙÙØ³Ù ØºÙØ± ÙÙØ¬ÙØ¯.")
        return

    user_id = update.effective_user.id
    set_state(user_id, "BROWSE", str(section_id))

    conn = db()
    conn.execute(
        "INSERT INTO visits(user_id,section_id,created_at) VALUES(?,?,?)",
        (user_id, section_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    rows = [[f"ð {x['name']}"] for x in get_children(section_id)]

    for c in get_contents(section_id):
        title = c["title"] or f"ÙØ´Ø§Ø±ÙØ© {c['id']}"
        rows.append([f"ð {title[:60]}"])

    conn = db()
    fav = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND section_id=?",
        (user_id, section_id),
    ).fetchone()
    conn.close()

    rows.append(["ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©" if fav else "â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©"])

    if section["parent_id"]:
        rows.append(["â¬ï¸ Ø±Ø¬ÙØ¹", "ðª Ø®Ø±ÙØ¬ ÙÙ Ø§ÙÙØ³Ù"])
    else:
        rows.append(["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"])

    await update.effective_message.reply_text(
        f"ð <b>{html.escape(section['name'])}</b>\n\n"
        f"ð {html.escape(section_path(section_id))}\n\n"
        "Ø§Ø®ØªØ±:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb(rows),
    )


async def show_content(update, content_id):
    conn = db()
    c = conn.execute("SELECT * FROM contents WHERE id=?", (content_id,)).fetchone()
    conn.close()

    if not c:
        await update.effective_message.reply_text("â Ø§ÙÙØ­ØªÙÙ ØºÙØ± ÙÙØ¬ÙØ¯.", reply_markup=back_kb())
        return

    await update.effective_message.reply_text(
        f"ð <b>{html.escape(c['title'] or 'ÙØ­ØªÙÙ')}</b>",
        parse_mode=ParseMode.HTML,
    )

    await telegram_app.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=c["source_chat_id"],
        message_id=c["source_message_id"],
    )

    set_state(update.effective_user.id, "CONTENT", str(c["section_id"]))


# ============================================================
# SEARCH / REFERRALS / BALANCE
# ============================================================

async def search(update):
    user_id = update.effective_user.id
    set_state(user_id, "SEARCH", "")
    await update.effective_message.reply_text(
        "ð Ø£Ø±Ø³Ù ÙÙÙØ© Ø§ÙØ¨Ø­Ø«:",
        reply_markup=kb([["â Ø¥ÙØºØ§Ø¡"], ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]),
    )


async def do_search(update, query):
    conn = db()
    rows = conn.execute(
        """SELECT c.*,s.name section_name
           FROM contents c JOIN sections s ON s.id=c.section_id
           WHERE c.title LIKE ? OR c.content_type LIKE ?
           ORDER BY c.id DESC LIMIT 30""",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()

    if not rows:
        await update.effective_message.reply_text(
            "â ÙÙ Ø£Ø¬Ø¯ ÙØªØ§Ø¦Ø¬.", reply_markup=main_keyboard(update.effective_user.id)
        )
        return

    buttons = []
    for r in rows:
        title = r["title"] or f"ÙØ´Ø§Ø±ÙØ© {r['id']}"
        buttons.append([f"ð {title[:60]}"])
    buttons.append(["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"])

    set_state(update.effective_user.id, "SEARCH_RESULTS", "")
    await update.effective_message.reply_text(
        f"ð ÙØªØ§Ø¦Ø¬ Ø§ÙØ¨Ø­Ø« Ø¹Ù: <b>{html.escape(query)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb(buttons),
    )


async def referrals(update):
    me = update.effective_user.id
    bot = await telegram_app.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{me}"

    conn = db()
    count = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE referrer_id=?", (me,)
    ).fetchone()["c"]
    row = conn.execute(
        "SELECT balance FROM users WHERE user_id=?", (me,)
    ).fetchone()
    conn.close()

    await update.effective_message.reply_text(
        "ð¥ <b>ÙØ¸Ø§Ù Ø§ÙØ¯Ø¹ÙØ§Øª</b>\n\n"
        f"ð Ø±Ø§Ø¨Ø·Ù:\n<code>{html.escape(link)}</code>\n\n"
        f"ð¤ Ø¹Ø¯Ø¯ Ø§ÙÙØ¯Ø¹ÙÙÙ: <b>{count}</b>\n"
        f"ð° Ø±ØµÙØ¯Ù: <b>{row['balance'] if row else 0}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=back_kb(),
    )


async def balance(update):
    conn = db()
    row = conn.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (update.effective_user.id,),
    ).fetchone()
    conn.close()

    await update.effective_message.reply_text(
        f"ð° Ø±ØµÙØ¯Ù Ø§ÙØ­Ø§ÙÙ: <b>{row['balance'] if row else 0}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=back_kb(),
    )


# ============================================================
# ADMIN
# ============================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            await update.effective_message.reply_text("â ØºÙØ± ÙØ³ÙÙØ­.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def admin_panel(update):
    clear_state(update.effective_user.id)
    await update.effective_message.reply_text(
        "ð <b>ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n\nØ§Ø®ØªØ±:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(),
    )


async def send_section_list(update, title, state):
    rows = [[f"ð {s['name']}"] for s in all_sections()]
    rows.append(["â Ø¥ÙØºØ§Ø¡"])
    set_state(update.effective_user.id, state, "")
    await update.effective_message.reply_text(title, reply_markup=kb(rows))


def all_sections():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM sections ORDER BY parent_id,sort_order,id"
    ).fetchall()
    conn.close()
    return rows


def section_by_button(text):
    if not text.startswith("ð "):
        return None
    name = text[2:].strip()
    conn = db()
    row = conn.execute(
        "SELECT id FROM sections WHERE name=? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    conn.close()
    return row["id"] if row else None


async def section_editor(update):
    set_state(update.effective_user.id, "ADMIN_SECTION_MENU", "")
    await update.effective_message.reply_text(
        "ð§© <b>ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([
            ["â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù", "âï¸ ØªØ¹Ø¯ÙÙ ÙØ³Ù"],
            ["ð Ø­Ø°Ù ÙØ³Ù", "âï¸ ÙÙÙ ÙØ³Ù"],
            ["ð Ø¯ÙØ¬ ÙØ³ÙÙÙ"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def admin_content_editor(update):
    set_state(update.effective_user.id, "ADMIN_CONTENT_MENU", "")
    await update.effective_message.reply_text(
        "ð¨ <b>ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([
            ["â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ©"],
            ["ð Ø­Ø°Ù ÙØ´Ø§Ø±ÙØ©"],
            ["ð Ø¹Ø±Ø¶ ÙØ´Ø§Ø±ÙØ§Øª Ø§ÙÙØ³Ù"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def statistics(update):
    conn = db()
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    active = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE last_seen>=?",
        ((datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).isoformat(),),
    ).fetchone()["c"]
    sections = conn.execute("SELECT COUNT(*) c FROM sections").fetchone()["c"]
    contents = conn.execute("SELECT COUNT(*) c FROM contents").fetchone()["c"]
    ratings = conn.execute("SELECT COUNT(*) c FROM ratings").fetchone()["c"]
    messages = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    banned = conn.execute("SELECT COUNT(*) c FROM users WHERE banned=1").fetchone()["c"]
    conn.close()

    await update.effective_message.reply_text(
        "ð <b>Ø¥Ø­ØµØ§Ø¦ÙØ§Øª Ø§ÙØ¨ÙØª</b>\n\n"
        f"ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ: <b>{users}</b>\n"
        f"ð¢ ÙØ´Ø·ÙÙ Ø§ÙÙÙÙ: <b>{active}</b>\n"
        f"ð Ø§ÙØ£ÙØ³Ø§Ù: <b>{sections}</b>\n"
        f"ð¨ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª: <b>{contents}</b>\n"
        f"â­ Ø§ÙØªÙÙÙÙØ§Øª: <b>{ratings}</b>\n"
        f"ð¬ Ø§ÙØ±Ø³Ø§Ø¦Ù: <b>{messages}</b>\n"
        f"ð« Ø§ÙÙØ­Ø¸ÙØ±ÙÙ: <b>{banned}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(),
    )


async def broadcast(update):
    set_state(update.effective_user.id, "BROADCAST", "")
    await update.effective_message.reply_text(
        "ð¢ Ø£Ø±Ø³Ù Ø§ÙØ¢Ù Ø§ÙØ±Ø³Ø§ÙØ© Ø§ÙØªÙ ØªØ±ÙØ¯ Ø¥Ø±Ø³Ø§ÙÙØ§ ÙÙØ¬ÙÙØ¹.\n"
        "ÙÙÙÙ Ø£Ù ØªÙÙÙ ÙØµÙØ§ Ø£Ù ØµÙØ±Ø© Ø£Ù ÙÙÙÙØ§ Ø£Ù ÙÙØ¯ÙÙ.\n\n"
        "ÙÙØ¥ÙØºØ§Ø¡: â Ø¥ÙØºØ§Ø¡",
        reply_markup=kb([["â Ø¥ÙØºØ§Ø¡"]]),
    )


async def execute_broadcast(update):
    conn = db()
    users = conn.execute("SELECT user_id FROM users WHERE banned=0").fetchall()
    conn.close()

    ok = 0
    fail = 0

    for row in users:
        try:
            await update.effective_message.copy(row["user_id"])
            ok += 1
        except Exception:
            fail += 1

    await update.effective_message.reply_text(
        f"ð¢ Ø§ÙØªÙÙØª Ø§ÙØ¥Ø°Ø§Ø¹Ø©.\n\nâ ÙØ¬Ø­: {ok}\nâ ÙØ´Ù: {fail}",
        reply_markup=admin_kb(),
    )


async def admin_users(update):
    conn = db()
    rows = conn.execute(
        "SELECT user_id,first_name,username,banned,balance FROM users ORDER BY last_seen DESC LIMIT 30"
    ).fetchall()
    conn.close()

    lines = ["ð¥ <b>Ø¢Ø®Ø± Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ</b>\n"]
    for r in rows:
        name = html.escape(r["first_name"] or "Ø¨Ø¯ÙÙ Ø§Ø³Ù")
        username = f"@{r['username']}" if r["username"] else "-"
        status = "ð«" if r["banned"] else "ð¢"
        lines.append(
            f"{status} <code>{r['user_id']}</code> â {name} â {username} â ð° {r['balance']}"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb(),
    )


# ============================================================
# MAIN MESSAGE ROUTER
# ============================================================

async def route(update, context):
    if not update.effective_message:
        return

    user = update.effective_user
    if not user:
        return

    if is_banned(user.id) and user.id != ADMIN_ID:
        await update.effective_message.reply_text("ð« ØªÙ Ø­Ø¸Ø± Ø­Ø³Ø§Ø¨Ù ÙÙ Ø§Ø³ØªØ®Ø¯Ø§Ù Ø§ÙØ¨ÙØª.")
        return

    text = (update.effective_message.text or "").strip()
    state = get_state(user.id)

    # Broadcast/media capture must run before normal routing.
    if user.id == ADMIN_ID and state and state["state"] == "BROADCAST":
        if text == "â Ø¥ÙØºØ§Ø¡":
            clear_state(user.id)
            await admin_panel(update)
        else:
            clear_state(user.id)
            await execute_broadcast(update)
        return

    # Admin add-content capture.
    if user.id == ADMIN_ID and state and state["state"] == "ADMIN_CONTENT_WAIT":
        if text == "â Ø¥ÙØºØ§Ø¡":
            clear_state(user.id)
            await admin_content_editor(update)
            return

        sid = int(state["value"])
        ctype = detect_content_type(update.effective_message)
        title = default_title(update.effective_message, ctype)
        cid = add_content(
            sid,
            update.effective_chat.id,
            update.effective_message.message_id,
            ctype,
            title,
        )
        clear_state(user.id)
        await update.effective_message.reply_text(
            f"â ØªÙ Ø­ÙØ¸ Ø§ÙÙØ´Ø§Ø±ÙØ©.\n\nð Ø§ÙÙØ³Ù: {html.escape(get_section(sid)['name'])}\n"
            f"ð Ø§ÙØ¹ÙÙØ§Ù: {html.escape(title)}\nð ID: <code>{cid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_kb(),
        )
        return

    # Search input.
    if state and state["state"] == "SEARCH":
        if text == "â Ø¥ÙØºØ§Ø¡":
            clear_state(user.id)
            await show_main(update)
            return
        await do_search(update, text)
        return

    # Rating.
    if state and state["state"] == "RATING":
        if text.startswith("â­"):
            rating = min(5, text.count("â­"))
            set_state(user.id, "RATING_COMMENT", str(rating))
            await update.effective_message.reply_text(
                f"â Ø§Ø®ØªØ±Øª {rating}/5.\nØ£Ø±Ø³Ù ÙÙØ§Ø­Ø¸ØªÙ Ø£Ù Ø§ÙØªØ¨ Â«ØªØ®Ø·ÙÂ».",
                reply_markup=kb([["ØªØ®Ø·Ù"], ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]),
            )
        return

    if state and state["state"] == "RATING_COMMENT":
        rating = int(state["value"])
        comment = "" if text == "ØªØ®Ø·Ù" else text
        add_rating(user.id, rating, comment)
        clear_state(user.id)
        try:
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"â­ <b>ØªÙÙÙÙ Ø¬Ø¯ÙØ¯</b>\n\n"
                f"ð¤ {html.escape(user.full_name)}\n"
                f"ð <code>{user.id}</code>\n"
                f"â­ {rating}/5\n"
                f"ð {html.escape(comment or 'Ø¨Ø¯ÙÙ ÙÙØ§Ø­Ø¸Ø©')}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        await update.effective_message.reply_text(
            "â Ø´ÙØ±ÙØ§ ÙØªÙÙÙÙÙ â¤ï¸",
            reply_markup=main_keyboard(user.id),
        )
        return

    # User support message.
    if state and state["state"] == "MESSAGE":
        if text:
            mid = add_message(user.id, text)
            clear_state(user.id)
            try:
                await telegram_app.bot.send_message(
                    ADMIN_ID,
                    f"ð¬ <b>Ø±Ø³Ø§ÙØ© Ø¬Ø¯ÙØ¯Ø© #{mid}</b>\n\n"
                    f"ð¤ {html.escape(user.full_name)}\n"
                    f"ð <code>{user.id}</code>\n\n"
                    f"{html.escape(text)}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            await update.effective_message.reply_text(
                "â ÙØµÙØª Ø±Ø³Ø§ÙØªÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.",
                reply_markup=main_keyboard(user.id),
            )
        return

    # Admin states.
    if user.id == ADMIN_ID:
        if await admin_state_router(update, context, state, text):
            return

    # Global navigation.
    if text in ("ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©", "/start"):
        clear_state(user.id)
        await show_main(update)
        return

    if text in ("â¬ï¸ Ø±Ø¬ÙØ¹", "ðª Ø®Ø±ÙØ¬ ÙÙ Ø§ÙÙØ³Ù"):
        if state and state["state"] in ("BROWSE", "CONTENT"):
            sid = int(state["value"])
            sec = get_section(sid)
            if sec and sec["parent_id"]:
                await show_section(update, sec["parent_id"])
            else:
                await show_main(update)
        else:
            await show_main(update)
        return

    # Main menu.
    if text == "ð Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ¹ÙÙÙÙØ©":
        roots = get_children(None)
        if roots:
            await show_section(update, roots[0]["id"])
        else:
            await show_main(update, "â ÙØ§ ØªÙØ¬Ø¯ Ø£ÙØ³Ø§Ù.")
        return

    if text == "ð Ø§ÙØ¨Ø­Ø«":
        await search(update)
        return

    if text == "â­ Ø§ÙÙÙØ¶ÙØ©":
        conn = db()
        rows = conn.execute(
            """SELECT s.* FROM sections s JOIN favorites f
               ON f.section_id=s.id WHERE f.user_id=? ORDER BY s.name""",
            (user.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await update.effective_message.reply_text(
                "â­ ÙØ§ ØªÙØ¬Ø¯ Ø£ÙØ³Ø§Ù ÙÙØ¶ÙØ©.",
                reply_markup=main_keyboard(user.id),
            )
        else:
            set_state(user.id, "FAVORITES", "")
            await update.effective_message.reply_text(
                "â­ <b>Ø§ÙÙÙØ¶ÙØ©</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb(
                    [[f"ð {r['name']}"] for r in rows]
                    + [["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]
                ),
            )
        return

    if text == "ð¥ Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù":
        conn = db()
        rows = conn.execute(
            """SELECT s.name,COUNT(v.id) n FROM visits v
               JOIN sections s ON s.id=v.section_id
               GROUP BY v.section_id ORDER BY n DESC LIMIT 10"""
        ).fetchall()
        conn.close()

        msg = "ð¥ <b>Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù</b>\n\n"
        msg += "\n".join(
            f"{i+1}. {html.escape(r['name'])} â {r['n']} Ø²ÙØ§Ø±Ø©"
            for i, r in enumerate(rows)
        ) if rows else "ÙØ§ ØªÙØ¬Ø¯ Ø¨ÙØ§ÙØ§Øª Ø¨Ø¹Ø¯."

        await update.effective_message.reply_text(
            msg, parse_mode=ParseMode.HTML, reply_markup=back_kb()
        )
        return

    if text == "ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª":
        set_state(user.id, "MESSAGE", "")
        await update.effective_message.reply_text(
            "ð¬ Ø§ÙØªØ¨ Ø±Ø³Ø§ÙØªÙ Ø£Ù Ø§Ø³ØªÙØ³Ø§Ø±Ù ÙØ³Ø£Ø±Ø³ÙÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.",
            reply_markup=back_kb(),
        )
        return

    if text == "â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª":
        set_state(user.id, "RATING", "")
        await update.effective_message.reply_text(
            "â­ Ø§Ø®ØªØ± ØªÙÙÙÙÙ:",
            reply_markup=kb([
                ["â­", "â­â­"],
                ["â­â­â­", "â­â­â­â­"],
                ["â­â­â­â­â­"],
                ["â¬ï¸ Ø±Ø¬ÙØ¹"],
            ]),
        )
        return

    if text == "â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª":
        await update.effective_message.reply_text(
            get_setting("about"),
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb(),
        )
        return

    if text == "ð¥ Ø§ÙØ¯Ø¹ÙØ§Øª":
        await referrals(update)
        return

    if text == "ð° Ø±ØµÙØ¯Ù":
        await balance(update)
        return

    # Browse dynamic buttons.
    if state and state["state"] in ("BROWSE", "FAVORITES", "SEARCH_RESULTS"):
        if text.startswith("ð "):
            sid = section_by_button(text)
            if sid:
                await show_section(update, sid)
                return

        if text.startswith("ð "):
            title = text[2:].strip()
            conn = db()
            rows = conn.execute(
                "SELECT id,section_id,title FROM contents WHERE title=? ORDER BY id DESC",
                (title,),
            ).fetchall()
            conn.close()
            if rows:
                await show_content(update, rows[0]["id"])
                return

        if text in ("â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©", "ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©"):
            sid = int(state["value"])
            enabled = toggle_favorite(user.id, sid)
            await show_section(update, sid)
            return

    if user.id == ADMIN_ID and text == "ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©":
        await admin_panel(update)
        return

    await update.effective_message.reply_text(
        "Ø§Ø³ØªØ®Ø¯Ù Ø£Ø²Ø±Ø§Ø± Ø§ÙØ¨ÙØª ÙÙ Ø§ÙÙØ§Ø¦ÙØ©.",
        reply_markup=main_keyboard(user.id),
    )


# ============================================================
# ADMIN STATE ROUTER
# ============================================================

async def admin_state_router(update, context, state, text):
    user_id = update.effective_user.id

    if text == "ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©":
        await admin_panel(update)
        return True

    if text == "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©":
        clear_state(user_id)
        await show_main(update)
        return True

    if text == "â¬ï¸ Ø±Ø¬ÙØ¹":
        clear_state(user_id)
        await admin_panel(update)
        return True

    if text == "ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù":
        await section_editor(update)
        return True

    if text == "ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª":
        await admin_content_editor(update)
        return True

    if text == "ð¢ Ø¥Ø±Ø³Ø§Ù Ø¬ÙØ§Ø¹Ù":
        await broadcast(update)
        return True

    if text == "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª":
        await statistics(update)
        return True

    if text == "ð¥ Ø¥Ø¯Ø§Ø±Ø© Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ":
        await admin_users(update)
        return True

    if text == "ð ØªØ¹Ø¯ÙÙ Ø­ÙÙ Ø§ÙØ¨ÙØª":
        set_state(user_id, "ADMIN_ABOUT", "")
        await update.effective_message.reply_text(
            "ð Ø£Ø±Ø³Ù Ø§ÙÙØµ Ø§ÙØ¬Ø¯ÙØ¯ ÙÙØ³Ù Â«Ø­ÙÙ Ø§ÙØ¨ÙØªÂ».",
            reply_markup=kb([["â Ø¥ÙØºØ§Ø¡"]]),
        )
        return True

    if state and state["state"] == "ADMIN_ABOUT":
        if text == "â Ø¥ÙØºØ§Ø¡":
            clear_state(user_id)
            await admin_panel(update)
        else:
            set_setting("about", text)
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ ØªØ­Ø¯ÙØ« ÙØ³Ù Ø­ÙÙ Ø§ÙØ¨ÙØª.",
                reply_markup=admin_kb(),
            )
        return True

    if text == "âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª":
        await update.effective_message.reply_text(
            "âï¸ <b>Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª</b>\n\n"
            "â¢ ADMIN_ID ÙØ¶Ø¨ÙØ· Ø¯Ø§Ø®Ù Ø§ÙÙÙØ¯/Render\n"
            "â¢ WEBHOOK_URL ÙÙ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Render\n"
            "â¢ ÙØ§Ø¹Ø¯Ø© Ø§ÙØ¨ÙØ§ÙØ§Øª SQLite\n"
            "â¢ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙÙÙØ±Ø³ ØªØªØ­Ø¯Ø« ØªÙÙØ§Ø¦ÙÙØ§",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_kb(),
        )
        return True

    if text == "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù":
        set_state(user_id, "ADD_PARENT", "")
        roots = get_children(None)
        await update.effective_message.reply_text(
            "â Ø§Ø®ØªØ± Ø§ÙØ£Ø¨Ø Ø£Ù Â«ð  Ø±Ø¦ÙØ³ÙÂ» ÙÙØ³Ù Ø±Ø¦ÙØ³Ù:",
            reply_markup=kb(
                [["ð  Ø±Ø¦ÙØ³Ù"]] + [[f"ð {x['name']}"] for x in roots] + [["â Ø¥ÙØºØ§Ø¡"]]
            ),
        )
        return True

    if state and state["state"] == "ADD_PARENT":
        if text == "â Ø¥ÙØºØ§Ø¡":
            await section_editor(update)
            return True
        if text == "ð  Ø±Ø¦ÙØ³Ù":
            set_state(user_id, "ADD_NAME", "0")
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù Ø§ÙØ¬Ø¯ÙØ¯:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return True
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "ADD_NAME", str(sid))
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù Ø§ÙØ¬Ø¯ÙØ¯:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return True

    if state and state["state"] == "ADD_NAME":
        if text:
            sid = create_section(int(state["value"]) or None, text)
            clear_state(user_id)
            await update.effective_message.reply_text(
                f"â ØªÙ Ø¥ÙØ´Ø§Ø¡ Ø§ÙÙØ³Ù.\nð <code>{sid}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_kb(),
            )
        return True

    if text == "âï¸ ØªØ¹Ø¯ÙÙ ÙØ³Ù":
        await send_section_list(update, "âï¸ Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:", "RENAME_SELECT")
        return True

    if state and state["state"] == "RENAME_SELECT":
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "RENAME_NAME", str(sid))
            await update.effective_message.reply_text("âï¸ Ø£Ø±Ø³Ù Ø§ÙØ§Ø³Ù Ø§ÙØ¬Ø¯ÙØ¯:")
        return True

    if state and state["state"] == "RENAME_NAME":
        rename_section(int(state["value"]), text)
        clear_state(user_id)
        await update.effective_message.reply_text("â ØªÙ ØªØ¹Ø¯ÙÙ Ø§ÙÙØ³Ù.", reply_markup=admin_kb())
        return True

    if text == "ð Ø­Ø°Ù ÙØ³Ù":
        await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ±Ø§Ø¯ Ø­Ø°ÙÙ:", "DELETE_SELECT")
        return True

    if state and state["state"] == "DELETE_SELECT":
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "DELETE_CONFIRM", str(sid))
            await update.effective_message.reply_text(
                "â ï¸ Ø³ÙØªÙ Ø­Ø°Ù Ø§ÙÙØ³Ù ÙØ¬ÙÙØ¹ ÙØ­ØªÙØ§Ù.\nÙÙ ØªØ¤ÙØ¯Ø",
                reply_markup=kb([["â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù"], ["â Ø¥ÙØºØ§Ø¡"]]),
            )
        return True

    if state and state["state"] == "DELETE_CONFIRM":
        if text == "â Ø¥ÙØºØ§Ø¡":
            await section_editor(update)
            return True
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù":
            delete_section_tree(int(state["value"]))
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙØ­Ø°Ù.", reply_markup=admin_kb()
            )
        return True

    if text == "âï¸ ÙÙÙ ÙØ³Ù":
        await send_section_list(update, "âï¸ Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ±Ø§Ø¯ ÙÙÙÙ:", "MOVE_SOURCE")
        return True

    if state and state["state"] == "MOVE_SOURCE":
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "MOVE_TARGET", str(sid))
            await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙØ£Ø¨ Ø§ÙØ¬Ø¯ÙØ¯:", "MOVE_TARGET")
        return True

    if state and state["state"] == "MOVE_TARGET":
        target = section_by_button(text)
        if target:
            source = int(state["value"])
            ok = move_section(source, target)
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙÙÙÙ." if ok else "â ÙØ§ ÙÙÙÙ ÙÙÙ Ø§ÙÙØ³Ù Ø¥ÙÙ Ø¯Ø§Ø®ÙÙ.",
                reply_markup=admin_kb(),
            )
        return True

    if text == "ð Ø¯ÙØ¬ ÙØ³ÙÙÙ":
        await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØµØ¯Ø±:", "MERGE_SOURCE")
        return True

    if state and state["state"] == "MERGE_SOURCE":
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "MERGE_TARGET", str(sid))
            await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ¯Ù:", "MERGE_TARGET")
        return True

    if state and state["state"] == "MERGE_TARGET":
        target = section_by_button(text)
        if target:
            source = int(state["value"])
            if source == target or target in descendants(source):
                clear_state(user_id)
                await update.effective_message.reply_text(
                    "â ÙØ§ ÙÙÙÙ Ø¯ÙØ¬ ÙØ°Ø§ Ø§ÙÙØ³Ù Ø¨ÙØ°Ø§ Ø§ÙÙØ¯Ù.", reply_markup=admin_kb()
                )
                return True

            conn = db()
            conn.execute("UPDATE sections SET parent_id=? WHERE parent_id=?", (target, source))
            conn.execute("UPDATE contents SET section_id=? WHERE section_id=?", (target, source))
            conn.execute("DELETE FROM favorites WHERE section_id=?", (source,))
            conn.execute("DELETE FROM sections WHERE id=?", (source,))
            conn.commit()
            conn.close()
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙØ¯ÙØ¬.", reply_markup=admin_kb()
            )
        return True

    if text == "â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ©":
        await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:", "CONTENT_SELECT")
        return True

    if state and state["state"] == "CONTENT_SELECT":
        sid = section_by_button(text)
        if sid:
            set_state(user_id, "ADMIN_CONTENT_WAIT", str(sid))
            await update.effective_message.reply_text(
                "ð¨ Ø£Ø±Ø³Ù Ø§ÙØ¢Ù Ø§ÙÙÙÙ/Ø§ÙØµÙØ±Ø©/Ø§ÙÙÙØ¯ÙÙ/Ø§ÙÙØµ ÙÙØªÙ Ø­ÙØ¸Ù Ø¯Ø§Ø®Ù Ø§ÙÙØ³Ù.",
                reply_markup=kb([["â Ø¥ÙØºØ§Ø¡"]]),
            )
        return True

    if text == "ð Ø­Ø°Ù ÙØ´Ø§Ø±ÙØ©":
        await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:", "CONTENT_DELETE_SECTION")
        return True

    if state and state["state"] == "CONTENT_DELETE_SECTION":
        sid = section_by_button(text)
        if sid:
            rows = get_contents(sid)
            if not rows:
                await update.effective_message.reply_text(
                    "ÙØ§ ØªÙØ¬Ø¯ ÙØ´Ø§Ø±ÙØ§Øª.", reply_markup=admin_kb()
                )
                clear_state(user_id)
                return True
            set_state(user_id, "CONTENT_DELETE", str(sid))
            await update.effective_message.reply_text(
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ´Ø§Ø±ÙØ©:",
                reply_markup=kb(
                    [[f"ð {c['title'] or f'ÙØ´Ø§Ø±ÙØ© {c['id']}'}"] for c in rows]
                    + [["â Ø¥ÙØºØ§Ø¡"]]
                ),
            )
        return True

    if state and state["state"] == "CONTENT_DELETE":
        sid = int(state["value"])
        if text.startswith("ð "):
            title = text[2:].strip()
            for c in get_contents(sid):
                if (c["title"] or f"ÙØ´Ø§Ø±ÙØ© {c['id']}") == title:
                    delete_content(c["id"])
                    clear_state(user_id)
                    await update.effective_message.reply_text(
                        "â ØªÙ Ø­Ø°Ù Ø§ÙÙØ´Ø§Ø±ÙØ©.", reply_markup=admin_kb()
                    )
                    return True
        return True

    if text == "ð Ø¹Ø±Ø¶ ÙØ´Ø§Ø±ÙØ§Øª Ø§ÙÙØ³Ù":
        await send_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:", "CONTENT_LIST")
        return True

    if state and state["state"] == "CONTENT_LIST":
        sid = section_by_button(text)
        if sid:
            rows = get_contents(sid)
            if rows:
                msg = "\n".join(
                    f"ð {html.escape(c['title'] or f'ÙØ´Ø§Ø±ÙØ© {c['id']}')} â {c['content_type']}"
                    for c in rows
                )
            else:
                msg = "ÙØ§ ØªÙØ¬Ø¯ ÙØ´Ø§Ø±ÙØ§Øª."
            clear_state(user_id)
            await update.effective_message.reply_text(
                msg, parse_mode=ParseMode.HTML, reply_markup=admin_kb()
            )
        return True

    if text == "â Ø¥ÙØºØ§Ø¡":
        clear_state(user_id)
        await admin_panel(update)
        return True

    return False


# ============================================================
# CONTENT HELPERS
# ============================================================

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
    if message.sticker:
        return "sticker"
    if message.text:
        return "text"
    return "other"


def default_title(message, ctype):
    if message.document and message.document.file_name:
        return message.document.file_name
    if message.caption:
        return message.caption[:80]
    return {
        "photo": "ØµÙØ±Ø©",
        "video": "ÙÙØ¯ÙÙ",
        "audio": "ØµÙØª",
        "voice": "Ø±Ø³Ø§ÙØ© ØµÙØªÙØ©",
        "animation": "ÙØªØ­Ø±Ù",
        "sticker": "ÙÙØµÙ",
        "text": (message.text or "ÙØµ")[:80],
    }.get(ctype, "ÙØ´Ø§Ø±ÙØ©")


# ============================================================
# COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                ref = int(arg[4:])
            except ValueError:
                ref = None

    new_user = add_user(update.effective_user, ref)
    clear_state(update.effective_user.id)

    if new_user and ref and ref != update.effective_user.id:
        try:
            conn = db()
            conn.execute(
                "UPDATE users SET balance=balance+1 WHERE user_id=?",
                (ref,),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Referral reward failed")

    await show_main(
        update,
        "ð <b>Ø£ÙÙØ§Ù Ø¨Ù ÙÙ Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØªØ¹ÙÙÙÙ Ø§ÙØ°ÙÙ</b>\n\n"
        "Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø£Ù Ø§Ø³ØªØ®Ø¯Ù Ø§ÙØ¨Ø­Ø« ÙÙÙØµÙÙ Ø¥ÙÙ Ø§ÙÙØ­Ø§Ø¶Ø±Ø§Øª ÙØ§ÙÙÙÙØ§Øª.",
    )


async def admin_command(update, context):
    if update.effective_user.id == ADMIN_ID:
        await admin_panel(update)
    else:
        await update.effective_message.reply_text("â ØºÙØ± ÙØ³ÙÙØ­.")


# ============================================================
# FLASK WEBHOOK
# ============================================================

@flask_app.get("/")
def health():
    return "Telegram Educational Bot is running", 200


@flask_app.post("/" + WEBHOOK_PATH)
def webhook():
    if telegram_app is None:
        return "Application not ready", 503

    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        return "OK", 200
    except Exception:
        logger.exception("Webhook error")
        return "Bad Request", 400


async def init_telegram():
    global telegram_app

    telegram_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("admin", admin_command))
    telegram_app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, route)
    )

    await telegram_app.initialize()
    await telegram_app.start()

    if WEBHOOK_URL:
        url = WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH
        await telegram_app.bot.set_webhook(url=url, drop_pending_updates=False)
        logger.info("Webhook set to %s", url)


def telegram_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_telegram())
    loop.run_forever()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    init_db()

    t = threading.Thread(target=telegram_thread, daemon=True)
    t.start()

    flask_app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True,
    )
