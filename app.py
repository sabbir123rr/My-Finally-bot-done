import sys
import time
import asyncio
import logging
import secrets
import string
import sqlite3
from html import escape

from config import Config

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)


# ============== CONFIG ==============

TOKEN = Config.BOT_TOKEN
ADMIN_IDS = set(Config.ADMIN_IDS)
BOT_USERNAME = Config.BOT_USERNAME
STORAGE_CHANNEL = Config.STORAGE_CHANNEL_ID
PRIVATE_CHANNELS = Config.PRIVATE_CHANNELS
DB_PATH = Config.DB_PATH


# ============== LOGGING ==============

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

log = logging.getLogger(__name__)


# ============== HELPERS ==============

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ============== GREEN STARTUP ANIMATION ==============

def startup_animation():
    GREEN = "\033[92m"
    RESET = "\033[0m"
    CLEAR = "\033[2J\033[H"

    # Clear terminal without changing its background color
    sys.stdout.write(CLEAR)
    sys.stdout.flush()

    frames = [
        "🚀 Starting TEAM DARK HUNTER Bot",
        "🚀 Starting TEAM DARK HUNTER Bot.",
        "🚀 Starting TEAM DARK HUNTER Bot..",
        "🚀 Starting TEAM DARK HUNTER Bot...",
    ]

    for frame in frames:
        sys.stdout.write("\033[H" + GREEN + frame + RESET)
        sys.stdout.flush()
        time.sleep(0.4)

    # Clear screen before displaying status box
    sys.stdout.write(CLEAR)
    sys.stdout.flush()

    lines = [
        "╔══════════════════════════════════════════════╗",
        "║                                              ║",
        "║         🔥 TEAM DARK HUNTER 🔥              ║",
        "║                                              ║",
        "║       ✅ YOUR BOT IS FULLY RUNNING           ║",
        "║                                              ║",
        "║       😈 DEVOLOPER : ALEX SABBIR                   ║",
        "║                                              ║",
        "║       ⚡ STATUS: ONLINE                      ║",
        "║                                              ║",
        "╚══════════════════════════════════════════════╝",
    ]

    for line in lines:
        print(GREEN + line + RESET)

    sys.stdout.flush()


# ============== DATABASE ==============

def db():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            code TEXT PRIMARY KEY,
            storage_message_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id)
        )
    """)

    conn.commit()
    return conn


# ============== PRIVATE JOIN REQUEST ==============

async def join_request_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    request = update.chat_join_request

    if not request:
        return

    allowed_channel_ids = {
        channel[0] for channel in PRIVATE_CHANNELS
    }

    if request.chat.id not in allowed_channel_ids:
        return

    conn = db()

    try:
        conn.execute("""
            INSERT OR REPLACE INTO pending_requests
            (user_id, chat_id)
            VALUES (?, ?)
        """, (
            request.from_user.id,
            request.chat.id,
        ))

        conn.commit()

    finally:
        conn.close()

    log.info(
        "Join request received: user=%s channel=%s",
        request.from_user.id,
        request.chat.id,
    )


# ============== FILE CODE ==============

def new_code():
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(10))


# ============== JOIN KEYBOARD ==============

def join_keyboard(code=""):
    rows = []

    # Private channel buttons: two per row
    for i in range(0, len(PRIVATE_CHANNELS), 2):
        row = []

        for channel in PRIVATE_CHANNELS[i:i + 2]:
            _, invite_link, title = channel

            row.append(
                InlineKeyboardButton(
                    title,
                    url=invite_link,
                )
            )

        rows.append(row)

    # Verify button
    rows.append([
        InlineKeyboardButton(
            "✅ VERIFY",
            callback_data=f"verify:{code}",
        )
    ])

    return InlineKeyboardMarkup(rows)


# ============== CHECK MEMBERSHIP / REQUEST ==============

async def is_joined(bot, user_id: int) -> bool:
    """
    For every configured private channel:
    - User is already a member, OR
    - User has a saved join-request record.
    """

    conn = db()

    try:
        for channel_id, _, _ in PRIVATE_CHANNELS:

            # 1. Check actual membership
            try:
                member = await bot.get_chat_member(
                    chat_id=channel_id,
                    user_id=user_id,
                )

                if member.status in (
                    "creator",
                    "administrator",
                    "member",
                ):
                    continue

                if (
                    member.status == "restricted"
                    and member.is_member
                ):
                    continue

            except Exception as e:
                log.warning(
                    "Membership check failed for %s: %s",
                    channel_id,
                    e,
                )

            # 2. Check saved join request
            result = conn.execute("""
                SELECT 1
                FROM pending_requests
                WHERE user_id = ? AND chat_id = ?
            """, (
                user_id,
                channel_id,
            )).fetchone()

            if result is None:
                return False

        return True

    finally:
        conn.close()


# ============== START COMMAND ==============

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    code = context.args[0] if context.args else ""
    user_name = escape(user.first_name or "User")

    if not await is_joined(context.bot, user.id):

        await chat.send_message(
            f"👋 Hello, <b>{user_name}</b>!\n\n"
            "⚡ <b>TEAM DARK HUNTER</b>\n"
            "📦 Fast • Secure • Reliable File Delivery\n\n"
            "🔐 To access your requested file, please join "
            "all required private channels or send a Join Request "
            "to each one.\n\n"
            "👇 After joining or requesting, press ✅ VERIFY.",
            reply_markup=join_keyboard(code),
            parse_mode="HTML",
        )
        return

    if code:
        await deliver(chat.id, code, context)

    else:
        await chat.send_message(
    f"╭━━━ ⚡ <b>TEAM DARK HUNTER</b> ━━━╮\n\n"
    f"👋 Hello, <b>{user_name}</b>!\n\n"
    "<i>🚀 Your file. One link. Instant delivery.</i>\n"
    "<i>🔗 How to get started</i>\n\n"
    "🔐 Secure • ⚡ Fast • 📁 Simple\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛠️ <i>Powered by TEAM DARK HUNTER</i>\n\n"
    
    "😈 <i>BOT DEVELOPER: @UltimateNoobs</i>",
    parse_mode="HTML",
)


# ============== VERIFY CALLBACK ==============

async def verify_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer("Checking membership...")

    code = query.data.partition(":")[2]

    if await is_joined(context.bot, query.from_user.id):

        animation_frames = [
            "🔍 Checking your membership...\n\n▫️▫️▫️▫️▫️",
            "🔐 Verifying channels...\n\n🟩▫️▫️▫️▫️",
            "⚡ Processing verification...\n\n🟩🟩🟩▫️▫️",
            "✅ Verification Successful!\n\n🟩🟩🟩🟩🟩 100%",
        ]

        # Animate verification in the existing message
        for frame in animation_frames:
            try:
                await query.message.edit_text(frame)
            except Exception as e:
                log.warning("Animation error: %s", e)

            await asyncio.sleep(0.75)

        # Keep the 100% success message visible for 2 seconds
        await asyncio.sleep(2)

        # Remove verification animation message
        try:
            await query.message.delete()
        except Exception as e:
            log.warning(
                "Verification message removal failed: %s",
                e,
            )

        # Deliver file after verification animation is removed
        if code:
            await deliver(
                query.message.chat_id,
                code,
                context,
            )

        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🎉 All required channels verified successfully!",
            )

    else:
        await query.message.reply_text(
            "❌ Verification incomplete.\n\n"
            "Please join or send a Join Request to all "
            "3 private channels, then press VERIFY again.",
            reply_markup=join_keyboard(code),
        )


# ============== DELIVER FILE ==============

async def deliver(
    chat_id,
    code,
    context: ContextTypes.DEFAULT_TYPE,
):
    conn = db()

    try:
        row = conn.execute(
            "SELECT storage_message_id FROM files WHERE code = ?",
            (code,),
        ).fetchone()

    finally:
        conn.close()

    if not row:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Invalid or expired file link.",
        )
        return

    progress_msg = None

    try:
        # Text-based progress animation: no GIF or video
        frames = [
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "▫️▫️▫️▫️▫️  0%"
            ),
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "🟩▫️▫️▫️▫️  20%"
            ),
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "🟩🟩▫️▫️▫️  40%"
            ),
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "🟩🟩🟩▫️▫️  60%"
            ),
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "🟩🟩🟩🟩▫️  80%"
            ),
            (
                "⚡ <b>TEAM DARK HUNTER FILE SYSTEM</b>\n"
                "<i>Preparing your file...</i>\n\n"
                "🟩🟩🟩🟩🟩  100%"
            ),
        ]

        progress_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=frames[0],
            parse_mode="HTML",
        )

        for frame in frames[1:]:
            await asyncio.sleep(0.45)

            await progress_msg.edit_text(
                text=frame,
                parse_mode="HTML",
            )

        # Send stored file
        await context.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=STORAGE_CHANNEL,
            message_id=row[0],
        )

        # Delete Preparing message after successful file delivery
        try:
            await progress_msg.delete()
        except Exception:
            log.warning("Could not delete progress message")

        # Delivery confirmation
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "╭━━━━━━━━━━━━━━━━━━━━╮\n"
                "   ✅ <b>FILE DELIVERED!</b>\n"
                "   ✦ <i>Enjoy Your File</i> ✦\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯"
            ),
            parse_mode="HTML",
        )

    except Exception:
        log.exception("Could not deliver stored file")

        # Clean up progress message if delivery failed
        if progress_msg:
            try:
                await progress_msg.delete()
            except Exception:
                pass

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>FILE DELIVERY FAILED</b>\n"
                "<i>Please try again later.</i>"
            ),
            parse_mode="HTML",
        )


# ============== ADMIN FILE UPLOAD ==============

async def admin_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not is_admin(user.id):
        return

    if not (
        message.document
        or message.video
        or message.audio
        or message.photo
        or message.animation
        or message.voice
        or message.video_note
    ):
        await message.reply_text(
            "📎 Please send a file, photo, video or audio."
        )
        return

    try:
        copied = await context.bot.copy_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            caption=(
                "🔥 TEAM DARK HUNTER FILE\n"
                "🟢 Main Channel : @aimbot0999"
            ),
        )

        code = new_code()

        conn = db()

        try:
            conn.execute(
                """
                INSERT INTO files
                (code, storage_message_id, created_by)
                VALUES (?, ?, ?)
                """,
                (
                    code,
                    copied.message_id,
                    user.id,
                ),
            )

            conn.commit()

        finally:
            conn.close()

        link = f"https://t.me/{BOT_USERNAME}?start={code}"

        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "✅ File saved to private storage channel!\n\n"
                f"🔗 Share link:\n{link}"
            ),
        )

    except Exception:
        log.exception("File save failed")

        await message.reply_text(
            "⚠️ File save failed. Check storage channel "
            "permissions and database settings."
        )


# ============== USER ID COMMAND ==============

async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    if user and message:
        await message.reply_text(
            f"Your Telegram ID: {user.id}"
        )


# ============== BOT COMMANDS ==============

async def post_init(app: Application):
    await app.bot.set_my_commands([
        ("start", "Start the bot"),
        ("id", "Show your Telegram ID"),
    ])


# ============== ERROR HANDLER ==============

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    log.error(
        "Unhandled bot exception:",
        exc_info=context.error,
    )


# ============== MAIN ==============

async def main():
    if not TOKEN:
        raise RuntimeError(
            "config.py-তে BOT_TOKEN বসাও"
        )

    if not ADMIN_IDS:
        raise RuntimeError(
            "config.py-তে অন্তত একজন Admin ID যোগ করো"
        )

    if len(PRIVATE_CHANNELS) != 3:
        log.warning(
            "Expected 3 private channels, found %s",
            len(PRIVATE_CHANNELS),
        )

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(error_handler)

    # Join requests from configured private channels
    app.add_handler(
        ChatJoinRequestHandler(join_request_handler)
    )

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", myid))

    # Verify callback
    app.add_handler(
        CallbackQueryHandler(
            verify_callback,
            pattern=r"^verify:",
        )
    )

    # Admin file upload
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            admin_file,
        )
    )

    # ============== START BOT ==============

    async with app:
        await app.start()

        # 1. Green startup animation
        startup_animation()

        # 2. Start polling
        if app.updater:
            await app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES
            )

        log.info("TEAM DARK HUNTER Bot is running.")

        try:
            await asyncio.Event().wait()

        finally:
            if app.updater:
                await app.updater.stop()

            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())