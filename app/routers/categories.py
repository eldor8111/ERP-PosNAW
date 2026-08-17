from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.category import Category
from app.models.user import User, UserRole
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["Categories"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse)


@router.get("/", response_model=List[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Faqat ota kategoriyalar, children ichiga kiritiladi
    q = db.query(Category).filter(Category.parent_id == None, Category.is_deleted == False)
    q = q.filter(Category.company_id == current_user.company_id)
    return q.order_by(Category.sort_order).all()


@router.get("/all", response_model=List[CategoryOut])
def list_all_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Category).filter(Category.is_deleted == False)
    q = q.filter(Category.company_id == current_user.company_id)
    return q.order_by(Category.sort_order).all()


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Category).filter(Category.id == category_id, Category.is_deleted == False)
    q = q.filter(Category.company_id == current_user.company_id)
    cat = q.first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    return cat


@router.post("/", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    if data.parent_id:
        parent = db.query(Category).filter(Category.id == data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Ota kategoriya topilmadi")

    cat = Category(name=data.name, parent_id=data.parent_id, sort_order=data.sort_order, is_perishable=data.is_perishable, company_id=current_user.company_id)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    q = db.query(Category).filter(Category.id == category_id, Category.is_deleted == False)
    q = q.filter(Category.company_id == current_user.company_id)
    cat = q.first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")

    if data.name is not None:
        cat.name = data.name
    if data.parent_id is not None:
        cat.parent_id = data.parent_id
    if data.sort_order is not None:
        cat.sort_order = data.sort_order
    if data.is_perishable is not None:
        cat.is_perishable = data.is_perishable

    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    q = db.query(Category).filter(Category.id == category_id, Category.is_deleted == False)
    q = q.filter(Category.company_id == current_user.company_id)
    cat = q.first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")

    # Soft delete: faqat is_deleted ni True qilamiz
    # Lekin agar mahsuloti bo'lsa o'chirmaslik mantiqli bo'lishi mumkin (yoki soft delete bo'lgani uchun ruxsat berish)
    # User filter qilishni so'raganiga ko'ra, soft delete qilamiz.
    
    cat.is_deleted = True
    db.commit()

@router.post("/seed-clothing")
def seed_clothing_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    """Kiyim-kechak uchun tayyor kategoriyalarni kiritadi."""
    clothing = [
        {"name": "Erkaklar kiyimi", "sub": ["Kostyum-shim", "Ko'ylaklar", "T-shirt (Futbolka)", "Jinsi va shimlar", "Kurtka va paltolar", "Poyabzal", "Aksessuarlar"]},
        {"name": "Ayollar kiyimi", "sub": ["Ko'ylak va yubkalar", "Bluzkalar", "T-shirt va toplar", "Jinsi va shimlar", "Kurtka va paltolar", "Poyabzal", "Aksessuarlar"]},
        {"name": "Bolalar kiyimi", "sub": ["O'g'il bolalar kiyimi", "Qiz bolalar kiyimi", "Chaqaloqlar kiyimi", "Maktab formasi", "Oyoq kiyimlar"]},
        {"name": "Sport kiyimlari", "sub": ["Sport kostyumlari", "Krossovkalar", "Sport anjomlari"]},
        {"name": "Uy kiyimlari", "sub": ["Pijamalar", "Uy shippaklari"]}
    ]
    
    count = 0
    for idx, main_cat in enumerate(clothing):
        # Ota kategoriyani qidirish yoki yaratish
        parent = db.query(Category).filter(Category.name == main_cat["name"], Category.company_id == current_user.company_id, Category.is_deleted == False).first()
        if not parent:
            parent = Category(name=main_cat["name"], sort_order=idx*10, company_id=current_user.company_id)
            db.add(parent)
            db.flush()
            count += 1
            
        # Quyi kategoriyalarni qidirish yoki yaratish
        for sub_idx, sub_name in enumerate(main_cat["sub"]):
            sub = db.query(Category).filter(Category.name == sub_name, Category.parent_id == parent.id, Category.company_id == current_user.company_id, Category.is_deleted == False).first()
            if not sub:
                sub = Category(name=sub_name, parent_id=parent.id, sort_order=sub_idx*10, company_id=current_user.company_id)
                db.add(sub)
                count += 1
                
    if count > 0:
        db.commit()
        return {"message": f"{count} ta kategoriya yaratildi"}
    return {"message": "Barcha kategoriyalar allaqachon mavjud"}
