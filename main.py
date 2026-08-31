import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------------------------------------------------------
# الإعدادات الأساسية
# ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5734654153  # معرف الأدمن الخاص بك

# جلب رابط التطبيق والمنفذ المخصص من متغيرات بيئة Render
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # مثال: https://your-app.onrender.com
PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# دالة مساعدة لحذف الرسائل القديمة
# ---------------------------------------------------------
async def delete_previous_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_msg_id = context.user_data.get("last_msg_id")
    chat_id = update.effective_chat.id
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_msg_id)
        except Exception:
            pass

# ---------------------------------------------------------
# لوحات المفاتيح (Keyboards)
# ---------------------------------------------------------
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("⚙️ محرر الأزرار"), KeyboardButton("📝 تعديل المشاركات (المحتوى)")],
        [KeyboardButton("👨‍✈️ Admin")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"), InlineKeyboardButton("📬 البريد المرسل", callback_data="admin_mail")],
        [InlineKeyboardButton("🧩 Extensions", callback_data="admin_ext"), InlineKeyboardButton("📢 الإعلانات", callback_data="admin_ads")],
        [InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="admin_settings"), InlineKeyboardButton("🎲 المتغيرات", callback_data="admin_vars")],
        [InlineKeyboardButton("👣 نظام الإجالة", callback_data="admin_referral"), InlineKeyboardButton("📖 ترقيم الصفحات", callback_data="admin_pagination")],
        [InlineKeyboardButton("📢 القنوات والمجموعات", callback_data="admin_channels"), InlineKeyboardButton("💭 رسالة البدء", callback_data="admin_start_msg")],
        [InlineKeyboardButton("👥 إعدادات المشرفين", callback_data="admin_admins"), InlineKeyboardButton("💸 الدفع التلقائي", callback_data="admin_payment")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="admin_shop"), InlineKeyboardButton("🤖 بوت السكرتير", callback_data="admin_secretary")],
        [InlineKeyboardButton("🛑 خروج من الإدارة", callback_data="admin_exit")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------------------------------------------------------
# الأوامر والمعالجات الأساسية
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await delete_previous_message(update, context)
    
    text = (
        "🛠 **أهلاً بك في بوت إدارة المحتوى**\n\n"
        "تم إعادة ضبط البوت إلى الوضع الافتراضي (0 أزرار فرعية).\n"
        "يرجى اختيار أحد الخيارات من القائمة أدناه للبدء بالتصميم:"
    )
    
    msg = await update.message.reply_text(
        text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    context.user_data["last_msg_id"] = msg.message_id

async def handle_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    try:
        await update.message.delete()
    except Exception:
        pass
        
    await delete_previous_message(update, context)

    if text == "⚙️ محرر الأزرار":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة زر جديد", callback_data="add_btn")],
            [InlineKeyboardButton("🛑 إيقاف المحرر (التعديل)", callback_data="stop_editor")]
        ])
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚙️ **أنت الآن في وضع تحرير الأزرار**\n\nقم باختيار العمليات المطلوبة لبناء القوائم:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        context.user_data["last_msg_id"] = sent_msg.message_id

    elif text == "📝 تعديل المشاركات (المحتوى)":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة رسالة", callback_data="add_msg"), InlineKeyboardButton("➕ إضافة سؤال", callback_data="add_q")],
            [InlineKeyboardButton("🛑 إيقاف المحرر", callback_data="stop_editor")]
        ])
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📝 **أنت الآن في وضع تحرير المحتوى والرسائل**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        context.user_data["last_msg_id"] = sent_msg.message_id

    elif text == "👨‍✈️ Admin":
        if user_id != ADMIN_ID:
            sent_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ عفواً، هذه اللوحة مخصصة للآدمن فقط."
            )
            context.user_data["last_msg_id"] = sent_msg.message_id
            return

        admin_text = (
            "🛠 **أنت في قائمة المسؤول الرئيسي.**\n\n"
            "📊 **حالة النظام:** نشط\n"
            "✉️ **الرسائل:** 49971/50000\n"
            "⚙️ اختر القسم الذي تريد إدارته من اللوحة أدناه:"
        )
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=admin_text,
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )
        context.user_data["last_msg_id"] = sent_msg.message_id

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_exit":
        await query.message.delete()
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔝 **تم العودة للقائمة الرئيسية**",
            reply_markup=get_main_keyboard()
        )
        context.user_data["last_msg_id"] = sent_msg.message_id

    elif data == "admin_admins":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data="add_sub_admin")],
            [InlineKeyboardButton("🔝 إلى الإدارة", callback_data="back_to_admin"), InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="admin_exit")]
        ])
        await query.edit_message_text(
            text="🔧 **أنت في وضع إعدادات المشرفين داخل البوت.**\n\n👥 **المشرفون الحاليون:**\n-- لا يوجد مشرفين فرعيين --",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    elif data == "back_to_admin":
        admin_text = (
            "🛠 **أنت في قائمة المسؤول الرئيسي.**\n\n"
            "📊 **حالة النظام:** نشط\n"
            "⚙️ اختر القسم الذي تريد إدارته من اللوحة أدناه:"
        )
        await query.edit_message_text(
            text=admin_text,
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )

    elif data == "stop_editor":
        await query.message.delete()
        sent_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🛑 **تم إيقاف وضع المحرر.**",
            reply_markup=get_main_keyboard()
        )
        context.user_data["last_msg_id"] = sent_msg.message_id

    elif data == "add_btn":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 إلغاء", callback_data="stop_editor")]
        ])
        await query.edit_message_text(
            text="➕ **أدخل اسماً للزر الجديد:**\n\nاضغط على (إلغاء) إذا غيرت رأيك.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

# ---------------------------------------------------------
# التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    if not BOT_TOKEN:
        raise ValueError("خطأ: لم يتم العثور على BOT_TOKEN!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu_text))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # إذا كان التطبيق مرفوعاً على Render يستخدم Webhook، وإلا يستخدم Polling محلياً
    if RENDER_EXTERNAL_URL:
        print("تشغيل البوت بنمط Webhook...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        )
    else:
        print("تشغيل البوت بنمط Polling (محلياً)...")
        app.run_polling()

if __name__ == "__main__":
    main()
