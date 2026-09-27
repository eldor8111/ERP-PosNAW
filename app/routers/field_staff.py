"""
Rahbar uchun dala xodimlari (kuryer/agent) boshqaruvi: ro'yxat, qurilmalar,
qo'l kassasi balansi, qurilmani uzish. Keyingi bosqichda jonli xarita va
hisobotlar ham shu yerga qo'shiladi.
"""
import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.mobile_device import MobileDevice
from app.models.moliya import Wallet
from app.models.user import MOBILE_ONLY_ROLES, User, UserRole, UserStatus, UserWallet

router = APIRouter(prefix="/field-staff", tags=["field-staff"],
                   dependencies=[Depends(require_feature("distribution"))])

MANAGE = (UserRole.admin, UserRole.director, UserRole.manager)


def _device_out(d: MobileDevice) -> dict:
    return {
        "id": d.id,
        "platform": d.platform,
        "model": d.model,
        "app_version": d.app_version,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "revoked": d.revoked_at is not None,
        "push_enabled": bool(d.fcm_token),
    }


@router.get("/users")
def list_field_staff(db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    cid = current_user.company_id
    users = db.query(User).filter(
        User.company_id == cid, User.role.in_(MOBILE_ONLY_ROLES), User.status == UserStatus.active,
    ).order_by(User.name).all()
    ids = [u.id for u in users]
    devices: dict = {}
    wallets: dict = {}
    if ids:
        for d in db.query(MobileDevice).filter(MobileDevice.user_id.in_(ids)).order_by(MobileDevice.last_seen_at.desc().nullslast()).all():
            devices.setdefault(d.user_id, []).append(_device_out(d))
        for uw, w in db.query(UserWallet, Wallet).join(Wallet, Wallet.id == UserWallet.wallet_id).filter(
            UserWallet.user_id.in_(ids), UserWallet.is_default == True, Wallet.company_id == cid,  # noqa: E712
        ).all():
            wallets[uw.user_id] = {"id": w.id, "balance": float(w.balance or 0)}
    from app.models.customer import Customer
    counts = dict(db.query(Customer.agent_id, func.count(Customer.id)).filter(
        Customer.company_id == cid, Customer.agent_id.in_(ids or [0])).group_by(Customer.agent_id).all())
    return [
        {
            "id": u.id, "name": u.name, "phone": u.phone, "role": u.role.value,
            "devices": devices.get(u.id, []),
            "wallet": wallets.get(u.id),
            "customers_count": int(counts.get(u.id, 0)),
        }
        for u in users
    ]


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    """Telefon yo'qolsa yoki xodim ketsa — shu qurilmadagi sessiya darhol bekor bo'ladi."""
    d = db.query(MobileDevice).filter(MobileDevice.id == device_id, MobileDevice.company_id == current_user.company_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Qurilma topilmadi")
    d.revoked_at = datetime.now(timezone.utc)
    d.fcm_token = None
    db.commit()
    return _device_out(d)


# ── Jonli xarita, trek, hisobot ─────────────────────────────────────────────

def _staff(db: Session, cid: int):
    return db.query(User).filter(
        User.company_id == cid, User.role.in_(MOBILE_ONLY_ROLES), User.status == UserStatus.active,
    ).order_by(User.name).all()


def _iso(dt):
    return dt.isoformat() if dt else None


@router.get("/live")
def live(db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    """Har bir xodimning oxirgi joylashuvi, smena holati va bugungi natijasi."""
    from app.models.agent_visit import AgentVisit
    from app.models.courier import Courier
    from app.models.employee_location import EmployeeLocation
    from app.models.field_shift import FieldShift
    from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
    from app.utils.report_utils import local_day_start, local_today

    cid = current_user.company_id
    staff = _staff(db, cid)
    ids = [u.id for u in staff]
    if not ids:
        return []
    day0 = local_day_start(local_today())
    last_sub = db.query(EmployeeLocation.user_id, func.max(EmployeeLocation.id).label("mid")).filter(
        EmployeeLocation.user_id.in_(ids)).group_by(EmployeeLocation.user_id).subquery()
    last = {l.user_id: l for l in db.query(EmployeeLocation).join(last_sub, EmployeeLocation.id == last_sub.c.mid).all()}
    shifts = {s.user_id: s for s in db.query(FieldShift).filter(FieldShift.user_id.in_(ids), FieldShift.ended_at.is_(None)).all()}
    visits = dict(db.query(AgentVisit.agent_id, func.count(AgentVisit.id)).filter(
        AgentVisit.agent_id.in_(ids), AgentVisit.check_in_at >= day0).group_by(AgentVisit.agent_id).all())
    courier_of = {c.user_id: c.id for c in db.query(Courier).filter(Courier.user_id.in_(ids)).all()}
    delivered = dict(db.query(SaleDelivery.courier_id, func.count(SaleDelivery.id)).filter(
        SaleDelivery.courier_id.in_(list(courier_of.values()) or [0]),
        SaleDelivery.status == SaleDeliveryStatus.delivered,
        SaleDelivery.delivered_at >= day0).group_by(SaleDelivery.courier_id).all())
    out = []
    for u in staff:
        loc = last.get(u.id)
        out.append({
            "id": u.id, "name": u.name, "phone": u.phone, "role": u.role.value,
            "on_shift": u.id in shifts,
            "shift_started_at": _iso(shifts[u.id].started_at) if u.id in shifts else None,
            "last": {
                "lat": float(loc.lat), "lng": float(loc.lng), "at": _iso(loc.recorded_at), "battery": loc.battery,
                "speed": float(loc.speed) if loc.speed is not None else None,
            } if loc else None,
            "today_visits": int(visits.get(u.id, 0)),
            "today_delivered": int(delivered.get(courier_of.get(u.id), 0)),
        })
    return out


@router.get("/track")
def track(user_id: int, day: Optional[date] = None, db: Session = Depends(get_db),
          current_user: User = Depends(require_roles(*MANAGE))):
    """Xodimning bir kunlik yo'li: GPS nuqtalari, tashriflar, yetkazish nuqtalari."""
    from app.models.agent_visit import AgentVisit
    from app.models.customer import Customer
    from app.models.employee_location import EmployeeLocation
    from app.models.field_shift import FieldShift
    from app.models.mobile_misc import DeliveryProof
    from app.utils.report_utils import local_day_start, local_today

    u = db.query(User).filter(User.id == user_id, User.company_id == current_user.company_id,
                              User.role.in_(MOBILE_ONLY_ROLES)).first()
    if not u:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    d = day or local_today()
    t0, t1 = local_day_start(d), local_day_start(d + timedelta(days=1))
    pts = db.query(EmployeeLocation).filter(
        EmployeeLocation.user_id == u.id, EmployeeLocation.recorded_at >= t0, EmployeeLocation.recorded_at < t1,
    ).order_by(EmployeeLocation.recorded_at).limit(20000).all()
    visits = db.query(AgentVisit, Customer.name).join(Customer, Customer.id == AgentVisit.customer_id).filter(
        AgentVisit.agent_id == u.id, AgentVisit.check_in_at >= t0, AgentVisit.check_in_at < t1,
    ).order_by(AgentVisit.check_in_at).all()
    proofs = db.query(DeliveryProof).filter(
        DeliveryProof.user_id == u.id, DeliveryProof.created_at >= t0, DeliveryProof.created_at < t1,
    ).order_by(DeliveryProof.created_at).all()
    shifts = db.query(FieldShift).filter(
        FieldShift.user_id == u.id, FieldShift.started_at < t1,
        or_(FieldShift.ended_at.is_(None), FieldShift.ended_at >= t0),
    ).all()
    return {
        "user": {"id": u.id, "name": u.name, "role": u.role.value},
        "date": d.isoformat(),
        "shifts": [{"started_at": _iso(s.started_at), "ended_at": _iso(s.ended_at)} for s in shifts],
        "points": [[float(p.lat), float(p.lng), _iso(p.recorded_at)] for p in pts],
        "visits": [
            {"id": v.id, "customer": name, "at": _iso(v.check_in_at), "out": _iso(v.check_out_at),
             "lat": float(v.lat) if v.lat is not None else None, "lng": float(v.lng) if v.lng is not None else None,
             "distance_m": v.distance_m, "within_radius": v.within_radius, "result": v.result,
             "has_photo": bool(v.photo_path)}
            for v, name in visits
        ],
        "deliveries": [
            {"id": p.id, "stop_key": p.stop_key, "at": _iso(p.created_at),
             "lat": float(p.lat) if p.lat is not None else None, "lng": float(p.lng) if p.lng is not None else None,
             "distance_m": p.distance_m, "has_photo": bool(p.photo_path)}
            for p in proofs
        ],
    }


@router.get("/report")
def report(date_from: Optional[date] = None, date_to: Optional[date] = None, db: Session = Depends(get_db),
           current_user: User = Depends(require_roles(*MANAGE))):
    """Davr bo'yicha: agentlar (reja bajarilishi, tasdiqlanmagan tashriflar,
    buyurtmalar, yig'ilgan pul) va kuryerlar (yetkazilgan/yetkazilmagan)."""
    from app.models.agent_visit import AgentVisit
    from app.models.courier import Courier
    from app.models.customer import Customer
    from app.models.moliya import KassaMovement
    from app.models.order import Order, OrderStatus
    from app.models.sale import Sale, SaleStatus
    from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
    from app.utils.report_utils import _date_range, local_today

    cid = current_user.company_id
    if not date_from and not date_to:
        date_to = local_today()
        date_from = date_to - timedelta(days=6)
    date_from = date_from or date_to
    date_to = date_to or date_from
    t0, t1 = _date_range(date_from, date_to)
    weekdays = [(date_from + timedelta(days=i)).isoweekday() for i in range((date_to - date_from).days + 1)]
    staff = _staff(db, cid)
    wallets = {
        uw.user_id: w for uw, w in db.query(UserWallet, Wallet).join(Wallet, Wallet.id == UserWallet.wallet_id).filter(
            UserWallet.user_id.in_([u.id for u in staff] or [0]), UserWallet.is_default == True,  # noqa: E712
        ).all()
    }
    agents, couriers = [], []
    for u in staff:
        w = wallets.get(u.id)
        cash = float(w.balance or 0) if w else 0
        if u.role == UserRole.agent:
            wd = [c.work_days or [] for c in db.query(Customer).filter(Customer.company_id == cid, Customer.agent_id == u.id).all()]
            planned = sum(1 for d in weekdays for x in wd if d in x)
            vq = db.query(AgentVisit).filter(AgentVisit.agent_id == u.id, AgentVisit.check_in_at >= t0, AgentVisit.check_in_at < t1)
            planned_done = vq.filter(AgentVisit.planned == True).count()  # noqa: E712
            n, s = db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0)).filter(
                Sale.agent_id == u.id, Sale.created_at >= t0, Sale.created_at < t1, Sale.status != SaleStatus.cancelled,
            ).first()
            collected = db.query(func.coalesce(func.sum(KassaMovement.amount), 0)).filter(
                KassaMovement.wallet_id == (w.id if w else 0), KassaMovement.reference_type == "customer_payment",
                KassaMovement.direction == "in", KassaMovement.created_at >= t0, KassaMovement.created_at < t1,
            ).scalar()
            agents.append({
                "id": u.id, "name": u.name, "planned": planned, "planned_done": planned_done,
                "plan_pct": round(planned_done / planned * 100) if planned else None,
                "visits": vq.count(), "unverified": vq.filter(AgentVisit.within_radius == False).count(),  # noqa: E712
                "orders": int(n or 0), "orders_sum": float(s or 0), "collected": float(collected or 0),
                "cash_on_hand": cash,
            })
        else:
            c = db.query(Courier).filter(Courier.user_id == u.id, Courier.company_id == cid).first()
            cour_id = c.id if c else 0
            sd_delivered = db.query(SaleDelivery).filter(
                SaleDelivery.courier_id == cour_id, SaleDelivery.status == SaleDeliveryStatus.delivered,
                SaleDelivery.delivered_at >= t0, SaleDelivery.delivered_at < t1).count()
            sd_failed = db.query(SaleDelivery).filter(
                SaleDelivery.courier_id == cour_id, SaleDelivery.status == SaleDeliveryStatus.cancelled,
                SaleDelivery.cancel_reason.isnot(None), SaleDelivery.created_at >= t0 - timedelta(days=30)).count()
            o_delivered = db.query(func.count(func.distinct(func.coalesce(Order.order_group_id, cast(Order.id, String))))).filter(
                Order.courier_id == cour_id, Order.status == OrderStatus.delivered,
                Order.delivered_at >= t0, Order.delivered_at < t1).scalar()
            couriers.append({
                "id": u.id, "name": u.name, "delivered": sd_delivered + int(o_delivered or 0),
                "failed": sd_failed, "cash_on_hand": cash,
            })
    return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "agents": agents, "couriers": couriers}


def _private_photo(base: str, rel: Optional[str]):
    if not rel:
        raise HTTPException(status_code=404, detail="Rasm yo'q")
    root = os.path.realpath(base)
    full = os.path.realpath(os.path.join(root, rel))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Rasm topilmadi")
    return FileResponse(full, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/visits/{visit_id}/photo")
def visit_photo(visit_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    from app.models.agent_visit import AgentVisit
    v = db.query(AgentVisit).filter(AgentVisit.id == visit_id, AgentVisit.company_id == current_user.company_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Tashrif topilmadi")
    return _private_photo(os.path.join("uploads_private", "visit_photos"), v.photo_path)


@router.get("/proofs/{proof_id}/photo")
def proof_photo(proof_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    from app.models.mobile_misc import DeliveryProof
    p = db.query(DeliveryProof).filter(DeliveryProof.id == proof_id, DeliveryProof.company_id == current_user.company_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Isbot topilmadi")
    return _private_photo(os.path.join("uploads_private", "delivery_proofs"), p.photo_path)


# ── Agentga mijozlarni biriktirish (ommaviy) ────────────────────────────────

class AssignCustomersIn(BaseModel):
    add: List[int] = []
    remove: List[int] = []
    work_days: Optional[List[int]] = None   # yangi biriktirilganlarga (bo'sh bo'lsa o'zgarmaydi)


@router.post("/agents/{agent_id}/customers")
def assign_customers(agent_id: int, data: AssignCustomersIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_roles(*MANAGE))):
    from app.models.customer import Customer
    cid = current_user.company_id
    agent = db.query(User).filter(User.id == agent_id, User.company_id == cid, User.role == UserRole.agent).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    days = sorted({d for d in (data.work_days or []) if 1 <= d <= 7})
    added = 0
    if data.add:
        for c in db.query(Customer).filter(Customer.company_id == cid, Customer.id.in_(data.add)).all():
            c.agent_id = agent.id
            if days and not (c.work_days or []):
                c.work_days = days
            added += 1
    removed = 0
    if data.remove:
        removed = db.query(Customer).filter(
            Customer.company_id == cid, Customer.id.in_(data.remove), Customer.agent_id == agent.id,
        ).update({"agent_id": None}, synchronize_session=False)
    db.commit()
    total = db.query(Customer).filter(Customer.company_id == cid, Customer.agent_id == agent.id).count()
    return {"added": added, "removed": removed, "total": total}
