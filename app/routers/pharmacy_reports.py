"""D4.1 — Dorixona hisobotlari: yaroqlilik muddati (seriya bo'yicha qoldiq) va hisobdan chiqarish dalolatnomasi.

Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403). Hisobotlar faqat o'qiydi:
haqiqiy hisobdan chiqarish mavjud `POST /inventory/write-off-expired` orqali bajariladi,
dalolatnoma esa shu amalning rasmiy hujjati (PDF).
Qoida yagona manbadan: `app.services.expiry.expired_batches_query` (dorixonada hamma dori).
"""
import csv
import io
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services.expiry import expired_batches_query
from app.utils.report_utils import local_today

router = APIRouter(
    prefix="/pharmacy/reports",
    tags=["Pharmacy reports"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

REPORT_VIEW_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager,
    UserRole.accountant, UserRole.warehouse,
)

DAYS_PATTERN = "^(30|60|90|expired)$"
OTHER_BRANCH = "Bu filial ma'lumotiga ruxsat yo'q"
DEFAULT_REASON = "Yaroqlilik muddati o'tgan"
MAX_ROWS = 5000


# ─── Umumiy: doira, so'rov, qatorlar ─────────────────────────────────────────

def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _warehouse_scope(
    db: Session, user: User, ctx: BranchContext,
    branch_id: Optional[int], warehouse_id: Optional[int],
) -> Optional[List[int]]:
    """Ombor id'lari ro'yxati: None — cheklov yo'q (butun korxona). Boshqa korxona resursi -> 404,
    foydalanuvchining filial doirasidan tashqari filial/ombor -> 403."""
    cid = user.company_id
    allowed = ctx.allowed_branch_ids  # None — cheklanmagan
    wq = db.query(Warehouse.id).filter(Warehouse.company_id == cid)
    restrict = False

    if branch_id:
        if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first():
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        if allowed is not None and branch_id not in allowed:
            raise HTTPException(status_code=403, detail=OTHER_BRANCH)
        wq = wq.filter(Warehouse.branch_id == branch_id)
        restrict = True
    if warehouse_id:
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id, Warehouse.company_id == cid).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
        if allowed is not None and wh.branch_id not in allowed:
            raise HTTPException(status_code=403, detail=OTHER_BRANCH)
        wq = wq.filter(Warehouse.id == warehouse_id)
        restrict = True

    # Filial konteksti (X-Branch-Id) yoki biriktirilgan filiallar bilan cheklash
    scope_ids = ctx.scope_ids()
    if scope_ids is not None:
        wq = wq.filter(Warehouse.branch_id.in_(list(scope_ids)))
        restrict = True
    return [r[0] for r in wq.all()] if restrict else None


def _status_of(days_left: int) -> str:
    if days_left < 0:
        return "expired"
    if days_left <= 30:
        return "30"
    if days_left <= 60:
        return "60"
    return "90"


def _num(v) -> float:
    return float(v or 0)


def _expiry_rows(
    db: Session, user: User, ctx: BranchContext, *,
    days: str, branch_id: Optional[int], warehouse_id: Optional[int],
    search: Optional[str], batch_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    today = local_today()
    warehouse_ids = _warehouse_scope(db, user, ctx, branch_id, warehouse_id)

    kwargs: Dict[str, Any] = {"warehouse_ids": warehouse_ids, "pharmacy": True}
    if days == "expired":
        kwargs["only_expired"] = True
    else:
        # Muddati o'tmaganlar: bugundan N kun ichida tugaydiganlar
        kwargs["expiry_from"] = today
        kwargs["expiry_until"] = today + timedelta(days=int(days))

    q = (
        expired_batches_query(db, user.company_id, today, **kwargs)
        .outerjoin(Warehouse, Warehouse.id == Batch.warehouse_id)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .outerjoin(ProductVariant, ProductVariant.id == Batch.variant_id)
    )
    if batch_ids:
        q = q.filter(Batch.id.in_(batch_ids))
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(or_(
            Product.name.ilike(like), Product.barcode.ilike(like), Product.sku.ilike(like),
            Batch.lot_number.ilike(like),
        ))
    rows = (
        q.with_entities(Batch, Product.name, Product.unit, ProductVariant.name,
                        Warehouse.name, Warehouse.branch_id, Branch.name)
        .order_by(Batch.expiry_date.asc(), Batch.id.asc())
        .limit(MAX_ROWS)
        .all()
    )

    result = []
    for b, p_name, p_unit, v_name, w_name, w_branch_id, br_name in rows:
        expiry = b.expiry_date.date() if hasattr(b.expiry_date, "date") else b.expiry_date
        left = (expiry - today).days
        qty = _num(b.quantity)
        cost = _num(b.purchase_price)
        result.append({
            "batch_id": b.id,
            "product_id": b.product_id,
            "product_name": p_name,
            "variant_name": v_name,
            "unit": p_unit,
            "lot_number": b.lot_number,
            "expiry_date": expiry.isoformat(),
            "days_left": left,
            "status": _status_of(left),
            "warehouse_id": b.warehouse_id,
            "warehouse_name": w_name,
            "branch_id": w_branch_id,
            "branch_name": br_name,
            "quantity": qty,
            "unit_cost": cost,
            "amount": round(qty * cost, 2),
        })
    return result


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, Dict[str, float]] = {}
    for r in rows:
        s = by_status.setdefault(r["status"], {"batches": 0, "quantity": 0.0, "amount": 0.0})
        s["batches"] += 1
        s["quantity"] += r["quantity"]
        s["amount"] += r["amount"]
    return {
        "batches": len(rows),
        "quantity": round(sum(r["quantity"] for r in rows), 3),
        "amount": round(sum(r["amount"] for r in rows), 2),
        "by_status": {k: {"batches": v["batches"], "quantity": round(v["quantity"], 3),
                          "amount": round(v["amount"], 2)} for k, v in by_status.items()},
    }


def _parse_ids(raw: Optional[str]) -> Optional[List[int]]:
    if not raw or not raw.strip():
        return None
    try:
        return [int(x) for x in raw.replace(" ", "").split(",") if x]
    except ValueError:
        raise HTTPException(status_code=422, detail="batch_ids: vergul bilan ajratilgan butun sonlar bo'lishi kerak")


def _split_names(values: Optional[List[str]]) -> List[str]:
    """Komissiya a'zolari: takrorlangan parametr yoki vergul bilan ajratilgan qator."""
    out: List[str] = []
    for v in values or []:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return out[:12]


# ─── Muddat hisoboti ─────────────────────────────────────────────────────────

@router.get("/expiry")
def expiry_report(
    branch_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    days: str = Query("30", pattern=DAYS_PATTERN, description="30 | 60 | 90 (kun ichida tugaydi) | expired (muddati o'tgan)"),
    search: Optional[str] = Query(None, description="Mahsulot nomi, shtrix-kod, SKU yoki seriya"),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Seriya/muddat bo'yicha qoldiq: mahsulot, seriya, muddat, ombor, filial, miqdor, kirim narxi, summa.
    `format=csv` — Excel ochadigan (UTF-8 BOM) fayl."""
    _company_id(current_user)
    rows = _expiry_rows(db, current_user, ctx, days=days, branch_id=branch_id,
                        warehouse_id=warehouse_id, search=search)

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["Mahsulot", "Seriya", "Muddat", "Qolgan kun", "Ombor", "Filial",
                    "Miqdor", "Kirim narxi", "Summa"])
        for r in rows:
            name = r["product_name"] + (f" ({r['variant_name']})" if r["variant_name"] else "")
            w.writerow([name, r["lot_number"] or "", r["expiry_date"], r["days_left"],
                        r["warehouse_name"] or "", r["branch_name"] or "",
                        f"{r['quantity']:g}", f"{r['unit_cost']:.2f}", f"{r['amount']:.2f}"])
        return Response(
            content=buf.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=muddat_hisoboti_{days}_{local_today():%Y%m%d}.csv"},
        )

    return {"days": days, "today": local_today().isoformat(), "rows": rows, "summary": _summary(rows)}


# ─── Hisobdan chiqarish dalolatnomasi (PDF) ──────────────────────────────────

_FONT_REGULAR = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    os.path.join(os.path.dirname(__file__), "..", "utils", "DejaVuSans.ttf"),
]
_FONT_BOLD = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _first_existing(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _money(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _qty(v: float) -> str:
    return f"{v:g}"


def build_write_off_pdf(
    *, company_name: str, branch_label: str, act_date: date, rows: List[Dict[str, Any]],
    commission: List[str], reason: str,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(10, 10, 10)

    reg = _first_existing(_FONT_REGULAR)
    unicode_ok = reg is not None
    family = "helvetica"
    if unicode_ok:
        family = "ActFont"
        pdf.add_font(family, "", reg)
        pdf.add_font(family, "B", _first_existing(_FONT_BOLD) or reg)

    def txt(s: Any) -> str:
        s = "" if s is None else str(s)
        # Unicode shrift topilmasa — standart (latin-1) shrift uchun belgilarni almashtiramiz
        return s if unicode_ok else s.encode("latin-1", "replace").decode("latin-1")

    def fit(s: Any, w: float) -> str:
        s = txt(s)
        w -= 2
        if pdf.get_string_width(s) <= w:
            return s
        while s and pdf.get_string_width(s + "...") > w:
            s = s[:-1]
        return s + "..."

    cols = [("T/r", 10, "C"), ("Mahsulot", 82, "L"), ("Seriya", 34, "L"), ("Muddat", 24, "C"),
            ("Ombor", 40, "L"), ("Miqdor", 24, "R"), ("Kirim narxi", 28, "R"), ("Summa", 35, "R")]

    def table_header():
        pdf.set_font(family, "B", 9)
        for name, w, _ in cols:
            pdf.cell(w, 7, txt(name), border=1, align="C")
        pdf.ln()
        pdf.set_font(family, "", 9)

    pdf.add_page()
    pdf.set_font(family, "B", 14)
    pdf.cell(0, 8, txt("HISOBDAN CHIQARISH DALOLATNOMASI"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 10)
    pdf.cell(0, 6, txt(f"Korxona: {company_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Filial: {branch_label}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Sana: {act_date:%d.%m.%Y}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Sabab: {reason}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    table_header()

    total_qty = 0.0
    total_amount = 0.0
    for i, r in enumerate(rows, 1):
        if pdf.get_y() > 185:
            pdf.add_page()
            table_header()
        name = r["product_name"] + (f" ({r['variant_name']})" if r["variant_name"] else "")
        vals = [str(i), name, r["lot_number"] or "-", date.fromisoformat(r["expiry_date"]).strftime("%d.%m.%Y"),
                r["warehouse_name"] or "-", _qty(r["quantity"]), _money(r["unit_cost"]), _money(r["amount"])]
        for (_, w, al), v in zip(cols, vals):
            pdf.cell(w, 6, fit(v, w), border=1, align=al)
        pdf.ln()
        total_qty += r["quantity"]
        total_amount += r["amount"]

    pdf.set_font(family, "B", 9)
    pdf.cell(sum(c[1] for c in cols[:5]), 7, txt("JAMI:"), border=1, align="R")
    pdf.cell(cols[5][1], 7, _qty(round(total_qty, 3)), border=1, align="R")
    pdf.cell(cols[6][1], 7, "", border=1)
    pdf.cell(cols[7][1], 7, _money(total_amount), border=1, align="R")
    pdf.ln(12)

    # Komissiya imzolari
    if pdf.get_y() > 160:
        pdf.add_page()
    pdf.set_font(family, "B", 10)
    pdf.cell(0, 6, txt("Komissiya a'zolari:"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 10)
    members = commission or ["", "", ""]
    for n, m in enumerate(members, 1):
        pdf.cell(10, 8, f"{n}.")
        pdf.cell(100, 8, fit(m, 100) if m else "", border="B")
        pdf.cell(10, 8, "")
        pdf.cell(50, 8, txt("(imzo)"), border="T", align="C", new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out)


@router.get("/write-off-act")
def write_off_act(
    branch_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    days: str = Query("expired", pattern=DAYS_PATTERN),
    search: Optional[str] = Query(None),
    batch_ids: Optional[str] = Query(None, description="Faqat shu partiyalar (vergul bilan); bo'sh — filtrdagi hammasi"),
    commission: Optional[List[str]] = Query(None, description="Komissiya a'zolari (takrorlanadi yoki vergul bilan)"),
    reason: Optional[str] = Query(None, max_length=200, description="Hisobdan chiqarish sababi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Hisobdan chiqarish dalolatnomasi (PDF): korxona, filial, sana, komissiya, qatorlar
    (seriya, muddat, miqdor, summa), sabab. Faqat hujjat — qoldiqni o'zgartirmaydi."""
    cid = _company_id(current_user)
    rows = _expiry_rows(db, current_user, ctx, days=days, branch_id=branch_id, warehouse_id=warehouse_id,
                        search=search, batch_ids=_parse_ids(batch_ids))
    if not rows:
        raise HTTPException(status_code=404, detail="Dalolatnoma uchun partiya topilmadi")

    company = db.get(Company, cid)
    branch_ids = {r["branch_id"] for r in rows if r["branch_id"]}
    if len(branch_ids) == 1:
        branch_label = next(r["branch_name"] for r in rows if r["branch_id"])
    elif branch_ids:
        branch_label = "Barcha filiallar"
    else:
        branch_label = "-"

    pdf_bytes = build_write_off_pdf(
        company_name=company.name if company else "",
        branch_label=branch_label,
        act_date=local_today(),
        rows=rows,
        commission=_split_names(commission),
        reason=(reason or "").strip() or DEFAULT_REASON,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=dalolatnoma_{local_today():%Y%m%d}.pdf"},
    )
