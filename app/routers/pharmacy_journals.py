"""D4.4 — Dorixona jurnallari: nazoratdagi dorilar harakati va retseptli sotuvlar jurnali.

Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403).

JURNAL TAHRIRLANMAYDI: alohida o'zgaruvchan jadval yo'q — har so'rovda manba yozuvlardan
(StockMovement, SalePrescription, Sale) qayta hisoblanadi. Shuning uchun bu yerda faqat GET bor;
yozish (POST/PUT/PATCH/DELETE) umuman mavjud emas. Xato yozuvni tuzatish faqat TESKARI HUJJAT
orqali bajariladi: sotuv uchun qaytarish (sale_refund), kirim uchun yetkazuvchiga qaytarish yoki
tuzatish (ADJUST), ortiqcha hisobdan chiqarish uchun inventarizatsiya/kirim. Teskari hujjat jurnalda
alohida qator bo'lib ko'rinadi ("Tuzatish/teskari hujjat"), asl qator esa o'zgarmay qoladi.

Oy boshi/oxiri qoldiq: oxiri = hozirgi qoldiq (StockLevel) − oy tugagandan keyingi harakatlar yig'indisi,
boshi = oxiri − oy ichidagi harakatlar yig'indisi. Shunda boshi + kirim − chiqim = oxiri doim bajariladi.
"""
import csv
import io
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.company import Company
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.prescription import SalePrescription
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User
from app.models.warehouse import Warehouse
from app.routers.pharmacy_reports import (
    _FONT_BOLD, _FONT_REGULAR, REPORT_VIEW_ROLES, _company_id, _first_existing, _qty, _warehouse_scope,
)
from app.utils.report_utils import local_day_start, local_today

router = APIRouter(
    prefix="/pharmacy/journals",
    tags=["Pharmacy journals"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_ROWS = 5000
CHUNK = 500
JOURNAL_NOTE = (
    "Jurnal tizim yozuvlaridan avtomatik hosil qilinadi va tahrirlanmaydi. "
    "Xatoni tuzatish faqat teskari hujjat (qaytarish, tuzatish) orqali bajariladi."
)

KIND_LABELS = {
    "receipt": "Kirim",
    "sale": "Sotuv",
    "return_customer": "Mijozdan qaytarish",
    "return_supplier": "Yetkazuvchiga qaytarish",
    "write_off": "Hisobdan chiqarish",
    "transfer_in": "Transfer (kirim)",
    "transfer_out": "Transfer (chiqim)",
    "adjustment": "Tuzatish",
    "reversal": "Teskari hujjat",
    "other": "Boshqa",
}


# ─── Umumiy yordamchilar ─────────────────────────────────────────────────────

def _num(v) -> float:
    return float(v or 0)


def _chunks(ids: List[int]):
    for i in range(0, len(ids), CHUNK):
        yield ids[i:i + CHUNK]


def _month_bounds(month: Optional[str]):
    """'YYYY-MM' -> (oy boshi sanasi, keyingi oy boshi sanasi). Bo'sh bo'lsa — joriy oy."""
    if month:
        y, m = int(month[:4]), int(month[5:7])
        first = date(y, m, 1)
    else:
        t = local_today()
        first = date(t.year, t.month, 1)
    nxt = date(first.year + (first.month // 12), first.month % 12 + 1, 1)
    return first, nxt


def _movement_kind(mv: StockMovement) -> str:
    """Harakat turi: avval hujjat turi (reference_type), keyin MovementType bo'yicha."""
    ref = mv.reference_type or ""
    mtype = mv.type.value if hasattr(mv.type, "value") else str(mv.type)
    if ref.endswith("_revert") or ref.endswith("_delete"):
        return "reversal"
    if ref == "sale":
        return "sale"
    if ref in ("sale_refund", "return_from_customer"):
        return "return_customer"
    if ref == "return_to_supplier":
        return "return_supplier"
    if ref == "batch_write_off" or mtype == MovementType.EXPIRED.value:
        return "write_off"
    if mtype == MovementType.TRANSFER_IN.value:
        return "transfer_in"
    if mtype == MovementType.TRANSFER_OUT.value:
        return "transfer_out"
    if mtype == MovementType.RETURN.value:
        return "return_customer"
    if mtype == MovementType.ADJUST.value or ref in ("adjustment", "revision"):
        return "adjustment"
    if mtype == MovementType.IN.value:
        return "receipt"
    if mtype == MovementType.OUT.value:
        return "write_off" if ref == "chiqim" else "other"
    return "other"


def _controlled_products(db: Session, cid: int, product_id: Optional[int]) -> Dict[int, Dict[str, Any]]:
    """Korxonaning nazoratdagi (control_class != none) dorilari. product_id boshqa korxonaniki -> 404."""
    if product_id:
        if not db.query(Product.id).filter(Product.id == product_id, Product.company_id == cid).first():
            raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    q = (
        db.query(Product.id, Product.name, Product.unit, ProductPharma.control_class)
        .join(ProductPharma, ProductPharma.product_id == Product.id)
        .filter(Product.company_id == cid, ProductPharma.control_class != "none")
    )
    if product_id:
        q = q.filter(Product.id == product_id)
    return {pid: {"product_id": pid, "name": name, "unit": unit, "control_class": cc}
            for pid, name, unit, cc in q.all()}


def _sum_by_product(db: Session, pids: List[int], wh_ids: Optional[List[int]], *,
                    since: Optional[datetime] = None, until: Optional[datetime] = None) -> Dict[int, float]:
    """Harakatlar yig'indisi (qty_after − qty_before) mahsulot kesimida; since <= created_at < until."""
    out: Dict[int, float] = {}
    for part in _chunks(pids):
        q = db.query(StockMovement.product_id, func.sum(StockMovement.qty_after - StockMovement.qty_before)) \
            .filter(StockMovement.product_id.in_(part))
        if since is not None:
            q = q.filter(StockMovement.created_at >= since)
        if until is not None:
            q = q.filter(StockMovement.created_at < until)
        if wh_ids is not None:
            q = q.filter(StockMovement.warehouse_id.in_(wh_ids))
        for pid, s in q.group_by(StockMovement.product_id).all():
            out[pid] = _num(s)
    return out


def _stock_now(db: Session, pids: List[int], wh_ids: Optional[List[int]]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for part in _chunks(pids):
        q = db.query(StockLevel.product_id, func.sum(StockLevel.quantity)).filter(StockLevel.product_id.in_(part))
        if wh_ids is not None:
            q = q.filter(StockLevel.warehouse_id.in_(wh_ids))
        for pid, s in q.group_by(StockLevel.product_id).all():
            out[pid] = _num(s)
    return out


def _sale_docs(db: Session, cid: int, sale_ids: List[int]):
    """Sotuv hujjatlari raqami va retsept qatorlari (faqat retsept raqami bor qatorlar)."""
    numbers: Dict[int, str] = {}
    rx: Dict[int, List[SalePrescription]] = {}
    for part in _chunks(sale_ids):
        for sid, num in db.query(Sale.id, Sale.number).filter(Sale.id.in_(part), Sale.company_id == cid).all():
            numbers[sid] = num
        for p in db.query(SalePrescription).filter(
            SalePrescription.sale_id.in_(part), SalePrescription.company_id == cid,
            SalePrescription.number.isnot(None),
        ).all():
            rx.setdefault(p.sale_id, []).append(p)
    return numbers, rx


# ─── 1. Nazoratdagi dorilar harakati jurnali ─────────────────────────────────

def _controlled_journal(
    db: Session, user: User, ctx: BranchContext, *,
    month: Optional[str], product_id: Optional[int], branch_id: Optional[int],
) -> Dict[str, Any]:
    cid = _company_id(user)
    first, nxt = _month_bounds(month)
    start, end = local_day_start(first), local_day_start(nxt)
    wh_ids = _warehouse_scope(db, user, ctx, branch_id, None)
    products = _controlled_products(db, cid, product_id)
    result: Dict[str, Any] = {
        "month": f"{first.year:04d}-{first.month:02d}", "from": first.isoformat(),
        "to": (nxt - timedelta(days=1)).isoformat(), "branch_id": branch_id, "product_id": product_id,
        "note": JOURNAL_NOTE, "products": [], "rows": [], "truncated": False,
    }
    if not products or (wh_ids is not None and not wh_ids):
        return result
    pids = list(products.keys())

    # Oy boshi / oxiri qoldiq (hozirgi qoldiqdan orqaga hisoblanadi)
    now_qty = _stock_now(db, pids, wh_ids)
    after = _sum_by_product(db, pids, wh_ids, since=end)
    inside = _sum_by_product(db, pids, wh_ids, since=start, until=end)

    # Oy ichidagi harakatlar
    rows: List[Any] = []
    for part in _chunks(pids):
        q = (
            db.query(StockMovement, Warehouse.name, User.name)
            .outerjoin(Warehouse, Warehouse.id == StockMovement.warehouse_id)
            .outerjoin(User, User.id == StockMovement.user_id)
            .filter(StockMovement.product_id.in_(part),
                    StockMovement.created_at >= start, StockMovement.created_at < end)
        )
        if wh_ids is not None:
            q = q.filter(StockMovement.warehouse_id.in_(wh_ids))
        rows.extend(q.all())
    rows.sort(key=lambda r: (r[0].created_at, r[0].id))
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS]
        result["truncated"] = True

    sale_ids = sorted({m.reference_id for m, _, _ in rows
                       if m.reference_id and m.reference_type in ("sale", "sale_refund")})
    numbers, rx_by_sale = _sale_docs(db, cid, sale_ids) if sale_ids else ({}, {})

    closing = {pid: round(now_qty.get(pid, 0.0) - after.get(pid, 0.0), 3) for pid in pids}
    balance = {pid: round(closing[pid] - inside.get(pid, 0.0), 3) for pid in pids}
    opening = dict(balance)
    totals = {pid: {"receipts": 0.0, "issues": 0.0, "by_kind": {}} for pid in pids}

    out_rows: List[Dict[str, Any]] = []
    for mv, wh_name, user_name in rows:
        pid = mv.product_id
        p = products[pid]
        delta = round(_num(mv.qty_after) - _num(mv.qty_before), 3)
        kind = _movement_kind(mv)
        balance[pid] = round(balance[pid] + delta, 3)
        t = totals[pid]
        if delta > 0:
            t["receipts"] += delta
        else:
            t["issues"] += -delta
        k = t["by_kind"].setdefault(kind, 0.0)
        t["by_kind"][kind] = round(k + delta, 3)

        prescriptions: List[Dict[str, Any]] = []
        if kind in ("sale", "return_customer") and mv.reference_type in ("sale", "sale_refund"):
            for rp in rx_by_sale.get(mv.reference_id, []):
                if rp.product_id is None or rp.product_id == pid:
                    prescriptions.append({
                        "number": rp.number, "issued_at": rp.issued_at.isoformat() if rp.issued_at else None,
                        "doctor": rp.doctor, "clinic": rp.clinic, "patient": rp.patient,
                        "blank_type": rp.blank_type,
                    })
        out_rows.append({
            "id": mv.id,
            "date": mv.created_at.isoformat() if mv.created_at else None,
            "product_id": pid, "product_name": p["name"], "unit": p["unit"], "control_class": p["control_class"],
            "kind": kind, "kind_label": KIND_LABELS[kind], "movement_type": mv.type.value if hasattr(mv.type, "value") else str(mv.type),
            "warehouse_id": mv.warehouse_id, "warehouse_name": wh_name,
            "delta": delta, "in_qty": delta if delta > 0 else 0.0, "out_qty": -delta if delta < 0 else 0.0,
            "balance_after": balance[pid],
            "document_type": mv.reference_type, "document_id": mv.reference_id,
            "document_number": numbers.get(mv.reference_id) if mv.reference_type in ("sale", "sale_refund") else None,
            "rx_number": ", ".join(x["number"] for x in prescriptions) or None,
            "prescriptions": prescriptions,
            # Nazoratdagi dori retseptsiz sotilgan bo'lsa — auditor ko'rishi uchun belgi
            "rx_missing": kind == "sale" and not prescriptions,
            "reason": mv.reason, "user_name": user_name,
        })

    for pid in pids:
        if not (opening[pid] or closing[pid] or totals[pid]["receipts"] or totals[pid]["issues"]):
            continue  # qoldig'i ham, harakati ham yo'q dori jurnalga kirmaydi
        p = products[pid]
        result["products"].append({
            **p, "opening": opening[pid], "receipts": round(totals[pid]["receipts"], 3),
            "issues": round(totals[pid]["issues"], 3), "closing": closing[pid],
            "by_kind": totals[pid]["by_kind"],
        })
    result["products"].sort(key=lambda x: (x["name"] or "", x["product_id"]))
    result["rows"] = out_rows
    return result


def _controlled_csv(data: Dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Sana", "Dori", "Nazorat sinfi", "Harakat", "Hujjat", "Retsept raqami", "Ombor",
                "Kirim", "Chiqim", "Qoldiq", "Izoh"])
    for r in data["rows"]:
        doc = r["document_number"] or (f"{r['document_type']}#{r['document_id']}" if r["document_type"] else "")
        w.writerow([r["date"] or "", r["product_name"], r["control_class"], r["kind_label"], doc,
                    r["rx_number"] or "", r["warehouse_name"] or "",
                    f"{r['in_qty']:g}", f"{r['out_qty']:g}", f"{r['balance_after']:g}", r["reason"] or ""])
    w.writerow([])
    w.writerow(["Dori", "Oy boshi qoldiq", "Kirim", "Chiqim", "Oy oxiri qoldiq"])
    for p in data["products"]:
        w.writerow([p["name"], f"{p['opening']:g}", f"{p['receipts']:g}", f"{p['issues']:g}", f"{p['closing']:g}"])
    return buf.getvalue().encode("utf-8-sig")


def build_controlled_pdf(*, company_name: str, data: Dict[str, Any]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(10, 10, 10)
    reg = _first_existing(_FONT_REGULAR)
    unicode_ok = reg is not None
    family = "helvetica"
    if unicode_ok:
        family = "JrnFont"
        pdf.add_font(family, "", reg)
        pdf.add_font(family, "B", _first_existing(_FONT_BOLD) or reg)

    def txt(s: Any) -> str:
        s = "" if s is None else str(s)
        return s if unicode_ok else s.encode("latin-1", "replace").decode("latin-1")

    def fit(s: Any, w: float) -> str:
        s = txt(s)
        w -= 2
        if pdf.get_string_width(s) <= w:
            return s
        while s and pdf.get_string_width(s + "...") > w:
            s = s[:-1]
        return s + "..."

    cols = [("Sana", 30, "C"), ("Harakat", 38, "L"), ("Hujjat", 40, "L"), ("Retsept", 52, "L"),
            ("Ombor", 38, "L"), ("Kirim", 22, "R"), ("Chiqim", 22, "R"), ("Qoldiq", 25, "R")]

    def table_header():
        pdf.set_font(family, "B", 9)
        for name, w, _ in cols:
            pdf.cell(w, 7, txt(name), border=1, align="C")
        pdf.ln()
        pdf.set_font(family, "", 8)

    pdf.add_page()
    pdf.set_font(family, "B", 14)
    pdf.cell(0, 8, txt("NAZORATDAGI DORILAR HARAKATI JURNALI"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 10)
    pdf.cell(0, 6, txt(f"Korxona: {company_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Davr: {data['month']} ({data['from']} — {data['to']})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 8)
    pdf.cell(0, 5, txt(JOURNAL_NOTE), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    by_product: Dict[int, List[Dict[str, Any]]] = {}
    for r in data["rows"]:
        by_product.setdefault(r["product_id"], []).append(r)

    if not data["products"]:
        pdf.set_font(family, "", 10)
        pdf.cell(0, 8, txt("Tanlangan davrda nazoratdagi dori harakati yo'q"), new_x="LMARGIN", new_y="NEXT")

    for p in data["products"]:
        if pdf.get_y() > 170:
            pdf.add_page()
        pdf.set_font(family, "B", 10)
        pdf.cell(0, 7, txt(f"{p['name']} ({p['control_class']}) — oy boshi qoldiq: {_qty(p['opening'])} {p['unit'] or ''}"),
                 new_x="LMARGIN", new_y="NEXT")
        table_header()
        for r in by_product.get(p["product_id"], []):
            if pdf.get_y() > 185:
                pdf.add_page()
                table_header()
            doc = r["document_number"] or (f"{r['document_type']}#{r['document_id']}" if r["document_type"] else "-")
            vals = [(r["date"] or "")[:16].replace("T", " "), r["kind_label"], doc, r["rx_number"] or "-",
                    r["warehouse_name"] or "-", _qty(r["in_qty"]), _qty(r["out_qty"]), _qty(r["balance_after"])]
            for (_, w, al), v in zip(cols, vals):
                pdf.cell(w, 6, fit(v, w), border=1, align=al)
            pdf.ln()
        pdf.set_font(family, "B", 9)
        pdf.cell(sum(c[1] for c in cols[:5]), 7, txt("Jami:"), border=1, align="R")
        pdf.cell(cols[5][1], 7, _qty(p["receipts"]), border=1, align="R")
        pdf.cell(cols[6][1], 7, _qty(p["issues"]), border=1, align="R")
        pdf.cell(cols[7][1], 7, _qty(p["closing"]), border=1, align="R")
        pdf.ln(9)

    if pdf.get_y() > 175:
        pdf.add_page()
    pdf.set_font(family, "", 10)
    pdf.cell(60, 8, txt("Mas'ul shaxs:"))
    pdf.cell(80, 8, "", border="B")
    pdf.cell(10, 8, "")
    pdf.cell(40, 8, txt("(imzo)"), border="T", align="C", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


@router.get("/controlled")
def controlled_journal(
    month: Optional[str] = Query(None, pattern=MONTH_PATTERN, description="Oy: YYYY-MM (standart: joriy oy)"),
    product_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    format: str = Query("json", pattern="^(json|csv|pdf)$", description="json | csv (Excel) | pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Nazoratdagi (control_class != none) dorilar harakati: kirim, sotuv (retsept raqami bilan), qaytarish,
    hisobdan chiqarish, transfer, tuzatish; har dori uchun oy boshi/oxiri qoldiq. Faqat o'qiydi."""
    data = _controlled_journal(db, current_user, ctx, month=month, product_id=product_id, branch_id=branch_id)
    if format == "csv":
        return Response(
            content=_controlled_csv(data), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nazoratdagi_jurnal_{data['month']}.csv"},
        )
    if format == "pdf":
        company = db.get(Company, current_user.company_id)
        return Response(
            content=build_controlled_pdf(company_name=company.name if company else "", data=data),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=nazoratdagi_jurnal_{data['month']}.pdf"},
        )
    return data


# ─── 2. Retseptli sotuvlar jurnali ───────────────────────────────────────────

@router.get("/prescriptions")
def prescriptions_journal(
    date_from: Optional[date] = Query(None, alias="from", description="Boshlanish sanasi (standart: to − 29 kun)"),
    date_to: Optional[date] = Query(None, alias="to", description="Tugash sanasi, shu kun ham kiradi (standart: bugun)"),
    doctor: Optional[str] = Query(None, max_length=200, description="Shifokor (qismi bo'yicha qidiruv)"),
    clinic: Optional[str] = Query(None, max_length=200, description="Shifoxona (qismi bo'yicha qidiruv)"),
    mode: str = Query("all", pattern="^(all|with|without)$",
                      description="all — hammasi | with — retseptli | without — retseptsiz sotilganlar (sabab bilan)"),
    branch_id: Optional[int] = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Retseptli sotuvlar (SalePrescription) va retseptsiz sotilganlar (sabab bilan). Bekor qilingan va
    kutilayotgan sotuvlar kirmaydi. Faqat o'qiydi."""
    cid = _company_id(current_user)
    d_to = date_to or local_today()
    d_from = date_from or (d_to - timedelta(days=29))
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="Boshlanish sanasi tugash sanasidan keyin bo'lmasligi kerak")
    wh_ids = _warehouse_scope(db, current_user, ctx, branch_id, None)

    result: Dict[str, Any] = {
        "from": d_from.isoformat(), "to": d_to.isoformat(), "mode": mode, "branch_id": branch_id,
        "note": JOURNAL_NOTE, "rows": [], "truncated": False,
        "summary": {"total": 0, "with_rx": 0, "without_rx": 0},
    }
    if wh_ids is not None and not wh_ids:
        return _rx_response(result, format, d_from, d_to)

    wh_col = func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id)
    q = (
        db.query(SalePrescription, Sale.number, Sale.created_at, Sale.status, Product.name,
                 ProductPharma.control_class, SaleItem.quantity, Warehouse.name)
        .join(Sale, Sale.id == SalePrescription.sale_id)
        .outerjoin(Product, Product.id == SalePrescription.product_id)
        .outerjoin(ProductPharma, ProductPharma.product_id == SalePrescription.product_id)
        .outerjoin(SaleItem, SaleItem.id == SalePrescription.sale_item_id)
        .outerjoin(Warehouse, Warehouse.id == wh_col)
        .filter(
            SalePrescription.company_id == cid, Sale.company_id == cid,
            Sale.status.notin_([SaleStatus.cancelled, SaleStatus.pending]),
            Sale.created_at >= local_day_start(d_from),
            Sale.created_at < local_day_start(d_to + timedelta(days=1)),
        )
    )
    if wh_ids is not None:
        q = q.filter(wh_col.in_(wh_ids))
    if mode == "with":
        q = q.filter(SalePrescription.number.isnot(None))
    elif mode == "without":
        q = q.filter(SalePrescription.number.is_(None))
    if doctor and doctor.strip():
        q = q.filter(SalePrescription.doctor.ilike(f"%{doctor.strip()}%"))
    if clinic and clinic.strip():
        q = q.filter(SalePrescription.clinic.ilike(f"%{clinic.strip()}%"))

    found = q.order_by(Sale.created_at.asc(), SalePrescription.id.asc()).limit(MAX_ROWS + 1).all()
    if len(found) > MAX_ROWS:
        found = found[:MAX_ROWS]
        result["truncated"] = True

    rows = []
    for rp, sale_no, sale_date, status, p_name, cclass, qty, wh_name in found:
        has_rx = rp.number is not None
        rows.append({
            "id": rp.id, "sale_id": rp.sale_id, "sale_number": sale_no,
            "sale_date": sale_date.isoformat() if sale_date else None,
            "sale_status": status.value if hasattr(status, "value") else str(status),
            "product_id": rp.product_id, "product_name": p_name,
            "control_class": cclass if cclass else "none", "quantity": _num(qty) if qty is not None else None,
            "warehouse_name": wh_name,
            "has_rx": has_rx, "number": rp.number,
            "issued_at": rp.issued_at.isoformat() if rp.issued_at else None,
            "doctor": rp.doctor, "clinic": rp.clinic, "patient": rp.patient, "blank_type": rp.blank_type,
            "reason_without_rx": rp.reason_without_rx,
        })
    with_rx = sum(1 for r in rows if r["has_rx"])
    result["rows"] = rows
    result["summary"] = {"total": len(rows), "with_rx": with_rx, "without_rx": len(rows) - with_rx}
    return _rx_response(result, format, d_from, d_to)


def _rx_response(result: Dict[str, Any], fmt: str, d_from: date, d_to: date):
    if fmt != "csv":
        return result
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Sotuv sanasi", "Sotuv", "Dori", "Nazorat sinfi", "Miqdor", "Retsept raqami", "Retsept sanasi",
                "Shifokor", "Shifoxona", "Bemor", "Blank turi", "Retseptsiz sotish sababi"])
    for r in result["rows"]:
        w.writerow([r["sale_date"] or "", r["sale_number"] or "", r["product_name"] or "", r["control_class"],
                    "" if r["quantity"] is None else f"{r['quantity']:g}", r["number"] or "", r["issued_at"] or "",
                    r["doctor"] or "", r["clinic"] or "", r["patient"] or "", r["blank_type"] or "",
                    r["reason_without_rx"] or ""])
    return Response(
        content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=retsept_jurnali_{d_from:%Y%m%d}_{d_to:%Y%m%d}.csv"},
    )
