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
    q = db.query(Category).filter(Category.parent_id == None)
    q = q.filter(Category.company_id == current_user.company_id)
    return q.order_by(Category.sort_order).all()


@router.get("/all", response_model=List[CategoryOut])
def list_all_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Category)
    q = q.filter(Category.company_id == current_user.company_id)
    return q.order_by(Category.sort_order).all()


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Category).filter(Category.id == category_id)
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

    cat = Category(name=data.name, parent_id=data.parent_id, sort_order=data.sort_order, company_id=current_user.company_id)
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
    q = db.query(Category).filter(Category.id == category_id)
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

    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    q = db.query(Category).filter(Category.id == category_id)
    q = q.filter(Category.company_id == current_user.company_id)
    cat = q.first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")

    if cat.products:
        raise HTTPException(status_code=400, detail="Bu kategoriyada mahsulotlar mavjud, o'chirib bo'lmaydi")

    db.delete(cat)
    db.commit()
