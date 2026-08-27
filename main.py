import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8925599691:AAEnU91zp05TD_PnZFb_DTmLZ8Ub_u5qzPM"
bot = telebot.TeleBot(TOKEN)
ADMIN_ID = 5734654153

DATA_FILE = "bot_data.json"

# هيكل البيانات الافتراضي
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                pass
    return {
        "buttons": ["الكورس الاول 🔻", "ملخصات الكورس الاول", "الكورس الثاني 🔻", "ملخصات الكورس الثاني", "💬 التواصل معنا"],
        "content": {}
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

# قاموس مؤقت لتتبع حالة المسؤول (إضافة، تعديل، حذف)
admin_states = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    data = load_data()
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # إضافة الأزرار المخزنة ديناميكياً
    for btn_text in data["buttons"]:
        markup.add(KeyboardButton(btn_text))
    
    # أزرار لوحة التحكم الخاصة بالمشرف
    if is_admin(user_id):
        markup.add(KeyboardButton("🎛️ محرر الأزرار"), KeyboardButton("📝 تعديل المشاركات (المحتوى)"))
        markup.add(KeyboardButton("💰 الرصيد"), KeyboardButton("🔓 Admin"))
        
    bot.send_message(message.chat.id, "أهلاً بك في نظام إدارة المحتوى التعليمي:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    data = load_data()
    
    # التحقق من حالات المشرف التفاعلية
    if is_admin(user_id) and user_id in admin_states:
        state = admin_states[user_id]
        
        if state == "waiting_add_button":
            data["buttons"].append(text)
            save_data(data)
            del admin_states[user_id]
            bot.send_message(message.chat.id, f"✅ تم إضافة الزر '{text}' بنجاح! اضغط /start لتحديث القائمة.")
            return
            
        elif state == "waiting_delete_button":
            if text in data["buttons"]:
                data["buttons"].remove(text)
                save_data(data)
                del admin_states[user_id]
                bot.send_message(message.chat.id, f"🗑️ تم حذف الزر '{text}' بنجاح! اضغط /start لتحديث القائمة.")
            else:
                bot.send_message(message.chat.id, "❌ اسم الزر غير موجود في القائمة. أرسل اسم الزر الصحيح للحذف:")
            return

        elif state == "waiting_content_section":
            admin_states[user_id] = {"state": "waiting_content_text", "section": text}
            bot.send_message(message.chat.id, f"📝 أرسل الآن الرسالة أو المحتوى الذي تريد إضافته للقسم: ({text})")
            return

        elif isinstance(state, dict) and state.get("state") == "waiting_content_text":
            section = state["section"]
            data["content"][section] = text
            save_data(data)
            del admin_states[user_id]
            bot.send_message(message.chat.id, f"✅ تم حفظ المحتوى بنجاح للقسم: {section}")
            return

    # الأوامر الرئيسية للمشرف
    if text == "🎛️ محرر الأزرار" and is_admin(user_id):
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(KeyboardButton("➕ إضافة زر جديد"), KeyboardButton("🗑️ حذف زر"), KeyboardButton("🔙 رجوع للقائمة الرئيسية"))
        bot.send_message(message.chat.id, "🎛️ **محرر الأزرار**: اختر العملية التي تريدها:", reply_markup=markup)
        return

    elif text == "📝 تعديل المشاركات (المحتوى)" and is_admin(user_id):
        admin_states[user_id] = "waiting_content_section"
        buttons_list = "\n".join([f"- {b}" for b in data["buttons"]])
        bot.send_message(message.chat.id, f"📝 **تعديل المحتوى**:\nالرجاء إرسال اسم القسم أو الزر الذي تريد إضافة رسالة أو محتوى له من القائمة أدناه:\n\n{buttons_list}")
        return

    elif text == "➕ إضافة زر جديد" and is_admin(user_id):
        admin_states[user_id] = "waiting_add_button"
        bot.send_message(message.chat.id, "✏️ أرسل الآن اسم الزر أو القسم الجديد الذي تريد إضافته:")
        return

    elif text == "🗑️ حذف زر" and is_admin(user_id):
        admin_states[user_id] = "waiting_delete_button"
        bot.send_message(message.chat.id, "🗑️ أرسل اسم الزر الموجود حالياً الذي تريد حذفه:")
        return

    elif text == "🔙 رجوع للقائمة الرئيسية":
        if user_id in admin_states:
            del admin_states[user_id]
        send_welcome(message)
        return

    elif text == "💰 الرصيد" and is_admin(user_id):
        bot.send_message(message.chat.id, "💰 الرصيد الحالي للمسؤول: 0 (مجاني).")
        return

    elif text == "🔓 Admin" and is_admin(user_id):
        bot.send_message(message.chat.id, "🔓 لوحة صلاحيات المسؤول مفعلة بالكامل.")
        return

    # عرض المحتوى المخزن إذا قام المستخدم بالضغط على زر القسم
    if text in data["content"]:
        bot.send_message(message.chat.id, data["content"][text])
    else:
        bot.send_message(message.chat.id, f"📁 أنت تتصفح: {text}\n(لا توجد رسائل مضافة لهذا القسم حتى الآن).")

if __name__ == "__main__":
    print("البوت يعمل الآن بنظام البيانات التفاعلي...")
    bot.infinity_polling()
