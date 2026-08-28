import logging
import sqlite3
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = "8925599691:AAGvo1qs6akZrIE-uVbcfhMfOVlju1Pzp1s"
ADMIN_ID = 5734654153

# إعداد قاعدة البيانات الشجرية المتكاملة
def init_db():
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS main_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            text TEXT NOT NULL,
            type TEXT DEFAULT 'menu',
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_parent_id'] = 0
    context.user_data.pop('admin_mode', None)
    context.user_data.pop('admin_state', None)
    context.user_data.pop('target_btn_id', None)
    await show_menu(update, context, parent_id=0)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0):
    user_id = update.effective_user.id
    context.user_data['current_parent_id'] = parent_id
  
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, text FROM main_buttons WHERE parent_id = ?", (parent_id,))
    buttons = cursor.fetchall()
    conn.close()

    keyboard = []
    row = []
    for btn_id, btn_text in buttons:
        row.append(KeyboardButton(btn_text))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    admin_mode = context.user_data.get('admin_mode', False)

    # إذا كان الآدمن في وضع المحرر، تظهر لوحة التحكم الخاصة بالتعديل والأزرار الاحترافية
    if user_id == ADMIN_ID and admin_mode:
        keyboard.append([KeyboardButton("⬆️"), KeyboardButton("⬇️"), KeyboardButton("⬅️"), KeyboardButton("➡️"), KeyboardButton("❌"), KeyboardButton("➗")])
        keyboard.append([KeyboardButton("➕ إضافة زر"), KeyboardButton("➕ إضافة رسالة")])
        keyboard.append([KeyboardButton("🔄 نقل"), KeyboardButton("📋 نسخ"), KeyboardButton("🔀 دمج")])
        keyboard.append([KeyboardButton("🔙 القائمة الرئيسية"), KeyboardButton("🛑 إيقاف المحرر (التعديل)")])
    else:
        nav_row = []
        if parent_id != 0:
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT parent_id FROM main_buttons WHERE id = ?", (parent_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                context.user_data['back_id'] = result[0]
            else:
                context.user_data['back_id'] = 0
            nav_row.append(KeyboardButton("🔙 رجوع"))
        
        nav_row.append(KeyboardButton("🔙 القائمة الرئيسية"))

        if user_id == ADMIN_ID:
            nav_row.append(KeyboardButton("🛠 محرر الأزرار"))
            nav_row.append(KeyboardButton("✏️ تعديل المشاركات (المحتوى)"))

        if nav_row:
            keyboard.append(nav_row)

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if parent_id == 0:
        current_title = "القائمة الرئيسية"
    else:
        conn = sqlite3.connect("tree_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM main_buttons WHERE id = ?", (parent_id,))
        res = cursor.fetchone()
        conn.close()
        current_title = res[0] if res else "القسم الحالي"

    if admin_mode:
        status_text = f"⚙️ أنت في وضع تحرير الأزرار.\n📍 القسم الحالي: *{current_title}*"
    else:
        status_text = f"📍 أنت الآن في: *{current_title}*"

    await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    admin_state = context.user_data.get('admin_state')
    admin_mode = context.user_data.get('admin_mode', False)

    if text == "🔙 القائمة الرئيسية":
        context.user_data.pop('admin_state', None)
        context.user_data.pop('target_btn_id', None)
        await show_menu(update, context, parent_id=0)
        return
    elif text == "🔙 رجوع":
        context.user_data.pop('admin_state', None)
        context.user_data.pop('target_btn_id', None)
        parent_id = context.user_data.get('back_id', 0)
        await show_menu(update, context, parent_id=parent_id)
        return

    # التحكم بتشغيل وإيقاف وضع المحرر
    if user_id == ADMIN_ID and text == "🛠 محرر الأزرار":
        context.user_data['admin_mode'] = True
        await update.message.reply_text("✏️ أنت في وضع تحرير الأزرار.", parse_mode="Markdown")
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    if user_id == ADMIN_ID and text == "🛑 إيقاف المحرر (التعديل)":
        context.user_data['admin_mode'] = False
        context.user_data.pop('admin_state', None)
        await update.message.reply_text("تم إيقاف المحرر بنجاح. ✅", parse_mode="Markdown")
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    # استقبال أوامر الإضافة والتحرير ضمن وضع المحرر
    if user_id == ADMIN_ID and admin_mode:
        if text == "➕ إضافة زر":
            context.user_data['admin_state'] = "waiting_add_btn_name"
            await update.message.reply_text("أرسل الآن اسم الزر الفرعي الجديد:")
            return
        elif text == "➕ إضافة رسالة":
            context.user_data['admin_state'] = "waiting_add_message_content"
            await update.message.reply_text("أرسل محتوى الرسالة النصية التي ستظهر عند الضغط هنا:")
            return

    if user_id == ADMIN_ID and admin_state:
        if admin_state == "waiting_add_btn_name":
            btn_name = text.strip()
            current_p = context.user_data.get('current_parent_id', 0)
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, 'menu', NULL)", (current_p, btn_name))
            conn.commit()
            conn.close()
            context.user_data.pop('admin_state', None)
            await update.message.reply_text(f"تمت إضافة الزر ({btn_name}) كقائمة بنجاح! ✅")
            await show_menu(update, context, parent_id=current_p)
            return

        elif admin_state == "waiting_add_message_content":
            msg_content = text.strip()
            current_p = context.user_data.get('current_parent_id', 0)
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, 'content', ?)", (current_p, "محتوى إضافي", 'content', msg_content))
            conn.commit()
            conn.close()
            context.user_data.pop('admin_state', None)
            await update.message.reply_text("تمت إضافة الرسالة/المحتوى بنجاح! ✅")
            await show_menu(update, context, parent_id=current_p)
            return

        elif admin_state == "waiting_edit_content":
            current_p = context.user_data.get('current_parent_id', 0)
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE main_buttons SET content = ? WHERE parent_id = ? AND type = 'content'", (text, current_p))
            conn.commit()
            conn.close()
            context.user_data.pop('admin_state', None)
            await update.message.reply_text("تم تحديث المشاركة/المحتوى بنجاح! ✅")
            await show_menu(update, context, parent_id=current_p)
            return

    if user_id == ADMIN_ID and text == "✏️ تعديل المشاركات (المحتوى)":
        context.user_data['admin_state'] = "waiting_edit_content"
        await update.message.reply_text("أرسل المحتوى أو التعديل الجديد ليتم حفظه في هذا القسم:")
        return

    # التفاعل الطبيعي للشجرة واختيار القوائم أو عرض المحتويات
    current_p = context.user_data.get('current_parent_id', 0)
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, content, text FROM main_buttons WHERE parent_id = ? AND text = ?", (current_p, text))
    btn = cursor.fetchone()
    conn.close()

    if btn:
        btn_id, b_type, b_content, b_text = btn
        if b_type == "menu":
            await show_menu(update, context, parent_id=btn_id)
        else:
            content_text = b_content if b_content else "لا يوجد محتوى مضاف بعد."
            await update.message.reply_text(f"📖 *{b_text}*\n\n{content_text}", parse_mode="Markdown")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("البوت يعمل بكفاءة تامة مع كافة خيارات التحرير والتنقل...")
    application.run_polling()

if __name__ == "__main__":
    main()
