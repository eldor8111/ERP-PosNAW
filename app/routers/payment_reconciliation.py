"""T3.18: provayder ko'chirmasi (CSV) bilan ichki to'lovlarni solishtirish.

Hech narsa yozmaydi (faqat o'qiydi). CSV ustunlari: `date, amount, reference`. Moslik tartibi:
  1) `reference` + summa bir xil;
  2) qolganlari uchun summa bir xil va vaqt farqi +-5 daqiqa.
Provayder ko'chirmasidagi vaqt mahalliy (standart UTC+5, `tz_offset_hours`), bazada vaqt UTC saqlanadi."""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.sale import Sale, SalePayment, SaleStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/finance/reconciliation", tags=["Payment reconciliation"])

RECON_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant, UserRole.manager)

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 50000
TIME_TOLERANCE = timedelta(minutes=5)
AMOUNT_EPS = Decimal("0.01")

CSV_REQUIRED = ("date", "amount", "reference")
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
)

Provider = Literal["payme", "click", "uzum", "uzcard", "humo"]


def _parse_dt(raw: str, row_no: int) -> datetime:
    s = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"CSV {row_no}-qator: sana noto'g'ri ({raw!r})")


def _parse_amount(raw: str, row_no: int) -> Decimal:
    s = (raw or "").strip().replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"CSV {row_no}-qator: summa noto'g'ri ({raw!r})")
    return v


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="CSV kodirovkasi noto'g'ri (UTF-8 bo'lishi kerak)")


def parse_provider_csv(content: bytes) -> List[dict]:
    """CSV (`date, amount, reference`) ni qatorlar ro'yxatiga o'giradi; format xato bo'lsa 400."""
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="CSV fayl bo'sh")
    text = _decode(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = [h.strip().lower().lstrip("﻿") for h in next(reader)]
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV fayl bo'sh")
    missing = [c for c in CSV_REQUIRED if c not in header]
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV ustunlari yetishmaydi: {', '.join(missing)} (kerak: date, amount, reference)")
    idx = {c: header.index(c) for c in CSV_REQUIRED}
    rows = []
    for n, rec in enumerate(reader, start=2):
        if not rec or not any((c or "").strip() for c in rec):
            continue
        if len(rows) >= MAX_CSV_ROWS:
            raise HTTPException(status_code=400, detail=f"CSV qatorlari {MAX_CSV_ROWS} tadan oshmasin")
        if len(rec) <= max(idx.values()):
            raise HTTPException(status_code=400, detail=f"CSV {n}-qator: ustunlar soni yetarli emas")
        rows.append({
            "row": n,
            "date": _parse_dt(rec[idx["date"]], n),
            "amount": _parse_amount(rec[idx["amount"]], n),
            "reference": (rec[idx["reference"]] or "").strip() or None,
        })
    return rows


def _norm_ref(ref: Optional[str]) -> Optional[str]:
    r = (ref or "").strip().lower()
    return r or None


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(Decimal(a) - Decimal(b)) <= AMOUNT_EPS


def match_payments(provider_rows: List[dict], system_rows: List[dict]) -> dict:
    """Moslashtirish (sof funksiya). system_rows: {payment_id, amount, reference, local_dt, ...}."""
    matched = []
    prov_left = list(provider_rows)
    sys_left = list(system_rows)

    # 1) reference + summa
    by_ref = {}
    for s in sys_left:
        key = _norm_ref(s.get("reference"))
        if key:
            by_ref.setdefault(key, []).append(s)
    used_sys = set()
    still_prov = []
    for p in prov_left:
        key = _norm_ref(p.get("reference"))
        hit = None
        if key:
            for s in by_ref.get(key, []):
                if s["payment_id"] not in used_sys and _close(s["amount"], p["amount"]):
                    hit = s
                    break
        if hit:
            used_sys.add(hit["payment_id"])
            matched.append({"provider": p, "system": hit, "match_type": "reference"})
        else:
            still_prov.append(p)

    # 2) summa + vaqt (+-5 daqiqa): eng yaqin vaqtli
    sys_rest = [s for s in sys_left if s["payment_id"] not in used_sys]
    only_provider = []
    for p in still_prov:
        best, best_diff = None, None
        for s in sys_rest:
            if s["payment_id"] in used_sys or not _close(s["amount"], p["amount"]):
                continue
            diff = abs(s["local_dt"] - p["date"])
            if diff <= TIME_TOLERANCE and (best is None or diff < best_diff):
                best, best_diff = s, diff
        if best is not None:
            used_sys.add(best["payment_id"])
            matched.append({"provider": p, "system": best, "match_type": "amount_time"})
        else:
            only_provider.append(p)

    only_system = [s for s in system_rows if s["payment_id"] not in used_sys]
    return {"matched": matched, "only_in_system": only_system, "only_in_provider": only_provider}


def _prov_out(p: dict) -> dict:
    return {"row": p["row"], "date": p["date"].isoformat(sep=" "), "amount": float(p["amount"]), "reference": p["reference"]}


def _sys_out(s: dict) -> dict:
    return {
        "payment_id": s["payment_id"], "sale_id": s["sale_id"], "sale_number": s["sale_number"],
        "branch_id": s["branch_id"], "terminal_id": s["terminal_id"], "amount": float(s["amount"]),
        "reference": s["reference"], "created_at": s["local_dt"].isoformat(sep=" "),
    }


@router.post("/import")
def import_reconciliation(
    file: UploadFile = File(...),
    provider: Provider = Query(..., description="payme | click | uzum | uzcard | humo"),
    branch_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    tz_offset_hours: int = Query(5, ge=-12, le=14, description="Ko'chirma vaqti UTC dan necha soat farq qiladi"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*RECON_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Provayder ko'chirmasi (CSV) ni shu korxonaning ichki to'lovlari bilan solishtiradi. Hech narsa yozmaydi."""
    cid = user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from date_to dan keyin bo'lishi mumkin emas")

    # Filial: korxonaniki (404) va foydalanuvchi ruxsat doirasida (403)
    if branch_id is not None:
        if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first():
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
            raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")

    content = file.file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status_code=400, detail="CSV fayl hajmi 5MB dan oshmasligi kerak")
    rows = parse_provider_csv(content)

    # Sana oralig'i (mahalliy vaqt): berilmasa ko'chirma qatorlari oralig'i
    if date_from is None and date_to is None and rows:
        lo = min(r["date"] for r in rows).replace(hour=0, minute=0, second=0, microsecond=0)
        hi = max(r["date"] for r in rows).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        lo = datetime.combine(date_from, datetime.min.time()) if date_from else None
        hi = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1) if date_to else None
    if lo is not None:
        rows = [r for r in rows if r["date"] >= lo]
    if hi is not None:
        rows = [r for r in rows if r["date"] < hi]

    off = timedelta(hours=tz_offset_hours)
    q = (
        db.query(SalePayment, Sale)
        .join(Sale, SalePayment.sale_id == Sale.id)
        .filter(
            Sale.company_id == cid,
            SalePayment.payment_type == provider,
            Sale.original_sale_id.is_(None),
            Sale.status.in_([SaleStatus.completed, SaleStatus.partial_refund, SaleStatus.refunded]),
        )
    )
    if branch_id is not None:
        q = q.filter(Sale.branch_id == branch_id)
    else:
        scope = ctx.scope_ids()
        if scope is not None:
            q = q.filter(Sale.branch_id.in_(list(scope)))
    if lo is not None:
        q = q.filter(Sale.created_at >= lo - off - TIME_TOLERANCE)
    if hi is not None:
        q = q.filter(Sale.created_at < hi - off + TIME_TOLERANCE)

    system_rows = []
    for pay, sale in q.order_by(Sale.created_at, SalePayment.id).all():
        local_dt = (sale.created_at.replace(tzinfo=None) if sale.created_at.tzinfo else sale.created_at) + off
        if (lo is not None and local_dt < lo) or (hi is not None and local_dt >= hi):
            continue
        system_rows.append({
            "payment_id": pay.id, "sale_id": sale.id, "sale_number": sale.number, "branch_id": sale.branch_id,
            "terminal_id": pay.terminal_id, "amount": Decimal(str(pay.amount or 0)),
            "reference": pay.reference, "local_dt": local_dt,
        })

    res = match_payments(rows, system_rows)
    sum_m = sum((m["provider"]["amount"] for m in res["matched"]), Decimal("0"))
    sum_s = sum((s["amount"] for s in res["only_in_system"]), Decimal("0"))
    sum_p = sum((p["amount"] for p in res["only_in_provider"]), Decimal("0"))
    return {
        "provider": provider,
        "branch_id": branch_id,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "matched": [
            {"provider": _prov_out(m["provider"]), "system": _sys_out(m["system"]), "match_type": m["match_type"]}
            for m in res["matched"]
        ],
        "only_in_system": [_sys_out(s) for s in res["only_in_system"]],
        "only_in_provider": [_prov_out(p) for p in res["only_in_provider"]],
        "totals": {
            "provider_rows": len(rows),
            "system_payments": len(system_rows),
            "matched_count": len(res["matched"]),
            "matched_amount": float(sum_m),
            "only_in_system_count": len(res["only_in_system"]),
            "only_in_system_amount": float(sum_s),
            "only_in_provider_count": len(res["only_in_provider"]),
            "only_in_provider_amount": float(sum_p),
        },
    }
