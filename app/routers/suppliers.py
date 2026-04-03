from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.database import get_db  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.schemas.supplier import SupplierCreate, SupplierOut, SupplierUpdate  # type: ignore

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)


@router.get("", response_model=List[SupplierOut])
def list_suppliers(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.is_active == True)
    q = q.filter(Supplier.company_id == current_user.company_id)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    return q.offset(skip).limit(limit).all()


@router.post("", response_model=SupplierOut)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    supplier_data = data.model_dump()
    supplier_data["company_id"] = current_user.company_id
    supplier = Supplier(**supplier_data)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    log_action(db, current_user.id, "CREATE", "supplier", supplier.id, new_values={"name": supplier.name})
    db.commit()
    return supplier


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    old = {"name": supplier.name}
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    log_action(db, current_user.id, "UPDATE", "supplier", supplier.id, old_values=old, new_values={"name": supplier.name})
    db.commit()
    return supplier


@router.post("/bulk-import")
def bulk_import_suppliers(
    rows: list[dict],
    allow_update: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Excel fayldan ta'minotchilarni yuklash yoki yangilash."""
    FIELD_MAP = {
        "Nomi":                 ("name",          str),
        "INN":                  ("inn",           str),
        "Telefon":              ("phone",         str),
        "Email":                ("email",         str),
        "Manzil":               ("address",       str),
        "To'lov muddati (kun)": ("payment_terms", int),
        "Qarz":                 ("debt_balance",  Decimal),
    }

    created = 0
    updated = 0
    errors = []

    dup_q_base = db.query(Supplier).filter(Supplier.company_id == current_user.company_id)

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        name = str(row.get("Nomi") or "").strip()
        inn = str(row.get("INN") or "").strip() or None

        if not name:
            errors.append({"row": row_num, "error": "Ta'minotchi nomi majburiy"})
            continue

        existing = None
        if inn:
            existing = dup_q_base.filter(Supplier.inn == inn).first()
        if not existing:
            existing = dup_q_base.filter(Supplier.name == name).first()

        if existing:
            if not allow_update:
                errors.append({
                    "row": row_num, "name": name,
                    "error": f"'{name}' allaqachon mavjud — o'tkazib yuborildi"
                })
                continue
            
            for row_key, (field, cast) in FIELD_MAP.items():
                raw = row.get(row_key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    setattr(existing, field, val)
                except Exception:
                    errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati xato: {raw}"})
                    continue

            updated += 1
            continue

        kwargs = {"company_id": current_user.company_id}
        for row_key, (field, cast) in FIELD_MAP.items():
            raw = row.get(row_key)
            if raw is not None and str(raw).strip() != "":
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    kwargs[field] = val
                except:
                    pass

        # check specific constraints if needed
        if "name" not in kwargs:
            kwargs["name"] = name

        sup = Supplier(**kwargs)
        db.add(sup)
        db.flush()
        created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": len(errors), "errors": errors}

@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Soft-delete: is_active = False"""
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    supplier.is_active = False
    db.commit()
    log_action(db, current_user.id, "DELETE", "supplier", supplier.id, old_values={"name": supplier.name})
    db.commit()
