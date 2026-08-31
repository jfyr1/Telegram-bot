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
ADMIN_ID = 5734654153  # معرف الآدمن الخاص بك

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# قاعدة البيانات المتقدمة (مطابقة لنظام المنصات Cellx / MenuBuilder)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    
    # جدول مستخدمي البوت
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    
    # جدول الأزرار الشجري (دعم أزرار لا نهائية في أي عمق أو قسم)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER DEFAULT 0,
            title TEXT NOT NULL,
            content TEXT DEFAULT 'لا يوجد محتوى مضاف بعد.'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def register_user(user_id: int):
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_users_count():
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# ---------------------------------------------------------
# بناء لوحات الكيبورد الديناميكية (ReplyKeyboard)
# ---------------------------------------------------------
def build_keyboard(parent_id=0, is_editor=False):
    """بناء كيبورد متفاعل 100% بناءً على مكان المستخدم الحالي في الشجرة"""
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM buttons WHERE parent_id = ?", (parent_id,))
    db_buttons = cursor.fetchall()
    conn.close()

    keyboard = []
    row = []
    
    # صف أزرار المستخدم المصممة ديناميكياً
    for btn in db_buttons:
        row.append(KeyboardButton(btn[0]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # 1. خيارات الكيبورد في وضع المحرر
    if is_editor:
        keyboard.append([KeyboardButton("➕ إضافة زر هنا"), KeyboardButton("📝 تعديل محتوى قسم")])
        keyboard.append([KeyboardButton("🗑 حذف زر من هنا")])
        if parent_id != 0:
            keyboard.append([KeyboardButton("🔙 رجوع للقسْم السابق"), KeyboardButton("🔝 القائمة الرئيسية")])
        keyboard.append([KeyboardButton("🛑 إيقاف وضع المحرر")])
        
    # 2. خيارات الكيبورد في الوضع العادي
    else:
        if parent_id != 0:
            keyboard.append([KeyboardButton("🔙 رجوع"), KeyboardButton("🔝 القائمة الرئيسية")])
        else:
            # الواجهة الافتراضية الرئيسية الخالية من أي مواد تلقائية
            keyboard.append([KeyboardButton("⚙️ محرر الأزرار"), KeyboardButton("📝 تعديل المشاركات (المحتوى)")])
            keyboard.append([KeyboardButton("👨‍✈️ Admin")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------------------------------------------------------
# معالجات الأوامر والتفاعل
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    
    # إعادة ضبط حالة المكان للمستخدم
    context.user_data["current_parent"] = 0
    context.user_data["is_editor"] = False
    
    welcome_text = (
        "👋 **أهلاً بك في منصتك الخاصة!**\n\n"
        "الواجهة حالياً جاهزة وتنتظر إنشائك للأقسام والمواد من الصفر.\n"
        "استخدم الأزرار أدناه للتحكم والإدارة:"
    )
    await update.message.reply_text(welcome_text, reply_markup=build_keyboard(0), parse_mode="Markdown")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    register_user(user_id)

    current_parent = context.user_data.get("current_parent", 0)
    is_editor = context.user_data.get("is_editor", False)

    # ---------------------------------------------------------
    # 1. استقبال المدخلات النصية لوظائف المحرر والآدمن
    # ---------------------------------------------------------
    # أ: إضافة زر جديد
    if context.user_data.get("awaiting_new_btn"):
        context.user_data["awaiting_new_btn"] = False
        btn_title = text.strip()
        
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO buttons (parent_id, title) VALUES (?, ?)", (current_parent, btn_title))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ تم إضافة الزر الجديد: **[{btn_title}]** بنجاح!",
            reply_markup=build_keyboard(current_parent, is_editor=True),
            parse_mode="Markdown"
        )
        return

    # ب: تعديل محتوى الزر
    if context.user_data.get("awaiting_content_update"):
        target_btn_id = context.user_data.get("target_btn_id")
        context.user_data["awaiting_content_update"] = False
        
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE buttons SET content = ? WHERE id = ?", (text, target_btn_id))
        conn.commit()
        conn.close()

        await update.message.reply_text(
            "✅ تم حفظ وتحديث المحتوى بنجاح!",
            reply_markup=build_keyboard(current_parent, is_editor=is_editor),
            parse_mode="Markdown"
        )
        return

    # جـ: استقبال رسالة الإذاعة العامة للآدمن
    if context.user_data.get("awaiting_broadcast"):
        if user_id != ADMIN_ID:
            return
        context.user_data["awaiting_broadcast"] = False
        users = get_all_users()
        
        await update.message.reply_text(f"⏳ **جاري إرسال الإذاعة إلى {len(users)} مشترك...**", parse_mode="Markdown")
        success, failed = 0, 0
        for uid in users:
            try:
                await update.message.copy(chat_id=uid)
                success += 1
            except Exception:
                failed += 1

        await update.message.reply_text(
            f"📢 **اكتملت الإذاعة:**\n\n🟢 تم الإرسال: {success}\n🔴 فشل الإرسال: {failed}",
            reply_markup=build_keyboard(current_parent, is_editor=False),
            parse_mode="Markdown"
        )
        return

    # ---------------------------------------------------------
    # 2. أوامر المحرر وأزرار التحكم بالتحرير (الكيبورد)
    # ---------------------------------------------------------
    if text in ["⚙️ محرر الأزرار", "📝 تعديل المشاركات (المحتوى)"]:
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ عفواً، هذا الوضع مخصص لمدير المنصة فقط.")
            return

        context.user_data["is_editor"] = True
        await update.message.reply_text(
            "⚙️ **تم تفعيل وضع التحرير المباشر!**\n\n"
            "يمكنك الآن التجوّل في أي قسم، إضافة أزرار، أو تعديل المحتويات بسهولة باستخدام الكيبورد أدناه:",
            reply_markup=build_keyboard(current_parent, is_editor=True),
            parse_mode="Markdown"
        )

    elif text == "🛑 إيقاف وضع المحرر":
        context.user_data["is_editor"] = False
        await update.message.reply_text(
            "🛑 تم إيقاف التحرير والعودة لواجهة المستخدم العادية.",
            reply_markup=build_keyboard(current_parent, is_editor=False)
        )

    elif text == "➕ إضافة زر هنا":
        context.user_data["awaiting_new_btn"] = True
        await update.message.reply_text("✍️ **أرسل اسم الزر الجديد الذي تريد إضافته في هذا القسم:**", parse_mode="Markdown")

    elif text == "🗑 حذف زر من هنا":
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM buttons WHERE parent_id = ?", (current_parent,))
        btns = cursor.fetchall()
        conn.close()

        if not btns:
            await update.message.reply_text("❌ لا توجد أزرار مضافة في هذا القسم لحذفها.")
            return

        # زر التأكيد الشفاف الوحيد الذي يظهر لتأكيد العملية
        inline_confirm = []
        for b_id, b_title in btns:
            inline_confirm.append([InlineKeyboardButton(f"❌ حذف: {b_title}", callback_data=f"del_confirm_{b_id}")])
        
        await update.message.reply_text(
            "⚠️ **اختر الزر الذي تريد حذفه نهائياً:**",
            reply_markup=InlineKeyboardMarkup(inline_confirm),
            parse_mode="Markdown"
        )

    elif text == "📝 تعديل محتوى قسم":
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM buttons WHERE parent_id = ?", (current_parent,))
        btns = cursor.fetchall()
        conn.close()

        if not btns:
            await update.message.reply_text("❌ لا توجد أزرار مضافة هنا لتعديل محتواها.")
            return

        inline_edit = []
        for b_id, b_title in btns:
            inline_edit.append([InlineKeyboardButton(f"📝 تعديل محتوى: {b_title}", callback_data=f"edit_content_{b_id}")])

        await update.message.reply_text(
            "✏️ **اختر الزر الذي تريد إضافة أو تعديل المحتوى المرفق به:**",
            reply_markup=InlineKeyboardMarkup(inline_edit),
            parse_mode="Markdown"
        )

    # ---------------------------------------------------------
    # 3. قسم الأدمن والمستجيبات العامة
    # ---------------------------------------------------------
    elif text == "👨‍✈️ Admin":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذه اللوحة مخصصة للأدمن فقط.")
            return

        cnt = get_users_count()
        # خيارات التأكيد والإحصائيات الشفافة
        admin_inline = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 إذاعة عامة للمستخدمين", callback_data="admin_broadcast_start")],
            [InlineKeyboardButton(f"📊 إجمالي المشتركين: {cnt}", callback_data="none")]
        ])
        await update.message.reply_text(
            "👨‍✈️ **أهلاً بك في لوحة تحكم الأدمن المستقلة:**",
            reply_markup=admin_inline,
            parse_mode="Markdown"
        )

    elif text in ["🔝 القائمة الرئيسية", "🔙 رجوع للقسْم السابق", "🔙 رجوع"]:
        context.user_data["current_parent"] = 0
        await update.message.reply_text(
            "🔝 تم العودة للقائمة الرئيسية.",
            reply_markup=build_keyboard(0, is_editor=is_editor)
        )

    # ---------------------------------------------------------
    # 4. التنقل في الأزرار التفاعلية التي أنشأها المستخدم
    # ---------------------------------------------------------
    else:
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, content FROM buttons WHERE title = ? AND parent_id = ?", (text, current_parent))
        btn_data = cursor.fetchone()

        if btn_data:
            btn_id, content = btn_data[0], btn_data[1]
            cursor.execute("SELECT COUNT(*) FROM buttons WHERE parent_id = ?", (btn_id,))
            has_children = cursor.fetchone()[0] > 0

            if has_children or is_editor:
                # إذا كان زراً يحتوي أقساماً فرعية أو كنا في وضع التحرير فنعمل على فتح مجاله
                context.user_data["current_parent"] = btn_id
                await update.message.reply_text(
                    f"📂 أنت الآن داخل قسم: **[{text}]**\n\n{content}",
                    reply_markup=build_keyboard(btn_id, is_editor=is_editor),
                    parse_mode="Markdown"
                )
            else:
                # عرض المحتوى المخزن
                await update.message.reply_text(f"📌 **[{text}]**\n\n{content}", parse_mode="Markdown")
        else:
            await update.message.reply_text("الرجاء اختيار خيار صحيح من أزرار الكيبورد أدناه.")
        conn.close()

# ---------------------------------------------------------
# معالجة أزرار التأكيد الشفافة (Inline Callbacks)
# ---------------------------------------------------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    current_parent = context.user_data.get("current_parent", 0)
    is_editor = context.user_data.get("is_editor", False)

    # تأكيد عملية الحذف
    if data.startswith("del_confirm_"):
        btn_id = int(data.split("_")[2])
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM buttons WHERE id = ? OR parent_id = ?", (btn_id, btn_id))
        conn.commit()
        conn.close()

        await query.edit_message_text("✅ تم حذف الزر وجميع محتوياته بنجاح!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="تم تحديث الكيبورد:",
            reply_markup=build_keyboard(current_parent, is_editor=is_editor)
        )

    # تحديد زر لتعديل محتواه
    elif data.startswith("edit_content_"):
        btn_id = int(data.split("_")[2])
        context.user_data["target_btn_id"] = btn_id
        context.user_data["awaiting_content_update"] = True
        await query.edit_message_text("✍️ **أرسل المحتوى الجديد (نص، روابط، أو كليشة) المخصص لهذا الزر:**", parse_mode="Markdown")

    # بدء إذاعة الأدمن
    elif data == "admin_broadcast_start":
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text("📢 **أرسل الآن الرسالة التي ترغب بإذاعتها لجميع مستخدمي البوت:**", parse_mode="Markdown")

# ---------------------------------------------------------
# التشغيل الرئيسي عبر Procfile
# ---------------------------------------------------------
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    print("Platform Engine Started...")
    app.run_polling()

if __name__ == "__main__":
    main()
