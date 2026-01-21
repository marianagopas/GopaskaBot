# Використовуємо стабільний Python 3.10
FROM python:3.10-slim

WORKDIR /app

# Копіюємо файли
COPY . .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python3", "bot.py"]
