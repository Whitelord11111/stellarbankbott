import logging
import logging.handlers
import hmac
import hashlib
import uuid
import json
import aiohttp
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiohttp import web
from config import Config
from database import Database

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            "bot.log",
            maxBytes=5*1024*1024,
            backupCount=3
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация компонентов
bot = Bot(token=Config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
db = Database()

# Состояния FSM
class PurchaseStates(StatesGroup):
    select_package = State()
    confirm_purchase = State()
    input_custom = State()
    select_currency = State()
    payment_waiting = State()
    enter_telegram_tag = State()

# Клавиатуры
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐️ Купить звёзды")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def currency_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="TON"), KeyboardButton(text="USDT")],
            [KeyboardButton(text="BTC")]
        ],
        resize_keyboard=True
    )

# Утилиты
async def notify_admins(message: str):
    for admin_id in Config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"⚠️ {message}")
        except Exception as e:
            logger.error(f"Admin notify failed: {e}")

async def crypto_api_request(method: str, endpoint: str, data: dict = None):
    try:
        url = f"{Config.CRYPTO_API_URL}/{endpoint}"
        headers = {
            "Crypto-Pay-API-Token": Config.CRYPTOBOT_TOKEN,
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making request to: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                response = await resp.json()
                logger.debug(f"API Response: {response}")
                
                if resp.status != 200:
                    logger.error(f"HTTP Error {resp.status}: {response}")
                    return None
                    
                if not response.get('ok'):
                    logger.error(f"API Error: {response.get('error')}")
                    return None
                    
                return response
                
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        return None
                
    except Exception as e:
        logger.error(f"Crypto API request failed: {str(e)}")
        return None

# Хендлеры
@router.message(Command("start"))
async def start(message: types.Message):
    async with db.cursor() as cursor:
        await cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (message.from_user.id, message.from_user.username)
        )
    await message.answer(
        "🚀 Добро пожаловать в магазин звёзд!",
        reply_markup=main_menu()
    )

@router.message(F.text == "⭐️ Купить звёзды")
async def buy_stars(message: types.Message, state: FSMContext):
    packages = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50 ⭐️ за 80₽", callback_data="buy_50")],
        [InlineKeyboardButton(text="100 ⭐️ за 160₽", callback_data="buy_100")],
        [InlineKeyboardButton(text="Свой вариант", callback_data="buy_custom")]
    ])
    await message.answer("Выберите пакет:", reply_markup=packages)
    await state.set_state(PurchaseStates.select_package)

@router.callback_query(F.data.startswith("buy_"))
async def handle_package(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    
    if action == "custom":
        await call.message.answer(f"Введите количество звёзд ({Config.MIN_STARS}-{Config.MAX_STARS}):")
        await state.set_state(PurchaseStates.input_custom)
    else:
        stars = int(action)
        await state.update_data(stars=stars)
        await call.message.answer(
            f"Выбрано {stars} звёзд за {stars * Config.STAR_PRICE_RUB}₽\n"
            "Подтверждаете покупку?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
            ]])
        )
        await state.set_state(PurchaseStates.confirm_purchase)

@router.message(PurchaseStates.input_custom)
async def process_custom_input(message: types.Message, state: FSMContext):
    try:
        stars = int(message.text)
        if not (Config.MIN_STARS <= stars <= Config.MAX_STARS):
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            f"Некорректное значение! Введите число от {Config.MIN_STARS} до {Config.MAX_STARS}"
        )
        return
    
    await state.update_data(stars=stars)
    await message.answer(
        f"Выбрано {stars} звёзд за {stars * Config.STAR_PRICE_RUB}₽\n"
        "Подтверждаете покупку?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
        ]])
    )
    await state.set_state(PurchaseStates.confirm_purchase)

@router.callback_query(PurchaseStates.confirm_purchase, F.data == "confirm_yes")
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "Выберите валюту для оплаты:",
        reply_markup=currency_menu()
    )
    await state.set_state(PurchaseStates.select_currency)

@router.message(PurchaseStates.select_currency, F.text.in_(["TON", "USDT", "BTC"]))
async def process_currency(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        stars = data['stars']
        amount_rub = stars * Config.STAR_PRICE_RUB

        # 1. Получение курсов валют
        rates = await crypto_api_request("GET", "getExchangeRates")  # Исправлен эндпоинт
        if not rates or not rates.get('result'):
            raise ValueError("Не удалось получить курсы валют")

        # 2. Поиск нужной валюты
        currency_data = next(
            (r for r in rates['result'] 
             if r.get('source') == message.text and r.get('target') == 'RUB'),
            None
        )
        
        if not currency_data:
            raise ValueError("Валюта не найдена")

        # 3. Расчет суммы
        currency_rate = float(currency_data['rate'])
        amount_crypto = round(amount_rub / currency_rate, 6)

        # 4. Создание инвойса
        invoice_id = str(uuid.uuid4())
        invoice = await crypto_api_request(
            "POST", 
            "createInvoice",  # Исправлен эндпоинт
            {
                "asset": message.text,
                "amount": str(amount_crypto),
                "description": f"Покупка {stars} звёзд",
                "hidden_message": str(message.from_user.id),
                "payload": invoice_id
            }
        )

        if not invoice or not invoice.get('result'):
            raise ValueError("Ошибка создания платежа")

        # 5. Сохранение в БД
        async with db.cursor() as cursor:
            await cursor.execute(
                """INSERT INTO transactions 
                (tx_id, user_id, stars, amount_rub, invoice_id, status)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), message.from_user.id, stars, amount_rub, 
                 invoice_id, "created")
            )

        # 6. Формирование ответа
        pay_url = invoice['result'].get('pay_url', '')
        if not pay_url:
            raise ValueError("Некорректный ответ от платежной системы")

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice_id}")]
        ])

        await message.answer(
            f"💎 Сумма к оплате: {amount_crypto} {message.text}\n"
            "⚠️ Платеж действителен 15 минут",
            reply_markup=markup
        )
        await state.set_state(PurchaseStates.payment_waiting)
        await state.update_data(invoice_id=invoice_id)

    except Exception as e:
        logger.error(f"Ошибка обработки валюты: {str(e)}")
        await message.answer("❌ Произошла ошибка при создании платежа")
        await state.clear()

@router.callback_query(F.data.startswith("check_"))
async def check_payment(call: types.CallbackQuery, state: FSMContext):
    invoice_id = call.data.split("_")[1]
    
    invoice_data = await crypto_api_request(
        "GET",
        f"getInvoices?invoice_ids={invoice_id}"
    )
    
    if not invoice_data or not invoice_data.get('result'):
        await call.answer("❌ Ошибка проверки платежа")
        return
    
    invoice = invoice_data['result']['items'][0]  # Важно: items[0]
    status = invoice['status']
    
    if status == 'paid':
        await call.message.answer("✅ Оплата подтверждена! Введите Telegram тег получателя:")
        await state.set_state(PurchaseStates.enter_telegram_tag)
        await state.update_data(invoice_id=invoice_id)
    else:
        await call.answer(f"Статус: {status}")

@router.message(PurchaseStates.enter_telegram_tag)
async def process_tag(message: types.Message, state: FSMContext):
    data = await state.get_data()
    invoice_id = data['invoice_id']
    recipient_tag = message.text.lstrip('@')
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                Config.FRAGMENT_API_URL,
                json={"recipient": recipient_tag, "stars": data['stars']},
                headers={"Authorization": f"Bearer {Config.FRAGMENT_KEY}"}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"Fragment API error: {error}")
                
                async with db.cursor() as cursor:
                    await cursor.execute(
                        """UPDATE transactions 
                        SET status='completed', recipient_tag=?
                        WHERE invoice_id=?""",
                        (recipient_tag, invoice_id)
                    )
                    
                    await cursor.execute(
                        """UPDATE users 
                        SET total_stars = total_stars + ?, 
                            total_spent = total_spent + ?
                        WHERE user_id = ?""",
                        (data['stars'], data['stars'] * Config.STAR_PRICE_RUB, 
                         message.from_user.id)
                    )
                    
                await message.answer(f"✅ {data['stars']} звёзд отправлены на @{recipient_tag}!")
                
    except Exception as e:
        logger.error(f"Ошибка отправки: {str(e)}")
        await crypto_api_request("POST", f"invoices/{invoice_id}/refund")
        async with db.cursor() as cursor:
            await cursor.execute(
                "UPDATE transactions SET status='refunded' WHERE invoice_id=?",
                (invoice_id,)
            )
        await message.answer("❌ Ошибка отправки. Средства возвращены.")
    
    await state.clear()

@router.message(F.text == "💰 Баланс")
async def show_balance(message: types.Message):
    async with db.cursor() as cursor:
        await cursor.execute(
            "SELECT total_stars, total_spent FROM users WHERE user_id = ?",
            (message.from_user.id,)
        )
        user_data = await cursor.fetchone()
    
    if user_data:
        await message.answer(
            f"📊 Ваш баланс:\n"
            f"⭐️ Звёзд: {user_data['total_stars']}\n"
            f"💰 Потрачено: {user_data['total_spent']:.2f}₽"
        )
    else:
        await message.answer("❌ Профиль не найден")

@router.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    try:
        async with db.cursor() as cursor:
            # Статистика пользователя
            await cursor.execute(
                """SELECT 
                    COUNT(*) as orders, 
                    COALESCE(SUM(stars), 0) as stars 
                FROM transactions 
                WHERE user_id = ? AND status = 'completed'""",
                (message.from_user.id,)
            )
            user_stats = await cursor.fetchone()

            # Общая статистика
            await cursor.execute(
                """SELECT 
                    COALESCE(SUM(total_stars), 0) as total_stars,
                    COALESCE(SUM(total_spent), 0) as total_spent 
                FROM users"""
            )
            global_stats = await cursor.fetchone()

        # Формирование ответа
        response = [
            "📊 Ваша статистика:",
            f"├ Заказов: {user_stats['orders']}",
            f"└ Получено звёзд: {user_stats['stars']}",
            "",
            "🌐 Общая статистика бота:",
            f"├ Всего звёзд: {global_stats['total_stars']}",
            f"└ Общая выручка: {global_stats['total_spent']:.2f}₽"
        ]

        await message.answer("\n".join(response))

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}", exc_info=True)
        await message.answer("❌ Не удалось получить статистику. Попробуйте позже.")

# Вебхуки
async def telegram_webhook(request: web.Request):
    return await SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=Config.WEBHOOK_SECRET
    ).handle(request)

async def crypto_webhook(request: web.Request):
    body = await request.text()
    sig = request.headers.get("Crypto-Pay-API-Signature", "")
    
    secret = Config.WEBHOOK_SECRET.encode()
    expected_sig = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(sig, expected_sig):
        logger.warning("Invalid CryptoBot signature")
        return web.Response(status=403)
    
    data = json.loads(body)
    if data.get('invoice', {}).get('status') == 'paid':
        async with db.cursor() as cursor:
            await cursor.execute(
                "UPDATE transactions SET status='paid' WHERE invoice_id=?",
                (data['invoice']['id'],)
            )
    
    return web.Response(text="OK")

async def health_check(request: web.Request):
    return web.Response(text="OK")

# Запуск
async def on_startup():
    await db.connect()
    await bot.set_webhook(
        url=Config.WEBHOOK_URL,
        secret_token=Config.WEBHOOK_SECRET
    )
    await notify_admins("🟢 Бот успешно запущен")

async def main():
    Config.validate()
    dp.include_router(router)
    
    app = web.Application()
    app.router.add_post(Config.WEBHOOK_PATH, telegram_webhook)
    app.router.add_post("/crypto_webhook", crypto_webhook)
    app.router.add_get("/healthz", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    
    await on_startup()
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
