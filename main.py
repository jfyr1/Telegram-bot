import logging
import sqlite3
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = "8925599691:AAGvo1qs6akZrIE-uVbcfhMfOVlju1Pzp1s"
ADMIN_ID = 5734654153

# إعداد قاعدة البيانات الشجرية
def init_db():
  conn = sqlite3.connect("tree_bot.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS main_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            text TEXT NOT NULL,
            type TEXT DEFAULT 'menu',
            content TEXT
        )
    """)
  conn.commit()
  conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data['current_parent_id'] = 0
  await show_menu(update, context, parent_id=0)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0):
  user_id = update.effective_user.id
  context.user_data['current_parent_id'] = parent_id
  
  conn = sqlite3.connect("tree_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, text FROM main_buttons WHERE parent_id = ?", (parent_id,))
  buttons = cursor.fetchall()
  conn.close()

  keyboard = []
  # ترتيب الأزرار في الأسفل (كل زرين في صف أو حسب الرغبة)
  row = []
  for btn_id, btn_text in buttons:
    row.append(KeyboardButton(btn_text))
    if len(row) == 2:
      keyboard.append(row)
      row = []
  if row:
    keyboard.append(row)

  # أزرار التنقل والتحكم بالأسفل
  nav_row = []
  if parent_id != 0:
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT parent_id FROM main_buttons WHERE id = ?", (parent_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
      context.user_data['back_id'] = result[0]
    else:
      context.user_data['back_id'] = 0
      
    nav_row.append(KeyboardButton("🔙 رجوع"))
  
  nav_row.append(KeyboardButton("🔙 القائمة الرئيسية"))

  if user_id == ADMIN_ID:
    nav_row.append(KeyboardButton("⚙️ لوحة تحكم الآدمن"))

  if nav_row:
    keyboard.append(nav_row)

  reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
  text_msg = "أهلاً بك في المنصة التعليمية 📚\nاختر من القائمة أدناه:"

  await update.message.reply_text(text_msg, reply_markup=reply_markup)

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text
  user_id = update.effective_user.id

  if text == "🔙 القائمة الرئيسية":
    await show_menu(update, context, parent_id=0)
    return
  elif text == "🔙 رجوع":
    parent_id = context.user_data.get('back_id', 0)
    await show_menu(update, context, parent_id=parent_id)
    return
  elif text == "⚙️ لوحة تحكم الآدمن" and user_id == ADMIN_ID:
    keyboard = [
        [KeyboardButton("➕ إضافة زر جديد")],
        [KeyboardButton("🔙 القائمة الرئيسية")],
    ]
    await update.message.reply_text("⚙️ لوحة تحكم الآدمن لإدارة القوائم:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return
  elif text == "➕ إضافة زر جديد" and user_id == ADMIN_ID:
    current_p = context.user_data.get('current_parent_id', 0)
    await update.message.reply_text(f"أرسل اسم الزر الجديد ليتم إضافته تحت القسم الحالي (رقم الأب: {current_p}):\nاكتب بالشكل: `إضافة زر: [نص الزر]`", parse_mode="Markdown")
    return

  # معالجة إضافة الزر إذا كان الآدمن يكتبه
  if user_id == ADMIN_ID and text.startswith("إضافة زر:"):
    try:
      btn_text = text.replace("إضافة زر:", "").strip()
      current_p = context.user_data.get('current_parent_id', 0)
      conn = sqlite3.connect("tree_bot.db")
      cursor = conn.cursor()
      cursor.execute("INSERT INTO main_buttons (parent_id, text, type) VALUES (?, ?, ?)", (current_p, btn_text, "menu"))
      conn.commit()
      conn.close()
      await update.message.reply_text(f"تمت إضافة الزر ({btn_text}) بنجاح! ✅")
      await show_menu(update, context, parent_id=current_p)
      return
    except Exception:
      await update.message.reply_text("خطأ في الصيغة. استخدم: `إضافة زر: [نص الزر]`", parse_mode="Markdown")
      return

  # البحث إذا كان النص المطابق هو أحد أزرار القائمة الحالية
  current_p = context.user_data.get('current_parent_id', 0)
  conn = sqlite3.connect("tree_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, type, content, text FROM main_buttons WHERE parent_id = ? AND text = ?", (current_p, text))
  btn = cursor.fetchone()
  conn.close()

  if btn:
    btn_id, b_type, b_content, b_text = btn
    if b_type == "menu":
      await show_menu(update, context, parent_id=btn_id)
    else:
      content_text = b_content if b_content else "لا يوجد محتوى مضاف بعد."
      await update.message.reply_text(f"📖 *{b_text}*\n\n{content_text}", parse_mode="Markdown")

def main():
  application = ApplicationBuilder().token(TOKEN).build()

  application.add_handler(CommandHandler("start", start))
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

  print("البوت يعمل الآن بلوحة المفاتيح السفلية (Reply Keyboard)...")
  application.run_polling()

if __name__ == "__main__":
  main()
