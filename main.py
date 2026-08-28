import os
import sqlite3
import logging
from contextlib import closing

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

1️⃣ اختر القسم من القائمة الرئيسية.
2️⃣ ادخل إلى المادة المطلوبة.
3️⃣ اختر المحاضرة أو الملخص أو الملف.
4️⃣ يمكنك استخدام 🔍 البحث في المواد للعثور على المحتوى بسرعة.
5️⃣ استخدم 🔙 رجوع للعودة للقائمة السابقة.
6️⃣ استخدم 🏠 القائمة الرئيسية للعودة إلى البداية."""

START_TEXT = """👋 أهلاً وسهلاً بك في المنصة الرسمية لدفعة الهندسة 2026.

📚 من هنا يمكنك الوصول إلى المواد الدراسية والمحاضرات والملخصات والملفات بسهولة.

اختر من القائمة أدناه 👇"""


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with closing(get_db()) as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            )
        """)

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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                title TEXT,
                username TEXT
            )
        """)

        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES (?)",
            (ADMIN_ID,),
        )

        defaults = {
            "maintenance": "0",
            "start_message": START_TEXT,
            "maintenance_message": "🛠 البوت حالياً في وضع الصيانة.\nيرجى المحاولة لاحقاً.",
            "latest_news": "",
            "editor_text": "",
        }

        for key, value in defaults.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, value),
            )

        conn.commit()


init_db()


def get_setting(key):
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else ""


def set_setting(key, value):
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True

    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None


def save_user(user):
    with closing(get_db()) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users(user_id, first_name, username)
            VALUES (?, ?, ?)
        """, (
            user.id,
            user.first_name or "",
            user.username or "",
        ))
        conn.commit()


def get_all_users():
    with closing(get_db()) as conn:
        return [
            row[0]
            for row in conn.execute("SELECT user_id FROM users").fetchall()
        ]


# =========================================================
# KEYBOARDS
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
    ]

    if is_admin(user_id):
        rows.append([KeyboardButton("⚙️ لوحة الأدمن")])

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
            KeyboardButton("❌ إلغاء"),
        ]
    ])


# =========================================================
# NAVIGATION
# =========================================================

def get_children(parent_id):
    with closing(get_db()) as conn:
        return conn.execute("""
            SELECT id, title
            FROM buttons
            WHERE parent_id = ?
            ORDER BY position, id
        """, (parent_id,)).fetchall()


def get_button(button_id):
    with closing(get_db()) as conn:
        return conn.execute("""
            SELECT id, parent_id, title, position
            FROM buttons
            WHERE id = ?
        """, (button_id,)).fetchone()


def get_button_path(parent_id):
    if parent_id == 0:
        return []

    path = []
    current = parent_id

    while current:
        row = get_button(current)
        if not row:
            break
        path.append(row)
        current = row[1]

    path.reverse()
    return path


def navigation_keyboard(parent_id, user_id):
    rows = []

    children = get_children(parent_id)

    for i in range(0, len(children), 2):
        row = [KeyboardButton(children[i][1])]
        if i + 1 < len(children):
            row.append(KeyboardButton(children[i + 1][1]))
        rows.append(row)

    if parent_id != 0:
        row = get_button(parent_id)
        previous_id = row[1] if row else 0
        rows.append([
            KeyboardButton("🔙 رجوع"),
            KeyboardButton("🏠 القائمة الرئيسية"),
        ])
    else:
        rows.append([
            KeyboardButton("🏠 القائمة الرئيسية"),
        ])

    return keyboard(rows)


async def show_section(update, context, parent_id=0):
    context.user_data["parent_id"] = parent_id
    context.user_data.pop("state", None)
    context.user_data.pop("selected_button", None)

    children = get_children(parent_id)

    if parent_id == 0:
        title = "📚 المواد الدراسية"
    else:
        row = get_button(parent_id)
        title = row[2] if row else "القسم"

    if not children:
        await update.message.reply_text(
            f"📂 {title}\n\nلا توجد أزرار مضافة داخل هذا القسم حالياً.",
            reply_markup=navigation_keyboard(parent_id, update.effective_user.id),
        )
        return

    await update.message.reply_text(
        f"📂 {title}\n\nاختر من القائمة:",
        reply_markup=navigation_keyboard(parent_id, update.effective_user.id),
    )


async def open_dynamic_button(update, context, button):
    button_id, parent_id, title, _ = button

    children = get_children(button_id)

    if children:
        await show_section(update, context, button_id)
        return

    with closing(get_db()) as conn:
        post = conn.execute("""
            SELECT content_type, text_content, file_id, caption
            FROM posts
            WHERE button_id = ?
        """, (button_id,)).fetchone()

    if not post:
        await update.message.reply_text(
            f"📌 {title}\n\nلا يوجد محتوى مضاف لهذا الزر حالياً.",
            reply_markup=navigation_keyboard(parent_id, update.effective_user.id),
        )
        return

    content_type, text_content, file_id, caption = post

    context.user_data["parent_id"] = parent_id

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
    save_user(update.effective_user)
    context.user_data.clear()

    if (
        get_setting("maintenance") == "1"
        and not is_admin(update.effective_user.id)
    ):
        await update.message.reply_text(
            get_setting("maintenance_message"),
            reply_markup=keyboard([[KeyboardButton("🔄 تحديث")]]),
        )
        return

    await update.message.reply_text(
        get_setting("start_message"),
        reply_markup=main_keyboard(update.effective_user.id),
    )


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "⚙️ لوحة الأدمن\n\nاختر القسم المطلوب:",
        reply_markup=admin_keyboard(),
    )


# =========================================================
# BUTTON EDITOR
# =========================================================

async def button_editor(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "🔘 محرر الأزرار\n\n"
        "هذا القسم خاص بإنشاء وإدارة الأزرار والقوائم فقط.\n\n"
        "أما النصوص والملفات والصور والفيديوهات فتدار من محرر المشاركات.",
        reply_markup=button_editor_keyboard(),
    )


async def add_button_start(update, context):
    context.user_data["state"] = "add_button_title"
    context.user_data["button_parent"] = 0

    await update.message.reply_text(
        "➕ أرسل اسم الزر الجديد.\n\n"
        "بعدها سيطلب منك اختيار مكانه.",
        reply_markup=cancel_keyboard(),
    )


async def edit_button_start(update, context):
    buttons = get_children(0)

    if not buttons:
        await update.message.reply_text(
            "لا توجد أزرار لتعديلها.",
            reply_markup=button_editor_keyboard(),
        )
        return

    context.user_data["state"] = "choose_edit_button"

    await update.message.reply_text(
        "✏️ اختر الزر الذي تريد تعديله:",
        reply_markup=keyboard(
            [[KeyboardButton(title)] for _, title in buttons]
            + [[KeyboardButton("❌ إلغاء")]]
        ),
    )


async def delete_button_start(update, context):
    buttons = get_children(0)

    if not buttons:
        await update.message.reply_text(
            "🗑 لا توجد أزرار لحذفها.",
            reply_markup=button_editor_keyboard(),
        )
        return

    context.user_data["state"] = "choose_delete_button"

    await update.message.reply_text(
        "🗑 اختر الزر الذي تريد حذفه:",
        reply_markup=keyboard(
            [[KeyboardButton(title)] for _, title in buttons]
            + [[KeyboardButton("❌ إلغاء")]]
        ),
    )


async def confirm_delete(update, context, button_id):
    row = get_button(button_id)

    if not row:
        await update.message.reply_text(
            "❌ الزر غير موجود.",
            reply_markup=button_editor_keyboard(),
        )
        context.user_data.clear()
        return

    context.user_data["delete_id"] = button_id
    context.user_data["state"] = "confirm_delete"

    await update.message.reply_text(
        f"⚠️ تأكيد الحذف\n\n"
        f"هل تريد حذف الزر:\n"
        f"« {row[2]} » ؟\n\n"
        f"سيتم حذف محتواه وجميع أزراره الفرعية أيضاً.",
        reply_markup=keyboard([
            [KeyboardButton("✅ نعم، حذف")],
            [KeyboardButton("❌ إلغاء")],
        ]),
    )


def delete_tree(button_id):
    with closing(get_db()) as conn:
        cur = conn.cursor()

        children = cur.execute(
            "SELECT id FROM buttons WHERE parent_id = ?",
            (button_id,),
        ).fetchall()

        for (child_id,) in children:
            delete_tree_with_cursor(cur, child_id)

        cur.execute("DELETE FROM posts WHERE button_id = ?", (button_id,))
        cur.execute("DELETE FROM buttons WHERE id = ?", (button_id,))
        conn.commit()


def delete_tree_with_cursor(cur, button_id):
    children = cur.execute(
        "SELECT id FROM buttons WHERE parent_id = ?",
        (button_id,),
    ).fetchall()

    for (child_id,) in children:
        delete_tree_with_cursor(cur, child_id)

    cur.execute("DELETE FROM posts WHERE button_id = ?", (button_id,))
    cur.execute("DELETE FROM buttons WHERE id = ?", (button_id,))


# =========================================================
# POST EDITOR
# =========================================================

async def post_editor(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "📝 محرر المشاركات\n\n"
        "هذا القسم خاص بمحتوى الأزرار.\n"
        "يمكنك ربط الزر بنص أو PDF أو صورة أو فيديو.",
        reply_markup=post_editor_keyboard(),
    )


def all_buttons():
    with closing(get_db()) as conn:
        return conn.execute("""
            SELECT id, title, parent_id
            FROM buttons
            ORDER BY position, id
        """).fetchall()


async def select_post_button(update, context, action):
    buttons = all_buttons()

    if not buttons:
        await update.message.reply_text(
            "❌ لا توجد أزرار. أنشئ الأزرار أولاً من محرر الأزرار.",
            reply_markup=post_editor_keyboard(),
        )
        return

    context.user_data["state"] = action

    rows = []
    for button_id, title, parent_id in buttons:
        rows.append([
            KeyboardButton(f"{title} 〔{button_id}〕")
        ])

    rows.append([KeyboardButton("❌ إلغاء")])

    await update.message.reply_text(
        "اختر الزر الذي تريد التعامل مع محتواه:",
        reply_markup=keyboard(rows),
    )


async def add_content_start(update, context):
    await select_post_button(update, context, "select_post_add")


async def edit_content_start(update, context):
    await select_post_button(update, context, "select_post_edit")


async def delete_content_start(update, context):
    await select_post_button(update, context, "select_post_delete")


def parse_button_choice(text):
    if "〔" not in text or "〕" not in text:
        return None

    try:
        return int(text.rsplit("〔", 1)[1].split("〕", 1)[0])
    except (ValueError, IndexError):
        return None


# =========================================================
# CONTENT SAVING
# =========================================================

async def ask_content_type(update, context):
    context.user_data["state"] = "choose_content_type"

    await update.message.reply_text(
        "اختر نوع المحتوى:",
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
                KeyboardButton("❌ إلغاء"),
            ],
        ]),
    )


async def save_post(button_id, content_type, text=None, file_id=None, caption=None):
    with closing(get_db()) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO posts
            (button_id, content_type, text_content, file_id, caption)
            VALUES (?, ?, ?, ?, ?)
        """, (
            button_id,
            content_type,
            text,
            file_id,
            caption,
        ))
        conn.commit()


# =========================================================
# NEWS
# =========================================================

async def news_editor(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "news"

    await update.message.reply_text(
        "📰 محرر الأخبار\n\n"
        "أرسل الخبر الجديد، وسيتم حفظه ليكون جاهزاً للنشر.",
        reply_markup=cancel_keyboard(),
    )


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "broadcast"

    await update.message.reply_text(
        "📢 أرسل الرسالة التي تريد إرسالها لجميع المشتركين.",
        reply_markup=cancel_keyboard(),
    )


async def do_broadcast(update, context):
    users = get_all_users()
    sent = 0
    failed = 0

    for user_id in users:
        try:
            await update.message.copy(chat_id=user_id)
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
# ADMINS / CHANNELS
# =========================================================

async def admins(update, context):
    if not is_admin(update.effective_user.id):
        return

    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT user_id FROM admins ORDER BY user_id"
        ).fetchall()

    text = "👮 إعداد المشرفين\n\n"
    for user_id, in rows:
        text += f"🆔 {user_id}\n"

    text += "\nلإضافة مشرف استخدم الصيغة:\n+ 123456789"
    text += "\nلحذف مشرف:\n- 123456789"

    context.user_data["state"] = "admin_manage"

    await update.message.reply_text(
        text,
        reply_markup=keyboard([
            [KeyboardButton("🔙 لوحة الأدمن")],
        ]),
    )


async def channels(update, context):
    if not is_admin(update.effective_user.id):
        return

    with closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT chat_id, title, username
            FROM channels
            ORDER BY id DESC
        """).fetchall()

    text = "📢 قنوات ومجموعات\n\n"

    if not rows:
        text += "لا توجد قنوات أو مجموعات محفوظة."
    else:
        for chat_id, title, username in rows:
            text += f"📌 {title or 'بدون اسم'}\n🆔 {chat_id}\n"
            if username:
                text += f"🔗 @{username}\n"
            text += "\n"

    text += "\nلإضافة قناة/مجموعة:\nأرسل + ثم ID ثم الاسم، مثال:\n+ -1001234567890 قناتي"

    context.user_data["state"] = "channel_manage"

    await update.message.reply_text(
        text,
        reply_markup=keyboard([
            [KeyboardButton("🔙 لوحة الأدمن")],
        ]),
    )


# =========================================================
# SETTINGS
# =========================================================

async def bot_settings(update, context):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "⚙️ إعدادات البوت\n\n"
        "✏️ رسالة البدء\n"
        "🔧 رسالة الصيانة\n"
        "🛠 تشغيل/إيقاف وضع الصيانة",
        reply_markup=keyboard([
            [KeyboardButton("✏️ رسالة البدء")],
            [KeyboardButton("🔧 رسالة الصيانة")],
            [KeyboardButton("🛠 وضع الصيانة")],
            [KeyboardButton("🔙 لوحة الأدمن")],
        ]),
    )


async def edit_start_message(update, context):
    context.user_data["state"] = "edit_start"
    await update.message.reply_text(
        "✏️ أرسل رسالة /start الجديدة:",
        reply_markup=cancel_keyboard(),
    )


async def edit_maintenance_message(update, context):
    context.user_data["state"] = "edit_maintenance"
    await update.message.reply_text(
        "🔧 أرسل رسالة الصيانة الجديدة:",
        reply_markup=cancel_keyboard(),
    )


async def toggle_maintenance(update, context):
    value = get_setting("maintenance")

    if value == "1":
        set_setting("maintenance", "0")
        text = "🟢 تم إيقاف وضع الصيانة."
    else:
        set_setting("maintenance", "1")
        text = "🛠 تم تفعيل وضع الصيانة."

    await update.message.reply_text(
        text,
        reply_markup=admin_keyboard(),
    )


# =========================================================
# SEARCH
# =========================================================

async def search_start(update, context):
    context.user_data["state"] = "search"

    await update.message.reply_text(
        "🔍 أرسل اسم المادة أو المحاضرة أو الملخص الذي تبحث عنه:",
        reply_markup=keyboard([
            [KeyboardButton("❌ إلغاء")],
        ]),
    )


async def perform_search(update, context, query):
    query = query.strip()

    with closing(get_db()) as conn:
        rows = conn.execute("""
            SELECT id, title, parent_id
            FROM buttons
            WHERE title LIKE ?
            ORDER BY position, id
            LIMIT 30
        """, (f"%{query}%",)).fetchall()

    if not rows:
        await update.message.reply_text(
            "❌ لم يتم العثور على نتائج.",
            reply_markup=main_keyboard(update.effective_user.id),
        )
        context.user_data.clear()
        return

    keyboard_rows = [
        [KeyboardButton(f"{title} 〔{button_id}〕")]
        for button_id, title, _ in rows
    ]

    keyboard_rows.append([
        KeyboardButton("🏠 القائمة الرئيسية")
    ])

    context.user_data["search_results"] = {
        button_id: (button_id, parent_id)
        for button_id, title, parent_id in rows
    }

    await update.message.reply_text(
        f"🔍 نتائج البحث عن: {query}",
        reply_markup=keyboard(keyboard_rows),
    )


# =========================================================
# MAIN TEXT HANDLER
# =========================================================

async def handle_text(update, context):
    if not update.message:
        return

    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    save_user(user)

    # Maintenance for normal users
    if (
        get_setting("maintenance") == "1"
        and not is_admin(user_id)
        and text != "🔄 تحديث"
    ):
        await update.message.reply_text(
            get_setting("maintenance_message"),
            reply_markup=keyboard([[KeyboardButton("🔄 تحديث")]]),
        )
        return

    state = context.user_data.get("state")

    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

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
                reply_markup=main_keyboard(user_id),
            )
        return

    # -----------------------------------------------------
    # ADMIN STATES
    # -----------------------------------------------------

    if is_admin(user_id):

        if state == "add_button_title":
            context.user_data["new_title"] = text
            context.user_data["state"] = "choose_parent"

            buttons = all_buttons()

            rows = [[KeyboardButton("🏠 القائمة الرئيسية")]]
            for button_id, title, parent_id in buttons:
                rows.append([
                    KeyboardButton(f"{title} 〔{button_id}〕")
                ])

            rows.append([KeyboardButton("❌ إلغاء")])

            await update.message.reply_text(
                "📁 اختر مكان الزر الجديد:",
                reply_markup=keyboard(rows),
            )
            return

        if state == "choose_parent":
            if text == "🏠 القائمة الرئيسية":
                parent_id = 0
            else:
                parent_id = parse_button_choice(text)

                if parent_id is None:
                    await update.message.reply_text(
                        "❌ اختر أحد الأزرار الظاهرة."
                    )
                    return

            title = context.user_data.get("new_title", "زر جديد")

            with closing(get_db()) as conn:
                position = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 "
                    "FROM buttons WHERE parent_id = ?",
                    (parent_id,),
                ).fetchone()[0]

                conn.execute("""
                    INSERT INTO buttons(parent_id, title, position)
                    VALUES (?, ?, ?)
                """, (parent_id, title, position))

                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(
                f"✅ تمت إضافة الزر:\n« {title} »",
                reply_markup=button_editor_keyboard(),
            )
            return

        if state == "choose_delete_button":
            button_id = parse_button_choice(text)

            if button_id is None:
                await update.message.reply_text(
                    "❌ اختر الزر من القائمة."
                )
                return

            await confirm_delete(update, context, button_id)
            return

        if state == "confirm_delete":
            if text == "✅ نعم، حذف":
                button_id = context.user_data.get("delete_id")

                if button_id:
                    delete_tree(button_id)

                context.user_data.clear()

                await update.message.reply_text(
                    "🗑 تم حذف الزر ومحتواه وأزراره الفرعية.",
                    reply_markup=button_editor_keyboard(),
                )
                return

            if text == "❌ إلغاء":
                context.user_data.clear()
                await update.message.reply_text(
                    "❌ تم إلغاء الحذف.",
                    reply_markup=button_editor_keyboard(),
                )
                return

        if state == "choose_edit_button":
            button_id = parse_button_choice(text)

            if button_id is None:
                await update.message.reply_text(
                    "❌ اختر الزر من القائمة."
                )
                return

            row = get_button(button_id)

            if not row:
                context.user_data.clear()
                await update.message.reply_text(
                    "❌ الزر غير موجود.",
                    reply_markup=button_editor_keyboard(),
                )
                return

            context.user_data["edit_button_id"] = button_id
            context.user_data["state"] = "edit_button_title"

            await update.message.reply_text(
                f"✏️ الاسم الحالي:\n{row[2]}\n\n"
                f"أرسل الاسم الجديد:",
                reply_markup=cancel_keyboard(),
            )
            return

        if state == "edit_button_title":
            button_id = context.user_data.get("edit_button_id")

            with closing(get_db()) as conn:
                conn.execute(
                    "UPDATE buttons SET title = ? WHERE id = ?",
                    (text, button_id),
                )
                conn.commit()

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تعديل اسم الزر.",
                reply_markup=button_editor_keyboard(),
            )
            return

        # POST EDITOR
        if state in ("select_post_add", "select_post_edit", "select_post_delete"):
            button_id = parse_button_choice(text)

            if button_id is None:
                await update.message.reply_text(
                    "❌ اختر الزر من القائمة."
                )
                return

            if state == "select_post_add":
                context.user_data["selected_button"] = button_id
                await ask_content_type(update, context)
                return

            if state == "select_post_edit":
                context.user_data["selected_button"] = button_id
                await ask_content_type(update, context)
                return

            if state == "select_post_delete":
                with closing(get_db()) as conn:
                    post = conn.execute(
                        "SELECT id FROM posts WHERE button_id = ?",
                        (button_id,),
                    ).fetchone()

                if not post:
                    context.user_data.clear()
                    await update.message.reply_text(
                        "❌ هذا الزر لا يحتوي على محتوى.",
                        reply_markup=post_editor_keyboard(),
                    )
                    return

                context.user_data["delete_post_button"] = button_id
                context.user_data["state"] = "confirm_delete_post"

                await update.message.reply_text(
                    "⚠️ تأكيد حذف المحتوى\n\n"
                    "هل تريد حذف محتوى هذا الزر؟",
                    reply_markup=keyboard([
                        [KeyboardButton("✅ نعم، حذف")],
                        [KeyboardButton("❌ إلغاء")],
                    ]),
                )
                return

        if state == "confirm_delete_post":
            if text == "✅ نعم، حذف":
                button_id = context.user_data.get("delete_post_button")

                with closing(get_db()) as conn:
                    conn.execute(
                        "DELETE FROM posts WHERE button_id = ?",
                        (button_id,),
                    )
                    conn.commit()

                context.user_data.clear()

                await update.message.reply_text(
                    "🗑 تم حذف المحتوى.",
                    reply_markup=post_editor_keyboard(),
                )
                return

        if state == "choose_content_type":
            types = {
                "📝 نص": "text",
                "📄 PDF": "document",
                "🖼 صورة": "photo",
                "🎬 فيديو": "video",
            }

            content_type = types.get(text)

            if not content_type:
                await update.message.reply_text(
                    "❌ اختر نوع المحتوى من القائمة."
                )
                return

            context.user_data["content_type"] = content_type

            if content_type == "text":
                context.user_data["state"] = "content_text"

                await update.message.reply_text(
                    "📝 أرسل النص الذي سيظهر عند الضغط على الزر:",
                    reply_markup=cancel_keyboard(),
                )
            else:
                context.user_data["state"] = "content_media"

                names = {
                    "document": "📄 أرسل ملف PDF:",
                    "photo": "🖼 أرسل الصورة:",
                    "video": "🎬 أرسل الفيديو:",
                }

                await update.message.reply_text(
                    names[content_type],
                    reply_markup=cancel_keyboard(),
                )
            return

        if state == "content_text":
            button_id = context.user_data.get("selected_button")

            await save_post(
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

        if state == "edit_start":
            set_setting("start_message", text)
            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تحديث رسالة /start.",
                reply_markup=admin_keyboard(),
            )
            return

        if state == "edit_maintenance":
            set_setting("maintenance_message", text)
            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تحديث رسالة الصيانة.",
                reply_markup=admin_keyboard(),
            )
            return

        if state == "news":
            set_setting("latest_news", text)
            context.user_data.clear()

            await update.message.reply_text(
                "📰 تم حفظ الخبر.",
                reply_markup=admin_keyboard(),
            )
            return

        if state == "broadcast":
            await do_broadcast(update, context)
            return

        if state == "admin_manage":
            if text.startswith("+"):
                try:
                    new_admin = int(text[1:].strip())

                    with closing(get_db()) as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO admins(user_id) VALUES (?)",
                            (new_admin,),
                        )
                        conn.commit()

                    await update.message.reply_text(
                        "✅ تمت إضافة المشرف.",
                        reply_markup=admin_keyboard(),
                    )
                    context.user_data.clear()
                    return

                except ValueError:
                    pass

            if text.startswith("-"):
                try:
                    remove_admin = int(text[1:].strip())

                    if remove_admin == ADMIN_ID:
                        await update.message.reply_text(
                            "❌ لا يمكن حذف المشرف الرئيسي.",
                            reply_markup=admin_keyboard(),
                        )
                        context.user_data.clear()
                        return

                    with closing(get_db()) as conn:
                        conn.execute(
                            "DELETE FROM admins WHERE user_id = ?",
                            (remove_admin,),
                        )
                        conn.commit()

                    await update.message.reply_text(
                        "🗑 تمت إزالة المشرف.",
                        reply_markup=admin_keyboard(),
                    )
                    context.user_data.clear()
                    return

                except ValueError:
                    pass

        if state == "channel_manage":
            if text.startswith("+"):
                parts = text[1:].strip().split(maxsplit=1)

                if parts:
                    chat_id = parts[0]
                    title = parts[1] if len(parts) > 1 else ""

                    with closing(get_db()) as conn:
                        conn.execute(
                            "INSERT INTO channels(chat_id,title) VALUES (?,?)",
                            (chat_id, title),
                        )
                        conn.commit()

                    context.user_data.clear()

                    await update.message.reply_text(
                        "✅ تمت إضافة القناة/المجموعة.",
                        reply_markup=admin_keyboard(),
                    )
                    return

        # SEARCH
        if state == "search":
            await perform_search(update, context, text)
            return

    # -----------------------------------------------------
    # SEARCH RESULT
    # -----------------------------------------------------

    search_results = context.user_data.get("search_results")

    if search_results and text not in (
        "🏠 القائمة الرئيسية",
        "🔙 رجوع",
    ):
        button_id = parse_button_choice(text)

        if button_id in search_results:
            row = get_button(button_id)

            if row:
                context.user_data.pop("search_results", None)
                await open_dynamic_button(update, context, row)
                return

    # -----------------------------------------------------
    # MAIN NAVIGATION
    # -----------------------------------------------------

    if text == "🏠 القائمة الرئيسية":
        context.user_data.clear()

        await update.message.reply_text(
            get_setting("start_message"),
            reply_markup=main_keyboard(user_id),
        )
        return

    if text == "🔙 لوحة الأدمن" and is_admin(user_id):
        await admin_panel(update, context)
        return

    if text == "🔙 رجوع":
        parent_id = context.user_data.get("parent_id", 0)

        if parent_id == 0:
            await update.message.reply_text(
                get_setting("start_message"),
                reply_markup=main_keyboard(user_id),
            )
            return

        row = get_button(parent_id)
        previous_id = row[1] if row else 0

        await show_section(update, context, previous_id)
        return

    if text == "🔄 تحديث":
        await start(update, context)
        return

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

    if text == "📚 المواد الدراسية":
        await show_section(update, context, 0)
        return

    if text == "📖 المحاضرات":
        await show_section(update, context, 0)
        return

    if text == "📝 الملخصات":
        await show_section(update, context, 0)
        return

    if text == "📂 الملفات":
        await show_section(update, context, 0)
        return

    if text == "❓ الأسئلة":
        await show_section(update, context, 0)
        return

    if text == "🔍 البحث في المواد":
        await search_start(update, context)
        return

    # -----------------------------------------------------
    # ADMIN MENU
    # -----------------------------------------------------

    if not is_admin(user_id):
        # Dynamic button
        parent_id = context.user_data.get("parent_id", 0)

        with closing(get_db()) as conn:
            row = conn.execute("""
                SELECT id, parent_id, title, position
                FROM buttons
                WHERE parent_id = ? AND title = ?
                LIMIT 1
            """, (parent_id, text)).fetchone()

        if row:
            await open_dynamic_button(update, context, row)
        return

    if text == "⚙️ لوحة الأدمن":
        await admin_panel(update, context)
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

        await update.message.reply_text(
            f"📊 إحصائيات البوت\n\n"
            f"👥 المشتركون: {users}\n"
            f"🔘 الأزرار: {buttons}\n"
            f"📝 المشاركات: {posts}\n"
            f"🤖 الحالة: "
            f"{'🛠 صيانة' if get_setting('maintenance') == '1' else '🟢 يعمل'}",
            reply_markup=admin_keyboard(),
        )
        return

    if text == "👥 المشتركين":
        users = get_all_users()

        await update.message.reply_text(
            f"👥 عدد المشتركين:\n\n{len(users)} مستخدم",
            reply_markup=admin_keyboard(),
        )
        return

    if text == "🔘 محرر الأزرار":
        await button_editor(update, context)
        return

    if text == "📝 محرر المشاركات":
        await post_editor(update, context)
        return

    if text == "➕ إضافة زر":
        await add_button_start(update, context)
        return

    if text == "✏️ تعديل زر":
        await edit_button_start(update, context)
        return

    if text == "🗑 حذف زر":
        await delete_button_start(update, context)
        return

    if text == "📋 عرض الأزرار":
        buttons = all_buttons()

        if not buttons:
            result = "📋 لا توجد أزرار."
        else:
            result = "📋 الأزرار:\n\n"
            for button_id, title, parent_id in buttons:
                result += f"🔘 {title} 〔{button_id}〕\n"

        await update.message.reply_text(
            result,
            reply_markup=button_editor_keyboard(),
        )
        return

    if text == "↕️ ترتيب الأزرار":
        await update.message.reply_text(
            "↕️ ترتيب الأزرار\n\n"
            "يمكن تطوير الترتيب بالسحب أو بأوامر نقل للأعلى والأسفل. "
            "حالياً يتم ترتيب الأزرار حسب ترتيب الإضافة.",
            reply_markup=button_editor_keyboard(),
        )
        return

    if text == "➕ إضافة محتوى":
        await add_content_start(update, context)
        return

    if text == "✏️ تعديل محتوى":
        await edit_content_start(update, context)
        return

    if text == "🗑 حذف محتوى":
        await delete_content_start(update, context)
        return

    if text == "📋 عرض المحتوى":
        with closing(get_db()) as conn:
            rows = conn.execute("""
                SELECT b.id, b.title, p.content_type
                FROM buttons b
                LEFT JOIN posts p ON p.button_id = b.id
                ORDER BY b.position, b.id
            """).fetchall()

        result = "📋 محتوى الأزرار:\n\n"

        for button_id, title, content_type in rows:
            result += (
                f"🔘 {title} 〔{button_id}〕\n"
                f"📄 {content_type or 'لا يوجد محتوى'}\n\n"
            )

        await update.message.reply_text(
            result,
            reply_markup=post_editor_keyboard(),
        )
        return

    if text == "📰 محرر الأخبار":
        await news_editor(update, context)
        return

    if text == "📢 إرسال جماعي":
        await broadcast_start(update, context)
        return

    if text == "⚙️ إعدادات البوت":
        await bot_settings(update, context)
        return

    if text == "🛠 وضع الصيانة":
        await toggle_maintenance(update, context)
        return

    if text == "✏️ رسالة البدء":
        await edit_start_message(update, context)
        return

    if text == "🔧 رسالة الصيانة":
        await edit_maintenance_message(update, context)
        return

    if text == "👮 إعداد المشرفين":
        await admins(update, context)
        return

    if text == "📢 قنوات ومجموعات":
        await channels(update, context)
        return

    # Dynamic admin navigation
    parent_id = context.user_data.get("parent_id", 0)

    with closing(get_db()) as conn:
        row = conn.execute("""
            SELECT id, parent_id, title, position
            FROM buttons
            WHERE parent_id = ? AND title = ?
            LIMIT 1
        """, (parent_id, text)).fetchone()

    if row:
        await open_dynamic_button(update, context, row)


# =========================================================
# MEDIA HANDLER
# =========================================================

async def handle_media(update, context):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return

    state = context.user_data.get("state")

    if state != "content_media":
        return

    button_id = context.user_data.get("selected_button")
    content_type = context.user_data.get("content_type")

    file_id = None

    if content_type == "document" and update.message.document:
        file_id = update.message.document.file_id

    elif content_type == "photo" and update.message.photo:
        file_id = update.message.photo[-1].file_id

    elif content_type == "video" and update.message.video:
        file_id = update.message.video.file_id

    else:
        await update.message.reply_text(
            "❌ نوع الملف غير مطابق. أرسل النوع المطلوب."
        )
        return

    await save_post(
        button_id,
        content_type,
        file_id=file_id,
    )

    context.user_data.clear()

    await update.message.reply_text(
        "✅ تم حفظ المحتوى وربطه بالزر بنجاح.",
        reply_markup=post_editor_keyboard(),
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود. أضفه في Environment Variables."
        )

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO,
            handle_media,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    print("🤖 البوت يعمل الآن...")
    app.run_polling()


if __name__ == "__main__":
    main()
