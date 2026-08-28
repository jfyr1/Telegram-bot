import os
import sqlite3
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# إعدادات البوت
# =========================================================

TOKEN = os.getenv("BOT_TOKEN", "8925599691:AAGvo1qs6akZrIE-uVbcfhMfOVlju1Pzp1s")
ADMIN_ID = 5734654153
DB_NAME = "study_bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================================================
# قاعدة البيانات
# =========================================================

def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT 0,
            title TEXT NOT NULL,
            position INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER,
            title TEXT NOT NULL,
            content_type TEXT DEFAULT 'text',
            content TEXT,
            file_id TEXT,
            position INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()

# =========================================================
# تسجيل المستخدم
# =========================================================

def save_user(user):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users
        (id, first_name, username)
        VALUES (?, ?, ?)
    """, (
        user.id,
        user.first_name or "",
        user.username or ""
    ))

    conn.commit()
    conn.close()


# =========================================================
# الكليشة الرئيسية
# =========================================================

WELCOME_TEXT = """
👋 أهلاً وسهلاً بك في البوت الدراسي 📚

🎓 منصتك التعليمية التي تجمع لك:
📖 المحاضرات
📝 الملخصات
📚 الملازم والكتب
❓ الأسئلة والمراجعات
📂 الملفات الدراسية

اختر من القائمة أدناه للوصول إلى المحتوى الذي تحتاجه.

🚀 بالتوفيق والنجاح الدائم ❤️
"""

# =========================================================
# إعداد القائمة الرئيسية
# =========================================================

def main_keyboard(user_id):

    keyboard = [
        [
            InlineKeyboardButton("📚 المواد الدراسية", callback_data="materials"),
            InlineKeyboardButton("📖 المحاضرات", callback_data="lectures"),
        ],
        [
            InlineKeyboardButton("📝 الملخصات", callback_data="summaries"),
            InlineKeyboardButton("📚 الملازم والكتب", callback_data="books"),
        ],
        [
            InlineKeyboardButton("❓ الأسئلة", callback_data="questions"),
            InlineKeyboardButton("🔍 البحث", callback_data="search"),
        ],
    ]

    if user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin")
        ])

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    save_user(user)

    context.user_data.clear()

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_keyboard(user.id)
    )


# =========================================================
# القائمة الرئيسية
# =========================================================

async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if query:
        await query.answer()

        await query.edit_message_text(
            WELCOME_TEXT,
            reply_markup=main_keyboard(query.from_user.id)
        )

    else:
        await update.message.reply_text(
            WELCOME_TEXT,
            reply_markup=main_keyboard(update.effective_user.id)
        )


# =========================================================
# عرض المواد
# =========================================================

async def show_materials(query):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title
        FROM menus
        WHERE parent_id = 0
        ORDER BY position, id
    """)

    rows = cur.fetchall()
    conn.close()

    keyboard = []

    for menu_id, title in rows:
        keyboard.append([
            InlineKeyboardButton(
                f"📚 {title}",
                callback_data=f"menu:{menu_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="home")
    ])

    if not rows:
        text = "📚 لا توجد مواد مضافة حالياً."
    else:
        text = "📚 اختر المادة الدراسية:"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# عرض قائمة
# =========================================================

async def show_menu(query, menu_id):

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT title, parent_id FROM menus WHERE id = ?",
        (menu_id,)
    )

    menu = cur.fetchone()

    if not menu:
        conn.close()
        return

    title, parent_id = menu

    cur.execute("""
        SELECT id, title
        FROM menus
        WHERE parent_id = ?
        ORDER BY position, id
    """, (menu_id,))

    submenus = cur.fetchall()

    cur.execute("""
        SELECT id, title, content_type
        FROM contents
        WHERE menu_id = ?
        ORDER BY position, id
    """, (menu_id,))

    contents = cur.fetchall()

    conn.close()

    keyboard = []

    for sub_id, sub_title in submenus:
        keyboard.append([
            InlineKeyboardButton(
                f"📂 {sub_title}",
                callback_data=f"menu:{sub_id}"
            )
        ])

    for content_id, content_title, content_type in contents:

        icon = {
            "text": "📄",
            "pdf": "📕",
            "photo": "🖼",
            "video": "🎥",
            "document": "📎",
            "audio": "🎧"
        }.get(content_type, "📄")

        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {content_title}",
                callback_data=f"content:{content_id}"
            )
        ])

    if parent_id == 0:
        back = "materials"
    else:
        back = f"menu:{parent_id}"

    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data=back),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home")
    ])

    await query.edit_message_text(
        f"📚 *{title}*\n\nاختر ما تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# =========================================================
# عرض المحتوى
# =========================================================

async def show_content(query, content_id):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT menu_id, title, content_type, content, file_id
        FROM contents
        WHERE id = ?
    """, (content_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        await query.answer("المحتوى غير موجود", show_alert=True)
        return

    menu_id, title, content_type, content, file_id = row

    await query.answer()

    try:

        if content_type == "text":

            await query.message.reply_text(
                f"📖 *{title}*\n\n{content or 'لا يوجد محتوى.'}",
                parse_mode="Markdown"
            )

        elif content_type == "pdf":

            await query.message.reply_document(
                document=file_id,
                caption=f"📕 {title}"
            )

        elif content_type == "document":

            await query.message.reply_document(
                document=file_id,
                caption=f"📎 {title}"
            )

        elif content_type == "photo":

            await query.message.reply_photo(
                photo=file_id,
                caption=f"🖼 {title}"
            )

        elif content_type == "video":

            await query.message.reply_video(
                video=file_id,
                caption=f"🎥 {title}"
            )

        elif content_type == "audio":

            await query.message.reply_audio(
                audio=file_id,
                caption=f"🎧 {title}"
            )

    except Exception as e:
        logging.error(e)
        await query.message.reply_text(
            "❌ حدث خطأ أثناء إرسال المحتوى."
        )


# =========================================================
# لوحة الأدمن
# =========================================================

def admin_keyboard():

    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة مادة", callback_data="add_material"),
            InlineKeyboardButton("➕ إضافة قسم", callback_data="add_menu"),
        ],
        [
            InlineKeyboardButton("📄 إضافة نص", callback_data="add_text"),
            InlineKeyboardButton("📕 إضافة PDF", callback_data="add_pdf"),
        ],
        [
            InlineKeyboardButton("📎 إضافة ملف", callback_data="add_file"),
            InlineKeyboardButton("🖼 إضافة صورة", callback_data="add_photo"),
        ],
        [
            InlineKeyboardButton("🎥 إضافة فيديو", callback_data="add_video"),
            InlineKeyboardButton("🎧 إضافة صوت", callback_data="add_audio"),
        ],
        [
            InlineKeyboardButton("🗑 حذف محتوى", callback_data="delete_content"),
            InlineKeyboardButton("📊 الإحصائيات", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("📢 إذاعة للطلاب", callback_data="broadcast"),
        ],
        [
            InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def admin_panel(query):

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return

    await query.answer()

    await query.edit_message_text(
        """
⚙️ *لوحة تحكم البوت*

من هنا تستطيع إدارة البوت الدراسي:

➕ إضافة المواد والأقسام
📄 إضافة المحاضرات والملخصات
📕 رفع ملفات PDF
📎 رفع الملفات
🖼 الصور
🎥 الفيديوهات
🎧 الملفات الصوتية
🗑 حذف المحتوى
📢 إرسال إشعار للطلاب
📊 معرفة الإحصائيات
        """,
        reply_markup=admin_keyboard(),
        parse_mode="Markdown"
    )


# =========================================================
# بدء إضافة مادة
# =========================================================

async def ask_add_material(query, context):

    if query.from_user.id != ADMIN_ID:
        return

    context.user_data["admin_action"] = "add_material"

    await query.answer()

    await query.message.reply_text(
        "➕ أرسل الآن اسم المادة الدراسية:"
    )


# =========================================================
# إضافة قسم
# =========================================================

async def ask_add_menu(query, context):

    if query.from_user.id != ADMIN_ID:
        return

    context.user_data["admin_action"] = "add_menu"

    await query.answer()

    await query.message.reply_text(
        "📂 أرسل اسم القسم الذي تريد إضافته:"
    )


# =========================================================
# إضافة نص
# =========================================================

async def ask_add_text(query, context):

    if query.from_user.id != ADMIN_ID:
        return

    context.user_data["admin_action"] = "add_text_title"

    await query.answer()

    await query.message.reply_text(
        "📄 أرسل عنوان المحتوى النصي:"
    )


# =========================================================
# إضافة ملفات
# =========================================================

async def ask_file(query, context, file_type):

    if query.from_user.id != ADMIN_ID:
        return

    context.user_data["admin_action"] = f"add_{file_type}_title"

    await query.answer()

    await query.message.reply_text(
        f"📎 أرسل عنوان {file_type}:"
    )


# =========================================================
# معالجة الأدمن
# =========================================================

async def admin_text(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get("admin_action")

    if not action:
        return

    text = update.message.text.strip()

    # -----------------------------------------
    # إضافة مادة
    # -----------------------------------------

    if action == "add_material":

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO menus
            (parent_id, title)
            VALUES (0, ?)
        """, (text,))

        conn.commit()
        conn.close()

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ تمت إضافة المادة:\n\n📚 {text}"
        )

        return

    # -----------------------------------------
    # إضافة قسم
    # -----------------------------------------

    if action == "add_menu":

        context.user_data["new_menu_title"] = text
        context.user_data["admin_action"] = "choose_parent"

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, title
            FROM menus
            ORDER BY id
        """)

        rows = cur.fetchall()
        conn.close()

        keyboard = []

        for menu_id, title in rows:
            keyboard.append([
                InlineKeyboardButton(
                    title,
                    callback_data=f"parent:{menu_id}"
                )
            ])

        await update.message.reply_text(
            "📂 اختر القسم الأب:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # -----------------------------------------
    # عنوان النص
    # -----------------------------------------

    if action == "add_text_title":

        context.user_data["new_content_title"] = text
        context.user_data["admin_action"] = "add_text_content"

        await update.message.reply_text(
            "📝 أرسل الآن محتوى المحاضرة أو الملخص:"
        )

        return

    # -----------------------------------------
    # محتوى النص
    # -----------------------------------------

    if action == "add_text_content":

        title = context.user_data.get("new_content_title")
        menu_id = context.user_data.get("selected_menu", 0)

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO contents
            (menu_id, title, content_type, content)
            VALUES (?, ?, 'text', ?)
        """, (
            menu_id,
            title,
            text
        ))

        conn.commit()
        conn.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تمت إضافة المحتوى بنجاح."
        )

        return


# =========================================================
# استقبال الملفات
# =========================================================

async def receive_file(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get("admin_action")

    if not action:
        return

    file_type = None

    if action == "add_pdf_title":
        file_type = "pdf"

    elif action == "add_file_title":
        file_type = "document"

    elif action == "add_photo_title":
        file_type = "photo"

    elif action == "add_video_title":
        file_type = "video"

    elif action == "add_audio_title":
        file_type = "audio"

    elif action in [
        "add_pdf_file",
        "add_file_file",
        "add_photo_file",
        "add_video_file",
        "add_audio_file"
    ]:

        file_type = action.replace("add_", "").replace("_file", "")

    if not file_type:
        return

    if action.endswith("_title"):

        context.user_data["new_content_title"] = update.message.text

        context.user_data["admin_action"] = f"add_{file_type}_file"

        await update.message.reply_text(
            f"📎 أرسل الآن ملف {file_type}:"
        )

        return

    file_id = None

    if file_type == "pdf" or file_type == "document":

        if update.message.document:
            file_id = update.message.document.file_id

    elif file_type == "photo":

        if update.message.photo:
            file_id = update.message.photo[-1].file_id

    elif file_type == "video":

        if update.message.video:
            file_id = update.message.video.file_id

    elif file_type == "audio":

        if update.message.audio:
            file_id = update.message.audio.file_id

    if not file_id:
        await update.message.reply_text(
            "❌ نوع الملف غير صحيح."
        )
        return

    title = context.user_data.get(
        "new_content_title",
        "محتوى جديد"
    )

    menu_id = context.user_data.get(
        "selected_menu",
        0
    )

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO contents
        (menu_id, title, content_type, file_id)
        VALUES (?, ?, ?, ?)
    """, (
        menu_id,
        title,
        file_type,
        file_id
    ))

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        "✅ تمت إضافة الملف بنجاح."
    )


# =========================================================
# اختيار القسم الأب
# =========================================================

async def choose_parent(query, context):

    if query.from_user.id != ADMIN_ID:
        return

    parent_id = int(query.data.split(":")[1])

    title = context.user_data.get("new_menu_title")

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO menus
        (parent_id, title)
        VALUES (?, ?)
    """, (
        parent_id,
        title
    ))

    conn.commit()
    conn.close()

    context.user_data.clear()

    await query.answer("تمت الإضافة ✅")

    await query.message.reply_text(
        f"✅ تمت إضافة القسم:\n\n📂 {title}"
    )


# =========================================================
# الإحصائيات
# =========================================================

async def stats(query):

    if query.from_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM menus")
    menus = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM contents")
    contents = cur.fetchone()[0]

    conn.close()

    await query.answer()

    await query.edit_message_text(
        f"""
📊 *إحصائيات البوت*

👥 المستخدمون: `{users}`
📚 الأقسام: `{menus}`
📖 المحتويات: `{contents}`
        """,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 لوحة التحكم",
                    callback_data="admin"
                )
            ]
        ]),
        parse_mode="Markdown"
    )


# =========================================================
# الإذاعة
# =========================================================

async def ask_broadcast(query, context):

    if query.from_user.id != ADMIN_ID:
        return

    context.user_data["admin_action"] = "broadcast"

    await query.answer()

    await query.message.reply_text(
        "📢 أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:"
    )


async def broadcast(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("admin_action") != "broadcast":
        return

    message = update.message.text

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users")
    users = cur.fetchall()

    conn.close()

    sent = 0

    for (user_id,) in users:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            sent += 1

        except Exception as e:
            logging.error(e)

    context.user_data.clear()

    await update.message.reply_text(
        f"📢 تمت الإذاعة بنجاح.\n\n"
        f"👥 تم الإرسال إلى: {sent} مستخدم"
    )


# =========================================================
# البحث
# =========================================================

async def ask_search(query, context):

    context.user_data["search"] = True

    await query.answer()

    await query.message.reply_text(
        "🔍 أرسل اسم المحاضرة أو المادة التي تبحث عنها:"
    )


async def search_content(update, context):

    if not context.user_data.get("search"):
        return False

    text = update.message.text.strip()

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, content_type
        FROM contents
        WHERE title LIKE ?
        ORDER BY id DESC
        LIMIT 20
    """, (
        f"%{text}%",
    ))

    rows = cur.fetchall()

    conn.close()

    context.user_data.pop("search", None)

    if not rows:

        await update.message.reply_text(
            "❌ لم يتم العثور على نتائج."
        )

        return True

    keyboard = []

    for content_id, title, content_type in rows:

        keyboard.append([
            InlineKeyboardButton(
                f"📖 {title}",
                callback_data=f"content:{content_id}"
            )
        ])

    await update.message.reply_text(
        f"🔎 نتائج البحث عن: {text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return True


# =========================================================
# معالجة الأزرار
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    data = query.data

    if data == "home":
        await home(update, context)

    elif data == "materials":
        await query.answer()
        await show_materials(query)

    elif data.startswith("menu:"):
        menu_id = int(data.split(":")[1])
        await query.answer()
        await show_menu(query, menu_id)

    elif data.startswith("content:"):
        content_id = int(data.split(":")[1])
        await show_content(query, content_id)

    elif data == "admin":
        await admin_panel(query)

    elif data == "add_material":
        await ask_add_material(query, context)

    elif data == "add_menu":
        await ask_add_menu(query, context)

    elif data == "add_text":
        await ask_add_text(query, context)

    elif data == "add_pdf":
        await ask_file(query, context, "pdf")

    elif data == "add_file":
        await ask_file(query, context, "file")

    elif data == "add_photo":
        await ask_file(query, context, "photo")

    elif data == "add_video":
        await ask_file(query, context, "video")

    elif data == "add_audio":
        await ask_file(query, context, "audio")

    elif data == "stats":
        await stats(query)

    elif data == "broadcast":
        await ask_broadcast(query, context)

    elif data == "search":
        await ask_search(query, context)

    elif data.startswith("parent:"):
        await choose_parent(query, context)


# =========================================================
# معالج الرسائل
# =========================================================

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id == ADMIN_ID:

        if context.user_data.get("admin_action") == "broadcast":
            await broadcast(update, context)
            return

        if update.message.text:

            if await search_content(update, context):
                return

            await admin_text(update, context)
            return

        await receive_file(update, context)
        return

    if update.message.text:

        if await search_content(update, context):
            return


# =========================================================
# تشغيل البوت
# =========================================================

def main():

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
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

    print("🤖 البوت الدراسي يعمل الآن...")

    application.run_polling()


if __name__ == "__main__":
    main()
