from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import MarketingPost, Order, Product
from app.schemas.schemas import AnalyticsSummary
from app.services import cache_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])

ANALYTICS_TTL = 3600  # 1 hour


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(db: Session = Depends(get_db)):
    """Return high-level business stats (cached for 1 hour)."""
    cached = cache_service.cache_get("analytics:summary")
    if cached is not None:
        return AnalyticsSummary(**cached)

    total_products = db.query(func.count(Product.id)).scalar()
    total_orders = db.query(func.count(Order.id)).scalar()
    total_posts = db.query(func.count(MarketingPost.id)).scalar()

    # Count orders grouped by status → {"new": 5, "confirmed": 3, ...}
    status_rows = (
        db.query(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .all()
    )
    orders_by_status = {status: count for status, count in status_rows}

    # Top 5 products by number of orders
    top_rows = (
        db.query(Product.name, func.count(Order.id).label("order_count"))
        .join(Order, Product.id == Order.product_id)
        .group_by(Product.id, Product.name)
        .order_by(func.count(Order.id).desc())
        .limit(5)
        .all()
    )
    top_products = [
        {"name": name, "order_count": count} for name, count in top_rows
    ]

    summary = AnalyticsSummary(
        total_products=total_products,
        total_orders=total_orders,
        total_marketing_posts=total_posts,
        orders_by_status=orders_by_status,
        top_products=top_products,
    )

    cache_service.cache_set("analytics:summary", summary.model_dump(), ANALYTICS_TTL)
    return summary
