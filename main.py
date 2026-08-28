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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_parent_id'] = 0
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
        nav_row.append(KeyboardButton("⚙️ لوحة تحكم الآدمن"))

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
    await update.message.reply_text(text_msg, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    admin_state = context.user_data.get('admin_state')

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

    # معالجة حالات الإدخال الخاصة بالآدمن (إضافة، تعديل، نقل، نسخ)
    if user_id == ADMIN_ID and admin_state:
        if admin_state == "waiting_add_text":
            btn_text = text.strip()
            context.user_data['new_btn_text'] = btn_text
            context.user_data['admin_state'] = "waiting_add_type"
            keyboard = [
                [KeyboardButton("📁 قسم فرعي (قائمة)"), KeyboardButton("📄 محتوى نصي")],
                [KeyboardButton("❌ إلغاء")]
            ]
            await update.message.reply_text("اختر نوع هذا الزر (قسم تفتح منه أقسام أخرى، أو محتوى نصي يظهر للمستخدم):", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return

        elif admin_state == "waiting_add_type":
            current_p = context.user_data.get('current_parent_id', 0)
            btn_text = context.user_data.get('new_btn_text')
            
            if text == "📁 قسم فرعي (قائمة)":
                b_type = "menu"
                b_content = None
            elif text == "📄 محتوى نصي":
                b_type = "content"
                b_content = "سيتم تحديث هذا المحتوى قريباً."
            else:
                await update.message.reply_text("الرجاء الاختيار من الأزرار الموجودة أدناه.")
                return

            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, ?, ?)", (current_p, btn_text, b_type, b_content))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('new_btn_text', None)
            await update.message.reply_text(f"تمت إضافة الزر ({btn_text}) بنجاح! ✅")
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
            await update.message.reply_text("تم تعديل محتوى الزر بنجاح! ✅")
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
            await update.message.reply_text("تم تغيير اسم الزر بنجاح! ✅")
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
                    await update.message.reply_text("القسم غير موجود أو ليس قائمة. أرسل اسم قسم صحيح أو اختر من الأزرار.")
                    return
                new_p_id = res[0]

            cursor.execute("UPDATE main_buttons SET parent_id = ? WHERE id = ?", (new_p_id, target_id))
            conn.commit()
            conn.close()

            context.user_data.pop('admin_state', None)
            context.user_data.pop('target_btn_id', None)
            await update.message.reply_text("تم نقل الزر بنجاح إلى القسم الجديد! ✅")
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

    # أزرار لوحة تحكم الآدمن الأساسية
    if text == "⚙️ لوحة تحكم الآدمن" and user_id == ADMIN_ID:
        keyboard = [
            [KeyboardButton("➕ إضافة زر هنا"), KeyboardButton("🛠 تعديل أو إدارة الأزرار الحالية")],
            [KeyboardButton("🔙 القائمة الرئيسية")]
        ]
        await update.message.reply_text("⚙️ لوحة تحكم الآدمن لإدارة القوائم الهرمية:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    elif text == "➕ إضافة زر هنا" and user_id == ADMIN_ID:
        context.user_data['admin_state'] = "waiting_add_text"
        keyboard = [[KeyboardButton("❌ إلغاء")]]
        await update.message.reply_text("أرسل الآن نص (اسم) الزر الجديد الذي تريد إضافته في هذا القسم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    elif text == "🛠 تعديل أو إدارة الأزرار الحالية" and user_id == ADMIN_ID:
        current_p = context.user_data.get('current_parent_id', 0)
        conn = sqlite3.connect("tree_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, text FROM main_buttons WHERE parent_id = ?", (current_p,))
        buttons = cursor.fetchall()
        conn.close()

        if not buttons:
            await update.message.reply_text("لا توجد أزرار في هذا القسم لتعديلها.")
            return

        keyboard = []
        for btn_id, btn_text in buttons:
            keyboard.append([KeyboardButton(f"إدارة: {btn_text}")])
        keyboard.append([KeyboardButton("⚙️ لوحة تحكم الآدمن"), KeyboardButton("🔙 القائمة الرئيسية")])
        
        await update.message.reply_text("اختر الزر الذي تريد إدارته (تعديل، حذف، نقل، نسخ):", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    # التحكم المباشر بزر معين تم اختياره للإدارة
    if user_id == ADMIN_ID and text.startswith("إدارة: "):
        btn_name = text.replace("إدارة: ", "").strip()
        current_p = context.user_data.get('current_parent_id', 0)
        
        conn = sqlite3.connect("tree_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, type FROM main_buttons WHERE parent_id = ? AND text = ?", (current_p, btn_name))
        btn = cursor.fetchone()
        conn.close()

        if btn:
            btn_id, b_type = btn
            context.user_data['target_btn_id'] = btn_id
            
            keyboard = [
                [KeyboardButton("✏️ تغيير الاسم"), KeyboardButton("🗑 حذف الزر")],
                [KeyboardButton("🚚 نقل إلى قسم آخر"), KeyboardButton("📋 نسخ الزر هنا")],
            ]
            if b_type == "content":
                keyboard.insert(0, [KeyboardButton("📝 تعديل المحتوى النصي")])
            
            keyboard.append([KeyboardButton("🛠 تعديل أو إدارة الأزرار الحالية"), KeyboardButton("🔙 القائمة الرئيسية")])
            await update.message.reply_text(f"خيارات التحكم بالزر: *{btn_name}*", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")
            return

    # تنفيذ عمليات التعديل للزر المستهدف
    if user_id == ADMIN_ID and 'target_btn_id' in context.user_data:
        target_id = context.user_data['target_btn_id']

        if text == "🗑 حذف الزر":
            # دالة لحذف الزر وكل فروع الشجرة التابعة له تلقائياً
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
            await update.message.reply_text("تم حذف الزر وكل محتوياته أو فروعه بنجاح! 🗑")
            current_p = context.user_data.get('current_parent_id', 0)
            await show_menu(update, context, parent_id=current_p)
            return

        elif text == "📝 تعديل المحتوى النصي":
            context.user_data['admin_state'] = "waiting_edit_content"
            keyboard = [[KeyboardButton("❌ إلغاء")]]
            await update.message.reply_text("أرسل المحتوى النصي الجديد الذي سيظهر للمستخدم عند الضغط على هذا الزر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return

        elif text == "✏️ تغيير الاسم":
            context.user_data['admin_state'] = "waiting_edit_title"
            keyboard = [[KeyboardButton("❌ إلغاء")]]
            await update.message.reply_text("أرسل الاسم الجديد لهذا الزر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
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

            await update.message.reply_text("اختر القسم الجديد الذي تريد نقل هذا الزر إليه:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return

        elif text == "📋 نسخ الزر هنا":
            current_p = context.user_data.get('current_parent_id', 0)
            
            # جلب بيانات الزر الأصلي لنسخه
            conn = sqlite3.connect("tree_bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT text, type, content FROM main_buttons WHERE id = ?", (target_id,))
            orig = cursor.fetchone()
            
            if orig:
                orig_text, orig_type, orig_content = orig
                # إضافة نسخة جديدة في القسم الحالي
                cursor.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, ?, ?)", 
                               (current_p, orig_text + " (نسخة)", orig_type, orig_content))
                new_copied_id = cursor.lastrowid
                conn.commit()

                # إذا كان الزر المنسوخ عبارة عن قائمة، يمكننا نسخ فروعها أيضاً (اختياري/متقدم)
                def copy_children(old_parent, new_parent):
                    cur2 = conn.cursor()
                    cur2.execute("SELECT text, type, content, id FROM main_buttons WHERE parent_id = ?", (old_parent,))
                    sub_items = cur2.fetchall()
                    for s_text, s_type, s_content, s_id in sub_items:
                        cur2.execute("INSERT INTO main_buttons (parent_id, text, type, content) VALUES (?, ?, ?, ?)",
                                     (new_parent, s_text, s_type, s_content))
                        new_sub_id = cur2.lastrowid
                        if s_type == 'menu':
                            copy_children(s_id, new_sub_id)
                    conn.commit()

                if orig_type == 'menu':
                    copy_children(target_id, new_copied_id)

            conn.close()
            context.user_data.pop('target_btn_id', None)
            await update.message.reply_text("تم نسخ الزر (مع فروعه إن وجدت) إلى هذا القسم بنجاح! 📋")
            await show_menu(update, context, parent_id=current_p)
            return

    if text == "❌ إلغاء":
        context.user_data.pop('admin_state', None)
        context.user_data.pop('target_btn_id', None)
        current_p = context.user_data.get('current_parent_id', 0)
        await show_menu(update, context, parent_id=current_p)
        return

    # التفاعل الطبيعي للمستخدم العادي (فتح القوائم أو عرض المحتوى)
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

    print("البوت يعمل الآن بنجاح مع كافة خيارات الإدارة والشجرة الهرمية عبر لوحة المفاتيح السفلية...")
    application.run_polling()

if __name__ == "__main__":
    main()
