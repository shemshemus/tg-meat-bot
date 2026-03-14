from sqlalchemy.orm import Session

from app.models.models import Order, Product
from app.schemas.schemas import OrderCreate


def get_all(db: Session, skip: int = 0, limit: int = 50) -> list[Order]:
    """Return a paginated list of orders, newest first."""
    return (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create(db: Session, data: OrderCreate) -> Order | None:
    """Create a new order. Returns None if the product doesn't exist."""
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        return None

    order = Order(**data.model_dump())
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_by_id(db: Session, order_id: int) -> Order | None:
    """Return a single order by ID, or None if not found."""
    return db.query(Order).filter(Order.id == order_id).first()


def update_status(db: Session, order_id: int, status: str) -> Order | None:
    """Update an order's status. Returns None if not found."""
    order = get_by_id(db, order_id)
    if not order:
        return None

    order.status = status
    db.commit()
    db.refresh(order)
    return order
