from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta, timezone
from config import BOT_TOKEN, OPENAI_API_KEY, CHANNEL_USERNAME, MAX_AGE_DAYS
import openai
from io import BytesIO

# Ініціалізація OpenAI
openai.api_key = OPENAI_API_KEY

async def start(update, context):
    await update.message.reply_text("Gopaska Stylist Bot працює ✨")

# Завантажуємо фото з Telegram
def download_photo(file_id, context):
    new_file = context.bot.get_file(file_id)
    bio = BytesIO()
    new_file.download(out=bio)
    bio.seek(0)
    return bio

# Аналізуємо фото через GPT-4o-mini
def analyze_photo(photo_bytes):
    try:
        # Перетворюємо фото в base64, щоб GPT міг його аналізувати
        import base64
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

async def handle_channel_post(update, context):
    message = update.channel_post
    if not message or not message.photo:
        return

    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Старе фото, пропускаємо")
        return

    file_id = message.photo[-1].file_id
    print("📸 Нове фото (≤5 тижнів):", file_id)

    # Завантажуємо фото
    photo_bytes = download_photo(file_id, context)

    # Аналіз через GPT
    analysis = analyze_photo(photo_bytes)
    print("📝 Результат аналізу:", analysis)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    app.run_polling()

if __name__ == "__main__":
    main()
