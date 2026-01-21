import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from datetime import datetime, timedelta, timezone
from config import BOT_TOKEN, OPENAI_API_KEY, CHANNEL_USERNAME, MAX_AGE_DAYS
from io import BytesIO
from openai import OpenAI

# OpenAI client (НОВИЙ API)
client = OpenAI(api_key=OPENAI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Gopaska Stylist Bot працює ✨")

async def download_photo(file_id, context: ContextTypes.DEFAULT_TYPE):
    new_file = await context.bot.get_file(file_id)
    bio = BytesIO()
    await new_file.download_to_memory(out=bio)
    bio.seek(0)
    return bio

async def analyze_photo():
    """
    ⚠️ MVP-аналіз (без реального Vision)
    Потрібно для стабільного запуску
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ти професійний fashion-стиліст жіночого одягу."
                },
                {
                    "role": "user",
                    "content": (
                        "Перед тобою фото речі з італійського бутіка.\n"
                        "Визнач:\n"
                        "1. Тип речі\n"
                        "2. Стиль\n"
                        "3. Основний колір\n"
                        "4. Сезон\n\n"
                        "Відповідай строго у форматі:\n"
                        "Тип: ...\n"
                        "Стиль: ...\n"
                        "Колір: ...\n"
                        "Сезон: ..."
                    )
                }
            ],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ OpenAI error: {e}"

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message or not message.photo:
        return

    # Перевірка каналу
    if str(message.chat.username) != CHANNEL_USERNAME:
        return

    # Перевірка дати
    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Старе фото — пропущено")
        return

    print("📸 Нове фото (≤5 тижнів)")

    # Фото завантажуємо (поки не передаємо в GPT)
    await download_photo(message.photo[-1].file_id, context)

    analysis = await analyze_photo()
    print("📝 Результат аналізу:")
    print(analysis)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    print("✅ Gopaska Stylist Bot запущено")
    app.run_polling()

if __name__ == "__main__":
    main()
