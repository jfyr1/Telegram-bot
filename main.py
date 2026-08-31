import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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
ADMIN_ID = 5734654153  # معرف الآدمن الخاص بك

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# قاعدة البيانات (SQLite) لتخزين الأزرار والمستخدمين
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # جدول المشتركين
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    # جدول الأزرار المضافة ديناميكياً
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custom_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            button_name TEXT UNIQUE,
            content_text TEXT DEFAULT 'لا يوجد محتوى مضاف بعد.'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def register_user(user_id: int):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_custom_buttons():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT button_name FROM custom_buttons")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_custom_button(name: str):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO custom_buttons (button_name) VALUES (?)", (name,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_button_content(name: str):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT content_text FROM custom_buttons WHERE button_name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "لا يوجد محتوى متاح."

def get_users_count():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ---------------------------------------------------------
# بناء لوحات التحكم المنيو والـ Inline (مطابق للصورة)
# ---------------------------------------------------------
def get_main_keyboard(is_editor_active=False):
    """لوحة المفاتيح الرئيسية أسفل الشاشة"""
    buttons = []
    
    # الأزرار الديناميكية
    custom_btns = get_custom_buttons()
    for btn_name in custom_btns:
        buttons.append([KeyboardButton(btn_name)])

    # الأزرار الأساسية الافتراضية إذا لم تكن مضافة ديناميكياً
    if "[ الكورس الاول 🔻 ]" not in custom_btns:
        buttons.append([KeyboardButton("[ الكورس الاول 🔻 ]")])
    if "ملخصات الكورس الاول" not in custom_btns:
        buttons.append([KeyboardButton("ملخصات الكورس الاول")])
    if "الكورس الثاني 🔻" not in custom_btns:
        buttons.append([KeyboardButton("الكورس الثاني 🔻")])
    if "ملخصات الكورس الثاني" not in custom_btns:
        buttons.append([KeyboardButton("ملخصات الكورس الثاني")])
    if "التواصل معنا 💬" not in custom_btns:
        buttons.append([KeyboardButton("التواصل معنا 💬")])

    # تحكم المحرر
    if is_editor_active:
        buttons.append([KeyboardButton("➕ إضافة زر")])
        buttons.append([KeyboardButton("📝 تعديل المشاركات (المحتوى)"), KeyboardButton("🛑 إيقاف المحرر (التعديل)")])
    else:
        buttons.append([KeyboardButton("⚙️ محرر الأزرار"), KeyboardButton("👨‍✈️ Admin")])

    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_editor_status_inline():
    """اللوحة الشفافة العلوية المطابقة للصورة تماماً"""
    text = (
        "📊 **المساعد الذكي**\n"
        "◼️ شرط: ---\n"
        "◼️ محرر: ---\n"
        "◼️ التنقل: ⏹️ إيقاف\n"
        "◼️ مكافأة: ---\n"
        "◼️ إصلاح الصرف: ---\n"
        "◼️ تبادل الدورات: ---\n"
        "◼️ إجراءات: ---\n"
        "◼️ فاتورة: ---\n"
        "◼️ سحب: ---\n"
        "◼️ العنوان: ---\n"
        "◼️ المتجر: ---"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️", callback_data="nav_left"),
            InlineKeyboardButton("⬆️", callback_data="nav_up"),
            InlineKeyboardButton("⬇️", callback_data="nav_down"),
            InlineKeyboardButton("➡️", callback_data="nav_right"),
            InlineKeyboardButton("➗", callback_data="op_div"),
            InlineKeyboardButton("✖️", callback_data="op_mul"),
            InlineKeyboardButton("👓", callback_data="op_view")
        ],
        [
            InlineKeyboardButton("➰", callback_data="op_loop"),
            InlineKeyboardButton("❇️", callback_data="op_star")
        ]
    ])
    return text, keyboard

# ---------------------------------------------------------
# معالجات الأوامر والتفاعلات
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    
    # إرسال كليشة محرر المنصة الشفافة أولاً
    status_text, status_markup = get_editor_status_inline()
    await update.message.reply_text(status_text, reply_markup=status_markup, parse_mode="Markdown")
    
    # إرسال القائمة الرئيسية أسفل الرسائل
    await update.message.reply_text(
        "مرحباً بك في منصة البوت الذكي. اختر من الأزرار التالية:",
        reply_markup=get_main_keyboard(is_editor_active=False)
    )

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    register_user(user_id)

    # حالة إضافة زر جديد
    if context.user_data.get("awaiting_button_name"):
        context.user_data["awaiting_button_name"] = False
        btn_name = text.strip()
        if add_custom_button(btn_name):
            await update.message.reply_text(
                f"✅ تم إضافة الزر `{btn_name}` بنجاح!",
                reply_markup=get_main_keyboard(is_editor_active=True),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ هذا الزر موجود بالفعل!")
        return

    # الأزرار الأساسية وإدارة المحرر
    if text == "⚙️ محرر الأزرار":
        context.user_data["editor_active"] = True
        status_text, status_markup = get_editor_status_inline()
        await update.message.reply_text("⚙️ **أنت الآن في وضع تحرير الأزرار والقوائم:**", parse_mode="Markdown")
        await update.message.reply_text(status_text, reply_markup=status_markup, parse_mode="Markdown")
        await update.message.reply_text(
            "تم تفعيل المحرر. اختر العمليات المطلوب تنفيذها:",
            reply_markup=get_main_keyboard(is_editor_active=True)
        )

    elif text == "🛑 إيقاف المحرر (التعديل)":
        context.user_data["editor_active"] = False
        await update.message.reply_text(
            "🛑 تم إيقاف وضع المحرر والعودة إلى القائمة الرئيسية.",
            reply_markup=get_main_keyboard(is_editor_active=False)
        )

    elif text == "➕ إضافة زر":
        context.user_data["awaiting_button_name"] = True
        await update.message.reply_text("📝 **أرسل الآن اسم الزر الجديد الذي تريد إضافته:**", parse_mode="Markdown")

    elif text == "👨‍✈️ Admin":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذه اللوحة مخصصة للآدمن فقط.")
            return

        users_cnt = get_users_count()
        admin_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"👥 المشتركين: {users_cnt}", callback_data="stats")],
            [InlineKeyboardButton("📢 إذاعة عامة", callback_data="broadcast")]
        ])
        await update.message.reply_text("👨‍✈️ **أهلاً بك في لوحة تحكم الأدمن الرئيسي:**", reply_markup=admin_markup, parse_mode="Markdown")

    else:
        # إذا كان الزر المكسور أو المنقر محدد في قاعدة البيانات
        content = get_button_content(text)
        await update.message.reply_text(f"📌 **محتوى قسم ({text}):**\n\n{content}", parse_mode="Markdown")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith(("nav_", "op_")):
        await query.answer("⚙️ جاري التعديل والتنقل في الهيكلية...", show_alert=False)

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing in environment variables!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    print("Platform Bot Running (Polling Mode)...")
    app.run_polling()

if __name__ == "__main__":
    main()
