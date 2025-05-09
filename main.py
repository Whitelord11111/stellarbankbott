import asyncio
import logging
import uuid
import hmac
import hashlib
import json

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from aiohttp import web, ClientSession

from config import Config
from database import db_connection, init_db

# ——— Logging —————————————————————————————————————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ——— Bot, Dispatcher & Router —————————————————————
bot = Bot(token=Config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()

# ——— FSM States ———————————————————————————————————
class PurchaseStates(StatesGroup):
    select_package     = State()
    confirm_purchase   = State()
    input_custom       = State()
    select_currency    = State()
    payment_waiting    = State()
    enter_telegram_tag = State()

# ——— Initialize DB ————————————————————————————
init_db()

# ——— Star Packages ————————————————————————————
STAR_PACKAGES = {
    "50 ⭐️ за 80₽":   50,
    "100 ⭐️ за 160₽": 100,
    "150 ⭐️ за 240₽": 150,
    "200 ⭐️ за 320₽": 200,
    "250 ⭐️ за 400₽": 250,
}

# ——— Keyboards ——————————————————————————————————
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("👛 Баланс"), KeyboardButton("👤 Профиль")],
            [KeyboardButton("⭐️ Покупка звёзд")]
        ], resize_keyboard=True
    )

def currency_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("TON"), KeyboardButton("USDT")],
            [KeyboardButton("BTC"), KeyboardButton("❌ Отмена")]
        ], resize_keyboard=True
    )

# ——— Crypto Pay API helper —————————————————————
async def crypto_api_request(method: str, endpoint: str, data: dict = None) -> dict:
    url = f"{Config.CRYPTO_API_URL}/{endpoint}"
    headers = {"Crypto-Pay-API-Token": Config.CRYPTOBOT_TOKEN}
    try:
        async with ClientSession() as session:
            async with session.request(method, url, json=data, headers=headers) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"Crypto API error: {e}")
        return {"ok": False, "error": str(e)}

# ——— Handlers ——————————————————————————————————
@router.message(Command(commands="start"))
async def cmd_start(message: types.Message):
    try:
        with db_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (message.from_user.id, message.from_user.username)
            )
        await message.answer(
            "🚀 Добро пожаловать в StellarBankBot!",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"start handler error: {e}")
        await message.answer("❌ Ошибка сервиса, попробуйте позже.")

@router.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=nm, callback_data=f"buy_{val}")
         for nm, val in STAR_PACKAGES.items()],
        [InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("🎁 Выберите пакет звёзд:", reply_markup=kb)

@router.callback_query(F.data.startswith("buy_"))
async def handle_package(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_", 1)[1]
    if action == "custom":
        await call.message.answer("🔢 Введите количество звёзд (50–1 000 000):")
        await state.set_state(PurchaseStates.input_custom)
    else:
        amount = int(action)
        cost = amount * Config.STAR_PRICE_RUB
        await state.update_data(amount=amount, cost=cost)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Отменить",   callback_data="confirm_no")
            ]
        ])
        await call.message.answer(
            f"🛒 Подтвердите покупку:\n• {amount} ⭐️\n• {cost:.2f}₽",
            reply_markup=kb
        )
        await state.set_state(PurchaseStates.confirm_purchase)

@router.message(PurchaseStates.input_custom)
async def process_custom_input(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        if not 50 <= amt <= 1_000_000:
            raise ValueError
        cost = amt * Config.STAR_PRICE_RUB
        await state.update_data(amount=amt, cost=cost)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Отменить",   callback_data="confirm_no")
            ]
        ])
        await message.answer(
            f"🛒 Подтвердите покупку:\n• {amt} ⭐️\n• {cost:.2f}₽",
            reply_markup=kb
        )
        await state.set_state(PurchaseStates.confirm_purchase)
    except:
        await message.answer("❌ Введите число от 50 до 1 000 000!")

@router.callback_query(PurchaseStates.confirm_purchase, F.data == "confirm_yes")
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💵 Выберите валюту:", reply_markup=currency_menu())
    await state.set_state(PurchaseStates.select_currency)

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "USDT", "BTC"]))
async def process_currency(message: types.Message, state: FSMContext):
    data = await state.get_data()
    asset = message.text
    rates = await crypto_api_request("GET", "getExchangeRates")
    if not rates.get("ok"):
        return await message.answer("❌ Не удалось получить курс.")
    rate = next((float(r["rate"]) for r in rates["result"]
                 if r["source"] == asset and r["target"] == "RUB"), None)
    if rate is None:
        return await message.answer(f"❌ Курс {asset}/RUB не найден.")
    total_rub = data["cost"]
    total_crypto = total_rub / rate

    inv = await crypto_api_request("POST", "createInvoice", {
        "asset": asset,
        "amount": f"{total_crypto:.8f}",
        "description": f"{data['amount']} ⭐️"
    })
    if not inv.get("ok"):
        return await message.answer("❌ Ошибка создания счёта.")
    inv_data = inv["result"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💳 Оплатить", url=inv_data["pay_url"])],
        [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_{inv_data['invoice_id']}")]
    ])
    await message.answer(
        f"📄 Счёт:\n• {total_crypto:.8f} {asset}\n• {total_rub:.2f}₽\n• {data['amount']} ⭐️",
        reply_markup=kb
    )

    with db_connection() as conn:
        conn.execute(
            "INSERT INTO transactions "
            "(tx_id, user_id, stars, amount_rub, invoice_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), message.from_user.id, data["amount"],
             total_rub, inv_data["invoice_id"], "created")
        )
    await state.update_data(invoice_id=inv_data["invoice_id"])
    await state.set_state(PurchaseStates.payment_waiting)

@router.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    invoice_id = call.data.split("_", 1)[1]
    resp = await crypto_api_request("GET", f"getInvoices?invoice_ids={invoice_id}")
    if not resp.get("ok"):
        return await call.answer("❌ Не удалось проверить оплату.", show_alert=True)
    item = resp["result"]["items"][0]
    if item["status"] == "paid":
        await call.message.edit_reply_markup()
        await call.message.answer("✅ Оплачено! Введите Telegram‑тег получателя:")
        await state.set_state(PurchaseStates.enter_telegram_tag)
    else:
        await call.answer("❌ Ещё не оплачено.", show_alert=True)

@router.message(PurchaseStates.enter_telegram_tag, F.text == "❌ Отмена")
async def cancel_tag_input(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Отменено.", reply_markup=main_menu())

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if "invoice_id" not in data:
        await message.answer("❌ Сессия устарела.")
        return await state.clear()

    tag = message.text.lstrip("@")
    logger.info(f"Sending stars: user={message.from_user.id} tag={tag} amount={data['amount']}")

    try:
        async with ClientSession() as session:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Config.FRAGMENT_API_KEY}"
            }
            payload = {
                "username": tag,
                "quantity": data["amount"],
                "show_sender": False
            }

            async with session.post(Config.FRAGMENT_API_URL, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status == 400:
                    return await message.answer("❌ Неверный тег, повторите или отмените.")
                if resp.status != 200:
                    logger.error(f"Fragment API {resp.status}: {text}")
                    raise ValueError("Ошибка сервера Fragment")
                result = await resp.json()
                if not result.get("success"):
                    raise ValueError(result.get("message", "Не удалось отправить звёзды"))

        with db_connection() as conn:
            conn.execute(
                "UPDATE transactions SET status = ?, recipient_tag = ? WHERE invoice_id = ?",
                ("completed", tag, data["invoice_id"])
            )

        await message.answer(f"🎉 Успешно отправлено {data['amount']} ⭐️ @{tag}")

    except Exception as e:
        logger.error(f"process_tag error: {e}", exc_info=True)
        # refund
        try:
            await crypto_api_request("POST", f"refund/{data['invoice_id']}")
            logger.info(f"Refunded invoice {data['invoice_id']}")
        except Exception as re:
            logger.error(f"refund error: {re}")
        await message.answer("❌ Ошибка — средства возвращены.")
    finally:
        await state.clear()

# ——— Webhook Handlers —————————————————————————————
async def telegram_webhook(request: web.Request):
    return await SimpleRequestHandler(dp, bot).handle(request)

async def crypto_webhook(request: web.Request):
    body = await request.text()
    sig  = request.headers.get("Crypto-Pay-API-Signature", "")
    mac  = hmac.new(Config.WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, sig):
        return web.Response(status=403)
    data = json.loads(body)
    inv  = data.get("invoice", {})
    if inv.get("status") == "paid":
        with db_connection() as conn:
            conn.execute(
                "UPDATE transactions SET status = ? WHERE invoice_id = ?",
                ("paid", inv["invoice_id"])
            )
    return web.Response(text="OK")

# ——— Startup & Main —————————————————————————————
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=Config.WEBHOOK_URL,
        secret_token=Config.WEBHOOK_SECRET
    )
    dp.include_router(router)
    logger.info("Webhook set, router included.")

async def main():
    Config.validate()
    app = web.Application()
    app.router.add_post("/webhook",        telegram_webhook)
    app.router.add_post("/crypto_webhook", crypto_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()

    await on_startup()
    logger.info(f"Server running on port {Config.PORT}")
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down bot")
