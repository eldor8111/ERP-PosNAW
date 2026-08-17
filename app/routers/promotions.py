from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.promotion import Promotion, PromotionProduct
from app.models.product import Product
from app.schemas.promotion import PromotionCreate, PromotionUpdate, PromotionOut
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/promotions", tags=["Promotions"])

@router.post("/", response_model=PromotionOut, status_code=status.HTTP_201_CREATED)
def create_promotion(
    data: PromotionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Asosiy aksiyani yaratish
    db_promo = Promotion(
        company_id=current_user.company_id,
        name=data.name,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        start_date=data.start_date,
        end_date=data.end_date,
        is_active=data.is_active
    )
    db.add(db_promo)
    db.commit()
    db.refresh(db_promo)

    # Mahsulotlarni bog'lash
    for prod in data.products:
        # Mahsulot borligini tekshirish
        p = db.query(Product).filter(Product.id == prod.product_id, Product.company_id == current_user.company_id).first()
        if p:
            promo_product = PromotionProduct(
                promotion_id=db_promo.id,
                product_id=p.id
            )
            db.add(promo_product)
    
    db.commit()
    db.refresh(db_promo)
    return db_promo

@router.get("/", response_model=List[PromotionOut])
def get_promotions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Promotion).filter(Promotion.company_id == current_user.company_id).all()

@router.get("/{promo_id}", response_model=PromotionOut)
def get_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    return promo

@router.put("/{promo_id}", response_model=PromotionOut)
def update_promotion(
    promo_id: int,
    data: PromotionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    
    if data.name is not None:
        promo.name = data.name
    if data.discount_type is not None:
        promo.discount_type = data.discount_type
    if data.discount_value is not None:
        promo.discount_value = data.discount_value
    if data.start_date is not None:
        promo.start_date = data.start_date
    if data.end_date is not None:
        promo.end_date = data.end_date
    if data.is_active is not None:
        promo.is_active = data.is_active

    # Update products if provided
    if data.products is not None:
        db.query(PromotionProduct).filter(PromotionProduct.promotion_id == promo.id).delete()
        for prod in data.products:
            p = db.query(Product).filter(Product.id == prod.product_id, Product.company_id == current_user.company_id).first()
            if p:
                db.add(PromotionProduct(promotion_id=promo.id, product_id=p.id))
    
    db.commit()
    db.refresh(promo)
    return promo

@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    
    db.delete(promo)
    db.commit()
    return None
