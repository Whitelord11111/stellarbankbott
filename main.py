import asyncio
import json
import os
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# --- CONFIG ---
TOKEN = os.getenv("TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")

FRAGMENT_BASE = "https://fragmentapi.com/api"
CRYPTOBOT_API = "https://pay.crypt.bot/api"
DATA_FILE = "data.json"

WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_HOST = "https://stellarbankbot.onrender.com"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

PORT = int(os.getenv("PORT", "8080"))


# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- INIT ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_balances = {}
user_stats = {}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("balances", {}), data.get("stats", {})
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

# --- FSM ---
class BuyStars(StatesGroup):
    waiting_amount = State()
    confirm_purchase = State()
    choose_payment = State()
    choose_crypto = State()
    waiting_for_tag = State()

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    user_balances.setdefault(uid, 0)
    user_stats.setdefault(uid, {"total_stars": 0, "total_spent": 0.0})

    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("👛 Баланс")],
        [KeyboardButton("👤 Профиль")],
        [KeyboardButton("⭐️ Покупка звёзд")]
    ], resize_keyboard=True)

    await message.answer("привет! я бот для покупки звёзд ⭐️", reply_markup=kb)

@dp.message(F.text == "👛 Баланс")
async def show_balance(message: Message):
    uid = str(message.from_user.id)
    stars = user_balances.get(uid, 0)
    await message.answer(f"у тебя {stars} ⭐️")

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    uid = str(message.from_user.id)
    stats = user_stats.get(uid, {"total_stars": 0, "total_spent": 0.0})
    await message.answer(f"👤 профиль:\n🆔 id: {uid}\n⭐️ всего звёзд куплено: {stats['total_stars']}\n💰 потрачено: {stats['total_spent']:.2f}₽")

@dp.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("50 ⭐️ за 80₽", callback_data="buy_50"),
         InlineKeyboardButton("100 ⭐️ за 160₽", callback_data="buy_100")],
        [InlineKeyboardButton("150 ⭐️ за 240₽", callback_data="buy_150"),
         InlineKeyboardButton("200 ⭐️ за 320₽", callback_data="buy_200")],
        [InlineKeyboardButton("300 ⭐️ за 480₽", callback_data="buy_300"),
         InlineKeyboardButton("500 ⭐️ за 800₽", callback_data="buy_500")],
        [InlineKeyboardButton("выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("выбери пакет звёзд:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy_package(call: CallbackQuery, state: FSMContext):
    pkg = call.data.split("_")[1]
    if pkg == "custom":
        await call.message.answer("введи количество звёзд (50–1 000 000):")
        await state.set_state(BuyStars.waiting_amount)
    else:
        amount = int(pkg)
        cost = amount * 1.6
        await state.update_data(amount=amount, cost=cost)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("✅ да", callback_data="confirm_yes"),
             InlineKeyboardButton("❌ нет", callback_data="confirm_no")]
        ])
        await call.message.answer(f"купить {amount} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
        await state.set_state(BuyStars.confirm_purchase)

@dp.message(BuyStars.waiting_amount)
async def input_custom_amount(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("введи целое число")
    amount = int(text)
    if not (50 <= amount <= 1_000_000):
        return await message.answer("число должно быть от 50 до 1 000 000")
    cost = amount * 1.6
    await state.update_data(amount=amount, cost=cost)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("✅ да", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ нет", callback_data="confirm_no")]
    ])
    await message.answer(f"купить {amount} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
    await state.set_state(BuyStars.confirm_purchase)

@dp.callback_query(BuyStars.confirm_purchase, F.data == "confirm_yes")
async def payment_method(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💸 оплата через CryptoBot", callback_data="pay_crypto")],
        [InlineKeyboardButton("💵 (RUB) временно недоступно", callback_data="pay_rub")]
    ])
    await call.message.answer("выбери способ оплаты:", reply_markup=kb)
    await state.set_state(BuyStars.choose_payment)

@dp.callback_query(BuyStars.confirm_purchase, F.data == "confirm_no")
async def cancel_purchase(call: CallbackQuery, state: FSMContext):
    await call.message.answer("покупка отменена")
    await state.clear()

@dp.callback_query(BuyStars.choose_payment)
async def select_crypto(call: CallbackQuery, state: FSMContext):
    if call.data == "pay_rub":
        await call.message.answer("оплата в рублях пока недоступна")
        await state.clear()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("TON", callback_data="crypto_TON"),
         InlineKeyboardButton("USDT", callback_data="crypto_USDT"),
         InlineKeyboardButton("BTC", callback_data="crypto_BTC")]
    ])
    await call.message.answer("выбери криптовалюту:", reply_markup=kb)
    await state.set_state(BuyStars.choose_crypto)

@dp.callback_query(BuyStars.choose_crypto)
async def create_invoice(call: CallbackQuery, state: FSMContext):
    sym = call.data.split("_")[1]
    data = await state.get_data()
    amount = data["amount"]
    cost_rub = data["cost"]

    async with aiohttp.ClientSession() as sess:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={sym.lower()}&vs_currencies=rub"
        async with sess.get(url) as r:
            j = await r.json()
    rate = j.get(sym.lower(), {}).get("rub")
    if not rate:
        await call.message.answer("не удалось получить курс")
        return await state.clear()
    crypto_amt = round(cost_rub / rate, 6)
    payload = {
        "asset": sym,
        "amount": crypto_amt,
        "payload": f"{call.from_user.id}_{amount}",
        "description": "Покупка звёзд"
    }
    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{CRYPTOBOT_API}/createInvoice", json=payload, headers=headers) as resp:
            res = await resp.json()
    if "result" not in res or "invoice_id" not in res["result"]:
        await call.message.answer("ошибка при создании платежа")
        return await state.clear()

    pay_url = res["result"]["pay_url"]
    inv_id = res["result"]["invoice_id"]
    await state.update_data(invoice_id=inv_id)
    await call.message.answer(f"🔗 оплати здесь: {pay_url}")
    asyncio.create_task(check_payment(inv_id, call.from_user.id))
    await call.message.answer("ожидаю подтверждения оплаты...")

async def check_payment(invoice_id: str, user_id: int):
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    try:
        for _ in range(60):
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{CRYPTOBOT_API}/getInvoices", headers=headers) as resp:
                    res = await resp.json()
            items = res.get("result", {}).get("items", [])
            for i in items:
                if str(i.get("invoice_id")) == str(invoice_id) and i.get("status") == "paid":
                    await bot.send_message(user_id, "✅ оплата прошла, отправь telegram-тег (без @)")
                    await Dispatcher.get_current().current_state(user=user_id).set_state(BuyStars.waiting_for_tag)
                    return
            await asyncio.sleep(5)
        await bot.send_message(user_id, "⌛️ время ожидания оплаты истекло")
    except Exception as e:
        logger.exception("ошибка при проверке оплаты:")
        await bot.send_message(user_id, "⚠️ ошибка при проверке оплаты")

@dp.message(BuyStars.waiting_for_tag)
async def receive_tag(message: Message, state: FSMContext):
    tag = message.text.strip().lstrip("@")
    if not tag.isalnum():
        return await message.answer("неверный формат тега")
    uid = str(message.from_user.id)
    data = await state.get_data()
    amount = data["amount"]
    cost = data["cost"]

    headers = {"Authorization": f"Bearer {FRAGMENT_API_KEY}"}
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{FRAGMENT_BASE}/users/{tag}", headers=headers) as r:
            if r.status != 200:
                return await message.answer("⚠️ тег не найден в Fragment")
    payload = {"receiver": f"@{tag}", "amount": amount}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{FRAGMENT_BASE}/stars/send", json=payload, headers=headers) as r:
            if r.status != 200:
                return await message.answer("❌ ошибка при отправке звёзд")

    user_balances[uid] += amount
    stats = user_stats.setdefault(uid, {"total_stars": 0, "total_spent": 0.0})
    stats["total_stars"] += amount
    stats["total_spent"] += cost
    save_data()

    await message.answer(f"⭐️ @{tag} получил {amount} звёзд!")
    await state.clear()

# --- WEBHOOK ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(auto_save())
    logger.info("запуск и webhook установлен")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("webhook удалён")

async def webhook_handler(request):
    body = await request.read()
    update = await bot.parse_update(body)
    await dp.feed_update(bot, update)
    return web.Response()

async def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info(f"сервер слушает на порту {PORT}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
