import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "ضع_التوكن_الجديد_هنا"
bot = telebot.TeleBot(TOKEN)
ADMIN_ID = 5734654153

def load_data():
    if os.path.exists("bot_data.json"):
        with open("bot_data.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"menu": {"root": {"name": "القائمة الرئيسية", "submenus": {}, "files": []}}}

def save_data(data):
    with open("bot_data.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # أزرار المستخدم العادي
    btn1 = KeyboardButton("📚 المراحل الدراسية")
    btn2 = KeyboardButton("ℹ️ حول البوت")
    markup.add(btn1, btn2)
    
    # أزرار تظهر فقط للمسؤول أسفل لوحة المفاتيح
    if is_admin(user_id):
        btn_admin1 = KeyboardButton("⚙️ إعدادات القوائم")
        btn_admin2 = KeyboardButton("➕ إضافة قسم أو ملف")
        markup.add(btn_admin1, btn_admin2)
        
    bot.send_message(message.chat.id, "أهلاً بك! استخدم الأزرار بالأسفل للتنقل:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    
    if text == "📚 المراحل الدراسية":
        bot.send_message(message.chat.id, "جاري عرض المراحل الدراسية...")
    elif text == "⚙️ إعدادات القوائم" and is_admin(user_id):
        bot.send_message(message.chat.id, "أنت الآن في لوحة تحكم المسؤول لتعديل القوائم.")
    elif text == "➕ إضافة قسم أو ملف" and is_admin(user_id):
        bot.send_message(message.chat.id, "أرسل تفاصيل القسم أو الملف الجديد للإضافة.")
    else:
        bot.send_message(message.chat.id, "اختر من الأزرار الموجودة في الأسفل.")

if __name__ == "__main__":
    print("البوت يعمل الآن...")
    bot.infinity_polling()
