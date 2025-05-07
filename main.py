import logging
import uuid
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
import aiohttp
import aiocryptopay
from config import Config
from database import get_db, init_db

# Инициализация логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# Инициализация компонентов
router = Router()
bot = Bot(token=Config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
crypto = aiocryptopay.CryptoPay(Config.CRYPTOBOT_TOKEN)
fragment_session = aiohttp.ClientSession(
    headers={"Authorization": Config.FRAGMENT_API_KEY}
)

# Состояния FSM
class PurchaseStates(StatesGroup):
    select_quantity = State()
    select_currency = State()
    payment_waiting = State()
    enter_telegram_tag = State()

# Инициализация БД
init_db()

# Клавиатуры
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌟 Купить звезды"), KeyboardButton(text="💰 Баланс")],
            [KeyboardButton(text="📊 Профиль")],
        ],
        resize_keyboard=True,
    )

def currency_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="TON"), KeyboardButton(text="USDT")],
            [KeyboardButton(text="BTC"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )

# Вспомогательные функции
async def get_crypto_rate(currency: str) -> float:
    rates = await crypto.get_exchange_rates()
    rate = next(
        (r.rate for r in rates if r.source == currency and r.target == "RUB"), None
    )
    if not rate:
        raise ValueError(f"Курс для {currency} не найден")
    return rate

async def verify_telegram_tag(tag: str) -> bool:
    try:
        async with fragment_session.get(
            f"https://fragment-api.com/verify?tag={tag}"
        ) as resp:
            data = await resp.json()
            return data.get("valid", False)
    except Exception as e:
        logger.error(f"Ошибка проверки тега: {e}")
        return False

async def purchase_stars(quantity: int, tag: str) -> Dict:
    try:
        async with fragment_session.post(
            "https://fragment-api.com/purchase",
            json={"quantity": quantity, "recipient_tag": tag},
        ) as resp:
            return await resp.json()
    except Exception as e:
        logger.error(f"Ошибка покупки звезд: {e}")
        return {"success": False}

async def update_user_data(user_id: int, stars: int, amount: float):
    with get_db() as conn:
        cursor = conn.cursor()
        # Обновляем пользователя
        cursor.execute(
            """INSERT OR IGNORE INTO users (user_id) VALUES (?)""", (user_id,)
        )
        cursor.execute(
            """UPDATE users 
            SET total_stars = total_stars + ?, 
                total_spent = total_spent + ? 
            WHERE user_id = ?""",
            (stars, amount, user_id),
        )
        # Добавляем транзакцию
        cursor.execute(
            """INSERT INTO transactions 
            (tx_id, user_id, stars, amount_rub, recipient_tag)
            VALUES (?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), user_id, stars, amount, tag),
        )
        conn.commit()

# Хендлеры
@router.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🚀 Добро пожаловать в StellarBankBot!", reply_markup=main_menu())

@router.message(F.text == "🌟 Купить звезды")
async def start_purchase(message: types.Message, state: FSMContext):
    await message.answer("🔢 Введите количество звезд (1-1000):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(PurchaseStates.select_quantity)

@router.message(PurchaseStates.select_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if 1 <= quantity <= 1000:
            await state.update_data(quantity=quantity)
            await message.answer("💵 Выберите валюту:", reply_markup=currency_menu())
            await state.set_state(PurchaseStates.select_currency)
        else:
            await message.answer("❌ Введите число от 1 до 1000")
    except ValueError:
        await message.answer("❌ Некорректный ввод. Введите целое число")

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "USDT", "BTC"]))
async def process_currency(message: types.Message, state: FSMContext):
    currency = message.text
    data = await state.get_data()
    
    try:
        rate = await get_crypto_rate(currency)
        total_rub = data["quantity"] * Config.STAR_PRICE_RUB
        total_crypto = total_rub / rate
        
        invoice = await crypto.create_invoice(
            asset=currency,
            amount=total_crypto,
            description=f"Покупка {data['quantity']} звезд",
            paid_btn_name="openBot",
            payload=f"{message.from_user.id}",
        )
        
        pay_button = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice.pay_url)],
                [InlineKeyboardButton(
                    text="✅ Проверить оплату",
                    callback_data=f"check_{invoice.invoice_id}"
                )],
            ]
        )
        
        await message.answer(
            f"📄 *Счет на оплату*\n\n"
            f"• Сумма: `{total_crypto:.8f} {currency}`\n"
            f"• RUB: {total_rub}₽\n"
            f"• Звезд: {data['quantity']}",
            reply_markup=pay_button,
            parse_mode=ParseMode.MARKDOWN,
        )
        await state.update_data(
            invoice_id=invoice.invoice_id,
            currency=currency,
            total_rub=total_rub,
        )
        await state.set_state(PurchaseStates.payment_waiting)
    except Exception as e:
        logger.error(f"Ошибка создания счета: {e}")
        await message.answer("❌ Ошибка при создании счета. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data.startswith("check_"))
async def check_payment(callback: types.CallbackQuery, state: FSMContext):
    invoice_id = callback.data.split("_")[1]
    
    try:
        invoice = await crypto.get_invoices(invoice_ids=invoice_id)
        if invoice.status != "paid":
            await callback.answer("❌ Оплата не получена", show_alert=True)
            return
        
        await callback.message.edit_reply_markup()
        await callback.message.answer("✅ Оплата подтверждена! Введите Telegram тег получателя (например, @username):")
        await state.set_state(PurchaseStates.enter_telegram_tag)
    except Exception as e:
        logger.error(f"Ошибка проверки оплаты: {e}")
        await callback.answer("⚠️ Ошибка проверки статуса", show_alert=True)

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    tag = message.text.lstrip("@")
    data = await state.get_data()
    
    if not await verify_telegram_tag(tag):
        await message.answer("❌ Тег не найден. Введите корректный Telegram тег:")
        return
    
    try:
        purchase_result = await purchase_stars(data["quantity"], tag)
        if not purchase_result.get("success"):
            raise ValueError(purchase_result.get("error", "Unknown error"))
        
        # Сохраняем данные
        await update_user_data(
            user_id=message.from_user.id,
            stars=data["quantity"],
            amount=data["total_rub"],
        )
        
        await message.answer(
            f"🎉 Успешная покупка!\n"
            f"• Получено звезд: {data['quantity']}\n"
            f"• Получатель: @{tag}\n"
            f"• Сумма: {data['total_rub']}₽"
        )
    except Exception as e:
        logger.error(f"Ошибка покупки: {e}")
        await message.answer("❌ Ошибка при обработке покупки. Средства будут возвращены.")
        # Здесь должен быть код возврата средств через CryptoBot API
    finally:
        await state.clear()

@router.message(F.text == "💰 Баланс")
async def show_balance(message: types.Message):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_stars, total_spent FROM users WHERE user_id = ?",
            (message.from_user.id,),
        )
        result = cursor.fetchone()
        
    if result:
        stars, spent = result
        await message.answer(
            f"📊 Ваш баланс:\n"
            f"• Звезд: {stars} 🌟\n"
            f"• Потрачено: {spent:.2f}₽"
        )
    else:
        await message.answer("❌ У вас еще нет покупок")

@router.message(F.text == "📊 Профиль")
async def show_profile(message: types.Message):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, total_stars, total_spent FROM users WHERE user_id = ?",
            (message.from_user.id,),
        )
        result = cursor.fetchone()
        
    if result:
        username, stars, spent = result
        response = (
            f"👤 Ваш профиль:\n"
            f"• Тег: @{username or 'не указан'}\n"
            f"• ID: {message.from_user.id}\n"
            f"• Всего звезд: {stars} 🌟\n"
            f"• Потрачено: {spent:.2f}₽"
        )
    else:
        response = "❌ Профиль не найден"
    
    await message.answer(response)

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    
    # Настройка вебхука
    await bot.set_webhook(
        url=Config.WEBHOOK_URL,
        secret_token=Config.WEBHOOK_SECRET,
    )
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
