import logging
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = "8925599691:AAEnU91zp05TD_PnZFb_DTmLZ8Ub_u5qzPM"
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
  user_id = update.effective_user.id
  await show_menu(update, context, parent_id=0, is_start=True)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0, is_start=False):
  user_id = update.effective_user.id
  conn = sqlite3.connect("tree_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, text FROM main_buttons WHERE parent_id = ?", (parent_id,))
  buttons = cursor.fetchall()
  conn.close()

  keyboard = []
  for btn_id, btn_text in buttons:
    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"btn_{btn_id}")])

  if parent_id != 0:
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT parent_id FROM main_buttons WHERE id = ?", (parent_id,))
    p_id = cursor.fetchone()[0]
    conn.close()
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"btn_{p_id}" if p_id != 0 else "main_menu")])
  else:
    keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])

  if user_id == ADMIN_ID:
    keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم الآدمن", callback_data="admin_panel")])

  reply_markup = InlineKeyboardMarkup(keyboard)
  text_msg = "أهلاً بك في المنصة التعليمية 📚\nاختر من القائمة أدناه:"

  if is_start:
    await update.message.reply_text(text_msg, reply_markup=reply_markup)
  else:
    query = update.callback_query
    await query.edit_message_text(text_msg, reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  if update.effective_user.id != ADMIN_ID:
    await query.answer("هذا الأمر مخصص للمشرف فقط!", show_alert=True)
    return

  keyboard = [
      [InlineKeyboardButton("➕ إضافة زر جديد", callback_data="add_btn")],
      [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
  ]
  await query.edit_message_text("⚙️ لوحة تحكم الآدمن لإدارة القوائم:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data
  user_id = update.effective_user.id

  if data == "main_menu":
    await show_menu(update, context, parent_id=0)
  elif data == "admin_panel":
    await admin_panel(update, context)
  elif data == "add_btn":
    if user_id != ADMIN_ID: return
    await query.message.reply_text("أرسل بيانات الزر الجديد بهذه الصيغة:\n`إضافة زر: [الرقم الأب (0 للرئيسية)], [نص الزر]`", parse_mode="Markdown")
  elif data.startswith("btn_"):
    btn_id = int(data.split("_")[1])
    conn = sqlite3.connect("tree_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, content, text FROM main_buttons WHERE id = ?", (btn_id,))
    btn = cursor.fetchone()
    conn.close()

    if btn:
      b_type, b_content, b_text = btn
      if b_type == "menu":
        await show_menu(update, context, parent_id=btn_id)
      else:
        await query.message.reply_text(f"📖 *{b_text}*\n\n{b_content}", parse_mode="Markdown")

async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if update.effective_user.id != ADMIN_ID:
    return

  text = update.message.text
  conn = sqlite3.connect("tree_bot.db")
  cursor = conn.cursor()

  if text.startswith("إضافة زر:"):
    try:
      parts = text.replace("إضافة زر:", "").split(",")
      parent_id = int(parts[0].strip())
      btn_text = parts[1].strip()
      cursor.execute("INSERT INTO main_buttons (parent_id, text, type) VALUES (?, ?, ?)", (parent_id, btn_text, "menu"))
      conn.commit()
      await update.message.reply_text(f"تمت إضافة الزر ({btn_text}) بنجاح! ✅")
    except Exception:
      await update.message.reply_text("خطأ في الصيغة. استخدم: `إضافة زر: [الرقم الأب], [نص الزر]`", parse_mode="Markdown")

  conn.close()

def main():
  application = ApplicationBuilder().token(TOKEN).build()

  application.add_handler(CommandHandler("start", start))
  application.add_handler(CallbackQueryHandler(button_handler))
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

  print("البوت يعمل الآن بنظام القوائم الشجرية...")
  application.run_polling()

if __name__ == "__main__":
  main()
