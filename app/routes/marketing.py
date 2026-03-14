from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import MarketingPost
from app.schemas.schemas import MarketingPostCreate, MarketingPostResponse
from app.services import ai_service, product_service

router = APIRouter(prefix="/marketing", tags=["Marketing"])


@router.post("/generate-post", response_model=MarketingPostResponse, status_code=201)
def generate_post(data: MarketingPostCreate, db: Session = Depends(get_db)):
    """Generate a marketing post for a product and save it to the database."""
    product = product_service.get_by_id(db, data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    generated_text = ai_service.generate_post(product, data.tone)

    post = MarketingPost(
        product_id=data.product_id,
        generated_text=generated_text,
        tone=data.tone,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("/posts", response_model=list[MarketingPostResponse])
def list_posts(db: Session = Depends(get_db)):
    """List all generated marketing posts."""
    return db.query(MarketingPost).order_by(MarketingPost.created_at.desc()).all()
