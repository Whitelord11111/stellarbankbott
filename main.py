import logging
import uuid
import hmac
import hashlib
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
from config import Config
from database import db_connection, init_db

# Инициализация
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=Config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
session = aiohttp.ClientSession()

# Состояния FSM
class PurchaseStates(StatesGroup):
    select_package = State()
    confirm_purchase = State()
    input_custom = State()
    select_currency = State()
    payment_waiting = State()
    enter_telegram_tag = State()

# Инициализация БД
init_db()

# Предустановленные пакеты
STAR_PACKAGES = {
    "50 ⭐️ за 80₽": 50,
    "100 ⭐️ за 160₽": 100,
    "150 ⭐️ за 240₽": 150,
    "200 ⭐️ за 320₽": 200,
    "250 ⭐️ за 400₽": 250
}

# Клавиатуры
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👛 Баланс"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="⭐️ Покупка звёзд")]
        ],
        resize_keyboard=True
    )

def currency_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="TON"), KeyboardButton(text="USDT")],
            [KeyboardButton(text="BTC"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )

# API функции
async def crypto_api_request(method: str, endpoint: str, data: dict = None) -> dict:
    url = f"{Config.CRYPTO_API_URL}/{endpoint}"
    headers = {"Crypto-Pay-API-Token": Config.CRYPTOBOT_TOKEN}
    async with session.request(method, url, json=data, headers=headers) as resp:
        return await resp.json()

async def create_invoice(asset: str, amount: float) -> dict:
    return await crypto_api_request(
        "POST", "createInvoice",
        {"asset": asset, "amount": amount, "description": "Покупка звёзд"}
    )

# Хендлеры
@router.message(Command("start"))
async def start(message: types.Message):
    with db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        conn.commit()
    await message.answer("🚀 Добро пожаловать в StellarBankBot!", reply_markup=main_menu())

@router.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"buy_{value}") 
         for name, value in STAR_PACKAGES.items()],
        [InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("Выбери пакет звёзд:", reply_markup=kb)

@router.callback_query(F.data.startswith("buy_"))
async def handle_package(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    
    if action == "custom":
        await call.message.answer("Введите количество звёзд (50-1000):")
        await state.set_state(PurchaseStates.input_custom)
    else:
        amount = int(action)
        cost = amount * 1.6  # 1.6 руб/звезда
        await state.update_data(amount=amount, cost=cost)
        
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
             InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
        ])
        await call.message.answer(
            f"Подтвердите покупку {amount} звёзд за {cost}₽",
            reply_markup=confirm_kb
        )
        await state.set_state(PurchaseStates.confirm_purchase)

@router.message(PurchaseStates.input_custom)
async def process_custom_input(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if 50 <= amount <= 1000000:
            cost = amount * 1.6
            await state.update_data(amount=amount, cost=cost)
            
            confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
                 InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
            ])
            await message.answer(
                f"Подтвердите покупку {amount} звёзд за {cost}₽",
                reply_markup=confirm_kb
            )
            await state.set_state(PurchaseStates.confirm_purchase)
        else:
            await message.answer("❌ Число должно быть от 50 до 1 000 000.")
    except ValueError:
        await message.answer("❌ Введите корректное число.")

@router.callback_query(PurchaseStates.confirm_purchase, F.data == "confirm_yes")
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💵 Выберите валюту:", reply_markup=currency_menu())
    await state.set_state(PurchaseStates.select_currency)

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "BTC", "USDT"]))
async def process_currency(message: types.Message, state: FSMContext):
    data = await state.get_data()
    asset = message.text
    
    try:
        rates = await crypto_api_request("GET", "getExchangeRates")
        rate = next(r["rate"] for r in rates["result"] if r["source"] == asset)
        
        total_rub = data["cost"]
        total_crypto = total_rub / rate
        
        invoice = await create_invoice(asset, total_crypto)
        invoice_data = invoice["result"]
        
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=invoice_data["pay_url"])],
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_{invoice_data['invoice_id']}")]
        ])
        
        await message.answer(
            f"📄 Счет на оплату:\n"
            f"• Сумма: {total_crypto:.8f} {asset}\n"
            f"• RUB: {total_rub:.2f}₽",
            reply_markup=pay_kb
        )
        
        with db_connection() as conn:
            conn.execute(
                """INSERT INTO transactions 
                (tx_id, user_id, stars, amount_rub, invoice_id, status)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), message.from_user.id, data["amount"], 
                total_rub, invoice_data["invoice_id"], "created")
            )
            conn.commit()
        
        await state.update_data(invoice_id=invoice_data["invoice_id"])
        await state.set_state(PurchaseStates.payment_waiting)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка при создании счета")
        await state.clear()

@router.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    invoice_id = call.data.split("_")[1]
    
    try:
        response = await crypto_api_request("GET", f"getInvoices?invoice_ids={invoice_id}")
        invoice = response["result"]["items"][0]
        
        if invoice["status"] == "paid":
            await call.message.edit_reply_markup()
            await call.message.answer("✅ Оплата подтверждена! Введите Telegram тег получателя:")
            await state.set_state(PurchaseStates.enter_telegram_tag)
        else:
            await call.answer("❌ Оплата не получена", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка проверки оплаты: {e}")
        await call.answer("⚠️ Ошибка проверки статуса", show_alert=True)

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    tag = message.text.lstrip("@")
    data = await state.get_data()
    
    if not await verify_telegram_tag(tag):  # Ваша функция проверки тега
        return await message.answer("❌ Тег не найден. Повторите ввод:")
    
    try:
        # Вызов Fragment API для покупки звезд
        async with session.post(
            "https://fragment-api.com/purchase",
            headers={"Authorization": Config.FRAGMENT_API_KEY},
            json={"quantity": data["amount"], "recipient_tag": tag}
        ) as resp:
            result = await resp.json()
        
        if result["success"]:
            with db_connection() as conn:
                conn.execute(
                    """UPDATE users 
                    SET total_stars = total_stars + ?, 
                        total_spent = total_spent + ? 
                    WHERE user_id = ?""",
                    (data["amount"], data["cost"], message.from_user.id)
                )
                conn.execute(
                    """UPDATE transactions 
                    SET status = ?, recipient_tag = ? 
                    WHERE invoice_id = ?""",
                    ("completed", tag, data["invoice_id"])
                )
                conn.commit()
            
            await message.answer(f"🎉 Успешно! {data['amount']} звёзд переданы @{tag}")
        else:
            raise ValueError(result.get("error", "Ошибка API"))
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка при обработке заказа")
        await crypto_api_request("POST", f"refund/{data['invoice_id']}")
    
    await state.clear()

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
