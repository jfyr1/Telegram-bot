import os
import json
import logging
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_ID = 5734654153
DATA_FILE = "bot_data.json"

# إنشاء مجلد حفظ الملفات
if not os.path.exists("stage_files"):
    os.makedirs("stage_files")

# دالة لتحميل البيانات من الملف
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "stages": {
            "stage1": {"name": "المرحلة الأولى", "files": []},
            "stage2": {"name": "المرحلة الثانية", "files": []},
            "stage3": {"name": "المرحلة الثالثة", "files": []}
        }
    }

# دالة لحفظ البيانات في الملف
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    keyboard = []
    
    for s_key, s_val in data["stages"].items():
        keyboard.append([InlineKeyboardButton(s_val["name"], callback_data=f'view_{s_key}')])
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("➕ إضافة مرحلة جديدة", callback_data='add_stage')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.message.edit_text('أهلاً بك! يرجى اختيار المرحلة:', reply_markup=reply_markup)
    else:
        await update.message.reply_text('أهلاً بك! يرجى اختيار المرحلة:', reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = load_data()

    if query.data.startswith('view_'):
        stage_key = query.data.split('_')[1]
        stage_info = data["stages"].get(stage_key)
        
        keyboard = []
        for idx, file_info in enumerate(stage_info.get("files", [])):
            keyboard.append([InlineKeyboardButton(f"📄 {file_info['name']}", callback_data=f"get_file_{stage_key}_{idx}")])
        
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("📤 أضف ملف لهذه المرحلة", callback_data=f'upload_{stage_key}')])
            keyboard.append([InlineKeyboardButton("✏️ إعادة تسمية المرحلة", callback_data=f'rename_{stage_key}')])
            keyboard.append([InlineKeyboardButton("🗑 حذف هذه المرحلة", callback_data=f'delete_{stage_key}')])
        
        keyboard.append([InlineKeyboardButton("⬅️ عودة للقائمة الرئيسية", callback_data='main_menu')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=f"محتويات {stage_info['name']}:", reply_markup=reply_markup)

    elif query.data == 'main_menu':
        await start(update, context)

    elif query.data == 'add_stage':
        if user_id == ADMIN_ID:
            context.user_data['state'] = 'waiting_for_stage_name'
            await query.edit_message_text(text="أرسل الآن اسم المرحلة الجديدة:")

    elif query.data.startswith('upload_'):
        if user_id == ADMIN_ID:
            stage_key = query.data.split('_')[1]
            context.user_data['state'] = f'waiting_for_file_{stage_key}'
            await query.edit_message_text(text="الرجاء إرسال الملف (مستند/PDF) الآن:")

    elif query.data.startswith('rename_'):
        if user_id == ADMIN_ID:
            stage_key = query.data.split('_')[1]
            context.user_data['state'] = f'waiting_for_rename_{stage_key}'
            await query.edit_message_text(text="أرسل الاسم الجديد للمرحلة:")

    elif query.data.startswith('delete_'):
        if user_id == ADMIN_ID:
            stage_key = query.data.split('_')[1]
            if stage_key in data["stages"]:
                del data["stages"][stage_key]
                save_data(data)
                await query.edit_message_text(text="تم حذف المرحلة بنجاح.")
                await start(update, context)

    elif query.data.startswith('get_file_'):
        parts = query.data.split('_')
        stage_key = parts[2]
        file_idx = int(parts[3])
        file_info = data["stages"][stage_key]["files"][file_idx]
        await context.bot.send_document(chat_id=user_id, document=file_info['file_id'], caption=file_info['name'])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        return

    state = context.user_data.get('state')
    data = load_data()

    if state == 'waiting_for_stage_name':
        stage_name = update.message.text
        stage_key = f"stage_{len(data['stages']) + 1}_{os.urandom(2).hex()}"
        data["stages"][stage_key] = {"name": stage_name, "files": []}
        save_data(data)
        del context.user_data['state']
        await update.message.reply_text(f"تم إضافة المرحلة '{stage_name}' بنجاح!")
        await start(update, context)

    elif state and state.startswith('waiting_for_rename_'):
        stage_key = state.split('_')[3]
        new_name = update.message.text
        if stage_key in data["stages"]:
            data["stages"][stage_key]["name"] = new_name
            save_data(data)
            del context.user_data['state']
            await update.message.reply_text(f"تم تغيير اسم المرحلة إلى '{new_name}' بنجاح.")
            await start(update, context)

    elif state and state.startswith('waiting_for_file_'):
        stage_key = state.split('_')[3]
        document = update.message.document
        if not document:
            await update.message.reply_text("الرجاء إرسال ملف صالح (Document).")
            return

        file_id = document.file_id
        file_name = update.message.caption if update.message.caption else document.file_name or "ملف بدون اسم"
        
        data["stages"][stage_key]["files"].append({
            "name": file_name,
            "file_id": file_id
        })
        save_data(data)
        del context.user_data['state']
        await update.message.reply_text(f"تم حفظ الملف باسم: {file_name} في المرحلة بنجاح.")

# إنشاء خادم ويب وهمي لكي يتوافق مع متطلبات المنصات مثل Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    from threading import Thread
    # تشغيل خادم الويب في خيط منفصل
    t = Thread(target=run_web)
    t.start()

    application = ApplicationBuilder().token('8925599691:AAHIGxwCVTb5hYQ-bCWKVS7-u__xduob...').build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    print("البوت يعمل الآن بكامل الميزات...")
    application.run_polling()
