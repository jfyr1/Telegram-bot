import os
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

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

    conn.commit()
    conn.close()

    defaults = {
        "maintenance": "0",
        "start_message": (
            "👋 أهلاً وسهلاً بك في البوت\n\n"
            "اختر من القائمة الرئيسية 👇"
        ),
        "maintenance_message": (
            "🛠 البوت حالياً في وضع الصيانة.\n"
            "يرجى المحاولة لاحقاً."
        ),
    }

    conn = db()
    cur = conn.cursor()

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)",
            (key, value)
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
        INSERT OR REPLACE INTO settings (key,value)
        VALUES (?,?)
    """, (key, value))

    conn.commit()
    conn.close()


# =========================================================
# SAVE USER
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


# =========================================================
# MAIN KEYBOARD
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

    if user_id == ADMIN_ID:
        buttons.append([
            KeyboardButton("⚙️ لوحة الأدمن")
        ])

    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        is_persistent=True
    )


# =========================================================
# ADMIN KEYBOARD
# =========================================================

def admin_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📊 إحصائيات البوت"),
                KeyboardButton("👥 عدد المشتركين")
            ],
            [
                KeyboardButton("📢 إرسال جماعي"),
                KeyboardButton("📣 الإعلانات")
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
# SETTINGS KEYBOARD
# =========================================================

def settings_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("✏️ تعديل رسالة البدء")
            ],
            [
                KeyboardButton("🛠 تعديل رسالة الصيانة")
            ],
            [
                KeyboardButton("🔙 رجوع")
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

    maintenance = get_setting("maintenance")

    if maintenance == "1" and user.id != ADMIN_ID:

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

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data.clear()

    await update.message.reply_text(
        "⚙️ لوحة تحكم البوت\n\n"
        "اختر القسم الذي تريد إدارته 👇",
        reply_markup=admin_keyboard()
    )


# =========================================================
# STATISTICS
# =========================================================

async def statistics(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        f"""
📊 إحصائيات البوت

👥 عدد المشتركين: {users}

🤖 حالة البوت:
{"🛠 صيانة" if get_setting("maintenance") == "1" else "🟢 يعمل"}

📅 قاعدة البيانات تعمل بشكل طبيعي.
""",
        reply_markup=admin_keyboard()
    )


# =========================================================
# SUBSCRIBERS
# =========================================================

async def subscribers(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        f"👥 عدد المشتركين في البوت:\n\n"
        f"🔢 {count} مستخدم",
        reply_markup=admin_keyboard()
    )


# =========================================================
# MAINTENANCE
# =========================================================

async def maintenance(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    current = get_setting("maintenance")

    if current == "1":
        set_setting("maintenance", "0")

        await update.message.reply_text(
            "🟢 تم إيقاف وضع الصيانة.\n"
            "البوت يعمل الآن.",
            reply_markup=admin_keyboard()
        )

    else:
        set_setting("maintenance", "1")

        await update.message.reply_text(
            "🛠 تم تفعيل وضع الصيانة.\n"
            "المستخدمون لن يستطيعوا استخدام البوت حتى يتم إيقافه.",
            reply_markup=admin_keyboard()
        )


# =========================================================
# START MESSAGE
# =========================================================

async def edit_start_message(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["state"] = "start_message"

    await update.message.reply_text(
        "✏️ أرسل رسالة البدء الجديدة:\n\n"
        "هذه الرسالة تظهر عند استخدام /start."
    )


# =========================================================
# MAINTENANCE MESSAGE
# =========================================================

async def edit_maintenance_message(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["state"] = "maintenance_message"

    await update.message.reply_text(
        "🔧 أرسل رسالة وضع الصيانة الجديدة:"
    )


# =========================================================
# SETTINGS
# =========================================================

async def bot_settings(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "⚙️ إعدادات البوت\n\n"
        "من هنا يمكنك تعديل الرسائل الأساسية.",
        reply_markup=settings_keyboard()
    )


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["state"] = "broadcast"

    await update.message.reply_text(
        "📢 أرسل الآن الرسالة التي تريد إرسالها لجميع المشتركين."
    )


async def broadcast(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    message = update.message.text

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    conn.close()

    sent = 0
    failed = 0

    for (user_id,) in users:

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
📢 تمت عملية الإرسال الجماعي.

✅ تم الإرسال: {sent}
❌ فشل الإرسال: {failed}
👥 الإجمالي: {len(users)}
""",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADMINS
# =========================================================

async def admins(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👮 إعداد المشرفين\n\n"
        "المشرف الرئيسي:\n"
        f"🆔 {ADMIN_ID}\n\n"
        "يمكن تطوير هذا القسم لإضافة وإزالة مشرفين متعددين.",
        reply_markup=admin_keyboard()
    )


# =========================================================
# CHANNELS / GROUPS
# =========================================================

async def channels(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "📢 قنوات ومجموعات\n\n"
        "يمكن تخصيص هذا القسم لإدارة القنوات والمجموعات "
        "المطلوبة في البوت.",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADS
# =========================================================

async def ads(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "📣 قسم الإعلانات\n\n"
        "يمكنك من هنا إدارة الإعلانات وإرسالها للمستخدمين.",
        reply_markup=admin_keyboard()
    )


# =========================================================
# HANDLE TEXT
# =========================================================

async def handle_text(update, context):

    text = update.message.text
    user_id = update.effective_user.id

    # -------------------------------
    # حالات الأدمن
    # -------------------------------

    if user_id == ADMIN_ID:

        state = context.user_data.get("state")

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

        if state == "broadcast":

            await broadcast(
                update,
                context
            )

            return

    # -------------------------------
    # الرئيسية
    # -------------------------------

    if text == "🏠 القائمة الرئيسية":

        context.user_data.clear()

        await update.message.reply_text(
            get_setting("start_message"),
            reply_markup=main_keyboard(user_id)
        )

        return

    # -------------------------------
    # لوحة الأدمن
    # -------------------------------

    if text == "⚙️ لوحة الأدمن":

        await admin_panel(
            update,
            context
        )

        return

    # -------------------------------
    # إحصائيات
    # -------------------------------

    if text == "📊 إحصائيات البوت":

        await statistics(
            update,
            context
        )

        return

    # -------------------------------
    # عدد المشتركين
    # -------------------------------

    if text == "👥 عدد المشتركين":

        await subscribers(
            update,
            context
        )

        return

    # -------------------------------
    # الإرسال الجماعي
    # -------------------------------

    if text == "📢 إرسال جماعي":

        await broadcast_start(
            update,
            context
        )

        return

    # -------------------------------
    # الإعلانات
    # -------------------------------

    if text == "📣 الإعلانات":

        await ads(
            update,
            context
        )

        return

    # -------------------------------
    # إعدادات البوت
    # -------------------------------

    if text == "⚙️ إعدادات البوت":

        await bot_settings(
            update,
            context
        )

        return

    # -------------------------------
    # وضع الصيانة
    # -------------------------------

    if text == "🛠 وضع الصيانة":

        await maintenance(
            update,
            context
        )

        return

    # -------------------------------
    # رسالة البدء
    # -------------------------------

    if text in [
        "✏️ رسالة البدء",
        "✏️ تعديل رسالة البدء"
    ]:

        await edit_start_message(
            update,
            context
        )

        return

    # -------------------------------
    # رسالة الصيانة
    # -------------------------------

    if text in [
        "🔧 رسالة الصيانة",
        "🛠 تعديل رسالة الصيانة"
    ]:

        await edit_maintenance_message(
            update,
            context
        )

        return

    # -------------------------------
    # المشرفين
    # -------------------------------

    if text == "👮 إعداد المشرفين":

        await admins(
            update,
            context
        )

        return

    # -------------------------------
    # القنوات والمجموعات
    # -------------------------------

    if text == "📢 قنوات ومجموعات":

        await channels(
            update,
            context
        )

        return

    # -------------------------------
    # رجوع
    # -------------------------------

    if text == "🔙 رجوع":

        await admin_panel(
            update,
            context
        )

        return

    # -------------------------------
    # تحديث
    # -------------------------------

    if text == "🔄 تحديث":

        await start(
            update,
            context
        )

        return

    # =====================================================
    # أقسام المستخدم
    # =====================================================

    if text == "📚 المواد الدراسية":

        await update.message.reply_text(
            "📚 المواد الدراسية\n\n"
            "لا توجد مواد مضافة حالياً.",
            reply_markup=main_keyboard(user_id)
        )

        return

    if text == "📖 المحاضرات":

        await update.message.reply_text(
            "📖 المحاضرات\n\n"
            "لا توجد محاضرات مضافة حالياً.",
            reply_markup=main_keyboard(user_id)
        )

        return

    if text == "📝 الملخصات":

        await update.message.reply_text(
            "📝 الملخصات\n\n"
            "لا توجد ملخصات مضافة حالياً.",
            reply_markup=main_keyboard(user_id)
        )

        return

    if text == "📂 الملفات":

        await update.message.reply_text(
            "📂 الملفات\n\n"
            "لا توجد ملفات مضافة حالياً.",
            reply_markup=main_keyboard(user_id)
        )

        return

    if text == "❓ الأسئلة":

        await update.message.reply_text(
            "❓ الأسئلة والمراجعات\n\n"
            "لا توجد أسئلة مضافة حالياً.",
            reply_markup=main_keyboard(user_id)
        )

        return

    if text == "🔍 البحث":

        await update.message.reply_text(
            "🔍 أرسل اسم المحاضرة أو الملخص الذي تريد البحث عنه.",
            reply_markup=main_keyboard(user_id)
        )

        return


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        print(
            "❌ لم يتم العثور على BOT_TOKEN."
        )

        return

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
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("🤖 البوت يعمل الآن...")

    app.run_polling()


if __name__ == "__main__":
    main()
