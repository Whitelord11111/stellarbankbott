import os
import json
import logging
import asyncio

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.filters import Text
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from aiocryptopay import AioCryptoPay, Networks

# --- КОНФИГ ---
BOT_TOKEN        = '7391952562:AAHEVkEAqvyEc5YYwQZowaQVOoXYqDCKcC4'
CRYPTO_TOKEN     = '378343:AA836haaZrzZYInSBc1fXlm9HcgQsz4ChrS'
FRAGMENT_API_KEY = 'c32ec465-5d81-4ca0-84d9-df6840773859'
FRAGMENT_BASE    = "https://fragmentapi.com/api"

APP_URL      = os.getenv("APP_URL", "https://stellarbankbot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = APP_URL + WEBHOOK_PATH
PORT         = int(os.getenv("PORT", "8080"))
CRYPTO_PATH  = "/crypto-pay"
DATA_FILE    = "data.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher(storage=MemoryStorage())
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)

# --- ПЕРСИСТЕНС ---
user_balances: dict[str,int] = {}
user_stats:    dict[str,dict] = {}

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
        except:
            logger.exception("Автосейв упал")
        await asyncio.sleep(10)

# --- FSM ---
class BuyStars(StatesGroup):
    waiting_amount   = State()
    confirm_purchase = State()
    choose_crypto    = State()
    waiting_for_tag  = State()

# --- ХЕНДЛЕРЫ ---
@dp.message.register(CommandStart())
async def cmd_start(msg: types.Message):
    uid = str(msg.from_user.id)
    user_balances.setdefault(uid, 0)
    user_stats.setdefault(uid, {"total_stars":0,"total_spent":0.0})
    kb = (
        types.ReplyKeyboardMarkup(resize_keyboard=True)
        .add(
            types.KeyboardButton(text="👛 Баланс"),
            types.KeyboardButton(text="👤 Профиль"),
            types.KeyboardButton(text="⭐️ Покупка звёзд")
        )
    )
    await msg.answer("Привет! Я бот для покупки звёзд ⭐️", reply_markup=kb)

@dp.message.register(Text(text="👛 Баланс"))
async def show_balance(msg: types.Message):
    uid = str(msg.from_user.id)
    await msg.answer(f"У тебя {user_balances.get(uid,0)} ⭐️")

@dp.message.register(Text(text="👤 Профиль"))
async def show_profile(msg: types.Message):
    uid = str(msg.from_user.id)
    st  = user_stats.get(uid, {"total_stars":0,"total_spent":0.0})
    await msg.answer(
        f"👤 Профиль:\n"
        f"🆔 {uid}\n"
        f"⭐️ Всего звёзд: {st['total_stars']}\n"
        f"💰 Потрачено: {st['total_spent']:.2f}₽"
    )

@dp.message.register(Text(text="⭐️ Покупка звёзд"))
async def buy_stars(msg: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="50 ⭐️ за 80₽",  callback_data="buy_50"),
            types.InlineKeyboardButton(text="100 ⭐️ за 160₽", callback_data="buy_100")
        ],
        [
            types.InlineKeyboardButton(text="150 ⭐️ за 240₽", callback_data="buy_150"),
            types.InlineKeyboardButton(text="200 ⭐️ за 320₽", callback_data="buy_200")
        ],
        [ types.InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom") ],
    ])
    await msg.answer("Выбери пакет звёзд:", reply_markup=kb)

@dp.callback_query.register(lambda c: c.data.startswith("buy_"))
async def handle_buy(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    pkg = call.data.split("_",1)[1]
    if pkg == "custom":
        await call.message.answer("Введи количество звёзд (50–1 000 000):")
        await state.set_state(BuyStars.waiting_amount)
    else:
        amt  = int(pkg)
        cost = amt * 1.6
        await state.update_data(amount=amt, cost=cost)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[ 
            types.InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
        ]])
        await call.message.answer(f"Купить {amt} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
        await state.set_state(BuyStars.confirm_purchase)

@dp.message.register(BuyStars.waiting_amount)
async def custom_amount(msg: types.Message, state: FSMContext):
    text = msg.text.strip()
    if not text.isdigit():
        return await msg.answer("Нужно целое число")
    amt = int(text)
    if not (50 <= amt <= 1_000_000):
        return await msg.answer("От 50 до 1 000 000")
    cost = amt * 1.6
    await state.update_data(amount=amt, cost=cost)
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[ 
        types.InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
    ]])
    await msg.answer(f"Купить {amt} ⭐️ за {cost:.2f}₽?", reply_markup=kb)
    await state.set_state(BuyStars.confirm_purchase)

@dp.callback_query.register(BuyStars.confirm_purchase, lambda c: c.data=="confirm_yes")
async def pick_crypto(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[ 
        types.InlineKeyboardButton(text="TON",  callback_data="crypto_TON"),
        types.InlineKeyboardButton(text="USDT", callback_data="crypto_USDT"),
        types.InlineKeyboardButton(text="BTC",  callback_data="crypto_BTC")
    ]])
    await call.message.answer("Выбери крипту:", reply_markup=kb)
    await state.set_state(BuyStars.choose_crypto)

@dp.callback_query.register(BuyStars.confirm_purchase, lambda c: c.data=="confirm_no")
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    await state.clear()

@dp.callback_query.register(BuyStars.choose_crypto)
async def create_invoice(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    sym  = call.data.split("_",1)[1]
    data = await state.get_data()
    amt  = data["amount"]
    cost = data["cost"]
    # получаем курс
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(f"https://api.coingecko.com/api/v3/simple/price?ids={sym.lower()}&vs_currencies=rub")
        j = await r.json()
    rate = j.get(sym.lower(),{}).get("rub")
    if not rate:
        return await call.message.answer("Ошибка курса")
    crypto_amt = round(cost / rate, 6)
    inv = await crypto.create_invoice(
        asset=sym,
        amount=crypto_amt,
        payload=f"{call.from_user.id}:{amt}:{cost}",
        description="Покупка звёзд"
    )
    pay_url = inv.bot_invoice_url or inv.url
    await call.message.answer(f"🔗 Оплати здесь: {pay_url}")

@crypto.pay_handler()
async def on_paid(update, app):
    if update.payload.status != "paid":
        return
    pl = update.payload.payload or ""
    try:
        chat, amt, cost = pl.split(":")
        chat_id = int(chat)
    except:
        logger.error("Bad payload %s", pl)
        return
    await bot.send_message(chat_id, "✅ Оплата получена! Введите @‑тег без @:")
    state = dp.current_state(user=chat_id, chat=chat_id)
    await state.set_state(BuyStars.waiting_for_tag)
    await state.update_data(amount=int(amt), cost=float(cost))

@dp.message.register(BuyStars.waiting_for_tag)
async def receive_tag(msg: types.Message, state: FSMContext):
    tag = msg.text.strip().lstrip("@")
    if not tag.isalnum():
        return await msg.answer("Неверный формат.")
    data = await state.get_data()
    amt, cost = data["amount"], data["cost"]
    # проверка Fragment
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(f"{FRAGMENT_BASE}/users/{tag}",
                           headers={"Authorization":f"Bearer {FRAGMENT_API_KEY}"})
        if r.status != 200:
            return await msg.answer("Тег не найден.")
    # отправка
    async with aiohttp.ClientSession() as sess:
        r = await sess.post(f"{FRAGMENT_BASE}/stars/send",
                            json={"receiver":f"@{tag}","amount":amt},
                            headers={"Authorization":f"Bearer {FRAGMENT_API_KEY}"})
        if r.status != 200:
            return await msg.answer("Ошибка отправки.")
    uid = str(msg.from_user.id)
    user_balances[uid]  = user_balances.get(uid,0) + amt
    st = user_stats.setdefault(uid, {"total_stars":0,"total_spent":0.0})
    st["total_stars"]  += amt
    st["total_spent"]  += cost
    save_data()
    await msg.answer(f"⭐️ @{tag} получил {amt} звёзд!")
    await state.clear()

# --- WEBHOOK + SERVER ---
async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message","callback_query"])
    asyncio.create_task(auto_save())
    logger.info("Webhook установлен")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await crypto.close()
    logger.info("Всё закрыто")

def main():
    app = web.Application()
    # Telegram
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=BOT_TOKEN)
    handler.register(app, path=WEBHOOK_PATH)
    # старты/стопы
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    # CryptoBot
    app.router.add_post(CRYPTO_PATH, crypto.webhook_handler)
    logger.info(f"Сервис живёт на 0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
