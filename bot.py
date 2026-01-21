import os
import psycopg2
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

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
CHANNEL_USERNAME = "Gopaska_boutique_Italyclothing"

# ================= OPENAI =================
client = OpenAI(api_key=OPENAI_API_KEY)

# ================= DATABASE =================
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def init_db():
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            telegram_file_id TEXT UNIQUE,
            category TEXT,
            style TEXT,
            color TEXT,
            season TEXT
        )
        """)
    print("✅ DB ready")

# ================= AI =================
ALLOWED = {
    "category": ["Футболка","Штани","Светр","Пальто"],
    "style": ["Casual","Classic","Sport"],
    "color": ["Чорний","Білий","Червоний","Синій"],
    "season": ["Весна","Літо","Осінь","Зима"],
}

async def get_photo_url(bot, file_id):
    file = await bot.get_file(file_id)
    return file.file_path

async def analyze_photo(photo_url):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": """
Вибери ТІЛЬКИ з варіантів:
Тип: Футболка, Штани, Светр, Пальто
Стиль: Casual, Classic, Sport
Колір: Чорний, Білий, Червоний, Синій
Сезон: Весна, Літо, Осінь, Зима

Формат:
Тип: ...
Стиль: ...
Колір: ...
Сезон: ...
"""}, 
                {"type": "input_image", "image_url": photo_url}
            ]
        }],
        temperature=0
    )

    text = response.output_text
    print("🧠 AI RAW:", text)

    data = {"category":None,"style":None,"color":None,"season":None}
    for line in text.splitlines():
        if "Тип:" in line: data["category"] = line.split(":",1)[1].strip()
        if "Стиль:" in line: data["style"] = line.split(":",1)[1].strip()
        if "Колір:" in line: data["color"] = line.split(":",1)[1].strip()
        if "Сезон:" in line: data["season"] = line.split(":",1)[1].strip()

    for k in data:
        if data[k] not in ALLOWED[k]:
            data[k] = None

    print("✅ PARSED:", data)
    return data

def save_item(file_id, data):
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO items (telegram_file_id, category, style, color, season)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """, (
            file_id,
            data["category"],
            data["style"],
            data["color"],
            data["season"],
        ))
    print("💾 SAVED")

# ================= FILTER STATE =================
user_filters = {}

def reset_filters(chat_id):
    user_filters[chat_id] = {
        "category": [],
        "style": [],
        "color": [],
        "season": [],
    }

# ================= MENUS =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👗 Всі образи", callback_data="show_all")],
        [InlineKeyboardButton("Тип", callback_data="filter:category")],
        [InlineKeyboardButton("Колір", callback_data="filter:color")],
        [InlineKeyboardButton("Стиль", callback_data="filter:style")],
        [InlineKeyboardButton("Сезон", callback_data="filter:season")],
        [InlineKeyboardButton("✅ Показати результат", callback_data="show_result")],
    ])

def filter_menu(chat_id, key):
    rows = []
    for v in ALLOWED[key]:
        mark = " ✅" if v in user_filters[chat_id][key] else ""
        rows.append([InlineKeyboardButton(v + mark, callback_data=f"toggle:{key}:{v}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="main")])
    return InlineKeyboardMarkup(rows)

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_filters(update.effective_chat.id)
    await update.message.reply_text("✨ Gopaska Stylist", reply_markup=main_menu())

async def channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or not msg.photo or msg.chat.username != CHANNEL_USERNAME:
        return

    file_id = msg.photo[-1].file_id
    photo_url = await get_photo_url(context.bot, file_id)

    data = await analyze_photo(photo_url)
    save_item(file_id, data)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id

    if chat_id not in user_filters:
        reset_filters(chat_id)

    d = q.data

    if d == "main":
        await q.edit_message_text("✨ Gopaska Stylist", reply_markup=main_menu())
        return

    if d.startswith("filter:"):
        key = d.split(":")[1]
        await q.edit_message_text("Вибери:", reply_markup=filter_menu(chat_id, key))
        return

    if d.startswith("toggle:"):
        _, key, value = d.split(":")
        if value in user_filters[chat_id][key]:
            user_filters[chat_id][key].remove(value)
        else:
            user_filters[chat_id][key].append(value)
        await q.edit_message_reply_markup(reply_markup=filter_menu(chat_id, key))
        return

    if d == "show_all":
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_file_id FROM items ORDER BY id DESC LIMIT 30")
            rows = cur.fetchall()
        await q.edit_message_text("👗 Всі образи")
        for r in rows:
            await context.bot.send_photo(chat_id, r[0])
        return

    if d == "show_result":
        sql = "SELECT telegram_file_id FROM items WHERE TRUE"
        params = []

        for key, values in user_filters[chat_id].items():
            if values:
                placeholders = ",".join(["%s"] * len(values))
                sql += f" AND {key} IN ({placeholders})"
                params.extend(values)

        print("🔎 SQL:", sql)
        print("🔎 PARAMS:", params)

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        if not rows:
            await q.edit_message_text("😔 Нічого не знайдено", reply_markup=main_menu())
            return

        await q.edit_message_text("🎯 Результат")
        for r in rows:
            await context.bot.send_photo(chat_id, r[0])

# ================= MAIN =================
def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        webhook_url=f"https://{RAILWAY_DOMAIN}",
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
