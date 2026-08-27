import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_ID = 5734654153

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("المرحلة الأولى", callback_data='stage1')],
        [InlineKeyboardButton("المرحلة الثانية", callback_data='stage2')],
        [InlineKeyboardButton("المرحلة الثالثة", callback_data='stage3')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('أهلاً بك! يرجى اختيار المرحلة:', reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'stage1':
        keyboard = [
            [InlineKeyboardButton("أضف ملف", callback_data='upload_stage1')],
            [InlineKeyboardButton("المواد", callback_data='sub1')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="اختر من المرحلة الأولى:", reply_markup=reply_markup)

    elif query.data == 'stage2':
        keyboard = [
            [InlineKeyboardButton("أضف ملف", callback_data='upload_stage2')],
            [InlineKeyboardButton("المواد", callback_data='sub2')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="اختر من المرحلة الثانية:", reply_markup=reply_markup)

    elif query.data == 'stage3':
        keyboard = [
            [InlineKeyboardButton("أضف ملف", callback_data='upload_stage3')],
            [InlineKeyboardButton("المواد", callback_data='sub3')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="اختر من المرحلة الثالثة:", reply_markup=reply_markup)

    elif query.data.startswith('upload_'):
        if query.from_user.id == ADMIN_ID:
            await query.edit_message_text(text="رجاءً أرسل الملف الآن.")
            context.user_data['stage_upload'] = query.data
        else:
            await query.edit_message_text(text="عذراً، فقط المسؤول يمكنه رفع الملفات.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == ADMIN_ID and 'stage_upload' in context.user_data:
        file_id = update.message.document.file_id
        new_file = await context.bot.get_file(file_id)
        file_path = f"stage_files/{file_id}.{update.message.document.file_name.split('.')[-1]}"
        await new_file.download_to_drive(file_path)
        await update.message.reply_text(f"تم حفظ الملف في المرحلة {context.user_data['stage_upload']}.")
        del context.user_data['stage_upload']
    else:
        await update.message.reply_text("عذراً، ليس لديك صلاحية رفع الملفات.")

if __name__ == '__main__':
    application = ApplicationBuilder().token('8925599691:AAHIGxwCVTb5hYQ-bCWKVS7-u__xduob')
