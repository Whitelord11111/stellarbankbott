import os
import json
import logging
import asyncio

from aiohttp import web
import aiohttp

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Text
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from aiocryptopay import AioCryptoPay, Networks

# --- КОНФИГ ---
BOT_TOKEN         = '7391952562:AAHEVkEAqvyEc5YYwQZowaQVOoXYqDCKcC4'
CRYPTO_TOKEN      = '378343:AA836haaZrzZYInSBc1fXlm9HcgQsz4ChrS'
FRAGMENT_API_KEY  = 'c32ec465-5d81-4ca0-84d9-df6840773859'
FRAGMENT_BASE     = "https://fragmentapi.com/api"

# URL вашего сервиса (на Render.com), например:
APP_URL           = os.getenv("APP_URL", "https://stellarbankbot.onrender.com")

# для Telegram‑webhook
WEBHOOK_SECRET    = BOT_TOKEN
WEBHOOK_PATH      = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL       = APP_URL + WEBHOOK_PATH
PORT              = int(os.getenv("PORT", "8080"))

# для CryptoBot‑webhook
CRYPTO_PATH       = "/crypto-pay"

# файл для хранения балансов/статистики
DATA_FILE         = "data.json"


# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- ИНИЦИАЛИЗАЦИЯ ---
bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher(storage=MemoryStorage())
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)


# --- ПЕРСИСТЕНС ---
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
        json.dump({"balances": user_balances, "stats": user_stats}, f,
                  ensure_ascii=False, indent=2)

user_balances, user_stats = load_data()

async def auto_save():
    while True:
        try:
            save_data()
        except Exception:
            logger.exception("Ошибка автосейва")
        await asyncio.sleep(10)


# --- FSM: состояния покупки звёзд ---
class BuyStars(StatesGroup):
    waiting_amount    = State()
    confirm_purchase  = State()
    choose_crypto     = State()
    waiting_for_tag   = State()


# --- ХЕНДЛЕРЫ ---

@dp.message.register(CommandStart())
async def cmd_start(message: types.Message):
    uid = str(message.from_user.id)
    user_balances.setdefault(uid, 0)
    user_stats  .setdefault(uid, {"total_stars": 0, "total_spent": 0.0})

    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="👛 Баланс")],
        [types.KeyboardButton(text="👤 Профиль")],
        [types.KeyboardButton(text="⭐️ Покупка звёзд")],
    ], resize_keyboard=True)
    await message.answer("Привет! Я бот для покупки звёзд ⭐️", reply_markup=kb)


@dp.message.register(Text(text="👛 Баланс"))
async def show_balance(message: types.Message):
    uid = str(message.from_user.id)
    await message.answer(f"У тебя {user_balances.get(uid,0)} ⭐️")


@dp.message.register(Text(text="👤 Профиль"))
async def show_profile(message: types.Message):
    uid   = str(message.from_user.id)
    stats = user_stats.get(uid, {"total_stars":0,"total_spent":0.0})
    await message.answer(
        f"👤 Профиль:\n"
        f"🆔 {uid}\n"
        f"⭐️ Всего звёзд: {stats['total_stars']}\n"
        f"💰 Потрачено: {stats['total_spent']:.2f}₽"
    )


@dp.message.register(Text(text="⭐️ Покупка звёзд"))
async def buy_stars(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="50 ⭐️ за 80₽",  callback_data="buy_50"),
            types.InlineKeyboardButton(text="100 ⭐️ за 160₽", callback_data="buy_100")
        ],
        [
            types.InlineKeyboardButton(text="150 ⭐️ за 240₽", callback_data="buy_150"),
            types.InlineKeyboardButton(text="200 ⭐️ за 320₽", callback_data="buy_200")
        ],
        [
            types.InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")
        ],
    ])
    await message.answer("Выбери пакет звёзд:", reply_markup=kb)


@dp.callback_query.register(lambda c: c.data.startswith("buy_"))
async def handle_buy_package(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    pkg = call.data.split("_",1)[1]
    if pkg == "custom":
        await call.message.answer("Введи количество звёзд (50–1 000 000):")
        await state.set_state(BuyStars.waiting_amount)
    else:
        amount = int(pkg)
        cost   = amount * 1.6
        await state.update_data(amount=amount, cost=cost)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no"),
        ]])
        await call.message.answer(f"Купить {amount} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
        await state.set_state(BuyStars.confirm_purchase)


@dp.message.register(BuyStars.waiting_amount)
async def input_custom_amount(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        return await message.answer("Нужно ввести целое число.")
    amt = int(text)
    if not (50 <= amt <= 1_000_000):
        return await message.answer("Число должно быть от 50 до 1 000 000.")
    cost = amt * 1.6
    await state.update_data(amount=amt, cost=cost)
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no"),
    ]])
    await message.answer(f"Купить {amt} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
    await state.set_state(BuyStars.confirm_purchase)


@dp.callback_query.register(BuyStars.confirm_purchase, lambda c: c.data=="confirm_yes")
async def payment_method(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    # сразу переходим к выбору крипты
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="TON",  callback_data="crypto_TON"),
        types.InlineKeyboardButton(text="USDT", callback_data="crypto_USDT"),
        types.InlineKeyboardButton(text="BTC",  callback_data="crypto_BTC"),
    ]])
    await call.message.answer("Выбери криптовалюту для оплаты:", reply_markup=kb)
    await state.set_state(BuyStars.choose_crypto)


@dp.callback_query.register(BuyStars.confirm_purchase, lambda c: c.data=="confirm_no")
async def cancel_purchase(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Покупка отменена.")
    await state.clear()


@dp.callback_query.register(BuyStars.choose_crypto)
async def create_invoice(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    sym   = call.data.split("_",1)[1]
    data  = await state.get_data()
    amount = data["amount"]
    cost   = data["cost"]

    # 1) получаем курс из CoinGecko
    async with aiohttp.ClientSession() as sess:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={sym.lower()}&vs_currencies=rub"
        async with sess.get(url) as r:
            j = await r.json()
    rate = j.get(sym.lower(),{}).get("rub")
    if not rate:
        return await call.message.answer("Не удалось получить курс.")
    crypto_amt = round(cost / rate, 6)

    # 2) создаём инвойс через aiocryptopay
    #    в payload зашиваем chat_id, amount, cost
    payload_str = f"{call.from_user.id}:{amount}:{cost}"
    invoice = await crypto.create_invoice(
        asset=sym,
        amount=crypto_amt,
        payload=payload_str,
        description="Покупка звёзд"
    )
    pay_url = invoice.bot_invoice_url or invoice.url
    await call.message.answer(f"🔗 Оплати здесь: {pay_url}")
    # далее ожидаем webhook от CryptoBot


@crypto.pay_handler()
async def invoice_paid(update, app):
    """Обработка уведомления от CryptoBot о платеже."""
    if update.payload.status != "paid":
        return
    pl = update.payload.payload or ""
    try:
        chat_str, amt_str, cost_str = pl.split(":")
        chat_id = int(chat_str)
    except Exception:
        logger.error("Невалидный payload в уведомлении: %s", pl)
        return

    # уведомляем пользователя и переводим FSM в ожидание тега
    await bot.send_message(chat_id, "✅ Оплата получена! Введите Telegram‑тег (без @):")
    state = dp.current_state(chat=chat_id, user=chat_id)
    await state.set_state(BuyStars.waiting_for_tag)
    await state.update_data(amount=int(amt_str), cost=float(cost_str))


@dp.message.register(BuyStars.waiting_for_tag)
async def receive_tag(message: types.Message, state: FSMContext):
    tag = message.text.strip().lstrip("@")
    if not tag.isalnum():
        return await message.answer("Неверный формат тега.")
    data = await state.get_data()
    amt  = data["amount"]
    cost = data["cost"]

    # проверяем существование пользователя в Fragment
    headers = {"Authorization": f"Bearer {FRAGMENT_API_KEY}"}
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{FRAGMENT_BASE}/users/{tag}", headers=headers) as resp:
            if resp.status != 200:
                return await message.answer("⚠️ Тег не найден в Fragment.")

    # отправляем звёзды через Fragment API
    async with aiohttp.ClientSession() as sess:
        async with sess.post(
            f"{FRAGMENT_BASE}/stars/send",
            json={"receiver": f"@{tag}", "amount": amt},
            headers=headers
        ) as resp:
            if resp.status != 200:
                return await message.answer("❌ Ошибка при отправке звёзд.")

    # обновляем баланс и статистику
    uid = str(message.from_user.id)
    user_balances[uid] = user_balances.get(uid, 0) + amt
    stats = user_stats.setdefault(uid, {"total_stars":0,"total_spent":0.0})
    stats["total_stars"]  += amt
    stats["total_spent"]  += cost
    save_data()

    await message.answer(f"⭐️ @{tag} получил {amt} звёзд!")
    await state.clear()


# --- WEBHOOK И ЗАПУСК СЕРВЕРА ---

async def on_startup(app: web.Application):
    # Telegram webhook
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message","callback_query"])
    # автосейв данных
    asyncio.create_task(auto_save())
    logger.info(f"Telegram webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
    # удаляем Telegram webhook
    await bot.delete_webhook()
    # закрываем сессию aiocryptopay
    await crypto.close()
    logger.info("Webhook удалён, сессии закрыты")


def main():
    app = web.Application()

    # 1) Telegram‑webhook
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
    handler.register(app, path=WEBHOOK_PATH)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 2) CryptoBot‑webhook
    app.router.add_post(CRYPTO_PATH, crypto.get_updates)

    # Запуск aiohttp‑сервера (Render.com слушает 0.0.0.0:PORT)
    logger.info(f"Сервис запущен на 0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
