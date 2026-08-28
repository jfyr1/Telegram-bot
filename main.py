import os
import sqlite3
import logging
from contextlib import closing

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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

TOKEN = os.getenv("8925599691:AAGvo1qs6akZrIEuVbcfhMfOVlju1Pzp1s")

ADMIN_ID = 5734654153
DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================================================
# STATIC TEXTS
# =========================================================

CONTACT_TEXT = """أهلاً بك في المنصة الرسمية لدفعة الهندسة 2026.

يسرنا تواصلكم معنا عبر منصاتنا الرسمية لمتابعة آخر التبليغات والمستجدات الدراسية:

📢 قناة التليجرام الرسمية:
https://t.me/Eng26am

📸 حساب الإنستغرام:
https://instagram.com/eng26c

🎵 حساب التيك توك:
https://tiktok.com/eng26c

مع تحيات:
ممثل الدفعة المهندس جعفر
💬 @JFYR1"""

HELP_TEXT = """📖 تعلم كيفية استخدام البوت

1️⃣ اختر القسم المطلوب من القائمة الرئيسية.

2️⃣ اختر المادة أو القسم الفرعي.

3️⃣ عند الضغط على الزر سيظهر المحتوى المرتبط به.

4️⃣ المحتوى يمكن أن يكون:
📝 نص
📄 PDF
🖼 صورة
🎬 فيديو

5️⃣ استخدم 🔙 رجوع للعودة للقائمة السابقة.

6️⃣ استخدم 🏠 القائمة الرئيسية للعودة للبداية.

7️⃣ استخدم 🔍 البحث في المواد للعثور على المحتوى بسرعة."""

START_TEXT = """👋 أهلاً وسهلاً بك في المنصة الرسمية لدفعة الهندسة 2026.

📚 من هنا يمكنك الوصول إلى المواد الدراسية والمحاضرات والملخصات والملفات بسهولة.

اختر من القائمة أدناه 👇"""

MAINTENANCE_TEXT = """🛠 البوت حالياً في وضع الصيانة.

يرجى المحاولة لاحقاً."""

# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():

    with closing(get_db()) as conn:

        cur = conn.cursor()

        # USERS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ADMINS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        # SETTINGS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # BUTTONS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL DEFAULT 'general',
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            )
        """)

        # POSTS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                button_id INTEGER UNIQUE,
                content_type TEXT NOT NULL DEFAULT 'none',
                text_content TEXT,
                file_id TEXT,
                caption TEXT
            )
        """)

        # NEWS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # CHANNELS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE,
                title TEXT,
                username TEXT
            )
        """)

        # MAIN ADMIN
        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES (?)",
            (ADMIN_ID,),
        )

        defaults = {
            "maintenance": "0",
            "start_message": START_TEXT,
            "maintenance_message": MAINTENANCE_TEXT,
        }

        for key, value in defaults.items():

            cur.execute(
                """
                INSERT OR IGNORE INTO settings(key,value)
                VALUES (?,?)
                """,
                (key, value),
            )

        conn.commit()

        # -------------------------------------------------
        # Upgrade old database if category column missing
        # -------------------------------------------------

        columns = [
            row[1]
            for row in cur.execute(
                "PRAGMA table_info(buttons)"
            ).fetchall()
        ]

        if "category" not in columns:

            cur.execute(
                """
                ALTER TABLE buttons
                ADD COLUMN category TEXT NOT NULL DEFAULT 'general'
                """
            )

            conn.commit()


init_db()

# =========================================================
# SETTINGS
# =========================================================

def get_setting(key):

    with closing(get_db()) as conn:

        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        return row[0] if row else ""


def set_setting(key, value):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT OR REPLACE INTO settings(key,value)
            VALUES (?,?)
            """,
            (key, value),
        )

        conn.commit()

# =========================================================
# USERS
# =========================================================

def save_user(user):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT OR REPLACE INTO users
            (user_id, first_name, username)
            VALUES (?, ?, ?)
            """,
            (
                user.id,
                user.first_name or "",
                user.username or "",
            ),
        )

        conn.commit()


def get_all_users():

    with closing(get_db()) as conn:

        rows = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

        return [row[0] for row in rows]

# =========================================================
# ADMINS
# =========================================================

def is_admin(user_id):

    if user_id == ADMIN_ID:
        return True

    with closing(get_db()) as conn:

        row = conn.execute(
            """
            SELECT 1
            FROM admins
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        return row is not None

# =========================================================
# KEYBOARD
# =========================================================

def keyboard(rows):

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def main_keyboard(user_id):

    rows = [

        [
            KeyboardButton("📚 المواد الدراسية"),
            KeyboardButton("📖 المحاضرات"),
        ],

        [
            KeyboardButton("📝 الملخصات"),
            KeyboardButton("📂 الملفات"),
        ],

        [
            KeyboardButton("❓ الأسئلة"),
            KeyboardButton("🔍 البحث في المواد"),
        ],

        [
            KeyboardButton("📖 تعلم كيفية استخدام البوت"),
            KeyboardButton("📞 تواصل معنا"),
        ],

        [
            KeyboardButton("💬 مراسلة الأدمن"),
        ],
    ]

    if is_admin(user_id):

        rows.append([
            KeyboardButton("⚙️ لوحة الأدمن")
        ])

    return keyboard(rows)


def admin_keyboard():

    return keyboard([

        [
            KeyboardButton("📊 الإحصائيات"),
            KeyboardButton("👥 المشتركين"),
        ],

        [
            KeyboardButton("🔘 محرر الأزرار"),
            KeyboardButton("📝 محرر المشاركات"),
        ],

        [
            KeyboardButton("📰 محرر الأخبار"),
            KeyboardButton("📢 إرسال جماعي"),
        ],

        [
            KeyboardButton("⚙️ إعدادات البوت"),
            KeyboardButton("🛠 وضع الصيانة"),
        ],

        [
            KeyboardButton("👮 إعداد المشرفين"),
            KeyboardButton("📢 قنوات ومجموعات"),
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية"),
        ],
    ])


def button_editor_keyboard():

    return keyboard([

        [
            KeyboardButton("➕ إضافة زر"),
            KeyboardButton("✏️ تعديل زر"),
        ],

        [
            KeyboardButton("🗑 حذف زر"),
            KeyboardButton("↕️ ترتيب الأزرار"),
        ],

        [
            KeyboardButton("📋 عرض الأزرار"),
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية"),
            KeyboardButton("🔙 لوحة الأدمن"),
        ],
    ])


def post_editor_keyboard():

    return keyboard([

        [
            KeyboardButton("➕ إضافة محتوى"),
            KeyboardButton("✏️ تعديل محتوى"),
        ],

        [
            KeyboardButton("🗑 حذف محتوى"),
            KeyboardButton("📋 عرض المحتوى"),
        ],

        [
            KeyboardButton("🏠 القائمة الرئيسية"),
            KeyboardButton("🔙 لوحة الأدمن"),
        ],
    ])


def back_keyboard():

    return keyboard([

        [
            KeyboardButton("🔙 رجوع"),
            KeyboardButton("🏠 القائمة الرئيسية"),
        ]
    ])


def cancel_keyboard():

    return keyboard([
        [
            KeyboardButton("❌ إلغاء")
        ]
    ])

# =========================================================
# CATEGORIES
# =========================================================

CATEGORIES = {

    "📚 المواد الدراسية": "subjects",

    "📖 المحاضرات": "lectures",

    "📝 الملخصات": "summaries",

    "📂 الملفات": "files",

    "❓ الأسئلة": "questions",
}


CATEGORY_NAMES = {

    "subjects": "📚 المواد الدراسية",

    "lectures": "📖 المحاضرات",

    "summaries": "📝 الملخصات",

    "files": "📂 الملفات",

    "questions": "❓ الأسئلة",
}

# =========================================================
# BUTTONS
# =========================================================

def get_children(parent_id, category):

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT id,parent_id,title,position
            FROM buttons
            WHERE parent_id = ?
            AND category = ?
            ORDER BY position,id
            """,
            (
                parent_id,
                category,
            ),
        ).fetchall()


def get_button(button_id):

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT id,parent_id,title,position,category
            FROM buttons
            WHERE id = ?
            """,
            (button_id,),
        ).fetchone()


def all_buttons():

    with closing(get_db()) as conn:

        return conn.execute(
            """
            SELECT id,title,parent_id,category,position
            FROM buttons
            ORDER BY category,parent_id,position,id
            """
        ).fetchall()


def parse_button_id(text):

    if "〔" not in text:
        return None

    if "〕" not in text:
        return None

    try:

        value = text.rsplit("〔", 1)[1]
        value = value.split("〕", 1)[0]

        return int(value)

    except Exception:

        return None


# =========================================================
# DYNAMIC NAVIGATION
# =========================================================

def navigation_keyboard(parent_id, category, user_id):

    children = get_children(
        parent_id,
        category,
    )

    rows = []

    for i in range(0, len(children), 2):

        row = [
            KeyboardButton(
                f"{children[i][2]} 〔{children[i][0]}〕"
            )
        ]

        if i + 1 < len(children):

            row.append(
                KeyboardButton(
                    f"{children[i + 1][2]} 〔{children[i + 1][0]}〕"
                )
            )

        rows.append(row)

    if parent_id != 0:

        rows.append([
            KeyboardButton("🔙 رجوع"),
            KeyboardButton("🏠 القائمة الرئيسية"),
        ])

    else:

        rows.append([
            KeyboardButton("🏠 القائمة الرئيسية"),
        ])

    return keyboard(rows)


async def show_section(
    update,
    context,
    parent_id,
    category,
):

    context.user_data["parent_id"] = parent_id
    context.user_data["category"] = category

    context.user_data.pop("state", None)
    context.user_data.pop("selected_button", None)
    context.user_data.pop("search_results", None)

    children = get_children(
        parent_id,
        category,
    )

    if parent_id == 0:

        title = CATEGORY_NAMES.get(
            category,
            "القسم",
        )

    else:

        row = get_button(parent_id)

        title = row[2] if row else "القسم"

    if not children:

        await update.message.reply_text(

            f"📂 {title}\n\n"
            f"لا توجد أزرار مضافة داخل هذا القسم حالياً.",

            reply_markup=navigation_keyboard(
                parent_id,
                category,
                update.effective_user.id,
            ),
        )

        return

    await update.message.reply_text(

        f"📂 {title}\n\n"
        f"اختر من القائمة:",

        reply_markup=navigation_keyboard(
            parent_id,
            category,
            update.effective_user.id,
        ),
    )


# =========================================================
# OPEN BUTTON
# =========================================================

async def open_dynamic_button(
    update,
    context,
    button,
):

    button_id = button[0]
    parent_id = button[1]
    title = button[2]
    category = button[4]

    children = get_children(
        button_id,
        category,
    )

    if children:

        await show_section(
            update,
            context,
            button_id,
            category,
        )

        return

    with closing(get_db()) as conn:

        post = conn.execute(
            """
            SELECT
                content_type,
                text_content,
                file_id,
                caption
            FROM posts
            WHERE button_id = ?
            """,
            (button_id,),
        ).fetchone()

    context.user_data["parent_id"] = parent_id
    context.user_data["category"] = category

    if not post:

        await update.message.reply_text(

            f"📌 {title}\n\n"
            f"لا يوجد محتوى مضاف لهذا الزر حالياً.",

            reply_markup=navigation_keyboard(
                parent_id,
                category,
                update.effective_user.id,
            ),
        )

        return

    content_type, text_content, file_id, caption = post

    if content_type == "text":

        await update.message.reply_text(
            text_content or "",
            reply_markup=back_keyboard(),
        )

    elif content_type == "photo":

        await update.message.reply_photo(
            photo=file_id,
            caption=caption or "",
            reply_markup=back_keyboard(),
        )

    elif content_type == "video":

        await update.message.reply_video(
            video=file_id,
            caption=caption or "",
            reply_markup=back_keyboard(),
        )

    elif content_type == "document":

        await update.message.reply_document(
            document=file_id,
            caption=caption or "",
            reply_markup=back_keyboard(),
        )

# =========================================================
# START
# =========================================================

async def start(update, context):

    save_user(
        update.effective_user
    )

    context.user_data.clear()

    if (
        get_setting("maintenance") == "1"
        and not is_admin(
            update.effective_user.id
        )
    ):

        await update.message.reply_text(

            get_setting(
                "maintenance_message"
            ),

            reply_markup=keyboard([
                [
                    KeyboardButton(
                        "🔄 تحديث"
                    )
                ]
            ]),
        )

        return

    await update.message.reply_text(

        get_setting(
            "start_message"
        ),

        reply_markup=main_keyboard(
            update.effective_user.id
        ),
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

        reply_markup=admin_keyboard(),
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

        "🔘 محرر الأزرار\n\n"
        "هذا القسم خاص بالأزرار والقوائم فقط.\n\n"
        "إضافة المحتوى وإدارة النصوص والملفات "
        "تتم من محرر المشاركات.",

        reply_markup=button_editor_keyboard(),
    )


# =========================================================
# ADD BUTTON
# =========================================================

async def add_button_start(update, context):

    context.user_data.clear()

    context.user_data["state"] = "add_title"

    await update.message.reply_text(

        "➕ إضافة زر جديد\n\n"
        "أرسل اسم الزر:",

        reply_markup=cancel_keyboard(),
    )


async def choose_category_for_button(
    update,
    context,
):

    context.user_data["state"] = "choose_category"

    await update.message.reply_text(

        "📁 اختر القسم الرئيسي للزر:",

        reply_markup=keyboard([

            [
                KeyboardButton(
                    "📚 المواد الدراسية"
                ),
                KeyboardButton(
                    "📖 المحاضرات"
                ),
            ],

            [
                KeyboardButton(
                    "📝 الملخصات"
                ),
                KeyboardButton(
                    "📂 الملفات"
                ),
            ],

            [
                KeyboardButton(
                    "❓ الأسئلة"
                ),
            ],

            [
                KeyboardButton(
                    "❌ إلغاء"
                )
            ],
        ]),
    )


async def choose_parent_for_button(
    update,
    context,
):

    category = context.user_data.get(
        "new_category"
    )

    buttons = all_buttons()

    rows = [
        [
            KeyboardButton(
                "🏠 داخل القسم الرئيسي"
            )
        ]
    ]

    for button_id, title, parent_id, btn_category, position in buttons:

        if btn_category != category:
            continue

        rows.append([
            KeyboardButton(
                f"{title} 〔{button_id}〕"
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "choose_parent"

    await update.message.reply_text(

        "📁 اختر مكان الزر:\n\n"
        "إذا اخترت «داخل القسم الرئيسي» "
        "سيظهر الزر مباشرة داخل القسم.",

        reply_markup=keyboard(rows),
    )


# =========================================================
# EDIT BUTTON
# =========================================================

async def edit_button_start(update, context):

    buttons = all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ لا توجد أزرار حالياً.",
            reply_markup=button_editor_keyboard(),
        )

        return

    rows = []

    for button_id, title, parent_id, category, position in buttons:

        rows.append([
            KeyboardButton(
                f"{title} 〔{button_id}〕"
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "edit_select"

    await update.message.reply_text(

        "✏️ اختر الزر الذي تريد تعديل اسمه:",

        reply_markup=keyboard(rows),
    )


# =========================================================
# DELETE BUTTON
# =========================================================

async def delete_button_start(update, context):

    buttons = all_buttons()

    if not buttons:

        await update.message.reply_text(
            "❌ لا توجد أزرار للحذف.",
            reply_markup=button_editor_keyboard(),
        )

        return

    rows = []

    for button_id, title, parent_id, category, position in buttons:

        rows.append([
            KeyboardButton(
                f"{title} 〔{button_id}〕"
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = "delete_select"

    await update.message.reply_text(

        "🗑 حذف زر\n\n"
        "اختر الزر الذي تريد حذفه:",

        reply_markup=keyboard(rows),
    )


def delete_tree(button_id):

    with closing(get_db()) as conn:

        cur = conn.cursor()

        def remove_tree(current_id):

            children = cur.execute(
                """
                SELECT id
                FROM buttons
                WHERE parent_id = ?
                """,
                (current_id,),
            ).fetchall()

            for child in children:

                remove_tree(
                    child[0]
                )

            cur.execute(
                "DELETE FROM posts WHERE button_id = ?",
                (current_id,),
            )

            cur.execute(
                "DELETE FROM buttons WHERE id = ?",
                (current_id,),
            )

        remove_tree(button_id)

        conn.commit()


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
        "هذا القسم خاص بمحتوى الأزرار.\n\n"
        "يمكن ربط أي زر بـ:\n"
        "📝 نص\n"
        "📄 PDF\n"
        "🖼 صورة\n"
        "🎬 فيديو",

        reply_markup=post_editor_keyboard(),
    )


async def select_post_button(
    update,
    context,
    action,
):

    buttons = all_buttons()

    if not buttons:

        await update.message.reply_text(

            "❌ لا توجد أزرار.\n"
            "أنشئ الأزرار أولاً من محرر الأزرار.",

            reply_markup=post_editor_keyboard(),
        )

        return

    rows = []

    for button_id, title, parent_id, category, position in buttons:

        rows.append([
            KeyboardButton(
                f"{title} 〔{button_id}〕"
            )
        ])

    rows.append([
        KeyboardButton("❌ إلغاء")
    ])

    context.user_data["state"] = action

    await update.message.reply_text(

        "اختر الزر المطلوب:",

        reply_markup=keyboard(rows),
    )


# =========================================================
# CONTENT TYPE
# =========================================================

async def ask_content_type(
    update,
    context,
):

    context.user_data["state"] = "content_type"

    await update.message.reply_text(

        "📝 اختر نوع المحتوى:",

        reply_markup=keyboard([

            [
                KeyboardButton("📝 نص"),
                KeyboardButton("📄 PDF"),
            ],

            [
                KeyboardButton("🖼 صورة"),
                KeyboardButton("🎬 فيديو"),
            ],

            [
                KeyboardButton("❌ إلغاء")
            ],
        ]),
    )


# =========================================================
# SAVE POST
# =========================================================

def save_post(
    button_id,
    content_type,
    text=None,
    file_id=None,
    caption=None,
):

    with closing(get_db()) as conn:

        conn.execute(
            """
            INSERT OR REPLACE INTO posts
            (
                button_id,
                content_type,
                text_content,
                file_id,
                caption
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                button_id,
                content_type,
                text,
                file_id,
                caption,
            ),
        )

        conn.commit()


# =========================================================
# NEWS EDITOR
# =========================================================

async def news_editor(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data["state"] = "news"

    await update.message.reply_text(

        "📰 محرر الأخبار\n\n"
        "أرسل نص الخبر بالكامل.\n"
        "يمكن أن يحتوي على أكثر من فقرة.",

        reply_markup=cancel_keyboard(),
    )


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    context.user_data["state"] = "broadcast"

    await update.message.reply_text(

        "📢 الإرسال الجماعي\n\n"
        "أرسل الرسالة الآن.\n"
        "يمكنك إرسال نص أو صورة أو فيديو أو PDF.",

        reply_markup=cancel_keyboard(),
    )


async def do_broadcast(
    update,
    context,
):

    users = get_all_users()

    sent = 0
    failed = 0

    for user_id in users:

        try:

            await update.message.copy(
                chat_id=user_id
            )

            sent += 1

        except Exception:

            failed += 1

    context.user_data.clear()

    await update.message.reply_text(

        f"📢 اكتمل الإرسال الجماعي.\n\n"
        f"✅ نجح: {sent}\n"
        f"❌ فشل: {failed}\n"
        f"👥 الإجمالي: {len(users)}",

        reply_markup=admin_keyboard(),
    )

# =========================================================
# ADMINS
# =========================================================

async def admins(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    with closing(get_db()) as conn:

        rows = conn.execute(
            """
            SELECT user_id
            FROM admins
            ORDER BY user_id
            """
        ).fetchall()

    text = "👮 إعداد المشرفين\n\n"

    for user_id, in rows:

        if user_id == ADMIN_ID:

            text += f"👑 {user_id} — المشرف الرئيسي\n"

        else:

            text += f"👮 {user_id}\n"

    text += """

طريقة الإضافة:
+ 123456789

طريقة الحذف:
- 123456789
"""

    context.user_data["state"] = "admin_manage"

    await update.message.reply_text(

        text,

        reply_markup=keyboard([

            [
                KeyboardButton("🔙 لوحة الأدمن")
            ]

        ]),
    )


# =========================================================
# CHANNELS
# =========================================================

async def channels(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    with closing(get_db()) as conn:

        rows = conn.execute(
            """
            SELECT chat_id,title,username
            FROM channels
            ORDER BY id DESC
            """
        ).fetchall()

    text = "📢 قنوات ومجموعات\n\n"

    if not rows:

        text += "لا توجد قنوات أو مجموعات محفوظة."

    else:

        for chat_id, title, username in rows:

            text += f"📌 {title or 'بدون اسم'}\n"
            text += f"🆔 {chat_id}\n"

            if username:

                text += f"🔗 @{username}\n"

            text += "\n"

    text += """

لإضافة قناة أو مجموعة:

+ -1001234567890 اسم القناة

"""

    context.user_data["state"] = "channel_manage"

    await update.message.reply_text(

        text,

        reply_markup=keyboard([

            [
                KeyboardButton("🔙 لوحة الأدمن")
            ]

        ]),
    )

# =========================================================
# SETTINGS
# =========================================================

async def bot_settings(update, context):

    if not is_admin(
        update.effective_user.id
    ):
        return

    await update.message.reply_text(

        "⚙️ إعدادات البوت\n\n"
        "اختر الإعداد المطلوب:",

        reply_markup=keyboard([

            [
                KeyboardButton("✏️ رسالة البدء"),
                KeyboardButton("🔧 رسالة الصيانة"),
            ],

            [
                KeyboardButton("🛠 وضع الصيانة"),
            ],

            [
                KeyboardButton("🔙 لوحة الأدمن"),
            ],
        ]),
    )


async def edit_start_message(
    update,
    context,
):

    context.user_data["state"] = "edit_start"

    await update.message.reply_text(

        "✏️ أرسل رسالة البدء الجديدة:",

        reply_markup=cancel_keyboard(),
    )


async def edit_maintenance_message(
    update,
    context,
):

    context.user_data["state"] = "edit_maintenance"

    await update.message.reply_text(

        "🔧 أرسل رسالة الصيانة الجديدة:",

        reply_markup=cancel_keyboard(),
    )


async def toggle_maintenance(
    update,
    context,
):

    current = get_setting(
        "maintenance"
    )

    if current == "1":

        set_setting(
            "maintenance",
            "0",
        )

        text = "🟢 تم إيقاف وضع الصيانة.\nالبوت يعمل الآن."

    else:

        set_setting(
            "maintenance",
            "1",
        )

        text = "🛠 تم تفعيل وضع الصيانة."

    await update.message.reply_text(

        text,

        reply_markup=admin_keyboard(),
    )

# =========================================================
# SEARCH
# =========================================================

async def search_start(update, context):

    context.user_data.clear()

    context.user_data["state"] = "search"

    await update.message.reply_text(

        "🔍 البحث في المواد\n\n"
        "أرسل اسم المادة أو المحاضرة أو الملخص:",

        reply_markup=cancel_keyboard(),
    )


async def perform_search(
    update,
    context,
    query,
):

    query = query.strip()

    if not query:

        await update.message.reply_text(
            "❌ اكتب كلمة للبحث."
        )

        return

    with closing(get_db()) as conn:

        rows = conn.execute(
            """
            SELECT
                id,
                title,
                parent_id,
                category
            FROM buttons
            WHERE title LIKE ?
            ORDER BY position,id
            LIMIT 50
            """,
            (
                f"%{query}%",
            ),
        ).fetchall()

    if not rows:

        context.user_data.clear()

        await update.message.reply_text(

            "❌ لم يتم العثور على نتائج.",

            reply_markup=main_keyboard(
                update.effective_user.id
            ),
        )

        return

    result_rows = []

    for button_id, title, parent_id, category in rows:

        result_rows.append([
            KeyboardButton(
                f"{title} 〔{button_id}〕"
            )
        ])

    result_rows.append([
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    context.user_data["search_results"] = {
        row[0]: row
        for row in rows
    }

    context.user_data["state"] = "search_result"

    await update.message.reply_text(

        f"🔍 نتائج البحث عن:\n« {query} »",

        reply_markup=keyboard(
            result_rows
        ),
    )

# =========================================================
# CONTACT ADMIN
# =========================================================

async def contact_admin_start(
    update,
    context,
):

    context.user_data.clear()

    context.user_data["state"] = "contact_admin"

    await update.message.reply_text(

        "💬 مراسلة الأدمن\n\n"
        "أرسل رسالتك الآن، وسيتم إيصالها إلى الأدمن.",

        reply_markup=cancel_keyboard(),
    )


async def forward_to_admin(
    update,
    context,
):

    user = update.effective_user

    try:

        await update.message.forward(
            chat_id=ADMIN_ID
        )

        await context.bot.send_message(

            chat_id=ADMIN_ID,

            text=(
                "💬 رسالة جديدة من مستخدم\n\n"
                f"👤 الاسم: {user.first_name or 'غير معروف'}\n"
                f"🆔 ID: {user.id}\n"
                f"🔗 @{user.username or 'لا يوجد'}"
            ),
        )

        context.user_data.clear()

        await update.message.reply_text(

            "✅ تم إرسال رسالتك إلى الأدمن.",

            reply_markup=main_keyboard(
                user.id
            ),
        )

    except Exception as e:

        logging.error(
            "Contact admin error: %s",
            e,
        )

        await update.message.reply_text(

            "❌ حدث خطأ أثناء إرسال الرسالة.",

            reply_markup=main_keyboard(
                user.id
            ),
        )

# =========================================================
# TEXT HANDLER
# =========================================================

async def handle_text(
    update,
    context,
):

    if not update.message:
        return

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    save_user(user)

    # =====================================================
    # MAINTENANCE
    # =====================================================

    if (
        get_setting("maintenance") == "1"
        and not is_admin(user_id)
        and text != "🔄 تحديث"
    ):

        await update.message.reply_text(

            get_setting(
                "maintenance_message"
            ),

            reply_markup=keyboard([

                [
                    KeyboardButton(
                        "🔄 تحديث"
                    )
                ]

            ]),
        )

        return

    state = context.user_data.get(
        "state"
    )

    # =====================================================
    # CANCEL
    # =====================================================

    if text == "❌ إلغاء":

        context.user_data.clear()

        if is_admin(user_id):

            await update.message.reply_text(
                "❌ تم الإلغاء.",
                reply_markup=admin_keyboard(),
            )

        else:

            await update.message.reply_text(
                "❌ تم الإلغاء.",
                reply_markup=main_keyboard(
                    user_id
                ),
            )

        return

    # =====================================================
    # ADMIN STATES
    # =====================================================

    if is_admin(user_id):

        # -------------------------------------------------
        # ADD BUTTON TITLE
        # -------------------------------------------------

        if state == "add_title":

            context.user_data["new_title"] = text

            await choose_category_for_button(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # CATEGORY
        # -------------------------------------------------

        if state == "choose_category":

            category = CATEGORIES.get(text)

            if not category:

                await update.message.reply_text(
                    "❌ اختر أحد الأقسام من القائمة."
                )

                return

            context.user_data[
                "new_category"
            ] = category

            await choose_parent_for_button(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # PARENT
        # -------------------------------------------------

        if state == "choose_parent":

            category = context.user_data.get(
                "new_category"
            )

            title = context.user_data.get(
                "new_title"
            )

            if text == "🏠 داخل القسم الرئيسي":

                parent_id = 0

            else:

                parent_id = parse_button_id(
                    text
                )

                if parent_id is None:

                    await update.message.reply_text(
                        "❌ اختر زرًا من القائمة."
                    )

                    return

                parent = get_button(
                    parent_id
                )

                if not parent:

                    await update.message.reply_text(
                        "❌ الزر غير موجود."
                    )

                    return

                if parent[4] != category:

                    await update.message.reply_text(
                        "❌ لا يمكن وضع الزر داخل قسم مختلف."
                    )

                    return

            with closing(get_db()) as conn:

                position = conn.execute(
                    """
                    SELECT COALESCE(
                        MAX(position),
                        -1
                    ) + 1
                    FROM buttons
                    WHERE parent_id = ?
                    AND category = ?
                    """,
                    (
                        parent_id,
                        category,
                    ),
                ).fetchone()[0]

                conn.execute(
                    """
                    INSERT INTO buttons
                    (
                        parent_id,
                        category,
                        title,
                        position
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        parent_id,
                        category,
                        title,
                        position,
                    ),
                )

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(

                f"✅ تمت إضافة الزر:\n"
                f"« {title} »",

                reply_markup=button_editor_keyboard(),
            )

            return

        # -------------------------------------------------
        # EDIT BUTTON SELECT
        # -------------------------------------------------

        if state == "edit_select":

            button_id = parse_button_id(
                text
            )

            row = get_button(
                button_id
            ) if button_id else None

            if not row:

                await update.message.reply_text(
                    "❌ اختر زرًا من القائمة."
                )

                return

            context.user_data[
                "edit_button_id"
            ] = button_id

            context.user_data[
                "state"
            ] = "edit_title"

            await update.message.reply_text(

                f"✏️ الاسم الحالي:\n"
                f"{row[2]}\n\n"
                f"أرسل الاسم الجديد:",

                reply_markup=cancel_keyboard(),
            )

            return

        # -------------------------------------------------
        # EDIT TITLE
        # -------------------------------------------------

        if state == "edit_title":

            button_id = context.user_data.get(
                "edit_button_id"
            )

            with closing(get_db()) as conn:

                conn.execute(
                    """
                    UPDATE buttons
                    SET title = ?
                    WHERE id = ?
                    """,
                    (
                        text,
                        button_id,
                    ),
                )

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(

                "✅ تم تعديل اسم الزر.",

                reply_markup=button_editor_keyboard(),
            )

            return

        # -------------------------------------------------
        # DELETE SELECT
        # -------------------------------------------------

        if state == "delete_select":

            button_id = parse_button_id(
                text
            )

            row = get_button(
                button_id
            ) if button_id else None

            if not row:

                await update.message.reply_text(
                    "❌ اختر زرًا من القائمة."
                )

                return

            context.user_data[
                "delete_button_id"
            ] = button_id

            context.user_data[
                "state"
            ] = "delete_confirm"

            await update.message.reply_text(

                "⚠️ تأكيد حذف\n\n"
                f"هل تريد حذف الزر:\n"
                f"« {row[2]} » ؟\n\n"
                "سيتم حذف محتواه وجميع أزراره الفرعية أيضاً.",

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
                    ],

                ]),
            )

            return

        # -------------------------------------------------
        # DELETE CONFIRM
        # -------------------------------------------------

        if state == "delete_confirm":

            if text == "✅ نعم، حذف":

                button_id = context.user_data.get(
                    "delete_button_id"
                )

                if button_id:

                    delete_tree(
                        button_id
                    )

                context.user_data.clear()

                await update.message.reply_text(

                    "🗑 تم حذف الزر ومحتواه "
                    "وجميع أزراره الفرعية.",

                    reply_markup=button_editor_keyboard(),
                )

                return

        # -------------------------------------------------
        # POST SELECT
        # -------------------------------------------------

        if state in (
            "post_add_select",
            "post_edit_select",
            "post_delete_select",
        ):

            button_id = parse_button_id(
                text
            )

            row = get_button(
                button_id
            ) if button_id else None

            if not row:

                await update.message.reply_text(
                    "❌ اختر زرًا من القائمة."
                )

                return

            context.user_data[
                "selected_button"
            ] = button_id

            if state == "post_delete_select":

                with closing(get_db()) as conn:

                    post = conn.execute(
                        """
                        SELECT id
                        FROM posts
                        WHERE button_id = ?
                        """,
                        (button_id,),
                    ).fetchone()

                if not post:

                    context.user_data.clear()

                    await update.message.reply_text(

                        "❌ هذا الزر لا يحتوي على محتوى.",

                        reply_markup=post_editor_keyboard(),
                    )

                    return

                context.user_data[
                    "state"
                ] = "post_delete_confirm"

                await update.message.reply_text(

                    "⚠️ تأكيد حذف المحتوى\n\n"
                    "هل تريد حذف المحتوى المرتبط بهذا الزر؟",

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
                        ],

                    ]),
                )

                return

            await ask_content_type(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # DELETE POST CONFIRM
        # -------------------------------------------------

        if state == "post_delete_confirm":

            if text == "✅ نعم، حذف":

                button_id = context.user_data.get(
                    "selected_button"
                )

                with closing(get_db()) as conn:

                    conn.execute(
                        """
                        DELETE FROM posts
                        WHERE button_id = ?
                        """,
                        (button_id,),
                    )

                    conn.commit()

                context.user_data.clear()

                await update.message.reply_text(

                    "🗑 تم حذف المحتوى.",

                    reply_markup=post_editor_keyboard(),
                )

                return

        # -------------------------------------------------
        # CONTENT TYPE
        # -------------------------------------------------

        if state == "content_type":

            types = {

                "📝 نص": "text",

                "📄 PDF": "document",

                "🖼 صورة": "photo",

                "🎬 فيديو": "video",
            }

            content_type = types.get(
                text
            )

            if not content_type:

                await update.message.reply_text(
                    "❌ اختر نوع المحتوى من القائمة."
                )

                return

            context.user_data[
                "content_type"
            ] = content_type

            if content_type == "text":

                context.user_data[
                    "state"
                ] = "content_text"

                await update.message.reply_text(

                    "📝 أرسل النص الذي سيظهر عند الضغط على الزر:",

                    reply_markup=cancel_keyboard(),
                )

            else:

                context.user_data[
                    "state"
                ] = "content_media"

                messages = {

                    "document":
                        "📄 أرسل ملف PDF الآن:",

                    "photo":
                        "🖼 أرسل الصورة الآن:",

                    "video":
                        "🎬 أرسل الفيديو الآن:",
                }

                await update.message.reply_text(

                    messages[content_type],

                    reply_markup=cancel_keyboard(),
                )

            return

        # -------------------------------------------------
        # TEXT CONTENT
        # -------------------------------------------------

        if state == "content_text":

            button_id = context.user_data.get(
                "selected_button"
            )

            save_post(
                button_id,
                "text",
                text=text,
            )

            context.user_data.clear()

            await update.message.reply_text(

                "✅ تم حفظ النص وربطه بالزر.",

                reply_markup=post_editor_keyboard(),
            )

            return

        # -------------------------------------------------
        # START MESSAGE
        # -------------------------------------------------

        if state == "edit_start":

            set_setting(
                "start_message",
                text,
            )

            context.user_data.clear()

            await update.message.reply_text(

                "✅ تم تحديث رسالة /start.",

                reply_markup=admin_keyboard(),
            )

            return

        # -------------------------------------------------
        # MAINTENANCE MESSAGE
        # -------------------------------------------------

        if state == "edit_maintenance":

            set_setting(
                "maintenance_message",
                text,
            )

            context.user_data.clear()

            await update.message.reply_text(

                "✅ تم تحديث رسالة الصيانة.",

                reply_markup=admin_keyboard(),
            )

            return

        # -------------------------------------------------
        # NEWS
        # -------------------------------------------------

        if state == "news":

            with closing(get_db()) as conn:

                conn.execute(
                    """
                    INSERT INTO news(title,content)
                    VALUES (?,?)
                    """,
                    (
                        "خبر جديد",
                        text,
                    ),
                )

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(

                "📰 تم حفظ الخبر بنجاح.",

                reply_markup=admin_keyboard(),
            )

            return

        # -------------------------------------------------
        # BROADCAST
        # -------------------------------------------------

        if state == "broadcast":

            await do_broadcast(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # ADMIN MANAGEMENT
        # -------------------------------------------------

        if state == "admin_manage":

            if text.startswith("+"):

                try:

                    new_admin = int(
                        text[1:].strip()
                    )

                    with closing(get_db()) as conn:

                        conn.execute(
                            """
                            INSERT OR IGNORE
                            INTO admins(user_id)
                            VALUES (?)
                            """,
                            (new_admin,),
                        )

                        conn.commit()

                    context.user_data.clear()

                    await update.message.reply_text(

                        "✅ تمت إضافة المشرف.",

                        reply_markup=admin_keyboard(),
                    )

                    return

                except ValueError:

                    await update.message.reply_text(
                        "❌ ID غير صحيح."
                    )

                    return

            if text.startswith("-"):

                try:

                    remove_admin = int(
                        text[1:].strip()
                    )

                    if remove_admin == ADMIN_ID:

                        await update.message.reply_text(
                            "❌ لا يمكن حذف المشرف الرئيسي."
                        )

                        return

                    with closing(get_db()) as conn:

                        conn.execute(
                            """
                            DELETE FROM admins
                            WHERE user_id = ?
                            """,
                            (remove_admin,),
                        )

                        conn.commit()

                    context.user_data.clear()

                    await update.message.reply_text(

                        "🗑 تمت إزالة المشرف.",

                        reply_markup=admin_keyboard(),
                    )

                    return

                except ValueError:

                    await update.message.reply_text(
                        "❌ ID غير صحيح."
                    )

                    return

        # -------------------------------------------------
        # CHANNEL MANAGEMENT
        # -------------------------------------------------

        if state == "channel_manage":

            if text.startswith("+"):

                parts = text[1:].strip().split(
                    maxsplit=1
                )

                if not parts:

                    await update.message.reply_text(
                        "❌ أدخل ID القناة أو المجموعة."
                    )

                    return

                chat_id = parts[0]

                title = (
                    parts[1]
                    if len(parts) > 1
                    else ""
                )

                with closing(get_db()) as conn:

                    conn.execute(
                        """
                        INSERT OR REPLACE
                        INTO channels(chat_id,title)
                        VALUES (?,?)
                        """,
                        (
                            chat_id,
                            title,
                        ),
                    )

                    conn.commit()

                context.user_data.clear()

                await update.message.reply_text(

                    "✅ تمت إضافة القناة/المجموعة.",

                    reply_markup=admin_keyboard(),
                )

                return

        # =================================================
        # SEARCH STATE
        # =================================================

        if state == "search":

            await perform_search(
                update,
                context,
                text,
            )

            return

        # =================================================
        # CONTACT ADMIN STATE
        # =================================================

        if state == "contact_admin":

            await forward_to_admin(
                update,
                context,
            )

            return

        # =================================================
        # SEARCH RESULT
        # =================================================

        if state == "search_result":

            button_id = parse_button_id(
                text
            )

            results = context.user_data.get(
                "search_results",
                {},
            )

            row_info = results.get(
                button_id
            )

            if row_info:

                row = get_button(
                    button_id
                )

                if row:

                    context.user_data.pop(
                        "search_results",
                        None,
                    )

                    await open_dynamic_button(
                        update,
                        context,
                        row,
                    )

                    return

    # =====================================================
    # COMMON NAVIGATION
    # =====================================================

    if text == "🏠 القائمة الرئيسية":

        context.user_data.clear()

        await update.message.reply_text(

            get_setting(
                "start_message"
            ),

            reply_markup=main_keyboard(
                user_id
            ),
        )

        return

    if text == "🔄 تحديث":

        await start(
            update,
            context,
        )

        return

    if text == "🔙 لوحة الأدمن" and is_admin(user_id):

        await admin_panel(
            update,
            context,
        )

        return

    if text == "🔙 رجوع":

        parent_id = context.user_data.get(
            "parent_id",
            0,
        )

        category = context.user_data.get(
            "category"
        )

        if not category:

            await start(
                update,
                context,
            )

            return

        if parent_id == 0:

            await start(
                update,
                context,
            )

            return

        row = get_button(
            parent_id
        )

        if not row:

            await start(
                update,
                context,
            )

            return

        previous_id = row[1]

        await show_section(

            update,
            context,
            previous_id,
            category,
        )

        return

    # =====================================================
    # USER MAIN
    # =====================================================

    if text == "📖 تعلم كيفية استخدام البوت":

        await update.message.reply_text(

            HELP_TEXT,

            reply_markup=back_keyboard(),
        )

        return

    if text == "📞 تواصل معنا":

        await update.message.reply_text(

            CONTACT_TEXT,

            reply_markup=back_keyboard(),
        )

        return

    if text == "💬 مراسلة الأدمن":

        await contact_admin_start(
            update,
            context,
        )

        return

    if text in CATEGORIES:

        category = CATEGORIES[text]

        await show_section(

            update,
            context,
            0,
            category,
        )

        return

    if text == "🔍 البحث في المواد":

        await search_start(
            update,
            context,
        )

        return

    # =====================================================
    # ADMIN MENU
    # =====================================================

    if is_admin(user_id):

        if text == "⚙️ لوحة الأدمن":

            await admin_panel(
                update,
                context,
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

                news = conn.execute(
                    "SELECT COUNT(*) FROM news"
                ).fetchone()[0]

            await update.message.reply_text(

                f"📊 إحصائيات البوت\n\n"
                f"👥 المشتركون: {users}\n"
                f"🔘 الأزرار: {buttons}\n"
                f"📝 المشاركات: {posts}\n"
                f"📰 الأخبار: {news}\n\n"
                f"🤖 الحالة: "
                f"{'🛠 صيانة' if get_setting('maintenance') == '1' else '🟢 يعمل'}",

                reply_markup=admin_keyboard(),
            )

            return

        if text == "👥 المشتركين":

            users = get_all_users()

            await update.message.reply_text(

                f"👥 عدد المشتركين:\n\n"
                f"🔢 {len(users)} مستخدم",

                reply_markup=admin_keyboard(),
            )

            return

        if text == "🔘 محرر الأزرار":

            await button_editor(
                update,
                context,
            )

            return

        if text == "📝 محرر المشاركات":

            await post_editor(
                update,
                context,
            )

            return

        if text == "➕ إضافة زر":

            await add_button_start(
                update,
                context,
            )

            return

        if text == "✏️ تعديل زر":

            await edit_button_start(
                update,
                context,
            )

            return

        if text == "🗑 حذف زر":

            await delete_button_start(
                update,
                context,
            )

            return

        if text == "📋 عرض الأزرار":

            buttons = all_buttons()

            if not buttons:

                result = "📋 لا توجد أزرار حالياً."

            else:

                result = "📋 جميع الأزرار:\n\n"

                for (
                    button_id,
                    title,
                    parent_id,
                    category,
                    position,
                ) in buttons:

                    result += (
                        f"🔘 {title} "
                        f"〔{button_id}〕\n"
                        f"📁 {CATEGORY_NAMES.get(category, category)}\n"
                        f"↳ الأب: {parent_id}\n\n"
                    )

            await update.message.reply_text(

                result,

                reply_markup=button_editor_keyboard(),
            )

            return

        if text == "↕️ ترتيب الأزرار":

            await update.message.reply_text(

                "↕️ ترتيب الأزرار\n\n"
                "حالياً يتم حفظ ترتيب الأزرار "
                "حسب ترتيب إضافتها داخل كل قائمة.",

                reply_markup=button_editor_keyboard(),
            )

            return

        # -------------------------------------------------
        # POST EDITOR
        # -------------------------------------------------

        if text == "➕ إضافة محتوى":

            await select_post_button(
                update,
                context,
                "post_add_select",
            )

            return

        if text == "✏️ تعديل محتوى":

            await select_post_button(
                update,
                context,
                "post_edit_select",
            )

            return

        if text == "🗑 حذف محتوى":

            await select_post_button(
                update,
                context,
                "post_delete_select",
            )

            return

        if text == "📋 عرض المحتوى":

            with closing(get_db()) as conn:

                rows = conn.execute(
                    """
                    SELECT
                        b.id,
                        b.title,
                        p.content_type
                    FROM buttons b
                    LEFT JOIN posts p
                    ON p.button_id = b.id
                    ORDER BY
                        b.category,
                        b.position,
                        b.id
                    """
                ).fetchall()

            result = "📋 محتوى الأزرار:\n\n"

            if not rows:

                result += "لا توجد أزرار."

            else:

                for button_id, title, content_type in rows:

                    result += (
                        f"🔘 {title} 〔{button_id}〕\n"
                        f"📄 {content_type or 'لا يوجد'}\n\n"
                    )

            await update.message.reply_text(

                result,

                reply_markup=post_editor_keyboard(),
            )

            return

        # -------------------------------------------------
        # NEWS
        # -------------------------------------------------

        if text == "📰 محرر الأخبار":

            await news_editor(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # BROADCAST
        # -------------------------------------------------

        if text == "📢 إرسال جماعي":

            await broadcast_start(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # SETTINGS
        # -------------------------------------------------

        if text == "⚙️ إعدادات البوت":

            await bot_settings(
                update,
                context,
            )

            return

        if text == "🛠 وضع الصيانة":

            await toggle_maintenance(
                update,
                context,
            )

            return

        if text == "✏️ رسالة البدء":

            await edit_start_message(
                update,
                context,
            )

            return

        if text == "🔧 رسالة الصيانة":

            await edit_maintenance_message(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # ADMINS
        # -------------------------------------------------

        if text == "👮 إعداد المشرفين":

            await admins(
                update,
                context,
            )

            return

        # -------------------------------------------------
        # CHANNELS
        # -------------------------------------------------

        if text == "📢 قنوات ومجموعات":

            await channels(
                update,
                context,
            )

            return

    # =====================================================
    # DYNAMIC USER BUTTON
    # =====================================================

    parent_id = context.user_data.get(
        "parent_id",
        0,
    )

    category = context.user_data.get(
        "category"
    )

    if category:

        children = get_children(
            parent_id,
            category,
        )

        for row in children:

            if text == f"{row[2]} 〔{row[0]}〕":

                await open_dynamic_button(
                    update,
                    context,
                    row,
                )

                return

    # =====================================================
    # UNKNOWN
    # =====================================================

    await update.message.reply_text(

        "❓ لم أفهم هذا الخيار.\n"
        "اختر من القائمة الظاهرة أمامك.",

        reply_markup=(
            admin_keyboard()
            if is_admin(user_id)
            else main_keyboard(user_id)
        ),
    )


# =========================================================
# MEDIA HANDLER
# =========================================================

async def handle_media(
    update,
    context,
):

    user_id = update.effective_user.id

    if not is_admin(user_id):
        return

    state = context.user_data.get(
        "state"
    )

    # -----------------------------------------------------
    # CONTENT MEDIA
    # -----------------------------------------------------

    if state == "content_media":

        button_id = context.user_data.get(
            "selected_button"
        )

        content_type = context.user_data.get(
            "content_type"
        )

        file_id = None
        caption = update.message.caption or ""

        if (
            content_type == "document"
            and update.message.document
        ):

            file_id = update.message.document.file_id

        elif (
            content_type == "photo"
            and update.message.photo
        ):

            file_id = update.message.photo[-1].file_id

        elif (
            content_type == "video"
            and update.message.video
        ):

            file_id = update.message.video.file_id

        else:

            await update.message.reply_text(

                "❌ نوع الملف غير مطابق.\n"
                "أرسل النوع المطلوب من القائمة.",

            )

            return

        save_post(

            button_id,

            content_type,

            file_id=file_id,

            caption=caption,
        )

        context.user_data.clear()

        await update.message.reply_text(

            "✅ تم حفظ المحتوى وربطه بالزر بنجاح.",

            reply_markup=post_editor_keyboard(),
        )

        return

    # -----------------------------------------------------
    # BROADCAST MEDIA
    # -----------------------------------------------------

    if state == "broadcast":

        await do_broadcast(
            update,
            context,
        )

        return

    # -----------------------------------------------------
    # CONTACT ADMIN MEDIA
    # -----------------------------------------------------

    if state == "contact_admin":

        await forward_to_admin(
            update,
            context,
        )

        return


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context,
):

    logging.error(
        "Exception while handling update:",
        exc_info=context.error,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود.\n"
            "أضف التوكن في Environment Variables."
        )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # START
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # MEDIA
    app.add_handler(
        MessageHandler(
            (
                filters.Document.ALL
                | filters.PHOTO
                | filters.VIDEO
            ),
            handle_media,
        )
    )

    # TEXT
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )

    # ERRORS
    app.add_error_handler(
        error_handler
    )

    print(
        "🤖 البوت يعمل الآن..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
