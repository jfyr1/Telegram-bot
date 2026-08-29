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
        "BOT_TOKEN غير موجود. أضفه في Environment Variables في Render."
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
            icon TEXT DEFAULT '📁',
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
            icon TEXT DEFAULT '🔘',
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
        ("favorites", "المفضلة", "⭐", 10, 1, 0),
        ("popular", "الأكثر دخولاً", "📊", 20, 1, 0),
        ("rating", "تقييم البوت", "⭐", 30, 1, 0),
        ("about", "حول البوت", "ℹ️", 40, 1, 0),
        ("contact", "مراسلة الإدارة", "✉️", 50, 1, 0),
        ("admin", "لوحة الإدارة", "🔐", 100, 1, 1),
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
        """, (0, "المرحلة الأولى", "🎓", 1, now))

        stage1 = cur.lastrowid

        cur.execute("""
            INSERT INTO sections
            (parent_id,name,icon,sort_order,enabled,created_at)
            VALUES (?,?,?,?,?,?)
        """, (
            stage1,
            "الكورس الأول",
            "📚",
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
            "الكورس الثاني",
            "📚",
            2,
            1,
            now,
        ))

        course2 = cur.lastrowid

        # مواد افتراضية
        subjects1 = [
            ("رياضيات", "📐"),
            ("برمجة", "💻"),
            ("دوائر كهربائية", "⚡"),
            ("أساسيات الحاسوب", "🖥️"),
        ]

        subjects2 = [
            ("الرياضيات", "📐"),
            ("البرمجة", "💻"),
            ("الإلكترونيات", "🔌"),
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

    if "رياض" in name:
        return "📐"
    if "برمج" in name:
        return "💻"
    if "حاسوب" in name:
        return "🖥️"
    if "كهرب" in name:
        return "⚡"
    if "إلكتر" in name:
        return "🔌"
    if "محاض" in name:
        return "📖"
    if "كورس" in name:
        return "📚"
    if "ملخص" in name:
        return "📝"
    if "مرحلة" in name:
        return "🎓"

    return "📁"


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
    return "  ›  ".join(path)


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
        "💛 إزالة من المفضلة"
        if is_favorite(user_id, section_id)
        else "⭐ إضافة إلى المفضلة"
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
                "✉️ ملاحظة بخصوص هذا القسم",
                callback_data=f"NOTE:{section_id}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data="MAIN"
        ),
        InlineKeyboardButton(
            "⬅️ الرجوع",
            callback_data=f"BACK:{section_id}"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            f"🚪 خروج من {get_section(section_id)['name']}",
            callback_data="MAIN"
        )
    ])

    return InlineKeyboardMarkup(rows)


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🧩 محرر الأزرار",
                callback_data="ADMIN:BUTTONS"
            ),
            InlineKeyboardButton(
                "📝 تعديل المشاركات",
                callback_data="ADMIN:CONTENT"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 الإحصائيات",
                callback_data="ADMIN:STATS"
            ),
            InlineKeyboardButton(
                "✉️ المراسلات",
                callback_data="ADMIN:NOTES"
            )
        ],
        [
            InlineKeyboardButton(
                "⭐ التقييمات",
                callback_data="ADMIN:RATINGS"
            ),
            InlineKeyboardButton(
                "⚙️ إعدادات البوت",
                callback_data="ADMIN:SETTINGS"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
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
        "🤖 <b>المساعد الذكي</b>\n\n"
        "📚 <b>اختر القسم الذي تريد الدخول إليه:</b>"
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
            bold("القسم غير موجود."),
            parse_mode=ParseMode.HTML
        )
        return

    record_visit(user.id, section_id)

    children = get_children(section_id)
    contents = get_contents(section_id)

    title = f"{section['icon']} {section['name']}"

    text = (
        f"<b>{html.escape(title)}</b>\n\n"
        f"<b>المسار:</b> {html.escape(path_text(section_id))}\n\n"
    )

    if children:
        text += "<b>اختر من الأقسام التالية:</b>"
    elif contents:
        text += "<b>المحتوى المتوفر لهذا القسم سيظهر أسفل هذه الواجهة.</b>"
    else:
        text += "<b>لا يوجد محتوى داخل هذا القسم حالياً.</b>"

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

    # إرسال المحتوى المخزن
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
                else "بدون معرف"
            )

            await context.bot.send_message(
                ADMIN_ID,
                (
                    "🆕 <b>مستخدم جديد دخل البوت</b>\n\n"
                    f"👤 الاسم: <b>{html.escape(user.full_name)}</b>\n"
                    f"🔹 المعرف: <b>{html.escape(username)}</b>\n"
                    f"🆔 ID: <code>{user.id}</code>"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("New user notification error: %s", e)

    if get_setting("welcome_enabled", "1") == "1":
        text = (
            "👋 <b>أهلاً وسهلاً بك في المساعد الذكي</b>\n\n"
            "📚 <b>اختر القسم الذي تريد الدخول إليه.</b>"
        )
    else:
        text = "<b>القائمة الرئيسية</b>"

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
            "<b>✉️ مراسلة الإدارة</b>\n\n"
            "<b>أرسل رسالتك الآن، وستصل إلى الإدارة مباشرة.</b>\n\n"
            "<b>للإلغاء:</b> /cancel",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="CANCEL"
                    )
                ]
            ])
        )

    elif key == "admin":
        if not is_admin(user.id):
            await query.answer(
                "غير مسموح لك بالدخول.",
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
            "🏠 القائمة الرئيسية",
            callback_data="MAIN"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>⭐ المفضلة</b>\n\n"
        + (
            "<b>الأقسام المحفوظة:</b>"
            if rows
            else "<b>لا توجد أقسام في المفضلة حالياً.</b>"
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
                f"{row['icon']} {row['name']} — {row['total']} زيارة",
                callback_data=f"OPEN:{row['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "🏠 القائمة الرئيسية",
            callback_data="MAIN"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>📊 الأكثر دخولاً</b>\n\n"
        "<b>أكثر الأقسام زيارة:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_rating(update, context):
    await update.callback_query.edit_message_text(
        "<b>⭐ تقييم البوت</b>\n\n"
        "<b>اختر تقييمك:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐", callback_data="RATE:1"),
                InlineKeyboardButton("⭐⭐", callback_data="RATE:2"),
                InlineKeyboardButton("⭐⭐⭐", callback_data="RATE:3"),
            ],
            [
                InlineKeyboardButton("⭐⭐⭐⭐", callback_data="RATE:4"),
                InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="RATE:5"),
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data="MAIN"
                )
            ]
        ])
    )


async def show_about(update, context):
    text = (
        "<b>ℹ️ حول البوت</b>\n\n"
        "<b>📚 فهرس الاستخدام:</b>\n\n"
        "1️⃣ <b>القائمة الرئيسية</b>\n"
        "منها تدخل إلى جميع الأقسام الرئيسية.\n\n"
        "2️⃣ <b>الأقسام الفرعية</b>\n"
        "كل قسم يمكن أن يحتوي على أقسام أخرى حتى أي مستوى.\n\n"
        "3️⃣ <b>المحتوى</b>\n"
        "المحاضرات يمكن أن تحتوي PDF أو صورة أو فيديو "
        "أو ملف أو صوت أو أي محتوى يسمح به Telegram.\n\n"
        "4️⃣ <b>المفضلة</b>\n"
        "احفظ الأقسام التي تدخل إليها كثيراً.\n\n"
        "5️⃣ <b>الأكثر دخولاً</b>\n"
        "يعرض الأقسام الأكثر زيارة.\n\n"
        "6️⃣ <b>مراسلة الإدارة</b>\n"
        "يمكن إرسال ملاحظة أو مشكلة إلى الإدارة.\n\n"
        "7️⃣ <b>تقييم البوت</b>\n"
        "يمكنك تقييم البوت من نجمة إلى خمس نجوم.\n\n"
        "8️⃣ <b>لوحة الإدارة</b>\n"
        "الإدارة تستطيع إنشاء وتعديل ونقل ودمج وحذف الأقسام، "
        "وتعديل الأزرار والمحتوى.\n\n"
        "<b>🎯 الهدف:</b>\n"
        "تنظيم المحاضرات والملفات بطريقة سهلة وسريعة."
    )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
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
        "تم حفظ تقييمك ❤️",
        show_alert=True
    )

    await update.callback_query.edit_message_text(
        f"<b>شكراً لك ❤️</b>\n\n"
        f"<b>تقييمك:</b> {'⭐' * rating}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
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
        f"<b>✉️ ملاحظة عن قسم: "
        f"{html.escape(section['name'])}</b>\n\n"
        "<b>أرسل الملاحظة الآن.</b>\n\n"
        "<b>للإلغاء:</b> /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ إلغاء",
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
                "✉️ <b>ملاحظة جديدة</b>\n\n"
                f"🆔 رقم: <code>{note_id}</code>\n"
                f"👤 المستخدم: <b>{html.escape(user.full_name)}</b>\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📂 القسم: <b>{html.escape(section['name'])}</b>\n\n"
                f"📝 <b>الملاحظة:</b>\n"
                f"{html.escape(text)}"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error("Note notification error: %s", e)

    context.user_data.clear()

    await update.message.reply_text(
        "<b>✅ تم إرسال ملاحظتك إلى الإدارة.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )


# ============================================================
# ADMIN
# ============================================================

async def show_admin(update, context):
    text = (
        "🔐 <b>لوحة الإدارة</b>\n\n"
        "<b>اختر العملية المطلوبة:</b>"
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
        "<b>🧩 محرر الأزرار</b>\n\n"
        "<b>هنا تستطيع التحكم بكل الأقسام والأزرار.</b>\n\n"
        "يمكنك:\n"
        "➕ إضافة قسم\n"
        "✏️ تعديل الاسم\n"
        "🎨 تعديل الأيقونة\n"
        "↕️ تغيير الترتيب\n"
        "📦 نقل القسم\n"
        "🔗 دمج الأقسام\n"
        "🗑 حذف القسم\n"
        "👁 إخفاء/إظهار القسم",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🏠 تعديل الواجهة الرئيسية",
                    callback_data="ED:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "➕ إضافة قسم رئيسي",
                    callback_data="ADD:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "⚙️ أزرار النظام",
                    callback_data="ED:SYSTEM"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
                    callback_data="ADMIN:HOME"
                )
            ]
        ])
    )


async def edit_section_screen(update, context, section_id):
    section = get_section(section_id)

    if not section:
        await update.callback_query.answer(
            "القسم غير موجود.",
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
                "➕ إضافة قسم داخل هذا القسم",
                callback_data=f"ADD:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ تعديل اسم القسم",
                callback_data=f"RENAME:{section_id}"
            ),
            InlineKeyboardButton(
                "🎨 تعديل الأيقونة",
                callback_data=f"ICON:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📦 نقل القسم",
                callback_data=f"MOVE:{section_id}"
            ),
            InlineKeyboardButton(
                "🔗 دمج القسم",
                callback_data=f"MERGE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬆️ رفع",
                callback_data=f"UP:{section_id}"
            ),
            InlineKeyboardButton(
                "⬇️ تنزيل",
                callback_data=f"DOWN:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "👁 إظهار/إخفاء",
                callback_data=f"TOGGLE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑 حذف القسم",
                callback_data=f"DELETE:{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ محرر الأزرار",
                callback_data="ADMIN:BUTTONS"
            )
        ]
    ])

    await update.callback_query.edit_message_text(
        f"<b>🧩 تحرير:</b> "
        f"{html.escape(section['icon'])} "
        f"{html.escape(section['name'])}\n\n"
        f"<b>المسار:</b> "
        f"{html.escape(path_text(section_id))}\n\n"
        "<b>الأقسام الموجودة داخل هذا القسم:</b>",
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
            "➕ إضافة قسم رئيسي",
            callback_data="ADD:ROOT"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "⚙️ أزرار النظام",
            callback_data="ED:SYSTEM"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ محرر الأزرار",
            callback_data="ADMIN:BUTTONS"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>🏠 تحرير الواجهة الرئيسية</b>\n\n"
        "<b>اختر القسم الذي تريد تعديله:</b>",
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
        location = "الواجهة الرئيسية"
    else:
        parent = get_section(parent_id)
        location = parent["name"] if parent else "القسم"

    await update.callback_query.edit_message_text(
        f"<b>➕ إضافة قسم جديد داخل: "
        f"{html.escape(location)}</b>\n\n"
        "<b>أرسل اسم القسم الآن.</b>\n\n"
        "<b>مثال:</b>\n"
        "<b>المحاضرة الأولى</b>\n\n"
        "<b>للإلغاء:</b> /cancel",
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
        f"<b>✏️ تعديل اسم القسم الحالي:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>أرسل الاسم الجديد:</b>",
        parse_mode=ParseMode.HTML
    )


async def ask_icon(update, context, section_id):
    context.user_data["state"] = "icon_section"
    context.user_data["section_id"] = section_id

    section = get_section(section_id)

    await update.callback_query.edit_message_text(
        f"<b>🎨 تعديل أيقونة:</b>\n\n"
        f"<b>{html.escape(section['name'])}</b>\n"
        f"<b>الأيقونة الحالية:</b> {section['icon']}\n\n"
        "<b>أرسل الإيموجي الجديد:</b>",
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
        "<b>⚠️ تأكيد الحذف</b>\n\n"
        f"القسم: <b>{html.escape(section['name'])}</b>\n"
        f"الأقسام داخله: <b>{children}</b>\n"
        f"المشاركات: <b>{contents}</b>\n\n"
        "<b>الحذف سيحذف القسم ومحتوياته.</b>\n"
        "<b>هل أنت متأكد؟</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ نعم، حذف",
                    callback_data=f"DELETE_YES:{section_id}"
                ),
                InlineKeyboardButton(
                    "❌ إلغاء",
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
                "🏠 الواجهة الرئيسية",
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
            "❌ إلغاء",
            callback_data=f"EDSEC:{section_id}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>📦 نقل القسم:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>اختر القسم الجديد الذي سيكون بداخله:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_move(update, context, source_id, target_id):
    source = get_section(source_id)

    if target_id == "ROOT":
        target_name = "الواجهة الرئيسية"
    else:
        target = get_section(int(target_id))
        target_name = target["name"]

    await update.callback_query.edit_message_text(
        "<b>⚠️ تأكيد النقل</b>\n\n"
        f"<b>القسم:</b> {html.escape(source['name'])}\n"
        f"<b>إلى:</b> {html.escape(target_name)}\n\n"
        "<b>هل تريد تنفيذ النقل؟</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ تأكيد النقل",
                    callback_data=f"MOVE_YES:{source_id}:{target_id}"
                ),
                InlineKeyboardButton(
                    "❌ إلغاء",
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
            "❌ إلغاء",
            callback_data=f"EDSEC:{source_id}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>🔗 دمج القسم:</b>\n"
        f"<b>{html.escape(source['name'])}</b>\n\n"
        "<b>اختر القسم الذي سيتم الدمج بداخله:</b>\n\n"
        "<b>سيتم نقل الأقسام والمشاركات ثم حذف القسم الأصلي.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_merge(update, context, source_id, target_id):
    source = get_section(source_id)
    target = get_section(target_id)

    await update.callback_query.edit_message_text(
        "<b>⚠️ تأكيد الدمج</b>\n\n"
        f"<b>المصدر:</b> {html.escape(source['name'])}\n"
        f"<b>الهدف:</b> {html.escape(target['name'])}\n\n"
        "<b>سيتم نقل محتوى المصدر إلى الهدف، "
        "ثم حذف المصدر.</b>\n\n"
        "<b>هل تريد المتابعة؟</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ نعم، دمج",
                    callback_data=f"MERGE_YES:{source_id}:{target_id}"
                ),
                InlineKeyboardButton(
                    "❌ إلغاء",
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
        status = "🟢" if row["enabled"] else "🔴"

        buttons.append([
            InlineKeyboardButton(
                f"{status} {row['icon']} {row['label']}",
                callback_data=f"SYS_EDIT:{row['button_key']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ محرر الأزرار",
            callback_data="ADMIN:BUTTONS"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>⚙️ محرر أزرار النظام</b>\n\n"
        "<b>يمكنك تعديل اسم الزر وأيقونته وترتيبه وإظهاره أو إخفاءه.</b>",
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
        f"<b>🧩 تعديل زر:</b>\n\n"
        f"{row['icon']} <b>{html.escape(row['label'])}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✏️ تعديل الاسم",
                    callback_data=f"SYS_RENAME:{key}"
                ),
                InlineKeyboardButton(
                    "🎨 تعديل الأيقونة",
                    callback_data=f"SYS_ICON:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "👁 إظهار/إخفاء",
                    callback_data=f"SYS_TOGGLE:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬆️ رفع",
                    callback_data=f"SYS_UP:{key}"
                ),
                InlineKeyboardButton(
                    "⬇️ تنزيل",
                    callback_data=f"SYS_DOWN:{key}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
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
        "<b>📝 تعديل المشاركات</b>\n\n"
        "<b>اختر القسم الذي تريد إدارة محتواه.</b>\n\n"
        "📄 PDF\n"
        "🖼 صورة\n"
        "🎬 فيديو\n"
        "📎 ملف\n"
        "🎵 صوت\n"
        "💬 نص\n"
        "وأي نوع محتوى يسمح به Telegram.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📂 اختيار القسم",
                    callback_data="CONTENT:BROWSE:ROOT"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
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
                "➕ إضافة مشاركة لهذا القسم",
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
            "⬅️ رجوع",
            callback_data="ADMIN:CONTENT"
        )
    ])

    await update.callback_query.edit_message_text(
        "<b>📂 اختر القسم:</b>",
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
                "➕ إضافة مشاركة",
                callback_data=f"CONTENT:ADD:{section_id}"
            )
        ]
    ]

    for item in contents:
        buttons.append([
            InlineKeyboardButton(
                f"📝 مشاركة #{item['id']} — {item['content_type']}",
                callback_data=f"CONTENT:EDIT:{item['id']}"
            )
        ])

    for child in children:
        buttons.append([
            InlineKeyboardButton(
                f"📁 {child['name']}",
                callback_data=f"CONTENT:OPEN:{child['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ رجوع",
            callback_data=f"CONTENT:BROWSE:{section['parent_id'] if section['parent_id'] is not None else 'ROOT'}"
        )
    ])

    await update.callback_query.edit_message_text(
        f"<b>📝 محتوى:</b> "
        f"{html.escape(section['name'])}\n\n"
        f"<b>عدد المشاركات:</b> {len(contents)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def ask_add_content(update, context, section_id):
    section = get_section(section_id)

    context.user_data["state"] = "add_content"
    context.user_data["content_section_id"] = section_id

    await update.callback_query.edit_message_text(
        f"<b>➕ إضافة مشاركة إلى:</b>\n"
        f"<b>{html.escape(section['name'])}</b>\n\n"
        "<b>أرسل الآن المحتوى نفسه.</b>\n\n"
        "يمكنك إرسال:\n"
        "📄 PDF\n"
        "🖼 صورة\n"
        "🎬 فيديو\n"
        "📎 ملف\n"
        "🎵 صوت\n"
        "💬 نص\n\n"
        "<b>أو قم بإعادة توجيه رسالة من محادثة أخرى.</b>\n\n"
        "<b>البوت يتعرف على نوع المحتوى تلقائياً.</b>\n\n"
        "<b>للإلغاء:</b> /cancel",
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
            "المشاركة غير موجودة.",
            show_alert=True
        )
        return

    await update.callback_query.edit_message_text(
        f"<b>📝 المشاركة #{content_id}</b>\n\n"
        f"<b>القسم:</b> {html.escape(row['section_name'])}\n"
        f"<b>النوع:</b> {html.escape(row['content_type'])}\n\n"
        "<b>اختر العملية:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 استبدال المحتوى",
                    callback_data=f"CONTENT:REPLACE:{content_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 حذف المشاركة",
                    callback_data=f"CONTENT:DELETE:{content_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data=f"CONTENT:OPEN:{row['section_id']}"
                )
            ]
        ])
    )


async def replace_content(update, context, content_id):
    context.user_data["state"] = "replace_content"
    context.user_data["replace_content_id"] = content_id

    await update.callback_query.edit_message_text(
        "<b>🔄 استبدال المشاركة</b>\n\n"
        "<b>أرسل المحتوى الجديد الآن.</b>\n\n"
        "<b>لا تحتاج لتحديد PDF أو صورة أو فيديو.</b>\n"
        "<b>البوت يتعرف عليه تلقائياً.</b>",
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
        "<b>⚠️ تأكيد حذف المشاركة</b>\n\n"
        f"<b>رقم المشاركة:</b> {content_id}\n"
        f"<b>النوع:</b> {html.escape(row['content_type'])}\n\n"
        "<b>هل تريد حذفها؟</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ نعم، حذف",
                    callback_data=f"CONTENT:DELETE_YES:{content_id}"
                ),
                InlineKeyboardButton(
                    "❌ إلغاء",
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
        "<b>📊 إحصائيات البوت</b>\n\n"
        f"👥 المستخدمون: <b>{users}</b>\n"
        f"📂 الأقسام: <b>{sections}</b>\n"
        f"📝 المشاركات: <b>{contents}</b>\n"
        f"⭐ التقييمات: <b>{ratings}</b>\n"
        f"⭐ متوسط التقييم: <b>{average}</b>\n"
        f"✉️ المراسلات: <b>{notes}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
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

    text = "<b>✉️ آخر المراسلات</b>\n\n"

    if not rows:
        text += "<b>لا توجد مراسلات.</b>"
    else:
        for row in rows:
            name = row["first_name"] or "مستخدم"
            section = row["section_name"] or "عام"

            short = row["text"][:200]

            text += (
                f"🆔 <b>{row['id']}</b>\n"
                f"👤 <b>{html.escape(name)}</b>\n"
                f"📂 <b>{html.escape(section)}</b>\n"
                f"📝 {html.escape(short)}\n\n"
            )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
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
        "<b>⭐ التقييمات</b>\n\n"
        f"<b>المتوسط:</b> "
        f"{avg:.2f}" if avg else
        "<b>المتوسط:</b> 0"
    )

    text += "\n\n"

    for row in rows:
        text += (
            f"{'⭐' * row['rating']} "
            f"<b>{row['total']}</b>\n"
        )

    await update.callback_query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
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
        return "🟢 يعمل" if v == "1" else "🔴 متوقف"

    await update.callback_query.edit_message_text(
        "<b>⚙️ إعدادات البوت</b>\n\n"
        f"👋 الترحيب: <b>{status(welcome)}</b>\n"
        f"🆕 إشعار مستخدم جديد: <b>{status(new_users)}</b>\n"
        f"⭐ التقييم: <b>{status(rating)}</b>\n"
        f"✉️ الملاحظات: <b>{status(notes)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👋 الترحيب",
                    callback_data="SETTING:welcome_enabled"
                ),
                InlineKeyboardButton(
                    "🆕 إشعارات",
                    callback_data="SETTING:new_user_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    "⭐ التقييم",
                    callback_data="SETTING:rating_enabled"
                ),
                InlineKeyboardButton(
                    "✉️ الملاحظات",
                    callback_data="SETTING:notes_enabled"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ لوحة الإدارة",
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
            "<b>❌ تم الإلغاء.</b>",
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
            "⭐ تمت الإضافة للمفضلة."
            if result
            else "تمت الإزالة من المفضلة.",
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
                "<b>✅ تم حذف القسم ومحتوياته.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
                            callback_data="ADMIN:BUTTONS"
                        ],
                        InlineKeyboardButton(
                            "🏠 الرئيسية",
                            callback_data="MAIN"
                        )
                    ]
                ])
            )
        return

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
                "<b>✅ تم نقل القسم بنجاح.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
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
                "<b>✅ تم دمج الأقسام بنجاح.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
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
                "<b>✏️ أرسل الاسم الجديد للزر:</b>\n\n"
                "<b>للإلغاء:</b> /cancel",
                parse_mode=ParseMode.HTML
            )
        return

    if data.startswith("SYS_ICON:"):
        if is_admin(user.id):
            key = data.split(":", 1)[1]

            context.user_data["state"] = "system_icon"
            context.user_data["system_key"] = key

            await query.edit_message_text(
                "<b>🎨 أرسل الأيقونة الجديدة:</b>",
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
            "<b>❌ تم إلغاء العملية.</b>",
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
                    "<b>أرسل اسم القسم كنص.</b>",
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
                "<b>✅ تم إنشاء القسم بنجاح.</b>\n\n"
                f"<b>{html.escape(name)}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
                            callback_data="ADMIN:BUTTONS"
                        ],
                        InlineKeyboardButton(
                            "🏠 الرئيسية",
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
                "<b>✅ تم تعديل اسم القسم.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
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
                "<b>✅ تم تعديل الأيقونة.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🧩 محرر الأزرار",
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
                "<b>✅ تم حفظ المشاركة.</b>\n\n"
                f"<b>النوع:</b> {html.escape(content_type)}\n"
                f"<b>رقم المشاركة:</b> {content_id}\n\n"
                "<b>عند ضغط المستخدم على القسم، "
                "سيتم إرسال المحتوى تلقائياً.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📝 تعديل المشاركات",
                            callback_data="ADMIN:CONTENT"
                        ],
                        InlineKeyboardButton(
                            "🔐 لوحة الإدارة",
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
                "<b>✅ تم استبدال المحتوى بنجاح.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📝 تعديل المشاركات",
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
                "<b>✅ تم تعديل اسم الزر.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⚙️ أزرار النظام",
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
                "<b>✅ تم تعديل أيقونة الزر.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⚙️ أزرار النظام",
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
                "<b>أرسل الملاحظة كنص.</b>",
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
                "<b>أرسل الرسالة كنص.</b>",
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
                    "✉️ <b>رسالة جديدة من المستخدمين</b>\n\n"
                    f"👤 <b>{html.escape(user.full_name)}</b>\n"
                    f"🆔 <code>{user.id}</code>\n\n"
                    f"📝 {html.escape(update.message.text)}"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("Global note error: %s", e)

        context.user_data.clear()

        await update.message.reply_text(
            "<b>✅ وصلت رسالتك إلى الإدارة.</b>",
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
            "<b>⛔ غير مسموح.</b>",
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
    # مهم:
    # هذا الكود لا يستخدم polling / getUpdates.
    # لذلك يمنع مشكلة:
    #
    # telegram.error.Conflict:
    # terminated by other getUpdates request
    #
    # بشرط أن تكون هناك نسخة واحدة فقط من الخدمة على Render.
    # --------------------------------------------------------

    if not RENDER_URL:
        raise RuntimeError(
            "RENDER_EXTERNAL_URL غير موجود. "
            "هذا الكود مخصص للتشغيل على Render Web Service."
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
