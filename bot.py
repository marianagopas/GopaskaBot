import os
import psycopg2
from datetime import datetime, timedelta, timezone
from io import BytesIO
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
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
    create_table_sql = """
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
    """
    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        print("✅ Таблиця 'items' створена (або вже існує)")

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

def cleanup_old_items():
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM items
            WHERE photo_date < NOW() - INTERVAL '35 days'
        """)
        print("🧹 Старі записи видалено (35+ днів)")

# ===================== BOT =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Gopaska Stylist Bot працює ✨")

async def download_photo(file_id, context: ContextTypes.DEFAULT_TYPE):
    new_file = await context.bot.get_file(file_id)
    bio = BytesIO()
    await new_file.download_to_memory(out=bio)
    bio.seek(0)
    return bio

async def analyze_photo():
    """MVP аналіз через OpenAI"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти професійний fashion-стиліст жіночого одягу."},
                {"role": "user", "content": (
                    "Перед тобою фото речі з італійського бутіка.\n"
                    "Визнач:\n"
                    "1. Тип речі\n2. Стиль\n3. Основний колір\n4. Сезон\n"
                    "Відповідай строго у форматі:\n"
                    "Тип: ...\nСтиль: ...\nКолір: ...\nСезон: ..."
                )}
            ],
            temperature=0
        )
        result_text = response.choices[0].message.content
        ai_data = {"category": None, "style": None, "color": None, "season": None, "description": result_text}
        for line in result_text.splitlines():
            if line.startswith("Тип:"):
                ai_data["category"] = line.split("Тип:")[1].strip()
            elif line.startswith("Стиль:"):
                ai_data["style"] = line.split("Стиль:")[1].strip()
            elif line.startswith("Колір:"):
                ai_data["color"] = line.split("Колір:")[1].strip()
            elif line.startswith("Сезон:"):
                ai_data["season"] = line.split("Сезон:")[1].strip()
        return ai_data
    except Exception as e:
        return {"description": f"❌ OpenAI error: {e}"}

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message or not message.photo:
        return

    if str(message.chat.username) != CHANNEL_USERNAME:
        return

    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Старе фото — пропущено")
        return

    print("📸 Нове фото (≤5 тижнів)")

    file_id = message.photo[-1].file_id
    await download_photo(file_id, context)
    ai_data = await analyze_photo()

    print("📝 Результат аналізу:")
    print(ai_data["description"])

    save_item(file_id, message.message_id, message.date, ai_data)

# ===================== MAIN =====================
def main():
    create_table()
    cleanup_old_items()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    print("✅ Gopaska Stylist Bot запущено")
    # Polling з drop_pending_updates, щоб не було конфліктів
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
