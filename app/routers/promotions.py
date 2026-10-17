from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from pydantic import BaseModel

from app.core.audit import log_action
from app.database import get_db
from app.models.promotion import Promotion, PromotionProduct, PromotionBranch
from app.models.branch import Branch
from app.models.product import Product
from app.schemas.promotion import PromotionCreate, PromotionUpdate, PromotionOut
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User, UserRole

router = APIRouter(prefix="/promotions", tags=["Promotions"])

# Aksiyani yaratish/o'zgartirish/o'chirish — faqat rahbariyat (kassir/omborchi emas)
PROMO_WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)


def _load_products(db: Session, company_id: int, items) -> list:
    """Aksiya mahsulotlari: har bir `product_id` shu korxonaning o'chirilmagan mahsuloti bo'lishi shart.
    Begona/o'chirilgan mahsulot jim o'tkazib yuborilmaydi — 400."""
    ids = []
    for it in items or []:
        if it.product_id not in ids:
            ids.append(it.product_id)
    if not ids:
        return []
    found = {
        p.id: p for p in db.query(Product).filter(
            Product.id.in_(ids),
            Product.company_id == company_id,
            Product.is_deleted == False,  # noqa: E712
        ).all()
    }
    for pid in ids:
        if pid not in found:
            raise HTTPException(status_code=400, detail=f"Mahsulot ID={pid} topilmadi")
    return [found[pid] for pid in ids]


BRANCH_NOT_FOUND = "Filial topilmadi"


def _load_branch_ids(db: Session, company_id: int, branch_ids) -> list:
    """T4.3: aksiya filiallari — har biri shu korxonaniki bo'lishi shart, aks holda 404 (begona filial
    mavjudligi oshkor qilinmaydi). Takrorlar olib tashlanadi, tartib saqlanadi."""
    ids = []
    for b in branch_ids or []:
        if b not in ids:
            ids.append(b)
    if not ids:
        return []
    found = {
        r[0] for r in db.query(Branch.id).filter(Branch.id.in_(ids), Branch.company_id == company_id).all()
    }
    if any(b not in found for b in ids):
        raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    return ids


def _promo_query(db: Session):
    return db.query(Promotion).options(
        joinedload(Promotion.products).joinedload(PromotionProduct.product),
        joinedload(Promotion.branches),
    ).execution_options(populate_existing=True)


@router.post("/", response_model=PromotionOut, status_code=status.HTTP_201_CREATED)
def create_promotion(
    data: PromotionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PROMO_WRITE_ROLES))
):
    # Mahsulotlar commit'dan oldin tekshiriladi (begona ID bo'lsa aksiya yaratilmaydi)
    products = _load_products(db, current_user.company_id, data.products) if data.applies_to == "products" else []
    branch_ids = _load_branch_ids(db, current_user.company_id, data.branch_ids)

    db_promo = Promotion(
        company_id=current_user.company_id,
        name=data.name,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        start_date=data.start_date,
        end_date=data.end_date,
        is_active=data.is_active,
        applies_to=data.applies_to,
    )
    db.add(db_promo)
    db.flush()

    for p in products:
        db.add(PromotionProduct(promotion_id=db_promo.id, product_id=p.id))
    for bid in branch_ids:
        db.add(PromotionBranch(promotion_id=db_promo.id, branch_id=bid))

    db.commit()
    return _promo_query(db).filter(Promotion.id == db_promo.id).first()

@router.get("/", response_model=List[PromotionOut])
def get_promotions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _promo_query(db).filter(Promotion.company_id == current_user.company_id).all()

@router.get("/active", response_model=List[PromotionOut])
def get_active_promotions_endpoint(
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """T4.3: hozir amal qilayotgan aksiyalar (faol, sana oralig'ida, shu filialga mos). `branch_id` berilmasa
    xodimning joriy filiali; filial aniqlanmasa faqat hamma filialga tegishli aksiyalar."""
    from app.services.promotion_service import get_active_promotions

    if branch_id is not None:
        _load_branch_ids(db, current_user.company_id, [branch_id])
    else:
        from app.core.branch_context import effective_branch_id
        branch_id = effective_branch_id(db, current_user)
    ids = [p.id for p in get_active_promotions(db, current_user.company_id, branch_id)]
    if not ids:
        return []
    return _promo_query(db).filter(Promotion.id.in_(ids)).order_by(Promotion.id.asc()).all()

class PromotionSettingsIn(BaseModel):
    auto_apply: bool


@router.get("/settings")
def get_promotion_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """T4.3: korxona aksiya sozlamalari. `auto_apply` — server `promotion_id`siz sotuv qatoriga eng yaxshi
    mos aksiyani o'zi qo'llaydi (sukut o'chiq)."""
    from app.services.promotion_service import company_auto_apply
    return {"auto_apply": company_auto_apply(db, current_user.company_id)}


@router.put("/settings")
def update_promotion_settings(
    data: PromotionSettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    from app.models.company import Company

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    old = bool(company.promotions_auto_apply)
    company.promotions_auto_apply = bool(data.auto_apply)
    if old != company.promotions_auto_apply:
        log_action(
            db, "PROMOTIONS_AUTO_APPLY", "company", company.id, current_user.id,
            old_values={"promotions_auto_apply": old}, new_values={"promotions_auto_apply": company.promotions_auto_apply},
            company_id=company.id,
        )
    db.commit()
    return {"auto_apply": bool(company.promotions_auto_apply)}


@router.get("/{promo_id}", response_model=PromotionOut)
def get_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    promo = _promo_query(db).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    return promo

@router.put("/{promo_id}", response_model=PromotionOut)
def update_promotion(
    promo_id: int,
    data: PromotionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PROMO_WRITE_ROLES))
):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")

    fields_set = data.model_fields_set

    # Birlashgan (yangi + eski) qiymatlarni tekshirish
    new_type = data.discount_type if data.discount_type is not None else promo.discount_type
    new_value = data.discount_value if data.discount_value is not None else promo.discount_value
    if data.discount_type is not None or data.discount_value is not None:
        if new_value is None or new_value <= 0:
            raise HTTPException(status_code=422, detail="Chegirma qiymati 0 dan katta bo'lishi kerak")
        if new_type == "percent" and new_value > 100:
            raise HTTPException(status_code=422, detail="Foiz chegirma 100 dan oshmasligi kerak")
    new_start = data.start_date if "start_date" in fields_set else promo.start_date
    new_end = data.end_date if "end_date" in fields_set else promo.end_date
    if new_start is not None and new_end is not None and new_end.replace(tzinfo=None) < new_start.replace(tzinfo=None):
        raise HTTPException(status_code=422, detail="Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas")

    new_applies = data.applies_to if data.applies_to is not None else promo.applies_to
    products = None
    if new_applies == "all":
        if data.applies_to == "all" or data.products is not None:
            products = []  # "Barcha mahsulotlar" — eski tanlov tozalanadi
    elif data.products is not None:
        products = _load_products(db, current_user.company_id, data.products)
    branch_ids = _load_branch_ids(db, current_user.company_id, data.branch_ids) if data.branch_ids is not None else None
    if new_applies == "products":
        remaining = len(products) if products is not None else len(promo.products)
        if remaining == 0:
            raise HTTPException(status_code=422, detail="Tanlangan mahsulotlar qamrovi uchun kamida bitta mahsulot kerak")

    if data.name is not None:
        promo.name = data.name
    if data.discount_type is not None:
        promo.discount_type = data.discount_type
    if data.discount_value is not None:
        promo.discount_value = data.discount_value
    # Sanani aniq `null` bilan bo'shatish mumkin
    if "start_date" in fields_set:
        promo.start_date = data.start_date
    if "end_date" in fields_set:
        promo.end_date = data.end_date
    if data.is_active is not None:
        promo.is_active = data.is_active
    promo.applies_to = new_applies

    if products is not None:
        db.query(PromotionProduct).filter(PromotionProduct.promotion_id == promo.id).delete()
        db.expire(promo, ["products"])
        for p in products:
            db.add(PromotionProduct(promotion_id=promo.id, product_id=p.id))

    if branch_ids is not None:
        db.query(PromotionBranch).filter(PromotionBranch.promotion_id == promo.id).delete()
        db.expire(promo, ["branches"])
        for bid in branch_ids:
            db.add(PromotionBranch(promotion_id=promo.id, branch_id=bid))

    db.commit()
    return _promo_query(db).filter(Promotion.id == promo.id).first()

@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PROMO_WRITE_ROLES))
):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.company_id == current_user.company_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    
    db.delete(promo)
    db.commit()
    return None
