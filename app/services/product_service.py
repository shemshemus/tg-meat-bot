from sqlalchemy.orm import Session

from app.models.models import Product
from app.schemas.schemas import ProductCreate, ProductUpdate
from app.services import cache_service

PRODUCTS_TTL = 300  # 5 minutes


def _product_to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category,
        "price_per_kg": p.price_per_kg,
        "description": p.description,
        "ingredients": p.ingredients,
        "in_stock": p.in_stock,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _dict_to_product(d: dict) -> Product:
    from datetime import datetime
    p = Product(
        id=d["id"],
        name=d["name"],
        category=d["category"],
        price_per_kg=d["price_per_kg"],
        description=d["description"],
        ingredients=d["ingredients"],
        in_stock=d["in_stock"],
    )
    if d.get("created_at"):
        p.created_at = datetime.fromisoformat(d["created_at"])
    return p


def get_all(db: Session, skip: int = 0, limit: int = 50) -> list[Product]:
    """Return a paginated list of products, cached for 5 minutes."""
    cache_key = f"products:all:{skip}:{limit}"
    cached = cache_service.cache_get(cache_key)
    if cached is not None:
        return [_dict_to_product(d) for d in cached]

    products = db.query(Product).offset(skip).limit(limit).all()
    cache_service.cache_set(cache_key, [_product_to_dict(p) for p in products], PRODUCTS_TTL)
    return products


def get_by_id(db: Session, product_id: int) -> Product | None:
    """Return a single product by ID, cached for 5 minutes."""
    cache_key = f"products:{product_id}"
    cached = cache_service.cache_get(cache_key)
    if cached is not None:
        return _dict_to_product(cached)

    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        cache_service.cache_set(cache_key, _product_to_dict(product), PRODUCTS_TTL)
    return product


def _invalidate_products_cache() -> None:
    """Delete all product cache keys matching products:*."""
    client = cache_service.get_client()
    if not client:
        return
    try:
        keys = client.keys("products:*")
        if keys:
            client.delete(*keys)
    except Exception:
        pass


def create(db: Session, data: ProductCreate) -> Product:
    """Create a new product and invalidate cache."""
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    _invalidate_products_cache()
    return product


def update(db: Session, product_id: int, data: ProductUpdate) -> Product | None:
    """Update an existing product and invalidate cache."""
    product = get_by_id(db, product_id)
    if not product:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    _invalidate_products_cache()
    return product
