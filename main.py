import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("المرحلة الأولى", callback_data='stage1')],
        [InlineKeyboardButton("المرحلة الثانية", callback_data='stage2')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('أهلاً بك! يرجى اختيار المرحلة:', reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'stage1':
        keyboard = [
            [InlineKeyboardButton("المادة 1", callback_data='sub1')],
            [InlineKeyboardButton("المادة 2", callback_data='sub2')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="اختر المادة للمرحلة الأولى:", reply_markup=reply_markup)
    elif query.data == 'stage2':
        await query.edit_message_text(text="المرحلة الثانية قيد التحديث.")

if name == '__main__':
    application = ApplicationBuilder().token('8925599691:AAHIGxwCVTb5hYQ-bCWKVS7-u__xduobniE')
').build()

    start_handler = CommandHandler('start', start)
    button_handler = CallbackQueryHandler(button)
    
    application.add_handler(start_handler)
    application.add_handler(button_handler)
    
    application.run_polling()
