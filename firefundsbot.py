import re
import json
import math
import os
import asyncio
import uvicorn
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram.utils.markdown import hbold
from aiogram import F
from aiohttp import web

# Инициализация бота и диспетчера
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Пример: "https://your-app.onrender.com"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Файл для хранения chat_id пользователей
CHAT_ID_FILE = "chat_ids.json"

# Функция для загрузки chat_id пользователей из файла.
def load_chat_ids():
    try:
        with open(CHAT_ID_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Функция для сохранения chat_id пользователя в файл.
def save_chat_id(username, chat_id):
    data = load_chat_ids()
    data[f"@{username}"] = chat_id  # Добавляем знак @ перед username
    with open(CHAT_ID_FILE, "w") as file:
        json.dump(data, file)

# Функция для обработки входного текста, выделяя активности и участников.
# Ожидается формат: "За что - Стоимость - Кто оплатил - За кого оплатил"
def process_text(message_text):
    activities = []
    participants = []
    
    parts = message_text.split("Участники:")
    activities_text = parts[0].strip()
    participants_text = parts[1].strip() if len(parts) > 1 else ""
    
    # Обработка строк активностей
    activity_lines = activities_text.splitlines()
    for line in activity_lines:
        match = re.match(r"([A-Za-zА-Яа-яЁё\s]+)\s*-\s*(\d+)\s*-\s*(@\w+)\s*-\s*(.+)", line)
        if match:
            activity_name = match.group(1).strip()
            amount = int(match.group(2))
            payer = match.group(3).strip()
            for_whom = match.group(4).strip().lower()  # Приводим к нижнему регистру для сравнения
            activities.append({
                "name": activity_name,
                "amount": amount,
                "payer": payer,
                "for_whom": for_whom
            })
    
    participants = participants_text.splitlines()
    return activities, participants

# Функция для расчета платежей.
# Алгоритм:
# 1. Для каждой активности: 
#    - Если "for_whom" равен "all", стоимость делится поровну между всеми участниками.
#    - Иначе, сумма начисляется только тому участнику, чей username указан.
# 2. Отдельно суммируется, сколько каждый участник оплатил.
# 3. Баланс = (оплачено) - (ожидаемая сумма).
def calculate_payments(activities, participants):
    expected = {participant: 0 for participant in participants}
    paid = {participant: 0 for participant in participants}
    
    for activity in activities:
        amount = activity["amount"]
        payer = activity["payer"]
        target = activity["for_whom"]  # уже в нижнем регистре
        if target == "all":
            share = math.floor(amount / len(participants))
            for participant in participants:
                expected[participant] += share
        else:
            for participant in participants:
                if participant.lower() == target:
                    expected[participant] += amount
        if payer in paid:
            paid[payer] += amount
    
    payments = {}
    for participant in participants:
        balance = paid[participant] - expected[participant]
        payments[participant] = balance
    return payments

# Функция для отправки информации об оплатах пользователям.
async def send_payment_info(message: Message, payments):
    chat_ids = load_chat_ids()
    for participant, balance in payments.items():
        if balance > 0:
            text = f"{participant}, вам должны вернуть: {balance}\nЗапрашивайте у @master_bahrom"
        else:
            text = f"Это были супер активности! Очень рад, что вы смогли к нам присоединиться\n{participant}, стоимость твоей активности составляет: {-balance}\nПеревести можете по ссылке - https://cpay.me/971547437161?amount={-balance}"
        
        # Логирование отправки
        if participant in chat_ids:
            await message.answer(f"Отправляю сообщение {participant} в чат {chat_ids[participant]}: {text}")
            await bot.send_message(chat_ids[participant], text)
        else:
            await message.answer(f"Не найден chat_id для {participant}, сообщение не отправлено.")
        await message.answer(text)

# Обработчик команды /start.
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Отправьте текст с активностями и участниками для расчёта.")

# Обработчик команды /me для регистрации пользователя.
@dp.message(Command("me"))
async def register_user(message: Message):
    save_chat_id(message.from_user.username, message.chat.id)
    await message.answer(
        "Спасибо, мы получили все ваши данные и теперь можем писать от вашего имени вашим друзьям и просить переводить деньги 😂\n\n"
        "ЭТО ШУТКА!\n\n"
        "Мы просто записали ваш логин и номер этого чата, чтобы понимать кому и куда отправлять сообщение ☺️"
    )

# Обработчик текстовых сообщений для расчёта платежей.
@dp.message()
async def handle_text(message: Message):
    text = message.text
    activities, participants = process_text(text)
    payments = calculate_payments(activities, participants)
    await send_payment_info(message, payments)

# FastAPI приложение для обработки вебхуков.
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "I'm alive!"}

# Эндпоинт для получения обновлений от Telegram.
@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    update_data = await request.json()
    update = Update.model_validate(update_data)
    # Обрабатываем обновление асинхронно.
    asyncio.create_task(dp.feed_update(bot, update))
    return {"ok": True}

# При запуске приложения устанавливаем вебхук.
@app.on_event("startup")
async def on_startup():
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.delete_webhook()
    await bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

# При завершении работы удаляем вебхук.
@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
