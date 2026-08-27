import os
import json
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8925599691:AAEnU91zp05TD_PnZFb_DTmLZ8Ub_u5qzPM"
bot = telebot.TeleBot(TOKEN)
ADMIN_ID = 5734654153

DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                pass
    return {
        "root": {
            "name": "القائمة الرئيسية",
            "submenus": {},
            "files": []
        }
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

# تتبع مسار وتصرفات المستخدم أو المشرف الحالي
admin_states = {}

def get_menu_markup(path, user_id):
    data = load_data()
    current = data["root"]
    
    # التنقل داخل الهيكل حسب المسار الحالي
    if path != "root":
        keys = path.split("/")
        for key in keys[1:]:
            if key in current["submenus"]:
                current = current["submenus"][key]
            else:
                break

    markup = InlineKeyboardMarkup(row_width=2)
    
    # أزرار الأقسام الفرعية التابعة للمستوى الحالي
    for sub_name in current["submenus"]:
        new_path = f"{path}/{sub_name}"
        markup.add(InlineKeyboardButton(f"📁 {sub_name}", callback_data=f"nav_{new_path}"))
        
    # عرض الملفات أو المحتوى المرتبط بهذا المستوى إن توفر
    if "files" in current and current["files"]:
        for idx, file_text in enumerate(current["files"]):
            markup.add(InlineKeyboardButton(f"📄 {file_text[:25]}...", callback_data=f"file_{path}_{idx}"))

    # زر الرجوع للخلف إذا لم نكن في الجذر
    if path != "root":
        parent_path = "/".join(path.split("/")[:-1])
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data=f"nav_{parent_path}"))
    else:
        markup.add(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="nav_root"))

    # أزرار تحكم المشرف تظهر في أي مستوى يدخله
    if is_admin(user_id):
        markup.add(
            InlineKeyboardButton("➕ إضافة قسم/زر", callback_data=f"add_sub_{path}"),
            InlineKeyboardButton("🗑️ حذف قسم", callback_data=f"del_sub_{path}")
        )
        markup.add(
            InlineKeyboardButton("📝 إضافة محتوى/رسالة", callback_data=f"add_content_{path}"),
            InlineKeyboardButton("🔴 إيقاف المحرر", callback_data="stop_admin")
        )
        
    return markup, current

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    markup, current = get_menu_markup("root", user_id)
    bot.send_message(message.chat.id, f"📍 أنت الآن في: **{current['name']}**\nاختر من الأقسام التالية:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = load_data()
    query = call.data
    
    if query.startswith("nav_"):
        path = query.replace("nav_", "")
        markup, current = get_menu_markup(path, user_id)
        bot.answer_callback_query(call.id, f"الانتقال إلى: {current['name']}")
        try:
            bot.edit_message_text(f"📍 أنت الآن في: **{current['name']}**", 
                                  call.message.chat.id, call.message.message_id, 
                                  reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(call.message.chat.id, f"📍 أنت الآن في: **{current['name']}**", reply_markup=markup, parse_mode="Markdown")

    elif query.startswith("add_sub_") and is_admin(user_id):
        path = query.replace("add_sub_", "")
        admin_states[user_id] = {"action": "add_sub", "path": path}
        bot.answer_callback_query(call.id, "أرسل اسم القسم الجديد")
        bot.send_message(call.message.chat.id, "✏️ أرسل الآن اسم القسم أو الزر الفرعي الجديد الذي تريد إضافته هنا:")

    elif query.startswith("del_sub_") and is_admin(user_id):
        path = query.replace("del_sub_", "")
        admin_states[user_id] = {"action": "del_sub", "path": path}
        bot.answer_callback_query(call.id, "أرسل اسم القسم للحذف")
        bot.send_message(call.message.chat.id, "🗑️ أرسل اسم القسم الفرعي الذي تريد حذفه من هذا المستودع:")

    elif query.startswith("add_content_") and is_admin(user_id):
        path = query.replace("add_content_", "")
        admin_states[user_id] = {"action": "add_content", "path": path}
        bot.answer_callback_query(call.id, "أرسل محتوى المشاركة")
        bot.send_message(call.message.chat.id, "📝 أرسل الآن النص أو الرسالة أو المحتوى لتتم إضافته لهذا القسم وتأكيد الحفظ:")

    elif query == "stop_admin":
        if user_id in admin_states:
            del admin_states[user_id]
        bot.answer_callback_query(call.id, "تم إيقاف وضع التحرير.")
        bot.send_message(call.message.chat.id, "🔴 **تم إيقاف محرر الصلاحيات بنجاح.**")

    elif query.startswith("file_"):
        parts = query.split("_")
        idx = int(parts[-1])
        path = "_".join(parts[1:-1])
        # استخراج المحتوى وعرضه
        current = data["root"]
        if path != "root":
            for key in path.split("/")[1:]:
                current = current["submenus"][key]
        file_content = current["files"][idx]
        bot.answer_callback_query(call.id, "عرض المحتوى")
        bot.send_message(call.message.chat.id, f"📄 **محتوى المشاركة:**\n\n{file_content}")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    data = load_data()
    
    if is_admin(user_id) and user_id in admin_states:
        state = admin_states[user_id]
        action = state["action"]
        path = state["path"]
        
        # الوصول للعقدة المستهدفة في شجرة البيانات
        current = data["root"]
        if path != "root":
            for key in path.split("/")[1:]:
                current = current["submenus"][key]
                
        if action == "add_sub":
            if text not in current["submenus"]:
                current["submenus"][text] = {"name": text, "submenus": {}, "files": []}
                save_data(data)
                del admin_states[user_id]
                markup, _ = get_menu_markup(path, user_id)
                bot.send_message(message.chat.id, f"✅ **تأكيد التعديل**: تم إضافة القسم '{text}' بنجاح وتحديث القوائم!", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ هذا القسم موجود مسبقاً، أرسل اسماً آخر:")
                
        elif action == "del_sub":
            if text in current["submenus"]:
                del current["submenus"][text]
                save_data(data)
                del admin_states[user_id]
                markup, _ = get_menu_markup(path, user_id)
                bot.send_message(message.chat.id, f"🗑️ **تأكيد الحذف**: تم إزالة القسم '{text}' بنجاح!", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ القسم غير موجود، تأكد من الاسم وأعد المحاولة:")
                
        elif action == "add_content":
            if "files" not in current:
                current["files"] = []
            current["files"].append(text)
            save_data(data)
            del admin_states[user_id]
            markup, _ = get_menu_markup(path, user_id)
            bot.send_message(message.chat.id, f"✅ **تأكيد حفظ التعديل**: تم إضافة ورسملة المحتوى للقسم بنجاح وتحديث واجهة العرض!", reply_markup=markup)

if __name__ == "__main__":
    print("البوت يعمل بنظام القوائم الهرمية التفاعلية وصلاحيات الإدارة الشاملة...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
