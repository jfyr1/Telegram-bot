import os
import sqlite3
import logging
from contextlib import closing

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

# ضع التوكن في Environment Variables باسم BOT_TOKEN
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# آيدي الأدمن الرئيسي
ADMIN_ID = 5734654153

DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================================================
# TEXT
# =========================================================

START_TEXT = (
    "👋 أهلاً وسهلاً بك في المنصة التعليمية\n\n"
    "📚 اختر القسم المطلوب من القائمة أدناه:"
)

ABOUT_TEXT = (
    "ℹ️ حول البوت\n\n"
    "منصة تعليمية لتنظيم المواد والمحاضرات "
    "والملخصات والملفات والأسئلة."
)

# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():

    with closing(get_db()) as conn:

        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS admins(
                user_id INTEGER PRIMARY KEY
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS buttons(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL DEFAULT 'main'
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS posts(
                button_id INTEGER PRIMARY KEY,
                content_type TEXT NOT NULL,
                file_id TEXT,
                text_content TEXT,
                caption TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS favorites(
                user_id INTEGER,
                button_id INTEGER,
                PRIMARY KEY(user_id, button_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS visits(
                button_id INTEGER PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                button_id INTEGER,
                kind TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS ratings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                rating INTEGER,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS news(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS channels(
                chat_id TEXT PRIMARY KEY,
                title TEXT,
                username TEXT
            )
        """)

        c.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES(?)",
            (ADMIN_ID,)
        )

        defaults = {
            "maintenance": "0",
            "start_text": START_TEXT,
            "about_text": ABOUT_TEXT,
        }

        for key, value in defaults.items():

            c.execute(
                """
                INSERT OR IGNORE
                INTO settings(key,value)
                VALUES(?,?)
                """,
                (key, value)
            )

        conn.commit()


init_db()

# =========================================================
# SETTINGS
# =========================================================

def get_setting(key, default=""):

    with closing(get_db()) as conn:

        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key=?
            """,
            (key,)
        ).fetchone()

        return row[0] if row else default


def set_setting(key, value):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT OR REPLACE
            INTO settings(key,value)
            VALUES(?,?)
            """,
            (key, value)
        )

        conn.commit()

# =========================================================
# USERS
# =========================================================

def save_user(user):

    with closing(get_db()) as conn:

        old = conn.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id=?
            """,
            (user.id,)
        ).fetchone()

        conn.execute(
            """
            INSERT OR REPLACE INTO users(
                user_id,
                first_name,
                username
            )
            VALUES(?,?,?)
            """,
            (
                user.id,
                user.first_name or "",
                user.username or ""
            )
        )

        conn.commit()

        return old is None


def get_users():

    with closing(get_db()) as conn:

        rows = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

        return [x[0] for x in rows]

# =========================================================
# ADMIN
# =========================================================

def is_admin(user_id):

    if user_id == ADMIN_ID:
        return True

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT 1
            FROM admins
            WHERE user_id=?
            """,
            (user_id,)
        ).fetchone() is not None

# =========================================================
# KEYBOARDS
# =========================================================

def keyboard(rows):

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True
    )


def main_keyboard(user_id):

    rows = [

        [
            KeyboardButton("📚 الأقسام"),
            KeyboardButton("⭐ المفضلة")
        ],

        [
            KeyboardButton("🔥 الأكثر دخولاً"),
            KeyboardButton("🔍 البحث")
        ],

        [
            KeyboardButton("⭐ تقييم البوت"),
            KeyboardButton("💬 مراسلة الأدمن")
        ],

        [
            KeyboardButton("ℹ️ حول البوت")
        ]
    ]

    if is_admin(user_id):

        rows.append([
            KeyboardButton("⚙️ لوحة الأدمن")
        ])

    return keyboard(rows)


def admin_keyboard():

    return keyboard([

        [
            KeyboardButton("🔘 محرر الأزرار"),
            KeyboardButton("📝 محرر المشاركات")
        ],

        [
            KeyboardButton("📊 الإحصائيات"),
            KeyboardButton("👥 المستخدمون")
        ],

        [
            KeyboardButton("📰 الأخبار"),
            KeyboardButton("📢 إرسال جماعي")
        ],

        [
            KeyboardButton("👮 المشرفون"),
            KeyboardButton("📢 القنوات والمجموعات")
        ],

        [
            KeyboardButton("⚙️ إعدادات البوت"),
            KeyboardButton("🛠 الصيانة")
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية")
        ]
    ])


def button_editor_keyboard():

    return keyboard([

        [
            KeyboardButton("➕ إضافة قسم"),
            KeyboardButton("✏️ تعديل قسم")
        ],

        [
            KeyboardButton("📦 نقل قسم"),
            KeyboardButton("🔗 دمج قسم")
        ],

        [
            KeyboardButton("🗑 حذف قسم"),
            KeyboardButton("↕️ ترتيب الأقسام")
        ],

        [
            KeyboardButton("📋 عرض الأقسام")
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية"),
            KeyboardButton("🔙 لوحة الأدمن")
        ]
    ])


def post_editor_keyboard():

    return keyboard([

        [
            KeyboardButton("➕ إضافة مشاركة"),
            KeyboardButton("✏️ تعديل مشاركة")
        ],

        [
            KeyboardButton("🗑 حذف مشاركة"),
            KeyboardButton("📋 المشاركات")
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية"),
            KeyboardButton("🔙 لوحة الأدمن")
        ]
    ])


def cancel_keyboard():

    return keyboard([
        [
            KeyboardButton("❌ إلغاء")
        ]
    ])


def back_keyboard():

    return keyboard([
        [
            KeyboardButton("🔙 رجوع"),
            KeyboardButton("🏠 القائمة الرئيسية")
        ]
    ])

# =========================================================
# BUTTONS
# =========================================================

def get_children(parent_id):

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT
                id,
                parent_id,
                title,
                position,
                category
            FROM buttons
            WHERE parent_id=?
            ORDER BY position,id
            """,
            (parent_id,)
        ).fetchall()


def get_button(button_id):

    if not button_id:
        return None

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT
                id,
                parent_id,
                title,
                position,
                category
            FROM buttons
            WHERE id=?
            """,
            (button_id,)
        ).fetchone()


def get_all_buttons():

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT
                id,
                parent_id,
                title,
                position,
                category
            FROM buttons
            ORDER BY parent_id,position,id
            """
        ).fetchall()


def button_text(row):

    return f"{row[2]} 〔{row[0]}〕"


def parse_button_id(text):

    if "〔" not in text:
        return None

    if "〕" not in text:
        return None

    try:

        return int(
            text.rsplit("〔", 1)[1]
            .split("〕", 1)[0]
        )

    except Exception:

        return None

# =========================================================
# NAVIGATION
# =========================================================

async def show_section(
    update,
    context,
    parent_id=0,
    title="📚 الأقسام"
):

    context.user_data["parent_id"] = parent_id

    children = get_children(parent_id)

    rows = []

    for i in range(0, len(children), 2):

        row = [
            KeyboardButton(
                button_text(children[i])
            )
        ]

        if i + 1 < len(children):

            row.append(
                KeyboardButton(
                    button_text(children[i + 1])
                )
            )

        rows.append(row)

    rows.append([
        KeyboardButton("🔙 خروج من القسم"),
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    if not children:

        await update.message.reply_text(
            f"📂 {title}\n\n"
            "لا توجد أقسام مضافة حالياً.",
            reply_markup=keyboard(rows)
        )

        return

    await update.message.reply_text(
        f"📂 {title}\n\n"
        "اختر القسم المطلوب:",
        reply_markup=keyboard(rows)
    )


async def open_button(
    update,
    context,
    button
):

    button_id = button[0]
    title = button[2]
    parent_id = button[1]

    # تسجيل الزيارة
    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT INTO visits(button_id,count)
            VALUES(?,1)
            ON CONFLICT(button_id)
            DO UPDATE SET count=count+1
            """,
            (button_id,)
        )

        conn.commit()

    kids = get_children(button_id)

    if kids:

        await show_section(
            update,
            context,
            button_id,
            title
        )

        return

    post = None

    with closing(get_db()) as conn:

        post = conn.execute(
            """
            SELECT
                content_type,
                file_id,
                text_content,
                caption
            FROM posts
            WHERE button_id=?
            """,
            (button_id,)
        ).fetchone()

    context.user_data["parent_id"] = parent_id

    if not post:

        await update.message.reply_text(
            f"📂 {title}\n\n"
            "لا يوجد محتوى مضاف لهذا القسم حالياً.",
            reply_markup=keyboard([
                [
                    KeyboardButton("🔙 خروج من القسم"),
                    KeyboardButton("🏠 القائمة الرئيسية")
                ]
            ])
        )

        return

    content_type, file_id, text_content, caption = post

    # النص
    if content_type == "text":

        await update.message.reply_text(
            text_content or "",
            reply_markup=back_keyboard()
        )

    # صورة
    elif content_type == "photo":

        await update.message.reply_photo(
            photo=file_id,
            caption=caption or "",
            reply_markup=back_keyboard()
        )

    # فيديو
    elif content_type == "video":

        await update.message.reply_video(
            video=file_id,
            caption=caption or "",
            reply_markup=back_keyboard()
        )

    # ملف / PDF
    elif content_type == "document":

        await update.message.reply_document(
            document=file_id,
            caption=caption or "",
            reply_markup=back_keyboard()
        )

    # صوت
    elif content_type == "audio":

        await update.message.reply_audio(
            audio=file_id,
            caption=caption or "",
            reply_markup=back_keyboard()
        )

    # رسالة Telegram أخرى
    elif content_type == "animation":

        await update.message.reply_animation(
            animation=file_id,
            caption=caption or "",
            reply_markup=back_keyboard()
        )

# =========================================================
# START
# =========================================================

async def start(update, context):

    new_user = save_user(
        update.effective_user
    )

    context.user_data.clear()

    if (
        new_user
        and update.effective_user.id != ADMIN_ID
    ):

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🔔 مستخدم جديد دخل البوت\n\n"
                    f"👤 الاسم: "
                    f"{update.effective_user.first_name or 'غير معروف'}\n"
                    f"🆔 ID: "
                    f"{update.effective_user.id}\n"
                    f"🔗 username: "
                    f"@{update.effective_user.username or 'لا يوجد'}"
                )
            )

        except Exception as e:

            logging.error(
                "New user notification error: %s",
                e
            )

    if (
        get_setting("maintenance") == "1"
        and not is_admin(
            update.effective_user.id
        )
    ):

        await update.message.reply_text(
            "🛠 البوت حالياً في وضع الصيانة.\n\n"
            "يرجى المحاولة لاحقاً."
        )

        return

    await update.message.reply_text(
        get_setting(
            "start_text",
            START_TEXT
        ),
        reply_markup=main_keyboard(
            update.effective_user.id
        )
    )

# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_panel(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "⚙️ لوحة الأدمن\n\n"
        "اختر القسم المطلوب:",
        reply_markup=admin_keyboard()
    )

# =========================================================
# BUTTON EDITOR
# =========================================================

async def button_editor(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "🔘 محرر الأقسام والأزرار\n\n"
        "من هنا تستطيع إنشاء وتعديل ونقل ودمج "
        "وحذف وترتيب جميع الأقسام والأزرار.",
        reply_markup=button_editor_keyboard()
    )

# =========================================================
# ADD BUTTON
# =========================================================

async def add_button(update, context):

    context.user_data.clear()

    context.user_data["state"] = "add_title"

    await update.message.reply_text(
        "➕ إضافة قسم / زر\n\n"
        "أرسل اسم القسم:",
        reply_markup=cancel_keyboard()
    )


async def choose_parent(update, context):

    buttons = get_all_buttons()

    rows = [
        [
            KeyboardButton(
                "🏠 القسم الرئيسي"
            )
        ]
    ]

    for row in buttons:

        rows.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "choose_parent"

    await update.message.reply_text(
        "📁 اختر مكان القسم الجديد:",
        reply_markup=keyboard(rows)
    )

# =========================================================
# EDIT BUTTON
# =========================================================

async def edit_button(update, context):

    buttons = get_all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ لا توجد أقسام حالياً.",
            reply_markup=button_editor_keyboard()
        )

        return

    rows = []

    for row in buttons:

        rows.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "edit_select"

    await update.message.reply_text(
        "✏️ اختر القسم الذي تريد تعديل اسمه:",
        reply_markup=keyboard(rows)
    )

# =========================================================
# MOVE BUTTON
# =========================================================

async def move_start(update, context):

    buttons = get_all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ لا توجد أقسام.",
            reply_markup=button_editor_keyboard()
        )

        return

    rows = []

    for row in buttons:

        rows.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "move_select"

    await update.message.reply_text(
        "📦 اختر القسم الذي تريد نقله:",
        reply_markup=keyboard(rows)
    )

# =========================================================
# DELETE BUTTON
# =========================================================

async def delete_start(update, context):

    buttons = get_all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ لا توجد أقسام للحذف.",
            reply_markup=button_editor_keyboard()
        )

        return

    rows = []

    for row in buttons:

        rows.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "delete_select"

    await update.message.reply_text(
        "🗑 اختر القسم الذي تريد حذفه:",
        reply_markup=keyboard(rows)
    )

# =========================================================
# POST EDITOR
# =========================================================

async def post_editor(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "📝 محرر المشاركات\n\n"
        "اختر القسم ثم أرسل المحتوى مباشرة.\n\n"
        "لا تحتاج إلى تحديد PDF أو صورة أو فيديو.\n"
        "البوت يتعرف تلقائياً على نوع الرسالة.",
        reply_markup=post_editor_keyboard()
    )


async def select_post_button(update, context, action):

    buttons = get_all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ أنشئ الأقسام أولاً من محرر الأزرار.",
            reply_markup=post_editor_keyboard()
        )

        return

    rows = []

    for row in buttons:

        rows.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = action

    await update.message.reply_text(
        "📂 اختر القسم الذي تريد إضافة/تعديل المحتوى له:",
        reply_markup=keyboard(rows)
    )

# =========================================================
# SAVE ANY CONTENT
# =========================================================

def save_content(
    button_id,
    content_type,
    file_id=None,
    text_content=None,
    caption=None
):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT OR REPLACE INTO posts(
                button_id,
                content_type,
                file_id,
                text_content,
                caption
            )
            VALUES(?,?,?,?,?)
            """,
            (
                button_id,
                content_type,
                file_id,
                text_content,
                caption
            )
        )

        conn.commit()

# =========================================================
# FAVORITES
# =========================================================

async def toggle_favorite(update, context, button_id):

    with closing(get_db()) as conn:

        exists = conn.execute(
            """
            SELECT 1
            FROM favorites
            WHERE user_id=? AND button_id=?
            """,
            (
                update.effective_user.id,
                button_id
            )
        ).fetchone()

        if exists:

            conn.execute(
                """
                DELETE FROM favorites
                WHERE user_id=? AND button_id=?
                """,
                (
                    update.effective_user.id,
                    button_id
                )
            )

            text = "☆ تمت إزالة القسم من المفضلة."

        else:

            conn.execute(
                """
                INSERT OR IGNORE
                INTO favorites(user_id,button_id)
                VALUES(?,?)
                """,
                (
                    update.effective_user.id,
                    button_id
                )
            )

            text = "⭐ تمت إضافة القسم إلى المفضلة."

        conn.commit()

    await update.message.reply_text(
        text,
        reply_markup=back_keyboard()
    )


async def favorites(update, context):

    with closing(get_db()) as conn:

        rows = conn.execute("""
            SELECT
                b.id,
                b.parent_id,
                b.title,
                b.position,
                b.category
            FROM favorites f
            JOIN buttons b
            ON b.id=f.button_id
            WHERE f.user_id=?
            ORDER BY b.title
        """, (
            update.effective_user.id,
        )).fetchall()

    if not rows:

        await update.message.reply_text(
            "⭐ المفضلة\n\n"
            "لا توجد أقسام محفوظة.",
            reply_markup=back_keyboard()
        )

        return

    keys = []

    for row in rows:

        keys.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    keys.append([
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    context.user_data["favorite_mode"] = True

    await update.message.reply_text(
        "⭐ المفضلة\n\n"
        "اختر القسم:",
        reply_markup=keyboard(keys)
    )

# =========================================================
# MOST VISITED
# =========================================================

async def most_visited(update, context):

    with closing(get_db()) as conn:

        rows = conn.execute("""
            SELECT
                b.id,
                b.parent_id,
                b.title,
                b.position,
                b.category,
                v.count
            FROM visits v
            JOIN buttons b
            ON b.id=v.button_id
            ORDER BY v.count DESC
            LIMIT 20
        """).fetchall()

    if not rows:

        await update.message.reply_text(
            "🔥 لا توجد زيارات مسجلة بعد.",
            reply_markup=back_keyboard()
        )

        return

    keys = []

    for row in rows:

        keys.append([
            KeyboardButton(
                f"{row[2]} — {row[5]} زيارة 〔{row[0]}〕"
            )
        ])

    keys.append([
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    context.user_data["popular_mode"] = True

    await update.message.reply_text(
        "🔥 الأكثر دخولاً\n\n"
        "اختر القسم:",
        reply_markup=keyboard(keys)
    )

# =========================================================
# RATING
# =========================================================

async def rating_start(update, context):

    context.user_data["state"] = "rating"

    await update.message.reply_text(
        "⭐ تقييم البوت\n\n"
        "اختر تقييمك:",
        reply_markup=keyboard([
            [
                KeyboardButton("⭐"),
                KeyboardButton("⭐⭐")
            ],
            [
                KeyboardButton("⭐⭐⭐"),
                KeyboardButton("⭐⭐⭐⭐")
            ],
            [
                KeyboardButton("⭐⭐⭐⭐⭐")
            ],
            [
                KeyboardButton("❌ إلغاء")
            ]
        ])
    )


async def save_rating(update, context, rating):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT INTO ratings(
                user_id,
                rating,
                note
            )
            VALUES(?,?,?)
            """,
            (
                update.effective_user.id,
                rating,
                ""
            )
        )

        conn.commit()

    try:

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "⭐ تقييم جديد\n\n"
                f"التقييم: {rating}/5\n"
                f"المستخدم: "
                f"{update.effective_user.first_name or 'غير معروف'}\n"
                f"ID: {update.effective_user.id}"
            )
        )

    except Exception:
        pass

    context.user_data.clear()

    await update.message.reply_text(
        "✅ شكراً لتقييمك ❤️",
        reply_markup=main_keyboard(
            update.effective_user.id
        )
    )

# =========================================================
# CONTACT ADMIN
# =========================================================

async def contact_start(update, context):

    context.user_data["state"] = "contact"

    await update.message.reply_text(
        "💬 مراسلة الأدمن\n\n"
        "أرسل رسالتك أو صورتك أو ملفك أو فيديوك.\n"
        "سيتم إيصالها إلى الأدمن.",
        reply_markup=cancel_keyboard()
    )


async def contact_admin(update, context):

    user = update.effective_user

    try:

        await update.message.forward(
            chat_id=ADMIN_ID
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "💬 رسالة من مستخدم\n\n"
                f"👤 {user.first_name or 'غير معروف'}\n"
                f"🆔 {user.id}\n"
                f"🔗 @{user.username or 'لا يوجد'}"
            )
        )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم إرسال رسالتك إلى الأدمن.",
            reply_markup=main_keyboard(
                user.id
            )
        )

    except Exception as e:

        logging.error(
            "Contact error: %s",
            e
        )

        await update.message.reply_text(
            "❌ تعذر إرسال الرسالة.",
            reply_markup=main_keyboard(
                user.id
            )
        )

# =========================================================
# SEARCH
# =========================================================

async def search_start(update, context):

    context.user_data["state"] = "search"

    await update.message.reply_text(
        "🔍 البحث\n\n"
        "أرسل اسم المادة أو القسم أو المحاضرة:",
        reply_markup=cancel_keyboard()
    )


async def search(update, context, query):

    with closing(get_db()) as conn:

        rows = conn.execute("""
            SELECT
                id,
                parent_id,
                title,
                position,
                category
            FROM buttons
            WHERE title LIKE ?
            ORDER BY title
            LIMIT 50
        """, (
            f"%{query.strip()}%",
        )).fetchall()

    if not rows:

        await update.message.reply_text(
            "❌ لم يتم العثور على نتائج.",
            reply_markup=main_keyboard(
                update.effective_user.id
            )
        )

        context.user_data.clear()

        return

    keys = []

    for row in rows:

        keys.append([
            KeyboardButton(
                button_text(row)
            )
        ])

    keys.append([
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    context.user_data["search_results"] = {
        row[0]: row for row in rows
    }

    context.user_data["state"] = "search_result"

    await update.message.reply_text(
        f"🔍 نتائج البحث عن: {query}",
        reply_markup=keyboard(keys)
    )

# =========================================================
# MEDIA DETECTION
# =========================================================

async def handle_media(update, context):

    user_id = update.effective_user.id

    save_user(update.effective_user)

    state = context.user_data.get("state")

    # ---------------------------------------------
    # ADMIN ADD/EDIT CONTENT
    # ---------------------------------------------

    if is_admin(user_id) and state in (
        "post_add",
        "post_edit"
    ):

        button_id = context.user_data.get(
            "selected_button"
        )

        if not button_id:
            return

        message = update.message

        content_type = None
        file_id = None

        if message.document:

            content_type = "document"
            file_id = message.document.file_id

        elif message.photo:

            content_type = "photo"
            file_id = message.photo[-1].file_id

        elif message.video:

            content_type = "video"
            file_id = message.video.file_id

        elif message.audio:

            content_type = "audio"
            file_id = message.audio.file_id

        elif message.animation:

            content_type = "animation"
            file_id = message.animation.file_id

        if not content_type:

            await message.reply_text(
                "❌ لم أتعرف على نوع المحتوى."
            )

            return

        save_content(
            button_id=button_id,
            content_type=content_type,
            file_id=file_id,
            caption=message.caption or ""
        )

        context.user_data.clear()

        await message.reply_text(
            "✅ تم حفظ المحتوى بنجاح.\n\n"
            "البوت سيعرضه تلقائياً عند الضغط على القسم.",
            reply_markup=post_editor_keyboard()
        )

        return

    # ---------------------------------------------
    # CONTACT ADMIN
    # ---------------------------------------------

    if state == "contact":

        await contact_admin(
            update,
            context
        )

        return

    # ---------------------------------------------
    # BROADCAST
    # ---------------------------------------------

    if is_admin(user_id) and state == "broadcast":

        users = get_users()

        success = 0
        failed = 0

        for uid in users:

            try:

                await update.message.copy(
                    chat_id=uid
                )

                success += 1

            except Exception:

                failed += 1

        context.user_data.clear()

        await update.message.reply_text(
            "📢 اكتمل الإرسال الجماعي.\n\n"
            f"✅ نجح: {success}\n"
            f"❌ فشل: {failed}",
            reply_markup=admin_keyboard()
        )

# =========================================================
# TEXT HANDLER
# =========================================================

async def handle_text(update, context):

    if not update.message:
        return

    user = update.effective_user
    uid = user.id
    text = update.message.text.strip()

    new_user = save_user(user)

    # ---------------------------------------------
    # MAINTENANCE
    # ---------------------------------------------

    if (
        get_setting("maintenance") == "1"
        and not is_admin(uid)
    ):

        await update.message.reply_text(
            "🛠 البوت حالياً في وضع الصيانة."
        )

        return

    state = context.user_data.get("state")

    # ---------------------------------------------
    # CANCEL
    # ---------------------------------------------

    if text == "❌ إلغاء":

        context.user_data.clear()

        await update.message.reply_text(
            "❌ تم إلغاء العملية.",
            reply_markup=(
                admin_keyboard()
                if is_admin(uid)
                else main_keyboard(uid)
            )
        )

        return

    # ---------------------------------------------
    # MAIN
    # ---------------------------------------------

    if text == "🏠 القائمة الرئيسية":

        context.user_data.clear()

        await update.message.reply_text(
            get_setting(
                "start_text",
                START_TEXT
            ),
            reply_markup=main_keyboard(uid)
        )

        return

    # ---------------------------------------------
    # BACK / EXIT
    # ---------------------------------------------

    if text in (
        "🔙 رجوع",
        "🔙 خروج من القسم"
    ):

        parent_id = context.user_data.get(
            "parent_id",
            0
        )

        if parent_id:

            row = get_button(parent_id)

            if row:

                previous = row[1]

                if previous:

                    previous_row = get_button(
                        previous
                    )

                    await show_section(
                        update,
                        context,
                        previous,
                        previous_row[2]
                        if previous_row
                        else "القسم"
                    )

                    return

                await show_section(
                    update,
                    context,
                    0,
                    "📚 الأقسام"
                )

                return

        await update.message.reply_text(
            get_setting(
                "start_text",
                START_TEXT
            ),
            reply_markup=main_keyboard(uid)
        )

        return

    # =====================================================
    # ADMIN STATES
    # =====================================================

    if is_admin(uid):

        # ---------------------------------------------
        # ADD TITLE
        # ---------------------------------------------

        if state == "add_title":

            context.user_data["new_title"] = text

            await choose_parent(
                update,
                context
            )

            return

        # ---------------------------------------------
        # CHOOSE PARENT
        # ---------------------------------------------

        if state == "choose_parent":

            title = context.user_data.get(
                "new_title"
            )

            if text == "🏠 القسم الرئيسي":

                parent_id = 0

            else:

                parent_id = parse_button_id(
                    text
                )

                if not parent_id:

                    await update.message.reply_text(
                        "❌ اختر قسماً من القائمة."
                    )

                    return

                if not get_button(parent_id):

                    await update.message.reply_text(
                        "❌ القسم غير موجود."
                    )

                    return

            with closing(get_db()) as conn:

                position = conn.execute(
                    """
                    SELECT COALESCE(
                        MAX(position),-1
                    )+1
                    FROM buttons
                    WHERE parent_id=?
                    """,
                    (parent_id,)
                ).fetchone()[0]

                conn.execute(
                    """
                    INSERT INTO buttons(
                        parent_id,
                        title,
                        position
                    )
                    VALUES(?,?,?)
                    """,
                    (
                        parent_id,
                        title,
                        position
                    )
                )

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(
                f"✅ تمت إضافة القسم:\n\n"
                f"**{title}**",
                parse_mode="Markdown",
                reply_markup=button_editor_keyboard()
            )

            return

        # ---------------------------------------------
        # EDIT SELECT
        # ---------------------------------------------

        if state == "edit_select":

            bid = parse_button_id(text)

            row = get_button(bid)

            if not row:

                await update.message.reply_text(
                    "❌ اختر قسماً صحيحاً."
                )

                return

            context.user_data["edit_id"] = bid
            context.user_data["state"] = "edit_title"

            await update.message.reply_text(
                f"✏️ الاسم الحالي:\n"
                f"**{row[2]}**\n\n"
                "أرسل الاسم الجديد:",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard()
            )

            return

        # ---------------------------------------------
        # EDIT TITLE
        # ---------------------------------------------

        if state == "edit_title":

            bid = context.user_data.get(
                "edit_id"
            )

            with closing(get_db()) as conn:

                conn.execute(
                    """
                    UPDATE buttons
                    SET title=?
                    WHERE id=?
                    """,
                    (
                        text,
                        bid
                    )
                )

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تعديل القسم بنجاح.",
                reply_markup=button_editor_keyboard()
            )

            return

        # ---------------------------------------------
        # MOVE SELECT
        # ---------------------------------------------

        if state == "move_select":

            bid = parse_button_id(text)

            if not get_button(bid):

                await update.message.reply_text(
                    "❌ اختر قسماً صحيحاً."
                )

                return

            context.user_data["move_id"] = bid

            buttons = get_all_buttons()

            rows = [
                [
                    KeyboardButton(
                        "🏠 القسم الرئيسي"
                    )
                ]
            ]

            for row in buttons:

                if row[0] != bid:

                    rows.append([
                        KeyboardButton(
                            button_text(row)
                        )
                    ])

            rows.append([
                KeyboardButton("❌ إلغاء")
            ])

            context.user_data["state"] = "move_destination"

            await update.message.reply_text(
                "📦 اختر المكان الجديد للقسم:",
                reply_markup=keyboard(rows)
            )

            return

        # ---------------------------------------------
        # MOVE DESTINATION
        # ---------------------------------------------

        if state == "move_destination":

            bid = context.user_data.get(
                "move_id"
            )

            if text == "🏠 القسم الرئيسي":

                destination = 0

            else:

                destination = parse_button_id(
                    text
                )

                if destination is None:

                    await update.message.reply_text(
                        "❌ اختر المكان من القائمة."
                    )

                    return

            context.user_data[
                "move_destination"
            ] = destination

            context.user_data[
                "state"
            ] = "move_confirm"

            row = get_button(bid)

            await update.message.reply_text(
                "⚠️ تأكيد النقل\n\n"
                f"القسم: **{row[2]}**\n\n"
                "هل تريد تنفيذ عملية النقل؟",
                parse_mode="Markdown",
                reply_markup=keyboard([
                    [
                        KeyboardButton(
                            "✅ نعم، نقل"
                        )
                    ],
                    [
                        KeyboardButton(
                            "❌ إلغاء"
                        )
                    ]
                ])
            )

            return

        # ---------------------------------------------
        # MOVE CONFIRM
        # ---------------------------------------------

        if state == "move_confirm":

            if text == "✅ نعم، نقل":

                bid = context.user_data.get(
                    "move_id"
                )

                destination = context.user_data.get(
                    "move_destination"
                )

                # منع النقل داخل أحد الأبناء
                current = destination

                invalid = False

                while current:

                    if current == bid:

                        invalid = True
                        break

                    r = get_button(current)

                    current = r[1] if r else 0

                if invalid:

                    await update.message.reply_text(
                        "❌ لا يمكن نقل القسم داخل قسم تابع له.",
                        reply_markup=button_editor_keyboard()
                    )

                    context.user_data.clear()

                    return

                with closing(get_db()) as conn:

                    position = conn.execute(
                        """
                        SELECT COALESCE(
                            MAX(position),-1
                        )+1
                        FROM buttons
                        WHERE parent_id=?
                        """,
                        (destination,)
                    ).fetchone()[0]

                    conn.execute(
                        """
                        UPDATE buttons
                        SET parent_id=?,position=?
                        WHERE id=?
                        """,
                        (
                            destination,
                            position,
                            bid
                        )
                    )

                    conn.commit()

                context.user_data.clear()

                await update.message.reply_text(
                    "✅ تم نقل القسم بنجاح.",
                    reply_markup=button_editor_keyboard()
                )

                return

        # ---------------------------------------------
        # DELETE SELECT
        # ---------------------------------------------

        if state == "delete_select":

            bid = parse_button_id(text)

            row = get_button(bid)

            if not row:

                await update.message.reply_text(
                    "❌ اختر قسماً صحيحاً."
                )

                return

            context.user_data[
                "delete_id"
            ] = bid

            context.user_data[
                "state"
            ] = "delete_confirm"

            await update.message.reply_text(
                "⚠️ تأكيد الحذف\n\n"
                f"سيتم حذف القسم:\n"
                f"**{row[2]}**\n\n"
                "وسيتم حذف الأقسام الفرعية والمحتوى المرتبط بها أيضاً.\n\n"
                "هل أنت متأكد؟",
                parse_mode="Markdown",
                reply_markup=keyboard([
                    [
                        KeyboardButton(
                            "✅ نعم، حذف"
                        )
                    ],
                    [
                        KeyboardButton(
                            "❌ إلغاء"
                        )
                    ]
                ])
            )

            return

        # ---------------------------------------------
        # DELETE CONFIRM
        # ---------------------------------------------

        if state == "delete_confirm":

            if text == "✅ نعم، حذف":

                bid = context.user_data.get(
                    "delete_id"
                )

                delete_tree(bid)

                context.user_data.clear()

                await update.message.reply_text(
                    "🗑 تم حذف القسم ومحتواه وأقسامه الفرعية.",
                    reply_markup=button_editor_keyboard()
                )

                return

        # ---------------------------------------------
        # POST SELECT
        # ---------------------------------------------

        if state in (
            "post_add_select",
            "post_edit_select"
        ):

            bid = parse_button_id(text)

            row = get_button(bid)

            if not row:

                await update.message.reply_text(
                    "❌ اختر قسماً صحيحاً."
                )

                return

            context.user_data[
                "selected_button"
            ] = bid

            context.user_data[
                "state"
            ] = (
                "post_add"
                if state == "post_add_select"
                else "post_edit"
            )

            await update.message.reply_text(
                "📥 أرسل المحتوى الآن.\n\n"
                "يمكنك إرسال أي نوع من المحتوى:\n"
                "📄 ملف\n"
                "🖼 صورة\n"
                "🎬 فيديو\n"
                "🎵 صوت\n"
                "📝 نص\n"
                "وغيرها.\n\n"
                "البوت يتعرف عليه تلقائياً.",
                reply_markup=cancel_keyboard()
            )

            return

        # ---------------------------------------------
        # POST DELETE
        # ---------------------------------------------

        if state == "post_delete_select":

            bid = parse_button_id(text)

            if not get_button(bid):

                await update.message.reply_text(
                    "❌ اختر قسماً صحيحاً."
                )

                return

            if not post_exists(bid):

                context.user_data.clear()

                await update.message.reply_text(
                    "❌ لا يوجد محتوى لهذا القسم.",
                    reply_markup=post_editor_keyboard()
                )

                return

            context.user_data[
                "delete_post_id"
            ] = bid

            context.user_data[
                "state"
            ] = "post_delete_confirm"

            row = get_button(bid)

            await update.message.reply_text(
                "⚠️ تأكيد حذف المحتوى\n\n"
                f"القسم: **{row[2]}**\n\n"
                "هل تريد حذف المحتوى؟",
                parse_mode="Markdown",
                reply_markup=keyboard([
                    [
                        KeyboardButton(
                            "✅ نعم، حذف"
                        )
                    ],
                    [
                        KeyboardButton(
                            "❌ إلغاء"
                        )
                    ]
                ])
            )

            return

        # ---------------------------------------------
        # DELETE POST
        # ---------------------------------------------

        if state == "post_delete_confirm":

            if text == "✅ نعم، حذف":

                bid = context.user_data.get(
                    "delete_post_id"
                )

                with closing(get_db()) as conn:

                    conn.execute(
                        """
                        DELETE FROM posts
                        WHERE button_id=?
                        """,
                        (bid,)
                    )

                    conn.commit()

                context.user_data.clear()

                await update.message.reply_text(
                    "🗑 تم حذف المحتوى.",
                    reply_markup=post_editor_keyboard()
                )

                return

        # ---------------------------------------------
        # RATING
        # ---------------------------------------------

        if state == "rating":

            ratings = {
                "⭐": 1,
                "⭐⭐": 2,
                "⭐⭐⭐": 3,
                "⭐⭐⭐⭐": 4,
                "⭐⭐⭐⭐⭐": 5
            }

            if text in ratings:

                await save_rating(
                    update,
                    context,
                    ratings[text]
                )

                return

        # ---------------------------------------------
        # BROADCAST TEXT
        # ---------------------------------------------

        if state == "broadcast":

            users = get_users()

            success = 0
            failed = 0

            for target in users:

                try:

                    await context.bot.send_message(
                        chat_id=target,
                        text=text
                    )

                    success += 1

                except Exception:

                    failed += 1

            context.user_data.clear()

            await update.message.reply_text(
                "📢 اكتمل الإرسال الجماعي.\n\n"
                f"✅ نجح: {success}\n"
                f"❌ فشل: {failed}",
                reply_markup=admin_keyboard()
            )

            return

    # =====================================================
    # USER FUNCTIONS
    # =====================================================

    if text == "📚 الأقسام":

        context.user_data.clear()

        await show_section(
            update,
            context,
            0,
            "📚 الأقسام"
        )

        return

    if text == "⭐ المفضلة":

        context.user_data.clear()

        await favorites(
            update,
            context
        )

        return

    if text == "🔥 الأكثر دخولاً":

        context.user_data.clear()

        await most_visited(
            update,
            context
        )

        return

    if text == "🔍 البحث":

        await search_start(
            update,
            context
        )

        return

    if text == "⭐ تقييم البوت":

        await rating_start(
            update,
            context
        )

        return

    if text == "💬 مراسلة الأدمن":

        await contact_start(
            update,
            context
        )

        return

    if text == "ℹ️ حول البوت":

        await update.message.reply_text(
            get_setting(
                "about_text",
                ABOUT_TEXT
            ),
            reply_markup=back_keyboard()
        )

        return

    # =====================================================
    # SEARCH
    # =====================================================

    if state == "search":

        await search(
            update,
            context,
            text
        )

        return

    if state == "search_result":

        bid = parse_button_id(text)

        results = context.user_data.get(
            "search_results",
            {}
        )

        if bid in results:

            row = get_button(bid)

            if row:

                context.user_data.clear()

                await open_button(
                    update,
                    context,
                    row
                )

                return

    # =====================================================
    # FAVORITE MODE
    # =====================================================

    if context.user_data.get(
        "favorite_mode"
    ):

        bid = parse_button_id(text)

        if bid:

            row = get_button(bid)

            if row:

                context.user_data.clear()

                await open_button(
                    update,
                    context,
                    row
                )

                return

    # =====================================================
    # POPULAR MODE
    # =====================================================

    if context.user_data.get(
        "popular_mode"
    ):

        bid = parse_button_id(text)

        if bid:

            row = get_button(bid)

            if row:

                context.user_data.clear()

                await open_button(
                    update,
                    context,
                    row
                )

                return

    # =====================================================
    # DYNAMIC BUTTON
    # =====================================================

    parent_id = context.user_data.get(
        "parent_id"
    )

    if parent_id is not None:

        for row in get_children(parent_id):

            if text == button_text(row):

                await open_button(
                    update,
                    context,
                    row
                )

                return

    # =====================================================
    # ADMIN MENU
    # =====================================================

    if is_admin(uid):

        if text == "⚙️ لوحة الأدمن":

            await admin_panel(
                update,
                context
            )

            return

        if text == "🔘 محرر الأزرار":

            await button_editor(
                update,
                context
            )

            return

        if text == "📝 محرر المشاركات":

            await post_editor(
                update,
                context
            )

            return

        if text == "➕ إضافة قسم":

            await add_button(
                update,
                context
            )

            return

        if text == "✏️ تعديل قسم":

            await edit_button(
                update,
                context
            )

            return

        if text == "📦 نقل قسم":

            await move_start(
                update,
                context
            )

            return

        if text == "🗑 حذف قسم":

            await delete_start(
                update,
                context
            )

            return

        if text == "➕ إضافة مشاركة":

            await select_post_button(
                update,
                context,
                "post_add_select"
            )

            return

        if text == "✏️ تعديل مشاركة":

            await select_post_button(
                update,
                context,
                "post_edit_select"
            )

            return

        if text == "🗑 حذف مشاركة":

            await select_post_button(
                update,
                context,
                "post_delete_select"
            )

            return

        if text == "📋 عرض الأقسام":

            buttons = get_all_buttons()

            if not buttons:

                result = "📋 لا توجد أقسام."

            else:

                result = "📋 جميع الأقسام:\n\n"

                for row in buttons:

                    result += (
                        f"🔘 {row[2]} 〔{row[0]}〕\n"
                        f"↳ الأب: {row[1]}\n\n"
                    )

            await update.message.reply_text(
                result,
                reply_markup=button_editor_keyboard()
            )

            return

        if text == "📋 المشاركات":

            with closing(get_db()) as conn:

                rows = conn.execute("""
                    SELECT
                        b.title,
                        b.id,
                        p.content_type
                    FROM buttons b
                    LEFT JOIN posts p
                    ON p.button_id=b.id
                    ORDER BY b.id
                """).fetchall()

            result = "📋 المشاركات:\n\n"

            for title, bid, ctype in rows:

                result += (
                    f"🔘 {title} 〔{bid}〕\n"
                    f"📦 {ctype or 'لا يوجد'}\n\n"
                )

            await update.message.reply_text(
                result,
                reply_markup=post_editor_keyboard()
            )

            return

        if text == "📊 الإحصائيات":

            with closing(get_db()) as conn:

                users = conn.execute(
                    "SELECT COUNT(*) FROM users"
                ).fetchone()[0]

                buttons = conn.execute(
                    "SELECT COUNT(*) FROM buttons"
                ).fetchone()[0]

                posts = conn.execute(
                    "SELECT COUNT(*) FROM posts"
                ).fetchone()[0]

                ratings = conn.execute(
                    "SELECT COUNT(*) FROM ratings"
                ).fetchone()[0]

            await update.message.reply_text(
                "📊 إحصائيات البوت\n\n"
                f"👥 المستخدمون: {users}\n"
                f"🔘 الأقسام: {buttons}\n"
                f"📝 المشاركات: {posts}\n"
                f"⭐ التقييمات: {ratings}",
                reply_markup=admin_keyboard()
            )

            return

        if text == "👥 المستخدمون":

            users = get_users()

            await update.message.reply_text(
                f"👥 عدد المستخدمين:\n\n"
                f"**{len(users)}** مستخدم",
                parse_mode="Markdown",
                reply_markup=admin_keyboard()
            )

            return

        if text == "📢 إرسال جماعي":

            context.user_data["state"] = "broadcast"

            await update.message.reply_text(
                "📢 الإرسال الجماعي\n\n"
                "أرسل الرسالة أو الملف أو الصورة أو الفيديو.",
                reply_markup=cancel_keyboard()
            )

            return

        if text == "🛠 الصيانة":

            current = get_setting(
                "maintenance",
                "0"
            )

            new_value = "0" if current == "1" else "1"

            set_setting(
                "maintenance",
                new_value
            )

            status = (
                "🛠 تم تفعيل الصيانة."
                if new_value == "1"
                else "🟢 تم إيقاف الصيانة."
            )

            await update.message.reply_text(
                status,
                reply_markup=admin_keyboard()
            )

            return

        if text == "⚙️ إعدادات البوت":

            await update.message.reply_text(
                "⚙️ إعدادات البوت\n\n"
                "حالياً يمكنك إدارة الإعدادات الأساسية "
                "من قاعدة البيانات.",
                reply_markup=admin_keyboard()
            )

            return

    # =====================================================
    # UNKNOWN
    # =====================================================

    await update.message.reply_text(
        "❓ اختر أحد الخيارات الموجودة في الكيبورد.",
        reply_markup=(
            admin_keyboard()
            if is_admin(uid)
            else main_keyboard(uid)
        )
    )

# =========================================================
# POST EXISTS
# =========================================================

def post_exists(button_id):

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT 1
            FROM posts
            WHERE button_id=?
            """,
            (button_id,)
        ).fetchone() is not None

# =========================================================
# ERROR
# =========================================================

async def error_handler(update, context):

    logging.error(
        "Bot error:",
        exc_info=context.error
    )

# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود.\n"
            "أضف BOT_TOKEN داخل Environment Variables."
        )

    if not ADMIN_ID:

        raise RuntimeError(
            "ADMIN_ID غير صحيح."
        )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            (
                filters.Document.ALL
                | filters.PHOTO
                | filters.VIDEO
                | filters.AUDIO
                | filters.ANIMATION
            ),
            handle_media
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text
        )
    )

    app.add_error_handler(
        error_handler
    )

    print("🤖 البوت يعمل الآن...")

    app.run_polling()


if __name__ == "__main__":
    main()
