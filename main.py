import logging
import uuid
import hmac
import hashlib
import json
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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, 
                f"{Config.CRYPTO_API_URL}/{endpoint}",
                json=data,
                headers={"Crypto-Pay-API-Token": Config.CRYPTOBOT_TOKEN}
            ) as resp:
                return await resp.json()
    except aiohttp.ClientError as e:
        logger.error(f"API Connection Error: {str(e)}")
        return {"ok": False, "error": str(e)}

# Хендлеры
@router.message(Command("start"))
async def start(message: types.Message):
    try:
        with db_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (message.from_user.id, message.from_user.username)
            )
            conn.commit()
        await message.answer("🚀 Добро пожаловать в StellarBankBot!", reply_markup=main_menu())
    except Exception as e:
        logger.error(f"Database Error: {str(e)}")
        await message.answer("❌ Произошла внутренняя ошибка. Попробуйте позже.")

@router.message(F.text == "⭐️ Покупка звёзд")
async def buy_stars(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"buy_{value}") for name, value in STAR_PACKAGES.items()],
        [InlineKeyboardButton(text="Выбрать своё количество", callback_data="buy_custom")]
    ])
    await message.answer("🎁 Выберите пакет звёзд:", reply_markup=kb)

@router.callback_query(F.data.startswith("buy_"))
async def handle_package(call: types.CallbackQuery, state: FSMContext):
    try:
        action = call.data.split("_")[1]
        
        if action == "custom":
            await call.message.answer("🔢 Введите количество звёзд (50-1000):")
            await state.set_state(PurchaseStates.input_custom)
        else:
            amount = int(action)
            cost = amount * Config.STAR_PRICE_RUB
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
    except Exception as e:
        logger.error(f"Package Handling Error: {str(e)}")
        await call.message.answer("❌ Произошла ошибка. Попробуйте снова.")

@router.message(PurchaseStates.input_custom)
async def process_custom_input(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if 50 <= amount <= 1000000:
            cost = amount * Config.STAR_PRICE_RUB
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
    except Exception as e:
        logger.error(f"Custom Input Error: {str(e)}")
        await message.answer("❌ Произошла ошибка. Попробуйте снова.")

@router.callback_query(PurchaseStates.confirm_purchase, F.data == "confirm_yes")
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.message.answer("💵 Выберите валюту:", reply_markup=currency_menu())
        await state.set_state(PurchaseStates.select_currency)
    except Exception as e:
        logger.error(f"Confirmation Error: {str(e)}")
        await call.message.answer("❌ Произошла ошибка. Попробуйте снова.")

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "BTC", "USDT"]))
async def process_currency(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        asset = message.text
        
        # Получение курса
        rates = await crypto_api_request("GET", "getExchangeRates")
        if not rates.get("ok"):
            raise ValueError("Ошибка получения курсов валют")
        
        rate = next(
            (float(r["rate"]) for r in rates["result"] 
             if r["source"] == asset and r["target"] == "RUB"),
            None
        )
        if not rate:
            raise ValueError(f"Курс для {asset}/RUB не найден")
        
        total_rub = data["cost"]
        total_crypto = total_rub / rate
        
        # Создание инвойса
        invoice = await crypto_api_request(
            "POST", "createInvoice",
            {
                "asset": asset,
                "amount": f"{total_crypto:.8f}",
                "description": f"Покупка {data['amount']} звезд"
            }
        )
        
        if not invoice.get("ok"):
            raise ValueError(f"Ошибка API: {invoice.get('description')}")
        
        invoice_data = invoice["result"]
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=invoice_data["pay_url"])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice_data['invoice_id']}")]
        ])
        
        await message.answer(
            f"📄 Счет на оплату:\n"
            f"• Сумма: {total_crypto:.8f} {asset}\n"
            f"• RUB: {total_rub:.2f}₽\n"
            f"• Звезд: {data['amount']}",
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
        logger.error(f"Currency Processing Error: {str(e)}", exc_info=True)
        await message.answer("❌ Ошибка при создании счета. Попробуйте позже.")
        await state.clear()

@router.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    try:
        invoice_id = call.data.split("_")[1]
        
        response = await crypto_api_request("GET", f"getInvoices?invoice_ids={invoice_id}")
        if not response.get("ok"):
            raise ValueError("Ошибка проверки статуса")
        
        invoice = response["result"]["items"][0]
        
        if invoice["status"] == "paid":
            await call.message.edit_reply_markup()
            await call.message.answer("✅ Оплата подтверждена! Введите Telegram тег получателя:")
            await state.set_state(PurchaseStates.enter_telegram_tag)
        else:
            await call.answer("❌ Оплата не получена!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Payment Check Error: {str(e)}")
        await call.answer("⚠️ Ошибка проверки статуса", show_alert=True)

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    try:
        tag = message.text.lstrip("@")
        data = await state.get_data()
        
        # Проверка тега через Fragment API
        async with aiohttp.ClientSession() as session:
            # 1. Проверка тега
            async with session.get(
                "https://api.fragment.com/username/check",
                params={"username": tag},
                headers={"Authorization": f"Bearer {Config.FRAGMENT_API_KEY}"}
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise ValueError(f"Fragment API error: {error_text}")
                
                result = await resp.json()
                if not result.get("ok") or not result["result"].get("valid"):
                    raise ValueError("Тег невалиден")

            # 2. Покупка звезд
            async with session.post(
                "https://api.fragment.com/purchase",
                headers={
                    "Authorization": f"Bearer {Config.FRAGMENT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "username": tag,
                    "amount": data["amount"],
                    "currency": "STARS"
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise ValueError(f"Ошибка покупки: {error_text}")
                
                purchase_result = await resp.json()
                if not purchase_result.get("ok"):
                    raise ValueError(purchase_result.get("error", "Ошибка"))

        # 3. Обновление транзакции
        with db_connection() as conn:
            conn.execute(
                """UPDATE transactions 
                SET status = ?, recipient_tag = ? 
                WHERE invoice_id = ?""",
                ("completed", tag, data["invoice_id"])
            )
            conn.commit()

        await message.answer(f"🎉 Успешно! {data['amount']} звёзд отправлены @{tag}")

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}", exc_info=True)
        # Возврат средств
        if 'invoice_id' in data:
            logger.info(f"Возврат средств для инвойса {data['invoice_id']}")
            await crypto_api_request("POST", f"refund/{data['invoice_id']}")
        await message.answer("❌ Ошибка отправки. Средства возвращены.")
    finally:
        await state.clear()

# Вебхук обработчик
async def crypto_webhook(request: web.Request):
    logger.info("Получен вебхук от Crypto Pay!")
    body = await request.text()
    logger.debug(f"Тело запроса: {body}")  # Логируем данные
    try:
        body = await request.text()
        signature = request.headers.get("Crypto-Pay-API-Signature")
        
        # Проверка подписи
        secret = Config.WEBHOOK_SECRET.encode()
        expected_signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        
        if signature != expected_signature:
            return web.Response(status=403)
        
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
        logger.error(f"Webhook Error: {str(e)}")
        return web.Response(status=500)

async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=Config.WEBHOOK_URL,
        secret_token=Config.WEBHOOK_SECRET
    )
    logger.info("Вебхук успешно установлен!")

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)
    
    # Настройка веб-сервера
    app = web.Application()
    app.router.add_post("/webhook", crypto_webhook)
    SimpleRequestHandler(dp, bot).register(app, path="/")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(Config.PORT))  # 0.0.0.0 обязательно!
    
    try:
        await site.start()
        logger.info(f"Сервер запущен на порту {Config.PORT}")
        # Уберите строку с start_polling!
        while True:
    await asyncio.sleep(3600)  # Бесконечное ожидание для работы сервера
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    import asyncio
    
    # Валидация конфигурации
    Config.validate()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
