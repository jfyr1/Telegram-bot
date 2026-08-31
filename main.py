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
# قاعدة البيانات (دعم حفظ النصوص والمستندات)
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
            title TEXT NOT NULL,
            content TEXT DEFAULT 'لا يوجد محتوى مضاف بعد لهذه المادة.',
            file_id TEXT DEFAULT NULL,
            file_type TEXT DEFAULT NULL
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
# بناء الكيبورد الديناميكي
# ---------------------------------------------------------
def build_keyboard(parent_id=0, is_editor=False):
    conn = sqlite3.connect("bot_platform.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM buttons WHERE parent_id = ?", (parent_id,))
    db_buttons = cursor.fetchall()
    conn.close()

    keyboard = []
    row = []
    
    for btn in db_buttons:
        row.append(KeyboardButton(btn[0]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if is_editor:
        keyboard.append([KeyboardButton("➕ إضافة زر هنا"), KeyboardButton("📝 تعديل محتوى قسم")])
        keyboard.append([KeyboardButton("🗑 حذف زر من هنا")])
        if parent_id != 0:
            keyboard.append([KeyboardButton("🔙 رجوع للقسْم السابق"), KeyboardButton("🔝 القائمة الرئيسية")])
        keyboard.append([KeyboardButton("🛑 إيقاف وضع المحرر")])
        
    else:
        if parent_id != 0:
            keyboard.append([KeyboardButton("🔙 رجوع"), KeyboardButton("🔝 القائمة الرئيسية")])
        else:
            keyboard.append([KeyboardButton("⚙️ محرر الأزرار"), KeyboardButton("📝 تعديل المشاركات (المحتوى)")])
            keyboard.append([KeyboardButton("👨‍✈️ Admin")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------------------------------------------------------
# معالجة الأوامر والرسائل
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    
    context.user_data["current_parent"] = 0
    context.user_data["is_editor"] = False
    
    welcome_text = (
        "👋 **أهلاً بك في منصتك الخاصة!**\n\n"
        "استخدم الكيبورد أدناه للتنقل وإدارة الأزرار والمحتويات:"
    )
    await update.message.reply_text(welcome_text, reply_markup=build_keyboard(0), parse_mode="Markdown")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)

    current_parent = context.user_data.get("current_parent", 0)
    is_editor = context.user_data.get("is_editor", False)

    # 1. استقبال المحتوى (نص، صورة، ملزمة، أو فيديو) لحفظه تحت القسم المخصص
    if context.user_data.get("awaiting_content_update"):
        target_btn_id = context.user_data.get("target_btn_id")
        context.user_data["awaiting_content_update"] = False

        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()

        if update.message.text:
            cursor.execute("UPDATE buttons SET content = ?, file_id = NULL, file_type = NULL WHERE id = ?", 
                           (update.message.text, target_btn_id))
        elif update.message.document:
            cursor.execute("UPDATE buttons SET content = ?, file_id = ?, file_type = 'document' WHERE id = ?", 
                           (update.message.caption or "مرفق مستند/ملزمة", update.message.document.file_id, target_btn_id))
        elif update.message.photo:
            cursor.execute("UPDATE buttons SET content = ?, file_id = ?, file_type = 'photo' WHERE id = ?", 
                           (update.message.caption or "مرفق صورة", update.message.photo[-1].file_id, target_btn_id))
        elif update.message.video:
            cursor.execute("UPDATE buttons SET content = ?, file_id = ?, file_type = 'video' WHERE id = ?", 
                           (update.message.caption or "مرفق فيديو", update.message.video.file_id, target_btn_id))

        conn.commit()
        conn.close()

        await update.message.reply_text(
            "✅ **تم حفظ المحتوى وتثبيته تحت الزر المحدد بنجاح!**",
            reply_markup=build_keyboard(current_parent, is_editor=is_editor),
            parse_mode="Markdown"
        )
        return

    # 2. استقبال إضافة زر جديد
    text = update.message.text or ""

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

    # 3. إذاعة الأدمن
    if context.user_data.get("awaiting_broadcast"):
        if user_id != ADMIN_ID:
            return
        context.user_data["awaiting_broadcast"] = False
        users = get_all_users()
        
        await update.message.reply_text(f"⏳ **جاري الإرسال إلى {len(users)} مشترك...**", parse_mode="Markdown")
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

    # 4. أوامر التحكم بالكيبورد
    if text in ["⚙️ محرر الأزرار", "📝 تعديل المشاركات (المحتوى)"]:
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذا الوضع مخصص لمدير المنصة فقط.")
            return

        context.user_data["is_editor"] = True
        await update.message.reply_text(
            "⚙️ **تم تفعيل وضع التحرير المباشر!**\n\n"
            "انتقل للقسم المطلوب ثم اضغط (📝 تعديل محتوى قسم) لإضافة الدروس والملازم:",
            reply_markup=build_keyboard(current_parent, is_editor=True),
            parse_mode="Markdown"
        )

    elif text == "🛑 إيقاف وضع المحرر":
        context.user_data["is_editor"] = False
        await update.message.reply_text(
            "🛑 تم إيقاف التحرير والعودة للوضع الافتراضي.",
            reply_markup=build_keyboard(current_parent, is_editor=False)
        )

    elif text == "➕ إضافة زر هنا":
        context.user_data["awaiting_new_btn"] = True
        await update.message.reply_text("✍️ **أرسل اسم الزر الجديد الذي تريد إضافته هنا:**", parse_mode="Markdown")

    elif text == "🗑 حذف زر من هنا":
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM buttons WHERE parent_id = ?", (current_parent,))
        btns = cursor.fetchall()
        conn.close()

        if not btns:
            await update.message.reply_text("❌ لا توجد أزرار مضافة في هذا القسم لحذفها.")
            return

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
            "✏️ **اختر الزر الموكل بإرسال المحتوى إليه:**",
            reply_markup=InlineKeyboardMarkup(inline_edit),
            parse_mode="Markdown"
        )

    elif text == "👨‍✈️ Admin":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ هذه اللوحة مخصصة للأدمن فقط.")
            return

        cnt = get_users_count()
        admin_inline = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 إذاعة عامة للمستخدمين", callback_data="admin_broadcast_start")],
            [InlineKeyboardButton(f"📊 إجمالي المشتركين: {cnt}", callback_data="none")]
        ])
        await update.message.reply_text(
            "👨‍✈️ **أهلاً بك في لوحة تحكم الأدمن:**",
            reply_markup=admin_inline,
            parse_mode="Markdown"
        )

    elif text in ["🔝 القائمة الرئيسية", "🔙 رجوع للقسْم السابق", "🔙 رجوع"]:
        context.user_data["current_parent"] = 0
        await update.message.reply_text(
            "🔝 تم العودة للقائمة الرئيسية.",
            reply_markup=build_keyboard(0, is_editor=is_editor)
        )

    else:
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, file_id, file_type FROM buttons WHERE title = ? AND parent_id = ?", (text, current_parent))
        btn_data = cursor.fetchone()

        if btn_data:
            btn_id, content, file_id, file_type = btn_data[0], btn_data[1], btn_data[2], btn_data[3]
            cursor.execute("SELECT COUNT(*) FROM buttons WHERE parent_id = ?", (btn_id,))
            has_children = cursor.fetchone()[0] > 0

            if has_children:
                context.user_data["current_parent"] = btn_id
                await update.message.reply_text(
                    f"📂 قسم: **[{text}]**",
                    reply_markup=build_keyboard(btn_id, is_editor=is_editor),
                    parse_mode="Markdown"
                )
            else:
                # إرسال المحتوى بناءً على نوع المرفق المطور
                if file_id:
                    if file_type == 'document':
                        await update.message.reply_document(document=file_id, caption=content)
                    elif file_type == 'photo':
                        await update.message.reply_photo(photo=file_id, caption=content)
                    elif file_type == 'video':
                        await update.message.reply_video(video=file_id, caption=content)
                else:
                    await update.message.reply_text(f"📌 **[{text}]**\n\n{content}", parse_mode="Markdown")
        else:
            await update.message.reply_text("الرجاء اختيار خيار صحيح من الكيبورد.")
        conn.close()

# ---------------------------------------------------------
# معالجة تفاعلات الحذف والتعديل
# ---------------------------------------------------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    current_parent = context.user_data.get("current_parent", 0)
    is_editor = context.user_data.get("is_editor", False)

    if data.startswith("del_confirm_"):
        btn_id = int(data.split("_")[2])
        conn = sqlite3.connect("bot_platform.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM buttons WHERE id = ? OR parent_id = ?", (btn_id, btn_id))
        conn.commit()
        conn.close()

        await query.edit_message_text("✅ تم حذف الزر ومحتوياته بنجاح!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="تم التحديث:",
            reply_markup=build_keyboard(current_parent, is_editor=is_editor)
        )

    elif data.startswith("edit_content_"):
        btn_id = int(data.split("_")[2])
        context.user_data["target_btn_id"] = btn_id
        context.user_data["awaiting_content_update"] = True
        await query.edit_message_text("✍️ **أرسل الآن المحتوى المطلوب لهذا الزر (نص، ملازم PDF، صور، أو فيديو):**", parse_mode="Markdown")

    elif data == "admin_broadcast_start":
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text("📢 **أرسل الآن الرسالة التي ترغب بإذاعتها لجميع المشتركين:**", parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    print("Engine Updated & Ready...")
    app.run_polling()

if __name__ == "__main__":
    main()
