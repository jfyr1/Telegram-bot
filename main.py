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
ADMIN_ID = 5734654153  # الآدمن المحدد

# إعداد قاعدة البيانات
def init_db():
  conn = sqlite3.connect("education_bot.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_id INTEGER,
            name TEXT NOT NULL,
            FOREIGN KEY(stage_id) REFERENCES stages(id)
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            name TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS lectures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            title TEXT NOT NULL,
            type TEXT NOT NULL,
            file_id TEXT,
            content TEXT,
            FOREIGN KEY(subject_id) REFERENCES subjects(id)
        )
    """)
  conn.commit()
  conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = update.effective_user.id
  conn = sqlite3.connect("education_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, name FROM stages")
  stages = cursor.fetchall()
  conn.close()

  if not stages:
    msg = "مرحباً بك في المنصة التعليمية 📚\nعذراً، لا توجد مراحل دراسية متاحة حالياً."
    if user_id == ADMIN_ID:
      msg += "\n\nأنت المشرف، يمكنك استخدام /admin للوصول إلى لوحة التحكم."
    await update.message.reply_text(msg)
    return

  keyboard = []
  for stage_id, stage_name in stages:
    keyboard.append([InlineKeyboardButton(stage_name, callback_data=f"st_{stage_id}")])

  if user_id == ADMIN_ID:
    keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم الآدمن", callback_data="admin_panel")])

  await update.message.reply_text(
      "أهلاً بك في المنصة التعليمية 📚\nيرجى اختيار المرحلة الدراسية:",
      reply_markup=InlineKeyboardMarkup(keyboard),
  )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  if update.effective_user.id != ADMIN_ID:
    if query:
      await query.answer("هذا الأمر مخصص للمشرف فقط!", show_alert=True)
    return

  keyboard = [
      [InlineKeyboardButton("➕ إضافة مرحلة", callback_data="add_stage")],
      [InlineKeyboardButton("➕ إضافة كورس", callback_data="add_course")],
      [InlineKeyboardButton("➕ إضافة مادة", callback_data="add_subject")],
      [InlineKeyboardButton("➕ إضافة محاضرة", callback_data="add_lecture")],
      [InlineKeyboardButton("🔙 الرئيسية", callback_data="main_menu")],
  ]
  
  if query:
    await query.edit_message_text(
        "⚙️ لوحة تحكم المشرف لإدارة المحتوى:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
  else:
    await update.message.reply_text(
        "⚙️ لوحة تحكم المشرف لإدارة المحتوى:", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data
  user_id = update.effective_user.id

  if data == "main_menu":
    conn = sqlite3.connect("education_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM stages")
    stages = cursor.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton(s[1], callback_data=f"st_{s[0]}")] for s in stages]
    if user_id == ADMIN_ID:
      keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم الآدمن", callback_data="admin_panel")])
    
    await query.edit_message_text(
        "أهلاً بك في المنصة التعليمية 📚\nيرجى اختيار المرحلة الدراسية:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

  elif data == "admin_panel":
    await admin_panel(update, context)

  elif data.startswith("st_"):
    stage_id = data.split("_")[1]
    conn = sqlite3.connect("education_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM courses WHERE stage_id = ?", (stage_id,))
    courses = cursor.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton(c[1], callback_data=f"co_{c[0]}")] for c in courses]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await query.edit_message_text("اختر الكورس التعليمي:", reply_markup=InlineKeyboardMarkup(keyboard))

  elif data.startswith("co_"):
    course_id = data.split("_")[1]
    conn = sqlite3.connect("education_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM subjects WHERE course_id = ?", (course_id,))
    subjects = cursor.fetchall()
    cursor.execute("SELECT stage_id FROM courses WHERE id = ?", (course_id,))
    stage_id = cursor.fetchone()[0]
    conn.close()

    keyboard = [[InlineKeyboardButton(s[1], callback_data=f"su_{s[0]}")] for s in subjects]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"st_{stage_id}")])
    await query.edit_message_text("اختر المادة الدراسية:", reply_markup=InlineKeyboardMarkup(keyboard))

  elif data.startswith("su_"):
    subject_id = data.split("_")[1]
    conn = sqlite3.connect("education_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM lectures WHERE subject_id = ?", (subject_id,))
    lectures = cursor.fetchall()
    cursor.execute("SELECT course_id FROM subjects WHERE id = ?", (subject_id,))
    course_id = cursor.fetchone()[0]
    conn.close()

    keyboard = [[InlineKeyboardButton(l[1], callback_data=f"le_{l[0]}")] for l in lectures]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"co_{course_id}")])
    await query.edit_message_text("اختر المحاضرة المطلوبة:", reply_markup=InlineKeyboardMarkup(keyboard))

  elif data.startswith("le_"):
    lecture_id = data.split("_")[1]
    conn = sqlite3.connect("education_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, type, file_id, content FROM lectures WHERE id = ?", (lecture_id,))
    lec = cursor.fetchone()
    conn.close()

    title, l_type, file_id, content = lec
    if l_type == "text":
      await query.message.reply_text(f"📖 *{title}*\n\n{content}", parse_mode="Markdown")
    elif l_type == "document":
      await query.message.reply_document(document=file_id, caption=title)
    elif l_type == "video":
      await query.message.reply_video(video=file_id, caption=title)

  elif data == "add_stage":
    if user_id != ADMIN_ID: return
    await query.message.reply_text("أرسل اسم المرحلة الجديدة بالصيغة التالية:\n`إضافة مرحلة: [الاسم]`", parse_mode="Markdown")
  elif data == "add_course":
    if user_id != ADMIN_ID: return
    await query.message.reply_text("أرسل بيانات الكورس بالصيغة التالية:\n`إضافة كورس: [رقم المرحلة], [اسم الكورس]`", parse_mode="Markdown")
  elif data == "add_subject":
    if user_id != ADMIN_ID: return
    await query.message.reply_text("أرسل بيانات المادة بالصيغة التالية:\n`إضافة مادة: [رقم الكورس], [اسم المادة]`", parse_mode="Markdown")

async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if update.effective_user.id != ADMIN_ID:
    return

  text = update.message.text
  conn = sqlite3.connect("education_bot.db")
  cursor = conn.cursor()

  if text.startswith("إضافة مرحلة:"):
    stage_name = text.replace("إضافة مرحلة:", "").strip()
    cursor.execute("INSERT INTO stages (name) VALUES (?)", (stage_name,))
    conn.commit()
    await update.message.reply_text(f"تمت إضافة المرحلة ({stage_name}) بنجاح! ✅")

  elif text.startswith("إضافة كورس:"):
    try:
      parts = text.replace("إضافة كورس:", "").split(",")
      stage_id = parts[0].strip()
      course_name = parts[1].strip()
      cursor.execute("INSERT INTO courses (stage_id, name) VALUES (?, ?)", (stage_id, course_name))
      conn.commit()
      await update.message.reply_text("تمت إضافة الكورس بنجاح! ✅")
    except Exception:
      await update.message.reply_text("خطأ في الصيغة. استخدم: `إضافة كورس: [رقم المرحلة], [اسم الكورس]`", parse_mode="Markdown")

  elif text.startswith("إضافة مادة:"):
    try:
      parts = text.replace("إضافة مادة:", "").split(",")
      course_id = parts[0].strip()
      subject_name = parts[1].strip()
      cursor.execute("INSERT INTO subjects (course_id, name) VALUES (?, ?)", (course_id, subject_name))
      conn.commit()
      await update.message.reply_text("تمت إضافة المادة بنجاح! ✅")
    except Exception:
      await update.message.reply_text("خطأ في الصيغة. استخدم: `إضافة مادة: [رقم الكورس], [اسم المادة]`", parse_mode="Markdown")

  conn.close()

def main():
  application = ApplicationBuilder().token(TOKEN).build()

  application.add_handler(CommandHandler("start", start))
  application.add_handler(CommandHandler("admin", admin_panel))
  application.add_handler(CallbackQueryHandler(button_handler))
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

  print("البوت يعمل الآن بصلاحيات الآدمن المحددة...")
  application.run_polling()

if __name__ == "__main__":
  main()
