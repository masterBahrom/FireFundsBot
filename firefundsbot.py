import re
import json
import math
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram import F
import asyncio
import os
from aiohttp import web

# Инициализация бота
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


bot = Bot(token=API_TOKEN)
dp = Dispatcher()
app = FastAPI()

# Устанавливаем Webhook
#@app.on_event("startup")
#async def on_startup():
   # await bot.set_webhook(WEBHOOK_URL)

# Обрабатываем входящие обновления
@app.post("/")
async def handle_update(update: dict):
    telegram_update = Update.model_validate(update)
    await dp.feed_update(bot, telegram_update)
    
# Файл для хранения chat_id пользователей
CHAT_ID_FILE = "chat_ids.json"

# Загружает chat_id пользователей из файла.
def load_chat_ids():
    try:
        with open(CHAT_ID_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
# Сохраняет chat_id пользователя в файл.
def save_chat_id(username, chat_id):
    data = load_chat_ids()
    data[f"@{username}"] = chat_id  
    with open(CHAT_ID_FILE, "w") as file:
        json.dump(data, file)
      
#  Обрабатывает входной текст, выделяя активности и участников.
def process_text(message_text):
    activities = []
    participants = []
    
    parts = message_text.split('Участники:')
    activities_text = parts[0].strip()
    participants_text = parts[1].strip() if len(parts) > 1 else ""
    
    activity_lines = activities_text.splitlines()
    for line in activity_lines:
        match = re.match(r'([A-Za-zА-Яа-яЁё\s]+) - (\d+) - (@\w+)', line)
        if match:
            activity_name = match.group(1).strip()
            amount = int(match.group(2))
            payer = match.group(3).strip()
            activities.append({"name": activity_name, "amount": amount, "payer": payer})
    
    participants = participants_text.splitlines()
    return activities, participants
  
#Рассчитывает, сколько должен или кому должны участники.
def calculate_payments(activities, participants):
    total_sum = sum([activity['amount'] for activity in activities])
    num_participants = len(participants)
    share_per_participant = math.floor(total_sum / num_participants)
    
    payments = {}
    for participant in participants:
        total_paid = sum([activity['amount'] for activity in activities if activity['payer'] == participant])
        balance = total_paid - share_per_participant
        payments[participant] = -balance
    
    return payments

# Отправляет пользователям информацию об их задолженностях.
async def send_payment_info(message: Message, payments):
    chat_ids = load_chat_ids()
    for participant, amount in payments.items():
        if amount > 0:
            text = f"{participant}, вы должны оплатить: {amount}\nПеревести можете по ссылке - https://cpay.me/971547437161?amount={amount} или на банковский счет - https://t.me/c/2053760794/1/3164"
        else:
            text = f"{participant}, вам должны вернуть: {-amount}\nЗапрашивайте у @master_bahrom"
        
        if participant in chat_ids:
            await bot.send_message(chat_ids[participant], text)
        else:
            await message.answer(f"Не найден chat_id для {participant}, сообщение не отправлено.")

        await message.answer(text)

# Обрабатывает команду /start.
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Отправьте текст с активностями и участниками для расчёта.")

# Регистрирует пользователя и сохраняет его chat_id.
@dp.message(Command("me"))
async def register_user(message: Message):
    save_chat_id(message.from_user.username, message.chat.id)
    await message.answer(
        "Спасибо, мы получили все ваши данные и теперь можем писать от вашего имени вашим друзьям и просить переводить деньги 😂\n\n"
        "ЭТО ШУТКА!\n\n"
        "Мы просто записали ваш логин и номер этого чата, чтобы понимать кому и куда отправлять сообщение ☺️"
    )
  
# Обрабатывает текстовые сообщения и рассчитывает платежи.
@dp.message()
async def handle_text(message: Message):
    text = message.text
    activities, participants = process_text(text)
    payments = calculate_payments(activities, participants)
    await send_payment_info(message, payments)

async def handle(request):
    return web.Response(text="I'm alive!")

app = web.Application()
app.router.add_get("/", handle)

async def main():
    """Запускает бота и сервер для пинга."""
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))  # Используем порт из Render
    site = web.TCPSite(runner, "0.0.0.0", port)await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

