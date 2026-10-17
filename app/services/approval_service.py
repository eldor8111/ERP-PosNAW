"""T4.6 — tasdiqlash (approval) jarayonlari va rol bo'yicha limitlar.

Oqim: `ApprovalRule` (qoida) amalni cheklaydi -> qoida buzilsa `block` rejimida 403 `limit_exceeded`,
`require_approval` rejimida 403 `approval_required` (javobda so'rov yuborish uchun `payload`) ->
kassir `POST /approvals/requests` yuboradi -> menejer/direktor `approve`/`reject` qiladi ->
kassir `approval_id` bilan amalni qayta yuboradi, servis `consume_approval` bilan tasdiqni BIR MARTA
ishlatadi (holat `used`). `payload_hash` tasdiq faqat aynan shu tarkibga (mahsulot, narx, miqdor) tegishli
ekanini kafolatlaydi.

Qoida yo'q korxonada hech narsa o'zgarmaydi. Admin/director qoidalardan ozod, lekin limitdan oshgan amali
`APPROVAL_EXEMPT` bilan audit'ga yoziladi.
"""
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence, Union

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Qoidalardan ozod rollar (limitdan oshgan amali faqat audit'ga yoziladi)
EXEMPT_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)
# So'rovni hal qila oladigan rollar (menejer — faqat o'z filiali)
APPROVER_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)

REQUEST_TTL_MINUTES = 15          # tasdiq oynasi (sotuv/qaytarish/o'chirish)
EXPENSE_TTL_HOURS = 24            # xarajat yozuvi allaqachon 'pending' — menejer kechroq ham hal qila oladi

ACTION_LABELS = {
    "discount": "Chegirma",
    "price_override": "Narxni tushirish",
    "expense": "Xarajat",
    "refund": "Qaytarish",
    "sale_delete": "Sotuvni o'chirish",
}

APPROVAL_INVALID = "approval_invalid"


def _utcnow() -> datetime:
    """Naive UTC (ustunlar `DateTime` — tz'siz; sqlite/PG bir xil solishtiradi)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def role_value(role) -> Optional[str]:
    if role is None:
        return None
    return role.value if hasattr(role, "value") else str(role)


def is_exempt(user) -> bool:
    return getattr(user, "role", None) in EXEMPT_ROLES


# ─── Payload va hash ─────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _num_str(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return "0" if s in ("-0", "") else s


def _norm(value):
    """Kanonik shakl: sonlar normallashtiriladi (100 == 100.00 == "100"), None kalitlar tashlanadi,
    dict kalitlari tartiblanadi, dict'lar ro'yxati tarkibi bo'yicha tartiblanadi."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return _num_str(Decimal(str(value)))
    if isinstance(value, str):
        return _num_str(Decimal(value)) if _NUM_RE.match(value.strip()) else value
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0])) if v is not None}
    if isinstance(value, (list, tuple)):
        items = [_norm(v) for v in value]
        if items and all(isinstance(i, dict) for i in items):
            items.sort(key=lambda i: json.dumps(i, sort_keys=True, ensure_ascii=False))
        return items
    return str(value)


def canonical_payload(payload) -> dict:
    return _norm(payload or {})


def json_safe(payload) -> dict:
    """JSON ustuniga/javobga yoziladigan o'qiladigan nusxa (Decimal -> son)."""
    return json.loads(json.dumps(payload or {}, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)))


def compute_payload_hash(payload) -> str:
    raw = json.dumps(canonical_payload(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sale_payload(data) -> dict:
    """`SaleCreate` dan tasdiq tarkibi: mahsulot, miqdor va klient yuborgan narx/chegirma (aynan so'rov tanasi)."""
    return {
        "customer_id": getattr(data, "customer_id", None),
        "discount_amount": (getattr(data, "discount_amount", None) or None),   # 0/None — kalit tashlanadi
        "items": [
            {
                "product_id": i.product_id,
                "variant_id": getattr(i, "variant_id", None),
                "quantity": i.quantity,
                "unit_price": getattr(i, "unit_price", None),
                "discount": getattr(i, "discount", None) or None,
            }
            for i in data.items
        ],
    }


def return_payload(data) -> dict:
    """`POST /sales/return` (SaleCreate) tarkibi."""
    return {
        "original_sale_id": getattr(data, "original_sale_id", None),
        "items": [
            {"product_id": i.product_id, "variant_id": getattr(i, "variant_id", None), "quantity": i.quantity}
            for i in data.items
        ],
    }


def partial_return_payload(sale_id: int, data) -> dict:
    """`POST /sales/{id}/return-items` (SaleReturnRequest) tarkibi."""
    return {
        "sale_id": sale_id,
        "items": [{"sale_item_id": i.sale_item_id, "quantity": i.quantity} for i in data.items],
    }


def sale_delete_payload(sale_id: int) -> dict:
    return {"sale_id": sale_id}


# ─── Qoidalar ────────────────────────────────────────────────────────────────

@dataclass
class Violation:
    """Qoida buzilishi: nima, qaysi rejim, limit va haqiqiy qiymat."""
    action_type: str
    mode: str
    rule_id: int
    limit: Optional[float]
    actual: float
    unit: str            # "percent" | "amount"

    @property
    def message(self) -> str:
        label = ACTION_LABELS.get(self.action_type, self.action_type)
        suffix = "%" if self.unit == "percent" else ""
        if self.limit is None:
            base = f"{label} uchun menejer tasdig'i kerak"
        else:
            base = f"{label} limiti oshdi: {self.actual:g}{suffix} (limit {self.limit:g}{suffix})"
        return base

    def detail(self, code: str, **extra) -> dict:
        d = {
            "code": code, "action_type": self.action_type,
            "limit": self.limit, "actual": self.actual, "unit": self.unit,
            "message": self.message if code != "approval_required" else self.message + ". So'rov yuboring",
        }
        d.update(extra)
        return d


def get_applicable_rule(db: Session, company_id: int, branch_id: Optional[int], action_type: str,
                        role) -> Optional[ApprovalRule]:
    """Amalga mos qoida: avval filial qoidasi, keyin korxona qoidasi; ichida — aniq rol, so'ng "barcha rollar".
    `role=None` — rolga qaramasdan (ozod foydalanuvchi audit tekshiruvi uchun)."""
    rv = role_value(role)
    rules = db.query(ApprovalRule).filter(
        ApprovalRule.company_id == company_id,
        ApprovalRule.action_type == action_type,
        ApprovalRule.is_active.is_(True),
    ).order_by(ApprovalRule.id).all()
    cands = [
        r for r in rules
        if (r.branch_id is None or (branch_id is not None and r.branch_id == branch_id))
        and (rv is None or r.role is None or r.role == rv)
    ]
    if not cands:
        return None
    cands.sort(key=lambda r: (0 if r.branch_id is not None else 1, 0 if r.role else 1, r.id))
    return cands[0]


def _exceeds(rule: ApprovalRule, percent: Optional[Decimal], amount: Optional[Decimal]):
    """Qoida buzildimi: `(limit, actual, unit)` yoki None. Chegara berilmagan qoida har doim amal qiladi."""
    pt, at = rule.threshold_percent, rule.threshold_amount
    if pt is None and at is None:
        if percent is not None and percent > 0:
            return None, float(percent), "percent"
        if amount is not None and amount > 0:
            return None, float(amount), "amount"
        return None
    if pt is not None and percent is not None and percent > _d(pt):
        return float(pt), float(percent), "percent"
    if at is not None and amount is not None and amount > _d(at):
        return float(at), float(amount), "amount"
    return None


def _check(db: Session, user, branch_id: Optional[int], action_type: str,
           percent: Optional[Decimal] = None, amount: Optional[Decimal] = None) -> Optional[Violation]:
    """Bitta amalni qoidaga tekshiradi. Ozod rol (admin/director) -> None, lekin limitdan oshsa audit."""
    if is_exempt(user):
        if user.company_id is None:
            return None
        rule = get_applicable_rule(db, user.company_id, branch_id, action_type, None)
        hit = _exceeds(rule, percent, amount) if rule else None
        if hit:
            log_action(
                db, "APPROVAL_EXEMPT", "approval", None, user_id=user.id, company_id=user.company_id,
                branch_id=branch_id,
                new_values={"action_type": action_type, "rule_id": rule.id, "limit": hit[0], "actual": hit[1],
                            "unit": hit[2]},
            )
        return None
    if user.company_id is None:
        return None
    rule = get_applicable_rule(db, user.company_id, branch_id, action_type, user.role)
    if rule is None:
        return None
    hit = _exceeds(rule, percent, amount)
    if hit is None:
        return None
    return Violation(action_type, rule.mode, rule.id, hit[0], hit[1], hit[2])


def evaluate_discount(db: Session, user, product, unit_price, discount, qty, *, branch_id: Optional[int] = None,
                      list_price=None, is_override: bool = False, rate=1) -> list:
    """Sotuv qatori: chegirma foizi `discount / (unit_price * qty) * 100` (`discount`) va, qo'lda narx
    ro'yxat narxidan past bo'lsa, narx farqi (`price_override`). Buzilishlar ro'yxati (bo'sh — muammo yo'q).
    `rate` — qator valyutasi kursi (summa chegarasi UZS da)."""
    unit_price, discount, qty = _d(unit_price), _d(discount), _d(qty)
    rate = _d(rate) or Decimal("1")
    out = []
    gross = unit_price * qty
    if discount > 0 and gross > 0:
        pct = (discount / gross * 100).quantize(Decimal("0.01"))
        v = _check(db, user, branch_id, "discount", percent=pct, amount=discount * rate)
        if v:
            out.append(v)
    lp = _d(list_price)
    if is_override and lp > 0 and unit_price < lp:
        pct = ((lp - unit_price) / lp * 100).quantize(Decimal("0.01"))
        v = _check(db, user, branch_id, "price_override", percent=pct, amount=(lp - unit_price) * qty * rate)
        if v:
            out.append(v)
    return out


def evaluate_expense(db: Session, user, branch_id: Optional[int], amount) -> Optional[Violation]:
    """Xarajat summasi (UZS) qoidadan oshdimi."""
    return _check(db, user, branch_id, "expense", amount=_d(amount))


def evaluate_refund(db: Session, user, amount, branch_id: Optional[int] = None) -> Optional[Violation]:
    """Qaytarish summasi (UZS) qoidadan oshdimi."""
    return _check(db, user, branch_id, "refund", amount=_d(amount))


def evaluate_sale_delete(db: Session, user, amount, branch_id: Optional[int] = None) -> Optional[Violation]:
    return _check(db, user, branch_id, "sale_delete", amount=_d(amount))


# ─── Majburlash (sotuv/qaytarish/o'chirish) ──────────────────────────────────

def _invalid(message: str):
    raise HTTPException(status_code=409, detail={"code": APPROVAL_INVALID, "message": message})


def consume_approval(db: Session, approval_id: int, user, action_type: Union[str, Sequence[str]],
                     payload_hash: str) -> ApprovalRequest:
    """Tasdiqni BIR MARTA ishlatadi: `approved`, shu korxona va shu so'rovchi, muddati o'tmagan, hash mos.
    Holat `used` ga o'tadi (tranzaksiya ichida — amal muvaffaqiyatsiz bo'lsa qaytadi). Aks holda 409."""
    types = (action_type,) if isinstance(action_type, str) else tuple(action_type)
    req = db.query(ApprovalRequest).filter(
        ApprovalRequest.id == approval_id, ApprovalRequest.company_id == user.company_id,
    ).with_for_update().first()
    if req is None or req.requested_by != user.id:
        _invalid("Tasdiq so'rovi topilmadi")
    if req.status == "used":
        _invalid("Bu tasdiq allaqachon ishlatilgan")
    if req.status != "approved":
        _invalid("So'rov hali tasdiqlanmagan" if req.status == "pending" else "So'rov tasdiqlanmagan yoki muddati o'tgan")
    if req.expires_at is not None and _naive(req.expires_at) <= _utcnow():
        _invalid("Tasdiq muddati o'tgan")
    if req.action_type not in types:
        _invalid("Tasdiq boshqa amal turi uchun berilgan")
    if req.payload_hash != payload_hash:
        _invalid("Tasdiqlangan so'rov boshqa tarkibga (mahsulot yoki narx) tegishli")
    req.status = "used"
    req.used_at = _utcnow()
    log_action(
        db, "APPROVAL_USE", "approval_request", req.id, user_id=user.id, company_id=req.company_id,
        branch_id=req.branch_id,
        new_values={"action_type": req.action_type, "amount": float(req.amount or 0)},
    )
    return req


def link_reference(req: Optional[ApprovalRequest], reference_type: str, reference_id: Optional[int]) -> None:
    """Ishlatilgan tasdiqni yaratilgan hujjatga (sotuv, qaytarish) bog'laydi."""
    if req is not None and reference_id is not None:
        req.reference_type = reference_type
        req.reference_id = reference_id


def enforce(db: Session, user, violations: list, *, payload: dict, amount, branch_id: Optional[int],
            approval_id: Optional[int], action_types: Optional[Sequence[str]] = None) -> Optional[ApprovalRequest]:
    """Buzilishlar bo'yicha qaror: `block` -> 403 `limit_exceeded`; `require_approval` -> `approval_id` yo'q bo'lsa
    403 `approval_required`, bor bo'lsa `consume_approval`. Buzilish yo'q bo'lsa None (approval_id e'tiborsiz)."""
    if not violations:
        return None
    for v in violations:
        if v.mode == "block":
            raise HTTPException(status_code=403, detail=v.detail("limit_exceeded"))
    first = violations[0]
    types = tuple(action_types) if action_types else tuple(dict.fromkeys(v.action_type for v in violations))
    if approval_id is None:
        raise HTTPException(status_code=403, detail=first.detail(
            "approval_required", request_action_type=types[0], payload=json_safe(payload),
            amount=float(_d(amount)), branch_id=branch_id,
        ))
    return consume_approval(db, approval_id, user, types, compute_payload_hash(payload))


# ─── So'rovlar ───────────────────────────────────────────────────────────────

def create_request(db: Session, user, *, action_type: str, branch_id: Optional[int], amount, payload: Optional[dict],
                   reason: Optional[str] = None, ttl: Optional[timedelta] = None,
                   reference_type: Optional[str] = None, reference_id: Optional[int] = None) -> ApprovalRequest:
    """Yangi `pending` so'rov (hash serverda hisoblanadi) + audit. Commit chaqiruvchida."""
    now = _utcnow()
    req = ApprovalRequest(
        company_id=user.company_id, branch_id=branch_id, action_type=action_type, status="pending",
        requested_by=user.id, amount=_d(amount), payload=json_safe(payload),
        payload_hash=compute_payload_hash(payload), reason=(reason or None),
        created_at=now, expires_at=now + (ttl or timedelta(minutes=REQUEST_TTL_MINUTES)),
        reference_type=reference_type, reference_id=reference_id,
    )
    db.add(req)
    db.flush()
    log_action(
        db, "APPROVAL_REQUEST", "approval_request", req.id, user_id=user.id, company_id=user.company_id,
        branch_id=branch_id,
        new_values={"action_type": action_type, "amount": float(req.amount or 0), "reason": reason},
    )
    return req


def _expense_of(db: Session, req: ApprovalRequest):
    if req.action_type != "expense" or req.reference_type != "expense" or not req.reference_id:
        return None
    from app.models.moliya import Expense
    # pending/rejected xarajatlar odatda hech qaysi so'rovda ko'rinmaydi (models/moliya.py) — bu yerda kerak
    return db.query(Expense).execution_options(include_unapproved_expenses=True).filter(
        Expense.id == req.reference_id, Expense.company_id == req.company_id,
    ).first()


def expire_request(db: Session, req: ApprovalRequest) -> None:
    """Muddati o'tgan (`pending`/`approved`) so'rovni `expired` qiladi (audit bilan); xarajat bo'lsa — rad etiladi."""
    req.status = "expired"
    exp = _expense_of(db, req)
    if exp is not None and exp.status == "pending":
        exp.status = "rejected"
    log_action(
        db, "APPROVAL_EXPIRE", "approval_request", req.id, user_id=None, company_id=req.company_id,
        branch_id=req.branch_id, new_values={"action_type": req.action_type},
    )


def expire_stale(db: Session, company_id: Optional[int] = None) -> int:
    """Muddati o'tgan `pending`/`approved` so'rovlarni `expired` qiladi. Commit chaqiruvchida. Soni qaytadi."""
    q = db.query(ApprovalRequest).filter(
        ApprovalRequest.status.in_(("pending", "approved")),
        ApprovalRequest.expires_at.isnot(None), ApprovalRequest.expires_at <= _utcnow(),
    )
    if company_id is not None:
        q = q.filter(ApprovalRequest.company_id == company_id)
    rows = q.all()
    for r in rows:
        expire_request(db, r)
    return len(rows)


def approver_branch_ids(db: Session, user) -> set:
    """Menejerning filiallari (T1.2: user_companies/user_branches, bo'lmasa legacy users.branch_id)."""
    from app.core.branch_context import assigned_branch_ids
    return set(assigned_branch_ids(db, user))


def can_see_request(db: Session, user, req: ApprovalRequest) -> bool:
    """So'rovni ko'rish: so'rovchi o'zi yoki approver (menejer — faqat o'z filiali)."""
    if user.role == UserRole.super_admin:
        return True
    if req.company_id != user.company_id:
        return False
    if req.requested_by == user.id:
        return True
    if user.role in (UserRole.admin, UserRole.director):
        return True
    if user.role == UserRole.manager:
        return req.branch_id is not None and req.branch_id in approver_branch_ids(db, user)
    return False


def decide(db: Session, request_id: int, approver, approve: bool, note: Optional[str] = None, *,
           role=None, branch_ids: Optional[set] = None, company_id: Optional[int] = None,
           ip: Optional[str] = None) -> ApprovalRequest:
    """So'rovni tasdiqlaydi/rad etadi (API va Telegram uchun yagona yo'l). Commit shu yerda.

    Xatolar: 404 (boshqa korxona/yo'q), 403 (o'z so'rovi, rol, boshqa filial menejeri), 409 (allaqachon hal
    qilingan), 410 (muddati o'tgan). `role`/`branch_ids`/`company_id` — Telegram bot korxonasi bo'yicha."""
    cid = company_id if company_id is not None else approver.company_id
    role = role or approver.role
    req = db.query(ApprovalRequest).filter(
        ApprovalRequest.id == request_id, ApprovalRequest.company_id == cid,
    ).with_for_update().first()
    if req is None:
        raise HTTPException(status_code=404, detail="So'rov topilmadi")
    if role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="Tasdiqlash huquqi yo'q")
    if req.requested_by == approver.id:
        raise HTTPException(status_code=403, detail="O'z so'rovingizni tasdiqlay olmaysiz")
    if role == UserRole.manager:
        ids = branch_ids if branch_ids is not None else approver_branch_ids(db, approver)
        if req.branch_id is None or req.branch_id not in ids:
            raise HTTPException(status_code=403, detail="Bu so'rov boshqa filialga tegishli")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="So'rov allaqachon hal qilingan")
    now = _utcnow()
    if req.expires_at is not None and _naive(req.expires_at) <= now:
        expire_request(db, req)
        db.commit()
        raise HTTPException(status_code=410, detail="So'rov muddati o'tgan")

    expense = _expense_of(db, req)
    req.decided_by = approver.id
    req.decided_at = now
    req.decision_note = (note or None)
    if approve:
        req.status = "approved"
        if expense is None:
            # tasdiqdan keyin amalni bajarish uchun yangi oyna
            req.expires_at = now + timedelta(minutes=REQUEST_TTL_MINUTES)
        else:
            from app.services.expense_service import approve_pending_expense
            approve_pending_expense(db, expense, approver)
            req.used_at = now      # xarajat tasdiq bilan birga bajariladi (alohida "ishlatish" yo'q)
    else:
        req.status = "rejected"
        if expense is not None:
            from app.services.expense_service import reject_pending_expense
            reject_pending_expense(db, expense)
    log_action(
        db, "APPROVAL_APPROVE" if approve else "APPROVAL_REJECT", "approval_request", req.id,
        user_id=approver.id, company_id=req.company_id, branch_id=req.branch_id, ip_address=ip,
        new_values={"action_type": req.action_type, "amount": float(req.amount or 0), "note": note,
                    "requested_by": req.requested_by},
    )
    db.commit()
    db.refresh(req)
    return req


# ─── Bildirishnoma ───────────────────────────────────────────────────────────

def notify_approvers(db: Session, req: ApprovalRequest) -> None:
    """Telegram (tugmali) va FCM push: admin/director va so'rov filiali menejeri. Xatolar yutiladi."""
    try:
        from app.utils.telegram_text import esc
        requester = db.get(User, req.requested_by)
        branch_name = req.branch.name if req.branch is not None else "—"
        label = ACTION_LABELS.get(req.action_type, req.action_type)
        text = (
            f"🔔 <b>Tasdiqlash kerak: {esc(label)}</b>\n"
            f"🏢 Filial: {esc(branch_name)}\n"
            f"👤 So'radi: {esc(requester.name if requester else '—')}\n"
            f"💰 Summa: {float(req.amount or 0):,.0f}\n"
            f"📝 Sabab: {esc(req.reason or '-')}"
        )
        from app.admin_tg_bot.notifications import approval_keyboard, trigger_instant_notification
        trigger_instant_notification(req.company_id, text, "approval", req.branch_id,
                                     reply_markup=approval_keyboard(req.id))
    except Exception as e:  # bildirishnoma asosiy amalga xalaqit bermasin
        logger.error("Tasdiq so'rovi Telegram xabari yuborilmadi (so'rov %s): %s", req.id, e)
    try:
        from app.services.mobile_service import push_to_user
        q = db.query(User.id).filter(
            User.company_id == req.company_id, User.role.in_((UserRole.admin, UserRole.director)),
        )
        ids = {r[0] for r in q.all()}
        if req.branch_id is not None:
            for r in db.query(User.id).filter(User.company_id == req.company_id, User.role == UserRole.manager,
                                              User.branch_id == req.branch_id).all():
                ids.add(r[0])
        ids.discard(req.requested_by)
        for uid in ids:
            push_to_user(db, uid, "Tasdiqlash kerak", f"{ACTION_LABELS.get(req.action_type, req.action_type)}: "
                         f"{float(req.amount or 0):,.0f}", {"type": "approval", "request_id": req.id})
    except Exception as e:
        logger.error("Tasdiq so'rovi push yuborilmadi (so'rov %s): %s", req.id, e)


def notify_approvers_by_id(request_id: int) -> None:
    """Fon vazifasi uchun: so'rovni O'Z sessiyasida yuklab `notify_approvers` ni chaqiradi (javobdan keyin
    so'rov sessiyasi yopilgan bo'lishi mumkin). Xatolar yutiladi."""
    import app.database as _database
    db = _database.SessionLocal()
    try:
        req = db.get(ApprovalRequest, request_id)
        if req is not None:
            notify_approvers(db, req)
    except Exception as e:
        logger.error("Tasdiq so'rovi bildirishnomasi yuborilmadi (so'rov %s): %s", request_id, e)
    finally:
        db.close()
