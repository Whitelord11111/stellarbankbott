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

# Инициализация компонентов
bot = Bot(token=Config.TELEGRAM_TOKEN)
dp = Dispatcher()
db = Database()
cp = CryptoPay(token=Config.CRYPTOBOT_TOKEN)

# Состояния FSM
class PurchaseStates(StatesGroup):
    SELECT_AMOUNT = State()
    CONFIRM_PAYMENT = State()
    ENTER_RECIPIENT = State()

async def setup_webhook():
    """Настройка вебхуков для Telegram и CryptoBot"""
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=f"{Config.WEBHOOK_URL}/telegram_webhook",
        secret_token=os.getenv("WEBHOOK_SECRET")
    )

async def web_application():
    """Создание веб-приложения с обработчиками"""
    app = web.Application()
    
    # Регистрация эндпоинтов
    app.router.add_post("/telegram_webhook", lambda r: dp._check_webhook(bot)(r))
    app.router.add_post("/crypto_webhook", crypto_webhook_handler)
    
    # Настройка сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    return app

@cp.webhook()
async def crypto_webhook_handler(request):
    """Обработчик вебхуков от CryptoBot"""
    data = await request.json()
    invoice = Invoice(**data)
    
    if invoice.status == "paid":
        logger.info(f"Оплачен инвойс: {invoice.invoice_id}")
        # Здесь можно добавить логику обработки оплаты
        
    return web.Response(text="OK")

@dp.message(Command("start"))
async def start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "🚀 Добро пожаловать! Купите звёзды через CryptoBot:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="⭐️ Купить звёзды")]],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "⭐️ Купить звёзды")
async def buy_stars(message: types.Message, state: FSMContext):
    """Начало процесса покупки"""
    await message.answer(f"Введите количество звёзд ({Config.MIN_STARS}-{Config.MAX_STARS}):")
    await state.set_state(PurchaseStates.SELECT_AMOUNT)

@dp.message(PurchaseStates.SELECT_AMOUNT)
async def process_amount(message: types.Message, state: FSMContext):
    """Обработка ввода количества звёзд"""
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

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    """Проверка статуса оплаты"""
    invoice_id = int(call.data.split("_")[1])
    invoice = await cp.get_invoice(invoice_id)
    
    if invoice.status == "paid":
        await call.message.answer("✅ Оплата подтверждена! Введите тег получателя:")
        await state.set_state(PurchaseStates.ENTER_RECIPIENT)
    else:
        await call.answer("⌛ Платеж не найден")

@dp.message(PurchaseStates.ENTER_RECIPIENT)
async def send_stars(message: types.Message, state: FSMContext):
    """Отправка звёзд через Fragment API"""
    data = await state.get_data()
    recipient = message.text.strip("@")
    
    try:
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
    except Exception as e:
        logger.error(f"Ошибка соединения: {str(e)}")
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
    
    await state.clear()

async def main():
    """Основная функция инициализации"""
    await db.connect()
    await setup_webhook()
    app = await web_application()
    logger.info("Сервер успешно запущен")
    
    # Бесконечное ожидание
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
