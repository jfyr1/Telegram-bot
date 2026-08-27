import os
import json
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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
        "buttons": ["الكورس الاول 🔻", "ملخصات الكورس الاول", "الكورس الثاني 🔻", "ملخصات الكورس الثاني", "💬 التواصل معنا"],
        "content": {}
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_admin(user_id):
    return user_id == ADMIN_ID

admin_states = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    data = load_data()
    
    # لوحة أزرار تفاعلية داخل الرسالة (Inline) مع أزواج الأسهم والتحكم كما في الصورة
    markup = InlineKeyboardMarkup(row_width=3)
    
    # أزرار التصفح والأسهم
    markup.add(
        InlineKeyboardButton("⬅️", callback_data="nav_left"),
        InlineKeyboardButton("⬆️", callback_data="nav_up"),
        InlineKeyboardButton("⬇️", callback_data="nav_down"),
        InlineKeyboardButton("➡️", callback_data="nav_right")
    )
    
    # أزرار الأقسام المسجلة
    for btn_text in data["buttons"]:
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"btn_{btn_text}"))
    
    # أزرار الإدارة للمشرف داخل الأزرار الشفافة
    if is_admin(user_id):
        markup.add(
            InlineKeyboardButton("🎛️ محرر الأزرار", callback_data="admin_editor"),
            InlineKeyboardButton("📝 تعديل المحتوى", callback_data="admin_content")
        )
        markup.add(
            InlineKeyboardButton("💰 الرصيد", callback_data="admin_balance"),
            InlineKeyboardButton("🔓 Admin", callback_data="admin_panel")
        )
        
    bot.send_message(message.chat.id, "مرحباً بك في لوحة التحكم والتنقل الذكية:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = load_data()
    query_data = call.data
    
    if query_data.startswith("btn_"):
        btn_name = query_data.replace("btn_", "")
        content = data["content"].get(btn_name, "لا توجد رسائل مضافة لهذا القسم حتى الآن.")
        bot.answer_callback_query(call.id, f"تم النقر على: {btn_name}")
        bot.send_message(call.message.chat.id, f"📁 **{btn_name}**:\n\n{content}")
        
    elif query_data == "admin_editor" and is_admin(user_id):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("➕ إضافة زر", callback_data="add_btn"),
            InlineKeyboardButton("🗑️ حذف زر", callback_data="del_btn")
        )
        bot.send_message(call.message.chat.id, "🎛️ **محرر الأزرار**: اختر العملية المطلوبة:", reply_markup=markup)
        
    elif query_data == "admin_content" and is_admin(user_id):
        buttons_list = "\n".join([f"- {b}" for b in data["buttons"]])
        admin_states[user_id] = "waiting_content_section"
        bot.send_message(call.message.chat.id, f"📝 **تعديل المشاركات**:\nأرسل في الرسالة القادمة اسم القسم أو الزر الذي تريد إضافة محتوى له:\n\n{buttons_list}")
        
    elif query_data == "add_btn" and is_admin(user_id):
        admin_states[user_id] = "waiting_add_button"
        bot.send_message(call.message.chat.id, "✏️ أرسل الآن اسم الزر الجديد:")
        
    elif query_data == "del_btn" and is_admin(user_id):
        admin_states[user_id] = "waiting_delete_button"
        bot.send_message(call.message.chat.id, "🗑️ أرسل اسم الزر المراد حذفه:")
        
    elif query_data in ["nav_left", "nav_up", "nav_down", "nav_right"]:
        bot.answer_callback_query(call.id, "تم استخدام أزرار التنقل السريع.")

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
            bot.send_message(message.chat.id, f"✅ تم إضافة الزر '{text}' بنجاح! أرسل /start لتحديث القائمة.")
            
        elif state == "waiting_delete_button":
            if text in data["buttons"]:
                data["buttons"].remove(text)
                save_data(data)
                del admin_states[user_id]
                bot.send_message(message.chat.id, f"🗑️ تم حذف الزر '{text}' بنجاح! أرسل /start لتحديث القائمة.")
            else:
                bot.send_message(message.chat.id, "❌ اسم الزر غير موجود، أعد المحاولة:")
                
        elif state == "waiting_content_section":
            admin_states[user_id] = {"state": "saving_content", "section": text}
            bot.send_message(message.chat.id, f"📝 أرسل الآن النص أو الملف للقسم: ({text})")
            
        elif isinstance(state, dict) and state.get("state") == "saving_content":
            section = state["section"]
            data["content"][section] = text
            save_data(data)
            del admin_states[user_id]
            bot.send_message(message.chat.id, f"✅ تم حفظ المحتوى بنجاح للقسم: {section}")

if __name__ == "__main__":
    print("البوت يعمل بنظام الأزرار الشفافة والتحكم...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
