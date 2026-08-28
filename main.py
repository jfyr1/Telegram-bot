import os
import sqlite3
import logging
from contextlib import closing
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# =========================================================
# CONFIG
# =========================================================
# ضع التوكن في Environment Variable باسم BOT_TOKEN
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ضع ID الأدمن في Environment Variable باسم ADMIN_ID
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================================================
# DATABASE
# =========================================================
def db():
    return sqlite3.connect(DB_NAME)

def init_db():
    with closing(db()) as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS buttons(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT 'main'
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS posts(
            button_id INTEGER PRIMARY KEY,
            content_type TEXT NOT NULL,
            file_id TEXT,
            text_content TEXT,
            caption TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS favorites(
            user_id INTEGER,
            button_id INTEGER,
            PRIMARY KEY(user_id, button_id)
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS visits(
            button_id INTEGER PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            button_id INTEGER,
            kind TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS ratings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            rating INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS news(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS channels(
            chat_id TEXT PRIMARY KEY,
            title TEXT,
            username TEXT
        )""")

        if ADMIN_ID:
            c.execute(
                "INSERT OR IGNORE INTO admins(user_id) VALUES(?)",
                (ADMIN_ID,)
            )

        defaults = {
            "maintenance": "0",
            "start_text":
                "👋 أهلاً وسهلاً بك في المنصة الرسمية.\n\n"
                "اختر القسم المطلوب من القائمة أدناه:",
            "about_text":
                "ℹ️ حول البوت\n\n"
                "منصة تعليمية لتنظيم المواد والمحاضرات والملخصات والملفات."
        }

        for k, v in defaults.items():
            c.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                (k, v)
            )

        conn.commit()

init_db()

# =========================================================
# HELPERS
# =========================================================
def setting(key, default=""):
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default

def set_setting(key, value):
    with closing(db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (key, value)
        )
        conn.commit()

def is_admin(uid):
    if uid == ADMIN_ID:
        return True
    with closing(db()) as conn:
        return conn.execute(
            "SELECT 1 FROM admins WHERE user_id=?", (uid,)
        ).fetchone() is not None

def save_user(user):
    with closing(db()) as conn:
        old = conn.execute(
            "SELECT 1 FROM users WHERE user_id=?", (user.id,)
        ).fetchone()

        conn.execute("""
            INSERT OR REPLACE INTO users(user_id,first_name,username)
            VALUES(?,?,?)
        """, (user.id, user.first_name or "", user.username or ""))
        conn.commit()
        return old is None

def all_users():
    with closing(db()) as conn:
        return [x[0] for x in conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()]

def parse_id(text):
    if "〔" not in text or "〕" not in text:
        return None
    try:
        return int(text.rsplit("〔", 1)[1].split("〕", 1)[0])
    except Exception:
        return None

def get_button(bid):
    if not bid:
        return None
    with closing(db()) as conn:
        return conn.execute("""
            SELECT id,parent_id,title,position,category
            FROM buttons WHERE id=?
        """, (bid,)).fetchone()

def children(parent_id):
    with closing(db()) as conn:
        return conn.execute("""
            SELECT id,parent_id,title,position,category
            FROM buttons
            WHERE parent_id=?
            ORDER BY position,id
        """, (parent_id,)).fetchall()

def all_buttons():
    with closing(db()) as conn:
        return conn.execute("""
            SELECT id,parent_id,title,position,category
            FROM buttons ORDER BY parent_id,position,id
        """).fetchall()

def button_label(row):
    return f"{row[2]} 〔{row[0]}〕"

def post_for(bid):
    with closing(db()) as conn:
        return conn.execute("""
            SELECT content_type,file_id,text_content,caption
            FROM posts WHERE button_id=?
        """, (bid,)).fetchone()

def delete_tree(bid):
    with closing(db()) as conn:
        c = conn.cursor()

        def rec(x):
            kids = c.execute(
                "SELECT id FROM buttons WHERE parent_id=?", (x,)
            ).fetchall()
            for kid, in kids:
                rec(kid)
            c.execute("DELETE FROM posts WHERE button_id=?", (x,))
            c.execute("DELETE FROM favorites WHERE button_id=?", (x,))
            c.execute("DELETE FROM visits WHERE button_id=?", (x,))
            c.execute("DELETE FROM buttons WHERE id=?", (x,))

        rec(bid)
        conn.commit()

def move_button(bid, new_parent):
    row = get_button(bid)
    parent = get_button(new_parent) if new_parent else None

    if not row:
        return False, "الزر غير موجود."

    if new_parent == bid:
        return False, "لا يمكن نقل الزر داخل نفسه."

    # لا تسمح بنقل الزر داخل أحد أبنائه
    cur = new_parent
    while cur:
        if cur == bid:
            return False, "لا يمكن نقل القسم داخل قسم فرعي تابع له."
        r = get_button(cur)
        cur = r[1] if r else 0

    if parent and parent[0] == bid:
        return False, "المكان الجديد غير صالح."

    with closing(db()) as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position),-1)+1 FROM buttons WHERE parent_id=?",
            (new_parent,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE buttons SET parent_id=?,position=? WHERE id=?",
            (new_parent, pos, bid)
        )
        conn.commit()

    return True, "تم النقل."

def get_main_keyboard(uid):
    # هذه هي الواجهة الأساسية الثابتة فقط.
    # الأقسام الدراسية يضيفها الأدمن من محرر الأزرار.
    rows = [
        [KeyboardButton("📚 الأقسام"), KeyboardButton("⭐ المفضلة")],
        [KeyboardButton("🔥 الأكثر دخولاً"), KeyboardButton("🔍 البحث")],
        [KeyboardButton("📝 تقييم البوت"), KeyboardButton("ℹ️ حول البوت")],
        [KeyboardButton("💬 مراسلة الأدمن")]
    ]
    if is_admin(uid):
        rows.append([KeyboardButton("⚙️ لوحة الأدمن")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)

def nav_keyboard(parent_id, uid, title=None):
    rows = []
    kids = children(parent_id)

    for i in range(0, len(kids), 2):
        row = [KeyboardButton(button_label(kids[i]))]
        if i + 1 < len(kids):
            row.append(KeyboardButton(button_label(kids[i+1])))
        rows.append(row)

    # كل قسم له واجهة مستقلة: اسم القسم + رجوع + رئيسية
    if title:
        rows.append([KeyboardButton(f"📍 {title}")])

    if parent_id:
        rows.append([
            KeyboardButton("🔙 رجوع"),
            KeyboardButton("🏠 الرئيسية")
        ])
    else:
        rows.append([KeyboardButton("🏠 الرئيسية")])

    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True
    )

def editor_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔘 محرر الأزرار"),
         KeyboardButton("📝 محرر المشاركات")],
        [KeyboardButton("📨 المراسلات"),
         KeyboardButton("⭐ التقييمات")],
        [KeyboardButton("📊 الإحصائيات"),
         KeyboardButton("⚙️ إعدادات البوت")],
        [KeyboardButton("📰 الأخبار"),
         KeyboardButton("📢 إرسال جماعي")],
        [KeyboardButton("👮 المشرفون"),
         KeyboardButton("📢 القنوات والمجموعات")],
        [KeyboardButton("📖 دليل البوت")],
        [KeyboardButton("🏠 الرئيسية")]
    ], resize_keyboard=True, is_persistent=True)

def button_editor_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ إضافة قسم/زر"),
         KeyboardButton("✏️ تعديل اسم")],
        [KeyboardButton("📦 إضافة قسم فرعي"),
         KeyboardButton("↔️ نقل قسم")],
        [KeyboardButton("🔗 دمج قسمين"),
         KeyboardButton("🗑 حذف قسم")],
        [KeyboardButton("📋 عرض الشجرة"),
         KeyboardButton("↕️ ترتيب الأقسام")],
        [KeyboardButton("🔙 لوحة الأدمن"),
         KeyboardButton("🏠 الرئيسية")]
    ], resize_keyboard=True, is_persistent=True)

def post_editor_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ إضافة/استبدال مشاركة"),
         KeyboardButton("✏️ تعديل مشاركة")],
        [KeyboardButton("🗑 حذف محتوى"),
         KeyboardButton("📋 عرض المشاركات")],
        [KeyboardButton("🔙 لوحة الأدمن"),
         KeyboardButton("🏠 الرئيسية")]
    ], resize_keyboard=True, is_persistent=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("❌ إلغاء")]],
        resize_keyboard=True,
        is_persistent=True
    )

def confirm_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("✅ تأكيد"), KeyboardButton("❌ إلغاء")]
    ], resize_keyboard=True, is_persistent=True)

# =========================================================
# CONTENT DELIVERY
# =========================================================
async def send_post(update, bid):
    post = post_for(bid)
    if not post:
        await update.message.reply_text(
            "📭 لا يوجد محتوى مضاف لهذا القسم حالياً.",
            reply_markup=nav_keyboard(
                get_button(bid)[1], update.effective_user.id
            )
        )
        return

    content_type, file_id, text_content, caption = post
    cap = caption or ""

    # المحتوى يُرسل حسب نوع الرسالة التي خزّنها الأدمن.
    if content_type == "text":
        await update.message.reply_text(text_content or "")
    elif content_type == "photo":
        await update.message.reply_photo(file_id, caption=cap)
    elif content_type == "video":
        await update.message.reply_video(file_id, caption=cap)
    elif content_type == "document":
        await update.message.reply_document(file_id, caption=cap)
    elif content_type == "audio":
        await update.message.reply_audio(file_id, caption=cap)
    elif content_type == "voice":
        await update.message.reply_voice(file_id, caption=cap)
    elif content_type == "animation":
        await update.message.reply_animation(file_id, caption=cap)
    elif content_type == "sticker":
        await update.message.reply_sticker(file_id)

def save_media_message(msg):
    if msg.document:
        return "document", msg.document.file_id, msg.caption or ""
    if msg.photo:
        return "photo", msg.photo[-1].file_id, msg.caption or ""
    if msg.video:
        return "video", msg.video.file_id, msg.caption or ""
    if msg.audio:
        return "audio", msg.audio.file_id, msg.caption or ""
    if msg.voice:
        return "voice", msg.voice.file_id, msg.caption or ""
    if msg.animation:
        return "animation", msg.animation.file_id, msg.caption or ""
    if msg.sticker:
        return "sticker", msg.sticker.file_id, ""
    return None

# =========================================================
# START / MAIN
# =========================================================
async def start(update, context):
    new = save_user(update.effective_user)

    if new and ADMIN_ID and update.effective_user.id != ADMIN_ID:
        try:
            u = update.effective_user
            await context.bot.send_message(
                ADMIN_ID,
                "🆕 مستخدم جديد دخل البوت\n\n"
                f"👤 الاسم: {u.first_name or '-'}\n"
                f"🔗 @{u.username or '-'}\n"
                f"🆔 ID: {u.id}"
            )
        except Exception as e:
            logging.warning("New user notification failed: %s", e)

    context.user_data.clear()

    if setting("maintenance") == "1" and not is_admin(u.id if 'u' in locals() else update.effective_user.id):
        await update.message.reply_text(
            "🛠 البوت في وضع الصيانة.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("🔄 تحديث")]],
                resize_keyboard=True
            )
        )
        return

    await update.message.reply_text(
        setting("start_text"),
        reply_markup=get_main_keyboard(update.effective_user.id)
    )

# =========================================================
# SECTION VIEW
# =========================================================
async def open_section(update, context, bid):
    row = get_button(bid)
    if not row:
        return

    context.user_data["parent_id"] = bid
    context.user_data["current_title"] = row[2]

    with closing(db()) as conn:
        conn.execute("""
            INSERT INTO visits(button_id,count) VALUES(?,1)
            ON CONFLICT(button_id) DO UPDATE SET count=count+1
        """, (bid,))
        conn.commit()

    kids = children(bid)
    post = post_for(bid)

    if kids:
        await update.message.reply_text(
            f"📍 {row[2]}\n\nاختر من الأقسام:",
            reply_markup=nav_keyboard(bid, update.effective_user.id, row[2])
        )
        return

    if post:
        await send_post(update, bid)
        await update.message.reply_text(
            f"📍 {row[2]}",
            reply_markup=nav_keyboard(row[1], update.effective_user.id, row[2])
        )
    else:
        await update.message.reply_text(
            f"📍 {row[2]}\n\n📭 لا يوجد محتوى حالياً.",
            reply_markup=nav_keyboard(row[1], update.effective_user.id, row[2])
        )

# =========================================================
# ADMIN PANEL
# =========================================================
async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        return
    context.user_data.clear()
    await update.message.reply_text(
        "⚙️ لوحة الأدمن\n\nاختر القسم:",
        reply_markup=editor_keyboard()
    )

async def button_editor(update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "🔘 محرر الأزرار\n\n"
        "يمكنك إضافة وتعديل ونقل ودمج وحذف الأقسام، "
        "وكل عملية حساسة تحتاج تأكيداً.",
        reply_markup=button_editor_keyboard()
    )

async def post_editor(update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 محرر المشاركات\n\n"
        "حدد القسم ثم أرسل المحتوى مباشرة.\n"
        "البوت يتعرف على نوع الملف تلقائياً.",
        reply_markup=post_editor_keyboard()
    )

# =========================================================
# ADMIN SELECT BUTTON
# =========================================================
async def select_buttons(update, context, state, prompt):
    rows = []
    for b in all_buttons():
        rows.append([KeyboardButton(button_label(b))])
    rows.append([KeyboardButton("❌ إلغاء")])
    context.user_data["state"] = state
    await update.message.reply_text(prompt, reply_markup=ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True
    ))

# =========================================================
# TEXT HANDLER
# =========================================================
async def handle_text(update, context):
    if not update.message:
        return

    user = update.effective_user
    uid = user.id
    text = update.message.text.strip()
    save_user(user)

    if setting("maintenance") == "1" and not is_admin(uid) and text != "🔄 تحديث":
        await update.message.reply_text(
            "🛠 البوت في وضع الصيانة.\nيرجى المحاولة لاحقاً.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("🔄 تحديث")]], resize_keyboard=True
            )
        )
        return

    state = context.user_data.get("state")

    # ---------- GLOBAL ----------
    if text == "❌ إلغاء":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ تم الإلغاء.",
            reply_markup=editor_keyboard() if is_admin(uid) else get_main_keyboard(uid)
        )
        return

    if text in ("🏠 الرئيسية", "🏠 القائمة الرئيسية"):
        context.user_data.clear()
        await update.message.reply_text(
            setting("start_text"),
            reply_markup=get_main_keyboard(uid)
        )
        return

    if text == "🔄 تحديث":
        await start(update, context)
        return

    if text == "🔙 لوحة الأدمن" and is_admin(uid):
        await admin_panel(update, context)
        return

    if text == "🔙 رجوع":
        parent = context.user_data.get("parent_id", 0)
        if parent:
            row = get_button(parent)
            if row:
                previous = row[1]
                context.user_data["parent_id"] = previous
                title = get_button(previous)[2] if previous else None
                await update.message.reply_text(
                    "🔙 رجوع",
                    reply_markup=nav_keyboard(previous, uid, title)
                )
                return
        await start(update, context)
        return

    # ---------- USER ----------
    if text == "📚 الأقسام":
        context.user_data["parent_id"] = 0
        await update.message.reply_text(
            "📚 الأقسام الرئيسية:",
            reply_markup=nav_keyboard(0, uid)
        )
        return

    if text == "⭐ المفضلة":
        with closing(db()) as conn:
            rows = conn.execute("""
                SELECT b.id,b.parent_id,b.title,b.position,b.category
                FROM favorites f JOIN buttons b ON b.id=f.button_id
                WHERE f.user_id=? ORDER BY b.title
            """, (uid,)).fetchall()

        if not rows:
            await update.message.reply_text(
                "⭐ لا توجد أقسام في المفضلة.",
                reply_markup=get_main_keyboard(uid)
            )
        else:
            await update.message.reply_text(
                "⭐ المفضلة:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton(button_label(r))] for r in rows] +
                    [[KeyboardButton("🏠 الرئيسية")]],
                    resize_keyboard=True, is_persistent=True
                )
            )
        return

    if text == "🔥 الأكثر دخولاً":
        with closing(db()) as conn:
            rows = conn.execute("""
                SELECT b.id,b.parent_id,b.title,b.position,b.category,v.count
                FROM visits v JOIN buttons b ON b.id=v.button_id
                ORDER BY v.count DESC LIMIT 20
            """).fetchall()

        if not rows:
            await update.message.reply_text(
                "🔥 لا توجد إحصائيات بعد.",
                reply_markup=get_main_keyboard(uid)
            )
        else:
            await update.message.reply_text(
                "🔥 الأكثر دخولاً:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton(f"{r[2]} 〔{r[0]}〕 — {r[5]} زيارة")] for r in rows] +
                    [[KeyboardButton("🏠 الرئيسية")]],
                    resize_keyboard=True, is_persistent=True
                )
            )
        return

    if text == "🔍 البحث":
        context.user_data.clear()
        context.user_data["state"] = "search"
        await update.message.reply_text(
            "🔍 أرسل اسم القسم أو المادة:",
            reply_markup=cancel_keyboard()
        )
        return

    if state == "search":
        q = f"%{text}%"
        with closing(db()) as conn:
            rows = conn.execute("""
                SELECT id,parent_id,title,position,category
                FROM buttons WHERE title LIKE ?
                ORDER BY title LIMIT 30
            """, (q,)).fetchall()

        if not rows:
            await update.message.reply_text("❌ لا توجد نتائج.")
            return

        context.user_data["state"] = "search_result"
        context.user_data["search_ids"] = {r[0] for r in rows}
        await update.message.reply_text(
            "🔍 النتائج:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(button_label(r))] for r in rows] +
                [[KeyboardButton("🏠 الرئيسية")]],
                resize_keyboard=True, is_persistent=True
            )
        )
        return

    if state == "search_result":
        bid = parse_id(text)
        if bid in context.user_data.get("search_ids", set()):
            context.user_data.clear()
            await open_section(update, context, bid)
            return

    if text == "📝 تقييم البوت":
        context.user_data.clear()
        context.user_data["state"] = "rating"
        await update.message.reply_text(
            "⭐ اختر تقييمك من 1 إلى 5:",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("⭐ 1"), KeyboardButton("⭐⭐ 2")],
                [KeyboardButton("⭐⭐⭐ 3"), KeyboardButton("⭐⭐⭐⭐ 4")],
                [KeyboardButton("⭐⭐⭐⭐⭐ 5")],
                [KeyboardButton("❌ إلغاء")]
            ], resize_keyboard=True)
        )
        return

    if state == "rating":
        vals = {"⭐ 1":1, "⭐⭐ 2":2, "⭐⭐⭐ 3":3,
                "⭐⭐⭐⭐ 4":4, "⭐⭐⭐⭐⭐ 5":5}
        if text in vals:
            context.user_data["rating"] = vals[text]
            context.user_data["state"] = "rating_note"
            await update.message.reply_text(
                "✍️ اكتب ملاحظتك (أو اكتب «بدون ملاحظة»):",
                reply_markup=cancel_keyboard()
            )
        return

    if state == "rating_note":
        rating = context.user_data.get("rating")
        note = "" if text == "بدون ملاحظة" else text
        with closing(db()) as conn:
            conn.execute(
                "INSERT INTO ratings(user_id,rating,note) VALUES(?,?,?)",
                (uid, rating, note)
            )
            conn.commit()
        context.user_data.clear()
        await update.message.reply_text(
            "✅ شكراً لتقييمك.",
            reply_markup=get_main_keyboard(uid)
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"⭐ تقييم جديد: {rating}/5\n"
                    f"👤 {user.first_name or '-'}\n"
                    f"🆔 {uid}\n"
                    f"📝 {note or '-'}"
                )
            except Exception:
                pass
        return

    if text == "ℹ️ حول البوت":
        await update.message.reply_text(
            setting("about_text"),
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("🏠 الرئيسية")]],
                resize_keyboard=True
            )
        )
        return

    if text == "💬 مراسلة الأدمن":
        context.user_data.clear()
        context.user_data["state"] = "contact"
        await update.message.reply_text(
            "💬 أرسل رسالتك أو الملف أو الصورة، وستصل للأدمن.",
            reply_markup=cancel_keyboard()
        )
        return

    if state == "contact":
        # النص هنا؛ الوسائط يعالجها handle_media.
        with closing(db()) as conn:
            conn.execute(
                "INSERT INTO messages(user_id,kind,content) VALUES(?,?,?)",
                (uid, "text", text)
            )
            conn.commit()
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"💬 مراسلة جديدة\n👤 {user.first_name or '-'}\n"
                    f"🆔 {uid}\n\n{text}"
                )
            except Exception:
                pass
        context.user_data.clear()
        await update.message.reply_text(
            "✅ تم إرسال رسالتك للأدمن.",
            reply_markup=get_main_keyboard(uid)
        )
        return

    # ---------- ADMIN ----------
    if is_admin(uid):
        if text == "⚙️ لوحة الأدمن":
            await admin_panel(update, context); return

        if text == "🔘 محرر الأزرار":
            await button_editor(update, context); return

        if text == "📝 محرر المشاركات":
            await post_editor(update, context); return

        # إضافة قسم رئيسي
        if text == "➕ إضافة قسم/زر":
            context.user_data["state"] = "add_root_title"
            await update.message.reply_text(
                "➕ أرسل اسم القسم الرئيسي:",
                reply_markup=cancel_keyboard()
            ); return

        if state == "add_root_title":
            with closing(db()) as conn:
                pos = conn.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM buttons WHERE parent_id=0"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO buttons(parent_id,title,position,category) VALUES(0,?,?,?)",
                    (text,pos,"main")
                )
                conn.commit()
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تمت إضافة القسم الرئيسي.",
                reply_markup=button_editor_keyboard()
            ); return

        if text == "📦 إضافة قسم فرعي":
            await select_buttons(
                update, context, "add_child_select",
                "📦 اختر القسم الأب:"
            ); return

        if state == "add_child_select":
            parent = parse_id(text)
            if not get_button(parent):
                await update.message.reply_text("❌ اختر من القائمة."); return
            context.user_data["new_parent"] = parent
            context.user_data["state"] = "add_child_title"
            await update.message.reply_text(
                "✏️ أرسل اسم القسم الفرعي:",
                reply_markup=cancel_keyboard()
            ); return

        if state == "add_child_title":
            parent = context.user_data["new_parent"]
            with closing(db()) as conn:
                pos = conn.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM buttons WHERE parent_id=?",
                    (parent,)
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO buttons(parent_id,title,position,category) VALUES(?,?,?,?)",
                    (parent,text,pos,"sub")
                )
                conn.commit()
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تمت إضافة القسم الفرعي.",
                reply_markup=button_editor_keyboard()
            ); return

        if text == "✏️ تعديل اسم":
            await select_buttons(
                update, context, "edit_title_select",
                "✏️ اختر القسم الذي تريد تعديل اسمه:"
            ); return

        if state == "edit_title_select":
            bid = parse_id(text)
            row = get_button(bid)
            if not row:
                await update.message.reply_text("❌ اختر من القائمة."); return
            context.user_data["edit_id"] = bid
            context.user_data["state"] = "edit_title"
            await update.message.reply_text(
                f"الاسم الحالي: {row[2]}\n\nأرسل الاسم الجديد:",
                reply_markup=cancel_keyboard()
            ); return

        if state == "edit_title":
            bid = context.user_data["edit_id"]
            with closing(db()) as conn:
                conn.execute("UPDATE buttons SET title=? WHERE id=?", (text,bid))
                conn.commit()
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تم تعديل الاسم.",
                reply_markup=button_editor_keyboard()
            ); return

        if text == "↔️ نقل قسم":
            await select_buttons(
                update, context, "move_select",
                "↔️ اختر القسم الذي تريد نقله:"
            ); return

        if state == "move_select":
            bid = parse_id(text)
            if not get_button(bid):
                await update.message.reply_text("❌ اختر من القائمة."); return
            context.user_data["move_id"] = bid
            context.user_data["state"] = "move_parent"
            rows = [[KeyboardButton("🏠 القسم الرئيسي")]]
            for b in all_buttons():
                if b[0] != bid:
                    rows.append([KeyboardButton(button_label(b))])
            rows.append([KeyboardButton("❌ إلغاء")])
            await update.message.reply_text(
                "📦 اختر المكان الجديد:",
                reply_markup=ReplyKeyboardMarkup(
                    rows, resize_keyboard=True, is_persistent=True
                )
            ); return

        if state == "move_parent":
            bid = context.user_data["move_id"]
            new_parent = 0 if text == "🏠 القسم الرئيسي" else parse_id(text)
            ok, msg = move_button(bid, new_parent)
            if not ok:
                await update.message.reply_text(f"❌ {msg}"); return
            context.user_data["pending_action"] = "move"
            context.user_data["state"] = "confirm_move"
            await update.message.reply_text(
                "⚠️ تأكيد النقل؟",
                reply_markup=confirm_keyboard()
            ); return

        if state == "confirm_move":
            if text == "✅ تأكيد":
                context.user_data.clear()
                await update.message.reply_text(
                    "✅ تم نقل القسم.",
                    reply_markup=button_editor_keyboard()
                )
            return

        if text == "🔗 دمج قسمين":
            await select_buttons(
                update, context, "merge_first",
                "🔗 اختر القسم الأول:"
            ); return

        if state == "merge_first":
            bid = parse_id(text)
            if not get_button(bid):
                await update.message.reply_text("❌ اختر من القائمة."); return
            context.user_data["merge_from"] = bid
            context.user_data["state"] = "merge_second"
            await select_buttons(
                update, context, "merge_second",
                "اختر القسم الذي ستُنقل إليه محتويات القسم الأول:"
            ); return

        if state == "merge_second":
            dest = parse_id(text)
            src = context.user_data.get("merge_from")
            if not get_button(dest) or dest == src:
                await update.message.reply_text("❌ اختيار غير صالح."); return
            context.user_data["merge_to"] = dest
            context.user_data["state"] = "merge_confirm"
            await update.message.reply_text(
                "⚠️ تأكيد الدمج؟\n"
                "سيتم نقل الأقسام الفرعية والمحتوى إلى القسم الثاني، "
                "ثم حذف القسم الأول.",
                reply_markup=confirm_keyboard()
            ); return

        if state == "merge_confirm":
            if text == "✅ تأكيد":
                src = context.user_data["merge_from"]
                dest = context.user_data["merge_to"]
                # نقل مباشر للأبناء
                with closing(db()) as conn:
                    conn.execute(
                        "UPDATE buttons SET parent_id=? WHERE parent_id=?",
                        (dest,src)
                    )
                    # إذا كان للقسم محتوى، انقله فقط إذا الوجهة بلا محتوى
                    src_post = conn.execute(
                        "SELECT content_type,file_id,text_content,caption FROM posts WHERE button_id=?",
                        (src,)
                    ).fetchone()
                    dest_post = conn.execute(
                        "SELECT 1 FROM posts WHERE button_id=?", (dest,)
                    ).fetchone()
                    if src_post and not dest_post:
                        conn.execute(
                            "INSERT INTO posts(button_id,content_type,file_id,text_content,caption) VALUES(?,?,?,?,?)",
                            (dest,*src_post)
                        )
                    conn.execute("DELETE FROM posts WHERE button_id=?", (src,))
                    conn.execute("DELETE FROM buttons WHERE id=?", (src,))
                    conn.commit()
                context.user_data.clear()
                await update.message.reply_text(
                    "✅ تم دمج القسمين.",
                    reply_markup=button_editor_keyboard()
                )
            return

        if text == "🗑 حذف قسم":
            await select_buttons(
                update, context, "delete_select",
                "🗑 اختر القسم الذي تريد حذفه:"
            ); return

        if state == "delete_select":
            bid = parse_id(text)
            row = get_button(bid)
            if not row:
                await update.message.reply_text("❌ اختر من القائمة."); return
            context.user_data["delete_id"] = bid
            context.user_data["state"] = "delete_confirm"
            await update.message.reply_text(
                f"⚠️ تأكيد الحذف\n\n« {row[2]} »\n\n"
                "سيتم حذف القسم وجميع الأقسام الفرعية والمحتوى.",
                reply_markup=confirm_keyboard()
            ); return

        if state == "delete_confirm":
            if text == "✅ تأكيد":
                delete_tree(context.user_data["delete_id"])
                context.user_data.clear()
                await update.message.reply_text(
                    "🗑 تم الحذف.",
                    reply_markup=button_editor_keyboard()
                )
            return

        if text == "📋 عرض الشجرة":
            buttons = all_buttons()
            if not buttons:
                out = "📋 لا توجد أقسام."
            else:
                out = "📋 شجرة الأقسام:\n\n"
                for b in buttons:
                    level = 0
                    p = b[1]
                    while p:
                        r = get_button(p)
                        if not r: break
                        level += 1
                        p = r[1]
                    out += "  " * level + f"• {b[2]} 〔{b[0]}〕\n"
            await update.message.reply_text(out, reply_markup=button_editor_keyboard())
            return

        # ---------- POST EDITOR ----------
        if text in ("➕ إضافة/استبدال مشاركة", "✏️ تعديل مشاركة", "🗑 حذف محتوى"):
            await select_buttons(
                update, context, "post_select",
                "📝 اختر القسم الذي تريد إدارة محتواه:"
            )
            context.user_data["post_action"] = text
            return

        if state == "post_select":
            bid = parse_id(text)
            if not get_button(bid):
                await update.message.reply_text("❌ اختر من القائمة."); return
            action = context.user_data.get("post_action")
            if action == "🗑 حذف محتوى":
                context.user_data["post_id"] = bid
                context.user_data["state"] = "post_delete_confirm"
                await update.message.reply_text(
                    "⚠️ تأكيد حذف المحتوى؟",
                    reply_markup=confirm_keyboard()
                )
            else:
                context.user_data["post_id"] = bid
                context.user_data["state"] = "post_wait"
                await update.message.reply_text(
                    "📨 الآن أرسل المحتوى مباشرة.\n"
                    "نص، PDF، صورة، فيديو، ملف، صوت، بصمة، ملصق أو GIF.\n\n"
                    "لا تحتاج لاختيار نوع المحتوى.",
                    reply_markup=cancel_keyboard()
                )
            return

        if state == "post_delete_confirm":
            if text == "✅ تأكيد":
                bid = context.user_data["post_id"]
                with closing(db()) as conn:
                    conn.execute("DELETE FROM posts WHERE button_id=?", (bid,))
                    conn.commit()
                context.user_data.clear()
                await update.message.reply_text(
                    "🗑 تم حذف المحتوى.",
                    reply_markup=post_editor_keyboard()
                )
            return

        if state == "post_wait":
            bid = context.user_data["post_id"]
            with closing(db()) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts(
                        button_id,content_type,text_content,file_id,caption
                    ) VALUES(?,?,?,?,?)
                """, (bid,"text",text,None,None))
                conn.commit()
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تم حفظ النص.",
                reply_markup=post_editor_keyboard()
            )
            return

        # ---------- ADMIN TOOLS ----------
        if text == "📊 الإحصائيات":
            with closing(db()) as conn:
                users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                buttons = conn.execute("SELECT COUNT(*) FROM buttons").fetchone()[0]
                posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                ratings = conn.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
                avg = conn.execute("SELECT AVG(rating) FROM ratings").fetchone()[0]
            await update.message.reply_text(
                f"📊 الإحصائيات\n\n"
                f"👥 المستخدمون: {users}\n"
                f"🔘 الأقسام: {buttons}\n"
                f"📝 المشاركات: {posts}\n"
                f"⭐ التقييمات: {ratings}\n"
                f"⭐ المتوسط: {avg:.2f}" if avg else
                f"📊 الإحصائيات\n\n👥 المستخدمون: {users}\n🔘 الأقسام: {buttons}\n📝 المشاركات: {posts}\n⭐ التقييمات: {ratings}",
                reply_markup=editor_keyboard()
            ); return

        if text == "⭐ التقييمات":
            with closing(db()) as conn:
                rows = conn.execute("""
                    SELECT user_id,rating,note,created_at
                    FROM ratings ORDER BY id DESC LIMIT 30
                """).fetchall()
            out = "⭐ آخر التقييمات:\n\n"
            for r in rows:
                out += f"👤 {r[0]} — {r[1]}/5\n📝 {r[2] or '-'}\n\n"
            await update.message.reply_text(out, reply_markup=editor_keyboard()); return

        if text == "📨 المراسلات":
            with closing(db()) as conn:
                rows = conn.execute("""
                    SELECT user_id,button_id,kind,content,created_at
                    FROM messages ORDER BY id DESC LIMIT 30
                """).fetchall()
            out = "📨 آخر المراسلات:\n\n"
            for r in rows:
                out += f"👤 {r[0]} | قسم: {r[1] or '-'}\n📝 {r[3] or r[2]}\n\n"
            await update.message.reply_text(out, reply_markup=editor_keyboard()); return

        if text == "⚙️ إعدادات البوت":
            context.user_data["state"] = "settings"
            await update.message.reply_text(
                "⚙️ الإعدادات:\n\n"
                "اكتب:\n"
                "start = لتعديل رسالة البداية\n"
                "about = لتعديل صفحة حول البوت\n"
                "maintenance = تشغيل/إيقاف الصيانة",
                reply_markup=cancel_keyboard()
            ); return

        if state == "settings":
            if text == "maintenance":
                new = "0" if setting("maintenance") == "1" else "1"
                set_setting("maintenance", new)
                await update.message.reply_text(
                    f"🛠 الصيانة: {'مفعلة' if new == '1' else 'متوقفة'}",
                    reply_markup=editor_keyboard()
                )
                context.user_data.clear()
                return
            if text in ("start","about"):
                context.user_data["setting_key"] = "start_text" if text == "start" else "about_text"
                context.user_data["state"] = "setting_value"
                await update.message.reply_text(
                    "✍️ أرسل النص الجديد:",
                    reply_markup=cancel_keyboard()
                ); return

        if state == "setting_value":
            set_setting(context.user_data["setting_key"], text)
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تم حفظ الإعداد.",
                reply_markup=editor_keyboard()
            ); return

        if text == "📖 دليل البوت":
            await update.message.reply_text(
                "📖 دليل البوت\n\n"
                "👤 المستخدم:\n"
                "• الأقسام: للوصول إلى الأقسام التي يضيفها الأدمن.\n"
                "• المفضلة: حفظ الأقسام المهمة.\n"
                "• الأكثر دخولاً: أكثر الأقسام زيارة.\n"
                "• البحث: البحث باسم القسم.\n"
                "• التقييم: إرسال تقييم وملاحظة.\n"
                "• المراسلة: إرسال ملاحظة للأدمن.\n\n"
                "👨‍💻 الأدمن:\n"
                "• محرر الأزرار: إضافة/تعديل/نقل/دمج/حذف.\n"
                "• محرر المشاركات: اختر القسم ثم أرسل المحتوى مباشرة.\n"
                "• الحذف والنقل والدمج تتطلب تأكيداً.\n"
                "• كل قسم يظهر بواجهة Keyboard مستقلة.",
                reply_markup=editor_keyboard()
            ); return

        # أخبار/إرسال جماعي/مشرفون/قنوات
        if text == "📰 الأخبار":
            context.user_data["state"] = "news"
            await update.message.reply_text(
                "📰 أرسل الخبر:",
                reply_markup=cancel_keyboard()
            ); return

        if state == "news":
            with closing(db()) as conn:
                conn.execute(
                    "INSERT INTO news(title,content) VALUES(?,?)",
                    ("خبر جديد",text)
                )
                conn.commit()
            context.user_data.clear()
            await update.message.reply_text(
                "✅ تم حفظ الخبر.", reply_markup=editor_keyboard()
            ); return

        if text == "📢 إرسال جماعي":
            context.user_data["state"] = "broadcast"
            await update.message.reply_text(
                "📢 أرسل الرسالة الجماعية أو الوسائط:",
                reply_markup=cancel_keyboard()
            ); return

    # ---------- DYNAMIC BUTTON ----------
    bid = parse_id(text)
    if bid:
        row = get_button(bid)
        if row:
            await open_section(update, context, bid)
            return

    # Dynamic navigation fallback
    parent = context.user_data.get("parent_id", 0)
    for row in children(parent):
        if text == button_label(row):
            await open_section(update, context, row[0])
            return

    await update.message.reply_text(
        "❓ اختر من القائمة.",
        reply_markup=editor_keyboard() if is_admin(uid) else get_main_keyboard(uid)
    )

# =========================================================
# MEDIA HANDLER
# =========================================================
async def handle_media(update, context):
    if not update.message:
        return

    user = update.effective_user
    uid = user.id
    save_user(user)

    state = context.user_data.get("state")

    # الأدمن يضيف المحتوى مباشرة للقسم المحدد
    if is_admin(uid) and state == "post_wait":
        bid = context.user_data.get("post_id")
        media = save_media_message(update.message)
        if not media:
            await update.message.reply_text("❌ نوع المحتوى غير مدعوم.")
            return

        content_type, file_id, caption = media

        with closing(db()) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO posts(
                    button_id,content_type,file_id,text_content,caption
                ) VALUES(?,?,?,?,?)
            """, (bid,content_type,file_id,None,caption))
            conn.commit()

        context.user_data.clear()
        await update.message.reply_text(
            "✅ تم حفظ المحتوى تلقائياً حسب نوعه.",
            reply_markup=post_editor_keyboard()
        )
        return

    # مراسلة الأدمن
    if state == "contact":
        media = save_media_message(update.message)
        if media:
            kind, file_id, caption = media
            with closing(db()) as conn:
                conn.execute(
                    "INSERT INTO messages(user_id,kind,content) VALUES(?,?,?)",
                    (uid,kind,file_id)
                )
                conn.commit()

            if ADMIN_ID:
                try:
                    await update.message.copy(chat_id=ADMIN_ID)
                    await context.bot.send_message(
                        ADMIN_ID,
                        f"💬 مراسلة وسائط من {user.first_name or '-'} "
                        f"(ID: {uid})"
                    )
                except Exception:
                    pass

            context.user_data.clear()
            await update.message.reply_text(
                "✅ تم إرسال المحتوى للأدمن.",
                reply_markup=get_main_keyboard(uid)
            )
            return

    # الإرسال الجماعي
    if is_admin(uid) and state == "broadcast":
        sent = failed = 0
        for target in all_users():
            try:
                await update.message.copy(chat_id=target)
                sent += 1
            except Exception:
                failed += 1
        context.user_data.clear()
        await update.message.reply_text(
            f"📢 اكتمل الإرسال.\n\n✅ {sent}\n❌ {failed}",
            reply_markup=editor_keyboard()
        )
        return

# =========================================================
# ERROR / MAIN
# =========================================================
async def error_handler(update, context):
    logging.error("Update error:", exc_info=context.error)

def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود. أضف التوكن في Environment Variables."
        )
    if not ADMIN_ID:
        raise RuntimeError(
            "ADMIN_ID غير موجود أو غير صحيح. أضف ID الأدمن في Environment Variables."
        )

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(
        filters.Document.ALL |
        filters.PHOTO |
        filters.VIDEO |
        filters.AUDIO |
        filters.VOICE |
        filters.ANIMATION |
        filters.Sticker.ALL,
        handle_media
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text
    ))

    app.add_error_handler(error_handler)

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
