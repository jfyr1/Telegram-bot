import os
import sqlite3
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = "8925599691:AAGvo1qs6akZrIE-uVbcfhMfOVlju1Pzp1s"
ADMIN_ID = 5734654153
DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = db()
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
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT 0,
            title TEXT NOT NULL,
            content_type TEXT DEFAULT 'menu',
            content TEXT,
            file_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            title TEXT,
            username TEXT
        )
    """)

    conn.commit()
    conn.close()

    defaults = {
        "maintenance": "0",
        "start_message":
            "👋 أهلاً وسهلاً بك في البوت الدراسي.\n\n"
            "📚 اختر من القائمة الرئيسية:",
        "maintenance_message":
            "🛠 البوت حالياً في وضع الصيانة.\n"
            "يرجى المحاولة لاحقاً."
    }

    conn = db()
    cur = conn.cursor()

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    cur.execute(
        "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
        (ADMIN_ID,)
    )

    conn.commit()
    conn.close()


init_db()


# =========================================================
# SETTINGS
# =========================================================

def get_setting(key):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    )

    row = cur.fetchone()
    conn.close()

    return row[0] if row else ""


def set_setting(key, value):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO settings (key, value)
        VALUES (?, ?)
    """, (key, value))

    conn.commit()
    conn.close()


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM admins WHERE user_id=?",
        (user_id,)
    )

    result = cur.fetchone()
    conn.close()

    return result is not None


# =========================================================
# USERS
# =========================================================

def save_user(user):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users
        (user_id, first_name, username)
        VALUES (?, ?, ?)
    """, (
        user.id,
        user.first_name or "",
        user.username or ""
    ))

    conn.commit()
    conn.close()


def get_users():
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users")
    users = [row[0] for row in cur.fetchall()]

    conn.close()
    return users


# =========================================================
# MAIN MENU
# =========================================================

def main_keyboard(user_id):

    buttons = [
        [
            KeyboardButton("📚 المواد الدراسية"),
            KeyboardButton("📖 المحاضرات")
        ],
        [
            KeyboardButton("📝 الملخصات"),
            KeyboardButton("📂 الملفات")
        ],
        [
            KeyboardButton("❓ الأسئلة"),
            KeyboardButton("🔍 البحث")
        ]
    ]

    if is_admin(user_id):
        buttons.append([
            KeyboardButton("⚙️ لوحة الأدمن")
        ])

    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        is_persistent=True
    )


# =========================================================
# ADMIN MENU
# =========================================================

def admin_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📊 الإحصائيات"),
                KeyboardButton("👥 المشتركين")
            ],
            [
                KeyboardButton("📰 محرر الأخبار"),
                KeyboardButton("✏️ المحرر النصي")
            ],
            [
                KeyboardButton("🔘 محرر الأزرار"),
                KeyboardButton("📢 إرسال جماعي")
            ],
            [
                KeyboardButton("⚙️ إعدادات البوت"),
                KeyboardButton("🛠 وضع الصيانة")
            ],
            [
                KeyboardButton("✏️ رسالة البدء"),
                KeyboardButton("🔧 رسالة الصيانة")
            ],
            [
                KeyboardButton("👮 إعداد المشرفين"),
                KeyboardButton("📢 قنوات ومجموعات")
            ],
            [
                KeyboardButton("🏠 القائمة الرئيسية")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


# =========================================================
# BUTTON EDITOR MENU
# =========================================================

def editor_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("➕ إضافة زر")
            ],
            [
                KeyboardButton("📝 إضافة نص"),
                KeyboardButton("📄 إضافة PDF")
            ],
            [
                KeyboardButton("🖼 إضافة صورة"),
                KeyboardButton("🎬 إضافة فيديو")
            ],
            [
                KeyboardButton("✏️ تعديل محتوى"),
                KeyboardButton("🗑 حذف زر")
            ],
            [
                KeyboardButton("📋 عرض الأزرار")
            ],
            [
                KeyboardButton("🔙 لوحة الأدمن")
            ]
        ],
        resize_keyboard=True
    )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    save_user(user)

    context.user_data.clear()

    if (
        get_setting("maintenance") == "1"
        and not is_admin(user.id)
    ):
        await update.message.reply_text(
            get_setting("maintenance_message"),
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("🔄 تحديث")]],
                resize_keyboard=True
            )
        )
        return

    await update.message.reply_text(
        get_setting("start_message"),
        reply_markup=main_keyboard(user.id)
    )


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_panel(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "⚙️ لوحة تحكم البوت\n\n"
        "اختر القسم المطلوب:",
        reply_markup=admin_keyboard()
    )


# =========================================================
# STATISTICS
# =========================================================

async def statistics(update, context):

    if not is_admin(update.effective_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM buttons")
    buttons = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM channels")
    channels = cur.fetchone()[0]

    conn.close()

    status = (
        "🛠 وضع الصيانة"
        if get_setting("maintenance") == "1"
        else "🟢 يعمل"
    )

    await update.message.reply_text(
        f"""
📊 إحصائيات البوت

👥 المشتركون: {users}
🔘 الأزرار: {buttons}
📢 القنوات والمجموعات: {channels}

🤖 الحالة: {status}
""",
        reply_markup=admin_keyboard()
    )


# =========================================================
# SUBSCRIBERS
# =========================================================

async def subscribers(update, context):

    if not is_admin(update.effective_user.id):
        return

    users = get_users()

    await update.message.reply_text(
        f"👥 عدد المشتركين:\n\n"
        f"🔢 {len(users)} مستخدم",
        reply_markup=admin_keyboard()
    )


# =========================================================
# MAINTENANCE
# =========================================================

async def maintenance(update, context):

    if not is_admin(update.effective_user.id):
        return

    current = get_setting("maintenance")

    if current == "1":
        set_setting("maintenance", "0")

        await update.message.reply_text(
            "🟢 تم إيقاف وضع الصيانة.",
            reply_markup=admin_keyboard()
        )

    else:
        set_setting("maintenance", "1")

        await update.message.reply_text(
            "🛠 تم تفعيل وضع الصيانة.",
            reply_markup=admin_keyboard()
        )


# =========================================================
# START MESSAGE
# =========================================================

async def edit_start_message(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "start_message"

    await update.message.reply_text(
        "✏️ أرسل رسالة البدء الجديدة:"
    )


# =========================================================
# MAINTENANCE MESSAGE
# =========================================================

async def edit_maintenance_message(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "maintenance_message"

    await update.message.reply_text(
        "🔧 أرسل رسالة الصيانة الجديدة:"
    )


# =========================================================
# BUTTON EDITOR
# =========================================================

async def button_editor(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data.clear()

    await update.message.reply_text(
        "🔘 محرر الأزرار المتقدم\n\n"
        "يمكنك إنشاء زر وربطه بنص أو PDF أو صورة أو فيديو.\n\n"
        "اختر العملية:",
        reply_markup=editor_keyboard()
    )


# =========================================================
# ADD BUTTON
# =========================================================

async def add_button(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "add_button"

    await update.message.reply_text(
        "🔘 أرسل اسم الزر الجديد:"
    )


# =========================================================
# ADD CONTENT TYPE
# =========================================================

async def choose_content_type(update, context, content_type):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["content_type"] = content_type
    context.user_data["state"] = "content"

    messages = {
        "text": "📝 أرسل النص الذي سيظهر عند الضغط على الزر:",
        "pdf": "📄 أرسل ملف PDF الآن:",
        "photo": "🖼 أرسل الصورة الآن:",
        "video": "🎬 أرسل الفيديو الآن:"
    }

    await update.message.reply_text(
        messages[content_type]
    )


# =========================================================
# SAVE BUTTON
# =========================================================

def create_button(title, content_type, content=None, file_id=None):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO buttons
        (parent_id, title, content_type, content, file_id)
        VALUES (?, ?, ?, ?, ?)
    """, (
        0,
        title,
        content_type,
        content,
        file_id
    ))

    conn.commit()
    conn.close()


# =========================================================
# SHOW USER BUTTONS
# =========================================================

async def show_dynamic_buttons(update, context):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title
        FROM buttons
        WHERE parent_id=0
        ORDER BY id ASC
    """)

    buttons = cur.fetchall()
    conn.close()

    if not buttons:

        await update.message.reply_text(
            "📂 لا توجد أقسام مضافة حالياً.",
            reply_markup=main_keyboard(
                update.effective_user.id
            )
        )
        return

    keyboard = []

    for button_id, title in buttons:

        keyboard.append([
            InlineKeyboardButton(
                title,
                callback_data=f"content:{button_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 الرئيسية",
            callback_data="home"
        )
    ])

    await update.message.reply_text(
        "📚 الأقسام الدراسية:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# CONTENT CALLBACK
# =========================================================

async def content_callback(update, context):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "home":

        await query.message.delete()

        await query.message.chat.send_message(
            get_setting("start_message"),
            reply_markup=main_keyboard(
                query.from_user.id
            )
        )

        return

    if not data.startswith("content:"):
        return

    button_id = int(data.split(":")[1])

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT title, content_type, content, file_id
        FROM buttons
        WHERE id=?
    """, (button_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return

    title, content_type, content, file_id = row

    if content_type == "text":

        await query.message.reply_text(
            f"📖 {title}\n\n{content}"
        )

    elif content_type == "pdf":

        await query.message.reply_document(
            document=file_id,
            caption=title
        )

    elif content_type == "photo":

        await query.message.reply_photo(
            photo=file_id,
            caption=title
        )

    elif content_type == "video":

        await query.message.reply_video(
            video=file_id,
            caption=title
        )


# =========================================================
# LIST BUTTONS
# =========================================================

async def list_buttons(update, context):

    if not is_admin(update.effective_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, content_type
        FROM buttons
        ORDER BY id ASC
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:

        await update.message.reply_text(
            "🔘 لا توجد أزرار حالياً.",
            reply_markup=editor_keyboard()
        )
        return

    text = "📋 الأزرار الموجودة:\n\n"

    for button_id, title, content_type in rows:

        type_names = {
            "menu": "📁 قائمة",
            "text": "📝 نص",
            "pdf": "📄 PDF",
            "photo": "🖼 صورة",
            "video": "🎬 فيديو"
        }

        text += (
            f"#{button_id} — {title}\n"
            f"النوع: {type_names.get(content_type, content_type)}\n\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=editor_keyboard()
    )


# =========================================================
# DELETE BUTTON
# =========================================================

async def delete_button_start(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "delete_button"

    await update.message.reply_text(
        "🗑 أرسل رقم الزر الذي تريد حذفه:"
    )


def delete_button(button_id):

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM buttons WHERE id=?",
        (button_id,)
    )

    deleted = cur.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "broadcast"

    await update.message.reply_text(
        "📢 أرسل الرسالة الجماعية الآن:"
    )


async def broadcast(update, context):

    if not is_admin(update.effective_user.id):
        return

    message = update.message.text
    users = get_users()

    sent = 0
    failed = 0

    for user_id in users:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            sent += 1

        except Exception:

            failed += 1

    context.user_data.clear()

    await update.message.reply_text(
        f"""
📢 اكتمل الإرسال الجماعي.

✅ نجح: {sent}
❌ فشل: {failed}
👥 الإجمالي: {len(users)}
""",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADMINS
# =========================================================

async def admins(update, context):

    if not is_admin(update.effective_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM admins"
    )

    rows = cur.fetchall()
    conn.close()

    text = "👮 المشرفون:\n\n"

    for (user_id,) in rows:
        text += f"🆔 {user_id}\n"

    await update.message.reply_text(
        text,
        reply_markup=admin_keyboard()
    )


# =========================================================
# CHANNELS
# =========================================================

async def channels(update, context):

    if not is_admin(update.effective_user.id):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT chat_id, title, username
        FROM channels
        ORDER BY id DESC
    """)

    rows = cur.fetchall()
    conn.close()

    text = "📢 القنوات والمجموعات:\n\n"

    if not rows:
        text += "لا توجد قنوات أو مجموعات مضافة."

    else:

        for chat_id, title, username in rows:

            text += f"📌 {title or 'بدون اسم'}\n"
            text += f"🆔 {chat_id}\n"

            if username:
                text += f"🔗 @{username}\n"

            text += "\n"

    await update.message.reply_text(
        text,
        reply_markup=admin_keyboard()
    )


# =========================================================
# NEWS EDITOR
# =========================================================

async def news_editor(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "news"

    await update.message.reply_text(
        "📰 محرر الأخبار\n\n"
        "أرسل نص الخبر أو الإعلان الآن:"
    )


# =========================================================
# TEXT EDITOR
# =========================================================

async def text_editor(update, context):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["state"] = "editor_text"

    await update.message.reply_text(
        "✏️ المحرر النصي\n\n"
        "أرسل النص الذي تريد حفظه:"
    )


# =========================================================
# HANDLE MEDIA
# =========================================================

async def handle_media(update, context):

    if not is_admin(update.effective_user.id):
        return

    state = context.user_data.get("state")

    if state != "content":
        return

    content_type = context.user_data.get(
        "content_type"
    )

    title = context.user_data.get(
        "button_title",
        "محتوى جديد"
    )

    file_id = None

    if content_type == "pdf" and update.message.document:

        file_id = update.message.document.file_id

    elif content_type == "photo" and update.message.photo:

        file_id = update.message.photo[-1].file_id

    elif content_type == "video" and update.message.video:

        file_id = update.message.video.file_id

    else:

        await update.message.reply_text(
            "❌ نوع الملف غير صحيح."
        )
        return

    create_button(
        title,
        content_type,
        file_id=file_id
    )

    context.user_data.clear()

    await update.message.reply_text(
        "✅ تمت إضافة المحتوى بنجاح.",
        reply_markup=editor_keyboard()
    )


# =========================================================
# TEXT HANDLER
# =========================================================

async def handle_text(update, context):

    text = update.message.text
    user_id = update.effective_user.id

    if is_admin(user_id):

        state = context.user_data.get("state")

        # -----------------------------------------------
        # إضافة زر
        # -----------------------------------------------

        if state == "add_button":

            context.user_data["button_title"] = text
            context.user_data["state"] = "choose_type"

            await update.message.reply_text(
                "🔘 الزر: "
                + text
                + "\n\nاختر نوع المحتوى:",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [
                            KeyboardButton("📝 نص"),
                            KeyboardButton("📄 PDF")
                        ],
                        [
                            KeyboardButton("🖼 صورة"),
                            KeyboardButton("🎬 فيديو")
                        ],
                        [
                            KeyboardButton("📁 قائمة")
                        ],
                        [
                            KeyboardButton("🔙 محرر الأزرار")
                        ]
                    ],
                    resize_keyboard=True
                )
            )

            return

        # -----------------------------------------------
        # اختيار نوع المحتوى
        # -----------------------------------------------

        if state == "choose_type":

            types = {
                "📝 نص": "text",
                "📄 PDF": "pdf",
                "🖼 صورة": "photo",
                "🎬 فيديو": "video",
                "📁 قائمة": "menu"
            }

            if text in types:

                content_type = types[text]

                if content_type == "menu":

                    create_button(
                        context.user_data["button_title"],
                        "menu"
                    )

                    context.user_data.clear()

                    await update.message.reply_text(
                        "✅ تمت إضافة القائمة بنجاح.",
                        reply_markup=editor_keyboard()
                    )

                else:

                    await choose_content_type(
                        update,
                        context,
                        content_type
                    )

                return

        # -----------------------------------------------
        # نص المحتوى
        # -----------------------------------------------

        if state == "content" and \
                context.user_data.get("content_type") == "text":

            title = context.user_data.get(
                "button_title",
                "نص"
            )

            create_button(
                title,
                "text",
                content=text
            )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تمت إضافة النص بنجاح.",
                reply_markup=editor_keyboard()
            )

            return

        # -----------------------------------------------
        # حذف
        # -----------------------------------------------

        if state == "delete_button":

            try:
                button_id = int(text)

            except ValueError:

                await update.message.reply_text(
                    "❌ أرسل رقم الزر فقط."
                )
                return

            if delete_button(button_id):

                await update.message.reply_text(
                    "🗑 تم حذف الزر بنجاح.",
                    reply_markup=editor_keyboard()
                )

            else:

                await update.message.reply_text(
                    "❌ لم يتم العثور على هذا الزر.",
                    reply_markup=editor_keyboard()
                )

            context.user_data.clear()
            return

        # -----------------------------------------------
        # رسالة البدء
        # -----------------------------------------------

        if state == "start_message":

            set_setting(
                "start_message",
                text
            )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تحديث رسالة البدء.",
                reply_markup=admin_keyboard()
            )

            return

        # -----------------------------------------------
        # رسالة الصيانة
        # -----------------------------------------------

        if state == "maintenance_message":

            set_setting(
                "maintenance_message",
                text
            )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم تحديث رسالة الصيانة.",
                reply_markup=admin_keyboard()
            )

            return

        # -----------------------------------------------
        # الإرسال الجماعي
        # -----------------------------------------------

        if state == "broadcast":

            await broadcast(
                update,
                context
            )

            return

        # -----------------------------------------------
        # الأخبار
        # -----------------------------------------------

        if state == "news":

            set_setting(
                "latest_news",
                text
            )

            context.user_data.clear()

            await update.message.reply_text(
                "📰 تم حفظ الخبر بنجاح.",
                reply_markup=admin_keyboard()
            )

            return

        # -----------------------------------------------
        # المحرر النصي
        # -----------------------------------------------

        if state == "editor_text":

            set_setting(
                "editor_text",
                text
            )

            context.user_data.clear()

            await update.message.reply_text(
                "✏️ تم حفظ النص بنجاح.",
                reply_markup=admin_keyboard()
            )

            return

    # =====================================================
    # GENERAL MENU
    # =====================================================

    if text == "⚙️ لوحة الأدمن":

        await admin_panel(
            update,
            context
        )
        return

    if text == "🏠 القائمة الرئيسية":

        context.user_data.clear()

        await update.message.reply_text(
            get_setting("start_message"),
            reply_markup=main_keyboard(user_id)
        )
        return

    if text == "📚 المواد الدراسية":

        await show_dynamic_buttons(
            update,
            context
        )
        return

    if text == "📖 المحاضرات":

        await show_dynamic_buttons(
            update,
            context
        )
        return

    if text == "📝 الملخصات":

        await show_dynamic_buttons(
            update,
            context
        )
        return

    if text == "📂 الملفات":

        await show_dynamic_buttons(
            update,
            context
        )
        return

    if text == "❓ الأسئلة":

        await show_dynamic_buttons(
            update,
            context
        )
        return

    if text == "🔍 البحث":

        await update.message.reply_text(
            "🔍 أرسل كلمة البحث."
        )
        return

    # =====================================================
    # ADMIN
    # =====================================================

    if not is_admin(user_id):
        return

    if text == "📊 الإحصائيات":

        await statistics(
            update,
            context
        )
        return

    if text == "👥 المشتركين":

        await subscribers(
            update,
            context
        )
        return

    if text == "📰 محرر الأخبار":

        await news_editor(
            update,
            context
        )
        return

    if text == "✏️ المحرر النصي":

        await text_editor(
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

    if text == "➕ إضافة زر":

        await add_button(
            update,
            context
        )
        return

    if text == "📝 إضافة نص":

        context.user_data["button_title"] = "نص جديد"

        await choose_content_type(
            update,
            context,
            "text"
        )
        return

    if text == "📄 إضافة PDF":

        context.user_data["button_title"] = "ملف PDF"

        await choose_content_type(
            update,
            context,
            "pdf"
        )
        return

    if text == "🖼 إضافة صورة":

        context.user_data["button_title"] = "صورة جديدة"

        await choose_content_type(
            update,
            context,
            "photo"
        )
        return

    if text == "🎬 إضافة فيديو":

        context.user_data["button_title"] = "فيديو جديد"

        await choose_content_type(
            update,
            context,
            "video"
        )
        return

    if text == "📋 عرض الأزرار":

        await list_buttons(
            update,
            context
        )
        return

    if text == "🗑 حذف زر":

        await delete_button_start(
            update,
            context
        )
        return

    if text == "🔙 محرر الأزرار":

        await button_editor(
            update,
            context
        )
        return

    if text == "📢 إرسال جماعي":

        await broadcast_start(
            update,
            context
        )
        return

    if text == "📣 الإعلانات":

        await news_editor(
            update,
            context
        )
        return

    if text == "⚙️ إعدادات البوت":

        await update.message.reply_text(
            "⚙️ إعدادات البوت\n\n"
            "✏️ رسالة البدء\n"
            "🔧 رسالة الصيانة",
            reply_markup=admin_keyboard()
        )
        return

    if text == "🛠 وضع الصيانة":

        await maintenance(
            update,
            context
        )
        return

    if text == "✏️ رسالة البدء":

        await edit_start_message(
            update,
            context
        )
        return

    if text == "🔧 رسالة الصيانة":

        await edit_maintenance_message(
            update,
            context
        )
        return

    if text == "👮 إعداد المشرفين":

        await admins(
            update,
            context
        )
        return

    if text == "📢 قنوات ومجموعات":

        await channels(
            update,
            context
        )
        return

    if text == "🔄 تحديث":

        await start(
            update,
            context
        )
        return


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود في Environment Variables"
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
        CallbackQueryHandler(
            content_callback
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_media
        )
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_media
        )
    )

    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_media
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("🤖 البوت يعمل الآن...")

    app.run_polling()


if __name__ == "__main__":
    main()
