# -*- coding: utf-8 -*-
"""
ربات چت ناشناس تلگرام
قابلیت‌ها:
  ۱. هر کاربر یه شناسه‌ی یکتای عمومی می‌گیره (public_id)
  ۲. کاربرها با /chat <شناسه> می‌تونن با کاربر دیگه چت ناشناس شروع کنن
  ۳. کاربرها می‌تونن مستقیم به ادمین پیام بفرستن (/admin یا هر پیام معمولی موقعی که تو چت نیستن... اینجا با دستور مشخص انجام میشه)
  ۴. ادمین می‌تونه برای هر پیام یه دکمه‌ی شیشه‌ای "چت ناشناس" بسازه و به بقیه بده
  ۵. چت با /end یا دکمه‌ی "پایان چت" تموم می‌شه
"""

import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import database as db

# ---------- تنظیمات ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_TELEGRAM_ID")  # آیدی عددی تلگرام ادمین
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

# callback_data prefix ها
CB_CHAT_WITH = "chatwith:"   # چت با کاربری که ادمین معرفی کرده
CB_END_CHAT = "endchat"      # پایان چت با دکمه


# ---------- توابع کمکی ----------

def end_chat_keyboard():
    """دکمه‌ی پایان چت که زیر پیام‌های حین چت نشون داده می‌شه (اختیاری برای هر پیام)"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔴 پایان چت", callback_data=CB_END_CHAT)]]
    )


# ---------- دستورها ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    public_id = db.register_user(telegram_id)

    text = (
        "👋 خوش اومدی!\n\n"
        f"🆔 شناسه‌ی یکتای تو: `{public_id}`\n"
        "این شناسه رو می‌تونی به بقیه بدی تا باهات چت ناشناس کنن.\n\n"
        "📌 دستورات:\n"
        "/chat <شناسه> — شروع چت ناشناس با یه کاربر (مثلاً /chat 123456)\n"
        "/end — پایان چت فعلی\n"
        "/admin <پیام> — ارسال پیام به ادمین\n"
        "/myid — نمایش دوباره‌ی شناسه‌ی خودت"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    public_id = db.register_user(telegram_id)
    await update.message.reply_text(f"🆔 شناسه‌ی تو: `{public_id}`", parse_mode=ParseMode.MARKDOWN)


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع چت ناشناس با وارد کردن دستی شناسه‌ی طرف مقابل: /chat 123456"""
    telegram_id = update.effective_user.id
    db.register_user(telegram_id)  # مطمئن می‌شیم خودش هم ثبت‌نامه

    if not context.args:
        await update.message.reply_text("لطفاً شناسه‌ی کاربر رو هم بنویس. مثال:\n/chat 123456")
        return

    target_public_id = context.args[0].strip()
    target_telegram_id = db.get_telegram_id_by_public_id(target_public_id)

    if target_telegram_id is None:
        await update.message.reply_text("❌ کاربری با این شناسه پیدا نشد.")
        return

    if target_telegram_id == telegram_id:
        await update.message.reply_text("❌ نمی‌تونی با خودت چت کنی!")
        return

    # اگه از قبل تو یه چت دیگه‌ای، ببندیمش
    db.end_chat_session(telegram_id)
    db.end_chat_session(target_telegram_id)

    db.start_chat_session(telegram_id, target_telegram_id)

    await update.message.reply_text(
        "✅ چت ناشناس شروع شد! هر پیامی بفرستی، بدون فاش شدن هویتت به طرف مقابل می‌رسه.\n"
        "برای پایان چت: /end",
        reply_markup=end_chat_keyboard(),
    )

    try:
        await context.bot.send_message(
            chat_id=target_telegram_id,
            text=(
                "🔔 یه کاربر ناشناس باهات چت شروع کرد!\n"
                "هر چی بنویسی رو براش می‌فرستیم، بدون اینکه هویتت لو بره.\n"
                "برای پایان چت: /end"
            ),
            reply_markup=end_chat_keyboard(),
        )
    except Exception as e:
        logger.warning(f"نتونستم به {target_telegram_id} پیام بدم: {e}")


async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    partner_id = db.end_chat_session(telegram_id)

    if partner_id is None:
        await update.message.reply_text("در حال حاضر تو هیچ چتی نیستی.")
        return

    await update.message.reply_text("🔴 چت پایان یافت.")
    try:
        await context.bot.send_message(chat_id=partner_id, text="🔴 طرف مقابل چت رو تموم کرد.")
    except Exception as e:
        logger.warning(f"نتونستم پایان چت رو به {partner_id} اطلاع بدم: {e}")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به ادمین: /admin <متن پیام>"""
    telegram_id = update.effective_user.id
    db.register_user(telegram_id)

    if not ADMIN_ID:
        await update.message.reply_text("⚠️ آیدی ادمین تنظیم نشده. به سازنده‌ی ربات اطلاع بده.")
        return

    if not context.args:
        await update.message.reply_text("لطفاً پیامت رو بنویس. مثال:\n/admin سلام، یه سوال داشتم")
        return

    message_text = " ".join(context.args)
    public_id = db.get_public_id(telegram_id)

    # توکن یکتا برای این کاربر می‌سازیم تا ادمین بتونه دکمه‌ی چت باهاش رو بسازه
    token = db.create_admin_contact_token(telegram_id)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 چت ناشناس با این کاربر", callback_data=f"{CB_CHAT_WITH}{token}")]]
    )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📩 پیام جدید از کاربر (شناسه: {public_id})\n\n"
            f"{message_text}"
        ),
        reply_markup=keyboard,
    )

    await update.message.reply_text("✅ پیامت برای ادمین ارسال شد.")


# ---------- دکمه‌های شیشه‌ای ----------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    clicking_user_id = query.from_user.id
    db.register_user(clicking_user_id)

    data = query.data

    if data == CB_END_CHAT:
        partner_id = db.end_chat_session(clicking_user_id)
        if partner_id is None:
            await query.edit_message_text("در حال حاضر تو هیچ چتی نیستی.")
            return
        await query.edit_message_text("🔴 چت پایان یافت.")
        try:
            await context.bot.send_message(chat_id=partner_id, text="🔴 طرف مقابل چت رو تموم کرد.")
        except Exception as e:
            logger.warning(f"نتونستم پایان چت رو به {partner_id} اطلاع بدم: {e}")
        return

    if data.startswith(CB_CHAT_WITH):
        token = data[len(CB_CHAT_WITH):]
        target_telegram_id = db.resolve_admin_contact_token(token)

        if target_telegram_id is None:
            await query.message.reply_text("❌ این دکمه دیگه معتبر نیست.")
            return

        if target_telegram_id == clicking_user_id:
            await query.message.reply_text("❌ این پیام خودتـه، نمی‌تونی با خودت چت کنی!")
            return

        # چت قبلی هر دو طرف رو می‌بندیم
        db.end_chat_session(clicking_user_id)
        db.end_chat_session(target_telegram_id)

        db.start_chat_session(clicking_user_id, target_telegram_id)

        await query.message.reply_text(
            "✅ چت ناشناس شروع شد! هر چی بنویسی به اون کاربر می‌رسه.\n"
            "برای پایان چت: /end",
            reply_markup=end_chat_keyboard(),
        )

        try:
            await context.bot.send_message(
                chat_id=target_telegram_id,
                text=(
                    "🔔 یه کاربر ناشناس باهات چت شروع کرد!\n"
                    "برای پایان چت: /end"
                ),
                reply_markup=end_chat_keyboard(),
            )
        except Exception as e:
            logger.warning(f"نتونستم به {target_telegram_id} پیام بدم: {e}")
        return


# ---------- فوروارد پیام‌های معمولی حین چت ----------

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هر پیام متنی/عکس/ویس معمولی که کاربر می‌فرسته (و دستور نیست) رو،
    اگه تو یه چت فعال باشه، برای طرف مقابل فوروارد می‌کنه بدون فاش کردن هویت.
    """
    telegram_id = update.effective_user.id
    db.register_user(telegram_id)

    partner_id = db.get_active_partner(telegram_id)

    if partner_id is None:
        await update.message.reply_text(
            "❕ تو الان تو هیچ چتی نیستی.\n"
            "برای شروع چت: /chat <شناسه>\n"
            "برای پیام به ادمین: /admin <متن>"
        )
        return

    try:
        # از copy_message استفاده می‌کنیم تا همه نوع پیام (عکس، ویس، متن، ویدیو) پشتیبانی بشه
        # و به صورت خودکار بدون نمایش نام فرستنده ارسال بشه
        await context.bot.copy_message(
            chat_id=partner_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
    except Exception as e:
        logger.warning(f"خطا در ارسال پیام به {partner_id}: {e}")
        await update.message.reply_text("⚠️ مشکلی در ارسال پیام پیش اومد. شاید طرف مقابل ربات رو بلاک کرده.")


# ---------- اجرای ربات (حالت Webhook برای Render Web Service) ----------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده!")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("chat", chat_command))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("admin", admin_command))

    app.add_handler(CallbackQueryHandler(button_handler))

    # هر پیام دیگه‌ای (متن، عکس، ویس و ...) که دستور نیست
    app.add_handler(MessageHandler(~filters.COMMAND, relay_message))

    # --- تنظیمات مخصوص Webhook ---
    # Render یه پورت از طریق متغیر محیطی PORT بهمون می‌ده
    port = int(os.environ.get("PORT", "8443"))

    # آدرس عمومی سرویس روی Render (خودکار توسط Render ست می‌شه)
    # مثلاً: https://my-bot.onrender.com
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        raise RuntimeError(
            "متغیر RENDER_EXTERNAL_URL پیدا نشد. این باید خودکار توسط Render ست بشه؛ "
            "اگه محلی اجرا می‌کنی، به‌جاش از bot_polling.py استفاده کن."
        )

    # مسیر webhook رو با خودِ توکن می‌سازیم تا حدس زدنش برای بقیه سخت باشه
    webhook_path = f"/webhook/{BOT_TOKEN}"
    webhook_url = f"{render_url}{webhook_path}"

    logger.info(f"ربات در حال اجراست (webhook mode) روی پورت {port}...")
    logger.info(f"آدرس webhook: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path,
        webhook_url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
