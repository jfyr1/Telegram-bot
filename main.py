import os
import json
import logging
from flask import Flask, request
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

# الثوابت الخاصة بالبوت
TOKEN = "8925599691:AAHIGxwCVTb5hYQ-bCWKVS7-u__xduobniE"
ADMIN_ID = 5734654153

PORT = int(os.environ.get("PORT", 10000))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://YOUR_RENDER_APP_NAME.onrender.com")

# إنشاء مجلد حفظ الملفات
if not os.path.exists("stage_files"):
    os.makedirs("stage_files")

def load_data():
    if os.path.exists("bot_data.json"):
        with open("bot_data.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "stages": {
            "stage1": {"name": "المرحلة الأولى", "files": []},
            "stage2": {"name": "المرحلة الثانية", "files": []},
            "stage3": {"name": "المرحلة الثالثة", "files": []}
        }
    }

def save_data(data):
    with open("bot_data.json", 'w', encoding='utf-8') as f:
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
                await query.edit_message_text(text="تم حذف المرحلة بنجاح!")
                await start(update, context)

    elif query.data.startswith('get_file_'):
        parts = query.data.split('_')
        stage_key = parts[2]
        idx = int(parts[3])
        stage_info = data["stages"].get(stage_key)
        if stage_info and idx < len(stage_info["files"]):
            file_info = stage_info["files"][idx]
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_info['file_id'],
                caption=f"📄 {file_info['name']}"
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    state = context.user_data.get('state')
    if not state:
        return

    data = load_data()

    if state == 'waiting_for_stage_name':
        stage_name = update.message.text
        stage_key = f"stage_{len(data['stages']) + 1}_{int(os.urandom(2).hex(), 16)}"
        data["stages"][stage_key] = {"name": stage_name, "files": []}
        save_data(data)
        context.user_data['state'] = None
        await update.message.reply_text(f"تم إضافة المرحلة '{stage_name}' بنجاح!")
        await start(update, context)

    elif state.startswith('waiting_for_rename_'):
        stage_key = state.split('_')[3]
        new_name = update.message.text
        if stage_key in data["stages"]:
            data["stages"][stage_key]["name"] = new_name
            save_data(data)
        context.user_data['state'] = None
        await update.message.reply_text("تم تحديث اسم المرحلة بنجاح!")
        await start(update, context)

    elif state.startswith('waiting_for_file_'):
        stage_key = state.split('_')[3]
        if update.message.document:
            doc = update.message.document
            file_id = doc.file_id
            file_name = doc.file_name or "ملف بدون اسم"
            
            if stage_key in data["stages"]:
                data["stages"][stage_key]["files"].append({
                    "name": file_name,
                    "file_id": file_id
                })
                save_data(data)
            
            context.user_data['state'] = None
            await update.message.reply_text("تم رفع وتخزين الملف بنجاح!")
            await start(update, context)
        else:
            await update.message.reply_text("الرجاء إرسال ملف صالح (مستند/PDF):")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # التشغيل بالطريقة العادية (Polling)
    application.run_polling()

if __name__ == '__main__':
    main()
