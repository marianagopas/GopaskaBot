import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from datetime import datetime, timedelta, timezone
from config import BOT_TOKEN, OPENAI_API_KEY, CHANNEL_USERNAME, MAX_AGE_DAYS
import openai
from io import BytesIO
import base64

# Ініціалізація OpenAI
openai.api_key = OPENAI_API_KEY

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Gopaska Stylist Bot працює ✨")

# Завантаження фото асинхронно
async def download_photo(file_id, context: ContextTypes.DEFAULT_TYPE):
    new_file = await context.bot.get_file(file_id)
    bio = BytesIO()
    await new_file.download_to_memory(out=bio)
    bio.seek(0)
    return bio

# Асинхронний аналіз через OpenAI (виконуємо в executor)
async def analyze_photo(photo_bytes):
    loop = asyncio.get_running_loop()
    def blocking_call():
        try:
            photo_base64 = base64.b64encode(photo_bytes.read()).decode("utf-8")
            prompt = f"""
            Оціни це фото: {photo_base64}
            Визнач:
            1. Тип речі (плаття, блузка, штани, пальто тощо)
            2. Стиль (casual, класика, елегант, спорт тощо)
            3. Колір (основний колір)
            4. Сезон (весна, літо, осінь, зима)
            Відповідай у форматі: Тип: ..., Стиль: ..., Колір: ..., Сезон: ...
            """
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Помилка OpenAI: {e}"
    return await loop.run_in_executor(None, blocking_call)

# Хендлер для channel_post
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message or not message.photo:
        return

    # Перевіряємо канал
    if str(message.chat.username) != CHANNEL_USERNAME:
        return

    # Перевіряємо дату
    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Старе фото, пропускаємо")
        return

    file_id = message.photo[-1].file_id
    print("📸 Нове фото (≤5 тижнів):", file_id)

    # Завантаження фото
    photo_bytes = await download_photo(file_id, context)

    # Аналіз через OpenAI
    analysis = await analyze_photo(photo_bytes)
    print("📝 Результат аналізу:", analysis)

# Головна функція
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    print("✅ Бот запущено. Чекаю нових постів у каналі...")
    app.run_polling()

if __name__ == "__main__":
    main()
