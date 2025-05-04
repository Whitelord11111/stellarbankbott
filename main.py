import asyncio
import json
import os
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import (
    Update, Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# --- CONFIG ---
TOKEN            = '7391952562:AAHEVkEAqvyEc5YYwQZowaQVOoXYqDCKcC4'
CRYPTOBOT_TOKEN  = '378343:AA836haaZrzZYInSBc1fXlm9HcgQsz4ChrS'
FRAGMENT_API_KEY = 'c32ec465-5d81-4ca0-84d9-df6840773859'

FRAGMENT_BASE = "https://fragmentapi.com/api"
CRYPTOBOT_API = "https://pay.crypt.bot/api"
DATA_FILE     = "data.json"

WEBHOOK_HOST = "https://stellarbankbot.onrender.com"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL  = WEBHOOK_HOST + WEBHOOK_PATH
PORT         = int(os.getenv("PORT", "8080"))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT & DISPATCHER ---
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# --- PERSISTENCE ---
user_balances = {}
user_stats    = {}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d.get("balances", {}), d.get("stats", {})
    return {}, {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"balances": user_balances, "stats": user_stats}, f, ensure_ascii=False, indent=2)

user_balances, user_stats = load_data()

async def auto_save():
    while True:
        try:
            save_data()
        except Exception:
            logger.exception("Ошибка автосейва")
        await asyncio.sleep(10)

# --- FSM STATES ---
class BuyStars(StatesGroup):
    waiting_amount     = State()
    confirm_purchase   = State()
    choose_payment     = State()
    choose_crypto      = State()
    waiting_for_tag    = State()

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    user_balances.setdefault(uid, 0)
    user_stats.setdefault(uid, {"total_stars": 0, "total_spent": 0.0})

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👛 Баланс")],
            [KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="⭐️ Покупка звёзд")]
        ],
        resize_keyboard=True
    )
    await message.answer("Привет! Я бот для покупки звёзд ⭐️", reply_markup=kb)

@dp.message(F.text == "👛 Баланс")
async def show_balance(message: Message):
    uid = str(message.from_user.id)
    await message.answer(f"У тебя {user_balances.get(uid,0)} ⭐️")

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    uid = str(message.from_user.id)
    stats = user_stats.get(uid, {"total_stars":0,"total_spent":0.0})
    await message.answer(
        f"👤 Профиль:\n"
        f"🆔 {uid}\n"
        f"⭐️ Всего звёзд: {stats['total_stars']}\n"
        f"💰 Потрачено: {stats['total_spent']:.2f}₽"
    )

@dp.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50 ⭐️ за 80₽", callback_data="buy_50"),
            InlineKeyboardButton(text="100 ⭐️ за 160₽", callback_data="buy_100")
        ],
        [
            InlineKeyboardButton(text="150 ⭐️ за 240₽", callback_data="buy_150"),
            InlineKeyboardButton(text="200 ⭐️ за 320₽", callback_data="buy_200")
        ],
        [InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("Выбери пакет звёзд:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy_package(call: CallbackQuery, state: FSMContext):
    await call.answer()
    pkg = call.data.split("_",1)[1]
    if pkg == "custom":
        await call.message.answer("Введи количество звёзд (50–1 000 000):")
        await state.set_state(BuyStars.waiting_amount)
    else:
        amount = int(pkg)
        cost   = amount * 1.6
        await state.update_data(amount=amount, cost=cost)
        kb = InlineKeyboardMarkup([[ 
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
        ]])
        await call.message.answer(f"Купить {amount} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
        await state.set_state(BuyStars.confirm_purchase)

@dp.message(BuyStars.waiting_amount)
async def input_custom_amount(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("Нужно ввести целое число.")
    amt = int(text)
    if not (50 <= amt <= 1_000_000):
        return await message.answer("Число должно быть от 50 до 1 000 000.")
    cost = amt * 1.6
    await state.update_data(amount=amt, cost=cost)
    kb = InlineKeyboardMarkup([[ 
        InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
    ]])
    await message.answer(f"Купить {amt} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
    await state.set_state(BuyStars.confirm_purchase)

@dp.callback_query(BuyStars.confirm_purchase, F.data == "confirm_yes")
async def payment_method(call: CallbackQuery, state: FSMContext):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Через CryptoBot", callback_data="pay_crypto")],
        [InlineKeyboardButton(text="💵 RUB (нет)", callback_data="pay_rub")]
    ])
    await call.message.answer("Выбери способ оплаты:", reply_markup=kb)
    await state.set_state(BuyStars.choose_payment)

@dp.callback_query(BuyStars.confirm_purchase, F.data == "confirm_no")
async def cancel_purchase(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Покупка отменена.")
    await state.clear()

@dp.callback_query(BuyStars.choose_payment)
async def select_crypto(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.data == "pay_rub":
        await call.message.answer("Оплата в рублях пока недоступна.")
        await state.clear()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[ 
        InlineKeyboardButton(text="TON", callback_data="crypto_TON"),
        InlineKeyboardButton(text="USDT", callback_data="crypto_USDT"),
        InlineKeyboardButton(text="BTC", callback_data="crypto_BTC")
    ]])
    await call.message.answer("Выбери криптовалюту:", reply_markup=kb)
    await state.set_state(BuyStars.choose_crypto)

@dp.callback_query(BuyStars.choose_crypto)
async def create_invoice(call: CallbackQuery, state: FSMContext):
    await call.answer()
    sym  = call.data.split("_",1)[1]
    data = await state.get_data()
    amt  = data["amount"]
    cost = data["cost"]
    # получаем курс
    async with aiohttp.ClientSession() as sess:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={sym.lower()}&vs_currencies=rub"
        async with sess.get(url) as r:
            j = await r.json()
    rate = j.get(sym.lower(),{}).get("rub")
    if not rate:
        await call.message.answer("Не удалось получить курс.")
        return await state.clear()
    crypto_amt = round(cost / rate, 6)
    # создаём счёт
    payload = {
        "asset": sym,
        "amount": crypto_amt,
        "payload": f"{call.from_user.id}_{amt}",
        "description": "Покупка звёзд"
    }
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{CRYPTOBOT_API}/createInvoice", json=payload, headers=headers) as resp:
            res = await resp.json()
    if "result" not in res or "invoice_id" not in res["result"]:
        await call.message.answer("Ошибка при создании платежа.")
        return await state.clear()
    pay_url = res["result"]["pay_url"]
    inv_id  = res["result"]["invoice_id"]
    await state.update_data(invoice_id=inv_id)
    await call.message.answer(f"🔗 Оплати здесь: {pay_url}")
    asyncio.create_task(check_payment(inv_id, call.from_user.id))

async def check_payment(invoice_id: str, user_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    for _ in range(60):
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{CRYPTOBOT_API}/getInvoices", headers=headers) as resp:
                res = await resp.json()
        items = res.get("result",{}).get("items",[])
        if any(str(i.get("invoice_id"))==str(invoice_id) and i.get("status")=="paid" for i in items):
            await bot.send_message(user_id, "✅ Оплата подтверждена!")
            # После подтверждения оплаты, запросить тег
            await bot.send_message(user_id, "Пожалуйста, введи свой Telegram-тег для зачисления звёзд.")
            await BuyStars.waiting_for_tag.set()
            break
        await asyncio.sleep(5)

@dp.message(BuyStars.waiting_for_tag)
async def input_tag(message: Message, state: FSMContext):
    uid = str(message.from_user.id)
    tag = message.text.strip().lstrip('@')
    async with aiohttp.ClientSession() as sess:
        url = f"{FRAGMENT_BASE}/users/{tag}"
        async with sess.get(url) as r:
            data = await r.json()
    if not data.get("found"):
        await message.answer("Пользователь с таким тегом не найден.")
        return await state.clear()
    amount = (await state.get_data())["amount"]
    # Отправка звёзд через Fragment API
    payload = {
        "api_key": FRAGMENT_API_KEY,
        "target": tag,
        "amount": amount
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{FRAGMENT_BASE}/buy_stars", json=payload) as r:
            data = await r.json()
    if data.get("status") == "success":
        # Успешно отправлено
        user_balances[uid] -= amount
        user_stats[uid]["total_stars"] += amount
        user_stats[uid]["total_spent"] += (amount * 1.6)
        await message.answer(f"Звёзды успешно отправлены на @{tag}.")
    else:
        await message.answer("Ошибка при отправке звёзд. Попробуйте позже.")
    await state.clear()

# --- WEBHOOK SETUP ---
app = web.Application()
app.add_routes([web.post(WEBHOOK_PATH, dp.update)])

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    # Start the auto-save task
    loop = asyncio.get_event_loop()
    loop.create_task(auto_save())
    
    # Run webhook
    web.run_app(app, host="0.0.0.0", port=PORT)
