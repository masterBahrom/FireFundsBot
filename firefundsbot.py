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
    
    parts = message_text.split("Участники:")
    activities_text = parts[0].strip()
    participants_text = parts[1].strip() if len(parts) > 1 else ""
    
    # Разбиваем активности построчно
    activity_lines = activities_text.splitlines()
    for line in activity_lines:
        # Регулярное выражение для 4-х полей
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
    
    # Разбиваем список участников построчно
    participants = participants_text.splitlines()
    return activities, participants

# Функция для расчета платежей.
# Алгоритм:
# 1. Для каждого участника вычисляем, какая сумма ожидается к оплате:
#    - Если активность для "all", то стоимость делится поровну между всеми участниками.
#    - Если указано конкретное имя (например, "@polyauspenska"), то эта сумма добавляется только для указанного участника.
# 2. Отдельно суммируем, сколько каждый участник оплатил (payer).
# 3. Баланс = (оплачено) - (ожидаемая сумма). Если баланс положительный – участник переплатил, иначе – недоплатил.
def calculate_payments(activities, participants):
    # Инициализируем словари для ожидаемой суммы и фактических платежей.
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
            # Добавляем сумму только тому, для кого предназначена оплата.
            # Сравниваем в нижнем регистре для надежности.
            for participant in participants:
                if participant.lower() == target:
                    expected[participant] += amount
        # Учитываем, сколько заплатил payer.
        if payer in paid:
            paid[payer] += amount
    
    # Рассчитываем баланс: разница между тем, сколько заплатил, и ожидаемой суммой.
    payments = {}
    for participant in participants:
        balance = paid[participant] - expected[participant]
        # Если баланс положительный – участник переплатил (ему должны вернуть деньги),
        # если отрицательный – он должен доплатить.
        payments[participant] = balance
    return payments

# Функция для отправки информации об оплатах пользователям.
async def send_payment_info(message: Message, payments):
    chat_ids = load_chat_ids()
    for participant, balance in payments.items():
        if balance > 0:
            text = f"{participant}, вам должны вернуть: {balance}\nЗапрашивайте у @master_bahrom"
        else:
            text = f"{participant}, вы должны оплатить: {-balance}\nПеревести можете по ссылке - https://cpay.me/971547437161?amount={-balance}"
        
        # Логирование отправки
        if participant in chat_ids:
            await message.answer(f"Отправляю сообщение {participant} в чат {chat_ids[participant]}: {text}")
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

