# main.py

import os
import html
import sqlite3
import logging
import threading
from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5734654153

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في Environment Variables")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID غير موجود في Environment Variables")

DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================================================
# FLASK FOR RENDER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram Bot is running!"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT 0,
            name TEXT NOT NULL,
            text TEXT DEFAULT '',
            content_type TEXT DEFAULT 'text',
            file_id TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()

    # إنشاء أقسام أولية إذا قاعدة البيانات فارغة
    count = cur.execute(
        "SELECT COUNT(*) FROM sections"
    ).fetchone()[0]

    if count == 0:
        initial = [
            (0, "📚 الكورس الأول"),
            (0, "📝 ملخصات الكورس الأول"),
            (0, "📚 الكورس الثاني"),
            (0, "📝 ملخصات الكورس الثاني"),
            (0, "💬 التواصل معنا"),
        ]

        for index, (parent, name) in enumerate(initial):
            cur.execute("""
                INSERT INTO sections
                (parent_id, name, sort_order)
                VALUES (?, ?, ?)
            """, (parent, name, index))

        conn.commit()

    conn.close()


# =========================================================
# HELPERS
# =========================================================

def esc(text):
    return html.escape(str(text))


def bold(text):
    return f"<b>{esc(text)}</b>"


def get_setting(key, default=""):
    conn = db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()
    conn.close()

    if row:
        return row["value"]

    return default


def set_setting(key, value):
    conn = db()

    conn.execute("""
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
    """, (key, value))

    conn.commit()
    conn.close()


def get_section(section_id):
    conn = db()

    row = conn.execute(
        "SELECT * FROM sections WHERE id=?",
        (section_id,)
    ).fetchone()

    conn.close()
    return row


def get_children(parent_id):
    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM sections
        WHERE parent_id=?
        ORDER BY sort_order ASC, id ASC
    """, (parent_id,)).fetchall()

    conn.close()
    return rows


def count_users():
    conn = db()
    result = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]
    conn.close()
    return result


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard(user_id):
    rows = [
        [KeyboardButton("📚 الكورس الأول")],
        [KeyboardButton("📝 ملخصات الكورس الأول")],
        [KeyboardButton("📚 الكورس الثاني")],
        [KeyboardButton("📝 ملخصات الكورس الثاني")],
        [KeyboardButton("💬 التواصل معنا")],
        [
            KeyboardButton("🎛️ محرر الأزرار"),
            KeyboardButton("📝 تعديل المشاركات")
        ],
        [
            KeyboardButton("⭐ تقييم البوت"),
            KeyboardButton("🔐 Admin")
        ],
    ]

    # الأدمن فقط
    if user_id != ADMIN_ID:
        rows = [
            [KeyboardButton("📚 الكورس الأول")],
            [KeyboardButton("📝 ملخصات الكورس الأول")],
            [KeyboardButton("📚 الكورس الثاني")],
            [KeyboardButton("📝 ملخصات الكورس الثاني")],
            [KeyboardButton("💬 التواصل معنا")],
            [KeyboardButton("⭐ تقييم البوت")],
        ]

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📊 الإحصائيات"),
                KeyboardButton("📥 البريد المرسل")
            ],
            [
                KeyboardButton("📢 الإعلانات"),
                KeyboardButton("🧩 Extensions")
            ],
            [
                KeyboardButton("⚙️ إعدادات البوت"),
                KeyboardButton("💾 المتغيرات")
            ],
            [
                KeyboardButton("📖 ترقيم الصفحات"),
                KeyboardButton("💬 رسالة البدء")
            ],
            [
                KeyboardButton("👣 نظام الإحالة"),
                KeyboardButton("👥 القنوات والمجموعات")
            ],
            [
                KeyboardButton("⭐ تقييمات البوت"),
                KeyboardButton("💵 الدفع التلقائي")
            ],
            [
                KeyboardButton("🎛️ محرر الأزرار"),
                KeyboardButton("📝 تعديل المشاركات")
            ],
            [
                KeyboardButton("🏠 القائمة الرئيسية")
            ],
        ],
        resize_keyboard=True
    )


def navigation_keyboard(section_id):
    section = get_section(section_id)

    if not section:
        return main_keyboard(ADMIN_ID)

    parent_id = section["parent_id"]

    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("↩️ رجوع")],
            [KeyboardButton(f"🚪 الخروج من {section['name']}")],
            [KeyboardButton("🏠 القائمة الرئيسية")],
        ],
        resize_keyboard=True
    )


# =========================================================
# SHOW SECTION
# =========================================================

async def show_section(update, context, section_id):
    section = get_section(section_id)

    if not section:
        await update.message.reply_text(
            bold("القسم غير موجود."),
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data["current_section"] = section_id

    children = get_children(section_id)

    text = section["text"]

    if text:
        message = (
            f"<b>{esc(section['name'])}</b>\n\n"
            f"<b>{esc(text)}</b>"
        )
    else:
        message = f"<b>{esc(section['name'])}</b>"

    if section["content_type"] == "photo" and section["file_id"]:
        await update.message.reply_photo(
            photo=section["file_id"],
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=navigation_keyboard(section_id)
        )

    elif section["content_type"] == "video" and section["file_id"]:
        await update.message.reply_video(
            video=section["file_id"],
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=navigation_keyboard(section_id)
        )

    elif section["content_type"] == "document" and section["file_id"]:
        await update.message.reply_document(
            document=section["file_id"],
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=navigation_keyboard(section_id)
        )

    else:
        if children:
            buttons = []

            for child in children:
                buttons.append([
                    KeyboardButton(child["name"])
                ])

            buttons.extend([
                [KeyboardButton("↩️ رجوع")],
                [KeyboardButton(
                    f"🚪 الخروج من {section['name']}"
                )],
                [KeyboardButton("🏠 القائمة الرئيسية")]
            ])

            markup = ReplyKeyboardMarkup(
                buttons,
                resize_keyboard=True
            )

        else:
            markup = navigation_keyboard(section_id)

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    conn = db()

    existing = conn.execute(
        "SELECT id FROM users WHERE id=?",
        (user.id,)
    ).fetchone()

    if not existing:

        conn.execute("""
            INSERT INTO users
            (id, username, first_name)
            VALUES (?, ?, ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or ""
        ))

        conn.commit()

        total = count_users()

        admin_message = (
            "<b>🔔 مستخدم جديد دخل البوت</b>\n\n"
            f"<b>👤 الاسم:</b> {esc(user.first_name or '-')}\n"
            f"<b>🆔 ID:</b> <code>{user.id}</code>\n"
            f"<b>🔗 Username:</b> @{esc(user.username) if user.username else '-'}\n"
            f"<b>👥 إجمالي المستخدمين:</b> {total}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    conn.close()

    context.user_data.clear()

    start_text = get_setting(
        "start_message",
        "أهلاً وسهلاً بك في البوت 🤖"
    )

    await update.message.reply_text(
        f"<b>{esc(start_text)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )


# =========================================================
# FIND SECTION BY NAME
# =========================================================

def find_section_by_name(name):
    conn = db()

    row = conn.execute("""
        SELECT *
        FROM sections
        WHERE name=?
        LIMIT 1
    """, (name,)).fetchone()

    conn.close()
    return row


# =========================================================
# BACK
# =========================================================

async def go_back(update, context):

    current_id = context.user_data.get("current_section")

    if not current_id:
        await update.message.reply_text(
            bold("أنت بالفعل في القائمة الرئيسية."),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(update.effective_user.id)
        )
        return

    current = get_section(current_id)

    if not current:
        await start(update, context)
        return

    parent_id = current["parent_id"]

    if parent_id == 0:
        await start(update, context)
    else:
        await show_section(update, context, parent_id)


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_panel(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            bold("❌ هذا القسم للأدمن فقط."),
            parse_mode=ParseMode.HTML
        )
        return

    await update.message.reply_text(
        "<b>🔐 لوحة الأدمن</b>\n\n"
        "<b>اختر القسم الذي تريد إدارته:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard()
    )


# =========================================================
# STATISTICS
# =========================================================

async def statistics(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    users = count_users()

    conn = db()

    ratings = conn.execute(
        "SELECT COUNT(*), AVG(rating) FROM ratings"
    ).fetchone()

    sections = conn.execute(
        "SELECT COUNT(*) FROM sections"
    ).fetchone()[0]

    conn.close()

    total_ratings = ratings[0] or 0
    average = ratings[1] or 0

    text = (
        "<b>📊 إحصائيات البوت</b>\n\n"
        f"<b>👥 المستخدمون:</b> {users}\n"
        f"<b>⭐ عدد التقييمات:</b> {total_ratings}\n"
        f"<b>⭐ متوسط التقييم:</b> {average:.2f}\n"
        f"<b>📂 الأقسام:</b> {sections}"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard()
    )


# =========================================================
# RATING
# =========================================================

async def rating_menu(update, context):

    keyboard = [
        [
            InlineKeyboardButton("⭐", callback_data="rate_1"),
            InlineKeyboardButton("⭐⭐", callback_data="rate_2"),
            InlineKeyboardButton("⭐⭐⭐", callback_data="rate_3"),
        ],
        [
            InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_4"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_5"),
        ],
    ]

    await update.message.reply_text(
        "<b>⭐ تقييم البوت</b>\n\n"
        "<b>قيّم تجربتك من 1 إلى 5:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def rating_callback(update, context):

    query = update.callback_query
    await query.answer()

    rating = int(query.data.split("_")[1])

    context.user_data["rating"] = rating
    context.user_data["rating_wait_comment"] = True

    await query.message.reply_text(
        f"<b>تم اختيار {rating} ⭐</b>\n\n"
        "<b>إذا عندك ملاحظة أو اقتراح، اكتبه الآن.</b>\n"
        "<b>أو اكتب: لا يوجد</b>",
        parse_mode=ParseMode.HTML
    )


# =========================================================
# BUTTON EDITOR
# =========================================================

async def button_editor(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    rows = get_children(0)

    keyboard = []

    for row in rows:
        keyboard.append([
            InlineKeyboardButton(
                f"✏️ {row['name']}",
                callback_data=f"editbtn_{row['id']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ إضافة قسم رئيسي",
            callback_data="add_root"
        )
    ])

    await update.message.reply_text(
        "<b>🎛️ محرر الأزرار</b>\n\n"
        "<b>اختر القسم الذي تريد تعديله:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_editor_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data.startswith("editbtn_"):

        section_id = int(data.split("_")[1])
        section = get_section(section_id)

        if not section:
            return

        children = get_children(section_id)

        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ تعديل الاسم",
                    callback_data=f"rename_{section_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "➕ إضافة زر فرعي",
                    callback_data=f"addchild_{section_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑️ حذف القسم",
                    callback_data=f"delete_{section_id}"
                )
            ],
        ]

        for child in children:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔹 {child['name']}",
                    callback_data=f"editbtn_{child['id']}"
                )
            ])

        await query.message.reply_text(
            f"<b>🎛️ {esc(section['name'])}</b>\n\n"
            "<b>الأزرار الفرعية:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# =========================================================
# CONTENT EDITOR
# =========================================================

async def content_editor(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    rows = get_children(0)

    keyboard = []

    for row in rows:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {row['name']}",
                callback_data=f"content_{row['id']}"
            )
        ])

    await update.message.reply_text(
        "<b>📝 تعديل المشاركات والمحتوى</b>\n\n"
        "<b>اختر القسم:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def content_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    section_id = int(query.data.split("_")[1])

    section = get_section(section_id)

    if not section:
        return

    context.user_data["editing_content"] = section_id

    keyboard = [
        [
            InlineKeyboardButton(
                "📝 تعديل النص",
                callback_data=f"settext_{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🖼️ إرسال صورة",
                callback_data=f"setphoto_{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🎥 إرسال فيديو",
                callback_data=f"setvideo_{section_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📎 إرسال ملف",
                callback_data=f"setdocument_{section_id}"
            )
        ],
    ]

    children = get_children(section_id)

    for child in children:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {child['name']}",
                callback_data=f"content_{child['id']}"
            )
        ])

    await query.message.reply_text(
        f"<b>📝 تعديل محتوى:</b>\n"
        f"<b>{esc(section['name'])}</b>\n\n"
        "<b>اختر نوع التعديل:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# CALLBACK EDITING
# =========================================================

async def editor_action_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data.startswith("rename_"):
        section_id = int(data.split("_")[1])

        context.user_data["rename_section"] = section_id

        await query.message.reply_text(
            "<b>✏️ أرسل الاسم الجديد للقسم:</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("addchild_"):
        parent_id = int(data.split("_")[1])

        context.user_data["add_child_parent"] = parent_id

        await query.message.reply_text(
            "<b>➕ أرسل اسم الزر الفرعي الجديد:</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("settext_"):
        section_id = int(data.split("_")[1])

        context.user_data["set_text_section"] = section_id

        await query.message.reply_text(
            "<b>📝 أرسل النص الجديد للمشاركة:</b>\n\n"
            "<b>سيظهر النص بالكامل بالخط الغامق.</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("setphoto_"):
        section_id = int(data.split("_")[1])

        context.user_data["set_photo_section"] = section_id

        await query.message.reply_text(
            "<b>🖼️ أرسل الصورة الآن.</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("setvideo_"):
        section_id = int(data.split("_")[1])

        context.user_data["set_video_section"] = section_id

        await query.message.reply_text(
            "<b>🎥 أرسل الفيديو الآن.</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("setdocument_"):
        section_id = int(data.split("_")[1])

        context.user_data["set_document_section"] = section_id

        await query.message.reply_text(
            "<b>📎 أرسل الملف الآن.</b>",
            parse_mode=ParseMode.HTML
        )

    elif data == "add_root":

        context.user_data["add_root"] = True

        await query.message.reply_text(
            "<b>➕ أرسل اسم القسم الرئيسي الجديد:</b>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("delete_"):

        section_id = int(data.split("_")[1])

        keyboard = [
            [
                InlineKeyboardButton(
                    "نعم، حذف",
                    callback_data=f"confirmdelete_{section_id}"
                ),
                InlineKeyboardButton(
                    "إلغاء",
                    callback_data="canceldelete"
                ),
            ]
        ]

        await query.message.reply_text(
            "<b>⚠️ هل تريد حذف القسم وجميع الأقسام الفرعية؟</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# =========================================================
# DELETE
# =========================================================

def delete_section_recursive(section_id):

    children = get_children(section_id)

    for child in children:
        delete_section_recursive(child["id"])

    conn = db()

    conn.execute(
        "DELETE FROM sections WHERE id=?",
        (section_id,)
    )

    conn.commit()
    conn.close()


async def delete_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    if query.data == "canceldelete":
        await query.message.reply_text(
            bold("تم إلغاء الحذف."),
            parse_mode=ParseMode.HTML
        )
        return

    section_id = int(
        query.data.split("_")[1]
    )

    delete_section_recursive(section_id)

    await query.message.reply_text(
        bold("✅ تم حذف القسم وجميع أقسامه الفرعية."),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard()
    )


# =========================================================
# TEXT HANDLER
# =========================================================

async def handle_text(update, context):

    user = update.effective_user
    text = update.message.text.strip()

    # -----------------------------------------------------
    # RATING COMMENT
    # -----------------------------------------------------

    if context.user_data.get("rating_wait_comment"):

        rating = context.user_data.get("rating")

        comment = ""

        if text != "لا يوجد":
            comment = text

        conn = db()

        conn.execute("""
            INSERT INTO ratings
            (user_id, rating, comment)
            VALUES (?, ?, ?)
        """, (
            user.id,
            rating,
            comment
        ))

        conn.commit()
        conn.close()

        context.user_data.pop("rating_wait_comment", None)
        context.user_data.pop("rating", None)

        await update.message.reply_text(
            "<b>✅ شكراً لتقييمك للبوت ❤️</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(user.id)
        )

        return

    # -----------------------------------------------------
    # ADD ROOT
    # -----------------------------------------------------

    if user.id == ADMIN_ID and context.user_data.get("add_root"):

        conn = db()

        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM sections WHERE parent_id=0"
        ).fetchone()[0]

        conn.execute("""
            INSERT INTO sections
            (parent_id, name, sort_order)
            VALUES (?, ?, ?)
        """, (
            0,
            text,
            max_order + 1
        ))

        conn.commit()
        conn.close()

        context.user_data.pop("add_root")

        await update.message.reply_text(
            f"<b>✅ تم إضافة:</b>\n<b>{esc(text)}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # RENAME
    # -----------------------------------------------------

    if user.id == ADMIN_ID and context.user_data.get("rename_section"):

        section_id = context.user_data["rename_section"]

        conn = db()

        conn.execute("""
            UPDATE sections
            SET name=?
            WHERE id=?
        """, (text, section_id))

        conn.commit()
        conn.close()

        context.user_data.pop("rename_section")

        await update.message.reply_text(
            "<b>✅ تم تعديل اسم القسم بنجاح.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # ADD CHILD
    # -----------------------------------------------------

    if user.id == ADMIN_ID and context.user_data.get("add_child_parent"):

        parent_id = context.user_data["add_child_parent"]

        conn = db()

        max_order = conn.execute("""
            SELECT COALESCE(MAX(sort_order),0)
            FROM sections
            WHERE parent_id=?
        """, (parent_id,)).fetchone()[0]

        conn.execute("""
            INSERT INTO sections
            (parent_id, name, sort_order)
            VALUES (?, ?, ?)
        """, (
            parent_id,
            text,
            max_order + 1
        ))

        conn.commit()
        conn.close()

        context.user_data.pop("add_child_parent")

        await update.message.reply_text(
            "<b>✅ تم إضافة الزر الفرعي بنجاح.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # SET TEXT
    # -----------------------------------------------------

    if user.id == ADMIN_ID and context.user_data.get("set_text_section"):

        section_id = context.user_data["set_text_section"]

        conn = db()

        conn.execute("""
            UPDATE sections
            SET text=?, content_type='text', file_id=''
            WHERE id=?
        """, (text, section_id))

        conn.commit()
        conn.close()

        context.user_data.pop("set_text_section")

        await update.message.reply_text(
            "<b>✅ تم تعديل محتوى المشاركة.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # MAIN MENU
    # -----------------------------------------------------

    if text in ("🏠 القائمة الرئيسية", "/start"):
        await start(update, context)
        return

    # -----------------------------------------------------
    # ADMIN
    # -----------------------------------------------------

    if text in ("🔐 Admin", "Admin"):
        await admin_panel(update, context)
        return

    if user.id == ADMIN_ID:

        if text == "📊 الإحصائيات":
            await statistics(update, context)
            return

        if text == "🎛️ محرر الأزرار":
            await button_editor(update, context)
            return

        if text == "📝 تعديل المشاركات":
            await content_editor(update, context)
            return

        if text == "⭐ تقييمات البوت":

            conn = db()

            rows = conn.execute("""
                SELECT r.*, u.username, u.first_name
                FROM ratings r
                LEFT JOIN users u ON u.id=r.user_id
                ORDER BY r.id DESC
                LIMIT 20
            """).fetchall()

            conn.close()

            if not rows:
                await update.message.reply_text(
                    bold("لا توجد تقييمات حالياً."),
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin_keyboard()
                )
                return

            text_out = "<b>⭐ آخر تقييمات البوت</b>\n\n"

            for row in rows:

                stars = "⭐" * row["rating"]

                text_out += (
                    f"<b>{stars}</b>\n"
                    f"<b>👤 {esc(row['first_name'] or '-')}</b>\n"
                    f"<b>🆔 {row['user_id']}</b>\n"
                )

                if row["comment"]:
                    text_out += (
                        f"<b>💬 {esc(row['comment'])}</b>\n"
                    )

                text_out += "\n"

            await update.message.reply_text(
                text_out,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "⚙️ إعدادات البوت":

            await update.message.reply_text(
                "<b>⚙️ إعدادات البوت</b>\n\n"
                "<b>اختر الإعداد الذي تريد تعديله:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [KeyboardButton("💬 رسالة البدء")],
                        [KeyboardButton("🏠 القائمة الرئيسية")]
                    ],
                    resize_keyboard=True
                )
            )
            return

        if text == "💬 رسالة البدء":

            context.user_data["edit_start_message"] = True

            current = get_setting(
                "start_message",
                "أهلاً وسهلاً بك في البوت 🤖"
            )

            await update.message.reply_text(
                "<b>💬 رسالة البدء الحالية:</b>\n\n"
                f"<b>{esc(current)}</b>\n\n"
                "<b>أرسل الرسالة الجديدة:</b>",
                parse_mode=ParseMode.HTML
            )

            return

        if text == "💾 المتغيرات":

            await update.message.reply_text(
                "<b>💾 المتغيرات</b>\n\n"
                "<b>BOT_TOKEN محفوظ في Environment Variables.</b>\n"
                "<b>ADMIN_ID محفوظ في Environment Variables.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "📥 البريد المرسل":

            await update.message.reply_text(
                "<b>📥 البريد المرسل</b>\n\n"
                "<b>سيتم تطويره لإرسال رسالة جماعية لجميع المستخدمين.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "📢 الإعلانات":

            await update.message.reply_text(
                "<b>📢 الإعلانات</b>\n\n"
                "<b>يمكن إضافة نظام نشر جماعي من هنا.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "🧩 Extensions":

            await update.message.reply_text(
                "<b>🧩 Extensions</b>\n\n"
                "<b>قسم الإضافات.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "📖 ترقيم الصفحات":

            await update.message.reply_text(
                "<b>📖 ترقيم الصفحات</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "👣 نظام الإحالة":

            await update.message.reply_text(
                "<b>👣 نظام الإحالة</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "👥 القنوات والمجموعات":

            await update.message.reply_text(
                "<b>👥 القنوات والمجموعات</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

        if text == "💵 الدفع التلقائي":

            await update.message.reply_text(
                "<b>💵 الدفع التلقائي</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard()
            )
            return

    # -----------------------------------------------------
    # START MESSAGE EDIT
    # -----------------------------------------------------

    if user.id == ADMIN_ID and context.user_data.get("edit_start_message"):

        set_setting("start_message", text)

        context.user_data.pop("edit_start_message")

        await update.message.reply_text(
            "<b>✅ تم تعديل رسالة البدء.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # RATING
    # -----------------------------------------------------

    if text == "⭐ تقييم البوت":
        await rating_menu(update, context)
        return

    # -----------------------------------------------------
    # BACK
    # -----------------------------------------------------

    if text == "↩️ رجوع":
        await go_back(update, context)
        return

    # -----------------------------------------------------
    # DYNAMIC SECTION
    # -----------------------------------------------------

    section = find_section_by_name(text)

    if section:

        await show_section(
            update,
            context,
            section["id"]
        )

        return

    # -----------------------------------------------------
    # ADMIN EDIT BUTTONS
    # -----------------------------------------------------

    if text == "🏠 القائمة الرئيسية":
        await start(update, context)
        return

    await update.message.reply_text(
        "<b>❓ لم أفهم اختيارك.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(user.id)
    )


# =========================================================
# MEDIA HANDLER
# =========================================================

async def handle_media(update, context):

    user = update.effective_user

    if user.id != ADMIN_ID:
        return

    section_id = None
    content_type = None
    file_id = None

    if update.message.photo:
        section_id = context.user_data.get("set_photo_section")
        content_type = "photo"
        file_id = update.message.photo[-1].file_id

    elif update.message.video:
        section_id = context.user_data.get("set_video_section")
        content_type = "video"
        file_id = update.message.video.file_id

    elif update.message.document:
        section_id = context.user_data.get("set_document_section")
        content_type = "document"
        file_id = update.message.document.file_id

    if not section_id:
        return

    caption = update.message.caption or ""

    conn = db()

    conn.execute("""
        UPDATE sections
        SET text=?, content_type=?, file_id=?
        WHERE id=?
    """, (
        caption,
        content_type,
        file_id,
        section_id
    ))

    conn.commit()
    conn.close()

    context.user_data.pop("set_photo_section", None)
    context.user_data.pop("set_video_section", None)
    context.user_data.pop("set_document_section", None)

    await update.message.reply_text(
        "<b>✅ تم حفظ المحتوى بنجاح.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard()
    )


# =========================================================
# MAIN
# =========================================================

async def post_init(application):
    init_db()


def main():

    init_db()

    # تشغيل Flask حتى يبقى Render يعتبر الخدمة شغالة
    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Start
    application.add_handler(
        CommandHandler("start", start)
    )

    # Rating callbacks
    application.add_handler(
        CallbackQueryHandler(
            rating_callback,
            pattern=r"^rate_[1-5]$"
        )
    )

    # Button editor callbacks
    application.add_handler(
        CallbackQueryHandler(
            button_editor_callback,
            pattern=r"^(editbtn_|add_root)"
        )
    )

    # Content editor callbacks
    application.add_handler(
        CallbackQueryHandler(
            content_callback,
            pattern=r"^content_"
        )
    )

    # Editor actions
    application.add_handler(
        CallbackQueryHandler(
            editor_action_callback,
            pattern=r"^(rename_|addchild_|settext_|setphoto_|setvideo_|setdocument_|delete_)"
        )
    )

    # Delete
    application.add_handler(
        CallbackQueryHandler(
            delete_callback,
            pattern=r"^(confirmdelete_|canceldelete)"
        )
    )

    # Media
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.Document.ALL,
            handle_media
        )
    )

    # Text
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("BOT STARTED")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
