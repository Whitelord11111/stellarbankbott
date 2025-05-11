import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiosend import CryptoPay
from aiosend.types import Invoice
from aiosend.webhook import AiohttpManager
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

class PurchaseStates(StatesGroup):
    SELECT_AMOUNT = State()
    CONFIRM_PAYMENT = State()
    ENTER_RECIPIENT = State()

async def init_webhooks(app: web.Application):
    """Инициализация вебхуков"""
    # Проверка корректности URL
    if not Config.WEBHOOK_URL.startswith("https://"):
        raise ValueError("WEBHOOK_URL должен начинаться с https://")
    
    # Инициализация CryptoPay
    cp = CryptoPay(
        token=Config.CRYPTOBOT_TOKEN,
        webhook_manager=AiohttpManager(app, "/crypto_webhook")
    )
    
    # Регистрация обработчика для CryptoBot
    @cp.webhook()
    async def crypto_webhook_handler(invoice: Invoice):
        if invoice.status == "paid":
            logger.info(f"Оплачен инвойс: {invoice.invoice_id}")
        return web.Response(text="OK")
    
    # Настройка вебхука для Telegram
    await bot.delete_webhook(drop_pending_updates=True)
    webhook_url = f"{Config.WEBHOOK_URL}/telegram_webhook"
    logger.info(f"Устанавливаю вебхук: {webhook_url}")
    
    await bot.set_webhook(
        url=webhook_url,
        secret_token=os.getenv("WEBHOOK_SECRET")
    )
    
    return cp

@dp.message(Command("start"))
async def start(message: types.Message):
    """Обработчик команды /start с логированием"""
    logger.info(f"Получена команда /start от {message.from_user.id}")
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

async def telegram_webhook(request):
    """Кастомный обработчик вебхуков Telegram"""
    try:
        request_data = await request.json()
        logger.debug(f"Получен вебхук: {request_data}")
        return await dp._check_webhook(bot)(request)
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {str(e)}")
        return web.Response(status=500)

async def main():
    await db.connect()
    
    # Создание веб-приложения
    app = web.Application()
    
    # Инициализация вебхуков
    cp = await init_webhooks(app)
    
    # Регистрация эндпоинтов
    app.router.add_post("/telegram_webhook", telegram_webhook)
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    
    logger.info(f"Сервер запущен на порту {os.getenv('PORT', 10000)}")
    logger.info(f"Telegram вебхук: {Config.WEBHOOK_URL}/telegram_webhook")
    logger.info(f"CryptoBot вебхук: {Config.WEBHOOK_URL}/crypto_webhook")
    
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
