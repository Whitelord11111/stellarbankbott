import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiosend import CryptoPay
from config import Config
from database import Database

# Инициализация
bot = Bot(token=Config.TELEGRAM_TOKEN)
dp = Dispatcher()
db = Database()
cp = CryptoPay(token=Config.CRYPTOBOT_TOKEN)

# Состояния
class PurchaseStates(StatesGroup):
    select_amount = State()
    confirm_payment = State()
    enter_recipient = State()

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
    await message.answer("Введите количество звёзд (50-1,000,000):")
    await state.set_state(PurchaseStates.select_amount)

@dp.message(PurchaseStates.select_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        stars = int(message.text)
        if not (Config.MIN_STARS <= stars <= Config.MAX_STARS):
            raise ValueError
        await state.update_data(stars=stars)
        
        # Создание инвойса через aiosend
        invoice = await cp.create_invoice(
            amount=stars * Config.STAR_PRICE_RUB,
            asset="USDT",
            description=f"Покупка {stars} звёзд",
            allow_anonymous=False
        )
        
        await message.answer(
            f"Оплатите {invoice.amount} USDT:\n{invoice.bot_invoice_url}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_{invoice.invoice_id}")
            ]])
        )
        await state.set_state(PurchaseStates.confirm_payment)
        
    except Exception as e:
        await message.answer("❌ Некорректное количество!")
        await state.clear()

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    invoice_id = int(call.data.split("_")[1])
    invoice = await cp.get_invoice(invoice_id)
    
    if invoice.status == "paid":
        await call.message.answer("✅ Оплата подтверждена! Введите тег получателя:")
        await state.set_state(PurchaseStates.enter_recipient)
    else:
        await call.answer("⌛ Платеж не найден")

@dp.message(PurchaseStates.enter_recipient)
async def send_stars(message: types.Message, state: FSMContext):
    data = await state.get_data()
    recipient = message.text.strip("@")
    
    # Отправка звёзд через Fragment API
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.fragment-api.com/v1/order/stars/",
            json={"username": recipient, "quantity": data['stars']},
            headers={"Authorization": f"Bearer {Config.FRAGMENT_KEY}"}
        ) as resp:
            if resp.status == 200:
                await message.answer(f"🌟 {data['stars']} звёзд отправлены @{recipient}!")
            else:
                await message.answer("❌ Ошибка отправки")
    
    await state.clear()

# Вебхук обработчик
@cp.webhook()
async def crypto_webhook(invoice):
    if invoice.status == "paid":
        logger.info(f"Оплачен инвойс: {invoice.invoice_id}")

async def main():
    await db.connect()
    await dp.start_polling(bot)
    await cp.start_polling()  # Запуск обработки вебхуков

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
