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
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
import aiohttp
import json
from config import Config
from database import db_connection, init_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

router = Router()
bot = Bot(token=Config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)

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

# Пакеты звезд
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

# Работа с Crypto Pay API
async def crypto_api_request(method: str, endpoint: str, data: dict = None) -> dict:
    url = f"{Config.CRYPTO_API_URL}/{endpoint}"
    headers = {"Crypto-Pay-API-Token": Config.CRYPTOBOT_TOKEN}
    
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, json=data, headers=headers) as resp:
            return await resp.json()

# Хендлеры
@router.message(Command("start"))
async def start(message: types.Message):
    with db_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (message.from_user.id, message.from_user.username)
        )
        conn.commit()
    await message.answer("🚀 Добро пожаловать в StellarBankBot!", reply_markup=main_menu())

@router.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"buy_{value}") 
         for name, value in STAR_PACKAGES.items()],
        [InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("🎁 Выберите пакет звёзд:", reply_markup=kb)

@router.callback_query(F.data.startswith("buy_"))
async def handle_package(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    
    if action == "custom":
        await call.message.answer("🔢 Введите количество звёзд (50-1000):")
        await state.set_state(PurchaseStates.input_custom)
    else:
        amount = int(action)
        cost = amount * 1.6  # 1.6 руб/звезда
        await state.update_data(amount=amount, cost=cost)
        
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
             InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no")]
        ])
        await call.message.answer(
            f"🛒 Подтвердите покупку:\n"
            f"• Звёзды: {amount} ⭐️\n"
            f"• Сумма: {cost:.2f}₽",
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
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
                 InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no")]
            ])
            await message.answer(
                f"🛒 Подтвердите покупку:\n"
                f"• Звёзды: {amount} ⭐️\n"
                f"• Сумма: {cost:.2f}₽",
                reply_markup=confirm_kb
            )
            await state.set_state(PurchaseStates.confirm_purchase)
        else:
            await message.answer("❌ Введите число от 50 до 1 000 000!")
    except ValueError:
        await message.answer("❌ Некорректный ввод!")

@router.callback_query(PurchaseStates.confirm_purchase, F.data == "confirm_yes")
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💵 Выберите валюту:", reply_markup=currency_menu())
    await state.set_state(PurchaseStates.select_currency)

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "BTC", "USDT"]))
async def process_currency(message: types.Message, state: FSMContext):
    data = await state.get_data()
    asset = message.text
    
    try:
        # Получение курса
        rates = await crypto_api_request("GET", "getExchangeRates")
        rate = next(r["rate"] for r in rates["result"] if r["source"] == asset)
        
        # Расчет стоимости
        total_rub = data["cost"]
        total_crypto = total_rub / rate
        
        # Создание инвойса
        invoice = await crypto_api_request(
            "POST", "createInvoice",
            {"asset": asset, "amount": total_crypto, "description": "Покупка звёзд"}
        )
        
        if not invoice.get("ok"):
            raise ValueError("Ошибка создания счета")
        
        invoice_data = invoice["result"]
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=invoice_data["pay_url"])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice_data['invoice_id']}")]
        ])
        
        await message.answer(
            f"📄 Счет на оплату:\n"
            f"• Сумма: {total_crypto:.8f} {asset}\n"
            f"• RUB: {total_rub:.2f}₽",
            reply_markup=pay_kb
        )
        
        # Сохранение транзакции
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
        logger.error(f"Ошибка: {str(e)}")
        await message.answer("❌ Ошибка при создании счета!")
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
            await call.answer("❌ Оплата не получена!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка проверки оплаты: {str(e)}")
        await call.answer("⚠️ Ошибка проверки статуса", show_alert=True)

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    tag = message.text.lstrip("@")
    data = await state.get_data()
    
    try:
        # Проверка тега через Fragment API
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://fragment-api.com/verify?tag={tag}",
                headers={"Authorization": Config.FRAGMENT_API_KEY}
            ) as resp:
                result = await resp.json()
                if not result.get("valid"):
                    raise ValueError("Тег не найден")
        
        # Покупка звезд
        async with session.post(
            "https://fragment-api.com/purchase",
            headers={"Authorization": Config.FRAGMENT_API_KEY},
            json={"quantity": data["amount"], "recipient_tag": tag}
        ) as resp:
            purchase_result = await resp.json()
            if not purchase_result.get("success"):
                raise ValueError(purchase_result.get("error", "Ошибка API"))
        
        # Обновление данных
        with db_connection() as conn:
            # Пользователь
            conn.execute(
                """UPDATE users 
                SET total_stars = total_stars + ?, 
                    total_spent = total_spent + ? 
                WHERE user_id = ?""",
                (data["amount"], data["cost"], message.from_user.id)
            )
            # Транзакция
            conn.execute(
                """UPDATE transactions 
                SET status = ?, recipient_tag = ? 
                WHERE invoice_id = ?""",
                ("completed", tag, data["invoice_id"])
            )
            conn.commit()
        
        await message.answer(
            f"🎉 Успешно! {data['amount']} звёзд переданы @{tag}\n"
            f"Сумма: {data['cost']:.2f}₽"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        await message.answer("❌ Ошибка при обработке заказа!")
        # Возврат средств
        await crypto_api_request("POST", f"refund/{data['invoice_id']}")
    
    await state.clear()

# Вебхук для Crypto Pay
async def crypto_webhook(request: web.Request):
    body = await request.text()
    signature = request.headers.get("Crypto-Pay-API-Signature")
    
    # Проверка подписи
    secret = Config.WEBHOOK_SECRET.encode()
    expected_signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    
    if signature != expected_signature:
        return web.Response(status=403)
    
    try:
        data = json.loads(body)
        invoice = data.get("invoice")
        
        if invoice["status"] == "paid":
            with db_connection() as conn:
                conn.execute(
                    "UPDATE transactions SET status = ? WHERE invoice_id = ?",
                    ("paid", invoice["invoice_id"])
                )
                conn.commit()
                
        return web.Response(text="OK")
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return web.Response(status=500)

async def on_startup(dp: Dispatcher):
    await bot.delete_webhook()
    if Config.WEBHOOK_URL:
        await bot.set_webhook(
            url=Config.WEBHOOK_URL,
            secret_token=Config.WEBHOOK_SECRET
        )

async def on_shutdown(dp: Dispatcher):
    await bot.delete_webhook()

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    
    # Настройка вебхука
    if Config.WEBHOOK_URL:
        app = web.Application()
        app.router.add_post("/webhook", crypto_webhook)
        SimpleRequestHandler(dp, bot).register(app, path="/")
        
        # Запуск веб-сервера
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=10000)
        await site.start()
        logger.info("Webhook server started")
        
        # Запуск бота
        await dp.start_polling(bot)
    else:
        await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    
    # Валидация конфига
    if not all([Config.TELEGRAM_TOKEN, Config.CRYPTOBOT_TOKEN]):
        raise ValueError("Не заданы обязательные переменные окружения!")
    
    asyncio.run(main())
