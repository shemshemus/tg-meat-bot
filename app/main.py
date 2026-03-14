import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bot.telegram_bot import create_bot_app
from app.database import Base, engine
from app.models import models  # noqa: F401 — registers models with Base
from app.routes import analytics, marketing, orders, products

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the Telegram bot when the server starts, stop it when it shuts down."""
    bot_app = create_bot_app()

    if bot_app:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()
        logger.info("Telegram bot started (polling)")

    yield  # Server is running — handle requests here

    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        logger.info("Telegram bot stopped")


app = FastAPI(
    title="Meat Bot API",
    description="AI Marketing & Order Copilot for a Local Food Business",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(products.router)
app.include_router(orders.router)
app.include_router(marketing.router)
app.include_router(analytics.router)


@app.get("/")
def health_check():
    return {"status": "running", "service": "meat-bot-api"}
