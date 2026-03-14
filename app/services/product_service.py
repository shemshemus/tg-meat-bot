from sqlalchemy.orm import Session

from app.models.models import Product
from app.schemas.schemas import ProductCreate, ProductUpdate


def get_all(db: Session, skip: int = 0, limit: int = 50) -> list[Product]:
    """Return a paginated list of products."""
    return db.query(Product).offset(skip).limit(limit).all()


def get_by_id(db: Session, product_id: int) -> Product | None:
    """Return a single product by ID, or None if not found."""
    return db.query(Product).filter(Product.id == product_id).first()


def create(db: Session, data: ProductCreate) -> Product:
    """Create a new product and return it."""
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update(db: Session, product_id: int, data: ProductUpdate) -> Product | None:
    """Update an existing product. Returns None if not found."""
    product = get_by_id(db, product_id)
    if not product:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product
