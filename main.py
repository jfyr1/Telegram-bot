# ============================================================
# Telegram Educational Bot - Complete Edition
# Python 3.11+
# python-telegram-bot 21+
# ============================================================

import os
import sqlite3
import secrets
import html
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin ID requested
ADMIN_ID = 5734654153

DB_NAME = "bot.db"

PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    secrets.token_urlsafe(32)
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN ØºÙØ± ÙÙØ¬ÙØ¯. Ø£Ø¶ÙÙ ÙÙ Environment Variables ÙÙ Render."
    )


# ============================================================
# DATABASE
# ============================================================

def db_connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_init():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'ð',
            sort_order INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(parent_id) REFERENCES sections(id)
                ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            source_chat_id INTEGER NOT NULL,
            source_message_id INTEGER NOT NULL,
            content_type TEXT DEFAULT 'unknown',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(id)
                ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, section_id),
            FOREIGN KEY(section_id) REFERENCES sections(id)
                ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            user_id INTEGER NOT NULL,
            section_id INTEGER NOT NULL,
            count INTEGER DEFAULT 0,
            last_visit TEXT,
            PRIMARY KEY(user_id, section_id),
            FOREIGN KEY(section_id) REFERENCES sections(id)
                ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            section_id INTEGER,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES sections(id)
                ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            button_key TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            icon TEXT DEFAULT 'ð',
            sort_order INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            admin_only INTEGER DEFAULT 0
        )
    """)

    conn.commit()

    # --------------------------------------------------------
    # DEFAULT SETTINGS
    # --------------------------------------------------------

    defaults = {
        "welcome_enabled": "1",
        "new_user_notifications": "1",
        "rating_enabled": "1",
        "notes_enabled": "1",
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",
            (key, value)
        )

    # --------------------------------------------------------
    # DEFAULT SYSTEM BUTTONS
    # --------------------------------------------------------

    system_buttons = [
        ("favorites", "Ø§ÙÙÙØ¶ÙØ©", "â­", 10, 1, 0),
        ("popular", "Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù", "ð", 20, 1, 0),
        ("rating", "ØªÙÙÙÙ Ø§ÙØ¨ÙØª", "â­", 30, 1, 0),
        ("about", "Ø­ÙÙ Ø§ÙØ¨ÙØª", "â¹ï¸", 40, 1, 0),
        ("contact", "ÙØ±Ø§Ø³ÙØ© Ø§ÙØ¥Ø¯Ø§Ø±Ø©", "âï¸", 50, 1, 0),
        ("admin", "ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©", "ð", 100, 1, 1),
    ]

    for item in system_buttons:
        cur.execute("""
            INSERT OR IGNORE INTO system_buttons
            (button_key,label,icon,sort_order,enabled,admin_only)
            VALUES (?,?,?,?,?,?)
        """, item)

    conn.commit()

    # --------------------------------------------------------
    # DEFAULT SECTIONS
    # --------------------------------------------------------

    count = cur.execute(
        "SELECT COUNT(*) FROM sections"
    ).fetchone()[0]

    if count == 0:
        now = datetime.now().isoformat()

        cur.execute("""
            INSERT INTO sections
            (parent_id,name,icon,sort_order,enabled,created_at)
            VALUES (NULL,?,?,?,?,?)
        """, (0, "Ø§ÙÙØ±Ø­ÙØ© Ø§ÙØ£ÙÙÙ", "ð", 1, now))

        stage1 = cur.lastrowid

        cur.execute("""
            INSERT INTO sections
            (parent_id,name,icon,sort_order,enabled,created_at)
            VALUES (?,?,?,?,?,?)
        """, (
            stage1,
            "Ø§ÙÙÙØ±Ø³ Ø§ÙØ£ÙÙ",
            "ð",
            1,
            1,
            now,
        ))

        course1 = cur.lastrowid

        cur.execute("""
            INSERT INTO sections
            (parent_id,name,icon,sort_order,enabled,created_at)
            VALUES (?,?,?,?,?,?)
        """, (
            stage1,
            "Ø§ÙÙÙØ±Ø³ Ø§ÙØ«Ø§ÙÙ",
            "ð",
            2,
            1,
            now,
        ))

        course2 = cur.lastrowid

        # ÙÙØ§Ø¯ Ø§ÙØªØ±Ø§Ø¶ÙØ©
        subjects1 = [
            ("Ø±ÙØ§Ø¶ÙØ§Øª", "ð"),
            ("Ø¨Ø±ÙØ¬Ø©", "ð»"),
            ("Ø¯ÙØ§Ø¦Ø± ÙÙØ±Ø¨Ø§Ø¦ÙØ©", "â¡"),
            ("Ø£Ø³Ø§Ø³ÙØ§Øª Ø§ÙØ­Ø§Ø³ÙØ¨", "ð¥ï¸"),
        ]

        subjects2 = [
            ("Ø§ÙØ±ÙØ§Ø¶ÙØ§Øª", "ð"),
            ("Ø§ÙØ¨Ø±ÙØ¬Ø©", "ð»"),
            ("Ø§ÙØ¥ÙÙØªØ±ÙÙÙØ§Øª", "ð"),
        ]

        for index, (name, icon) in enumerate(subjects1, 1):
            cur.execute("""
                INSERT INTO sections
                (parent_id,name,icon,sort_order,enabled,created_at)
                VALUES (?,?,?,?,?,?)
            """, (
                course1,
                name,
                icon,
                index,
                1,
                now,
            ))

        for index, (name, icon) in enumerate(subjects2, 1):
            cur.execute("""
                INSERT INTO sections
                (parent_id,name,icon,sort_order,enabled,created_at)
                VALUES (?,?,?,?,?,?)
            """, (
                course2,
                name,
                icon,
                index,
                1,
                now,
            ))

        conn.commit()

    conn.close()


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now().isoformat()


def bold(text):
    return f"<b>{html.escape(str(text))}</b>"


def get_setting(key, default="0"):
    conn = db_connect()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()
    conn.close()

    if not row:
        return default

    return row["value"]


def set_setting(key, value):
    conn = db_connect()
    conn.execute("""
        INSERT INTO settings(key,value)
        VALUES (?,?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def add_user(user):
    conn = db_connect()

    exists = conn.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (user.id,)
    ).fetchone()

    first = not bool(exists)

    conn.execute("""
        INSERT INTO users
        (user_id,username,first_name,last_name,joined_at,last_seen)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            last_seen=excluded.last_seen
    """, (
        user.id,
        user.username or "",
        user.first_name or "",
        user.last_name or "",
        now(),
        now(),
    ))

    conn.commit()
    conn.close()

    return first


def get_section(section_id):
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM sections WHERE id=?",
        (section_id,)
    ).fetchone()
    conn.close()
    return row


def get_children(parent_id):
    conn = db_connect()

    if parent_id is None:
        rows = conn.execute("""
            SELECT *
            FROM sections
            WHERE parent_id IS NULL
              AND enabled=1
            ORDER BY sort_order,id
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT *
            FROM sections
            WHERE parent_id=?
              AND enabled=1
            ORDER BY sort_order,id
        """, (parent_id,)).fetchall()

    conn.close()
    return rows


def get_all_children(parent_id):
    conn = db_connect()

    if parent_id is None:
        rows = conn.execute("""
            SELECT *
            FROM sections
            WHERE parent_id IS NULL
            ORDER BY sort_order,id
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT *
            FROM sections
            WHERE parent_id=?
            ORDER BY sort_order,id
        """, (parent_id,)).fetchall()

    conn.close()
    return rows


def get_contents(section_id):
    conn = db_connect()
    rows = conn.execute("""
        SELECT *
        FROM contents
        WHERE section_id=?
        ORDER BY sort_order,id
    """, (section_id,)).fetchall()
    conn.close()
    return rows


def section_has_children(section_id):
    conn = db_connect()
    value = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE parent_id=?",
        (section_id,)
    ).fetchone()[0]
    conn.close()
    return value > 0


def section_has_contents(section_id):
    conn = db_connect()
    value = conn.execute(
        "SELECT COUNT(*) FROM contents WHERE section_id=?",
        (section_id,)
    ).fetchone()[0]
    conn.close()
    return value > 0


def default_icon(name):
    name = name.lower()

    if "Ø±ÙØ§Ø¶" in name:
        return "ð"
    if "Ø¨Ø±ÙØ¬" in name:
        return "ð»"
    if "Ø­Ø§Ø³ÙØ¨" in name:
        return "ð¥ï¸"
    if "ÙÙØ±Ø¨" in name:
        return "â¡"
    if "Ø¥ÙÙØªØ±" in name:
        return "ð"
    if "ÙØ­Ø§Ø¶" in name:
        return "ð"
    if "ÙÙØ±Ø³" in name:
        return "ð"
    if "ÙÙØ®Øµ" in name:
        return "ð"
    if "ÙØ±Ø­ÙØ©" in name:
        return "ð"

    return "ð"


def get_path(section_id):
    path = []
    current = get_section(section_id)

    while current:
        path.append(current["name"])
        parent_id = current["parent_id"]

        if parent_id is None:
            break

        current = get_section(parent_id)

    path.reverse()
    return path


def path_text(section_id):
    path = get_path(section_id)
    return "  âº  ".join(path)


def record_visit(user_id, section_id):
    conn = db_connect()

    conn.execute("""
        INSERT INTO visits(user_id,section_id,count,last_visit)
        VALUES (?,?,1,?)
        ON CONFLICT(user_id,section_id)
        DO UPDATE SET
            count=count+1,
            last_visit=excluded.last_visit
    """, (
        user_id,
        section_id,
        now(),
    ))

    conn.commit()
    conn.close()


def is_favorite(user_id, section_id):
    conn = db_connect()

    row = conn.execute("""
        SELECT 1
        FROM favorites
        WHERE user_id=? AND section_id=?
    """, (user_id, section_id)).fetchone()

    conn.close()
    return bool(row)


def toggle_favorite(user_id, section_id):
    conn = db_connect()

    exists = conn.execute("""
        SELECT 1
        FROM favorites
        WHERE user_id=? AND section_id=?
    """, (user_id, section_id)).fetchone()

    if exists:
        conn.execute("""
            DELETE FROM favorites
            WHERE user_id=? AND section_id=?
        """, (user_id, section_id))
        result = False
    else:
        conn.execute("""
            INSERT INTO favorites
            (user_id,section_id,created_at)
            VALUES (?,?,?)
        """, (user_id, section_id, now()))
        result = True

    conn.commit()
    conn.close()

    return result


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard(user_id):
    rows = []

    sections = get_children(None)

    for section in sections:
        rows.append([
            InlineKeyboardButton(
                f"{section['icon']} {section['name']}",
                callback_data=f"OPEN:{section['id']}"
            )
        ])

    conn = db_connect()

    system = conn.execute("""
        SELECT *
        FROM system_buttons
        WHERE enabled=1
        ORDER BY sort_order,id
    """).fetchall()

    conn.close()

    temp = []

    for button in system:
        if button["admin_only"] and not is_admin(user_id):
            continue

        temp.append(
            InlineKeyboardButton(
                f"{button['icon']} {button['label']}",
                callback_data=f"SYS:{button['button_key']}"
            )
        )

        if len(temp) == 2:
            rows.append(temp)
            temp = []

    if temp:
        rows.append(temp)

    return InlineKeyboardMarkup(rows)


def section_keyboard(user_id, section_id):
    rows = []

    children = get_children(section_id)

    for child in children:
        rows.append([
            InlineKeyboardButton(
                f"{child['icon']} {child['name']}",
                callback_data=f"OPEN:{child['id']}"
            )
        ])

    favorite_text = (
        "ð Ø¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©"
        if is_favorite(user_id, section_id)
        else "â­ Ø¥Ø¶Ø§ÙØ© Ø¥ÙÙ Ø§ÙÙÙØ¶ÙØ©"
    )

    rows.append([
        InlineKeyboardButton(
            favorite_text,
            callback_data=f"FAV:{section_id}"
        )
    ])

    if get_setting("notes_enabled", "1") == "1":
        rows.append([
            InlineKeyboardButton(
                "âï¸ ÙÙØ§Ø­Ø¸Ø© Ø¨Ø®ØµÙØµ ÙØ°Ø§ Ø§ÙÙØ³Ù",
                callback_data=f"NOTE:{section_id}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
            callback_data="MAIN"
        ),
        InlineKeyboardButton(
            "â¬ï¸ Ø§ÙØ±Ø¬ÙØ¹",
            callback_data=f"BACK:{section_id}"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            f"ðª Ø®Ø±ÙØ¬ ÙÙ {get_section(section_id)['name']}",
            callback_data="MAIN"
        )
    ])

    return InlineKeyboardMarkup(rows)


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                callback_data="ADMIN:BUTTONS"
            ),
            InlineKeyboardButton(
                "ð ØªØ¹Ø¯ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª",
                callback_data="ADMIN:CONTENT"
            )
        ],
        [
            InlineKeyboardButton(
                "ð Ø§ÙØ¥Ø­ØµØ§Ø¦ÙØ§Øª",
                callback_data="ADMIN:STATS"
            ),
            InlineKeyboardButton(
                "âï¸ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª",
                callback_data="ADMIN:NOTES"
            )
        ],
        [
            InlineKeyboardButton(
                "â­ Ø§ÙØªÙÙÙÙØ§Øª",
                callback_data="ADMIN:RATINGS"
            ),
            InlineKeyboardButton(
                "âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª",
                callback_data="ADMIN:SETTINGS"
            )
        ],
        [
            InlineKeyboardButton(
                "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                callback_data="MAIN"
            )
        ]
    ])


# ============================================================
# MAIN SCREENS
# ============================================================

async def send_main_menu(update, context, edit=False):
    user = update.effective_user

    text = (
        "ð¤ <b>Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØ°ÙÙ</b>\n\n"
        "ð <b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ Ø§ÙØ¯Ø®ÙÙ Ø¥ÙÙÙ:</b>"
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )
    else:
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )


async def show_section(update, context, section_id, edit=True):
    user = update.effective_user
    section = get_section(section_id)

    if not section:
        await update.effective_message.reply_text(
            bold("Ø§ÙÙØ³Ù ØºÙØ± ÙÙØ¬ÙØ¯."),
            parse_mode=ParseMode.HTML
        )
        return

    record_visit(user.id, section_id)

    children = get_children(section_id)
    contents = get_contents(section_id)

    title = f"{section['icon']} {section['name']}"

    text = (
        f"<b>{html.escape(title)}</b>\n\n"
        f"<b>Ø§ÙÙØ³Ø§Ø±:</b> {html.escape(path_text(section_id))}\n\n"
    )

    if children:
        text += "<b>Ø§Ø®ØªØ± ÙÙ Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªØ§ÙÙØ©:</b>"
    elif contents:
        text += "<b>Ø§ÙÙØ­ØªÙÙ Ø§ÙÙØªÙÙØ± ÙÙØ°Ø§ Ø§ÙÙØ³Ù Ø³ÙØ¸ÙØ± Ø£Ø³ÙÙ ÙØ°Ù Ø§ÙÙØ§Ø¬ÙØ©.</b>"
    else:
        text += "<b>ÙØ§ ÙÙØ¬Ø¯ ÙØ­ØªÙÙ Ø¯Ø§Ø®Ù ÙØ°Ø§ Ø§ÙÙØ³Ù Ø­Ø§ÙÙØ§Ù.</b>"

    keyboard = section_keyboard(user.id, section_id)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    else:
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    # Ø¥Ø±Ø³Ø§Ù Ø§ÙÙØ­ØªÙÙ Ø§ÙÙØ®Ø²Ù
    if contents:
        for item in contents:
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=item["source_chat_id"],
                    message_id=item["source_message_id"]
                )
            except Exception as e:
                logger.error(
                    "Content copy error: %s",
                    e
                )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    first = add_user(user)

    if first and get_setting("new_user_notifications", "1") == "1":
        try:
            username = (
                f"@{user.username}"
                if user.username
                else "Ø¨Ø¯ÙÙ ÙØ¹Ø±Ù"
            )

            await context.bot.send_message(
                ADMIN_ID,
                (
                    "ð <b>ÙØ³ØªØ®Ø¯Ù Ø¬Ø¯ÙØ¯ Ø¯Ø®Ù Ø§ÙØ¨ÙØª</b>\n\n"
                    f"ð¤ Ø§ÙØ§Ø³Ù: <b>{html.escape(user.full_name)}</b>\n"
                    f"ð¹ Ø§ÙÙØ¹Ø±Ù: <b>{html.escape(username)}</b>\n"
                    f"ð ID: <code>{user.id}</code>"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("New user notification error: %s", e)

    if get_setting("welcome_enabled", "1") == "1":
        text = (
            "ð <b>Ø£ÙÙØ§Ù ÙØ³ÙÙØ§Ù Ø¨Ù ÙÙ Ø§ÙÙØ³Ø§Ø¹Ø¯ Ø§ÙØ°ÙÙ</b>\n\n"
            "ð <b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ Ø§ÙØ¯Ø®ÙÙ Ø¥ÙÙÙ.</b>"
        )
    else:
        text = "<b>Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©</b>"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )


# ============================================================
# SYSTEM BUTTONS
# ============================================================

async def system_button(update, context, key):
    query = update.callback_query
    user = update.effective_user

    if key == "favorites":
        await show_favorites(update, context)

    elif key == "popular":
        await show_popular(update, context)

    elif key == "rating":
        await show_rating(update, context)

    elif key == "about":
        await show_about(update, context)

    elif key == "contact":
        context.user_data["state"] = "global_note"

        await query.edit_message_text(
            "<b>âï¸ ÙØ±Ø§Ø³ÙØ© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n\n"
            "<b>Ø£Ø±Ø³Ù Ø±Ø³Ø§ÙØªÙ Ø§ÙØ¢ÙØ ÙØ³ØªØµÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø© ÙØ¨Ø§Ø´Ø±Ø©.</b>\n\n"
            "<b>ÙÙØ¥ÙØºØ§Ø¡:</b> /cancel",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "â Ø¥ÙØºØ§Ø¡",
                        callback_data="CANCEL"
                    )
                ]
            ])
        )

    elif key == "admin":
        if not is_admin(user.id):
            await query.answer(
                "ØºÙØ± ÙØ³ÙÙØ­ ÙÙ Ø¨Ø§ÙØ¯Ø®ÙÙ.",
                show_alert=True
            )
            return

        await show_admin(update, context)


async def show_favorites(update, context):
    user = update.effective_user

    conn = db_connect()

    rows = conn.execute("""
        SELECT s.*
        FROM favorites f
        JOIN sections s ON s.id=f.section_id
        WHERE f.user_id=?
        ORDER BY f.created_at DESC
    """, (user.id,)).fetchall()

    conn.close()

    buttons = []

    for section in rows:
        buttons.append([
            InlineKeyboardButton(
                f"{section['icon']} {section['name']}",
                callback_data=f"OPEN:{section['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
            callback_data="MAIN"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>â­ Ø§ÙÙÙØ¶ÙØ©</b>\n\n"
        + (
            "<b>Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙÙØ­ÙÙØ¸Ø©:</b>"
            if rows
            else "<b>ÙØ§ ØªÙØ¬Ø¯ Ø£ÙØ³Ø§Ù ÙÙ Ø§ÙÙÙØ¶ÙØ© Ø­Ø§ÙÙØ§Ù.</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_popular(update, context):
    conn = db_connect()

    rows = conn.execute("""
        SELECT
            s.id,
            s.name,
            s.icon,
            SUM(v.count) AS total
        FROM visits v
        JOIN sections s ON s.id=v.section_id
        GROUP BY s.id
        ORDER BY total DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    buttons = []

    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                f"{row['icon']} {row['name']} â {row['total']} Ø²ÙØ§Ø±Ø©",
                callback_data=f"OPEN:{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
            callback_data="MAIN"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>ð Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù</b>\n\n"
        "<b>Ø£ÙØ«Ø± Ø§ÙØ£ÙØ³Ø§Ù Ø²ÙØ§Ø±Ø©:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_rating(update, context):
    await update.callback_query.edit_message_text(
        "<b>â­ ØªÙÙÙÙ Ø§ÙØ¨ÙØª</b>\n\n"
        "<b>Ø§Ø®ØªØ± ØªÙÙÙÙÙ:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("â­", callback_data="RATE:1"),
                InlineKeyboardButton("â­â­", callback_data="RATE:2"),
                InlineKeyboardButton("â­â­â­", callback_data="RATE:3"),
            ],
            [
                InlineKeyboardButton("â­â­â­â­", callback_data="RATE:4"),
                InlineKeyboardButton("â­â­â­â­â­", callback_data="RATE:5"),
            ],
            [
                InlineKeyboardButton(
                    "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                    callback_data="MAIN"
                )
            ]
        ])
    )


async def show_about(update, context):
    text = (
        "<b>â¹ï¸ Ø­ÙÙ Ø§ÙØ¨ÙØª</b>\n\n"
        "<b>ð ÙÙØ±Ø³ Ø§ÙØ§Ø³ØªØ®Ø¯Ø§Ù:</b>\n\n"
        "1ï¸â£ <b>Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©</b>\n"
        "ÙÙÙØ§ ØªØ¯Ø®Ù Ø¥ÙÙ Ø¬ÙÙØ¹ Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØ±Ø¦ÙØ³ÙØ©.\n\n"
        "2ï¸â£ <b>Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙÙØ±Ø¹ÙØ©</b>\n"
        "ÙÙ ÙØ³Ù ÙÙÙÙ Ø£Ù ÙØ­ØªÙÙ Ø¹ÙÙ Ø£ÙØ³Ø§Ù Ø£Ø®Ø±Ù Ø­ØªÙ Ø£Ù ÙØ³ØªÙÙ.\n\n"
        "3ï¸â£ <b>Ø§ÙÙØ­ØªÙÙ</b>\n"
        "Ø§ÙÙØ­Ø§Ø¶Ø±Ø§Øª ÙÙÙÙ Ø£Ù ØªØ­ØªÙÙ PDF Ø£Ù ØµÙØ±Ø© Ø£Ù ÙÙØ¯ÙÙ "
        "Ø£Ù ÙÙÙ Ø£Ù ØµÙØª Ø£Ù Ø£Ù ÙØ­ØªÙÙ ÙØ³ÙØ­ Ø¨Ù Telegram.\n\n"
        "4ï¸â£ <b>Ø§ÙÙÙØ¶ÙØ©</b>\n"
        "Ø§Ø­ÙØ¸ Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØªÙ ØªØ¯Ø®Ù Ø¥ÙÙÙØ§ ÙØ«ÙØ±Ø§Ù.\n\n"
        "5ï¸â£ <b>Ø§ÙØ£ÙØ«Ø± Ø¯Ø®ÙÙØ§Ù</b>\n"
        "ÙØ¹Ø±Ø¶ Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙØ£ÙØ«Ø± Ø²ÙØ§Ø±Ø©.\n\n"
        "6ï¸â£ <b>ÙØ±Ø§Ø³ÙØ© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n"
        "ÙÙÙÙ Ø¥Ø±Ø³Ø§Ù ÙÙØ§Ø­Ø¸Ø© Ø£Ù ÙØ´ÙÙØ© Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.\n\n"
        "7ï¸â£ <b>ØªÙÙÙÙ Ø§ÙØ¨ÙØª</b>\n"
        "ÙÙÙÙÙ ØªÙÙÙÙ Ø§ÙØ¨ÙØª ÙÙ ÙØ¬ÙØ© Ø¥ÙÙ Ø®ÙØ³ ÙØ¬ÙÙ.\n\n"
        "8ï¸â£ <b>ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n"
        "Ø§ÙØ¥Ø¯Ø§Ø±Ø© ØªØ³ØªØ·ÙØ¹ Ø¥ÙØ´Ø§Ø¡ ÙØªØ¹Ø¯ÙÙ ÙÙÙÙ ÙØ¯ÙØ¬ ÙØ­Ø°Ù Ø§ÙØ£ÙØ³Ø§ÙØ "
        "ÙØªØ¹Ø¯ÙÙ Ø§ÙØ£Ø²Ø±Ø§Ø± ÙØ§ÙÙØ­ØªÙÙ.\n\n"
        "<b>ð¯ Ø§ÙÙØ¯Ù:</b>\n"
        "ØªÙØ¸ÙÙ Ø§ÙÙØ­Ø§Ø¶Ø±Ø§Øª ÙØ§ÙÙÙÙØ§Øª Ø¨Ø·Ø±ÙÙØ© Ø³ÙÙØ© ÙØ³Ø±ÙØ¹Ø©."
    )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                    callback_data="MAIN"
                )
            ]
        ])
    )


# ============================================================
# RATING
# ============================================================

async def save_rating(update, context, rating):
    user = update.effective_user

    conn = db_connect()

    conn.execute("""
        INSERT INTO ratings
        (user_id,rating,comment,created_at)
        VALUES (?,?,?,?)
    """, (
        user.id,
        rating,
        "",
        now()
    ))

    conn.commit()
    conn.close()

    await update.callback_query.answer(
        "ØªÙ Ø­ÙØ¸ ØªÙÙÙÙÙ â¤ï¸",
        show_alert=True
    )

    await update.callback_query.edit_message_text(
        f"<b>Ø´ÙØ±Ø§Ù ÙÙ â¤ï¸</b>\n\n"
        f"<b>ØªÙÙÙÙÙ:</b> {'â­' * rating}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð  Ø§ÙÙØ§Ø¦ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                    callback_data="MAIN"
                )
            ]
        ])
    )


# ============================================================
# NOTES
# ============================================================

async def start_note(update, context, section_id):
    context.user_data["state"] = "section_note"
    context.user_data["note_section_id"] = section_id

    section = get_section(section_id)

    await update.callback_query.edit_message_text(
        f"<b>âï¸ ÙÙØ§Ø­Ø¸Ø© Ø¹Ù ÙØ³Ù: "
        f"{html.escape(section['name'])}</b>\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§ÙÙÙØ§Ø­Ø¸Ø© Ø§ÙØ¢Ù.</b>\n\n"
        "<b>ÙÙØ¥ÙØºØ§Ø¡:</b> /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â Ø¥ÙØºØ§Ø¡",
                    callback_data="CANCEL"
                )
            ]
        ])
    )


async def save_note(update, context, section_id, text):
    user = update.effective_user

    conn = db_connect()

    conn.execute("""
        INSERT INTO notes
        (user_id,section_id,text,created_at)
        VALUES (?,?,?,?)
    """, (
        user.id,
        section_id,
        text,
        now()
    ))

    note_id = conn.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    conn.commit()
    conn.close()

    section = get_section(section_id)

    try:
        await context.bot.send_message(
            ADMIN_ID,
            (
                "âï¸ <b>ÙÙØ§Ø­Ø¸Ø© Ø¬Ø¯ÙØ¯Ø©</b>\n\n"
                f"ð Ø±ÙÙ: <code>{note_id}</code>\n"
                f"ð¤ Ø§ÙÙØ³ØªØ®Ø¯Ù: <b>{html.escape(user.full_name)}</b>\n"
                f"ð ID: <code>{user.id}</code>\n"
                f"ð Ø§ÙÙØ³Ù: <b>{html.escape(section['name'])}</b>\n\n"
                f"ð <b>Ø§ÙÙÙØ§Ø­Ø¸Ø©:</b>\n"
                f"{html.escape(text)}"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error("Note notification error: %s", e)

    context.user_data.clear()

    await update.message.reply_text(
        "<b>â ØªÙ Ø¥Ø±Ø³Ø§Ù ÙÙØ§Ø­Ø¸ØªÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )


# ============================================================
# ADMIN
# ============================================================

async def show_admin(update, context):
    text = (
        "ð <b>ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©</b>\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ© Ø§ÙÙØ·ÙÙØ¨Ø©:</b>"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )


# ============================================================
# ADMIN - BUTTON EDITOR
# ============================================================

async def editor_home(update, context):
    await update.callback_query.edit_message_text(
        "<b>ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±</b>\n\n"
        "<b>ÙÙØ§ ØªØ³ØªØ·ÙØ¹ Ø§ÙØªØ­ÙÙ Ø¨ÙÙ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙØ£Ø²Ø±Ø§Ø±.</b>\n\n"
        "ÙÙÙÙÙ:\n"
        "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù\n"
        "âï¸ ØªØ¹Ø¯ÙÙ Ø§ÙØ§Ø³Ù\n"
        "ð¨ ØªØ¹Ø¯ÙÙ Ø§ÙØ£ÙÙÙÙØ©\n"
        "âï¸ ØªØºÙÙØ± Ø§ÙØªØ±ØªÙØ¨\n"
        "ð¦ ÙÙÙ Ø§ÙÙØ³Ù\n"
        "ð Ø¯ÙØ¬ Ø§ÙØ£ÙØ³Ø§Ù\n"
        "ð Ø­Ø°Ù Ø§ÙÙØ³Ù\n"
        "ð Ø¥Ø®ÙØ§Ø¡/Ø¥Ø¸ÙØ§Ø± Ø§ÙÙØ³Ù",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð  ØªØ¹Ø¯ÙÙ Ø§ÙÙØ§Ø¬ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                    callback_data="ED:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù Ø±Ø¦ÙØ³Ù",
                    callback_data="ADD:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "âï¸ Ø£Ø²Ø±Ø§Ø± Ø§ÙÙØ¸Ø§Ù",
                    callback_data="ED:SYSTEM"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


async def edit_section_screen(update, context, section_id):
    section = get_section(section_id)

    if not section:
        await update.callback_query.answer(
            "Ø§ÙÙØ³Ù ØºÙØ± ÙÙØ¬ÙØ¯.",
            show_alert=True
        )
        return

    children = get_all_children(section_id)

    buttons = []

    for child in children:
        buttons.append([
            InlineKeyboardButton(
                f"{child['icon']} {child['name']}",
                callback_data=f"EDSEC:{child['id']}"
            )
        ])

    buttons.extend([
        [
            InlineKeyboardButton(
                "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù Ø¯Ø§Ø®Ù ÙØ°Ø§ Ø§ÙÙØ³Ù",
                callback_data=f"ADD:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "âï¸ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙÙØ³Ù",
                callback_data=f"RENAME:{section_id}"
            ),
            InlineKeyboardButton(
                "ð¨ ØªØ¹Ø¯ÙÙ Ø§ÙØ£ÙÙÙÙØ©",
                callback_data=f"ICON:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "ð¦ ÙÙÙ Ø§ÙÙØ³Ù",
                callback_data=f"MOVE:{section_id}"
            ),
            InlineKeyboardButton(
                "ð Ø¯ÙØ¬ Ø§ÙÙØ³Ù",
                callback_data=f"MERGE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "â¬ï¸ Ø±ÙØ¹",
                callback_data=f"UP:{section_id}"
            ),
            InlineKeyboardButton(
                "â¬ï¸ ØªÙØ²ÙÙ",
                callback_data=f"DOWN:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "ð Ø¥Ø¸ÙØ§Ø±/Ø¥Ø®ÙØ§Ø¡",
                callback_data=f"TOGGLE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "ð Ø­Ø°Ù Ø§ÙÙØ³Ù",
                callback_data=f"DELETE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "â¬ï¸ ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                callback_data="ADMIN:BUTTONS"
            )
        ]
    ])

    await update.callback_query.edit_message_text(
        f"<b>ð§© ØªØ­Ø±ÙØ±:</b> "
        f"{html.escape(section['icon'])} "
        f"{html.escape(section['name'])}\n\n"
        f"<b>Ø§ÙÙØ³Ø§Ø±:</b> "
        f"{html.escape(path_text(section_id))}\n\n"
        "<b>Ø§ÙØ£ÙØ³Ø§Ù Ø§ÙÙÙØ¬ÙØ¯Ø© Ø¯Ø§Ø®Ù ÙØ°Ø§ Ø§ÙÙØ³Ù:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def edit_root_screen(update, context):
    sections = get_all_children(None)

    buttons = []

    for section in sections:
        buttons.append([
            InlineKeyboardButton(
                f"{section['icon']} {section['name']}",
                callback_data=f"EDSEC:{section['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù Ø±Ø¦ÙØ³Ù",
            callback_data="ADD:ROOT"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "âï¸ Ø£Ø²Ø±Ø§Ø± Ø§ÙÙØ¸Ø§Ù",
            callback_data="ED:SYSTEM"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "â¬ï¸ ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
            callback_data="ADMIN:BUTTONS"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>ð  ØªØ­Ø±ÙØ± Ø§ÙÙØ§Ø¬ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©</b>\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ ØªØ¹Ø¯ÙÙÙ:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ============================================================
# ADD SECTION
# ============================================================

async def ask_add_section(update, context, parent_id):
    context.user_data["state"] = "add_section"
    context.user_data["parent_id"] = parent_id

    if parent_id == "ROOT":
        location = "Ø§ÙÙØ§Ø¬ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"
    else:
        parent = get_section(parent_id)
        location = parent["name"] if parent else "Ø§ÙÙØ³Ù"

    await update.callback_query.edit_message_text(
        f"<b>â Ø¥Ø¶Ø§ÙØ© ÙØ³Ù Ø¬Ø¯ÙØ¯ Ø¯Ø§Ø®Ù: "
        f"{html.escape(location)}</b>\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù Ø§ÙØ¢Ù.</b>\n\n"
        "<b>ÙØ«Ø§Ù:</b>\n"
        "<b>Ø§ÙÙØ­Ø§Ø¶Ø±Ø© Ø§ÙØ£ÙÙÙ</b>\n\n"
        "<b>ÙÙØ¥ÙØºØ§Ø¡:</b> /cancel",
        parse_mode=ParseMode.HTML
    )


def create_section(parent_id, name):
    conn = db_connect()

    if parent_id == "ROOT":
        parent = None
    else:
        parent = int(parent_id)

    row = conn.execute("""
        SELECT COALESCE(MAX(sort_order),0)+1
        FROM sections
        WHERE parent_id IS ?
    """, (parent,)).fetchone()

    order = row[0]

    cur = conn.execute("""
        INSERT INTO sections
        (parent_id,name,icon,sort_order,enabled,created_at)
        VALUES (?,?,?,?,?,?)
    """, (
        parent,
        name,
        default_icon(name),
        order,
        1,
        now()
    ))

    section_id = cur.lastrowid

    conn.commit()
    conn.close()

    return section_id


# ============================================================
# RENAME / ICON
# ============================================================

async def ask_rename(update, context, section_id):
    context.user_data["state"] = "rename_section"
    context.user_data["section_id"] = section_id

    section = get_section(section_id)

    await update.callback_query.edit_message_text(
        f"<b>âï¸ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙÙØ³Ù Ø§ÙØ­Ø§ÙÙ:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§ÙØ§Ø³Ù Ø§ÙØ¬Ø¯ÙØ¯:</b>",
        parse_mode=ParseMode.HTML
    )


async def ask_icon(update, context, section_id):
    context.user_data["state"] = "icon_section"
    context.user_data["section_id"] = section_id

    section = get_section(section_id)

    await update.callback_query.edit_message_text(
        f"<b>ð¨ ØªØ¹Ø¯ÙÙ Ø£ÙÙÙÙØ©:</b>\n\n"
        f"<b>{html.escape(section['name'])}</b>\n"
        f"<b>Ø§ÙØ£ÙÙÙÙØ© Ø§ÙØ­Ø§ÙÙØ©:</b> {section['icon']}\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§ÙØ¥ÙÙÙØ¬Ù Ø§ÙØ¬Ø¯ÙØ¯:</b>",
        parse_mode=ParseMode.HTML
    )


# ============================================================
# DELETE
# ============================================================

def count_descendants(section_id):
    children = get_all_children(section_id)
    total = len(children)

    for child in children:
        total += count_descendants(child["id"])

    return total


async def confirm_delete(update, context, section_id):
    section = get_section(section_id)

    if not section:
        return

    children = count_descendants(section_id)
    contents = len(get_contents(section_id))

    await update.callback_query.edit_message_text(
        "<b>â ï¸ ØªØ£ÙÙØ¯ Ø§ÙØ­Ø°Ù</b>\n\n"
        f"Ø§ÙÙØ³Ù: <b>{html.escape(section['name'])}</b>\n"
        f"Ø§ÙØ£ÙØ³Ø§Ù Ø¯Ø§Ø®ÙÙ: <b>{children}</b>\n"
        f"Ø§ÙÙØ´Ø§Ø±ÙØ§Øª: <b>{contents}</b>\n\n"
        "<b>Ø§ÙØ­Ø°Ù Ø³ÙØ­Ø°Ù Ø§ÙÙØ³Ù ÙÙØ­ØªÙÙØ§ØªÙ.</b>\n"
        "<b>ÙÙ Ø£ÙØª ÙØªØ£ÙØ¯Ø</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â ÙØ¹ÙØ Ø­Ø°Ù",
                    callback_data=f"DELETE_YES:{section_id}"
                ),
                InlineKeyboardButton(
                    "â Ø¥ÙØºØ§Ø¡",
                    callback_data=f"EDSEC:{section_id}"
                )
            ]
        ])
    )


def delete_section(section_id):
    conn = db_connect()

    conn.execute(
        "DELETE FROM sections WHERE id=?",
        (section_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# MOVE
# ============================================================

def descendants_ids(section_id):
    result = set()

    for child in get_all_children(section_id):
        result.add(child["id"])
        result.update(descendants_ids(child["id"]))

    return result


async def move_screen(update, context, section_id):
    section = get_section(section_id)

    if not section:
        return

    forbidden = descendants_ids(section_id)
    forbidden.add(section_id)

    all_sections = []

    conn = db_connect()
    rows = conn.execute("""
        SELECT *
        FROM sections
        ORDER BY parent_id,sort_order,id
    """).fetchall()
    conn.close()

    buttons = [
        [
            InlineKeyboardButton(
                "ð  Ø§ÙÙØ§Ø¬ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                callback_data=f"MOVE_TO:{section_id}:ROOT"
            )
        ]
    ]

    for row in rows:
        if row["id"] in forbidden:
            continue

        buttons.append([
            InlineKeyboardButton(
                f"{row['icon']} {row['name']}",
                callback_data=f"MOVE_TO:{section_id}:{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â Ø¥ÙØºØ§Ø¡",
            callback_data=f"EDSEC:{section_id}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>ð¦ ÙÙÙ Ø§ÙÙØ³Ù:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ¬Ø¯ÙØ¯ Ø§ÙØ°Ù Ø³ÙÙÙÙ Ø¨Ø¯Ø§Ø®ÙÙ:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_move(update, context, source_id, target_id):
    source = get_section(source_id)

    if target_id == "ROOT":
        target_name = "Ø§ÙÙØ§Ø¬ÙØ© Ø§ÙØ±Ø¦ÙØ³ÙØ©"
    else:
        target = get_section(int(target_id))
        target_name = target["name"]

    await update.callback_query.edit_message_text(
        "<b>â ï¸ ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ</b>\n\n"
        f"<b>Ø§ÙÙØ³Ù:</b> {html.escape(source['name'])}\n"
        f"<b>Ø¥ÙÙ:</b> {html.escape(target_name)}\n\n"
        "<b>ÙÙ ØªØ±ÙØ¯ ØªÙÙÙØ° Ø§ÙÙÙÙØ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â ØªØ£ÙÙØ¯ Ø§ÙÙÙÙ",
                    callback_data=f"MOVE_YES:{source_id}:{target_id}"
                ),
                InlineKeyboardButton(
                    "â Ø¥ÙØºØ§Ø¡",
                    callback_data=f"EDSEC:{source_id}"
                )
            ]
        ])
    )


def perform_move(source_id, target_id):
    conn = db_connect()

    if target_id == "ROOT":
        parent = None
    else:
        parent = int(target_id)

    order = conn.execute("""
        SELECT COALESCE(MAX(sort_order),0)+1
        FROM sections
        WHERE parent_id IS ?
    """, (parent,)).fetchone()[0]

    conn.execute("""
        UPDATE sections
        SET parent_id=?,sort_order=?
        WHERE id=?
    """, (
        parent,
        order,
        source_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# MERGE
# ============================================================

async def merge_screen(update, context, source_id):
    source = get_section(source_id)

    rows = []

    conn = db_connect()
    rows = conn.execute("""
        SELECT *
        FROM sections
        WHERE id != ?
        ORDER BY parent_id,sort_order,id
    """, (source_id,)).fetchall()
    conn.close()

    forbidden = descendants_ids(source_id)

    buttons = []

    for row in rows:
        if row["id"] in forbidden:
            continue

        buttons.append([
            InlineKeyboardButton(
                f"{row['icon']} {row['name']}",
                callback_data=f"MERGE_TO:{source_id}:{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â Ø¥ÙØºØ§Ø¡",
            callback_data=f"EDSEC:{source_id}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>ð Ø¯ÙØ¬ Ø§ÙÙØ³Ù:</b>\n"
        f"<b>{html.escape(source['name'])}</b>\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù Ø³ÙØªÙ Ø§ÙØ¯ÙØ¬ Ø¨Ø¯Ø§Ø®ÙÙ:</b>\n\n"
        "<b>Ø³ÙØªÙ ÙÙÙ Ø§ÙØ£ÙØ³Ø§Ù ÙØ§ÙÙØ´Ø§Ø±ÙØ§Øª Ø«Ù Ø­Ø°Ù Ø§ÙÙØ³Ù Ø§ÙØ£ØµÙÙ.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_merge(update, context, source_id, target_id):
    source = get_section(source_id)
    target = get_section(target_id)

    await update.callback_query.edit_message_text(
        "<b>â ï¸ ØªØ£ÙÙØ¯ Ø§ÙØ¯ÙØ¬</b>\n\n"
        f"<b>Ø§ÙÙØµØ¯Ø±:</b> {html.escape(source['name'])}\n"
        f"<b>Ø§ÙÙØ¯Ù:</b> {html.escape(target['name'])}\n\n"
        "<b>Ø³ÙØªÙ ÙÙÙ ÙØ­ØªÙÙ Ø§ÙÙØµØ¯Ø± Ø¥ÙÙ Ø§ÙÙØ¯ÙØ "
        "Ø«Ù Ø­Ø°Ù Ø§ÙÙØµØ¯Ø±.</b>\n\n"
        "<b>ÙÙ ØªØ±ÙØ¯ Ø§ÙÙØªØ§Ø¨Ø¹Ø©Ø</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â ÙØ¹ÙØ Ø¯ÙØ¬",
                    callback_data=f"MERGE_YES:{source_id}:{target_id}"
                ),
                InlineKeyboardButton(
                    "â Ø¥ÙØºØ§Ø¡",
                    callback_data=f"EDSEC:{source_id}"
                )
            ]
        ])
    )


def perform_merge(source_id, target_id):
    conn = db_connect()

    max_order = conn.execute("""
        SELECT COALESCE(MAX(sort_order),0)
        FROM sections
        WHERE parent_id=?
    """, (target_id,)).fetchone()[0]

    children = conn.execute("""
        SELECT id
        FROM sections
        WHERE parent_id=?
        ORDER BY sort_order,id
    """, (source_id,)).fetchall()

    for child in children:
        max_order += 1

        conn.execute("""
            UPDATE sections
            SET parent_id=?,sort_order=?
            WHERE id=?
        """, (
            target_id,
            max_order,
            child["id"]
        ))

    conn.execute("""
        UPDATE contents
        SET section_id=?
        WHERE section_id=?
    """, (
        target_id,
        source_id
    ))

    conn.execute(
        "DELETE FROM sections WHERE id=?",
        (source_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# REORDER
# ============================================================

def reorder(section_id, direction):
    section = get_section(section_id)

    if not section:
        return

    parent = section["parent_id"]

    conn = db_connect()

    rows = conn.execute("""
        SELECT *
        FROM sections
        WHERE parent_id IS ?
        ORDER BY sort_order,id
    """, (parent,)).fetchall()

    index = None

    for i, row in enumerate(rows):
        if row["id"] == section_id:
            index = i
            break

    if index is None:
        conn.close()
        return

    other_index = index - 1 if direction == "up" else index + 1

    if other_index < 0 or other_index >= len(rows):
        conn.close()
        return

    current = rows[index]
    other = rows[other_index]

    conn.execute("""
        UPDATE sections
        SET sort_order=?
        WHERE id=?
    """, (
        other["sort_order"],
        current["id"]
    ))

    conn.execute("""
        UPDATE sections
        SET sort_order=?
        WHERE id=?
    """, (
        current["sort_order"],
        other["id"]
    ))

    conn.commit()
    conn.close()


# ============================================================
# SYSTEM BUTTON EDITOR
# ============================================================

async def system_editor(update, context):
    conn = db_connect()

    rows = conn.execute("""
        SELECT *
        FROM system_buttons
        ORDER BY sort_order,id
    """).fetchall()

    conn.close()

    buttons = []

    for row in rows:
        status = "ð¢" if row["enabled"] else "ð´"

        buttons.append([
            InlineKeyboardButton(
                f"{status} {row['icon']} {row['label']}",
                callback_data=f"SYS_EDIT:{row['button_key']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â¬ï¸ ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
            callback_data="ADMIN:BUTTONS"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>âï¸ ÙØ­Ø±Ø± Ø£Ø²Ø±Ø§Ø± Ø§ÙÙØ¸Ø§Ù</b>\n\n"
        "<b>ÙÙÙÙÙ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙØ²Ø± ÙØ£ÙÙÙÙØªÙ ÙØªØ±ØªÙØ¨Ù ÙØ¥Ø¸ÙØ§Ø±Ù Ø£Ù Ø¥Ø®ÙØ§Ø¡Ù.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def system_button_edit(update, context, key):
    conn = db_connect()

    row = conn.execute("""
        SELECT *
        FROM system_buttons
        WHERE button_key=?
    """, (key,)).fetchone()

    conn.close()

    if not row:
        return

    await update.callback_query.edit_message_text(
        f"<b>ð§© ØªØ¹Ø¯ÙÙ Ø²Ø±:</b>\n\n"
        f"{row['icon']} <b>{html.escape(row['label'])}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "âï¸ ØªØ¹Ø¯ÙÙ Ø§ÙØ§Ø³Ù",
                    callback_data=f"SYS_RENAME:{key}"
                ),
                InlineKeyboardButton(
                    "ð¨ ØªØ¹Ø¯ÙÙ Ø§ÙØ£ÙÙÙÙØ©",
                    callback_data=f"SYS_ICON:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "ð Ø¥Ø¸ÙØ§Ø±/Ø¥Ø®ÙØ§Ø¡",
                    callback_data=f"SYS_TOGGLE:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ Ø±ÙØ¹",
                    callback_data=f"SYS_UP:{key}"
                ),
                InlineKeyboardButton(
                    "â¬ï¸ ØªÙØ²ÙÙ",
                    callback_data=f"SYS_DOWN:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ Ø±Ø¬ÙØ¹",
                    callback_data="ED:SYSTEM"
                )
            ]
        ])
    )


# ============================================================
# CONTENT EDITOR
# ============================================================

async def content_editor(update, context):
    await update.callback_query.edit_message_text(
        "<b>ð ØªØ¹Ø¯ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª</b>\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙÙØ³Ù Ø§ÙØ°Ù ØªØ±ÙØ¯ Ø¥Ø¯Ø§Ø±Ø© ÙØ­ØªÙØ§Ù.</b>\n\n"
        "ð PDF\n"
        "ð¼ ØµÙØ±Ø©\n"
        "ð¬ ÙÙØ¯ÙÙ\n"
        "ð ÙÙÙ\n"
        "ðµ ØµÙØª\n"
        "ð¬ ÙØµ\n"
        "ÙØ£Ù ÙÙØ¹ ÙØ­ØªÙÙ ÙØ³ÙØ­ Ø¨Ù Telegram.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð Ø§Ø®ØªÙØ§Ø± Ø§ÙÙØ³Ù",
                    callback_data="CONTENT:BROWSE:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


async def content_browse(update, context, parent_id):
    if parent_id == "ROOT":
        children = get_all_children(None)
    else:
        children = get_all_children(int(parent_id))

    buttons = []

    if parent_id != "ROOT":
        section = get_section(int(parent_id))

        buttons.append([
            InlineKeyboardButton(
                "â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ© ÙÙØ°Ø§ Ø§ÙÙØ³Ù",
                callback_data=f"CONTENT:ADD:{section['id']}"
            )
        ])

    for child in children:
        buttons.append([
            InlineKeyboardButton(
                f"{child['icon']} {child['name']}",
                callback_data=f"CONTENT:OPEN:{child['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â¬ï¸ Ø±Ø¬ÙØ¹",
            callback_data="ADMIN:CONTENT"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>ð Ø§Ø®ØªØ± Ø§ÙÙØ³Ù:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def content_section(update, context, section_id):
    section = get_section(section_id)
    contents = get_contents(section_id)
    children = get_all_children(section_id)

    buttons = [
        [
            InlineKeyboardButton(
                "â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ©",
                callback_data=f"CONTENT:ADD:{section_id}"
            )
        ]
    ]

    for item in contents:
        buttons.append([
            InlineKeyboardButton(
                f"ð ÙØ´Ø§Ø±ÙØ© #{item['id']} â {item['content_type']}",
                callback_data=f"CONTENT:EDIT:{item['id']}"
            )
        ])

    for child in children:
        buttons.append([
            InlineKeyboardButton(
                f"ð {child['name']}",
                callback_data=f"CONTENT:OPEN:{child['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "â¬ï¸ Ø±Ø¬ÙØ¹",
            callback_data=f"CONTENT:BROWSE:{section['parent_id'] if section['parent_id'] is not None else 'ROOT'}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>ð ÙØ­ØªÙÙ:</b> "
        f"{html.escape(section['name'])}\n\n"
        f"<b>Ø¹Ø¯Ø¯ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª:</b> {len(contents)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def ask_add_content(update, context, section_id):
    section = get_section(section_id)

    context.user_data["state"] = "add_content"
    context.user_data["content_section_id"] = section_id

    await update.callback_query.edit_message_text(
        f"<b>â Ø¥Ø¶Ø§ÙØ© ÙØ´Ø§Ø±ÙØ© Ø¥ÙÙ:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§ÙØ¢Ù Ø§ÙÙØ­ØªÙÙ ÙÙØ³Ù.</b>\n\n"
        "ÙÙÙÙÙ Ø¥Ø±Ø³Ø§Ù:\n"
        "ð PDF\n"
        "ð¼ ØµÙØ±Ø©\n"
        "ð¬ ÙÙØ¯ÙÙ\n"
        "ð ÙÙÙ\n"
        "ðµ ØµÙØª\n"
        "ð¬ ÙØµ\n\n"
        "<b>Ø£Ù ÙÙ Ø¨Ø¥Ø¹Ø§Ø¯Ø© ØªÙØ¬ÙÙ Ø±Ø³Ø§ÙØ© ÙÙ ÙØ­Ø§Ø¯Ø«Ø© Ø£Ø®Ø±Ù.</b>\n\n"
        "<b>Ø§ÙØ¨ÙØª ÙØªØ¹Ø±Ù Ø¹ÙÙ ÙÙØ¹ Ø§ÙÙØ­ØªÙÙ ØªÙÙØ§Ø¦ÙØ§Ù.</b>\n\n"
        "<b>ÙÙØ¥ÙØºØ§Ø¡:</b> /cancel",
        parse_mode=ParseMode.HTML
    )


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
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    if message.text:
        return "text"

    return "unknown"


def save_content(section_id, chat_id, message_id, content_type):
    conn = db_connect()

    order = conn.execute("""
        SELECT COALESCE(MAX(sort_order),0)+1
        FROM contents
        WHERE section_id=?
    """, (section_id,)).fetchone()[0]

    cur = conn.execute("""
        INSERT INTO contents
        (section_id,source_chat_id,source_message_id,content_type,sort_order,created_at)
        VALUES (?,?,?,?,?,?)
    """, (
        section_id,
        chat_id,
        message_id,
        content_type,
        order,
        now()
    ))

    content_id = cur.lastrowid

    conn.commit()
    conn.close()

    return content_id


async def ask_edit_content(update, context, content_id):
    conn = db_connect()

    row = conn.execute("""
        SELECT c.*,s.name AS section_name
        FROM contents c
        JOIN sections s ON s.id=c.section_id
        WHERE c.id=?
    """, (content_id,)).fetchone()

    conn.close()

    if not row:
        await update.callback_query.answer(
            "Ø§ÙÙØ´Ø§Ø±ÙØ© ØºÙØ± ÙÙØ¬ÙØ¯Ø©.",
            show_alert=True
        )
        return

    await update.callback_query.edit_message_text(
        f"<b>ð Ø§ÙÙØ´Ø§Ø±ÙØ© #{content_id}</b>\n\n"
        f"<b>Ø§ÙÙØ³Ù:</b> {html.escape(row['section_name'])}\n"
        f"<b>Ø§ÙÙÙØ¹:</b> {html.escape(row['content_type'])}\n\n"
        "<b>Ø§Ø®ØªØ± Ø§ÙØ¹ÙÙÙØ©:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð Ø§Ø³ØªØ¨Ø¯Ø§Ù Ø§ÙÙØ­ØªÙÙ",
                    callback_data=f"CONTENT:REPLACE:{content_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "ð Ø­Ø°Ù Ø§ÙÙØ´Ø§Ø±ÙØ©",
                    callback_data=f"CONTENT:DELETE:{content_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ Ø±Ø¬ÙØ¹",
                    callback_data=f"CONTENT:OPEN:{row['section_id']}"
                )
            ]
        ])
    )


async def replace_content(update, context, content_id):
    context.user_data["state"] = "replace_content"
    context.user_data["replace_content_id"] = content_id

    await update.callback_query.edit_message_text(
        "<b>ð Ø§Ø³ØªØ¨Ø¯Ø§Ù Ø§ÙÙØ´Ø§Ø±ÙØ©</b>\n\n"
        "<b>Ø£Ø±Ø³Ù Ø§ÙÙØ­ØªÙÙ Ø§ÙØ¬Ø¯ÙØ¯ Ø§ÙØ¢Ù.</b>\n\n"
        "<b>ÙØ§ ØªØ­ØªØ§Ø¬ ÙØªØ­Ø¯ÙØ¯ PDF Ø£Ù ØµÙØ±Ø© Ø£Ù ÙÙØ¯ÙÙ.</b>\n"
        "<b>Ø§ÙØ¨ÙØª ÙØªØ¹Ø±Ù Ø¹ÙÙÙ ØªÙÙØ§Ø¦ÙØ§Ù.</b>",
        parse_mode=ParseMode.HTML
    )


async def confirm_delete_content(update, context, content_id):
    conn = db_connect()

    row = conn.execute(
        "SELECT * FROM contents WHERE id=?",
        (content_id,)
    ).fetchone()

    conn.close()

    if not row:
        return

    await update.callback_query.edit_message_text(
        "<b>â ï¸ ØªØ£ÙÙØ¯ Ø­Ø°Ù Ø§ÙÙØ´Ø§Ø±ÙØ©</b>\n\n"
        f"<b>Ø±ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ©:</b> {content_id}\n"
        f"<b>Ø§ÙÙÙØ¹:</b> {html.escape(row['content_type'])}\n\n"
        "<b>ÙÙ ØªØ±ÙØ¯ Ø­Ø°ÙÙØ§Ø</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â ÙØ¹ÙØ Ø­Ø°Ù",
                    callback_data=f"CONTENT:DELETE_YES:{content_id}"
                ),
                InlineKeyboardButton(
                    "â Ø¥ÙØºØ§Ø¡",
                    callback_data=f"CONTENT:EDIT:{content_id}"
                )
            ]
        ])
    )


# ============================================================
# ADMIN STATS
# ============================================================

async def admin_stats(update, context):
    conn = db_connect()

    users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    sections = conn.execute(
        "SELECT COUNT(*) FROM sections"
    ).fetchone()[0]

    contents = conn.execute(
        "SELECT COUNT(*) FROM contents"
    ).fetchone()[0]

    ratings = conn.execute(
        "SELECT COUNT(*) FROM ratings"
    ).fetchone()[0]

    notes = conn.execute(
        "SELECT COUNT(*) FROM notes"
    ).fetchone()[0]

    avg = conn.execute(
        "SELECT AVG(rating) FROM ratings"
    ).fetchone()[0]

    conn.close()

    average = f"{avg:.2f}" if avg else "0"

    await update.callback_query.edit_message_text(
        "<b>ð Ø¥Ø­ØµØ§Ø¦ÙØ§Øª Ø§ÙØ¨ÙØª</b>\n\n"
        f"ð¥ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ: <b>{users}</b>\n"
        f"ð Ø§ÙØ£ÙØ³Ø§Ù: <b>{sections}</b>\n"
        f"ð Ø§ÙÙØ´Ø§Ø±ÙØ§Øª: <b>{contents}</b>\n"
        f"â­ Ø§ÙØªÙÙÙÙØ§Øª: <b>{ratings}</b>\n"
        f"â­ ÙØªÙØ³Ø· Ø§ÙØªÙÙÙÙ: <b>{average}</b>\n"
        f"âï¸ Ø§ÙÙØ±Ø§Ø³ÙØ§Øª: <b>{notes}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


# ============================================================
# ADMIN NOTES
# ============================================================

async def admin_notes(update, context):
    conn = db_connect()

    rows = conn.execute("""
        SELECT
            n.id,
            n.text,
            n.created_at,
            u.first_name,
            u.username,
            s.name AS section_name
        FROM notes n
        LEFT JOIN users u ON u.user_id=n.user_id
        LEFT JOIN sections s ON s.id=n.section_id
        ORDER BY n.id DESC
        LIMIT 15
    """).fetchall()

    conn.close()

    text = "<b>âï¸ Ø¢Ø®Ø± Ø§ÙÙØ±Ø§Ø³ÙØ§Øª</b>\n\n"

    if not rows:
        text += "<b>ÙØ§ ØªÙØ¬Ø¯ ÙØ±Ø§Ø³ÙØ§Øª.</b>"
    else:
        for row in rows:
            name = row["first_name"] or "ÙØ³ØªØ®Ø¯Ù"
            section = row["section_name"] or "Ø¹Ø§Ù"

            short = row["text"][:200]

            text += (
                f"ð <b>{row['id']}</b>\n"
                f"ð¤ <b>{html.escape(name)}</b>\n"
                f"ð <b>{html.escape(section)}</b>\n"
                f"ð {html.escape(short)}\n\n"
            )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


# ============================================================
# ADMIN RATINGS
# ============================================================

async def admin_ratings(update, context):
    conn = db_connect()

    rows = conn.execute("""
        SELECT
            rating,
            COUNT(*) AS total
        FROM ratings
        GROUP BY rating
        ORDER BY rating DESC
    """).fetchall()

    avg = conn.execute(
        "SELECT AVG(rating) FROM ratings"
    ).fetchone()[0]

    conn.close()

    text = (
        "<b>â­ Ø§ÙØªÙÙÙÙØ§Øª</b>\n\n"
        f"<b>Ø§ÙÙØªÙØ³Ø·:</b> "
        f"{avg:.2f}" if avg else
        "<b>Ø§ÙÙØªÙØ³Ø·:</b> 0"
    )

    text += "\n\n"

    for row in rows:
        text += (
            f"{'â­' * row['rating']} "
            f"<b>{row['total']}</b>\n"
        )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


# ============================================================
# ADMIN SETTINGS
# ============================================================

async def admin_settings(update, context):
    welcome = get_setting("welcome_enabled", "1")
    new_users = get_setting("new_user_notifications", "1")
    rating = get_setting("rating_enabled", "1")
    notes = get_setting("notes_enabled", "1")

    def status(v):
        return "ð¢ ÙØ¹ÙÙ" if v == "1" else "ð´ ÙØªÙÙÙ"

    await update.callback_query.edit_message_text(
        "<b>âï¸ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§ÙØ¨ÙØª</b>\n\n"
        f"ð Ø§ÙØªØ±Ø­ÙØ¨: <b>{status(welcome)}</b>\n"
        f"ð Ø¥Ø´Ø¹Ø§Ø± ÙØ³ØªØ®Ø¯Ù Ø¬Ø¯ÙØ¯: <b>{status(new_users)}</b>\n"
        f"â­ Ø§ÙØªÙÙÙÙ: <b>{status(rating)}</b>\n"
        f"âï¸ Ø§ÙÙÙØ§Ø­Ø¸Ø§Øª: <b>{status(notes)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ð Ø§ÙØªØ±Ø­ÙØ¨",
                    callback_data="SETTING:welcome_enabled"
                ),
                InlineKeyboardButton(
                    "ð Ø¥Ø´Ø¹Ø§Ø±Ø§Øª",
                    callback_data="SETTING:new_user_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    "â­ Ø§ÙØªÙÙÙÙ",
                    callback_data="SETTING:rating_enabled"
                ),
                InlineKeyboardButton(
                    "âï¸ Ø§ÙÙÙØ§Ø­Ø¸Ø§Øª",
                    callback_data="SETTING:notes_enabled"
                )
            ],
            [
                InlineKeyboardButton(
                    "â¬ï¸ ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        pass

    user = update.effective_user
    data = query.data

    # --------------------------------------------------------
    # MAIN
    # --------------------------------------------------------

    if data == "MAIN":
        context.user_data.clear()
        await send_main_menu(update, context, edit=True)
        return

    # --------------------------------------------------------
    # CANCEL
    # --------------------------------------------------------

    if data == "CANCEL":
        context.user_data.clear()

        await query.edit_message_text(
            "<b>â ØªÙ Ø§ÙØ¥ÙØºØ§Ø¡.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )
        return

    # --------------------------------------------------------
    # OPEN SECTION
    # --------------------------------------------------------

    if data.startswith("OPEN:"):
        section_id = int(data.split(":")[1])
        await show_section(update, context, section_id, True)
        return

    # --------------------------------------------------------
    # BACK
    # --------------------------------------------------------

    if data.startswith("BACK:"):
        section_id = int(data.split(":")[1])
        section = get_section(section_id)

        if not section or section["parent_id"] is None:
            await send_main_menu(update, context, True)
        else:
            await show_section(
                update,
                context,
                section["parent_id"],
                True
            )
        return

    # --------------------------------------------------------
    # FAVORITE
    # --------------------------------------------------------

    if data.startswith("FAV:"):
        section_id = int(data.split(":")[1])

        result = toggle_favorite(
            user.id,
            section_id
        )

        await query.answer(
            "â­ ØªÙØª Ø§ÙØ¥Ø¶Ø§ÙØ© ÙÙÙÙØ¶ÙØ©."
            if result
            else "ØªÙØª Ø§ÙØ¥Ø²Ø§ÙØ© ÙÙ Ø§ÙÙÙØ¶ÙØ©.",
            show_alert=True
        )

        await show_section(
            update,
            context,
            section_id,
            True
        )
        return

    # --------------------------------------------------------
    # NOTE
    # --------------------------------------------------------

    if data.startswith("NOTE:"):
        section_id = int(data.split(":")[1])
        await start_note(update, context, section_id)
        return

    # --------------------------------------------------------
    # RATE
    # --------------------------------------------------------

    if data.startswith("RATE:"):
        rating = int(data.split(":")[1])
        await save_rating(update, context, rating)
        return

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    if data.startswith("SYS:"):
        key = data.split(":", 1)[1]
        await system_button(update, context, key)
        return

    # --------------------------------------------------------
    # ADMIN HOME
    # --------------------------------------------------------

    if data == "ADMIN:HOME":
        if not is_admin(user.id):
            return

        context.user_data.clear()
        await show_admin(update, context)
        return

    # --------------------------------------------------------
    # ADMIN BUTTONS
    # --------------------------------------------------------

    if data == "ADMIN:BUTTONS":
        if is_admin(user.id):
            await editor_home(update, context)
        return

    # --------------------------------------------------------
    # ADMIN CONTENT
    # --------------------------------------------------------

    if data == "ADMIN:CONTENT":
        if is_admin(user.id):
            await content_editor(update, context)
        return

    # --------------------------------------------------------
    # ADMIN STATS
    # --------------------------------------------------------

    if data == "ADMIN:STATS":
        if is_admin(user.id):
            await admin_stats(update, context)
        return

    # --------------------------------------------------------
    # ADMIN NOTES
    # --------------------------------------------------------

    if data == "ADMIN:NOTES":
        if is_admin(user.id):
            await admin_notes(update, context)
        return

    # --------------------------------------------------------
    # ADMIN RATINGS
    # --------------------------------------------------------

    if data == "ADMIN:RATINGS":
        if is_admin(user.id):
            await admin_ratings(update, context)
        return

    # --------------------------------------------------------
    # ADMIN SETTINGS
    # --------------------------------------------------------

    if data == "ADMIN:SETTINGS":
        if is_admin(user.id):
            await admin_settings(update, context)
        return

    # --------------------------------------------------------
    # ROOT EDITOR
    # --------------------------------------------------------

    if data == "ED:ROOT":
        if is_admin(user.id):
            await edit_root_screen(update, context)
        return

    # --------------------------------------------------------
    # SYSTEM EDITOR
    # --------------------------------------------------------

    if data == "ED:SYSTEM":
        if is_admin(user.id):
            await system_editor(update, context)
        return

    # --------------------------------------------------------
    # SECTION EDITOR
    # --------------------------------------------------------

    if data.startswith("EDSEC:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await edit_section_screen(update, context, section_id)
        return

    # --------------------------------------------------------
    # ADD SECTION
    # --------------------------------------------------------

    if data.startswith("ADD:"):
        if is_admin(user.id):
            value = data.split(":", 1)[1]
            await ask_add_section(
                update,
                context,
                value
            )
        return

    # --------------------------------------------------------
    # RENAME
    # --------------------------------------------------------

    if data.startswith("RENAME:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await ask_rename(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # ICON
    # --------------------------------------------------------

    if data.startswith("ICON:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await ask_icon(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    if data.startswith("DELETE:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await confirm_delete(
                update,
                context,
                section_id
            )
        return

    if data.startswith("DELETE_YES:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            delete_section(section_id)
    
            await query.edit_message_text(
                "<b>â ØªÙ Ø­Ø°Ù Ø§ÙÙØ³Ù ÙÙØ­ØªÙÙØ§ØªÙ Ø¨ÙØ¬Ø§Ø­.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        ),
                        InlineKeyboardButton(
                            "ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                            callback_data="MAIN"
                        )
                    ]
                ])
            )
    
    # --------------------------------------------------------
    # MOVE
    # --------------------------------------------------------

    if data.startswith("MOVE:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await move_screen(
                update,
                context,
                section_id
            )
        return

    if data.startswith("MOVE_TO:"):
        if is_admin(user.id):
            _, source, target = data.split(":")
            await confirm_move(
                update,
                context,
                int(source),
                target
            )
        return

    if data.startswith("MOVE_YES:"):
        if is_admin(user.id):
            _, source, target = data.split(":")
            perform_move(
                int(source),
                target
            )

            await query.edit_message_text(
                "<b>â ØªÙ ÙÙÙ Ø§ÙÙØ³Ù Ø¨ÙØ¬Ø§Ø­.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        )
                    ]
                ])
            )
        return

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    if data.startswith("MERGE:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            await merge_screen(
                update,
                context,
                section_id
            )
        return

    if data.startswith("MERGE_TO:"):
        if is_admin(user.id):
            _, source, target = data.split(":")
            await confirm_merge(
                update,
                context,
                int(source),
                int(target)
            )
        return

    if data.startswith("MERGE_YES:"):
        if is_admin(user.id):
            _, source, target = data.split(":")
            perform_merge(
                int(source),
                int(target)
            )

            await query.edit_message_text(
                "<b>â ØªÙ Ø¯ÙØ¬ Ø§ÙØ£ÙØ³Ø§Ù Ø¨ÙØ¬Ø§Ø­.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        )
                    ]
                ])
            )
        return

    # --------------------------------------------------------
    # REORDER
    # --------------------------------------------------------

    if data.startswith("UP:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            reorder(section_id, "up")
            await edit_section_screen(
                update,
                context,
                section_id
            )
        return

    if data.startswith("DOWN:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])
            reorder(section_id, "down")
            await edit_section_screen(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # TOGGLE
    # --------------------------------------------------------

    if data.startswith("TOGGLE:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[1])

            conn = db_connect()

            conn.execute("""
                UPDATE sections
                SET enabled =
                    CASE
                        WHEN enabled=1 THEN 0
                        ELSE 1
                    END
                WHERE id=?
            """, (section_id,))

            conn.commit()
            conn.close()

            await edit_section_screen(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # CONTENT BROWSE
    # --------------------------------------------------------

    if data.startswith("CONTENT:BROWSE:"):
        if is_admin(user.id):
            value = data.split(":")[-1]
            await content_browse(
                update,
                context,
                value
            )
        return

    if data.startswith("CONTENT:OPEN:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[-1])
            await content_section(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # ADD CONTENT
    # --------------------------------------------------------

    if data.startswith("CONTENT:ADD:"):
        if is_admin(user.id):
            section_id = int(data.split(":")[-1])
            await ask_add_content(
                update,
                context,
                section_id
            )
        return

    # --------------------------------------------------------
    # EDIT CONTENT
    # --------------------------------------------------------

    if data.startswith("CONTENT:EDIT:"):
        if is_admin(user.id):
            content_id = int(data.split(":")[-1])
            await ask_edit_content(
                update,
                context,
                content_id
            )
        return

    # --------------------------------------------------------
    # REPLACE CONTENT
    # --------------------------------------------------------

    if data.startswith("CONTENT:REPLACE:"):
        if is_admin(user.id):
            content_id = int(data.split(":")[-1])
            await replace_content(
                update,
                context,
                content_id
            )
        return

    # --------------------------------------------------------
    # DELETE CONTENT
    # --------------------------------------------------------

    if data.startswith("CONTENT:DELETE:"):
        if is_admin(user.id):
            content_id = int(data.split(":")[-1])
            await confirm_delete_content(
                update,
                context,
                content_id
            )
        return

    if data.startswith("CONTENT:DELETE_YES:"):
        if is_admin(user.id):
            content_id = int(data.split(":")[-1])

            conn = db_connect()

            row = conn.execute("""
                SELECT section_id
                FROM contents
                WHERE id=?
            """, (content_id,)).fetchone()

            section_id = row["section_id"] if row else None

            conn.execute(
                "DELETE FROM contents WHERE id=?",
                (content_id,)
            )

            conn.commit()
            conn.close()

            if section_id:
                await content_section(
                    update,
                    context,
                    section_id
                )
        return

    # --------------------------------------------------------
    # SYSTEM EDIT
    # --------------------------------------------------------

    if data.startswith("SYS_EDIT:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]
            await system_button_edit(
                update,
                context,
                key
            )
        return

    if data.startswith("SYS_RENAME:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]

            context.user_data["state"] = "system_rename"
            context.user_data["system_key"] = key

            await query.edit_message_text(
                "<b>âï¸ Ø£Ø±Ø³Ù Ø§ÙØ§Ø³Ù Ø§ÙØ¬Ø¯ÙØ¯ ÙÙØ²Ø±:</b>\n\n"
                "<b>ÙÙØ¥ÙØºØ§Ø¡:</b> /cancel",
                parse_mode=ParseMode.HTML
            )
        return

    if data.startswith("SYS_ICON:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]

            context.user_data["state"] = "system_icon"
            context.user_data["system_key"] = key

            await query.edit_message_text(
                "<b>ð¨ Ø£Ø±Ø³Ù Ø§ÙØ£ÙÙÙÙØ© Ø§ÙØ¬Ø¯ÙØ¯Ø©:</b>",
                parse_mode=ParseMode.HTML
            )
        return

    if data.startswith("SYS_TOGGLE:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]

            conn = db_connect()

            conn.execute("""
                UPDATE system_buttons
                SET enabled =
                    CASE
                        WHEN enabled=1 THEN 0
                        ELSE 1
                    END
                WHERE button_key=?
            """, (key,))

            conn.commit()
            conn.close()

            await system_button_edit(
                update,
                context,
                key
            )
        return

    if data.startswith("SYS_UP:") or data.startswith("SYS_DOWN:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]
            direction = (
                "up"
                if data.startswith("SYS_UP:")
                else "down"
            )

            conn = db_connect()

            rows = conn.execute("""
                SELECT *
                FROM system_buttons
                ORDER BY sort_order,id
            """).fetchall()

            index = next(
                (
                    i for i, row in enumerate(rows)
                    if row["button_key"] == key
                ),
                None
            )

            if index is not None:
                other_index = (
                    index - 1
                    if direction == "up"
                    else index + 1
                )

                if 0 <= other_index < len(rows):
                    a = rows[index]
                    b = rows[other_index]

                    conn.execute("""
                        UPDATE system_buttons
                        SET sort_order=?
                        WHERE button_key=?
                    """, (
                        b["sort_order"],
                        a["button_key"]
                    ))

                    conn.execute("""
                        UPDATE system_buttons
                        SET sort_order=?
                        WHERE button_key=?
                    """, (
                        a["sort_order"],
                        b["button_key"]
                    ))

                    conn.commit()

            conn.close()

            await system_button_edit(
                update,
                context,
                key
            )
        return

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    if data.startswith("SETTING:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]

            current = get_setting(key, "1")

            set_setting(
                key,
                "0" if current == "1" else "1"
            )

            await admin_settings(
                update,
                context
            )
        return


# ============================================================
# TEXT / CONTENT HANDLER
# ============================================================

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message:
        return

    state = context.user_data.get("state")

    # --------------------------------------------------------
    # CANCEL
    # --------------------------------------------------------

    if update.message.text == "/cancel":
        context.user_data.clear()

        await update.message.reply_text(
            "<b>â ØªÙ Ø¥ÙØºØ§Ø¡ Ø§ÙØ¹ÙÙÙØ©.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=(
                admin_keyboard()
                if is_admin(user.id)
                else main_keyboard(user.id)
            )
        )
        return

    # --------------------------------------------------------
    # ADMIN ONLY
    # --------------------------------------------------------

    if state and is_admin(user.id):

        # ----------------------------------------------------
        # ADD SECTION
        # ----------------------------------------------------

        if state == "add_section":
            if not update.message.text:
                await update.message.reply_text(
                    "<b>Ø£Ø±Ø³Ù Ø§Ø³Ù Ø§ÙÙØ³Ù ÙÙØµ.</b>",
                    parse_mode=ParseMode.HTML
                )
                return

            name = update.message.text.strip()

            if not name:
                return

            parent_id = context.user_data["parent_id"]

            section_id = create_section(
                parent_id,
                name
            )

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ Ø¥ÙØ´Ø§Ø¡ Ø§ÙÙØ³Ù Ø¨ÙØ¬Ø§Ø­.</b>\n\n"
                f"<b>{html.escape(name)}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        ),
                        InlineKeyboardButton(
                            "ð  Ø§ÙØ±Ø¦ÙØ³ÙØ©",
                            callback_data="MAIN"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # RENAME
        # ----------------------------------------------------

        if state == "rename_section":
            name = (
                update.message.text or ""
            ).strip()

            if not name:
                return

            section_id = context.user_data["section_id"]

            conn = db_connect()

            conn.execute("""
                UPDATE sections
                SET name=?
                WHERE id=?
            """, (
                name,
                section_id
            ))

            conn.commit()
            conn.close()

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙÙØ³Ù.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # ICON
        # ----------------------------------------------------

        if state == "icon_section":
            icon = (
                update.message.text or ""
            ).strip()

            if not icon:
                return

            section_id = context.user_data["section_id"]

            conn = db_connect()

            conn.execute("""
                UPDATE sections
                SET icon=?
                WHERE id=?
            """, (
                icon[:10],
                section_id
            ))

            conn.commit()
            conn.close()

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ ØªØ¹Ø¯ÙÙ Ø§ÙØ£ÙÙÙÙØ©.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð§© ÙØ­Ø±Ø± Ø§ÙØ£Ø²Ø±Ø§Ø±",
                            callback_data="ADMIN:BUTTONS"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # ADD CONTENT
        # ----------------------------------------------------

        if state == "add_content":
            section_id = context.user_data[
                "content_section_id"
            ]

            content_type = detect_content_type(
                update.message
            )

            content_id = save_content(
                section_id,
                update.message.chat_id,
                update.message.message_id,
                content_type
            )

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ Ø­ÙØ¸ Ø§ÙÙØ´Ø§Ø±ÙØ©.</b>\n\n"
                f"<b>Ø§ÙÙÙØ¹:</b> {html.escape(content_type)}\n"
                f"<b>Ø±ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ©:</b> {content_id}\n\n"
                "<b>Ø¹ÙØ¯ Ø¶ØºØ· Ø§ÙÙØ³ØªØ®Ø¯Ù Ø¹ÙÙ Ø§ÙÙØ³ÙØ "
                "Ø³ÙØªÙ Ø¥Ø±Ø³Ø§Ù Ø§ÙÙØ­ØªÙÙ ØªÙÙØ§Ø¦ÙØ§Ù.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð ØªØ¹Ø¯ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª",
                            callback_data="ADMIN:CONTENT"
                        ),
                        InlineKeyboardButton(
                            "ð ÙÙØ­Ø© Ø§ÙØ¥Ø¯Ø§Ø±Ø©",
                            callback_data="ADMIN:HOME"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # REPLACE CONTENT
        # ----------------------------------------------------

        if state == "replace_content":
            content_id = context.user_data[
                "replace_content_id"
            ]

            content_type = detect_content_type(
                update.message
            )

            conn = db_connect()

            conn.execute("""
                UPDATE contents
                SET source_chat_id=?,
                    source_message_id=?,
                    content_type=?
                WHERE id=?
            """, (
                update.message.chat_id,
                update.message.message_id,
                content_type,
                content_id
            ))

            conn.commit()
            conn.close()

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ Ø§Ø³ØªØ¨Ø¯Ø§Ù Ø§ÙÙØ­ØªÙÙ Ø¨ÙØ¬Ø§Ø­.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "ð ØªØ¹Ø¯ÙÙ Ø§ÙÙØ´Ø§Ø±ÙØ§Øª",
                            callback_data="ADMIN:CONTENT"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # SYSTEM RENAME
        # ----------------------------------------------------

        if state == "system_rename":
            label = (
                update.message.text or ""
            ).strip()

            key = context.user_data["system_key"]

            if label:
                conn = db_connect()

                conn.execute("""
                    UPDATE system_buttons
                    SET label=?
                    WHERE button_key=?
                """, (
                    label,
                    key
                ))

                conn.commit()
                conn.close()

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ ØªØ¹Ø¯ÙÙ Ø§Ø³Ù Ø§ÙØ²Ø±.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "âï¸ Ø£Ø²Ø±Ø§Ø± Ø§ÙÙØ¸Ø§Ù",
                            callback_data="ED:SYSTEM"
                        )
                    ]
                ])
            )
            return

        # ----------------------------------------------------
        # SYSTEM ICON
        # ----------------------------------------------------

        if state == "system_icon":
            icon = (
                update.message.text or ""
            ).strip()

            key = context.user_data["system_key"]

            if icon:
                conn = db_connect()

                conn.execute("""
                    UPDATE system_buttons
                    SET icon=?
                    WHERE button_key=?
                """, (
                    icon[:10],
                    key
                ))

                conn.commit()
                conn.close()

            context.user_data.clear()

            await update.message.reply_text(
                "<b>â ØªÙ ØªØ¹Ø¯ÙÙ Ø£ÙÙÙÙØ© Ø§ÙØ²Ø±.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "âï¸ Ø£Ø²Ø±Ø§Ø± Ø§ÙÙØ¸Ø§Ù",
                            callback_data="ED:SYSTEM"
                        )
                    ]
                ])
            )
            return

    # --------------------------------------------------------
    # USER SECTION NOTE
    # --------------------------------------------------------

    if state == "section_note":
        section_id = context.user_data.get(
            "note_section_id"
        )

        if not update.message.text:
            await update.message.reply_text(
                "<b>Ø£Ø±Ø³Ù Ø§ÙÙÙØ§Ø­Ø¸Ø© ÙÙØµ.</b>",
                parse_mode=ParseMode.HTML
            )
            return

        await save_note(
            update,
            context,
            section_id,
            update.message.text
        )
        return

    # --------------------------------------------------------
    # GLOBAL NOTE
    # --------------------------------------------------------

    if state == "global_note":
        if not update.message.text:
            await update.message.reply_text(
                "<b>Ø£Ø±Ø³Ù Ø§ÙØ±Ø³Ø§ÙØ© ÙÙØµ.</b>",
                parse_mode=ParseMode.HTML
            )
            return

        conn = db_connect()

        conn.execute("""
            INSERT INTO notes
            (user_id,section_id,text,created_at)
            VALUES (?,?,?,?)
        """, (
            user.id,
            None,
            update.message.text,
            now()
        ))

        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(
                ADMIN_ID,
                (
                    "âï¸ <b>Ø±Ø³Ø§ÙØ© Ø¬Ø¯ÙØ¯Ø© ÙÙ Ø§ÙÙØ³ØªØ®Ø¯ÙÙÙ</b>\n\n"
                    f"ð¤ <b>{html.escape(user.full_name)}</b>\n"
                    f"ð <code>{user.id}</code>\n\n"
                    f"ð {html.escape(update.message.text)}"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("Global note error: %s", e)

        context.user_data.clear()

        await update.message.reply_text(
            "<b>â ÙØµÙØª Ø±Ø³Ø§ÙØªÙ Ø¥ÙÙ Ø§ÙØ¥Ø¯Ø§Ø±Ø©.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )
        return


# ============================================================
# /ADMIN COMMAND
# ============================================================

async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "<b>â ØºÙØ± ÙØ³ÙÙØ­.</b>",
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data.clear()

    await show_admin(update, context)


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):
    logger.exception(
        "Exception while handling update:",
        exc_info=context.error
    )


# ============================================================
# START APPLICATION
# ============================================================

def main():
    db_init()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin_command)
    )

    application.add_handler(
        CallbackQueryHandler(callbacks)
    )

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            messages
        )
    )

    application.add_error_handler(error_handler)

    # --------------------------------------------------------
    # WEBHOOK - Render
    # --------------------------------------------------------
    #
    # ÙÙÙ:
    # ÙØ°Ø§ Ø§ÙÙÙØ¯ ÙØ§ ÙØ³ØªØ®Ø¯Ù polling / getUpdates.
    # ÙØ°ÙÙ ÙÙÙØ¹ ÙØ´ÙÙØ©:
    #
    # telegram.error.Conflict:
    # terminated by other getUpdates request
    #
    # Ø¨Ø´Ø±Ø· Ø£Ù ØªÙÙÙ ÙÙØ§Ù ÙØ³Ø®Ø© ÙØ§Ø­Ø¯Ø© ÙÙØ· ÙÙ Ø§ÙØ®Ø¯ÙØ© Ø¹ÙÙ Render.
    # --------------------------------------------------------

    if not RENDER_URL:
        raise RuntimeError(
            "RENDER_EXTERNAL_URL ØºÙØ± ÙÙØ¬ÙØ¯. "
            "ÙØ°Ø§ Ø§ÙÙÙØ¯ ÙØ®ØµØµ ÙÙØªØ´ØºÙÙ Ø¹ÙÙ Render Web Service."
        )

    webhook_url = (
        f"{RENDER_URL}/{WEBHOOK_SECRET}"
    )

    logger.info(
        "Starting webhook: %s",
        webhook_url
    )

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_SECRET,
        webhook_url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
