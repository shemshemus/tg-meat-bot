import logging
import random
import re
from datetime import timedelta

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
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
from app.models.models import Order, Product
from app.schemas.schemas import OrderCreate
from app.services import ai_service, cache_service, order_service, product_service

logger = logging.getLogger(__name__)

# In-memory fallbacks (used when Redis is unavailable)
_known_users: set[int] = set()
_user_languages: dict[int, str] = {}
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
        "back_btn": "◀️ Назад в меню",
        "products_header": "📋 Наши товары:\n",
        "no_products": "Сейчас нет товаров в наличии.",
        "order_btn": "Заказать",
        "price_usage": "Использование: /price название продукта",
        "price_not_found": 'Товар "{query}" не найден.\nИспользуйте /products чтобы посмотреть ассортимент.',
        "enter_quantity": 'Сколько штук "{product}" вы хотите? Напишите число:',
        "ask_phone": (
            "📱 Для оформления заказа нам нужен ваш номер телефона.\n\n"
            "Нажмите кнопку ниже, чтобы поделиться номером, "
            "или введите его вручную:"
        ),
        "share_phone_btn": "📱 Поделиться номером",
        "ask_address": "📍 Укажите адрес доставки:",
        "confirm_saved_info": (
            "📋 Используем сохранённые данные?\n\n"
            "📱 Телефон: {phone}\n"
            "📍 Адрес: {address}"
        ),
        "yes_btn": "✅ Да",
        "change_btn": "✏️ Изменить",
        "order_success": (
            "✅ Заказ оформлен!\n\n"
            "Товар: {product}\n"
            "Количество: {qty} шт\n"
            "Сумма: {total}\n"
            "📱 Телефон: {phone}\n"
            "📍 Адрес: {address}\n\n"
            "Мы скоро свяжемся с вами!"
        ),
        "order_error": "Что-то пошло не так. Попробуйте ещё раз.",
        "not_understood": (
            "Не понял вас.\n\n"
            'Попробуйте написать, например: "2 beef sausage"\n'
            "Или нажмите /products чтобы посмотреть ассортимент."
        ),
        "order_more_btn": "🔄 Заказать ещё",
        "back_to_products_btn": "📋 К товарам",
        "no_orders": "📦 У вас пока нет заказов.",
        "orders_header": "📦 Ваши заказы:\n",
        "invalid_quantity": "Пожалуйста, введите целое число (например, 1, 2 или 3).",
        "invalid_phone": "Пожалуйста, введите корректный номер телефона.",
        "lang_set": "Язык установлен: 🇷🇺 Русский",
        "status_new": "новый",
        "status_confirmed": "подтверждён",
        "status_completed": "выполнен",
        "status_cancelled": "отменён",
    },
    "en": {
        "choose_lang": "Выберите язык / Choose your language:",
        "welcome": (
            "Welcome to our meat shop! 🥩\n\n"
            "Choose an action:"
        ),
        "products_btn": "🛒 See Products",
        "orders_btn": "📦 My Orders",
        "back_btn": "◀️ Back to Menu",
        "products_header": "📋 Our products:\n",
        "no_products": "No products available right now.",
        "order_btn": "Order",
        "price_usage": "Usage: /price product name",
        "price_not_found": 'No product matching "{query}".\nUse /products to see what\'s available.',
        "enter_quantity": 'How many "{product}" would you like? Type a number:',
        "ask_phone": (
            "📱 We need your phone number to process the order.\n\n"
            "Tap the button below to share your number, "
            "or type it manually:"
        ),
        "share_phone_btn": "📱 Share Phone Number",
        "ask_address": "📍 Enter your delivery address:",
        "confirm_saved_info": (
            "📋 Use your saved info?\n\n"
            "📱 Phone: {phone}\n"
            "📍 Address: {address}"
        ),
        "yes_btn": "✅ Yes",
        "change_btn": "✏️ Change",
        "order_success": (
            "✅ Order placed!\n\n"
            "Product: {product}\n"
            "Quantity: {qty}\n"
            "Total: {total}\n"
            "📱 Phone: {phone}\n"
            "📍 Address: {address}\n\n"
            "We'll contact you soon!"
        ),
        "order_error": "Something went wrong. Please try again.",
        "not_understood": (
            "I didn't understand that.\n\n"
            'Try something like: "2 beef sausage"\n'
            "Or use /products to see what's available."
        ),
        "order_more_btn": "🔄 Order More",
        "back_to_products_btn": "📋 Back to Products",
        "no_orders": "📦 You have no orders yet.",
        "orders_header": "📦 Your orders:\n",
        "invalid_quantity": "Please enter a whole number (e.g. 1, 2, or 3).",
        "invalid_phone": "Please enter a valid phone number.",
        "lang_set": "Language set: 🇬🇧 English",
        "status_new": "new",
        "status_confirmed": "confirmed",
        "status_completed": "completed",
        "status_cancelled": "cancelled",
    },
}

# Order flow states stored in context.user_data["order_step"]
STEP_QUANTITY = "quantity"
STEP_PHONE = "phone"
STEP_ADDRESS = "address"


def _add_known_user(user_id: int) -> None:
    _known_users.add(user_id)
    cache_service.add_known_user(user_id)


def _get_known_users() -> set[int]:
    users = cache_service.get_known_users()
    return users if users else _known_users


def _set_user_language(user_id: int, lang: str) -> None:
    _user_languages[user_id] = lang
    cache_service.set_user_language(user_id, lang)


def get_lang(user_id: int) -> str:
    lang = cache_service.get_user_language(user_id)
    if lang:
        return lang
    return _user_languages.get(user_id, "ru")


def _set_last_promo(product_id: int) -> None:
    global _last_promo_product_id
    _last_promo_product_id = product_id
    cache_service.set_last_promo_product(product_id)


def _get_last_promo() -> int | None:
    val = cache_service.get_last_promo_product()
    return val if val is not None else _last_promo_product_id


def _clear_order_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove all pending order data from user_data."""
    for key in ("pending_product_id", "pending_quantity", "order_step", "pending_phone"):
        context.user_data.pop(key, None)


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


def _back_button(user_id: int) -> list[InlineKeyboardButton]:
    """Single-element list with a Back to Menu button."""
    return [InlineKeyboardButton(msg("back_btn", user_id), callback_data="menu_main")]


def _format_price(price: float) -> str:
    return f"{price:,.0f} ₸"


def _status_label(status: str, user_id: int) -> str:
    key = f"status_{status}"
    lang = get_lang(user_id)
    return MESSAGES[lang].get(key, status)


# ──────────────────────────────────────────────
# Command handlers
# ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — language selection."""
    _clear_order_state(context)
    _add_known_user(update.effective_user.id)
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
    _clear_order_state(context)
    user_id = update.effective_user.id
    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        in_stock = [p for p in products if p.in_stock]

        if not in_stock:
            await update.message.reply_text(
                msg("no_products", user_id),
                reply_markup=InlineKeyboardMarkup([_back_button(user_id)]),
            )
            return

        lines = []
        buttons = []
        for p in in_stock:
            lines.append(f"• {p.name} ({p.category}) — {_format_price(p.price_per_kg)}")
            buttons.append([InlineKeyboardButton(
                f"{msg('order_btn', user_id)} {p.name}",
                callback_data=f"order_{p.id}",
            )])
        buttons.append(_back_button(user_id))

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
            f"{match.name}: {_format_price(match.price_per_kg)}\n"
            f"{match.description or ''}",
            reply_markup=InlineKeyboardMarkup([_back_button(user_id)]),
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
    _add_known_user(user_id)
    _set_user_language(user_id, lang)

    await query.edit_message_text(msg("lang_set", user_id))
    await query.message.reply_text(
        msg("welcome", user_id),
        reply_markup=_main_menu_keyboard(user_id),
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu buttons (products / orders / back to main)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data
    _clear_order_state(context)

    if action == "menu_main":
        await query.edit_message_text(
            msg("welcome", user_id),
            reply_markup=_main_menu_keyboard(user_id),
        )

    elif action == "menu_products":
        db = SessionLocal()
        try:
            products = product_service.get_all(db)
            in_stock = [p for p in products if p.in_stock]

            if not in_stock:
                await query.edit_message_text(
                    msg("no_products", user_id),
                    reply_markup=InlineKeyboardMarkup([_back_button(user_id)]),
                )
                return

            lines = []
            buttons = []
            for p in in_stock:
                lines.append(f"• {p.name} ({p.category}) — {_format_price(p.price_per_kg)}")
                buttons.append([InlineKeyboardButton(
                    f"{msg('order_btn', user_id)} {p.name}",
                    callback_data=f"order_{p.id}",
                )])
            buttons.append(_back_button(user_id))

            text = msg("products_header", user_id) + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        finally:
            db.close()

    elif action == "menu_orders":
        db = SessionLocal()
        try:
            orders = (
                db.query(Order)
                .filter(Order.telegram_user_id == str(user_id))
                .order_by(Order.created_at.desc())
                .limit(10)
                .all()
            )

            if not orders:
                await query.edit_message_text(
                    msg("no_orders", user_id),
                    reply_markup=InlineKeyboardMarkup([_back_button(user_id)]),
                )
                return

            lines = []
            for o in orders:
                product = product_service.get_by_id(db, o.product_id)
                product_name = product.name if product else f"#{o.product_id}"
                status = _status_label(o.status, user_id)
                date_str = o.created_at.strftime("%d.%m.%Y") if o.created_at else ""
                total = o.quantity_kg * (product.price_per_kg if product else 0)
                lines.append(
                    f"• {product_name} x{int(o.quantity_kg)} — "
                    f"{_format_price(total)} [{status}] {date_str}"
                )
        finally:
            db.close()

        text = msg("orders_header", user_id) + "\n".join(lines)
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    msg("products_btn", user_id), callback_data="menu_products"
                )],
                _back_button(user_id),
            ]),
        )


async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Order <product>' button — ask for quantity."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    product_id = int(query.data.replace("order_", ""))

    context.user_data["pending_product_id"] = product_id
    context.user_data["order_step"] = STEP_QUANTITY

    db = SessionLocal()
    try:
        product = product_service.get_by_id(db, product_id)
        product_name = product.name if product else "?"
    finally:
        db.close()

    await query.edit_message_text(
        msg("enter_quantity", user_id, product=product_name),
        reply_markup=InlineKeyboardMarkup([_back_button(user_id)]),
    )


async def confirm_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Yes, use saved info' or 'Change' buttons."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data  # "confirm_yes" or "confirm_change"

    if action == "confirm_yes":
        # Use saved phone and address
        phone = cache_service.get_user_phone(user_id) or ""
        address = cache_service.get_user_address(user_id) or ""
        context.user_data["pending_phone"] = phone

        await query.edit_message_text(
            query.message.text + "\n\n✅",
        )

        await _place_order_final(update, context, phone, address)

    elif action == "confirm_change":
        # Ask for phone again
        context.user_data["order_step"] = STEP_PHONE
        await query.edit_message_text(query.message.text + "\n\n✏️")
        await _ask_for_phone(update, context, user_id)


# ──────────────────────────────────────────────
# Order flow helpers
# ──────────────────────────────────────────────

async def _ask_for_phone(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Send a message asking for phone number with a Share Contact button."""
    context.user_data["order_step"] = STEP_PHONE
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(msg("share_phone_btn", user_id), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    # Use the bot to send a new message (since we might be coming from a callback)
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=msg("ask_phone", user_id),
        reply_markup=keyboard,
    )


async def _ask_for_address(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Send a message asking for delivery address."""
    context.user_data["order_step"] = STEP_ADDRESS
    await update.message.reply_text(
        msg("ask_address", user_id),
        reply_markup=ReplyKeyboardRemove(),
    )


async def _place_order_final(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    phone: str,
    address: str,
):
    """Create the order in DB with all collected info."""
    user = update.effective_user
    user_id = user.id

    product_id = context.user_data.get("pending_product_id")
    quantity = context.user_data.get("pending_quantity", 1)

    db = SessionLocal()
    try:
        product = product_service.get_by_id(db, product_id)
        if not product:
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id=chat_id, text=msg("order_error", user_id))
            _clear_order_state(context)
            return

        order_data = OrderCreate(
            customer_name=user.full_name or "",
            telegram_user_id=str(user_id),
            telegram_username=user.username or "",
            phone=phone,
            delivery_address=address,
            product_id=product.id,
            quantity_kg=float(quantity),
        )
        order = order_service.create(db, order_data)
    finally:
        db.close()

    _clear_order_state(context)

    if not order:
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text=msg("order_error", user_id))
        return

    # Save phone and address for next time
    cache_service.set_user_phone(user_id, phone)
    cache_service.set_user_address(user_id, address)

    total = quantity * product.price_per_kg
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(msg("order_more_btn", user_id), callback_data="menu_products")],
        _back_button(user_id),
    ])

    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=msg(
            "order_success", user_id,
            product=product.name,
            qty=quantity,
            total=_format_price(total),
            phone=phone,
            address=address,
        ),
        reply_markup=keyboard,
    )


# ──────────────────────────────────────────────
# Contact handler (Telegram Share Contact button)
# ──────────────────────────────────────────────

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shared contact — extract phone number for the order."""
    user_id = update.effective_user.id

    if context.user_data.get("order_step") != STEP_PHONE:
        return

    phone = update.message.contact.phone_number
    context.user_data["pending_phone"] = phone

    await _ask_for_address(update, context, user_id)


# ──────────────────────────────────────────────
# Free-text order parsing (rule-based)
# ──────────────────────────────────────────────

def parse_order_text(text: str, products: list[Product]) -> dict | None:
    """Try to extract quantity and product from free text.

    Examples:
        "2 beef sausage"     → {"quantity": 2, "product": <Product>}
        "3 chicken"          → {"quantity": 3, "product": <Product>}
        "beef sausage 1"     → {"quantity": 1, "product": <Product>}
    """
    text_lower = text.lower().strip()

    # Try to find a number (with optional "kg"/"шт" suffix for backwards compat)
    qty_match = re.search(r"(\d+)\s*(?:kg|шт|pcs|x)?", text_lower)
    if not qty_match:
        return None

    quantity = int(qty_match.group(1))
    if quantity <= 0:
        return None

    # Remove the quantity part to isolate the product name
    remaining = re.sub(r"\d+\s*(?:kg|шт|pcs|x)?", "", text_lower).strip()

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

    return {"quantity": quantity, "product": best_match}


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages — multi-step order flow or free-text order."""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    _add_known_user(user_id)

    order_step = context.user_data.get("order_step")

    # ── Step: user is typing phone number manually ──
    if order_step == STEP_PHONE:
        # Basic phone validation: digits, optional +, spaces, dashes
        phone = re.sub(r"[\s\-()]", "", text)
        if not re.match(r"^\+?\d{7,15}$", phone):
            await update.message.reply_text(msg("invalid_phone", user_id))
            return
        context.user_data["pending_phone"] = phone
        await _ask_for_address(update, context, user_id)
        return

    # ── Step: user is typing delivery address ──
    if order_step == STEP_ADDRESS:
        address = text
        phone = context.user_data.get("pending_phone", "")
        await _place_order_final(update, context, phone, address)
        return

    # ── Step: user is typing quantity after clicking "Order" button ──
    pending_product_id = context.user_data.get("pending_product_id")
    if pending_product_id and order_step == STEP_QUANTITY:
        try:
            quantity = int(text.replace(",", ".").split(".")[0])
            if quantity <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(msg("invalid_quantity", user_id))
            return

        context.user_data["pending_quantity"] = quantity

        # Check if we have saved contact info for this user
        saved_phone = cache_service.get_user_phone(user_id)
        saved_address = cache_service.get_user_address(user_id)

        if saved_phone and saved_address:
            # Offer to reuse saved info
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(msg("yes_btn", user_id), callback_data="confirm_yes"),
                    InlineKeyboardButton(msg("change_btn", user_id), callback_data="confirm_change"),
                ]
            ])
            await update.message.reply_text(
                msg("confirm_saved_info", user_id, phone=saved_phone, address=saved_address),
                reply_markup=keyboard,
            )
        else:
            # First-time user — ask for phone
            await _ask_for_phone(update, context, user_id)
        return

    # ── Scenario: free-text order (e.g. "2 beef sausage") ──
    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        parsed = parse_order_text(text, products)
    finally:
        db.close()

    if not parsed:
        await update.message.reply_text(msg("not_understood", user_id))
        return

    # Start the order flow for free-text orders too
    context.user_data["pending_product_id"] = parsed["product"].id
    context.user_data["pending_quantity"] = parsed["quantity"]

    saved_phone = cache_service.get_user_phone(user_id)
    saved_address = cache_service.get_user_address(user_id)

    if saved_phone and saved_address:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(msg("yes_btn", user_id), callback_data="confirm_yes"),
                InlineKeyboardButton(msg("change_btn", user_id), callback_data="confirm_change"),
            ]
        ])
        await update.message.reply_text(
            msg("confirm_saved_info", user_id, phone=saved_phone, address=saved_address),
            reply_markup=keyboard,
        )
    else:
        await _ask_for_phone(update, context, user_id)


# ──────────────────────────────────────────────
# Scheduled promo posts
# ──────────────────────────────────────────────

PROMO_TONES = ["friendly", "professional", "funny", "urgent"]


async def send_promo_post(context: ContextTypes.DEFAULT_TYPE):
    """Send a promotional post about a random product to all known users."""
    users = _get_known_users()

    if not users:
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
    last_promo_id = _get_last_promo()
    candidates = [p for p in in_stock if p.id != last_promo_id]
    if not candidates:
        candidates = in_stock
    product = random.choice(candidates)
    _set_last_promo(product.id)

    tone = random.choice(PROMO_TONES)

    # Cache generated text per language to avoid duplicate AI calls
    promo_texts: dict[str, str] = {}

    ORDER_BTN_LABEL = {"ru": "Заказать", "en": "Order"}

    sent = 0
    for user_id in list(users):
        lang = get_lang(user_id)

        if lang not in promo_texts:
            marketing_text = ai_service.generate_post(product, tone, language=lang)
            promo_texts[lang] = (
                f"\U0001f525 {marketing_text}\n\n"
                f"\U0001f4b0 {_format_price(product.price_per_kg)}"
            )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{ORDER_BTN_LABEL.get(lang, ORDER_BTN_LABEL['ru'])} {product.name}",
                callback_data=f"order_{product.id}",
            )]
        ])

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=promo_texts[lang],
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
    app.add_handler(CallbackQueryHandler(confirm_info_callback, pattern="^confirm_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(order_callback, pattern="^order_"))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Schedule promotional posts every 1.5 days, first run after 1 minute
    app.job_queue.run_repeating(
        send_promo_post,
        interval=timedelta(days=1, hours=12),
        first=timedelta(minutes=1),
    )

    return app
