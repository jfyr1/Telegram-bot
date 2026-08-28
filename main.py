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

# إعداد قاعدة البيانات الشجرية
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

async def delete_last_bot_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """حذف آخر رسالة إشعار أو محرر أرسلها البوت للحفاظ على نظافة وسلاسة المحادثة"""
    last_msg_id = context.user_data.get('last_notification_id')
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
        except Exception:
            pass
        context.user_data['last_notification_id'] = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_parent_id'] = 0
    context.user_data.pop('admin_state', None)
    context.user_data.pop('target_btn_id', None)
    context.user_data.pop('editor_mode', None)
    await delete_last_bot_message(context, update.effective_chat.id)
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
        if context.user_data.get('editor_mode'):
            nav_row.append(KeyboardButton("🛑 إيقاف المحرر (التعديل)"))
        else:
            nav_row.append(KeyboardButton("🛠 محرر الأزرار"))
        nav_row.append(KeyboardButton("Admin"))

    if nav_row:
        keyboard.append(nav_row)

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # جلب عنوان القسم الحالي
    if parent_id == 0:
        current_title = "القائمة الرئيسية"
    else:
        conn = sqlite3.connect("tree_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM main_buttons WHERE id = ?", (parent_id,))
        res = cursor.fetchone()
        conn.close()
        current_title = res[0] if res else "القسم الحالي"

    text_msg = f"📍 أنت الآن في: *{current_title}*\nاختر من القائمة أدناه:"
    
    # إرسال القائمة الجديدة
    msg = await update.message.reply_text(text_msg, reply_markup=reply_markup, parse_mode="Markdown")
    context.user_data['last_notification_id'] = msg.message_id

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    admin_state = context.user_data.get('admin_state')
    editor_mode = context.user_data.get('editor_mode', False)

    # محاولة حذف رسالة المستخدم أو تنظيف رسائل النظام السابقة لزيادة السلاسة
    await delete_last_bot_message(context, chat_id)

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

    # تشغيل وإيقاف محرر الأزرار السريع
    if text == "🛠 محرر الأزرار" and user_id == ADMIN_ID:
        context.user_data['editor_mode'] = True
        msg = await update.message.reply_text("✏️ *أنت في وضع تحرير الأزرار.*", parse_mode="Markdown")
        context.user_data['last_notification_id'] = msg.message_id
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    elif text == "🛑 إيقاف المحرر (التعديل)" and user_id == ADMIN_ID:
        context.user_data['editor_mode'] = False
        context.user_data.pop('admin_state', None)
        context.user_data.pop('target_btn_id', None)
        msg = await update.message.reply_text("🛑 تم إيقاف محرر الأزرار.", parse_mode="Markdown")
        context.user_data['last_notification_id'] = msg.message_id
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    # معالجة حالات الإدخال الخاصة بالآدمن أثناء التحرير
    if user_id == ADMIN_ID and admin_state:
        if admin_state == "waiting_add_text":
            btn_text = text.strip()
            context.user_data['new_btn_text'] = btn_text
            context.user_data['admin_state'] = "waiting_add_type"
            keyboard = [
                [KeyboardButton("📁 قسم فرعي (قائمة)"), KeyboardButton("📄 محتوى نصي")],
                [KeyboardButton("❌ إلغاء")]
            ]
            msg = await update.message.reply_text("اختر نوع هذا الزر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            context.user_data['last_notification_id'] = msg.message_id
            return

        elif admin_state == "waiting_add_type":
            current_p = context.user_data.get('current_parent_id', 0)
            btn_text = context.user_data.get('new_btn_text')
            
            if text == "📁 قسم فرعي (قائمة)":
                b_type = "menu"
                b_content = None
            elif text == "📄 محتوى نصي":
                b_type = "content"
                b_content = "محتوى فارغ."
            else:
                return

            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, ?, ?)", (current_p, btn_text, b_type, b_content))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('new_btn_text', None)
            msg = await update.message.reply_text(f"تمت إضافة الزر ({btn_text}) بنجاح! ✅")
            context.user_data['last_notification_id'] = msg.message_id
            await show_menu(update, context, parent_id=current_p)
            return

        elif admin_state == "waiting_edit_content":
            target_id = context.user_data.get('target_btn_id')
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE main_buttons SET content = ? WHERE id = ?", (text, target_id))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('target_btn_id', None)
            msg = await update.message.reply_text("تم تعديل المحتوى بنجاح! ✅")
            context.user_data['last_notification_id'] = msg.message_id
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

        elif admin_state == "waiting_edit_title":
            target_id = context.user_data.get('target_btn_id')
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE main_buttons SET text = ? WHERE id = ?", (text, target_id))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('target_btn_id', None)
            msg = await update.message.reply_text("تم تعديل الاسم بنجاح! ✅")
            context.user_data['last_notification_id'] = msg.message_id
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

        elif admin_state == "waiting_move_target":
            target_id = context.user_data.get('target_btn_id')
            new_parent_text = text.strip()
            
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            if new_parent_text == "الجذر الرئيسي (الرئيسية)":
                new_p_id = 0
            else:
                cursor.execute("SELECT id FROM main_buttons WHERE text = ? AND type = 'menu'", (new_parent_text,))
                res = cursor.fetchone()
                if not res:
                    conn.close()
                    return
                new_p_id = res[0]

            cursor.execute("UPDATE main_buttons SET parent_id = ? WHERE id = ?", (new_p_id, target_id))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('target_btn_id', None)
            msg = await update.message.reply_text("تم نقل الزر بنجاح! ✅")
            context.user_data['last_notification_id'] = msg.message_id
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

    # لوحة تحكم الآدمن العامة
    if text == "Admin" and user_id == ADMIN_ID:
        msg = await update.message.reply_text("⚙️ لوحة تحكم الآدمن العامة (إحصائيات أو إعدادات عامة).")
        context.user_data['last_notification_id'] = msg.message_id
        return

    # إذا كان محرر الأزرار مفعل وتم الضغط على زر موجود لإدارته
    if user_id == ADMIN_ID and editor_mode:
        current_p = context.user_data.get('current_parent_id', 0)
        conn = sqlite3.connect("tree_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, type FROM main_buttons WHERE parent_id = ? AND text = ?", (current_p, text))
        btn = cursor.fetchone()
        conn.close()

        if text == "➕ إضافة زر":
            context.user_data['admin_state'] = "waiting_add_text"
            keyboard = [[KeyboardButton("❌ إلغاء")]]
            msg = await update.message.reply_text("أرسل اسم الزر الجديد:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            context.user_data['last_notification_id'] = msg.message_id
            return

        if btn:
            btn_id, b_type = btn
            context.user_data['target_btn_id'] = btn_id
            
            # قائمة خيارات التحكم بالزر (أسهم، نقل، نسخ، تعديل، حذف) شبيهة بالصورة
            keyboard = [
                [KeyboardButton("⬅️"), KeyboardButton("➡️"), KeyboardButton("⬆️"), KeyboardButton("⬇️")],
                [KeyboardButton("✏️ تغيير الاسم"), KeyboardButton("🗑 حذف الزر")],
                [KeyboardButton("🚚 نقل إلى قسم آخر"), KeyboardButton("📋 نسخ الزر هنا")],
            ]
            if b_type == "content":
                keyboard.insert(0, [KeyboardButton("📝 تعديل المحتوى النصي")])
            
            keyboard.append([KeyboardButton("🛑 إيقاف المحرر (التعديل)"), KeyboardButton("🔙 القائمة الرئيسية")])
            msg = await update.message.reply_text(f"⚙️ خيارات تحكم الزر: *{text}*", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")
            context.user_data['last_notification_id'] = msg.message_id
            return

    # أوامر تحكم الزر المستهدف في وضع المحرر
    if user_id == ADMIN_ID and editor_mode and 'target_btn_id' in context.user_data:
        target_id = context.user_data['target_btn_id']

        if text == "🗑 حذف الزر":
            def delete_recursive(b_id):
                conn_sub = sqlite3.connect("tree_bot.db")
                cur_sub = conn_sub.cursor()
                cur_sub.execute("SELECT id FROM main_buttons WHERE parent_id = ?", (b_id,))
                children = cur_sub.fetchall()
                for child in children:
                    delete_recursive(child[0])
                cur_sub.execute("DELETE FROM main_buttons WHERE id = ?", (b_id,))
                conn_sub.commit()
                conn_sub.close()

            delete_recursive(target_id)
            context.user_data.pop('target_btn_id', None)
            msg = await update.message.reply_text("تم الحذف بنجاح! 🗑")
            context.user_data['last_notification_id'] = msg.message_id
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

        elif text == "📝 تعديل المحتوى النصي":
            context.user_data['admin_state'] = "waiting_edit_content"
            keyboard = [[KeyboardButton("❌ إلغاء")]]
            msg = await update.message.reply_text("أرسل المحتوى الجديد:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            context.user_data['last_notification_id'] = msg.message_id
            return

        elif text == "✏️ تغيير الاسم":
            context.user_data['admin_state'] = "waiting_edit_title"
            keyboard = [[KeyboardButton("❌ إلغاء")]]
            msg = await update.message.reply_text("أرسل الاسم الجديد:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            context.user_data['last_notification_id'] = msg.message_id
            return

        elif text == "🚚 نقل إلى قسم آخر":
            context.user_data['admin_state'] = "waiting_move_target"
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT text FROM main_buttons WHERE type = 'menu'")
            menus = cursor.fetchall()
            conn.close()

            keyboard = [[KeyboardButton("الجذر الرئيسي (الرئيسية)")]]
            for m in menus:
                keyboard.append([KeyboardButton(m[0])])
            keyboard.append([KeyboardButton("❌ إلغاء")])

            msg = await update.message.reply_text("اختر القسم الجديد للنقل:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            context.user_data['last_notification_id'] = msg.message_id
            return

        elif text == "📋 نسخ الزر هنا":
            current_p = context.user_data.get('current_parent_id', 0)
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT text, type, content FROM main_buttons WHERE id = ?", (target_id,))
            orig = cursor.fetchone()
            if orig:
                orig_text, orig_type, orig_content = orig
                cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, ?, ?)", 
                               (current_p, orig_text + " (نسخة)", orig_type, orig_content))
                conn.commit()
            conn.close()
            context.user_data.pop('target_btn_id', None)
            msg = await update.message.reply_text("تم النسخ بنجاح! 📋")
            context.user_data['last_notification_id'] = msg.message_id
            await show_menu(update, context, parent_id=current_p)
            return

    if text == "❌ إلغاء":
        context.user_data.pop('admin_state', None)
        context.user_data.pop('target_btn_id', None)
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    # التفاعل العادي للمستخدم أو عرض المحتوى إذا لم يكن في وضع التحرير
    current_p = context.user_data.get('current_parent_id', 0)
    
    # إذا كان محرر الأزرار مفعلاً، نظهر زر إضافة زر إضافي في القائمة
    if user_id == ADMIN_ID and editor_mode and text not in ["➕ إضافة زر"]:
        # السماح بفتح القائمة حتى لو كان محرر الأزرار مفعل لتصفح الأقسام
        pass

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
            msg = await update.message.reply_text(f"📖 *{b_text}*\n\n{content_text}", parse_mode="Markdown")
            context.user_data['last_notification_id'] = msg.message_id
    elif user_id == ADMIN_ID and editor_mode and text == "➕ إضافة زر":
        context.user_data['admin_state'] = "waiting_add_text"
        keyboard = [[KeyboardButton("❌ إلغاء")]]
        msg = await update.message.reply_text("أرسل اسم الزر الجديد:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        context.user_data['last_notification_id'] = msg.message_id

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("البوت يعمل الآن بسلاسة فائقة مع نظام حذف الإشعارات التلقائي ومحرر الأزرار...")
    application.run_polling()

if __name__ == "__main__":
    main()
