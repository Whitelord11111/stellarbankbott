# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiosend import CryptoPay
from aiosend.types import Invoice
from config import Config
from database import Database
from aiohttp import web
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=Config.TELEGRAM_TOKEN)
dp = Dispatcher()
db = Database()
cp = CryptoPay(token=Config.CRYPTOBOT_TOKEN)

# Состояния FSM
class PurchaseStates(StatesGroup):
    SELECT_AMOUNT = State()
    CONFIRM_PAYMENT = State()
    ENTER_RECIPIENT = State()

# Хендлеры
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🚀 Добро пожаловать! Купите звёзды через CryptoBot:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="⭐️ Купить звёзды")]],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "⭐️ Купить звёзды")
async def buy_stars(message: types.Message, state: FSMContext):
    await message.answer(f"Введите количество звёзд ({Config.MIN_STARS}-{Config.MAX_STARS}):")
    await state.set_state(PurchaseStates.SELECT_AMOUNT)

@dp.message(PurchaseStates.SELECT_AMOUNT)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        stars = int(message.text)
        if not (Config.MIN_STARS <= stars <= Config.MAX_STARS):
            raise ValueError
            
        amount_usd = stars * Config.STAR_PRICE_USD
        invoice = await cp.create_invoice(
            amount=amount_usd,
            asset="USDT",
            description=f"Покупка {stars} звёзд",
            allow_anonymous=False
        )

        await message.answer(
            f"💸 Оплатите {amount_usd:.2f} USDT:\n{invoice.bot_invoice_url}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="✅ Проверить оплату",
                    callback_data=f"check_{invoice.invoice_id}"
                )
            ]])
        )
        await state.update_data(invoice_id=invoice.invoice_id, stars=stars)
        await state.set_state(PurchaseStates.CONFIRM_PAYMENT)

    except ValueError:
        await message.answer("❌ Некорректное количество!")
        await state.clear()

@cp.invoice_polling()
async def handle_paid_invoice(invoice: Invoice):
    if invoice.status == "paid":
        logger.info(f"Оплачен инвойс: {invoice.invoice_id}")

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    invoice_id = int(call.data.split("_")[1])
    invoice = await cp.get_invoice(invoice_id)
    
    if invoice.status == "paid":
        await call.message.answer("✅ Оплата подтверждена! Введите тег получателя:")
        await state.set_state(PurchaseStates.ENTER_RECIPIENT)
    else:
        await call.answer("⌛ Платеж не найден")

@dp.message(PurchaseStates.ENTER_RECIPIENT)
async def send_stars(message: types.Message, state: FSMContext):
    data = await state.get_data()
    recipient = message.text.strip("@")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.fragment-api.com/v1/order/stars/",
            json={"username": recipient, "quantity": data['stars']},
            headers={"Authorization": Config.FRAGMENT_KEY}
        ) as resp:
            if resp.status == 200:
                await message.answer(f"🌟 {data['stars']} звёзд отправлены @{recipient}!")
            else:
                error = await resp.text()
                logger.error(f"Fragment API Error: {error}")
                await message.answer("❌ Ошибка отправки. Обратитесь в поддержку.")
    
    await state.clear()

async def web_app():
    app = web.Application()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return app

async def main():
    await db.connect()
    app = await web_app()
    await dp.start_polling(bot)
    await cp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
