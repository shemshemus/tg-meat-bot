from datetime import datetime

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Product schemas
# ──────────────────────────────────────────────

class ProductCreate(BaseModel):
    """What the client sends to create a product."""

    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="general", max_length=50)
    price_per_kg: float = Field(gt=0)
    description: str = ""
    ingredients: str = ""
    in_stock: bool = True


class ProductUpdate(BaseModel):
    """What the client sends to update a product.
    All fields are optional — only provided fields get updated.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    price_per_kg: float | None = Field(default=None, gt=0)
    description: str | None = None
    ingredients: str | None = None
    in_stock: bool | None = None


class ProductResponse(BaseModel):
    """What the API returns for a product."""

    id: int
    name: str
    category: str
    price_per_kg: float
    description: str
    ingredients: str
    in_stock: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Order schemas
# ──────────────────────────────────────────────

class OrderCreate(BaseModel):
    """What the client sends to create an order."""

    customer_name: str = ""
    telegram_user_id: str = ""
    product_id: int
    quantity_kg: float = Field(gt=0)
    note: str = ""


class OrderResponse(BaseModel):
    """What the API returns for an order."""

    id: int
    customer_name: str
    telegram_user_id: str
    product_id: int
    quantity_kg: float
    note: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Marketing post schemas
# ──────────────────────────────────────────────

class MarketingPostCreate(BaseModel):
    """What the client sends to generate a marketing post."""

    product_id: int
    tone: str = Field(default="friendly", max_length=30)


class MarketingPostResponse(BaseModel):
    """What the API returns for a marketing post."""

    id: int
    product_id: int
    generated_text: str
    tone: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Analytics schemas
# ──────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    """Summary stats for the analytics endpoint."""

    total_products: int
    total_orders: int
    total_marketing_posts: int
    orders_by_status: dict[str, int]
    top_products: list[dict]
