from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.bom import BOM, BOMItem
from app.models.production_order import ProductionOrder, ProductionOrderStatus
from app.models.user import User, UserRole
from app.schemas.production import (
    BOMCreate, BOMUpdate, BOMOut, BOMListOut, BOMItemOut,
    ProductionOrderCreate, ProductionOrderOut, ProductionOrderListOut,
    CompleteProductionOrderRequest, ProductionOrderCostOut,
)
from app.services.production_service import (
    create_production_order, start_production_order,
    complete_production_order, cancel_production_order,
    calculate_shortages,
)

router = APIRouter(prefix="/production", tags=["Ishlab chiqarish"],
                   dependencies=[Depends(require_feature("manufacturing"))])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _company_id(current_user: User) -> int:
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyangiz aniqlanmadi")
    return current_user.company_id


# ─── BOM (Retseptura) ──────────────────────────────────────────────────────

def _build_bom_out(bom: BOM) -> BOMOut:
    return BOMOut(
        id=bom.id,
        product_id=bom.product_id,
        product_name=bom.product.name,
        variant_id=bom.variant_id,
        variant_name=bom.variant.name if bom.variant else None,
        name=bom.name,
        is_active=bom.is_active,
        created_at=bom.created_at,
        items=[
            BOMItemOut(
                id=it.id,
                component_product_id=it.component_product_id,
                component_product_name=it.component_product.name,
                component_variant_id=it.component_variant_id,
                component_variant_name=it.component_variant.name if it.component_variant else None,
                component_unit=it.component_product.unit,
                quantity_per_unit=it.quantity_per_unit,
            )
            for it in bom.items
        ],
    )


@router.get("/boms", response_model=List[BOMListOut])
def list_boms(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(BOM).options(joinedload(BOM.items), joinedload(BOM.product)).filter(
        BOM.company_id == _company_id(current_user)
    )
    if is_active is not None:
        q = q.filter(BOM.is_active == is_active)
    boms = q.order_by(BOM.created_at.desc()).all()
    return [
        BOMListOut(
            id=b.id, product_id=b.product_id, product_name=b.product.name,
            name=b.name, is_active=b.is_active, item_count=len(b.items), created_at=b.created_at,
        )
        for b in boms
    ]


@router.get("/boms/{bom_id}", response_model=BOMOut)
def get_bom(
    bom_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    bom = db.query(BOM).options(
        joinedload(BOM.items).joinedload(BOMItem.component_product),
        joinedload(BOM.items).joinedload(BOMItem.component_variant),
        joinedload(BOM.product), joinedload(BOM.variant),
    ).filter(BOM.id == bom_id, BOM.company_id == _company_id(current_user)).first()
    if not bom:
        raise HTTPException(status_code=404, detail="Retseptura topilmadi")
    return _build_bom_out(bom)


@router.post("/boms", response_model=BOMOut, status_code=201)
def create_bom(
    data: BOMCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Kamida bitta xom ashyo qatori kerak")
    company_id = _company_id(current_user)

    bom = BOM(product_id=data.product_id, variant_id=data.variant_id, name=data.name, company_id=company_id)
    db.add(bom)
    db.flush()
    for item in data.items:
        db.add(BOMItem(
            bom_id=bom.id,
            component_product_id=item.component_product_id,
            component_variant_id=item.component_variant_id,
            quantity_per_unit=item.quantity_per_unit,
        ))
    db.commit()

    return get_bom(bom.id, db, current_user)


@router.put("/boms/{bom_id}", response_model=BOMOut)
def update_bom(
    bom_id: int,
    data: BOMUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    bom = db.query(BOM).filter(BOM.id == bom_id, BOM.company_id == _company_id(current_user)).first()
    if not bom:
        raise HTTPException(status_code=404, detail="Retseptura topilmadi")

    if data.name is not None:
        bom.name = data.name
    if data.is_active is not None:
        bom.is_active = data.is_active
    if data.items is not None:
        if not data.items:
            raise HTTPException(status_code=400, detail="Kamida bitta xom ashyo qatori kerak")
        db.query(BOMItem).filter(BOMItem.bom_id == bom.id).delete()
        for item in data.items:
            db.add(BOMItem(
                bom_id=bom.id,
                component_product_id=item.component_product_id,
                component_variant_id=item.component_variant_id,
                quantity_per_unit=item.quantity_per_unit,
            ))
    db.commit()
    return get_bom(bom.id, db, current_user)


@router.delete("/boms/{bom_id}")
def delete_bom(
    bom_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    bom = db.query(BOM).filter(BOM.id == bom_id, BOM.company_id == _company_id(current_user)).first()
    if not bom:
        raise HTTPException(status_code=404, detail="Retseptura topilmadi")
    used = db.query(ProductionOrder).filter(ProductionOrder.bom_id == bom.id).first()
    if used:
        # Tarixiy buyurtmalar bu BOM'ga bog'liq — o'chirish o'rniga faolsizlantiramiz
        bom.is_active = False
        db.commit()
        return {"status": "deactivated", "detail": "Bu retsepturadan ishlab chiqarish buyurtmalari yaratilgan, shuning uchun o'chirilmadi — faolsizlantirildi"}
    db.delete(bom)
    db.commit()
    return {"status": "deleted"}


# ─── Ishlab chiqarish buyurtmalari ─────────────────────────────────────────

def _build_order_out(order: ProductionOrder) -> ProductionOrderOut:
    return ProductionOrderOut(
        id=order.id,
        number=order.number,
        bom_id=order.bom_id,
        bom_name=order.bom.name,
        product_id=order.product_id,
        product_name=order.product.name,
        variant_id=order.variant_id,
        variant_name=order.variant.name if order.variant else None,
        planned_quantity=order.planned_quantity,
        produced_quantity=order.produced_quantity,
        defect_quantity=order.defect_quantity,
        warehouse_id=order.warehouse_id,
        warehouse_name=order.warehouse.name,
        target_warehouse_id=order.target_warehouse_id,
        target_warehouse_name=order.target_warehouse.name,
        status=order.status,
        note=order.note,
        created_by=order.created_by,
        creator_name=order.creator.name,
        started_at=order.started_at,
        completed_at=order.completed_at,
        created_at=order.created_at,
        unit_cost=order.unit_cost,
        total_cost=order.total_cost,
        costs=[ProductionOrderCostOut.model_validate(c) for c in order.costs],
    )


def _load_order(db: Session, order_id: int, company_id: int) -> Optional[ProductionOrder]:
    return db.query(ProductionOrder).options(
        joinedload(ProductionOrder.bom),
        joinedload(ProductionOrder.product),
        joinedload(ProductionOrder.variant),
        joinedload(ProductionOrder.warehouse),
        joinedload(ProductionOrder.target_warehouse),
        joinedload(ProductionOrder.creator),
        joinedload(ProductionOrder.costs),
    ).filter(ProductionOrder.id == order_id, ProductionOrder.company_id == company_id).first()


@router.get("/orders", response_model=List[ProductionOrderListOut])
def list_orders(
    status: Optional[ProductionOrderStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(ProductionOrder).options(
        joinedload(ProductionOrder.product), joinedload(ProductionOrder.warehouse), joinedload(ProductionOrder.target_warehouse),
    ).filter(ProductionOrder.company_id == _company_id(current_user))
    if status:
        q = q.filter(ProductionOrder.status == status)
    orders = q.order_by(ProductionOrder.created_at.desc()).offset(skip).limit(limit).all()
    return [
        ProductionOrderListOut(
            id=o.id, number=o.number, product_name=o.product.name,
            planned_quantity=o.planned_quantity, produced_quantity=o.produced_quantity,
            status=o.status, warehouse_name=o.warehouse.name, target_warehouse_name=o.target_warehouse.name,
            created_at=o.created_at,
        )
        for o in orders
    ]


@router.get("/orders/{order_id}", response_model=ProductionOrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    order = _load_order(db, order_id, _company_id(current_user))
    if not order:
        raise HTTPException(status_code=404, detail="Ishlab chiqarish buyurtmasi topilmadi")
    out = _build_order_out(order)
    if order.status in (ProductionOrderStatus.draft, ProductionOrderStatus.in_progress):
        out.shortages = calculate_shortages(db, order.bom, order.planned_quantity, order.warehouse_id)
    return out


@router.post("/orders", response_model=ProductionOrderOut, status_code=201)
def create_order(
    data: ProductionOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    company_id = _company_id(current_user)
    order = create_production_order(db, data, current_user.id, company_id)
    db.commit()
    order = _load_order(db, order.id, company_id)
    out = _build_order_out(order)
    out.shortages = calculate_shortages(db, order.bom, order.planned_quantity, order.warehouse_id)
    return out


@router.post("/orders/{order_id}/start", response_model=ProductionOrderOut)
def start_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    company_id = _company_id(current_user)
    start_production_order(db, order_id, company_id)
    db.commit()
    return _build_order_out(_load_order(db, order_id, company_id))


@router.post("/orders/{order_id}/complete", response_model=ProductionOrderOut)
def complete_order(
    order_id: int,
    data: CompleteProductionOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    company_id = _company_id(current_user)
    complete_production_order(db, order_id, current_user.id, company_id, data)
    db.commit()
    order = _load_order(db, order_id, company_id)
    return _build_order_out(order)


@router.post("/orders/{order_id}/cancel", response_model=ProductionOrderOut)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    company_id = _company_id(current_user)
    cancel_production_order(db, order_id, company_id)
    db.commit()
    return _build_order_out(_load_order(db, order_id, company_id))


# ─── Ogohlantirishlar ──────────────────────────────────────────────────────

@router.get("/alerts")
def production_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """1) Ochiq (qoralama/jarayondagi) buyurtmalarni bajarishga yetmaydigan
    xom ashyo — ombor bo'yicha jamlangan; 2) minimal qoldiqdan kam xom ashyo."""
    from decimal import Decimal
    from sqlalchemy import func
    from app.models.inventory import StockLevel
    from app.models.product import Product
    from app.models.warehouse import Warehouse

    cid = _company_id(current_user)
    orders = db.query(ProductionOrder).options(joinedload(ProductionOrder.bom).joinedload(BOM.items)).filter(
        ProductionOrder.company_id == cid,
        ProductionOrder.status.in_([ProductionOrderStatus.draft, ProductionOrderStatus.in_progress]),
    ).all()

    need: dict = {}  # (product_id, variant_id, warehouse_id) -> {"qty", "orders"}
    for o in orders:
        for it in o.bom.items:
            key = (it.component_product_id, it.component_variant_id, o.warehouse_id)
            row = need.setdefault(key, {"qty": Decimal("0"), "orders": []})
            row["qty"] += Decimal(str(it.quantity_per_unit)) * Decimal(str(o.planned_quantity))
            if o.number not in row["orders"]:
                row["orders"].append(o.number)

    shortages = []
    if need:
        pids = {k[0] for k in need}
        whs = {k[2] for k in need}
        products = {p.id: p for p in db.query(Product).filter(Product.id.in_(pids)).all()}
        wh_names = {w.id: w.name for w in db.query(Warehouse).filter(Warehouse.id.in_(whs)).all()}
        stock = {
            (s.product_id, s.variant_id, s.warehouse_id): Decimal(str(s.quantity or 0))
            for s in db.query(StockLevel).filter(StockLevel.product_id.in_(pids), StockLevel.warehouse_id.in_(whs)).all()
        }
        for (pid, vid, wid), row in need.items():
            have = stock.get((pid, vid, wid), Decimal("0"))
            if have < row["qty"]:
                p = products.get(pid)
                shortages.append({
                    "product_id": pid, "product_name": p.name if p else f"#{pid}", "unit": p.unit if p else None,
                    "warehouse_id": wid, "warehouse_name": wh_names.get(wid),
                    "required": float(row["qty"]), "available": float(have), "shortage": float(row["qty"] - have),
                    "orders": row["orders"],
                })
        shortages.sort(key=lambda x: x["shortage"], reverse=True)

    totals = db.query(Product, func.coalesce(func.sum(StockLevel.quantity), 0)).outerjoin(
        StockLevel, StockLevel.product_id == Product.id,
    ).filter(
        Product.company_id == cid,
        Product.product_type == "raw_material",
        Product.is_deleted == False,  # noqa: E712
        Product.min_stock > 0,
    ).group_by(Product.id).all()
    low_stock = [
        {"product_id": p.id, "product_name": p.name, "unit": p.unit,
         "quantity": float(q or 0), "min_stock": p.min_stock}
        for p, q in totals if Decimal(str(q or 0)) <= Decimal(str(p.min_stock))
    ]
    return {"shortages": shortages, "low_stock": low_stock}


# ─── Hisobotlar ────────────────────────────────────────────────────────────

@router.get("/reports")
def production_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Davr bo'yicha yakunlangan ishlab chiqarish: mahsulotlar kesimida
    miqdor/tannarx, qo'shimcha xarajatlar va xom ashyo sarfi."""
    from decimal import Decimal
    from sqlalchemy import func
    from app.models.inventory import StockMovement, MovementType
    from app.models.product import Product
    from app.models.production_order import ProductionOrderCost
    from app.utils.report_utils import _date_range, local_today

    cid = _company_id(current_user)
    if not date_from and not date_to:
        date_to = local_today()
        date_from = date_to - timedelta(days=29)
    start, end = _date_range(date_from, date_to)

    orders = db.query(ProductionOrder).filter(
        ProductionOrder.company_id == cid,
        ProductionOrder.status == ProductionOrderStatus.completed,
        ProductionOrder.completed_at >= start,
        ProductionOrder.completed_at < end,
    ).all()
    ids = [o.id for o in orders]

    by_product: dict = {}
    for o in orders:
        r = by_product.setdefault(o.product_id, {"orders": 0, "produced": Decimal("0"), "defect": Decimal("0"), "total_cost": Decimal("0")})
        r["orders"] += 1
        r["produced"] += Decimal(str(o.produced_quantity or 0))
        r["defect"] += Decimal(str(o.defect_quantity or 0))
        r["total_cost"] += Decimal(str(o.total_cost or 0))

    extra_by_type: dict = {}
    consumption = []
    pids = set(by_product)
    movement_rows = []
    if ids:
        for ctype, amt in db.query(ProductionOrderCost.cost_type, func.sum(ProductionOrderCost.amount)).filter(
            ProductionOrderCost.production_order_id.in_(ids),
        ).group_by(ProductionOrderCost.cost_type).all():
            extra_by_type[ctype] = float(amt or 0)
        movement_rows = db.query(StockMovement.product_id, func.sum(StockMovement.quantity)).filter(
            StockMovement.reference_type == "production_order",
            StockMovement.reference_id.in_(ids),
            StockMovement.type == MovementType.OUT,
        ).group_by(StockMovement.product_id).all()
        pids |= {r[0] for r in movement_rows}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(pids)).all()} if pids else {}

    for pid, qty in movement_rows:
        p = products.get(pid)
        cost = Decimal(str(p.cost_price or 0)) if p else Decimal("0")
        consumption.append({
            "product_id": pid, "product_name": p.name if p else f"#{pid}", "unit": p.unit if p else None,
            "quantity": float(qty or 0),
            # Joriy tannarx bo'yicha taxminiy qiymat
            "estimated_value": float(Decimal(str(qty or 0)) * cost),
        })
    consumption.sort(key=lambda x: x["estimated_value"], reverse=True)

    products_out = []
    for pid, r in by_product.items():
        p = products.get(pid)
        made = r["produced"] + r["defect"]
        products_out.append({
            "product_id": pid, "product_name": p.name if p else f"#{pid}", "unit": p.unit if p else None,
            "orders": r["orders"], "produced": float(r["produced"]), "defect": float(r["defect"]),
            "total_cost": float(r["total_cost"]),
            "avg_unit_cost": float(r["total_cost"] / r["produced"]) if r["produced"] > 0 else 0,
            "defect_rate": round(float(r["defect"] / made * 100), 1) if made > 0 else 0,
        })
    products_out.sort(key=lambda x: x["total_cost"], reverse=True)

    total_cost = sum(p["total_cost"] for p in products_out)
    extra_total = sum(extra_by_type.values())
    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "summary": {
            "orders": len(orders),
            "produced": sum(p["produced"] for p in products_out),
            "defect": sum(p["defect"] for p in products_out),
            "total_cost": total_cost,
            "raw_material_cost": total_cost - extra_total,
            "extra_cost": extra_total,
        },
        "extra_by_type": extra_by_type,
        "products": products_out,
        "consumption": consumption,
    }
