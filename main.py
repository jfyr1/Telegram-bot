import os
import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------------------------------------------------------
# الإعدادات وتأمين البيانات
# ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5734654153  # أدخل ID الحساب الخاص بك كأدمن

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# محرك قاعدة البيانات الديناميكي
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT 0,
            title TEXT UNIQUE NOT NULL,
            content TEXT DEFAULT 'لا يوجد محتوى مضاف لهذه المادة بعد.'
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM buttons")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO buttons (id, parent_id, title) VALUES (1, 0, '[ الكورس الاول 🔻 ]')")
        cursor.execute("INSERT INTO buttons (id, parent_id, title) VALUES (2, 0, 'ملخصات الكورس الاول')")
        cursor.execute("INSERT INTO buttons (id, parent_id, title) VALUES (3, 0, 'الكورس الثاني 🔻')")
        cursor.execute("INSERT INTO buttons (id, parent_id, title) VALUES (4, 0, 'ملخصات الكورس الثاني')")
        cursor.execute("INSERT INTO buttons (id, parent_id, title, content) VALUES (5, 0, 'التواصل معنا 💬', 'للتواصل مع الإدارة يرجى مراسلة المعرف المباشر.')")
        
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'فكر اسلامي', 'محتوى وملازم مادة الفكر الإسلامي...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'الرسم الهندسي', 'محتوى وملازم مادة الرسم الهندسي...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'الورش الهندسية', 'محتوى وملازم مادة الورش الهندسية...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'أنظمة الرقمية', 'محتوى وملازم مادة الأنظمة الرقمية...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'رياضيات', 'محتوى وملازم مادة الرياضيات...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'انكليزي', 'محتوى وملازم مادة الإنكليزي...')")
        cursor.execute("INSERT INTO buttons (parent_id, title, content) VALUES (1, 'كهربائيه', 'محتوى وملازم مادة الكهربائية...')")
        conn.commit()
    conn.close()

init_db()

def register_user(user_id: int):
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_keyboard_by_parent(parent_id=0, is_editor=False):
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM buttons WHERE parent_id = ?", (parent_id,))
    rows = cursor.fetchall()
    conn.close()

    keyboard = []
    row = []
    for item in rows:
        row.append(KeyboardButton(item[0]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if parent_id != 0:
        keyboard.append([KeyboardButton("🔝 القائمة الرئيسية"), KeyboardButton("🔙 رجوع")])

    if is_editor:
        keyboard.append([KeyboardButton("➕ إضافة زر جديد"), KeyboardButton("📝 تعديل المحتوى")])
        keyboard.append([KeyboardButton("🛑 إيقاف المحرر")])
    elif parent_id == 0:
        keyboard.append([KeyboardButton("⚙️ محرر الأزرار"), KeyboardButton("👨‍✈️ Admin")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def add_new_button(title: str, parent_id=0):
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO buttons (parent_id, title) VALUES (?, ?)", (parent_id, title))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_editor_inline_board():
    text = (
        "⚙️ **محرر منصة الأزرار المباشر**\n\n"
        "◼️ حالة التنقل: 🟢 نشط\n"
        "◼️ إجراء التعديل: جاهز للاستقبال\n\n"
        "استخدم الأسهم والأدوات أدناه للتحكم في الهيكلية:"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️", callback_data="nav_left"),
            InlineKeyboardButton("⬆️", callback_data="nav_up"),
            InlineKeyboardButton("⬇️", callback_data="nav_down"),
            InlineKeyboardButton("➡️", callback_data="nav_right")
        ],
        [
            InlineKeyboardButton("➗ قسم فرعي", callback_data="op_sub"),
            InlineKeyboardButton("✖️ حذف زر", callback_data="op_del"),
            InlineKeyboardButton("👓 معاينة", callback_data="op_view")
        ]
    ])
    return text, keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    context.user_data["current_parent"] = 0
    
    welcome = (
        "ماذا يمكن لهذا البوت فعله؟ 🎓\n"
        "أهلاً بك في البوت الدراسي 📚\n\n"
        "نوفر لك المحاضرات والملخصات والأسئلة بأسلوب سلس ورائع.\n"
        "اختر القسم المطلوب من الأسفل:"
    )
    await update.message.reply_text(welcome, reply_markup=get_keyboard_by_parent(0))

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    register_user(user_id)
    
    current_parent = context.user_data.get("current_parent", 0)
    is_editor = context.user_data.get("is_editor", False)

    if context.user_data.get("awaiting_btn_name"):
        context.user_data["awaiting_btn_name"] = False
        if add_new_button(text.strip(), parent_id=current_parent):
            await update.message.reply_text(
                f"✅ تم إضافة الزر `{text}` بنجاح!",
                reply_markup=get_keyboard_by_parent(current_parent, is_editor=True),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ هذا الزر مضاف سابقاً!")
        return

    if text == "⚙️ محرر الأزرار":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذا الوضع مخصص لمدير البوت فقط.")
            return

        context.user_data["is_editor"] = True
        editor_text, editor_markup = get_editor_inline_board()
        await update.message.reply_text(editor_text, reply_markup=editor_markup, parse_mode="Markdown")
        await update.message.reply_text(
            "تم تفعيل محرر المنصة. تمكين وضع التعديل أسفل الشاشة:",
            reply_markup=get_keyboard_by_parent(current_parent, is_editor=True)
        )

    elif text == "🛑 إيقاف المحرر":
        context.user_data["is_editor"] = False
        await update.message.reply_text(
            "🛑 تم إيقاف وضع التعديل والعودة للوضع الافتراضي.",
            reply_markup=get_keyboard_by_parent(current_parent, is_editor=False)
        )

    elif text == "➕ إضافة زر جديد":
        context.user_data["awaiting_btn_name"] = True
        await update.message.reply_text("📝 **أرسل الآن الاسم المطلوب للزر الجديد:**", parse_mode="Markdown")

    elif text in ["🔝 القائمة الرئيسية", "🔙 رجوع"]:
        context.user_data["current_parent"] = 0
        await update.message.reply_text(
            "تم العودة للقائمة الرئيسية.",
            reply_markup=get_keyboard_by_parent(0, is_editor=is_editor)
        )

    elif text == "👨‍✈️ Admin":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذه اللوحة مخصصة للأدمن فقط.")
            return

        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        u_count = cursor.fetchone()[0]
        conn.close()

        admin_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👥 عدد المستخدمين: {u_count}", callback_data="stats")],
            [InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="broadcast")]
        ])
        await update.message.reply_text("🛠 **لوحة تحكم إدارة المنصة:**", reply_markup=admin_markup, parse_mode="Markdown")

    else:
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, content FROM buttons WHERE title = ?", (text,))
        btn_data = cursor.fetchone()

        if btn_data:
            btn_id, content = btn_data[0], btn_data[1]
            cursor.execute("SELECT COUNT(*) FROM buttons WHERE parent_id = ?", (btn_id,))
            has_children = cursor.fetchone()[0] > 0

            if has_children:
                context.user_data["current_parent"] = btn_id
                await update.message.reply_text(
                    f"📂 قسم: **{text}**",
                    reply_markup=get_keyboard_by_parent(btn_id, is_editor=is_editor),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"📌 **محتوى {text}:**\n\n{content}", parse_mode="Markdown")
        else:
            await update.message.reply_text("الرجاء اختيار أحد الأزرار المتاحة بالقائمة.")
        conn.close()

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing in environment variables!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    print("Bot engine is running automatically via Procfile...")
    app.run_polling()

if __name__ == "__main__":
    main()
