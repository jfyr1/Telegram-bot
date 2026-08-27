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
    # تبدأ القوائم فارغة وجاهزة للإضافة كلياً
    return {
        "buttons": [],
        "content": {}
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

admin_states = {}

def get_main_menu(user_id):
    data = load_data()
    markup = InlineKeyboardMarkup(row_width=2)
    
    # أسهم التنقل السريع
    markup.add(
        InlineKeyboardButton("⬅️", callback_data="nav_left"),
        InlineKeyboardButton("⬆️", callback_data="nav_up"),
        InlineKeyboardButton("⬇️", callback_data="nav_down"),
        InlineKeyboardButton("➡️", callback_data="nav_right")
    )
    
    # أزرار القوائم المضافة ديناميكياً (تبدأ فارغة)
    for btn_text in data["buttons"]:
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"btn_{btn_text}"))
        
    # أزرار الإدارة للمشرف
    if is_admin(user_id):
        markup.add(
            InlineKeyboardButton("🎛️ محرر الأزرار", callback_data="admin_editor"),
            InlineKeyboardButton("📝 تعديل المحتوى", callback_data="admin_content")
        )
        markup.add(
            InlineKeyboardButton("💰 الرصيد", callback_data="admin_balance"),
            InlineKeyboardButton("🔓 Admin", callback_data="admin_panel")
        )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    markup = get_main_menu(user_id)
    bot.send_message(message.chat.id, "مرحباً بك. البوت جاهز لإضافة وتعديل الأقسام والقوائم:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = load_data()
    query_data = call.data
    
    if query_data.startswith("btn_"):
        btn_name = query_data.replace("btn_", "")
        content = data["content"].get(btn_name, "لا توجد رسائل مضافة لهذا القسم حتى الآن.")
        bot.answer_callback_query(call.id, f"تم فتح: {btn_name}")
        bot.send_message(call.message.chat.id, f"📁 **{btn_name}**:\n\n{content}")
        
    elif query_data == "admin_editor" and is_admin(user_id):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("➕ إضافة زر جديد", callback_data="add_btn"),
            InlineKeyboardButton("🗑️ حذف زر", callback_data="del_btn"),
            InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_home")
        )
        bot.edit_message_text("🎛️ **محرر الأزرار**: اختر العملية التي تريد تنفيذها:", 
                              call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif query_data == "admin_content" and is_admin(user_id):
        if not data["buttons"]:
            bot.answer_callback_query(call.id, "لا توجد أزرار مضافة بعد!", show_alert=True)
            return
        admin_states[user_id] = "waiting_content_section"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 إلغاء", callback_data="back_home"))
        buttons_list = "\n".join([f"- {b}" for b in data["buttons"]])
        bot.edit_message_text(f"📝 **تعديل المحتوى والمشاركات**:\nأرسل اسم القسم الذي تريد تخصيص محتواه:\n\n{buttons_list}", 
                              call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif query_data == "add_btn" and is_admin(user_id):
        admin_states[user_id] = "waiting_add_button"
        bot.answer_callback_query(call.id, "أرسل اسم الزر الجديد")
        bot.send_message(call.message.chat.id, "✏️ أرسل الآن اسم الزر أو القسم الجديد الذي تريد إضافته:")
        
    elif query_data == "del_btn" and is_admin(user_id):
        if not data["buttons"]:
            bot.answer_callback_query(call.id, "القائمة فارغة اساساً!", show_alert=True)
            return
        admin_states[user_id] = "waiting_delete_button"
        bot.answer_callback_query(call.id, "أرسل اسم الزر للحذف")
        bot.send_message(call.message.chat.id, "🗑️ أرسل اسم الزر الذي تريد حذفه:")

    elif query_data == "back_home":
        if user_id in admin_states:
            del admin_states[user_id]
        markup = get_main_menu(user_id)
        bot.edit_message_text("🏠 القائمة الرئيسية:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    elif query_data in ["nav_left", "nav_up", "nav_down", "nav_right"]:
        bot.answer_callback_query(call.id, "تم التنقل بنجاح.")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    text = message.text
    data = load_data()
    
    if is_admin(user_id) and user_id in admin_states:
        state = admin_states[user_id]
        
        if state == "waiting_add_button":
            data["buttons"].append(text)
            save_data(data)
            del admin_states[user_id]
            markup = get_main_menu(user_id)
            bot.send_message(message.chat.id, f"✅ **تأكيد التعديل**: تم إضافة القسم '{text}' بنجاح وتحديث القائمة!", reply_markup=markup)
            
        elif state == "waiting_delete_button":
            if text in data["buttons"]:
                data["buttons"].remove(text)
                if text in data["content"]:
                    del data["content"][text]
                save_data(data)
                del admin_states[user_id]
                markup = get_main_menu(user_id)
                bot.send_message(message.chat.id, f"🗑️ **تأكيد الحذف**: تم إزالة القسم '{text}' بنجاح!", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ اسم القسم غير موجود، أرسل اسماً صحيحاً:")
                
        elif state == "waiting_content_section":
            admin_states[user_id] = {"state": "saving_content", "section": text}
            bot.send_message(message.chat.id, f"📝 أرسل الآن المحتوى أو الرسالة للقسم: ({text})")
            
        elif isinstance(state, dict) and state.get("state") == "saving_content":
            section = state["section"]
            data["content"][section] = text
            save_data(data)
            del admin_states[user_id]
            markup = get_main_menu(user_id)
            bot.send_message(message.chat.id, f"✅ **تأكيد حفظ التعديل**: تم حفظ محتوى القسم ({section}) بنجاح!", reply_markup=markup)

if __name__ == "__main__":
    print("البوت يعمل بقوائم فارغة جاهزة للإدارة...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
