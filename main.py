# -*- coding: utf-8 -*-
"""
Telegram Educational Bot - Standalone Render version
- Python 3.11+
- python-telegram-bot 21.x
- Flask webhook
- SQLite database
- Dynamic sections / nested sections
- Any Telegram content can be stored (PDF, photo, video, audio, document, text, etc.)
- Admin editor: add / rename / delete / move / merge sections
- Add content by sending or forwarding it to the bot
- Favorites / most visited / ratings / messages
- About & full usage guide
- Per-level Back / Exit buttons
"""

import os
import html
import sqlite3
import logging
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, request

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Put your Telegram numeric admin ID in Render Environment Variables:
# ADMIN_ID=123456789
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")

DB_FILE = os.getenv("DB_FILE", "bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN ØºÙØ± ÙÙØ¬ÙØ¯ ÙÙ Environment Variables")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID ØºÙØ± ÙÙØ¬ÙØ¯ ÙÙ Environment Variables")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("educational-bot")

app = Flask(__name__)
application = None

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
                username TEXT,
                joined_at TEXT,
                last_seen TEXT,
                visits INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(parent_id) REFERENCES sections(id)
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
                created_at TEXT,
                FOREIGN KEY(section_id) REFERENCES sections(id)
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

        conn.commit()

        # Initial structure: only created once.
        cur.execute("SELECT COUNT(*) AS c FROM sections")
        if cur.fetchone()["c"] == 0:
            create_section_db(None, "ð ÙÙØ¯Ø³Ø© ØªÙÙÙØ§Øª Ø§ÙØ­Ø§Ø³ÙØ¨")
        conn.commit()
        conn.close()


def create_section_db(parent_id, name):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM sections WHERE parent_id IS ?",
        (parent_id,),
    )
    order_no = cur.fetchone()["n"]
    cur.execute(
        """INSERT INTO sections(parent_id,name,sort_order,created_at)
           VALUES(?,?,?,?,?)""",
        (parent_id, name, order_no, datetime.utcnow().isoformat()),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def get_section(section_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM sections WHERE id=?", (section_id,)
    ).fetchone()
    conn.close()
    return row


def get_children(parent_id):
    conn = db()
    rows = conn.execute(
        """SELECT * FROM sections
           WHERE parent_id IS ?
           ORDER BY sort_order ASC, id ASC""",
        (parent_id,),
    ).fetchall()
    conn.close()
    return rows


def get_contents(section_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM contents WHERE section_id=? ORDER BY id ASC",
        (section_id,),
    ).fetchall()
    conn.close()
    return rows


def rename_section(section_id, name):
    with db_lock:
        conn = db()
        conn.execute(
            "UPDATE sections SET name=? WHERE id=?",
            (name, section_id),
        )
        conn.commit()
        conn.close()


def delete_section_tree(section_id):
    with db_lock:
        conn = db()
        children = conn.execute(
            "SELECT id FROM sections WHERE parent_id=?",
            (section_id,),
        ).fetchall()

        for child in children:
            delete_section_tree_db(conn, child["id"])

        conn.execute("DELETE FROM contents WHERE section_id=?", (section_id,))
        conn.execute("DELETE FROM favorites WHERE section_id=?", (section_id,))
        conn.execute("DELETE FROM sections WHERE id=?", (section_id,))
        conn.commit()
        conn.close()


def delete_section_tree_db(conn, section_id):
    children = conn.execute(
        "SELECT id FROM sections WHERE parent_id=?", (section_id,)
    ).fetchall()
    for child in children:
        delete_section_tree_db(conn, child["id"])

    conn.execute("DELETE FROM contents WHERE section_id=?", (section_id,))
    conn.execute("DELETE FROM favorites WHERE section_id=?", (section_id,))
    conn.execute("DELETE FROM sections WHERE id=?", (section_id,))


def move_section(section_id, new_parent_id):
    if section_id == new_parent_id:
        return False

    # Prevent moving a section inside one of its own descendants.
    descendant_ids = collect_descendants(section_id)
    if new_parent_id in descendant_ids:
        return False

    with db_lock:
        conn = db()
        conn.execute(
            "UPDATE sections SET parent_id=? WHERE id=?",
            (new_parent_id, section_id),
        )
        conn.commit()
        conn.close()
    return True


def collect_descendants(section_id):
    result = set()
    queue = [section_id]
    while queue:
        current = queue.pop()
        for row in get_children(current):
            result.add(row["id"])
            queue.append(row["id"])
    return result


def merge_sections(source_id, target_id):
    if source_id == target_id:
        return False

    if target_id in collect_descendants(source_id):
        return False

    with db_lock:
        conn = db()

        # Move direct children to target.
        conn.execute(
            "UPDATE sections SET parent_id=? WHERE parent_id=?",
            (target_id, source_id),
        )

        # Move all stored content.
        conn.execute(
            "UPDATE contents SET section_id=? WHERE section_id=?",
            (target_id, source_id),
        )

        conn.execute("DELETE FROM favorites WHERE section_id=?", (source_id,))
        conn.execute("DELETE FROM sections WHERE id=?", (source_id,))

        conn.commit()
        conn.close()

    return True


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


def add_user(tg_user):
    now = datetime.utcnow().isoformat()
    is_new = False

    with db_lock:
        conn = db()
        old = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?",
            (tg_user.id,),
        ).fetchone()

        if old is None:
            is_new = True
            conn.execute(
                """INSERT INTO users
                   (user_id,first_name,username,joined_at,last_seen,visits)
                   VALUES(?,?,?,?,?,1)""",
                (
                    tg_user.id,
                    tg_user.first_name or "",
                    tg_user.username or "",
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """UPDATE users SET first_name=?,username=?,
                   last_seen=?,visits=visits+1 WHERE user_id=?""",
                (
                    tg_user.first_name or "",
                    tg_user.username or "",
                    now,
                    tg_user.id,
                ),
            )

        conn.commit()
        conn.close()

    return is_new


def user_visits(user_id):
    conn = db()
    row = conn.execute(
        "SELECT visits FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row["visits"] if row else 0


def set_state(user_id, state, value=""):
    conn = db()
    conn.execute(
        """INSERT INTO user_state(user_id,state,value)
           VALUES(?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,
           value=excluded.value""",
        (user_id, state, value),
    )
    conn.commit()
    conn.close()


def get_state(user_id):
    conn = db()
    row = conn.execute(
        "SELECT state,value FROM user_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row if row else None


def clear_state(user_id):
    conn = db()
    conn.execute("DELETE FROM user_state WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def is_favorite(user_id, section_id):
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND section_id=?",
        (user_id, section_id),
    ).fetchone()
    conn.close()
    return row is not None


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


def add_rating(user_id, rating, comment=""):
    conn = db()
    conn.execute(
        """INSERT INTO ratings(user_id,rating,comment,created_at)
           VALUES(?,?,?,?)""",
        (user_id, rating, comment, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def add_message(user_id, text):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO messages(user_id,text,created_at)
           VALUES(?,?,?)""",
        (user_id, text, datetime.utcnow().isoformat()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


# ============================================================
# KEYBOARDS
# ============================================================

MAIN_BUTTONS = [
    ["ð Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ¹ÙÙÙÙØ©"],
    ["â­ Ø§ÙÙÙØ¶ÙØ©", "ð¥ Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù"],
    ["ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª", "â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª"],
    ["â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª"],
]

ADMIN_BUTTONS = [
    ["ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù"],
    ["ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª"],
    ["ð ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±"],
    ["ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª"],
    ["ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª ÙØ§ÙØªÙÙÙÙØ§Øª"],
    ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
]


def kb(rows, resize=True):
    return ReplyKeyboardMarkup(rows, resize_keyboard=resize)


def main_keyboard(user_id):
    rows = [row[:] for row in MAIN_BUTTONS]
    if user_id == ADMIN_ID:
        rows.append(["ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©"])
    return kb(rows)


def back_keyboard():
    return kb([
        ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
    ])


def admin_keyboard():
    return kb(ADMIN_BUTTONS)


# ============================================================
# HELPERS
# ============================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            await update.effective_message.reply_text(
                "â ÙØ°Ø§ Ø§ÙÙØ³Ù ÙØ®ØµØµ ÙÙØ¥Ø¯Ø§Ø±Ø© ÙÙØ·.",
                reply_markup=main_keyboard(update.effective_user.id),
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def show_main(update, context, text=None):
    if text is None:
        text = (
            "ð <b>Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØªØ¹ÙÙÙÙ Ø§ÙØ°ÙÙ</b>\n\n"
            "Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ Ø§ÙÙØµÙÙ Ø¥ÙÙÙ ÙÙ ÙÙØ­Ø© Ø§ÙØ£Ø²Ø±Ø§Ø± Ø£Ø¯ÙØ§Ù."
        )
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(update.effective_user.id),
    )


def section_path(section_id):
    parts = []
    current = get_section(section_id)
    while current:
        parts.append(current["name"])
        parent = current["parent_id"]
        current = get_section(parent) if parent else None
    return "  âº  ".join(reversed(parts))


async def show_section(update, context, section_id):
    section = get_section(section_id)
    if not section:
        await show_main(update, context, "â Ø§ÙÙØ³Ù ØºÙØ± ÙÙØ¬ÙØ¯.")
        return

    user_id = update.effective_user.id
    set_state(user_id, "BROWSE", str(section_id))

    children = get_children(section_id)
    contents = get_contents(section_id)

    rows = []
    for child in children:
        rows.append([f"ð {child['name']}"])

    for content in contents:
        title = content["title"] or f"ÙØ´Ø§Ø±ÙØ© {content['id']}"
        rows.append([f"ð {title}"])

    fav_text = "ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©" if is_favorite(user_id, section_id) else "â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©"
    rows.append([fav_text])

    # Every level has its own Back and Exit.
    if section["parent_id"]:
        rows.append(["â¬ï¸ Ø±Ø¬ÙØ¹", "ðª Ø®Ø±ÙØ¬ ÙÙ Ø§ÙÙØ³Ù"])
    else:
        rows.append(["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"])

    await update.effective_message.reply_text(
        f"ð <b>{html.escape(section['name'])}</b>\n\n"
        f"ð {html.escape(section_path(section_id))}\n\n"
        "Ø§Ø®ØªØ± ÙÙ Ø§ÙØ£Ø²Ø±Ø§Ø±:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb(rows),
    )


async def show_content(update, context, content_id):
    conn = db()
    content = conn.execute(
        "SELECT * FROM contents WHERE id=?", (content_id,)
    ).fetchone()
    conn.close()

    if not content:
        await update.effective_message.reply_text(
            "â Ø§ÙÙØ´Ø§Ø±ÙØ© ØºÙØ± ÙÙØ¬ÙØ¯Ø©.",
            reply_markup=back_keyboard(),
        )
        return

    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=content["source_chat_id"],
        message_id=content["source_message_id"],
    )

    section_id = content["section_id"]
    await update.effective_message.reply_text(
        "â¬ï¸ ÙÙØ±Ø¬ÙØ¹ Ø¥ÙÙ Ø§ÙÙØ³ÙØ Ø§Ø³ØªØ®Ø¯Ù Ø§ÙØ²Ø± Ø£Ø¯ÙØ§Ù.",
        reply_markup=kb([
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
            ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
        ]),
    )
    set_state(update.effective_user.id, "CONTENT", str(section_id))


async def notify_new_user(update):
    user = update.effective_user
    username = f"@{user.username}" if user.username else "Ø¨Ø¯ÙÙ ÙØ¹Ø±Ù"
    text = (
        "ð <b>ÙØ³ØªØ®Ø¯Ù Ø¬Ø¯ÙØ¯ Ø¯Ø®Ù Ø§ÙØ¨ÙØª</b>\n\n"
        f"ð¤ Ø§ÙØ§Ø³Ù: {html.escape(user.full_name)}\n"
        f"ð¹ Ø§ÙÙØ¹Ø±Ù: {username}\n"
        f"ð ID: <code>{user.id}</code>"
    )
    try:
        await application.bot.send_message(
            ADMIN_ID, text, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("Could not notify admin")


# ============================================================
# START / MAIN
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_user = add_user(update.effective_user)
    clear_state(update.effective_user.id)

    if new_user:
        await notify_new_user(update)

    await show_main(
        update,
        context,
        "ð <b>Ø£ÙÙØ§Ù Ø¨Ù ÙÙ Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØªØ¹ÙÙÙÙ Ø§ÙØ°ÙÙ</b>\n\n"
        "Ø§Ø®ØªØ± ÙØ§ ØªØ±ÙØ¯ ÙÙ ÙÙØ­Ø© Ø§ÙØ£Ø²Ø±Ø§Ø±.",
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    user_id = update.effective_user.id

    # --------------------------------------------------------
    # Global navigation
    # --------------------------------------------------------
    if text == "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©":
        clear_state(user_id)
        await show_main(update, context)
        return

    if text in ("â¬ï¸ Ø±Ø¬ÙØ¹", "ðª Ø®Ø±ÙØ¬ ÙÙ Ø§ÙÙØ³Ù"):
        state = get_state(user_id)

        if state and state["state"] in ("BROWSE", "CONTENT"):
            try:
                sid = int(state["value"])
            except Exception:
                sid = 0

            section = get_section(sid)
            if section and section["parent_id"]:
                await show_section(update, context, section["parent_id"])
            else:
                await show_main(update, context)
        else:
            await show_main(update, context)
        return

    # --------------------------------------------------------
    # Main sections
    # --------------------------------------------------------
    if text == "ð Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ¹ÙÙÙÙØ©":
        root = get_children(None)
        # The first root is the educational root created above.
        if root:
            await show_section(update, context, root[0]["id"])
        else:
            await show_main(update, context, "ÙØ§ ØªÙØ¬Ø¯ Ø£ÙØ³Ø§Ù Ø­Ø§ÙÙØ§Ù.")
        return

    if text == "â­ Ø§ÙÙÙØ¶ÙØ©":
        conn = db()
        rows = conn.execute(
            """SELECT s.* FROM sections s
               JOIN favorites f ON f.section_id=s.id
               WHERE f.user_id=?
               ORDER BY s.name""",
            (user_id,),
        ).fetchall()
        conn.close()

        if not rows:
            await update.effective_message.reply_text(
                "â­ ÙØ§ ØªÙØ¬Ø¯ Ø£ÙØ³Ø§Ù ÙÙ Ø§ÙÙÙØ¶ÙØ©.",
                reply_markup=main_keyboard(user_id),
            )
            return

        await update.effective_message.reply_text(
            "â­ <b>Ø§ÙÙÙØ¶ÙØ©</b>\n\nØ§Ø®ØªØ± Ø§ÙÙØ³Ù:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb(
                [[f"ð {r['name']}"] for r in rows]
                + [["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]
            ),
        )
        set_state(user_id, "FAVORITES", "")
        return

    if text == "ð¥ Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù":
        conn = db()
        rows = conn.execute(
            """SELECT * FROM users
               ORDER BY visits DESC LIMIT 10"""
        ).fetchall()
        conn.close()

        # Show the user's own visits plus general bot usage.
        visits = user_visits(user_id)
        await update.effective_message.reply_text(
            "ð¥ <b>Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù</b>\n\n"
            f"ð Ø¹Ø¯Ø¯ ÙØ±Ø§Øª Ø¯Ø®ÙÙÙ ÙÙØ¨ÙØª: <b>{visits}</b>\n\n"
            "ÙØ°Ø§ Ø§ÙÙØ³Ù ÙØ®ØµØµ ÙØªØ¬ÙÙØ¹ Ø¥Ø­ØµØ§Ø¦ÙØ§Øª Ø§ÙØ§Ø³ØªØ®Ø¯Ø§Ù.\n"
            "Ø³ÙØªÙ ØªÙØ³ÙØ¹Ù ÙØ§Ø­ÙØ§Ù ÙÙØ¹Ø±Ø¶ Ø£ÙØ«Ø± Ø§ÙØ£ÙØ³Ø§Ù Ø²ÙØ§Ø±Ø©Ù Ø¨Ø´ÙÙ ÙØ¨Ø§Ø´Ø±.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )
        return

    if text == "â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª":
        await update.effective_message.reply_text(
            "â­ <b>ÙÙÙÙ Ø§ÙØ¨ÙØª</b>\n\n"
            "Ø§Ø®ØªØ± ØªÙÙÙÙÙ:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([
                ["â­", "â­â­"],
                ["â­â­â­", "â­â­â­â­"],
                ["â­â­â­â­â­"],
                ["â¬ï¸ Ø±Ø¬ÙØ¹"],
            ]),
        )
        set_state(user_id, "RATING", "")
        return

    if text == "ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª":
        await update.effective_message.reply_text(
            "ð¬ <b>Ø§ÙÙØ±Ø§Ø³ÙØ§Øª</b>\n\n"
            "Ø§ÙØªØ¨ Ø±Ø³Ø§ÙØªÙ Ø£Ù ÙÙØ§Ø­Ø¸ØªÙØ ÙØ³ØªØµÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )
        set_state(user_id, "MESSAGE", "")
        return

    if text == "â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª":
        await update.effective_message.reply_text(
            "â¹ï¸ <b>Ø­ÙÙ Ø§ÙØ¨ÙØª ÙØ·Ø±ÙÙØ© Ø§ÙØ§Ø³ØªØ®Ø¯Ø§Ù</b>\n\n"
            "ð <b>Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ¹ÙÙÙÙØ©:</b>\n"
            "ØªØ¯Ø®Ù Ø¥ÙÙ Ø§ÙÙØ±Ø­ÙØ© Ø«Ù Ø§ÙÙÙØ±Ø³ Ø«Ù Ø§ÙÙØ§Ø¯Ø© Ø«Ù Ø§ÙÙØ­Ø§Ø¶Ø±Ø©.\n\n"
            "ð <b>Ø§ÙÙØ´Ø§Ø±ÙØ§Øª:</b>\n"
            "Ø§ÙÙØ­Ø§Ø¶Ø±Ø© ÙÙÙÙ Ø£Ù ØªÙÙÙ PDF Ø£Ù ØµÙØ±Ø© Ø£Ù ÙÙØ¯ÙÙ Ø£Ù ÙÙÙ Ø£Ù Ø±Ø³Ø§ÙØ© ÙØµÙØ© "
            "Ø£Ù Ø£Ù ÙØ­ØªÙÙ ÙØ³ÙØ­ Ø§ÙØ¨ÙØª Ø¨ØªØ®Ø²ÙÙÙ.\n\n"
            "â­ <b>Ø§ÙÙÙØ¶ÙØ©:</b>\n"
            "Ø£Ø¶Ù Ø£Ù ÙØ³Ù ÙÙÙÙØ¶ÙØ© ÙÙÙØµÙÙ Ø¥ÙÙÙ Ø¨Ø³Ø±Ø¹Ø©.\n\n"
            "ð¬ <b>Ø§ÙÙØ±Ø§Ø³ÙØ§Øª:</b>\n"
            "Ø£Ø±Ø³Ù ÙÙØ§Ø­Ø¸Ø© Ø£Ù Ø§Ø³ØªÙØ³Ø§Ø±Ø§Ù ÙÙØ¥Ø¯Ø§Ø±Ø©.\n\n"
            "â­ <b>Ø§ÙØªÙÙÙÙ:</b>\n"
            "Ø§Ø®ØªØ± Ø¹Ø¯Ø¯ Ø§ÙÙØ¬ÙÙ Ø«Ù Ø§ÙØªØ¨ ÙÙØ§Ø­Ø¸ØªÙ Ø¥Ù Ø£Ø±Ø¯Øª.\n\n"
            "ð <b>Ø§ÙØ±Ø¬ÙØ¹ ÙØ§ÙØ®Ø±ÙØ¬:</b>\n"
            "ÙÙ ÙØ³ØªÙÙ ÙÙ Ø±Ø¬ÙØ¹ Ø®Ø§Øµ Ø¨ÙØ ÙØ§ÙØ®Ø±ÙØ¬ ÙØ¹ÙØ¯Ù Ø¥ÙÙ Ø§ÙÙØ³ØªÙÙ Ø§ÙØ³Ø§Ø¨Ù Ø£Ù Ø§ÙØ±Ø¦ÙØ³ÙØ©.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )
        return

    if text == "ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©" and user_id == ADMIN_ID:
        clear_state(user_id)
        await update.effective_message.reply_text(
            "ð <b>ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n\n"
            "Ø§Ø®ØªØ± Ø£Ø¯Ø§Ø©:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    # --------------------------------------------------------
    # Rating state
    # --------------------------------------------------------
    state = get_state(user_id)

    if state and state["state"] == "RATING":
        if text.startswith("â­"):
            rating = text.count("â­")
            set_state(user_id, "RATING_COMMENT", str(rating))
            await update.effective_message.reply_text(
                f"â ØªÙ Ø§Ø®ØªÙØ§Ø± {rating} ÙÙ 5.\n\n"
                "Ø§ÙØªØ¨ ÙÙØ§Ø­Ø¸ØªÙØ Ø£Ù Ø§ÙØªØ¨ Â«ØªØ®Ø·ÙÂ».",
                reply_markup=kb([["ØªØ®Ø·Ù"], ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"]]),
            )
            return

    if state and state["state"] == "RATING_COMMENT":
        rating = int(state["value"])
        comment = "" if text == "ØªØ®Ø·Ù" else text
        add_rating(user_id, rating, comment)
        clear_state(user_id)

        await context.bot.send_message(
            ADMIN_ID,
            "â­ <b>ØªÙÙÙÙ Ø¬Ø¯ÙØ¯</b>\n\n"
            f"ð¤ {html.escape(update.effective_user.full_name)}\n"
            f"ð <code>{user_id}</code>\n"
            f"â­ Ø§ÙØªÙÙÙÙ: <b>{rating}/5</b>\n"
            f"ð Ø§ÙÙÙØ§Ø­Ø¸Ø©: {html.escape(comment or 'Ø¨Ø¯ÙÙ ÙÙØ§Ø­Ø¸Ø©')}",
            parse_mode=ParseMode.HTML,
        )

        await update.effective_message.reply_text(
            "â Ø´ÙØ±Ø§Ù ÙØªÙÙÙÙÙ â¤ï¸",
            reply_markup=main_keyboard(user_id),
        )
        return

    # --------------------------------------------------------
    # User message state
    # --------------------------------------------------------
    if state and state["state"] == "MESSAGE":
        if text:
            mid = add_message(user_id, text)
            clear_state(user_id)

            await context.bot.send_message(
                ADMIN_ID,
                "ð¬ <b>Ø±Ø³Ø§ÙØ© Ø¬Ø¯ÙØ¯Ø©</b>\n\n"
                f"Ø±ÙÙ Ø§ÙØ±Ø³Ø§ÙØ©: <code>{mid}</code>\n"
                f"ð¤ {html.escape(update.effective_user.full_name)}\n"
                f"ð <code>{user_id}</code>\n\n"
                f"ð¬ {html.escape(text)}",
                parse_mode=ParseMode.HTML,
            )

            await update.effective_message.reply_text(
                "â ÙØµÙØª Ø±Ø³Ø§ÙØªÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.",
                reply_markup=main_keyboard(user_id),
            )
            return

    # --------------------------------------------------------
    # Browse dynamic buttons
    # --------------------------------------------------------
    if state and state["state"] in ("BROWSE", "FAVORITES"):
        if text.startswith("ð "):
            name = text[2:].strip()

            if state["state"] == "FAVORITES":
                conn = db()
                row = conn.execute(
                    "SELECT * FROM sections WHERE name=? ORDER BY id DESC LIMIT 1",
                    (name,),
                ).fetchone()
                conn.close()
                if row:
                    await show_section(update, context, row["id"])
                    return

            current_id = int(state["value"]) if state["value"] else None
            candidates = get_children(current_id)

            for child in candidates:
                if child["name"] == name:
                    await show_section(update, context, child["id"])
                    return

        if text.startswith("ð "):
            title = text[2:].strip()
            current_id = int(state["value"])
            for content in get_contents(current_id):
                if (content["title"] or f"ÙØ´Ø§Ø±ÙØ© {content['id']}") == title:
                    await show_content(update, context, content["id"])
                    return

        if text in ("â­ Ø¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©", "ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©"):
            current_id = int(state["value"])
            enabled = toggle_favorite(user_id, current_id)
            await update.effective_message.reply_text(
                "â­ ØªÙØª Ø§ÙØ¥Ø¶Ø§ÙØ© Ø¥ÙÙ Ø§ÙÙÙØ¶ÙØ©." if enabled else "ð ØªÙØª Ø§ÙØ¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©.",
            )
            await show_section(update, context, current_id)
            return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------
    if user_id == ADMIN_ID:
        await admin_router(update, context, text)
        return

    # Unknown
    await update.effective_message.reply_text(
        "Ø§Ø³ØªØ®Ø¯Ù Ø£Ø²Ø±Ø§Ø± Ø§ÙØ¨ÙØª ÙÙ ÙÙØ­Ø© Ø§ÙÙÙØ§ØªÙØ­.",
        reply_markup=main_keyboard(user_id),
    )


# ============================================================
# ADMIN EDITOR
# ============================================================

async def admin_router(update, context, text):
    user_id = update.effective_user.id
    state = get_state(user_id)

    if text == "ð ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±":
        await update.effective_message.reply_text(
            "ð <b>ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±</b>\n\n"
            "Ø§ÙØ£ÙØ³Ø§Ù ÙÙØ³ÙØ§ ÙÙ Ø§ÙØªÙ ØªØ¸ÙØ± ÙØ£Ø²Ø±Ø§Ø± ØªÙÙØ§Ø¦ÙØ§Ù.\n"
            "ÙÙÙÙÙ Ø§ÙØªØ­ÙÙ Ø¨Ø§ÙØ§Ø³Ù ÙØ§ÙØªØ±ØªÙØ¨ ÙØ§ÙØ¨ÙÙØ© ÙÙ ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù.\n\n"
            "Ø§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ©:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([
                ["ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù"],
                ["â¬ï¸ Ø±Ø¬ÙØ¹"],
                ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
            ]),
        )
        return

    if text == "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª":
        conn = db()
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        contents = conn.execute("SELECT COUNT(*) c FROM contents").fetchone()["c"]
        sections = conn.execute("SELECT COUNT(*) c FROM sections").fetchone()["c"]
        ratings = conn.execute("SELECT COUNT(*) c FROM ratings").fetchone()["c"]
        messages = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        conn.close()

        await update.effective_message.reply_text(
            "ð <b>Ø¥Ø­ØµØ§Ø¦ÙØ§Øª Ø§ÙØ¨ÙØª</b>\n\n"
            f"ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ: <b>{users}</b>\n"
            f"ð Ø§ÙØ£ÙØ³Ø§Ù: <b>{sections}</b>\n"
            f"ð¨ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª: <b>{contents}</b>\n"
            f"â­ Ø§ÙØªÙÙÙÙØ§Øª: <b>{ratings}</b>\n"
            f"ð¬ Ø§ÙØ±Ø³Ø§Ø¦Ù: <b>{messages}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    if text == "ð¬ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª ÙØ§ÙØªÙÙÙÙØ§Øª":
        conn = db()
        msgs = conn.execute(
            "SELECT * FROM messages ORDER BY id DESC LIMIT 10"
        ).fetchall()
        ratings = conn.execute(
            "SELECT * FROM ratings ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()

        out = ["ð¬ <b>Ø¢Ø®Ø± Ø§ÙÙØ±Ø§Ø³ÙØ§Øª ÙØ§ÙØªÙÙÙÙØ§Øª</b>\n"]

        if msgs:
            out.append("ð¬ <b>Ø§ÙÙØ±Ø§Ø³ÙØ§Øª:</b>")
            for m in msgs:
                out.append(
                    f"#{m['id']} â ID <code>{m['user_id']}</code>\n"
                    f"{html.escape(m['text'][:300])}"
                )
        else:
            out.append("ð¬ ÙØ§ ØªÙØ¬Ø¯ ÙØ±Ø§Ø³ÙØ§Øª.")

        if ratings:
            out.append("\nâ­ <b>Ø§ÙØªÙÙÙÙØ§Øª:</b>")
            for r in ratings:
                out.append(
                    f"#{r['id']} â ID <code>{r['user_id']}</code> â "
                    f"{r['rating']}/5\n"
                    f"{html.escape((r['comment'] or '')[:300])}"
                )
        else:
            out.append("â­ ÙØ§ ØªÙØ¬Ø¯ ØªÙÙÙÙØ§Øª.")

        await update.effective_message.reply_text(
            "\n".join(out),
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    if text == "ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù":
        clear_state(user_id)
        await update.effective_message.reply_text(
            "ð§© <b>ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù</b>\n\n"
            "Ø§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ©:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([
                ["â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù", "âï¸ ØªØ¹Ø¯ÙÙ ÙØ³Ù"],
                ["ð Ø­Ø°Ù ÙØ³Ù", "âï¸ ÙÙÙ ÙØ³Ù"],
                ["ð Ø¯ÙØ¬ ÙØ³ÙÙÙ"],
                ["â¬ï¸ Ø±Ø¬ÙØ¹"],
            ]),
        )
        set_state(user_id, "ADMIN_SECTION_MENU", "")
        return

    if text == "ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª":
        await admin_content_editor(update, context)
        return

    # ---------------- Section editor ----------------

    if text == "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù":
        set_state(user_id, "ADMIN_ADD_PARENT", "")
        roots = get_children(None)
        await update.effective_message.reply_text(
            "â Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ£Ø¨.\n"
            "ÙØ¥ÙØ´Ø§Ø¡ ÙØ³Ù Ø±Ø¦ÙØ³Ù Ø§Ø®ØªØ± Â«Ø±Ø¦ÙØ³ÙÂ».",
            reply_markup=kb(
                [["ð  Ø±Ø¦ÙØ³Ù"]]
                + [[f"ð {r['name']}"] for r in roots]
                + [["â Ø¥ÙØºØ§Ø¡"]]
            ),
        )
        return

    if state and state["state"] == "ADMIN_ADD_PARENT":
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return

        if text == "ð  Ø±Ø¦ÙØ³Ù":
            set_state(user_id, "ADMIN_ADD_NAME", "0")
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù Ø§ÙØ¬Ø¯ÙØ¯:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        if text.startswith("ð "):
            name = text[2:].strip()
            roots = get_children(None)
            for r in roots:
                if r["name"] == name:
                    set_state(user_id, "ADMIN_ADD_NAME", str(r["id"]))
                    await update.effective_message.reply_text(
                        f"âï¸ Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù Ø¯Ø§Ø®Ù Â«{name}Â»:",
                        reply_markup=ReplyKeyboardRemove(),
                    )
                    return

    if state and state["state"] == "ADMIN_ADD_NAME":
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return

        parent_id = int(state["value"]) or None
        sid = create_section_db(parent_id, text)
        clear_state(user_id)

        await update.effective_message.reply_text(
            f"â ØªÙ Ø¥ÙØ´Ø§Ø¡ Ø§ÙÙØ³Ù:\n\nð <b>{html.escape(text)}</b>\n"
            f"ð ID: <code>{sid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([
                ["ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù"],
                ["ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª"],
                ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
            ]),
        )
        return

    if text == "âï¸ ØªØ¹Ø¯ÙÙ ÙØ³Ù":
        set_state(user_id, "ADMIN_RENAME_SELECT", "")
        await send_admin_section_list(
            update,
            "âï¸ Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ ØªØ¹Ø¯ÙÙ Ø§Ø³ÙÙ:"
        )
        return

    if state and state["state"] == "ADMIN_RENAME_SELECT":
        sid = section_from_button(text)
        if sid:
            set_state(user_id, "ADMIN_RENAME_NAME", str(sid))
            await update.effective_message.reply_text(
                "âï¸ Ø£Ø±Ø³Ù Ø§ÙØ§Ø³Ù Ø§ÙØ¬Ø¯ÙØ¯:",
                reply_markup=ReplyKeyboardMarkup(
                    [["â Ø¥ÙØºØ§Ø¡"]],
                    resize_keyboard=True,
                ),
            )
            return

    if state and state["state"] == "ADMIN_RENAME_NAME":
        sid = int(state["value"])
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return
        rename_section(sid, text)
        clear_state(user_id)
        await update.effective_message.reply_text(
            "â ØªÙ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙÙØ³Ù.",
            reply_markup=kb([
                ["ð§© ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù"],
                ["ð¨ ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª"],
                ["ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"],
            ]),
        )
        return

    if text == "ð Ø­Ø°Ù ÙØ³Ù":
        set_state(user_id, "ADMIN_DELETE_SELECT", "")
        await send_admin_section_list(
            update,
            "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ±Ø§Ø¯ Ø­Ø°ÙÙ:"
        )
        return

    if state and state["state"] == "ADMIN_DELETE_SELECT":
        sid = section_from_button(text)
        if sid:
            section = get_section(sid)
            set_state(user_id, "ADMIN_DELETE_CONFIRM", str(sid))
            await update.effective_message.reply_text(
                "â ï¸ <b>ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù</b>\n\n"
                f"Ø³ÙØªÙ Ø­Ø°Ù Ø§ÙÙØ³Ù Â«{html.escape(section['name'])}Â» "
                "ÙÙÙ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙÙØ´Ø§Ø±ÙØ§Øª Ø§ÙÙÙØ¬ÙØ¯Ø© Ø¯Ø§Ø®ÙÙ.\n\n"
                "ÙÙ Ø£ÙØª ÙØªØ£ÙØ¯Ø",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([
                    ["â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù"],
                    ["â Ø¥ÙØºØ§Ø¡"],
                ]),
            )
            return

    if state and state["state"] == "ADMIN_DELETE_CONFIRM":
        sid = int(state["value"])
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù":
            delete_section_tree(sid)
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙØ­Ø°Ù Ø¨ÙØ¬Ø§Ø­.",
                reply_markup=admin_keyboard(),
            )
            return

    if text == "âï¸ ÙÙÙ ÙØ³Ù":
        set_state(user_id, "ADMIN_MOVE_SOURCE", "")
        await send_admin_section_list(update, "âï¸ Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ±Ø§Ø¯ ÙÙÙÙ:")
        return

    if state and state["state"] == "ADMIN_MOVE_SOURCE":
        sid = section_from_button(text)
        if sid:
            set_state(user_id, "ADMIN_MOVE_TARGET", str(sid))
            await send_admin_section_list(
                update,
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ£Ø¨ Ø§ÙØ¬Ø¯ÙØ¯:"
            )
            return

    if state and state["state"] == "ADMIN_MOVE_TARGET":
        target = section_from_button(text)
        source = int(state["value"])
        if target:
            set_state(
                user_id,
                "ADMIN_MOVE_CONFIRM",
                f"{source}|{target}",
            )
            s = get_section(source)
            t = get_section(target)
            await update.effective_message.reply_text(
                "â ï¸ <b>ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ</b>\n\n"
                f"ÙÙ: <b>{html.escape(s['name'])}</b>\n"
                f"Ø¥ÙÙ: <b>{html.escape(t['name'])}</b>\n\n"
                "ØªØ£ÙÙØ¯Ø",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([
                    ["â ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ"],
                    ["â Ø¥ÙØºØ§Ø¡"],
                ]),
            )
            return

    if state and state["state"] == "ADMIN_MOVE_CONFIRM":
        source, target = map(int, state["value"].split("|"))
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ":
            ok = move_section(source, target)
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ ÙÙÙ Ø§ÙÙØ³Ù." if ok else "â ØªØ¹Ø°Ø± ÙÙÙ Ø§ÙÙØ³Ù.",
                reply_markup=admin_keyboard(),
            )
            return

    if text == "ð Ø¯ÙØ¬ ÙØ³ÙÙÙ":
        set_state(user_id, "ADMIN_MERGE_SOURCE", "")
        await send_admin_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØµØ¯Ø±:")
        return

    if state and state["state"] == "ADMIN_MERGE_SOURCE":
        source = section_from_button(text)
        if source:
            set_state(user_id, "ADMIN_MERGE_TARGET", str(source))
            await send_admin_section_list(update, "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙÙØ¯Ù:")
            return

    if state and state["state"] == "ADMIN_MERGE_TARGET":
        target = section_from_button(text)
        source = int(state["value"])
        if target:
            set_state(
                user_id,
                "ADMIN_MERGE_CONFIRM",
                f"{source}|{target}",
            )
            s = get_section(source)
            t = get_section(target)
            await update.effective_message.reply_text(
                "â ï¸ <b>ØªØ£ÙÙØ¯ Ø§ÙØ¯ÙØ¬</b>\n\n"
                f"Ø§ÙÙØµØ¯Ø±: <b>{html.escape(s['name'])}</b>\n"
                f"Ø§ÙÙØ¯Ù: <b>{html.escape(t['name'])}</b>\n\n"
                "Ø³ÙØªÙ ÙÙÙ ÙØ­ØªÙÙ Ø§ÙÙØµØ¯Ø± ÙØ£ÙØ³Ø§ÙÙ Ø¥ÙÙ Ø§ÙÙØ¯Ù Ø«Ù Ø­Ø°Ù Ø§ÙÙØµØ¯Ø±.\n\n"
                "ÙÙ ØªØ±ÙØ¯ Ø§ÙÙØªØ§Ø¨Ø¹Ø©Ø",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([
                    ["â ØªØ£ÙÙØ¯ Ø§ÙØ¯ÙØ¬"],
                    ["â Ø¥ÙØºØ§Ø¡"],
                ]),
            )
            return

    if state and state["state"] == "ADMIN_MERGE_CONFIRM":
        source, target = map(int, state["value"].split("|"))
        if text == "â Ø¥ÙØºØ§Ø¡":
            await admin_section_menu(update)
            return
        if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ¯ÙØ¬":
            ok = merge_sections(source, target)
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø¯ÙØ¬ Ø§ÙÙØ³ÙÙÙ." if ok else "â ØªØ¹Ø°Ø± Ø§ÙØ¯ÙØ¬.",
                reply_markup=admin_keyboard(),
            )
            return

    # Admin content addition state
    if state and state["state"] == "ADMIN_CONTENT_SELECT":
        sid = section_from_button(text)
        if sid:
            set_state(user_id, "ADMIN_CONTENT_WAIT", str(sid))
            await update.effective_message.reply_text(
                "ð¨ Ø§ÙØ¢Ù Ø£Ø±Ø³Ù Ø£Ù Ø£Ø¹Ø¯ ØªÙØ¬ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ© Ø¥ÙÙ Ø§ÙØ¨ÙØª.\n\n"
                "ÙÙÙÙ Ø£Ù ØªÙÙÙ:\n"
                "ð PDF / ÙÙÙ\n"
                "ð¼ ØµÙØ±Ø©\n"
                "ð¥ ÙÙØ¯ÙÙ\n"
                "ðµ ØµÙØª\n"
                "ð ÙØµ\n"
                "ÙØ£Ù ÙÙØ¹ Ø±Ø³Ø§ÙØ© ÙØ¯Ø¹ÙÙ ØªÙÙÙØ¬Ø±Ø§Ù.\n\n"
                "Ø¨Ø¹Ø¯ Ø§ÙØ¥Ø±Ø³Ø§Ù Ø³ÙØªÙ ØªØ®Ø²ÙÙÙØ§ Ø¯Ø§Ø®Ù Ø§ÙÙØ³Ù ØªÙÙØ§Ø¦ÙØ§Ù.",
                reply_markup=kb([["â Ø¥ÙØºØ§Ø¡"]]),
            )
            return

    if state and state["state"] == "ADMIN_CONTENT_TITLE":
        # The title is optional and is handled in message_capture.
        return

    if text == "â Ø¥ÙØºØ§Ø¡":
        clear_state(user_id)
        await update.effective_message.reply_text(
            "â ØªÙ Ø¥ÙØºØ§Ø¡ Ø§ÙØ¹ÙÙÙØ©.",
            reply_markup=admin_keyboard(),
        )
        return


async def admin_section_menu(update):
    clear_state(update.effective_user.id)
    await update.effective_message.reply_text(
        "ð§© <b>ÙØ­Ø±Ø± Ø§ÙØ£ÙØ³Ø§Ù</b>\n\nØ§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ©:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([
            ["â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù", "âï¸ ØªØ¹Ø¯ÙÙ ÙØ³Ù"],
            ["ð Ø­Ø°Ù ÙØ³Ù", "âï¸ ÙÙÙ ÙØ³Ù"],
            ["ð Ø¯ÙØ¬ ÙØ³ÙÙÙ"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )


async def send_admin_section_list(update, title):
    rows = []
    conn = db()
    sections = conn.execute(
        "SELECT * FROM sections ORDER BY parent_id, sort_order, id"
    ).fetchall()
    conn.close()

    for s in sections:
        rows.append([f"ð {s['name']}"])
    rows.append(["â Ø¥ÙØºØ§Ø¡"])

    await update.effective_message.reply_text(
        title,
        reply_markup=kb(rows),
    )


def section_from_button(text):
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


async def admin_content_editor(update, context):
    await update.effective_message.reply_text(
        "ð¨ <b>ÙØ­Ø±Ø± Ø§ÙÙØ´Ø§Ø±ÙØ§Øª</b>\n\n"
        "Ø§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ©:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([
            ["â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ©"],
            ["ð Ø­Ø°Ù ÙØ´Ø§Ø±ÙØ©"],
            ["ð Ø¹Ø±Ø¶ ÙØ´Ø§Ø±ÙØ§Øª Ø§ÙÙØ³Ù"],
            ["â¬ï¸ Ø±Ø¬ÙØ¹"],
        ]),
    )
    set_state(update.effective_user.id, "ADMIN_CONTENT_MENU", "")


# ============================================================
# MESSAGE CAPTURE
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


def default_title(message, content_type):
    if message.document and message.document.file_name:
        return message.document.file_name
    if message.caption:
        return message.caption[:80]
    if content_type == "photo":
        return "ØµÙØ±Ø©"
    if content_type == "video":
        return "ÙÙØ¯ÙÙ"
    if content_type == "audio":
        return "ØµÙØª"
    if content_type == "voice":
        return "Ø±Ø³Ø§ÙØ© ØµÙØªÙØ©"
    if content_type == "animation":
        return "ÙØªØ­Ø±Ù"
    if content_type == "sticker":
        return "ÙÙØµÙ"
    if content_type == "text":
        return (message.text or "ÙØµ")[:80]
    return "ÙØ´Ø§Ø±ÙØ©"


async def message_capture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return

    user_id = update.effective_user.id
    add_user(update.effective_user)

    state = get_state(user_id)

    # Admin content receiving: the next arbitrary message is stored.
    if user_id == ADMIN_ID and state and state["state"] == "ADMIN_CONTENT_WAIT":
        if update.effective_message.text == "â Ø¥ÙØºØ§Ø¡":
            clear_state(user_id)
            await update.effective_message.reply_text(
                "â ØªÙ Ø§ÙØ¥ÙØºØ§Ø¡.",
                reply_markup=admin_keyboard(),
            )
            return

        section_id = int(state["value"])
        msg = update.effective_message
        ctype = detect_content_type(msg)
        title = default_title(msg, ctype)

        cid = add_content(
            section_id,
            update.effective_chat.id,
            msg.message_id,
            ctype,
            title,
        )

        clear_state(user_id)

        await update.effective_message.reply_text(
            "â <b>ØªÙ Ø­ÙØ¸ Ø§ÙÙØ´Ø§Ø±ÙØ©</b>\n\n"
            f"ð Ø§ÙÙØ³Ù: <b>{html.escape(get_section(section_id)['name'])}</b>\n"
            f"ð Ø§ÙØ¹ÙÙØ§Ù: <b>{html.escape(title)}</b>\n"
            f"ð¹ Ø§ÙÙÙØ¹: <b>{ctype}</b>\n"
            f"ð Ø§ÙÙØ´Ø§Ø±ÙØ©: <code>{cid}</code>\n\n"
            "ÙÙÙÙ ÙÙÙØ³ØªØ®Ø¯Ù Ø§ÙØ¢Ù Ø§ÙØ¶ØºØ· Ø¹ÙÙ Ø§Ø³ÙÙØ§ ÙÙØªÙ Ø¥Ø±Ø³Ø§Ù Ø§ÙÙØ­ØªÙÙ ÙÙØ³Ù.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    # Normal text is routed through menu_handler.
    await menu_handler(update, context)


# ============================================================
# ADMIN CONTENT COMMANDS VIA MENU
# ============================================================

async def admin_command_router(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await admin_content_editor(update, context)


# Patch content editor choices into menu handler through a small
# wrapper that runs before the generic admin router.
_original_menu_handler = menu_handler


async def enhanced_menu_handler(update, context):
    text = (update.effective_message.text or "").strip()
    user_id = update.effective_user.id
    state = get_state(user_id)

    # Admin content editor actions.
    if user_id == ADMIN_ID:
        if text == "â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ©":
            set_state(user_id, "ADMIN_CONTENT_SELECT", "")
            await send_admin_section_list(
                update,
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù Ø³ØªÙØ­ÙØ¸ Ø¯Ø§Ø®ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ©:",
            )
            return

        if text == "ð Ø­Ø°Ù ÙØ´Ø§Ø±ÙØ©":
            set_state(user_id, "ADMIN_CONTENT_DELETE_SECTION", "")
            await send_admin_section_list(
                update,
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ­ØªÙÙ ÙØ´Ø§Ø±ÙØªÙ Ø¹ÙÙ Ø§ÙØ­Ø°Ù:",
            )
            return

        if state and state["state"] == "ADMIN_CONTENT_DELETE_SECTION":
            sid = section_from_button(text)
            if sid:
                contents = get_contents(sid)
                if not contents:
                    await update.effective_message.reply_text(
                        "ÙØ§ ØªÙØ¬Ø¯ ÙØ´Ø§Ø±ÙØ§Øª Ø¯Ø§Ø®Ù ÙØ°Ø§ Ø§ÙÙØ³Ù.",
                        reply_markup=admin_keyboard(),
                    )
                    return
                set_state(user_id, "ADMIN_CONTENT_DELETE_SELECT", str(sid))
                await update.effective_message.reply_text(
                    "ð Ø§Ø®ØªØ± Ø§ÙÙØ´Ø§Ø±ÙØ©:",
                    reply_markup=kb([
                        [f"ð {c['title'] or f'ÙØ´Ø§Ø±ÙØ© {c['id']}'}"]
                        for c in contents
                    ] + [["â Ø¥ÙØºØ§Ø¡"]]),
                )
                return

        if state and state["state"] == "ADMIN_CONTENT_DELETE_SELECT":
            sid = int(state["value"])
            if text.startswith("ð "):
                title = text[2:].strip()
                for c in get_contents(sid):
                    if (c["title"] or f"ÙØ´Ø§Ø±ÙØ© {c['id']}") == title:
                        set_state(
                            user_id,
                            "ADMIN_CONTENT_DELETE_CONFIRM",
                            str(c["id"]),
                        )
                        await update.effective_message.reply_text(
                            "â ï¸ ØªØ£ÙÙØ¯ Ø­Ø°Ù Ø§ÙÙØ´Ø§Ø±ÙØ©Ø",
                            reply_markup=kb([
                                ["â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù"],
                                ["â Ø¥ÙØºØ§Ø¡"],
                            ]),
                        )
                        return

        if state and state["state"] == "ADMIN_CONTENT_DELETE_CONFIRM":
            cid = int(state["value"])
            if text == "â Ø¥ÙØºØ§Ø¡":
                clear_state(user_id)
                await update.effective_message.reply_text(
                    "â ØªÙ Ø§ÙØ¥ÙØºØ§Ø¡.",
                    reply_markup=admin_keyboard(),
                )
                return
            if text == "â ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù":
                delete_content(cid)
                clear_state(user_id)
                await update.effective_message.reply_text(
                    "â ØªÙ Ø­Ø°Ù Ø§ÙÙØ´Ø§Ø±ÙØ©.",
                    reply_markup=admin_keyboard(),
                )
                return

        if text == "ð Ø¹Ø±Ø¶ ÙØ´Ø§Ø±ÙØ§Øª Ø§ÙÙØ³Ù":
            set_state(user_id, "ADMIN_CONTENT_LIST_SECTION", "")
            await send_admin_section_list(
                update,
                "ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:",
            )
            return

        if state and state["state"] == "ADMIN_CONTENT_LIST_SECTION":
            sid = section_from_button(text)
            if sid:
                contents = get_contents(sid)
                if not contents:
                    msg = "ÙØ§ ØªÙØ¬Ø¯ ÙØ´Ø§Ø±ÙØ§Øª."
                else:
                    lines = [
                        f"ð {c['title'] or f'ÙØ´Ø§Ø±ÙØ© {c['id']}'} â {c['content_type']}"
                        for c in contents
                    ]
                    msg = "\n".join(lines)

                await update.effective_message.reply_text(
                    f"ð <b>{html.escape(get_section(sid)['name'])}</b>\n\n"
                    + msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin_keyboard(),
                )
                clear_state(user_id)
                return

    await _original_menu_handler(update, context)


# ============================================================
# FLASK / WEBHOOK
# ============================================================

@app.get("/")
def health():
    return "Telegram bot is running", 200


@app.post(f"/{WEBHOOK_PATH}")
def telegram_webhook():
    global application

    if application is None:
        return "Application not ready", 503

    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put_nowait(update)
        return "OK", 200
    except Exception:
        logger.exception("Webhook update error")
        return "Bad Request", 400


async def post_init(app_obj):
    global application
    application = app_obj

    if WEBHOOK_URL:
        full_url = WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH
        await app_obj.bot.set_webhook(url=full_url)
        logger.info("Webhook set: %s", full_url)


async def post_shutdown(app_obj):
    try:
        await app_obj.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        logger.exception("Could not delete webhook")


def build_application():
    global application

    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )

    application = builder.build()

    application.add_handler(CommandHandler("start", start))

    # Commands.
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^/admin$"),
            lambda update, context: enhanced_menu_handler(update, context),
        )
    )

    # Any message, including arbitrary media.
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            message_capture,
        )
    )

    return application


def run():
    init_db()
    bot_app = build_application()

    # Run the Telegram application in the background so Flask can serve
    # the webhook. This avoids polling and therefore avoids the
    # "Conflict: terminated by other getUpdates request" error.
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=(
            WEBHOOK_URL.rstrip("/") + "/" + WEBHOOK_PATH
            if WEBHOOK_URL else None
        ),
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    run()
