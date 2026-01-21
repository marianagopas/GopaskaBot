import os
import psycopg2
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI

# ===================== CONFIG =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

CHANNEL_USERNAME = "Gopaska_boutique_Italyclothing"
MAX_AGE_DAYS = 35

# ===================== OPENAI =====================
client = OpenAI(api_key=OPENAI_API_KEY)

# ===================== DATABASE =====================
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def create_table():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                telegram_file_id TEXT UNIQUE NOT NULL,
                channel_message_id BIGINT,
                photo_date TIMESTAMP,
                category TEXT,
                style TEXT,
                season TEXT,
                color TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
    print("✅ Таблиця items готова")

def cleanup_old_items():
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM items
            WHERE photo_date < NOW() - INTERVAL '35 days'
        """)
    print("🧹 Старі фото (35+ днів) видалені")

def save_item(file_id, message_id, photo_date, ai_data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO items (
                telegram_file_id,
                channel_message_id,
                photo_date,
                category,
                style,
                season,
                color,
                description
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (telegram_file_id) DO NOTHING
        """, (
            file_id,
            message_id,
            photo_date,
            ai_data.get("category"),
            ai_data.get("style"),
            ai_data.get("season"),
            ai_data.get("color"),
            ai_data.get("description")
        ))

# ===================== AI ANALYSIS =====================
async def analyze_photo():
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ти fashion-стиліст жіночого італійського одягу."
                },
                {
                    "role": "user",
                    "content": (
                        "Визнач для речі:\n"
                        "Тип\nСтиль\nКолір\nСезон\n\n"
                        "Формат відповіді:\n"
                        "Тип: ...\nСтиль: ...\nКолір: ...\nСезон: ..."
                    )
                }
            ],
            temperature=0
        )
        text = response.choices[0].message.content

        data = {"category": None, "style": None, "color": None, "season": None, "description": text}
        for line in text.splitlines():
            if line.startswith("Тип:"):
                data["category"] = line.replace("Тип:", "").strip()
            elif line.startswith("Стиль:"):
                data["style"] = line.replace("Стиль:", "").strip()
            elif line.startswith("Колір:"):
                data["color"] = line.replace("Колір:", "").strip()
            elif line.startswith("Сезон:"):
                data["season"] = line.replace("Сезон:", "").strip()
        return data
    except Exception as e:
        return {"description": f"❌ OpenAI error: {e}"}

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Показати всі образи", callback_data="show_all")],
        [InlineKeyboardButton("Фільтр за типом", callback_data="filter_category")],
        [InlineKeyboardButton("Фільтр за кольором", callback_data="filter_color")],
        [InlineKeyboardButton("Фільтр за стилем", callback_data="filter_style")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✨ Gopaska Stylist Bot працює", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("📩 Отримано подію від Telegram")
    message = update.channel_post
    if not message or not message.photo:
        return
    if message.chat.username != CHANNEL_USERNAME:
        return
    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Фото старше 35 днів — пропущено")
        return
    print("📸 Нове фото з каналу")
    file_id = message.photo[-1].file_id
    ai_data = await analyze_photo()
    print("📝 Аналіз:", ai_data.get("description"))
    save_item(file_id=file_id, message_id=message.message_id, photo_date=message.date, ai_data=ai_data)

# ===================== CALLBACK BUTTONS =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_all":
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items ORDER BY created_at DESC LIMIT 10")
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text("Немає збережених образів 😔")
            return
        for row in rows:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=row[0])

    elif data == "filter_category":
        keyboard = [
            [InlineKeyboardButton("Футболка", callback_data="category:Футболка")],
            [InlineKeyboardButton("Штани", callback_data="category:Штани")],
            [InlineKeyboardButton("Светр", callback_data="category:Светр")],
            [InlineKeyboardButton("Пальто", callback_data="category:Пальто")],
        ]
        await query.edit_message_text("Виберіть тип:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("category:"):
        cat = data.split(":",1)[1]
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items WHERE category=%s ORDER BY created_at DESC LIMIT 10", (cat,))
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text(f"Немає предметів типу {cat} 😔")
            return
        await query.edit_message_text(f"Образи типу {cat}:")
        for row in rows:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=row[0])

    elif data == "filter_color":
        keyboard = [
            [InlineKeyboardButton("Червоний", callback_data="color:Червоний")],
            [InlineKeyboardButton("Синій", callback_data="color:Синій")],
            [InlineKeyboardButton("Чорний", callback_data="color:Чорний")],
            [InlineKeyboardButton("Білий", callback_data="color:Білий")],
        ]
        await query.edit_message_text("Виберіть колір:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("color:"):
        col = data.split(":",1)[1]
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items WHERE color=%s ORDER BY created_at DESC LIMIT 10", (col,))
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text(f"Немає предметів кольору {col} 😔")
            return
        await query.edit_message_text(f"Образи кольору {col}:")
        for row in rows:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=row[0])

    elif data == "filter_style":
        keyboard = [
            [InlineKeyboardButton("Casual", callback_data="style:Casual")],
            [InlineKeyboardButton("Classic", callback_data="style:Classic")],
            [InlineKeyboardButton("Sport", callback_data="style:Sport")],
        ]
        await query.edit_message_text("Виберіть стиль:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("style:"):
        style = data.split(":",1)[1]
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items WHERE style=%s ORDER BY created_at DESC LIMIT 10", (style,))
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text(f"Немає предметів стилю {style} 😔")
            return
        await query.edit_message_text(f"Образи стилю {style}:")
        for row in rows:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=row[0])

# ===================== MAIN (WEBHOOK) =====================
def main():
    create_table()
    cleanup_old_items()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    app.add_handler(CallbackQueryHandler(button_handler))
    PORT = int(os.getenv("PORT", 8080))
    WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
    print("🌍 Webhook URL:", WEBHOOK_URL)
    print("✅ Gopaska Stylist Bot запущено через WEBHOOK")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
