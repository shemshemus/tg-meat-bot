from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import OrderCreate, OrderResponse
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all orders, newest first."""
    return order_service.get_all(db, skip=skip, limit=limit)


@router.post("/", response_model=OrderResponse, status_code=201)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    """Create a new order. The product_id must reference an existing product."""
    order = order_service.create(db, data)
    if not order:
        raise HTTPException(status_code=404, detail="Product not found")
    return order


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Get a single order by ID."""
    order = order_service.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/{order_id}/status")
def update_order_status(
    order_id: int,
    status: str = Query(pattern="^(new|confirmed|completed|cancelled)$"),
    db: Session = Depends(get_db),
):
    """Update order status. Valid values: new, confirmed, completed, cancelled."""
    order = order_service.update_status(db, order_id, status)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
