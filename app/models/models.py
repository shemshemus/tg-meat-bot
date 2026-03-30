from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False, default="general")
    price_per_kg = Column(Float, nullable=False)
    description = Column(Text, default="")
    ingredients = Column(Text, default="")
    in_stock = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), default="")
    telegram_user_id = Column(String(50), default="")
    telegram_username = Column(String(100), default="")
    phone = Column(String(20), default="")
    delivery_address = Column(Text, default="")
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_kg = Column(Float, nullable=False)
    note = Column(Text, default="")
    status = Column(String(20), default="new")
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketingPost(Base):
    __tablename__ = "marketing_posts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    generated_text = Column(Text, nullable=False)
    tone = Column(String(30), default="friendly")
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
