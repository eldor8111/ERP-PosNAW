"""D3.2 — Dorixona: markirovka (Data Matrix) kodlarini kuzatish.

Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403) va faqat `product.requires_marking`
mahsulotlar uchun. Oddiy do'kon markirovkani avvalgidek faqat sotuvda skanerlaydi — hech narsa bloklanmaydi.

Hayot sikli (`MarkingCode.status`):
  kirim qabuli -> in_stock -> sotuv -> sold -> qaytarish -> in_stock (qaytgan omborga)

Endpoint'lar:
  POST /api/pharmacy/marking/parse    GS1 Data Matrix kodini tahlil qiladi (GTIN, seriya, muddat, partiya)
  POST /api/pharmacy/marking/receive  qabul qilingan xarid qatoriga kodlarni biriktiradi (idempotent)
  GET  /api/pharmacy/marking          kodlar ro'yxati va holati

Quyidagi yordamchi funksiyalar servislar tomonidan chaqiriladi (kirim, sotuv, qaytarish):
  parse_gs1, canonical_code, register_receipt_codes, plan_sale_marking / apply_sale_marking,
  plan_return_marking / apply_return_marking.
"""
import calendar
import json
import re
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.batch import Batch
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.purchase_order import PurchaseOrder
from app.models.user import User, UserRole

router = APIRouter(
    prefix="/pharmacy/marking", tags=["Pharmacy marking"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)
VIEW_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager,
    UserRole.accountant, UserRole.warehouse,
)
MAX_CODES_PER_REQUEST = 5000
MAX_ROWS = 500

STATUS_LABELS = {
    "in_stock": "omborda", "sold": "sotilgan", "returned": "qaytarilgan", "written_off": "hisobdan chiqarilgan",
}

# ─── GS1 Data Matrix tahlili ─────────────────────────────────────────────────

GS = "\x1d"  # FNC1 / Group Separator
# Qat'iy uzunlikdagi AI'lar (raqamlar soni)
_FIXED_AI = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2}
# O'zgaruvchan uzunlikdagi AI'lar (maksimal uzunlik); 91..99 — kripto kalit/imzo (markirovka dumi)
_VAR_AI = {"10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "240": 30, "241": 30, "242": 6,
           "250": 30, "251": 30, "253": 30, "254": 20, "255": 25}
_VAR_AI.update({str(n): 90 for n in range(91, 100)})
_SYMBOLOGY_ID = re.compile(r"^\][A-Za-z][0-9A-Za-z]")
_PAREN = re.compile(r"\((\d{2,4})\)([^()]*)")


def _gtin_check_ok(gtin: str) -> bool:
    """GS1 nazorat raqami (mod 10): oxirgi raqam qolganlardan hisoblanadi."""
    if not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in gtin]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == digits[-1]


def _parse_yymmdd(value: str) -> Optional[date]:
    """YYMMDD -> sana; DD=00 — oy oxiri (GS1 qoidasi)."""
    if len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:])
    if not 1 <= mm <= 12:
        return None
    year = 2000 + yy
    last = calendar.monthrange(year, mm)[1]
    if dd == 0:
        dd = last
    if not 1 <= dd <= last:
        return None
    return date(year, mm, dd)


def _split_ais(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Qavssiz (xom) ko'rinish: AI + qiymat ketma-ketligi, o'zgaruvchan qiymatlar GS bilan tugaydi."""
    ais: Dict[str, str] = {}
    errors: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == GS:
            i += 1
            continue
        ai = next((text[i:i + k] for k in (2, 3, 4) if text[i:i + k] in _FIXED_AI or text[i:i + k] in _VAR_AI), None)
        if ai is None:
            errors.append(f"Noma'lum AI: '{text[i:i + 4]}'")
            break
        start = i + len(ai)
        if ai in _FIXED_AI:
            end = start + _FIXED_AI[ai]
            value = text[start:end]
            if len(value) != _FIXED_AI[ai] or not value.isdigit():
                errors.append(f"({ai}) qiymati {_FIXED_AI[ai]} raqamdan iborat bo'lishi kerak")
                break
        else:
            gs_at = text.find(GS, start)
            end = gs_at if gs_at != -1 else n
            if end - start > _VAR_AI[ai]:   # ajratgich yo'q: maksimal uzunlik bilan kesiladi
                end = start + _VAR_AI[ai]
            value = text[start:end]
            if not value:
                errors.append(f"({ai}) qiymati bo'sh")
                break
        ais.setdefault(ai, value)
        i = end
    return ais, errors


def parse_gs1(raw: Optional[str]) -> dict:
    """GS1 Data Matrix: `(01)GTIN(21)serial(17)YYMMDD(10)lot` (qavsli) yoki FNC1/GS ajratgichli xom matn.

    Hech qachon xato tashlamaydi — natijada `valid` (GTIN va seriya topildi), `errors`, `warnings`.
    `code` — kuzatuv kaliti: GTIN va seriya bo'lsa `01<GTIN>21<seriya>`, aks holda toza matn."""
    text = (raw or "").strip()
    text = _SYMBOLOGY_ID.sub("", text).replace("␝", GS).strip()
    out = {"raw": raw or "", "code": "", "valid": False, "gtin": None, "serial": None, "expiry_date": None,
           "manufacture_date": None, "lot": None, "ais": {}, "errors": [], "warnings": []}
    if not text:
        out["errors"].append("Kod bo'sh")
        return out
    if "(" in text:
        matches = list(_PAREN.finditer(text))
        leftover = _PAREN.sub("", text).replace(GS, "").strip()
        ais = {}
        for m in matches:
            ais.setdefault(m.group(1), m.group(2).replace(GS, "").strip())
        errors = [] if matches and not leftover else ["Qavsli GS1 formati noto'g'ri"]
    else:
        ais, errors = _split_ais(text)
    out["ais"] = ais
    out["errors"].extend(errors)

    gtin, serial = ais.get("01"), ais.get("21")
    if gtin is not None and not (gtin.isdigit() and len(gtin) == 14):
        out["errors"].append("GTIN (01) 14 raqamdan iborat bo'lishi kerak")
        gtin = None
    out["gtin"], out["serial"] = gtin, (serial or None)
    out["lot"] = ais.get("10") or None
    for ai, key in (("17", "expiry_date"), ("11", "manufacture_date")):
        if ai in ais:
            d = _parse_yymmdd(ais[ai])
            if d is None:
                out["warnings"].append(f"({ai}) sanasi noto'g'ri: '{ais[ai]}'")
            else:
                out[key] = d.isoformat()
    if gtin and not _gtin_check_ok(gtin):
        out["warnings"].append("GTIN nazorat raqami noto'g'ri")
    if not gtin:
        out["errors"].append("GTIN (01) topilmadi")
    if not serial:
        out["errors"].append("Seriya raqami (21) topilmadi")
    out["valid"] = bool(gtin and serial)
    clean = text.replace(GS, "")
    out["code"] = f"01{gtin}21{serial}" if out["valid"] else clean
    return out


def canonical_code(raw: Optional[str]) -> Tuple[str, dict]:
    """(kuzatuv kaliti, tahlil natijasi). Kassadagi to'liq kod ham, kirimdagi qisqa kod ham bir xil kalit beradi."""
    parsed = parse_gs1(raw)
    return parsed["code"], parsed


# ─── Mahsulot / partiya moslashuvi ───────────────────────────────────────────

def _digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "").lstrip("0")


def _product_barcodes(db: Session, product: Product) -> List[str]:
    codes = [product.barcode]
    extra = getattr(product, "extra_barcodes", None)
    if extra:
        try:
            parsed = json.loads(extra)
            codes.extend(parsed if isinstance(parsed, list) else [])
        except (TypeError, ValueError):
            codes.extend(x.strip() for x in str(extra).split(","))
    codes.extend(
        b for (b,) in db.query(ProductVariant.barcode).filter(ProductVariant.product_id == product.id).all()
    )
    return [d for d in (_digits(c) for c in codes) if d]


def gtin_matches_product(db: Session, gtin: Optional[str], product: Product) -> bool:
    if not gtin:
        return True   # GTIN yo'q kod uchun alohida ogohlantirish beriladi
    g = _digits(gtin)
    return g in _product_barcodes(db, product)


def _pick_batch(batches: List[Batch], parsed: dict) -> Optional[Batch]:
    lot = (parsed.get("lot") or "").strip().lower()
    if lot:
        for b in batches:
            if (b.lot_number or "").strip().lower() == lot:
                return b
    return batches[0] if len(batches) == 1 else None


def _batch_expiry(b: Batch) -> Optional[date]:
    e = b.expiry_date
    return e.date() if hasattr(e, "date") else e


# ─── Kirim: kodlarni qabul qilish ────────────────────────────────────────────

def register_receipt_codes(
    db: Session, *, po: PurchaseOrder, product: Product, codes: Iterable[str], batches: List[Batch],
    label: str, warnings: List[str], expected_qty=None, warehouse_id: Optional[int] = None,
) -> Tuple[int, int]:
    """Qabul qilingan qator uchun kodlarni `in_stock` holatida yozadi. (yangi, avvaldan bor) qaytaradi.

    Qat'iy xato (400): kod bo'sh, so'rovda takror, boshqa mahsulot/xarid/holatda allaqachon ro'yxatda.
    Ogohlantirish (qabulni to'xtatmaydi): GTIN mahsulot shtrix-kodiga mos emas, seriya/muddat partiyaga mos emas,
    kodlar soni miqdorga teng emas. Qayta yuborilgan o'sha kod (shu xarid, shu mahsulot, in_stock) jim o'tkaziladi."""
    seen = set()
    new_rows: List[MarkingCode] = []   # hammasi tekshirilgach bir yo'la yoziladi (xatoda yarim yozilmaydi)
    already = 0
    bad_gtin = bad_lot = bad_exp = 0
    expiries = {_batch_expiry(b) for b in batches if b.expiry_date}
    lots = {(b.lot_number or "").strip().lower() for b in batches if b.lot_number}
    for raw in codes:
        if not (raw or "").strip():
            continue
        canon, parsed = canonical_code(raw)
        if not canon:
            raise HTTPException(status_code=400, detail=f"{label}: bo'sh markirovka kodi")
        if len(canon) > 300:
            raise HTTPException(status_code=400, detail=f"{label}: markirovka kodi juda uzun")
        if canon in seen:
            raise HTTPException(status_code=400, detail=f"{label}: kod takrorlangan — {canon}")
        seen.add(canon)
        existing = (
            db.query(MarkingCode)
            .filter(MarkingCode.company_id == po.company_id, MarkingCode.code == canon)
            .with_for_update().first()
        )
        if existing is not None:
            if existing.product_id == product.id and existing.status == "in_stock" and existing.received_po_id == po.id:
                already += 1
                continue
            raise HTTPException(
                status_code=400,
                detail=f"{label}: kod allaqachon ro'yxatda ({STATUS_LABELS.get(existing.status, existing.status)}) — {canon}",
            )
        if parsed["valid"] and not gtin_matches_product(db, parsed["gtin"], product):
            bad_gtin += 1
        elif not parsed["valid"]:
            bad_gtin += 1
        if parsed["lot"] and lots and parsed["lot"].strip().lower() not in lots:
            bad_lot += 1
        if parsed["expiry_date"] and expiries and date.fromisoformat(parsed["expiry_date"]) not in expiries:
            bad_exp += 1
        batch = _pick_batch(batches, parsed)
        new_rows.append(MarkingCode(
            company_id=po.company_id, code=canon, gtin=parsed["gtin"],
            serial=(parsed["serial"] or None) and parsed["serial"][:100],
            lot_number=(parsed["lot"] or None) and parsed["lot"][:100],
            expiry_date=date.fromisoformat(parsed["expiry_date"]) if parsed["expiry_date"] else None,
            product_id=product.id, batch_id=batch.id if batch is not None else None,
            warehouse_id=warehouse_id if warehouse_id is not None else po.warehouse_id,
            status="in_stock", received_po_id=po.id,
        ))
    if bad_gtin:
        warnings.append(f"{label}: {bad_gtin} ta kodning GTIN'i mahsulot shtrix-kodiga mos kelmaydi yoki kod GS1 formatida emas")
    if bad_lot:
        warnings.append(f"{label}: {bad_lot} ta kodning seriyasi (10) qabul qilingan partiyaga mos kelmaydi")
    if bad_exp:
        warnings.append(f"{label}: {bad_exp} ta kodning muddati (17) qabul qilingan partiya muddatiga mos kelmaydi")
    new_count = len(new_rows)
    db.add_all(new_rows)
    total = new_count + already
    if expected_qty is not None and total and abs(float(expected_qty) - total) > 1e-9:
        warnings.append(f"{label}: kodlar soni ({total}) qabul miqdoriga ({float(expected_qty):g}) teng emas")
    db.flush()
    return new_count, already


# ─── Sotuv: kodlarni tekshirish va "sold" qilish ─────────────────────────────

def plan_sale_marking(db: Session, company_id: int, lines: List[Tuple[int, Product, Optional[Product], List[str]]],
                      warnings: Optional[list] = None) -> Dict[int, List[MarkingCode]]:
    """Dorixona rejimida sotuvdan OLDIN (yozishdan oldin): shu korxonada `in_stock` va shu mahsulotniki bo'lgan kodlar
    `sold` qilinadi (kuzatiladi). lines: [(qator indeksi, mahsulot, manba mahsulot (konversiya) yoki None, kodlar)].
    Faqat `requires_marking` mahsulotlar. P.13: sotuv rad etilmaydi — kirimda qabul qilinmagan, takrorlangan, avval
    sotilgan, yaroqsiz holatdagi yoki boshqa mahsulot kodi chekda qoladi, kuzatilmaydi, `warnings` ga yoziladi."""
    plan: Dict[int, List[MarkingCode]] = {}
    seen = set()

    def _warn(code: str, product, text: str) -> None:
        if warnings is not None:
            warnings.append({"code": code, "product_id": product.id, "message": f"'{product.name}': {text}"})

    for idx, product, source, codes in lines:
        if not getattr(product, "requires_marking", False):
            continue
        allowed = {product.id} | ({source.id} if source is not None else set())
        rows = []
        for raw in codes:
            if not (raw or "").strip():
                continue
            canon, _parsed = canonical_code(raw)
            if canon in seen:
                _warn("marking_duplicate", product, f"kod chekda takrorlangan, kuzatuvsiz sotildi — {canon}")
                continue
            seen.add(canon)
            row = (
                db.query(MarkingCode)
                .filter(MarkingCode.company_id == company_id, MarkingCode.code == canon)
                .with_for_update().first()
            )
            if row is None:
                _warn("marking_not_received", product, "markirovka kodi kirimda qabul qilinmagan, kuzatuvsiz sotildi")
                continue
            if row.status != "in_stock" or row.product_id not in allowed:
                why = ("kod avval sotilgan" if row.status == "sold"
                       else f"kod holati: {STATUS_LABELS.get(row.status, row.status)}" if row.status != "in_stock"
                       else "kod boshqa mahsulotga tegishli")
                _warn("marking_not_tracked", product, f"{why}, kuzatuvsiz sotildi — {canon}")
                continue
            rows.append(row)
        if rows:
            plan[idx] = rows
    return plan


def apply_sale_marking(plan: Dict[int, List[MarkingCode]], sale_item_ids: Dict[int, int]) -> None:
    """Sotuv qatorlari saqlangach (id bor) kodlarni `sold` qiladi."""
    for idx, rows in plan.items():
        for row in rows:
            row.status = "sold"
            row.sale_item_id = sale_item_ids.get(idx)


# ─── Qaytarish: "sold" -> "returned" -> "in_stock" ───────────────────────────

def plan_return_marking(
    db: Session, company_id: int, *, product: Product, source: Optional[Product], original_item,
    codes: Optional[List[str]], qty, used_ids: set,
) -> List[MarkingCode]:
    """Qaytarishda qaysi kodlar omborga qaytishini aniqlaydi (yozmaydi).
    Kassir kod yuborgan bo'lsa — o'sha kodlar (sotilgan, shu korxonaniki, asl qatorga tegishli); yubormagan bo'lsa va
    asl sotuv qatori berilgan bo'lsa — shu qatorning hali qaytarilmagan `sold` kodlaridan miqdorcha."""
    if not getattr(product, "requires_marking", False):
        return []
    allowed = {product.id} | ({source.id} if source is not None else set())
    limit = int(qty)
    rows: List[MarkingCode] = []
    given = [c for c in (codes or []) if (c or "").strip()]
    if given:
        if len(given) > limit:
            raise HTTPException(status_code=400, detail=f"'{product.name}': kodlar soni qaytarilayotgan miqdordan ko'p")
        for raw in given:
            canon, _p = canonical_code(raw)
            row = (
                db.query(MarkingCode)
                .filter(MarkingCode.company_id == company_id, MarkingCode.code == canon)
                .with_for_update().first()
            )
            if row is None or row.product_id not in allowed:
                raise HTTPException(status_code=400, detail=f"'{product.name}': markirovka kodi topilmadi — {canon}")
            if row.status != "sold":
                raise HTTPException(
                    status_code=400,
                    detail=f"'{product.name}': kod sotilmagan, qaytarib bo'lmaydi ({STATUS_LABELS.get(row.status, row.status)}) — {canon}",
                )
            if original_item is not None and row.sale_item_id != original_item.id:
                raise HTTPException(status_code=400, detail=f"'{product.name}': kod asl sotuv qatoriga tegishli emas — {canon}")
            if row.id in used_ids:
                raise HTTPException(status_code=400, detail=f"'{product.name}': kod takrorlangan — {canon}")
            used_ids.add(row.id)
            rows.append(row)
    elif original_item is not None and limit > 0:
        q = (
            db.query(MarkingCode)
            .filter(MarkingCode.company_id == company_id, MarkingCode.sale_item_id == original_item.id,
                    MarkingCode.status == "sold")
            .order_by(MarkingCode.id.asc()).with_for_update()
        )
        for row in q.all():
            if row.id in used_ids:
                continue
            used_ids.add(row.id)
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def apply_return_marking(rows: List[MarkingCode], warehouse_id: Optional[int]) -> None:
    """Qaytgan kodlar yana omborda: sold -> returned -> in_stock (qaytgan omborga; oraliq holat bir amal ichida)."""
    for row in rows:
        row.status = "in_stock"
        row.sale_item_id = None
        if warehouse_id is not None:
            row.warehouse_id = warehouse_id


# ─── API ─────────────────────────────────────────────────────────────────────

class ParseIn(BaseModel):
    code: str = Field(..., max_length=500)


class ReceiveItemIn(BaseModel):
    po_item_id: int
    marking_codes: List[str] = Field(default_factory=list, max_length=MAX_CODES_PER_REQUEST)


class ReceiveIn(BaseModel):
    po_id: int
    items: List[ReceiveItemIn]


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


@router.post("/parse")
def parse_code(data: ParseIn, current_user: User = Depends(get_current_user)):
    """Skanerlangan kodni tahlil qiladi: GTIN, seriya, muddat (17), partiya (10). Bazaga yozmaydi."""
    return parse_gs1(data.code)


@router.post("/receive")
def receive_codes(
    data: ReceiveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Qabul qilingan xarid qatorlariga markirovka kodlarini biriktiradi (`in_stock`). Qayta yuborish zararsiz."""
    from app.services.purchase_order_service import _get_po
    cid = _company_id(current_user)
    po = _get_po(db, data.po_id, current_user)
    if po.company_id != cid:
        raise HTTPException(status_code=404, detail="Xarid topilmadi")
    items = {i.id: i for i in po.items}
    warnings: List[str] = []
    registered = already = 0
    for n, row in enumerate(data.items, 1):
        item = items.get(row.po_item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"PO item ID={row.po_item_id} topilmadi")
        product = item.product or db.get(Product, item.product_id)
        label = f"{n}-qator '{product.name}'"
        if not product.requires_marking:
            raise HTTPException(status_code=400, detail=f"{label}: bu mahsulot markirovka talab qilmaydi")
        if not row.marking_codes:
            continue
        if float(item.qty_received or 0) <= 0:
            raise HTTPException(status_code=400, detail=f"{label}: avval tovarni qabul qiling")
        batches = (
            db.query(Batch)
            .filter(Batch.po_id == po.id, Batch.product_id == item.product_id, Batch.variant_id == item.variant_id)
            .order_by(Batch.id.asc()).all()
        )
        new, old = register_receipt_codes(
            db, po=po, product=product, codes=row.marking_codes, batches=batches, label=label,
            warnings=warnings, expected_qty=item.qty_received,
        )
        registered += new
        already += old
    db.commit()
    return {"registered": registered, "already": already, "warnings": warnings}


@router.get("")
def list_codes(
    product_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, pattern="^(in_stock|sold|returned|written_off)$"),
    code: Optional[str] = Query(None, max_length=300),
    po_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=MAX_ROWS),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
):
    cid = _company_id(current_user)
    q = db.query(MarkingCode).filter(MarkingCode.company_id == cid)
    if product_id:
        q = q.filter(MarkingCode.product_id == product_id)
    if status:
        q = q.filter(MarkingCode.status == status)
    if po_id:
        q = q.filter(MarkingCode.received_po_id == po_id)
    if code and code.strip():
        canon, _p = canonical_code(code)
        q = q.filter(MarkingCode.code == canon)
    rows = q.order_by(MarkingCode.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "code": r.code, "gtin": r.gtin, "serial": r.serial, "lot_number": r.lot_number,
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
            "product_id": r.product_id, "batch_id": r.batch_id, "warehouse_id": r.warehouse_id,
            "status": r.status, "sale_item_id": r.sale_item_id, "received_po_id": r.received_po_id,
        }
        for r in rows
    ]
