import os
import json
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ضع التوكن الخاص بك هنا
TOKEN = "892559691:AAHIGxwCVtB5hYQ-bCWKVS7-u__xduobniE"
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 5734654153

def load_data():
    if os.path.exists("bot_data.json"):
        with open("bot_data.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "menu": {
            "root": {
                "name": "القائمة الرئيسية",
                "submenus": {},
                "files": []
            }
        }
    }

def save_data(data):
    with open("bot_data.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def send_welcome(message):
    data = load_data()
    markup = InlineKeyboardMarkup()
    
    # بناء أزرار القائمة الرئيسية
    markup.add(InlineKeyboardButton("📚 عرض المراحل الدراسية", callback_data="show_root"))
    
    if is_admin(message.from_user.id):
        markup.add(InlineKeyboardButton("⚙️ لوحة تحكم المسؤول", callback_data="admin_panel"))
        
    bot.send_message(message.chat.id, "أهلاً بك في بوت المحاضرات والقوائم التعليمية.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    data = load_data()
    user_id = call.from_user.id
    
    if call.data == "show_root":
        markup = InlineKeyboardMarkup()
        root_menu = data["menu"]["root"]["submenus"]
        
        for key, value in root_menu.items():
            markup.add(InlineKeyboardButton(value["name"], callback_data=f"submenu_{key}"))
            
        if is_admin(user_id):
            markup.add(InlineKeyboardButton("➕ إضافة قسم رئيسي", callback_data="add_root"))
            
        bot.edit_message_text("اختر القسم أو المرحلة:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "هذا الزر مخصص للمسؤول فقط!", show_alert=True)
            return
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📁 إدارة الأقسام والقوائم", callback_data="manage_menus"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="show_root"))
        bot.edit_message_text("أهلاً بك في لوحة تحكم المسؤول. اختر العملية المطلوبة:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# تشغيل البوت
if __name__ == "__main__":
    print("البوت يعمل الآن...")
    bot.infinity_polling()
