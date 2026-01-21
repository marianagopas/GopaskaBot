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
            ai_data.get("category", "").strip().lower() if ai_data.get("category") else None,
            ai_data.get("style", "").strip().lower() if ai_data.get("style") else None,
            ai_data.get("season", "").strip().lower() if ai_data.get("season") else None,
            ai_data.get("color", "").strip().lower() if ai_data.get("color") else None,
            ai_data.get("description")
        ))

# ===================== AI ANALYSIS =====================
async def analyze_photo():
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти fashion-стиліст жіночого італійського одягу."},
                {"role": "user", "content": (
                    "Визнач для речі:\n"
                    "Тип\nСтиль\nКолір\nСезон\n\n"
                    "Формат відповіді:\n"
                    "Тип: ...\nСтиль: ...\nКолір: ...\nСезон: ..."
                )}
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

# ===================== USER FILTERS =====================
user_filters = {}  # key: chat_id, value: dict з вибраними фільтрами

def reset_filters(chat_id):
    user_filters[chat_id] = {"category": [], "style": [], "color": [], "season": []}

# ===================== MENU =====================
def build_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Показати всі образи", callback_data="show_all")],
        [InlineKeyboardButton("Фільтр за типом", callback_data="filter_category")],
        [InlineKeyboardButton("Фільтр за кольором", callback_data="filter_color")],
        [InlineKeyboardButton("Фільтр за стилем", callback_data="filter_style")],
        [InlineKeyboardButton("Фільтр за сезоном", callback_data="filter_season")],
        [InlineKeyboardButton("Показати результати", callback_data="show_results")]
    ])

def build_filter_keyboard(chat_id, filter_type, options):
    keyboard = []
    for opt in options:
        mark = " ✅" if opt.lower() in [v.lower() for v in user_filters[chat_id][filter_type]] else ""
        keyboard.append([InlineKeyboardButton(opt + mark, callback_data=f"{filter_type}:{opt}")])
    # Додаємо кнопки "Назад" та "Головне меню"
    keyboard.append([InlineKeyboardButton("Назад", callback_data="main_menu")])
    keyboard.append([InlineKeyboardButton("Головне меню", callback_data="main_menu_clear")])
    return InlineKeyboardMarkup(keyboard)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    reset_filters(chat_id)
    await update.message.reply_text("✨ Gopaska Stylist Bot працює", reply_markup=build_main_keyboard())

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message or not message.photo:
        return
    if message.chat.username != CHANNEL_USERNAME:
        return
    now = datetime.now(timezone.utc)
    if now - message.date > timedelta(days=MAX_AGE_DAYS):
        return
    file_id = message.photo[-1].file_id
    ai_data = await analyze_photo()
    save_item(file_id=file_id, message_id=message.message_id, photo_date=message.date, ai_data=ai_data)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    if chat_id not in user_filters:
        reset_filters(chat_id)
    data = query.data

    # Головне меню (залишаємо фільтри)
    if data == "main_menu":
        await query.edit_message_text("✨ Gopaska Stylist Bot працює", reply_markup=build_main_keyboard())
        return

    # Головне меню з очищенням всіх фільтрів
    if data == "main_menu_clear":
        reset_filters(chat_id)
        await query.edit_message_text("✨ Gopaska Stylist Bot працює", reply_markup=build_main_keyboard())
        return

    # Показати всі фото
    if data == "show_all":
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items ORDER BY created_at DESC LIMIT 50")
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text("Немає збережених образів 😔", reply_markup=build_main_keyboard())
            return
        await query.edit_message_text("🎨 Всі образи:")
        for row in rows:
            await context.bot.send_photo(chat_id=chat_id, photo=row[0])
        return

    # Фільтри
    if data.startswith("filter_"):
        filter_type = data.split("_")[1]
        options = []
        if filter_type == "category":
            options = ["Футболка","Штани","Светр","Пальто"]
        elif filter_type == "color":
            options = ["Червоний","Синій","Чорний","Білий"]
        elif filter_type == "style":
            options = ["Casual","Classic","Sport"]
        elif filter_type == "season":
            options = ["Весна","Літо","Осінь","Зима"]
        await query.edit_message_text(
            f"Виберіть {filter_type} (можна кілька):",
            reply_markup=build_filter_keyboard(chat_id, filter_type, options)
        )
        return

    # Додавання фільтра
    if ":" in data:
        filter_type, value = data.split(":",1)
        if value.lower() not in [v.lower() for v in user_filters[chat_id][filter_type]]:
            user_filters[chat_id][filter_type].append(value)
        # Оновлюємо меню з позначкою ✅
        options = []
        if filter_type == "category":
            options = ["Футболка","Штани","Светр","Пальто"]
        elif filter_type == "color":
            options = ["Червоний","Синій","Чорний","Білий"]
        elif filter_type == "style":
            options = ["Casual","Classic","Sport"]
        elif filter_type == "season":
            options = ["Весна","Літо","Осінь","Зима"]
        await query.edit_message_text(
            f"Виберіть {filter_type} (можна кілька):",
            reply_markup=build_filter_keyboard(chat_id, filter_type, options)
        )
        return

    # Показати результати
    if data == "show_results":
        filters = user_filters[chat_id]
        query_text = "SELECT telegram_file_id FROM items WHERE TRUE"
        params = []
        for key, vals in filters.items():
            if vals:
                query_text += f" AND LOWER({key}) = ANY(%s)"
                params.append([v.lower() for v in vals])
        query_text += " ORDER BY created_at DESC LIMIT 50"
        with conn.cursor() as cur:
            cur.execute(query_text, params)
            rows = cur.fetchall()
        if not rows:
            await query.edit_message_text("Немає результатів для обраних фільтрів 😔", reply_markup=build_main_keyboard())
            return
        await query.edit_message_text("🎯 Результати для ваших фільтрів:")
        for row in rows:
            await context.bot.send_photo(chat_id=chat_id, photo=row[0])
        return

# ===================== MAIN =====================
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
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
