import logging
import random
import re
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import settings
from app.database import SessionLocal
from app.models.models import Product
from app.schemas.schemas import OrderCreate
from app.services import ai_service, order_service, product_service

logger = logging.getLogger(__name__)

# Users who have interacted with the bot (for promo broadcasts)
known_users: set[int] = set()

# Avoid promoting the same product twice in a row
_last_promo_product_id: int | None = None


# ──────────────────────────────────────────────
# i18n
# ──────────────────────────────────────────────

MESSAGES = {
    "ru": {
        "choose_lang": "Выберите язык / Choose your language:",
        "welcome": (
            "Добро пожаловать в наш мясной магазин! 🥩\n\n"
            "Выберите действие:"
        ),
        "products_btn": "🛒 Наши товары",
        "orders_btn": "📦 Мои заказы",
        "products_header": "📋 Наши товары:\n",
        "no_products": "Сейчас нет товаров в наличии.",
        "order_btn": "Заказать",
        "price_usage": "Использование: /price название продукта",
        "price_not_found": 'Товар "{query}" не найден.\nИспользуйте /products чтобы посмотреть ассортимент.',
        "enter_quantity": 'Сколько кг "{product}" вы хотите? Напишите число:',
        "order_success": (
            "✅ Заказ оформлен!\n\n"
            "Товар: {product}\n"
            "Количество: {qty} кг\n"
            "Сумма: {total} ₸\n\n"
            "Мы скоро подтвердим ваш заказ!"
        ),
        "order_error": "Что-то пошло не так. Попробуйте ещё раз.",
        "not_understood": (
            "Не понял вас.\n\n"
            'Попробуйте написать, например: "2 kg beef sausage"\n'
            "Или нажмите /products чтобы посмотреть ассортимент."
        ),
        "order_more_btn": "🔄 Заказать ещё",
        "back_to_products_btn": "📋 К товарам",
        "orders_coming_soon": "📦 История заказов скоро будет доступна!",
        "invalid_quantity": "Пожалуйста, введите число (например, 2 или 1.5).",
        "lang_set": "Язык установлен: 🇷🇺 Русский",
    },
    "en": {
        "choose_lang": "Выберите язык / Choose your language:",
        "welcome": (
            "Welcome to our meat shop! 🥩\n\n"
            "Choose an action:"
        ),
        "products_btn": "🛒 See Products",
        "orders_btn": "📦 My Orders",
        "products_header": "📋 Our products:\n",
        "no_products": "No products available right now.",
        "order_btn": "Order",
        "price_usage": "Usage: /price product name",
        "price_not_found": 'No product matching "{query}".\nUse /products to see what\'s available.',
        "enter_quantity": 'How many kg of "{product}" would you like? Type a number:',
        "order_success": (
            "✅ Order placed!\n\n"
            "Product: {product}\n"
            "Quantity: {qty} kg\n"
            "Total: {total} ₸\n\n"
            "We'll confirm your order soon!"
        ),
        "order_error": "Something went wrong. Please try again.",
        "not_understood": (
            "I didn't understand that.\n\n"
            'Try something like: "2 kg beef sausage"\n'
            "Or use /products to see what's available."
        ),
        "order_more_btn": "🔄 Order More",
        "back_to_products_btn": "📋 Back to Products",
        "orders_coming_soon": "📦 Order history coming soon!",
        "invalid_quantity": "Please enter a number (e.g. 2 or 1.5).",
        "lang_set": "Language set: 🇬🇧 English",
    },
}

user_languages: dict[int, str] = {}


def get_lang(user_id: int) -> str:
    return user_languages.get(user_id, "ru")


def msg(key: str, user_id: int, **kwargs) -> str:
    lang = get_lang(user_id)
    return MESSAGES[lang][key].format(**kwargs) if kwargs else MESSAGES[lang][key]


def _main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("products_btn", user_id), callback_data="menu_products"),
            InlineKeyboardButton(msg("orders_btn", user_id), callback_data="menu_orders"),
        ]
    ])


def _format_price(price: float) -> str:
    return f"{price:,.0f} ₸"


# ──────────────────────────────────────────────
# Command handlers
# ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — language selection."""
    known_users.add(update.effective_user.id)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])
    await update.message.reply_text(
        "Выберите язык / Choose your language:",
        reply_markup=keyboard,
    )


async def products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /products — list all in-stock products with Order buttons."""
    user_id = update.effective_user.id
    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        in_stock = [p for p in products if p.in_stock]

        if not in_stock:
            await update.message.reply_text(msg("no_products", user_id))
            return

        lines = []
        buttons = []
        for p in in_stock:
            lines.append(f"• {p.name} ({p.category}) — {_format_price(p.price_per_kg)}/кг")
            buttons.append([InlineKeyboardButton(
                f"{msg('order_btn', user_id)} {p.name}",
                callback_data=f"order_{p.id}",
            )])

        text = msg("products_header", user_id) + "\n".join(lines)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    finally:
        db.close()


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /price <product name> — show price for a specific product."""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(msg("price_usage", user_id))
        return

    query = " ".join(context.args).lower()

    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        match = None
        for p in products:
            if query in p.name.lower():
                match = p
                break

        if not match:
            await update.message.reply_text(msg("price_not_found", user_id, query=query))
            return

        await update.message.reply_text(
            f"{match.name}: {_format_price(match.price_per_kg)}/кг\n"
            f"{match.description or ''}"
        )
    finally:
        db.close()


# ──────────────────────────────────────────────
# Callback handlers (inline buttons)
# ──────────────────────────────────────────────

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection buttons."""
    query = update.callback_query
    await query.answer()

    lang = query.data.replace("lang_", "")  # "ru" or "en"
    user_id = query.from_user.id
    known_users.add(user_id)
    user_languages[user_id] = lang

    await query.edit_message_text(msg("lang_set", user_id))
    await query.message.reply_text(
        msg("welcome", user_id),
        reply_markup=_main_menu_keyboard(user_id),
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu buttons (products / orders)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data  # "menu_products" or "menu_orders"

    if action == "menu_products":
        db = SessionLocal()
        try:
            products = product_service.get_all(db)
            in_stock = [p for p in products if p.in_stock]

            if not in_stock:
                await query.edit_message_text(msg("no_products", user_id))
                return

            lines = []
            buttons = []
            for p in in_stock:
                lines.append(f"• {p.name} ({p.category}) — {_format_price(p.price_per_kg)}/кг")
                buttons.append([InlineKeyboardButton(
                    f"{msg('order_btn', user_id)} {p.name}",
                    callback_data=f"order_{p.id}",
                )])

            text = msg("products_header", user_id) + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        finally:
            db.close()

    elif action == "menu_orders":
        await query.edit_message_text(msg("orders_coming_soon", user_id))


async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Order <product>' button — ask for quantity."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    product_id = int(query.data.replace("order_", ""))

    context.user_data["pending_product_id"] = product_id

    db = SessionLocal()
    try:
        product = product_service.get_by_id(db, product_id)
        product_name = product.name if product else "?"
    finally:
        db.close()

    await query.edit_message_text(msg("enter_quantity", user_id, product=product_name))


# ──────────────────────────────────────────────
# Order placement helper
# ──────────────────────────────────────────────

async def _place_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product: Product,
    quantity: float,
):
    """Create order and send confirmation message."""
    user = update.effective_user
    user_id = user.id

    db = SessionLocal()
    try:
        order_data = OrderCreate(
            customer_name=user.full_name or "",
            telegram_user_id=str(user.id),
            product_id=product.id,
            quantity_kg=quantity,
        )
        order = order_service.create(db, order_data)
    finally:
        db.close()

    if not order:
        await update.message.reply_text(msg("order_error", user_id))
        return

    total = quantity * product.price_per_kg
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("order_more_btn", user_id), callback_data="menu_products"),
            InlineKeyboardButton(msg("back_to_products_btn", user_id), callback_data="menu_products"),
        ]
    ])
    await update.message.reply_text(
        msg("order_success", user_id, product=product.name, qty=quantity, total=_format_price(total)),
        reply_markup=keyboard,
    )


# ──────────────────────────────────────────────
# Free-text order parsing (rule-based)
# ──────────────────────────────────────────────

def parse_order_text(text: str, products: list[Product]) -> dict | None:
    """Try to extract quantity and product from free text.

    Examples:
        "2 kg beef sausage"  → {"quantity_kg": 2.0, "product": <Product>}
        "3.5kg chicken"      → {"quantity_kg": 3.5, "product": <Product>}
        "beef sausage 1 kg"  → {"quantity_kg": 1.0, "product": <Product>}
    """
    text_lower = text.lower().strip()

    # Try to find a number followed by "kg" (or "kg" preceded by a number)
    qty_match = re.search(r"(\d+\.?\d*)\s*kg", text_lower)
    if not qty_match:
        return None

    quantity = float(qty_match.group(1))
    if quantity <= 0:
        return None

    # Remove the quantity part to isolate the product name
    remaining = re.sub(r"\d+\.?\d*\s*kg", "", text_lower).strip()

    # Find the best matching product
    best_match = None
    best_score = 0
    for p in products:
        name_lower = p.name.lower()
        # Check if any word from the message matches the product name
        words = remaining.split()
        matching_words = sum(1 for w in words if w in name_lower)
        if matching_words > best_score:
            best_score = matching_words
            best_match = p

    if not best_match or best_score == 0:
        return None

    return {"quantity_kg": quantity, "product": best_match}


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages — quantity input or free-text order."""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    known_users.add(user_id)

    # Scenario A: user typed quantity after clicking "Order" button
    pending_product_id = context.user_data.get("pending_product_id")
    if pending_product_id:
        context.user_data.pop("pending_product_id")
        try:
            quantity = float(text.replace(",", "."))
            if quantity <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(msg("invalid_quantity", user_id))
            return

        db = SessionLocal()
        try:
            product = product_service.get_by_id(db, pending_product_id)
        finally:
            db.close()

        if not product:
            await update.message.reply_text(msg("order_error", user_id))
            return

        await _place_order(update, context, product, quantity)
        return

    # Scenario B: free-text order (e.g. "2 kg beef sausage")
    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        parsed = parse_order_text(text, products)
    finally:
        db.close()

    if not parsed:
        await update.message.reply_text(msg("not_understood", user_id))
        return

    await _place_order(update, context, parsed["product"], parsed["quantity_kg"])


# ──────────────────────────────────────────────
# Scheduled promo posts
# ──────────────────────────────────────────────

PROMO_TONES = ["friendly", "professional", "funny", "urgent"]


async def send_promo_post(context: ContextTypes.DEFAULT_TYPE):
    """Send a promotional post about a random product to all known users."""
    global _last_promo_product_id

    if not known_users:
        logger.info("Promo skipped — no known users yet")
        return

    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        in_stock = [p for p in products if p.in_stock]
    finally:
        db.close()

    if not in_stock:
        logger.info("Promo skipped — no products in stock")
        return

    # Pick a random product, avoiding the last promoted one
    candidates = [p for p in in_stock if p.id != _last_promo_product_id]
    if not candidates:
        candidates = in_stock
    product = random.choice(candidates)
    _last_promo_product_id = product.id

    tone = random.choice(PROMO_TONES)
    marketing_text = ai_service.generate_post(product, tone)

    promo_message = (
        f"\U0001f525 {marketing_text}\n\n"
        f"\U0001f4b0 {_format_price(product.price_per_kg)}/кг"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Заказать {product.name}", callback_data=f"order_{product.id}")]
    ])

    sent = 0
    for user_id in list(known_users):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=promo_message,
                reply_markup=keyboard,
            )
            sent += 1
        except Exception:
            logger.debug("Could not send promo to user %s", user_id)

    logger.info("Promo sent to %d users (product: %s, tone: %s)", sent, product.name, tone)


# ──────────────────────────────────────────────
# Bot setup
# ──────────────────────────────────────────────

def create_bot_app() -> Application | None:
    """Create and configure the Telegram bot application."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return None

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("products", products_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(order_callback, pattern="^order_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Schedule promotional posts every 1.5 days, first run after 1 minute
    app.job_queue.run_repeating(
        send_promo_post,
        interval=timedelta(days=1, hours=12),
        first=timedelta(minutes=1),
    )

    return app
