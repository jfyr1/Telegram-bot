# -*- coding: utf-8 -*-
"""
Telegram Menu Builder style bot - standalone implementation.

Requirements:
    python-telegram-bot>=21,<23

Environment:
    BOT_TOKEN       - required
    REQUIRED_CHANNEL - required channel username such as @mychannel
    ADMIN_ID        - optional; defaults to 5734654153
    DB_PATH         - optional; defaults to bot.db

The implementation is inspired by common Telegram menu-builder UX patterns.
It does not copy MenuBuilder's proprietary source code or branding.
"""

import os
import time
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Tuple

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("menu_builder_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = 5734654153
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
DB_PATH = os.getenv("DB_PATH", "bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from Environment Variables")

if not REQUIRED_CHANNEL:
    log.warning(
        "REQUIRED_CHANNEL is not configured. Subscription gate will ask the admin "
        "to configure it before normal users can enter."
    )

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            notifications INTEGER NOT NULL DEFAULT 1,
            joined_at INTEGER NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            title TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'menu',
            target TEXT,
            admin_only INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            button_id INTEGER UNIQUE NOT NULL,
            text TEXT,
            media_type TEXT,
            file_id TEXT,
            updated_at INTEGER NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            button_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY,
            menu_id INTEGER,
            editor_menu_id INTEGER,
            selected_button_id INTEGER,
            state TEXT,
            temp_text TEXT,
            temp_id INTEGER,
            updated_at INTEGER NOT NULL
        )
        """)

    defaults = {
        "home_title": "🏠 القائمة الرئيسية",
        "welcome_text": "👋 أهلاً بك!\nاختر من القائمة أدناه.",
        "maintenance": "0",
        "maintenance_text": "🛠️ البوت تحت الصيانة حالياً. حاول لاحقاً.",
        "subscribe_text": "🔐 لاستخدام البوت، يجب الاشتراك بالقناة أولاً.",
        "subscribe_button": "📢 الاشتراك بالقناة",
        "verify_button": "✅ تحقق من الاشتراك",
    }
    with db() as c:
        for k, v in defaults.items():
            c.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                (k, v),
            )

        count = c.execute(
            "SELECT COUNT(*) AS n FROM buttons WHERE parent_id IS NULL"
        ).fetchone()["n"]
        if count == 0:
            seeds = [
                ("📚 المواد الدراسية", "menu"),
                ("📝 الملخصات", "menu"),
                ("🧠 اختبارات MCQ", "menu"),
                ("⭐ المفضلة", "favorites"),
                ("💬 تواصل معنا", "contact"),
            ]
            for i, (title, kind) in enumerate(seeds):
                c.execute(
                    """INSERT INTO buttons(parent_id,title,kind,sort_order)
                       VALUES(NULL,?,?,?)""",
                    (title, kind, i),
                )


def get_required_channel() -> str:
    return get_setting("required_channel", REQUIRED_CHANNEL).strip()


def get_setting(key: str, default: str = "") -> str:
    with db() as c:
        row = c.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    with db() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def upsert_user(user):
    if not user:
        return
    with db() as c:
        c.execute(
            """INSERT INTO users(user_id,first_name,username,joined_at)
               VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 first_name=excluded.first_name,
                 username=excluded.username""",
            (
                user.id,
                user.first_name or "",
                user.username or "",
                int(time.time()),
            ),
        )


def get_state(user_id: int):
    with db() as c:
        row = c.execute(
            "SELECT * FROM user_state WHERE user_id=?", (user_id,)
        ).fetchone()
    return row


def save_state(
    user_id: int,
    menu_id=None,
    editor_menu_id=None,
    selected_button_id=None,
    state="",
    temp_text="",
    temp_id=None,
):
    old = get_state(user_id)
    vals = {
        "menu_id": old["menu_id"] if old and menu_id is None else menu_id,
        "editor_menu_id": (
            old["editor_menu_id"] if old and editor_menu_id is None
            else editor_menu_id
        ),
        "selected_button_id": (
            old["selected_button_id"]
            if old and selected_button_id is None
            else selected_button_id
        ),
        "state": state,
        "temp_text": temp_text,
        "temp_id": temp_id,
    }
    with db() as c:
        c.execute(
            """INSERT INTO user_state(
                 user_id,menu_id,editor_menu_id,selected_button_id,
                 state,temp_text,temp_id,updated_at
               ) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 menu_id=excluded.menu_id,
                 editor_menu_id=excluded.editor_menu_id,
                 selected_button_id=excluded.selected_button_id,
                 state=excluded.state,
                 temp_text=excluded.temp_text,
                 temp_id=excluded.temp_id,
                 updated_at=excluded.updated_at""",
            (
                user_id,
                vals["menu_id"],
                vals["editor_menu_id"],
                vals["selected_button_id"],
                vals["state"],
                vals["temp_text"],
                vals["temp_id"],
                int(time.time()),
            ),
        )


def get_buttons(parent_id=None, admin=False):
    with db() as c:
        if parent_id is None:
            rows = c.execute(
                """SELECT * FROM buttons
                   WHERE parent_id IS NULL
                   AND (hidden=0 OR ?=1)
                   ORDER BY sort_order,id""",
                (1 if admin else 0,),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM buttons
                   WHERE parent_id=?
                   AND (hidden=0 OR ?=1)
                   ORDER BY sort_order,id""",
                (parent_id, 1 if admin else 0),
            ).fetchall()
    return rows


def get_button(button_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM buttons WHERE id=?", (button_id,)
        ).fetchone()


def get_children_count(button_id: int):
    with db() as c:
        return c.execute(
            "SELECT COUNT(*) AS n FROM buttons WHERE parent_id=?",
            (button_id,),
        ).fetchone()["n"]


def get_post(button_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM posts WHERE button_id=?", (button_id,)
        ).fetchone()


def create_button(parent_id, title, kind="menu", target=None):
    with db() as c:
        n = c.execute(
            "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM buttons "
            "WHERE parent_id IS ?",
            (parent_id,),
        ).fetchone()["n"]
        cur = c.execute(
            """INSERT INTO buttons(parent_id,title,kind,target,sort_order)
               VALUES(?,?,?,?,?)""",
            (parent_id, title, kind, target, n),
        )
        return cur.lastrowid


def delete_button(button_id: int):
    with db() as c:
        child_ids = [
            r["id"] for r in c.execute(
                "SELECT id FROM buttons WHERE parent_id=?", (button_id,)
            ).fetchall()
        ]
        for cid in child_ids:
            delete_button_tx(c, cid)
        delete_button_tx(c, button_id)


def delete_button_tx(c, button_id):
    c.execute("DELETE FROM posts WHERE button_id=?", (button_id,))
    c.execute("DELETE FROM ratings WHERE button_id=?", (button_id,))
    c.execute("DELETE FROM buttons WHERE id=?", (button_id,))


def rename_button(button_id: int, title: str):
    with db() as c:
        c.execute(
            "UPDATE buttons SET title=? WHERE id=?", (title, button_id)
        )


def set_admin_only(button_id: int, value: bool):
    with db() as c:
        c.execute(
            "UPDATE buttons SET admin_only=? WHERE id=?",
            (1 if value else 0, button_id),
        )


def set_hidden(button_id: int, value: bool):
    with db() as c:
        c.execute(
            "UPDATE buttons SET hidden=? WHERE id=?",
            (1 if value else 0, button_id),
        )


def move_button(button_id: int, direction: int):
    b = get_button(button_id)
    if not b:
        return
    siblings = get_buttons(b["parent_id"], admin=True)
    idx = next((i for i, x in enumerate(siblings) if x["id"] == button_id), None)
    if idx is None:
        return
    other_idx = idx + direction
    if other_idx < 0 or other_idx >= len(siblings):
        return
    a = siblings[idx]
    other = siblings[other_idx]
    with db() as c:
        c.execute(
            "UPDATE buttons SET sort_order=? WHERE id=?",
            (other["sort_order"], a["id"]),
        )
        c.execute(
            "UPDATE buttons SET sort_order=? WHERE id=?",
            (a["sort_order"], other["id"]),
        )


def save_post(button_id, text=None, media_type=None, file_id=None):
    with db() as c:
        c.execute(
            """INSERT INTO posts(button_id,text,media_type,file_id,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(button_id) DO UPDATE SET
                 text=excluded.text,
                 media_type=excluded.media_type,
                 file_id=excluded.file_id,
                 updated_at=excluded.updated_at""",
            (button_id, text, media_type, file_id, int(time.time())),
        )


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def is_admin(user_id: int) -> bool:
    try:
        return int(user_id) == ADMIN_ID
    except Exception:
        return False


def kb(rows: List[List[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(x) for x in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_keyboard(user_id: int):
    admin = is_admin(user_id)
    rows = []
    buttons = get_buttons(None, admin=admin)
    for i in range(0, len(buttons), 2):
        pair = [b["title"] for b in buttons[i:i+2]]
        rows.append(pair)
    if admin:
        rows.append(["👑 لوحة الأدمن"])
    return kb(rows or [["🏠 القائمة الرئيسية"]])


def editor_keyboard(menu_id, user_id):
    buttons = get_buttons(menu_id, admin=True)
    rows = []
    for i in range(0, len(buttons), 2):
        row = []
        for b in buttons[i:i+2]:
            title = b["title"]
            state = get_state(user_id)
            selected = state and state["selected_button_id"] == b["id"]
            row.append(f"[ {title} ]" if selected else title)
        rows.append(row)
    rows.extend([
        ["➕ إضافة زر", "↕️ ترتيب الأزرار"],
        ["✏️ تعديل المحدد", "📝 محتوى المحدد"],
        ["🗑 حذف المحدد", "🔒 صلاحيات المحدد"],
        ["👁️ معاينة", "⚙️ إعدادات البوت"],
        ["🏠 الرئيسية", "⏹️ إيقاف المحرر"],
    ])
    return kb(rows)


def admin_keyboard():
    return kb([
        ["🎛 محرر الأزرار", "📝 محرر المحتوى"],
        ["📢 إعلان", "📣 رسالة جماعية"],
        ["🔔 الإشعارات", "💬 المراسلات"],
        ["👥 المستخدمون", "📊 الإحصائيات"],
        ["⭐ التقييمات", "⚙️ إعدادات البوت"],
        ["👁️ معاينة", "🏠 الرئيسية"],
    ])


def confirm_keyboard(ok: str, cancel: str = "❌ إلغاء"):
    return kb([[ok, cancel]])


def subscribe_keyboard():
    rows = []
    if get_required_channel():
        rows.append([KeyboardButton(get_setting("subscribe_button"))])
    rows.append([KeyboardButton(get_setting("verify_button"))])
    return kb(rows)


def parse_selected_id(user_id: int) -> Optional[int]:
    st = get_state(user_id)
    return st["selected_button_id"] if st else None


async def safe_delete(message):
    if not message:
        return
    try:
        await message.delete()
    except Exception:
        pass


async def clean_previous(update: Update, context: ContextTypes.DEFAULT_TYPE):
    old = context.user_data.get("last_bot_message_id")
    if old:
        try:
            await context.bot.delete_message(update.effective_chat.id, old)
        except Exception:
            pass
    context.user_data["last_bot_message_id"] = None


async def send_clean(update: Update, context, text, reply_markup=None, **kwargs):
    await clean_previous(update, context)
    msg = await update.effective_message.reply_text(
        text, reply_markup=reply_markup, **kwargs
    )
    context.user_data["last_bot_message_id"] = msg.message_id
    return msg


# ---------------------------------------------------------------------------
# Subscription gate
# ---------------------------------------------------------------------------

async def subscribed(user_id: int, bot) -> bool:
    if is_admin(user_id):
        return True
    channel = get_required_channel()
    if not channel:
        return False
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except Exception as exc:
        log.warning("Subscription check failed: %s", exc)
        return False


async def require_subscription(update: Update, context) -> bool:
    user = update.effective_user
    if not user:
        return False
    if is_admin(user.id):
        return True
    if await subscribed(user.id, context.bot):
        return True

    text = get_setting("subscribe_text")
    await send_clean(
        update,
        context,
        text,
        reply_markup=subscribe_keyboard(),
    )
    return False


# ---------------------------------------------------------------------------
# Rendering menus and posts
# ---------------------------------------------------------------------------

async def show_home(update, context, edit_state=True):
    user = update.effective_user
    if edit_state:
        save_state(user.id, menu_id=None, state="")
    text = get_setting("welcome_text")
    if is_admin(user.id):
        text += "\n\n👑 وضع الأدمن متاح لك."
    await send_clean(
        update,
        context,
        text,
        reply_markup=main_keyboard(user.id),
    )


async def show_menu(update, context, button_id: int):
    user = update.effective_user
    b = get_button(button_id)
    if not b:
        await show_home(update, context)
        return

    if b["admin_only"] and not is_admin(user.id):
        return

    if b["kind"] == "favorites":
        await show_favorites(update, context)
        return
    if b["kind"] == "contact":
        await send_clean(
            update,
            context,
            "💬 للتواصل معنا أرسل رسالتك هنا وسيتم تحويلها للإدارة.",
            reply_markup=kb([["🏠 الرئيسية"]]),
        )
        save_state(user.id, menu_id=button_id, state="contact")
        return

    children = get_buttons(button_id, admin=is_admin(user.id))
    post = get_post(button_id)

    if post:
        await render_post(update, context, button_id, post)
        return

    save_state(user.id, menu_id=button_id, state="")
    rows = []
    for i in range(0, len(children), 2):
        rows.append([x["title"] for x in children[i:i+2]])
    rows.append(["↩️ رجوع", "🏠 الرئيسية"])

    title = b["title"]
    text = f"📂 {title}\n\nاختر من القائمة:"
    await send_clean(update, context, text, reply_markup=kb(rows))


async def render_post(update, context, button_id, post):
    user = update.effective_user
    save_state(user.id, menu_id=button_id, state="")
    text = post["text"] or ""
    if post["media_type"] == "photo" and post["file_id"]:
        await clean_previous(update, context)
        msg = await update.effective_message.reply_photo(
            post["file_id"],
            caption=text[:1024],
            reply_markup=kb([["↩️ رجوع", "🏠 الرئيسية"], ["⭐ تقييم"]]),
        )
        context.user_data["last_bot_message_id"] = msg.message_id
        return
    if post["media_type"] == "document" and post["file_id"]:
        await clean_previous(update, context)
        msg = await update.effective_message.reply_document(
            post["file_id"],
            caption=text[:1024],
            reply_markup=kb([["↩️ رجوع", "🏠 الرئيسية"], ["⭐ تقييم"]]),
        )
        context.user_data["last_bot_message_id"] = msg.message_id
        return
    if post["media_type"] == "video" and post["file_id"]:
        await clean_previous(update, context)
        msg = await update.effective_message.reply_video(
            post["file_id"],
            caption=text[:1024],
            reply_markup=kb([["↩️ رجوع", "🏠 الرئيسية"], ["⭐ تقييم"]]),
        )
        context.user_data["last_bot_message_id"] = msg.message_id
        return
    if post["media_type"] == "audio" and post["file_id"]:
        await clean_previous(update, context)
        msg = await update.effective_message.reply_audio(
            post["file_id"],
            caption=text[:1024],
            reply_markup=kb([["↩️ رجوع", "🏠 الرئيسية"], ["⭐ تقييم"]]),
        )
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    await send_clean(
        update,
        context,
        text or "📭 لا يوجد محتوى حالياً.",
        reply_markup=kb([["↩️ رجوع", "🏠 الرئيسية"], ["⭐ تقييم"]]),
    )


async def show_favorites(update, context):
    with db() as c:
        rows = c.execute(
            """SELECT DISTINCT b.* FROM ratings r
               JOIN buttons b ON b.id=r.button_id
               WHERE r.user_id=? AND r.rating>=4
               ORDER BY r.created_at DESC""",
            (update.effective_user.id,),
        ).fetchall()
    if not rows:
        text = "⭐ لا توجد مفضلات حتى الآن."
        buttons = [["🏠 الرئيسية"]]
    else:
        text = "⭐ المفضلة"
        buttons = [[r["title"]] for r in rows] + [["🏠 الرئيسية"]]
    await send_clean(update, context, text, reply_markup=kb(buttons))


# ---------------------------------------------------------------------------
# Admin editor
# ---------------------------------------------------------------------------

async def open_editor(update, context, menu_id=None):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if menu_id is None:
        st = get_state(user.id)
        menu_id = st["editor_menu_id"] if st else None
    save_state(
        user.id,
        editor_menu_id=menu_id,
        selected_button_id=None,
        state="editor",
    )
    title = "🎛 محرر الأزرار"
    if menu_id:
        b = get_button(menu_id)
        title += f"\n📂 داخل: {b['title'] if b else 'قسم'}"
    else:
        title += "\n🏠 الرئيسية"
    await send_clean(
        update,
        context,
        title + "\n\nاضغط زر مرة واحدة لتحديده، واضغطه مرة ثانية للدخول للقسم.",
        reply_markup=editor_keyboard(menu_id, user.id),
    )


async def editor_button_click(update, context, title: str):
    user = update.effective_user
    st = get_state(user.id)
    if not st or st["state"] != "editor":
        return False
    buttons = get_buttons(st["editor_menu_id"], admin=True)
    match = next((b for b in buttons if b["title"] == title or f"[ {b['title']} ]" == title), None)
    if not match:
        return False

    selected = st["selected_button_id"]
    if selected == match["id"]:
        # Second press: enter submenu if it has children.
        if get_children_count(match["id"]) > 0 or match["kind"] == "menu":
            await open_editor(update, context, match["id"])
            return True

    save_state(
        user.id,
        editor_menu_id=st["editor_menu_id"],
        selected_button_id=match["id"],
        state="editor",
    )
    await open_editor(update, context, st["editor_menu_id"])
    return True


async def add_button_start(update, context):
    save_state(update.effective_user.id, state="await_add_title")
    await send_clean(
        update, context,
        "➕ **إضافة زر**\n\nأرسل اسم الزر الجديد:",
        reply_markup=kb([["❌ إلغاء"]]),
    )


async def edit_selected_start(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.", reply_markup=editor_keyboard(
            get_state(update.effective_user.id)["editor_menu_id"], update.effective_user.id))
        return
    b = get_button(bid)
    save_state(update.effective_user.id, state="await_rename", temp_id=bid)
    await send_clean(
        update, context,
        f"✏️ **تعديل الزر**\n\nالاسم الحالي:\n{b['title']}\n\nأرسل الاسم الجديد:",
        reply_markup=kb([["❌ إلغاء"]]),
    )


async def edit_content_start(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.")
        return
    b = get_button(bid)
    save_state(update.effective_user.id, state="await_content", temp_id=bid)
    await send_clean(
        update, context,
        f"📝 **محرر المحتوى**\n\nالزر: {b['title']}\n\n"
        "أرسل النص أو PDF أو صورة أو فيديو أو ملف صوتي.\n"
        "سيتم استبدال المحتوى السابق بعد التأكيد.",
        reply_markup=kb([["❌ إلغاء"]]),
    )


async def delete_selected_start(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.")
        return
    b = get_button(bid)
    save_state(update.effective_user.id, state="confirm_delete", temp_id=bid)
    await send_clean(
        update, context,
        f"🗑️ **تأكيد الحذف**\n\nالزر: **{b['title']}**\n\n"
        "⚠️ سيتم حذف الزر ومحتواه والأقسام الموجودة داخله.\n"
        "هل أنت متأكد؟",
        reply_markup=confirm_keyboard("✅ نعم، احذف", "❌ إلغاء"),
    )


async def move_menu(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.")
        return
    save_state(update.effective_user.id, state="move")
    await send_clean(
        update, context,
        "↕️ **ترتيب الزر**\n\nاختر الاتجاه:",
        reply_markup=kb([
            ["⬆️ للأعلى", "⬇️ للأسفل"],
            ["↩️ إلغاء"],
        ]),
    )


async def permission_menu(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.")
        return
    b = get_button(bid)
    save_state(update.effective_user.id, state="permissions", temp_id=bid)
    status = "مفعل 🔒" if b["admin_only"] else "مفتوح 👥"
    await send_clean(
        update, context,
        f"🔒 **صلاحيات الزر**\n\n{b['title']}\nالحالة: {status}",
        reply_markup=kb([
            ["🔒 للأدمن فقط", "👥 للجميع"],
            ["👻 إخفاء/إظهار"],
            ["↩️ إلغاء"],
        ]),
    )


async def preview_selected(update, context):
    bid = parse_selected_id(update.effective_user.id)
    if not bid:
        await send_clean(update, context, "⚠️ حدد زر أولاً.")
        return
    b = get_button(bid)
    await send_clean(
        update, context,
        f"👁️ **معاينة**\n\n{b['title']}\n\nهذه هي الواجهة كما يراها المستخدم.",
        reply_markup=main_keyboard(update.effective_user.id),
    )


async def bot_settings(update, context):
    if not is_admin(update.effective_user.id):
        return
    maintenance = get_setting("maintenance") == "1"
    await send_clean(
        update, context,
        "⚙️ **إعدادات البوت**",
        reply_markup=kb([
            [f"🛠 الصيانة: {'ON 🟢' if maintenance else 'OFF 🔴'}"],
            ["🏷️ تعديل اسم الرئيسية", "📝 تعديل رسالة الترحيب"],
            ["🔐 إعداد قناة الاشتراك", "📩 رسائل النظام"],
            ["↩️ رجوع للأدمن"],
        ]),
    )


# ---------------------------------------------------------------------------
# Admin broadcasts, notifications, stats, ratings
# ---------------------------------------------------------------------------

async def broadcast_start(update, context, notification_only=False):
    if not is_admin(update.effective_user.id):
        return
    save_state(
        update.effective_user.id,
        state="await_broadcast",
        temp_text="notifications" if notification_only else "all",
    )
    target = "المستخدمين المفعّلين للإشعارات" if notification_only else "جميع المستخدمين"
    await send_clean(
        update, context,
        f"📣 **رسالة جماعية**\n\nالهدف: {target}\n\nأرسل الرسالة الآن.",
        reply_markup=kb([["❌ إلغاء"]]),
    )


async def stats(update, context):
    with db() as c:
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        buttons = c.execute("SELECT COUNT(*) n FROM buttons").fetchone()["n"]
        posts = c.execute("SELECT COUNT(*) n FROM posts").fetchone()["n"]
        ratings = c.execute("SELECT COUNT(*) n FROM ratings").fetchone()["n"]
    await send_clean(
        update, context,
        f"📊 **الإحصائيات**\n\n"
        f"👥 المستخدمون: {users}\n"
        f"🎛 الأزرار: {buttons}\n"
        f"📝 المحتويات: {posts}\n"
        f"⭐ التقييمات: {ratings}",
        reply_markup=admin_keyboard(),
    )


async def ratings_report(update, context):
    with db() as c:
        rows = c.execute(
            """SELECT rating, COUNT(*) n FROM ratings
               GROUP BY rating ORDER BY rating"""
        ).fetchall()
    lines = ["⭐ **التقييمات**", ""]
    for r in rows:
        lines.append(f"{r['rating']} ⭐ : {r['n']}")
    await send_clean(update, context, "\n".join(lines), reply_markup=admin_keyboard())


# ---------------------------------------------------------------------------
# Main message router
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_user(update.effective_user)
    save_state(update.effective_user.id, state="")
    if not await require_subscription(update, context):
        return
    await show_home(update, context)


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    upsert_user(user)
    text = update.message.text or ""
    st = get_state(user.id)

    # Admin actions bypass subscription gate.
    if not is_admin(user.id):
        if not await require_subscription(update, context):
            return

    # Always-available navigation.
    if text in {"🏠 الرئيسية", "القائمة الرئيسية", "/home"}:
        await show_home(update, context)
        return

    if text == "👑 لوحة الأدمن":
        if is_admin(user.id):
            save_state(user.id, state="admin")
            await send_clean(update, context, "👑 **لوحة الإدارة**", reply_markup=admin_keyboard())
        return

    # ---------------- editor state ----------------
    if is_admin(user.id) and st and st["state"] == "editor":
        if text == "➕ إضافة زر":
            await add_button_start(update, context); return
        if text == "✏️ تعديل المحدد":
            await edit_selected_start(update, context); return
        if text == "📝 محتوى المحدد":
            await edit_content_start(update, context); return
        if text == "🗑 حذف المحدد":
            await delete_selected_start(update, context); return
        if text == "↕️ ترتيب الأزرار":
            await move_menu(update, context); return
        if text == "🔒 صلاحيات المحدد":
            await permission_menu(update, context); return
        if text == "👁️ معاينة":
            await preview_selected(update, context); return
        if text == "⚙️ إعدادات البوت":
            await bot_settings(update, context); return
        if text == "⏹️ إيقاف المحرر":
            save_state(user.id, state="admin")
            await send_clean(update, context, "👑 تم إيقاف المحرر.", reply_markup=admin_keyboard())
            return
        if text == "↩️ رجوع":
            parent = get_button(st["editor_menu_id"]) if st["editor_menu_id"] else None
            await open_editor(update, context, parent["parent_id"] if parent else None)
            return
        if text == "🏠 الرئيسية":
            await open_editor(update, context, None); return
        if await editor_button_click(update, context, text):
            return

    # ---------------- editor workflows ----------------
    if is_admin(user.id) and st:
        state = st["state"]

        if state == "await_add_title":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            title = text.strip()
            if not title:
                return
            parent = st["editor_menu_id"]
            new_id = create_button(parent, title)
            save_state(user.id, editor_menu_id=parent, selected_button_id=new_id, state="editor")
            await open_editor(update, context, parent)
            return

        if state == "await_rename":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            bid = st["temp_id"]
            save_state(user.id, state="confirm_rename", temp_id=bid, temp_text=text.strip())
            await send_clean(
                update, context,
                f"✏️ **تأكيد التعديل**\n\nالاسم الجديد:\n{text.strip()}\n\nهل تريد الحفظ؟",
                reply_markup=confirm_keyboard("✅ حفظ التعديل"),
            )
            return

        if state == "confirm_rename":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            if text == "✅ حفظ التعديل":
                rename_button(st["temp_id"], st["temp_text"])
                await open_editor(update, context, st["editor_menu_id"])
            return

        if state == "confirm_delete":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            if text == "✅ نعم، احذف":
                delete_button(st["temp_id"])
                await open_editor(update, context, st["editor_menu_id"])
            return

        if state == "move":
            if text == "↩️ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            if text in {"⬆️ للأعلى", "⬇️ للأسفل"}:
                move_button(st["selected_button_id"], -1 if text.startswith("⬆") else 1)
                await open_editor(update, context, st["editor_menu_id"])
            return

        if state == "permissions":
            bid = st["temp_id"]
            if text == "🔒 للأدمن فقط":
                set_admin_only(bid, True)
                await open_editor(update, context, st["editor_menu_id"])
                return
            if text == "👥 للجميع":
                set_admin_only(bid, False)
                await open_editor(update, context, st["editor_menu_id"])
                return
            if text == "👻 إخفاء/إظهار":
                b = get_button(bid)
                set_hidden(bid, not bool(b["hidden"]))
                await open_editor(update, context, st["editor_menu_id"])
                return
            if text == "↩️ إلغاء":
                await open_editor(update, context, st["editor_menu_id"])
                return

        if state == "await_content":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            bid = st["temp_id"]
            save_state(user.id, state="confirm_content", temp_id=bid, temp_text=text)
            await send_clean(
                update, context,
                f"📝 **تأكيد المحتوى**\n\n{text[:1500]}\n\nهل تريد حفظه؟",
                reply_markup=confirm_keyboard("✅ حفظ المحتوى"),
            )
            return

        if state == "confirm_content":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            if text == "✅ حفظ المحتوى":
                save_post(st["temp_id"], text=st["temp_text"], media_type=None, file_id=None)
                await open_editor(update, context, st["editor_menu_id"])
            return

        if state == "confirm_media":
            if text == "❌ إلغاء":
                await open_editor(update, context, st["editor_menu_id"]); return
            if text == "✅ حفظ المحتوى":
                pending = context.user_data.pop("pending_media", None)
                if pending:
                    media_type, file_id = pending
                    save_post(
                        st["temp_id"],
                        text=st["temp_text"],
                        media_type=media_type,
                        file_id=file_id,
                    )
                await open_editor(update, context, st["editor_menu_id"])
            return

        if state == "await_broadcast":
            if text == "❌ إلغاء":
                save_state(user.id, state="admin")
                await send_clean(update, context, "❌ تم الإلغاء.", reply_markup=admin_keyboard())
                return
            save_state(user.id, state="confirm_broadcast", temp_text=st["temp_text"], temp_id=None)
            context.user_data["broadcast_text"] = text
            target = "المشتركين بالإشعارات" if st["temp_text"] == "notifications" else "جميع المستخدمين"
            await send_clean(
                update, context,
                f"📣 **تأكيد الإرسال**\n\nالهدف: {target}\n\n{text[:1500]}",
                reply_markup=confirm_keyboard("📤 إرسال الآن"),
            )
            return

        if state == "confirm_broadcast":
            if text == "❌ إلغاء":
                save_state(user.id, state="admin")
                await send_clean(update, context, "❌ تم الإلغاء.", reply_markup=admin_keyboard())
                return
            if text == "📤 إرسال الآن":
                body = context.user_data.get("broadcast_text", "")
                only_notifications = st["temp_text"] == "notifications"
                with db() as c:
                    if only_notifications:
                        users = c.execute("SELECT user_id FROM users WHERE notifications=1").fetchall()
                    else:
                        users = c.execute("SELECT user_id FROM users").fetchall()
                sent = 0
                for row in users:
                    try:
                        await context.bot.send_message(row["user_id"], body)
                        sent += 1
                    except Exception:
                        pass
                save_state(user.id, state="admin")
                await send_clean(
                    update, context,
                    f"📤 تم الإرسال.\n✅ نجح: {sent}\n\n🧹 تم إنهاء العملية.",
                    reply_markup=admin_keyboard(),
                )
                return

        if state == "contact":
            if text == "↩️ رجوع" or text == "🏠 الرئيسية":
                await show_home(update, context); return
            await context.bot.send_message(
                ADMIN_ID,
                f"💬 رسالة من {user.full_name} (@{user.username or 'بدون معرف'})\n\n{text}"
            )
            await send_clean(update, context, "✅ وصلت رسالتك إلى الإدارة.", reply_markup=kb([["🏠 الرئيسية"]]))
            return

    # ---------------- admin menu ----------------
    if is_admin(user.id):
        if text == "🎛 محرر الأزرار":
            await open_editor(update, context, None); return
        if text == "📝 محرر المحتوى":
            await open_editor(update, context, None); return
        if text == "📢 إعلان":
            await broadcast_start(update, context, False); return
        if text == "📣 رسالة جماعية":
            await broadcast_start(update, context, False); return
        if text == "🔔 الإشعارات":
            await broadcast_start(update, context, True); return
        if text == "💬 المراسلات":
            await send_clean(update, context, "💬 المراسلات: رسائل المستخدمين تصل مباشرة إلى الإدارة.", reply_markup=admin_keyboard()); return
        if text == "👥 المستخدمون":
            await stats(update, context); return
        if text == "📊 الإحصائيات":
            await stats(update, context); return
        if text == "⭐ التقييمات":
            await ratings_report(update, context); return
        if text == "⚙️ إعدادات البوت":
            await bot_settings(update, context); return
        if text == "👁️ معاينة":
            await show_home(update, context); return

        if text.startswith("🛠 الصيانة:"):
            new = "0" if get_setting("maintenance") == "1" else "1"
            set_setting("maintenance", new)
            await bot_settings(update, context); return

        if text == "🏷️ تعديل اسم الرئيسية":
            save_state(user.id, state="await_home_title")
            await send_clean(update, context, "🏷️ أرسل اسم القائمة الرئيسية الجديد:", reply_markup=kb([["❌ إلغاء"]]))
            return

        if text == "📝 تعديل رسالة الترحيب":
            save_state(user.id, state="await_welcome")
            await send_clean(update, context, "📝 أرسل رسالة الترحيب الجديدة:", reply_markup=kb([["❌ إلغاء"]]))
            return

        if text == "🔐 إعداد قناة الاشتراك":
            save_state(user.id, state="await_channel")
            await send_clean(update, context, "🔐 أرسل @username للقناة المطلوبة للاشتراك:", reply_markup=kb([["❌ إلغاء"]]))
            return

        if text == "📩 رسائل النظام":
            await send_clean(update, context, "📩 رسائل النظام قابلة للتعديل من إعدادات المشروع.", reply_markup=admin_keyboard())
            return

        if text == "↩️ رجوع للأدمن":
            save_state(user.id, state="admin")
            await send_clean(update, context, "👑 لوحة الإدارة", reply_markup=admin_keyboard())
            return

        if st and st["state"] == "await_home_title":
            if text == "❌ إلغاء":
                await bot_settings(update, context); return
            set_setting("home_title", text.strip())
            await bot_settings(update, context); return

        if st and st["state"] == "await_welcome":
            if text == "❌ إلغاء":
                await bot_settings(update, context); return
            set_setting("welcome_text", text)
            await bot_settings(update, context); return

        if st and st["state"] == "await_channel":
            if text == "❌ إلغاء":
                await bot_settings(update, context); return
            set_setting("required_channel", text.strip())
            await bot_settings(update, context); return

    # ---------------- normal menu navigation ----------------
    if text == "↩️ رجوع":
        st = get_state(user.id)
        parent_id = st["menu_id"] if st else None
        parent = get_button(parent_id) if parent_id else None
        if parent and parent["parent_id"]:
            await show_menu(update, context, parent["parent_id"])
        else:
            await show_home(update, context)
        return

    if text == "⭐ تقييم":
        st = get_state(user.id)
        bid = st["menu_id"] if st else None
        if bid:
            save_state(user.id, state="await_rating", temp_id=bid)
            await send_clean(
                update, context,
                "⭐ قيّم هذا المحتوى من 1 إلى 5:",
                reply_markup=kb([["1 ⭐", "2 ⭐", "3 ⭐"], ["4 ⭐", "5 ⭐"], ["❌ إلغاء"]]),
            )
        return

    if st and st["state"] == "await_rating":
        if text == "❌ إلغاء":
            await show_home(update, context); return
        if "⭐" in text and text[0].isdigit():
            rating = int(text[0])
            with db() as c:
                c.execute(
                    "INSERT INTO ratings(user_id,button_id,rating,created_at) VALUES(?,?,?,?)",
                    (user.id, st["temp_id"], rating, int(time.time())),
                )
            await send_clean(update, context, "❤️ شكراً لتقييمك!", reply_markup=kb([["🏠 الرئيسية"]]))
            return

    # Match current menu buttons.
    current_parent = st["menu_id"] if st else None
    buttons = get_buttons(current_parent, admin=is_admin(user.id))
    match = next((b for b in buttons if b["title"] == text), None)
    if match:
        await show_menu(update, context, match["id"])
        return

    # Search all top-level buttons for direct access from stale keyboards.
    top = get_buttons(None, admin=is_admin(user.id))
    match = next((b for b in top if b["title"] == text), None)
    if match:
        await show_menu(update, context, match["id"])
        return

    await send_clean(
        update, context,
        "❓ لم أفهم الاختيار. استخدم أزرار القائمة.",
        reply_markup=main_keyboard(user.id),
    )


# ---------------------------------------------------------------------------
# Media handler for content editor
# ---------------------------------------------------------------------------

async def media_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.message:
        return
    st = get_state(user.id)
    if not st or st["state"] != "await_content":
        return

    media_type = None
    file_id = None
    caption = update.message.caption or ""

    if update.message.photo:
        media_type = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        media_type = "document"
        file_id = update.message.document.file_id
    elif update.message.video:
        media_type = "video"
        file_id = update.message.video.file_id
    elif update.message.audio:
        media_type = "audio"
        file_id = update.message.audio.file_id
    else:
        return

    save_state(
        user.id,
        state="confirm_media",
        temp_id=st["temp_id"],
        temp_text=caption,
    )
    context.user_data["pending_media"] = (media_type, file_id)
    await send_clean(
        update, context,
        f"📝 **تأكيد حفظ المحتوى**\n\nالنوع: {media_type}\n"
        f"{caption[:500]}\n\nهل تريد الحفظ؟",
        reply_markup=confirm_keyboard("✅ حفظ المحتوى"),
    )


# ---------------------------------------------------------------------------
# Commands and callbacks
# ---------------------------------------------------------------------------

async def admin_command(update, context):
    if is_admin(update.effective_user.id):
        save_state(update.effective_user.id, state="admin")
        await send_clean(update, context, "👑 **لوحة الإدارة**", reply_markup=admin_keyboard())
    else:
        await update.message.reply_text("⛔ هذا الأمر مخصص للإدارة.")


async def verify_command(update, context):
    upsert_user(update.effective_user)
    if await subscribed(update.effective_user.id, context.bot):
        await show_home(update, context)
    else:
        await send_clean(update, context, get_setting("subscribe_text"), reply_markup=subscribe_keyboard())


async def callback_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()


async def error_handler(update, context):
    log.exception("Unhandled error", exc_info=context.error)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def build_app():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("home", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("verify", verify_command))

    # Media first, then text. This prevents media messages being swallowed.
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.ALL | filters.VIDEO | filters.AUDIO,
            media_router,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_handler(CallbackQueryHandler(callback_noop))
    app.add_error_handler(error_handler)
    return app


def main():
    app = build_app()
    log.info("Bot started | admin=%s | channel=%s", ADMIN_ID, REQUIRED_CHANNEL or "<not set>")
    # run_polling owns the event loop and avoids the "no current event loop"
    # failure that commonly happens when mixing asyncio.run() with PTB.
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
