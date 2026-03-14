import logging
import re

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import settings
from app.database import SessionLocal
from app.models.models import Product
from app.schemas.schemas import OrderCreate
from app.services import order_service, product_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Command handlers
#
# The bot can't use FastAPI's Depends(get_db) — that only works
# inside HTTP request handlers. So we manage sessions manually:
#   db = SessionLocal() / try / finally: db.close()
# ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — welcome message."""
    await update.message.reply_text(
        "Welcome to our meat shop! 🥩\n\n"
        "Here's what I can do:\n"
        "/products — see what's available\n"
        "/price <product name> — check a price\n\n"
        "Or just type something like:\n"
        "\"2 kg beef sausage\"\n"
        "and I'll place an order for you!"
    )


async def products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /products — list all in-stock products."""
    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        in_stock = [p for p in products if p.in_stock]

        if not in_stock:
            await update.message.reply_text("No products available right now.")
            return

        lines = []
        for p in in_stock:
            lines.append(f"• {p.name} ({p.category}) — ${p.price_per_kg:.2f}/kg")

        text = "📋 Our products:\n\n" + "\n".join(lines)
        await update.message.reply_text(text)
    finally:
        db.close()


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /price <product name> — show price for a specific product."""
    if not context.args:
        await update.message.reply_text("Usage: /price beef sausage")
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
            await update.message.reply_text(
                f"No product matching \"{query}\".\n"
                f"Use /products to see what's available."
            )
            return

        await update.message.reply_text(
            f"{match.name}: ${match.price_per_kg:.2f}/kg\n"
            f"{match.description or ''}"
        )
    finally:
        db.close()


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
    """Handle free-text messages — try to parse as an order."""
    text = update.message.text

    db = SessionLocal()
    try:
        products = product_service.get_all(db)
        parsed = parse_order_text(text, products)

        if not parsed:
            await update.message.reply_text(
                "I didn't understand that.\n\n"
                "Try something like: \"2 kg beef sausage\"\n"
                "Or use /products to see what's available."
            )
            return

        product = parsed["product"]
        quantity = parsed["quantity_kg"]
        user = update.effective_user

        order_data = OrderCreate(
            customer_name=user.full_name or "",
            telegram_user_id=str(user.id),
            product_id=product.id,
            quantity_kg=quantity,
        )

        order = order_service.create(db, order_data)

        if not order:
            await update.message.reply_text("Something went wrong. Please try again.")
            return

        total = quantity * product.price_per_kg
        await update.message.reply_text(
            f"✅ Order placed!\n\n"
            f"Product: {product.name}\n"
            f"Quantity: {quantity} kg\n"
            f"Total: ${total:.2f}\n\n"
            f"We'll confirm your order soon!"
        )
    finally:
        db.close()


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app
