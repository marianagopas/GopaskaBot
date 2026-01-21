from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta, timezone
from config import BOT_TOKEN, OPENAI_API_KEY, CHANNEL_USERNAME, MAX_AGE_DAYS
import openai

# Ініціалізація OpenAI
openai.api_key = OPENAI_API_KEY

async def start(update, context):
    await update.message.reply_text("Gopaska Stylist Bot працює ✨")

# Функція для аналізу фото через OpenAI
def analyze_photo(file_id):
    """
    Тимчасова реалізація: OpenAI не обробляє фото прямо через file_id,
    потрібно завантажити фото або URL. Тут просто приклад логіки.
    """
    # Для прикладу відправляємо запит до ChatGPT
    prompt = f"Аналізуй фото з file_id: {file_id}. Визнач тип речі, стиль, сезон та колір."
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        result = response.choices[0].message.content
    except Exception as e:
        result = f"Помилка OpenAI: {e}"
    
    return result

async def handle_channel_post(update, context):
    message = update.channel_post
    if not message or not message.photo:
        return

    # Перевірка дати
    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        print("⏭ Старе фото, пропускаємо")
        return

    # Беремо останнє фото (найбільше за розміром)
    file_id = message.photo[-1].file_id
    print("📸 Нове фото (≤5 тижнів):", file_id)

    # Аналіз через OpenAI
    analysis = analyze_photo(file_id)
    print("📝 Результат аналізу:", analysis)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
    app.run_polling()

if __name__ == "__main__":
    main()
