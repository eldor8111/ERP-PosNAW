"""
Kuryer ish maydoni: bugungi marshrut(lar), to'xtovlar, statuslar va
yetkazish isboti. Status o'zgarishi logistika bilan bir xil mantiqda
(logistics._Stop): Telegram buyurtmasi yetkazilsa avto-sotuv, sotuv
yetkazmasida yetkazish haqi — endi kuryerning qo'l kassasiga yoziladi.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.delivery_route import DeliveryRoute, DeliveryRouteStatus
from app.models.mobile_misc import DeliveryProof
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.sale import SaleItem
from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
from app.models.user import User, UserRole
from app.routers import logistics as L
from app.services import sale_delivery_service as sd_service
from app.services.mobile_service import distance_m, ensure_courier_profile

router = APIRouter(prefix="/mobile/courier", tags=["mobile-courier"],
                   dependencies=[Depends(require_feature("distribution"))])

courier_user = require_roles(UserRole.courier)
PROOF_DIR = os.path.join("uploads_private", "delivery_proofs")


def _me(db: Session, user: User):
    c = ensure_courier_profile(db, user)
    if not c or not c.is_active:
        raise HTTPException(status_code=403, detail="Kuryer profili faol emas")
    return c


def _my_stop(db: Session, user: User, courier, key: str) -> "L._Stop":
    st = L._load_stops(db, user.company_id, [key]).get(key)
    if not st:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    owner_ok = (st.delivery.courier_id == courier.id) if st.is_sale else all(o.courier_id == courier.id for o in st.orders)
    if not owner_ok:
        raise HTTPException(status_code=404, detail="Buyurtma sizga biriktirilmagan")
    return st


@router.get("/today")
def courier_today(db: Session = Depends(get_db), current_user: User = Depends(courier_user)):
    """Faol marshrutlar (rejalashtirilgan/yo'lda) + marshrutsiz biriktirilgan buyurtmalar."""
    courier = _me(db, current_user)
    cid = current_user.company_id
    routes = db.query(DeliveryRoute).filter(
        DeliveryRoute.company_id == cid, DeliveryRoute.courier_id == courier.id,
        DeliveryRoute.status.in_(L.ACTIVE_ROUTE),
    ).order_by(DeliveryRoute.route_date.asc(), DeliveryRoute.id.asc()).all()
    routes_out = [L._route_out(db, r) for r in routes]
    on_routes = {s["group_key"] for r in routes_out for s in r["stops"]}

    loose: dict = {}
    for o in db.query(Order).filter(
        Order.courier_id == courier.id, Order.status.in_([OrderStatus.assigned, OrderStatus.on_way]),
    ).all():
        k = L._group_key(o)
        if k not in on_routes:
            loose.setdefault(k, L._Stop(k)).orders.append(o)
    for d in db.query(SaleDelivery).filter(
        SaleDelivery.company_id == cid, SaleDelivery.courier_id == courier.id,
        SaleDelivery.status.in_([SaleDeliveryStatus.assigned, SaleDeliveryStatus.on_way]),
    ).all():
        k = f"{L.SALE_PREFIX}{d.sale_id}"
        if k not in on_routes:
            loose[k] = L._Stop(k, delivery=d)
    customers = L._customers_map(db, loose)
    db.commit()  # ensure_courier_profile birinchi marta bog'lagan bo'lsa
    return {
        "courier": {"id": courier.id, "name": courier.name},
        "routes": routes_out,
        "loose": [st.summary(customers) for st in loose.values()],
    }


@router.get("/stops/{key}")
def stop_detail(key: str, db: Session = Depends(get_db), current_user: User = Depends(courier_user)):
    courier = _me(db, current_user)
    st = _my_stop(db, current_user, courier, key)
    summary = st.summary(L._customers_map(db, {key: st}))
    if st.is_sale:
        rows = db.query(SaleItem, Product.name, Product.unit).join(Product, Product.id == SaleItem.product_id).filter(
            SaleItem.sale_id == st.delivery.sale_id).all()
        items = [{"name": n, "unit": u, "quantity": float(si.quantity), "amount": float(si.subtotal or 0)} for si, n, u in rows]
    else:
        names = {p.id: (p.name, p.unit) for p in db.query(Product).filter(Product.id.in_([o.product_id for o in st.orders])).all()}
        items = [{"name": names.get(o.product_id, ("—", None))[0], "unit": names.get(o.product_id, (None, None))[1],
                  "quantity": float(o.quantity), "amount": float(o.total_amount or 0)} for o in st.orders]
    proofs = db.query(DeliveryProof).filter(DeliveryProof.company_id == current_user.company_id, DeliveryProof.stop_key == key).count()
    return {**summary, "items": items, "proof_count": proofs}


@router.post("/routes/{route_id}/start")
def start_my_route(route_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                   current_user: User = Depends(courier_user)):
    courier = _me(db, current_user)
    route = L._get_route(db, route_id, current_user.company_id)
    if route.courier_id != courier.id:
        raise HTTPException(status_code=404, detail="Marshrut topilmadi")
    if route.status == DeliveryRouteStatus.in_progress:
        return L._route_out(db, route)  # idempotent
    return L.start_route(route_id, background_tasks, db, current_user)


class StopActionIn(BaseModel):
    action: str = Field(..., pattern="^(on_way|delivered|failed)$")
    reason: Optional[str] = Field(None, max_length=300)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)


@router.post("/stops/{key}/status")
def set_status(key: str, data: StopActionIn, background_tasks: BackgroundTasks,
               db: Session = Depends(get_db), current_user: User = Depends(courier_user)):
    courier = _me(db, current_user)
    st = _my_stop(db, current_user, courier, key)
    target = {"on_way": "on_way", "delivered": "delivered", "failed": "cancelled"}[data.action]
    if st.status == target:
        return {"status": st.status}  # oflayn navbatdan qayta kelgan — idempotent
    if st.is_final:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon yakunlangan")

    if data.action == "on_way":
        st.start()
    else:
        delivered = data.action == "delivered"
        st.finish(delivered)
        if not delivered and data.reason:
            if st.is_sale:
                st.delivery.cancel_reason = data.reason
            else:
                for o in st.orders:
                    o.cancel_reason = data.reason
        if st.is_sale and delivered:
            sd_service.record_fee_once(db, st.delivery, current_user)
    if data.lat is not None and data.action != "on_way":
        # Status qayerda bosilgani — manzildan uzoqligi rahbarga ko'rinadi
        s = st.summary({})
        db.add(DeliveryProof(company_id=current_user.company_id, stop_key=key, user_id=current_user.id,
                             lat=data.lat, lng=data.lng, distance_m=distance_m(data.lat, data.lng, s["lat"], s["lng"])))
    db.commit()

    if not st.is_sale:
        from app.routers.orders import _notify_customer_status
        background_tasks.add_task(_notify_customer_status, db, st.orders, OrderStatus(target))
        if data.action == "delivered":
            from app.services.order_to_sale import maybe_create_sale_for_delivered_group
            background_tasks.add_task(maybe_create_sale_for_delivered_group, db, st.orders, current_user)
    return {"status": st.status}


@router.post("/stops/{key}/proof", status_code=201)
async def upload_proof(key: str, file: UploadFile = File(...), lat: Optional[float] = Form(None),
                       lng: Optional[float] = Form(None), db: Session = Depends(get_db),
                       current_user: User = Depends(courier_user)):
    """Yetkazish isboti — rasm (topshirilgan tovar/imzo) shaxsiy papkaga."""
    from app.routers.customer_profile import _image_ext
    courier = _me(db, current_user)
    st = _my_stop(db, current_user, courier, key)
    content = await file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Rasm hajmi 8 MB dan oshmasligi kerak")
    ext = _image_ext(content)
    rel = os.path.join(str(current_user.company_id), f"{uuid.uuid4().hex}.{ext}")
    os.makedirs(os.path.join(PROOF_DIR, str(current_user.company_id)), exist_ok=True)
    with open(os.path.join(PROOF_DIR, rel), "wb") as f:
        f.write(content)
    s = st.summary({})
    proof = DeliveryProof(company_id=current_user.company_id, stop_key=key, user_id=current_user.id,
                          photo_path=rel.replace("\\", "/"), lat=lat, lng=lng,
                          distance_m=distance_m(lat, lng, s["lat"], s["lng"]))
    db.add(proof)
    db.commit()
    return {"id": proof.id, "distance_m": proof.distance_m}
