"""
ماژول دیتابیس ربات
- روی PostgreSQL (برای Render) و SQLite (برای تست محلی) کار می‌کنه
- تشخیص خودکار: اگه DATABASE_URL ست شده باشه از Postgres استفاده می‌کنه، وگرنه SQLite محلی
"""

import os
import sqlite3
import random
import string
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")  # روی Render این ست می‌شه
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


@contextmanager
def get_conn():
    """یه connection به دیتابیس می‌ده (Postgres یا SQLite بسته به محیط)"""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        try:
            yield conn
        finally:
            conn.close()
    else:
        conn = sqlite3.connect("bot_database.db")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def _ph():
    """placeholder مناسب برای هر دیتابیس (%s برای Postgres، ? برای SQLite)"""
    return "%s" if USE_POSTGRES else "?"


def init_db():
    """جدول‌های لازم رو در صورت نبود می‌سازه"""
    with get_conn() as conn:
        cur = conn.cursor()

        if USE_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    public_id TEXT UNIQUE NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_chats (
                    user_id BIGINT PRIMARY KEY,
                    partner_id BIGINT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_contact_tokens (
                    token TEXT PRIMARY KEY,
                    target_telegram_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    public_id TEXT UNIQUE NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_chats (
                    user_id INTEGER PRIMARY KEY,
                    partner_id INTEGER NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_contact_tokens (
                    token TEXT PRIMARY KEY,
                    target_telegram_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()


def _generate_public_id():
    """یه شناسه عددی ۶ رقمی یکتا برای کاربر می‌سازه"""
    return "".join(random.choices(string.digits, k=6))


def register_user(telegram_id: int) -> str:
    """
    کاربر رو در دیتابیس ثبت می‌کنه (اگه از قبل نبوده) و public_id رو برمی‌گردونه.
    اگه از قبل ثبت بوده، همون public_id قبلی رو برمی‌گردونه.
    """
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT public_id FROM users WHERE telegram_id = {ph}", (telegram_id,))
        row = cur.fetchone()
        if row:
            return row[0]

        # تولید public_id یکتا (تکرار تا زمانی که یکتا بشه)
        while True:
            new_id = _generate_public_id()
            cur.execute(f"SELECT 1 FROM users WHERE public_id = {ph}", (new_id,))
            if not cur.fetchone():
                break

        cur.execute(
            f"INSERT INTO users (telegram_id, public_id) VALUES ({ph}, {ph})",
            (telegram_id, new_id),
        )
        conn.commit()
        return new_id


def get_telegram_id_by_public_id(public_id: str):
    """با شناسه‌ی عمومی، آیدی واقعی تلگرام کاربر رو پیدا می‌کنه"""
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT telegram_id FROM users WHERE public_id = {ph}", (public_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_public_id(telegram_id: int):
    """با آیدی تلگرام، شناسه‌ی عمومی کاربر رو پیدا می‌کنه"""
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT public_id FROM users WHERE telegram_id = {ph}", (telegram_id,))
        row = cur.fetchone()
        return row[0] if row else None


def start_chat_session(user_a: int, user_b: int):
    """یه چت ناشناس دوطرفه بین دو کاربر باز می‌کنه"""
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        # اول هر چت قبلی این دو نفر رو پاک می‌کنیم تا تداخل نشه
        cur.execute(f"DELETE FROM active_chats WHERE user_id IN ({ph}, {ph})", (user_a, user_b))
        cur.execute(
            f"INSERT INTO active_chats (user_id, partner_id) VALUES ({ph}, {ph})",
            (user_a, user_b),
        )
        cur.execute(
            f"INSERT INTO active_chats (user_id, partner_id) VALUES ({ph}, {ph})",
            (user_b, user_a),
        )
        conn.commit()


def get_active_partner(telegram_id: int):
    """اگه کاربر توی یه چت ناشناس فعاله، آیدی طرف مقابلش رو برمی‌گردونه"""
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT partner_id FROM active_chats WHERE user_id = {ph}", (telegram_id,))
        row = cur.fetchone()
        return row[0] if row else None


def end_chat_session(telegram_id: int):
    """چت ناشناس فعلی کاربر رو (برای هر دو طرف) پاک می‌کنه. آیدی طرف مقابل رو برمی‌گردونه."""
    partner_id = get_active_partner(telegram_id)
    if partner_id is None:
        return None

    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM active_chats WHERE user_id IN ({ph}, {ph})", (telegram_id, partner_id))
        conn.commit()
    return partner_id


def create_admin_contact_token(target_telegram_id: int) -> str:
    """
    برای دکمه‌ی شیشه‌ای که ادمین می‌سازه، یه توکن یکتا می‌سازه که
    به آیدی واقعی کاربر (کسی که به ادمین پیام داده) اشاره می‌کنه.
    این توکن تو callback_data دکمه قرار می‌گیره، نه خودِ آیدی -
    که کاربرا نتونن آیدی عددی تلگرام همدیگه رو ببینن.
    """
    token = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO admin_contact_tokens (token, target_telegram_id) VALUES ({ph}, {ph})",
            (token, target_telegram_id),
        )
        conn.commit()
    return token


def resolve_admin_contact_token(token: str):
    """با توکن، آیدی واقعی تلگرام کاربر هدف رو پیدا می‌کنه"""
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT target_telegram_id FROM admin_contact_tokens WHERE token = {ph}", (token,)
        )
        row = cur.fetchone()
        return row[0] if row else None
