import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# تم وضع التوكن مباشرة هنا لتجنب مشاكل القراءة على السيرفر
TOKEN = "8925599691:AAEnU91zp05TD_PnZFb_DTmLZ8Ub_u5qzPM"
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
    
    # أزرار القائمة للمستخدمين
    btn1 = KeyboardButton("الكورس الاول 🔻")
    btn2 = KeyboardButton("ملخصات الكورس الاول")
    btn3 = KeyboardButton("الكورس الثاني 🔻")
    btn4 = KeyboardButton("ملخصات الكورس الثاني")
    btn5 = KeyboardButton("💬 التواصل معنا")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    
    # الأزرار الخاصة بالمسؤول
    if is_admin(user_id):
        btn_admin1 = KeyboardButton("🎛️ محرر الأزرار")
        btn_admin2 = KeyboardButton("📝 تعديل المشاركات (المحتوى)")
        btn_admin3 = KeyboardButton("💰 الرصيد")
        btn_admin4 = KeyboardButton("🔓 Admin")
        markup.add(btn_admin1, btn_admin2, btn_admin3, btn_admin4)
        
    bot.send_message(message.chat.id, "أهلاً بك في النظام التعليمي:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    
    if text == "🎛️ محرر الأزرار" and is_admin(user_id):
        bot.send_message(message.chat.id, "أنت الآن في وضع **محرر الأزرار**.")
    elif text == "📝 تعديل المشاركات (المحتوى)" and is_admin(user_id):
        bot.send_message(message.chat.id, "أنت الآن في وضع **تعديل المحتوى**.")
    elif text == "💰 الرصيد" and is_admin(user_id):
        bot.send_message(message.chat.id, "الرصيد الحالي للمسؤول.")
    elif text == "🔓 Admin" and is_admin(user_id):
        bot.send_message(message.chat.id, "لوحة صلاحيات المسؤول مفعلة.")
    else:
        bot.send_message(message.chat.id, "اختر من الأزرار الموجودة في الأسفل.")

if __name__ == "__main__":
    print("البوت يعمل الآن...")
    bot.infinity_polling()
