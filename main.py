import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

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
        "buttons": [],
        "content": {}
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

# تتبع حالات المسؤول التنقلية
admin_states = {}

def get_dynamic_keyboard(user_id):
    data = load_data()
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # إضافة الأزرار والقوائم المسجلة
    for btn_text in data["buttons"]:
        markup.add(KeyboardButton(btn_text))
        
    # أزرار الإدارة للمشرف في الأسفل
    if is_admin(user_id):
        markup.add(KeyboardButton("🎛️ محرر الأزرار"), KeyboardButton("📝 تعديل المشاركات (المحتوى)"))
        markup.add(KeyboardButton("➕ إضافة زر"), KeyboardButton("🗑️ حذف زر"))
        markup.add(KeyboardButton("🔴 إيقاف المحرر (التعديل)"))
        
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    markup = get_dynamic_keyboard(user_id)
    bot.send_message(message.chat.id, "أهلاً بك. القائمة الرئيسية جاهزة:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text
    data = load_data()
    
    # التعامل مع حالات التعديل والإضافة للمشرف
    if is_admin(user_id) and user_id in admin_states:
        state = admin_states[user_id]
        
        if state == "waiting_add_button":
            data["buttons"].append(text)
            save_data(data)
            del admin_states[user_id]
            markup = get_dynamic_keyboard(user_id)
            bot.send_message(message.chat.id, f"✅ تم إضافة الزر '{text}' بنجاح وتحديث القائمة السفلية!", reply_markup=markup)
            return
            
        elif state == "waiting_delete_button":
            if text in data["buttons"]:
                data["buttons"].remove(text)
                if text in data["content"]:
                    del data["content"][text]
                save_data(data)
                del admin_states[user_id]
                markup = get_dynamic_keyboard(user_id)
                bot.send_message(message.chat.id, f"🗑️ تم حذف الزر '{text}' بنجاح وتحديث القائمة!", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ اسم الزر غير موجود، أرسل اسماً صحيحاً للحذف:")
            return
            
        elif state == "waiting_content_section":
            admin_states[user_id] = {"state": "saving_content", "section": text}
            bot.send_message(message.chat.id, f"📝 أرسل الآن المحتوى أو الرسالة للقسم: ({text})")
            return
            
        elif isinstance(state, dict) and state.get("state") == "saving_content":
            section = state["section"]
            data["content"][section] = text
            save_data(data)
            del admin_states[user_id]
            markup = get_dynamic_keyboard(user_id)
            bot.send_message(message.chat.id, f"✅ **تأكيد حفظ التعديل**: تم حفظ محتوى القسم ({section}) بنجاح!", reply_markup=markup)
            return

    # الأوامر الرئيسية للمشرف عبر الأزرار السفلية
    if text == "🎛️ محرر الأزرار" and is_admin(user_id):
        admin_states[user_id] = "editor_mode"
        bot.send_message(message.chat.id, "أنت الآن في وضع **تعديل الأزرار**. استخدم خيارات الإضافة أو الحذف بالأسفل.")
        return
        
    elif text == "📝 تعديل المشاركات (المحتوى)" and is_admin(user_id):
        if not data["buttons"]:
            bot.send_message(message.chat.id, "⚠️ لا توجد أزرار أو أقسام مضافة بعد لتعديل محتواها.")
            return
        admin_states[user_id] = "waiting_content_section"
        buttons_list = "\n".join([f"- {b}" for b in data["buttons"]])
        bot.send_message(message.chat.id, f"أنت في وضع **تعديل الرسائل**.\nأرسل اسم القسم من القائمة أدناه لتعديله:\n\n{buttons_list}")
        return
        
    elif text == "➕ إضافة زر" and is_admin(user_id):
        admin_states[user_id] = "waiting_add_button"
        bot.send_message(message.chat.id, "✏️ أرسل اسم الزر أو القسم الجديد الذي تريد إضافته للقائمة السفلية:")
        return
        
    elif text == "🗑️ حذف زر" and is_admin(user_id):
        if not data["buttons"]:
            bot.send_message(message.chat.id, "القائمة فارغة أساساً.")
            return
        admin_states[user_id] = "waiting_delete_button"
        bot.send_message(message.chat.id, "🗑️ أرسل اسم الزر الموجود حالياً في القائمة والذي تريد حذفه:")
        return
        
    elif text == "🔴 إيقاف المحرر (التعديل)" and is_admin(user_id):
        if user_id in admin_states:
            del admin_states[user_id]
        markup = get_dynamic_keyboard(user_id)
        bot.send_message(message.chat.id, "🔴 تم إيقاف وضع التحرير والعودة للقائمة الرئيسية.", reply_markup=markup)
        return

    # عرض محتوى الأقسام عند الضغط عليها من الأزرار السفلية
    if text in data["content"]:
        bot.send_message(message.chat.id, data["content"][text])
    elif text in data["buttons"]:
        bot.send_message(message.chat.id, f"📁 القسم: {text}\n(لا توجد رسائل مضافة لهذا القسم حتى الآن).")
    else:
        bot.send_message(message.chat.id, "اختر من الأزرار الظاهرة في الأسفل أو استخدم /start لإعادة تحميل القائمة.")

if __name__ == "__main__":
    print("البوت يعمل بنظام الأزرار السفلية التفاعلية...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
