"""AI tahlil va Copilot uchun filial doirasi (T2.9).

`resolve_ai_scope(db, user, requested_branch_id)` — foydalanuvchi qaysi filial(lar) ma'lumotini
ko'ra olishini aniqlaydi (T1.1 `build_branch_context` qoidalari bo'yicha) va `AIScope` qaytaradi.
`None` — "butun korxona" (filtr yo'q).

Qoidalar:
  - filialga bog'langan foydalanuvchi: faqat o'z filiali (yoki o'z filiallari); boshqa filial
    so'ralsa 403, begona korxona filiali — 404;
  - cheklanmagan foydalanuvchi (admin/director/filialsiz manager): so'ralgan filial korxonaniki
    bo'lishi shart (404), aks holda butun korxona.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.branch_context import BRANCH_FORBIDDEN, BRANCH_NOT_FOUND, build_branch_context
from app.models.branch import Branch
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.warehouse import Warehouse

WHOLE_COMPANY_LABEL = "Butun korxona"
DEFAULT_LOW_STOCK = 10


@dataclass(frozen=True)
class AIScope:
    """AI javoblari qaysi doirada hisoblanishi.

    `branch_id`/`branch_name` — bitta filial (bir nechta ruxsat etilgan filial bo'lsa None);
    `warehouse_ids` — doiradagi omborlar; `label` — javobda ko'rsatiladigan nom;
    `branch_ids` — doiradagi filiallar; `restricted` — foydalanuvchi filialga bog'langan.
    """
    branch_id: Optional[int]
    branch_name: Optional[str]
    warehouse_ids: list
    label: str
    company_id: Optional[int] = None
    branch_ids: tuple = ()
    restricted: bool = False

    def sale_filter(self):
        """`Sale` uchun SQL sharti: T1.9 filial snapshot'i; snapshot'i yo'q eski sotuvlar ombor filiali bo'yicha."""
        return or_(
            Sale.branch_id.in_(list(self.branch_ids)),
            and_(Sale.branch_id.is_(None), Sale.warehouse_id.in_(list(self.warehouse_ids))),
        )


def scope_label(scope: Optional[AIScope]) -> str:
    return scope.label if scope is not None else WHOLE_COMPANY_LABEL


def scope_info(scope: Optional[AIScope]) -> dict:
    """API javobi uchun: `{branch_id, label}`."""
    return {"branch_id": scope.branch_id if scope is not None else None, "label": scope_label(scope)}


def scope_sale_filter(scope: Optional[AIScope]):
    """Sotuv filtri; butun korxona uchun None."""
    return scope.sale_filter() if scope is not None else None


def item_scope_filter(scope: Optional[AIScope]):
    """`SaleItem` (Sale bilan birga so'ralganda) uchun sharti: qator ombori (bo'lmasa sotuv ombori) doirada,
    ombori umuman yo'q qator esa sotuv filiali bo'yicha. Butun korxona uchun None."""
    if scope is None:
        return None
    from app.models.sale import SaleItem
    wh = func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id)
    return or_(wh.in_(list(scope.warehouse_ids)), and_(wh.is_(None), scope.sale_filter()))


def scope_warehouse_ids(scope: Optional[AIScope]) -> Optional[list]:
    """Ombor id'lari; butun korxona uchun None (filtr yo'q)."""
    return list(scope.warehouse_ids) if scope is not None else None


def scope_cache_part(scope: Optional[AIScope]) -> str:
    """Kesh kaliti uchun: filial yoki 'all' (bir nechta filial — id'lar birlashmasi)."""
    if scope is None:
        return "all"
    if scope.branch_id is not None:
        return str(scope.branch_id)
    return "b" + "-".join(str(b) for b in sorted(scope.branch_ids)) if scope.branch_ids else "none"


def _branch_label(name: str) -> str:
    n = (name or "").strip()
    if n.lower().endswith(("filial", "filiali")):
        return n
    return f"{n} filiali"


def _warehouses_of(db: Session, company_id, branch_ids) -> list:
    if not branch_ids:
        return []
    rows = db.query(Warehouse.id).filter(
        Warehouse.company_id == company_id, Warehouse.branch_id.in_(list(branch_ids)),
    ).order_by(Warehouse.id).all()
    return [r[0] for r in rows]


def _make_scope(db: Session, company_id, branch_ids, restricted: bool) -> AIScope:
    ids = sorted(branch_ids)
    names = {}
    if ids:
        names = {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(
            Branch.id.in_(ids), Branch.company_id == company_id).all()}
    whs = _warehouses_of(db, company_id, ids)
    if len(ids) == 1:
        name = names.get(ids[0]) or ""
        return AIScope(ids[0], name, whs, _branch_label(name), company_id, tuple(ids), restricted)
    if not ids:
        return AIScope(None, None, whs, "Filial biriktirilmagan", company_id, (), restricted)
    label = "Filiallar: " + ", ".join(names.get(i, str(i)) for i in ids)
    return AIScope(None, None, whs, label, company_id, tuple(ids), restricted)


def resolve_ai_scope(db: Session, user, requested_branch_id: Optional[int] = None) -> Optional[AIScope]:
    """Foydalanuvchi uchun AI doirasi. `None` — butun korxona.

    Xatolar: 404 (filial korxonada yo'q), 403 (filialga bog'langan foydalanuvchi boshqa filialni so'radi).
    """
    company_id = getattr(user, "company_id", None)
    ctx = build_branch_context(db, user)
    allowed = ctx.allowed_branch_ids  # None — cheklanmagan

    if requested_branch_id:
        exists = db.query(Branch.id).filter(
            Branch.id == requested_branch_id, Branch.company_id == company_id,
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        if allowed is not None and requested_branch_id not in allowed:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        return _make_scope(db, company_id, [requested_branch_id], allowed is not None)

    if allowed is None:
        return None
    if ctx.branch_id is not None:
        return _make_scope(db, company_id, [ctx.branch_id], True)
    return _make_scope(db, company_id, list(allowed), True)


def resolve_branch_by_name(db: Session, company_id: int, name: str, allowed_ids=None):
    """LLM bergan filial nomi bo'yicha filialni topadi: `(Branch | None, xato_matni | None)`.

    Katta-kichik harf farqsiz; avval to'liq moslik, keyin qisman moslik. Topilmasa yoki noaniq bo'lsa
    xato matni (mavjud filiallar ro'yxati bilan) qaytariladi. `allowed_ids` berilsa faqat shular orasidan.
    """
    q = db.query(Branch).filter(Branch.company_id == company_id, Branch.is_active == True)  # noqa: E712
    if allowed_ids is not None:
        q = q.filter(Branch.id.in_(list(allowed_ids)))
    branches = q.order_by(Branch.id).all()
    wanted = (name or "").strip().casefold()
    names = ", ".join(b.name for b in branches) or "filial yo'q"
    if not wanted:
        return None, f"Filial nomi ko'rsatilmadi. Mavjud filiallar: {names}."

    def norm(b):
        return (b.name or "").strip().casefold()

    exact = [b for b in branches if norm(b) == wanted]
    if not exact:
        # "Yunusobod" ↔ "Yunusobod filiali"
        stripped = wanted.replace("filiali", "").replace("filial", "").strip()
        exact = [b for b in branches if norm(b).replace("filiali", "").replace("filial", "").strip() == stripped] \
            if stripped else []
    if len(exact) == 1:
        return exact[0], None
    found = exact or [b for b in branches if wanted in norm(b) or norm(b) in wanted]
    if len(found) == 1:
        return found[0], None
    if len(found) > 1:
        return None, ("Bir nechta filial mos keldi: " + ", ".join(b.name for b in found)
                      + ". Qaysi filial kerakligini aniqlashtiring.")
    return None, f"'{name}' nomli filial topilmadi. Mavjud filiallar: {names}. Qaysi filial kerak?"


def resolve_tool_scope(db: Session, user, kwargs: dict):
    """Copilot vositalari uchun: `(scope, izoh, xato_javobi)`.

    `branch` (nom) yoki ichki `branch_id` (chat'da tanlangan filial). Filialga bog'langan foydalanuvchi
    uchun so'ralgan boshqa filial e'tiborga olinmaydi (izoh qaytariladi). Noma'lum/noaniq nom — xato
    emas, aniqlashtiruvchi javob (`xato_javobi`)."""
    company_id = getattr(user, "company_id", None)
    branch_name = (kwargs.get("branch") or "").strip() if isinstance(kwargs.get("branch"), str) else ""
    branch_id = kwargs.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id not in (None, "") else None
    except (TypeError, ValueError):
        branch_id = None

    if branch_name:
        allowed = build_branch_context(db, user).allowed_branch_ids
        branch, err = resolve_branch_by_name(db, company_id, branch_name)
        if err:
            return None, None, {"reply": "❓ " + err}
        if allowed is not None and branch.id not in allowed:
            return _own_scope_with_note(db, user) + (None,)
        branch_id = branch.id

    try:
        return resolve_ai_scope(db, user, branch_id), None, None
    except HTTPException as e:
        if e.status_code == 403:
            return _own_scope_with_note(db, user) + (None,)
        return None, None, {"reply": "❓ Filial topilmadi. Qaysi filial kerakligini aniqlashtiring."}


def _own_scope_with_note(db: Session, user):
    """Ruxsatsiz filial so'ralganda: foydalanuvchining o'z doirasi va izoh."""
    scope = resolve_ai_scope(db, user, None)
    return scope, f"So'ralgan filial ruxsatingizdan tashqarida, {scope_label(scope)} ma'lumotlari ko'rsatildi."


def scope_header(scope: Optional[AIScope], note: Optional[str] = None) -> str:
    """Vosita javobi boshiga qo'yiladigan doira qatori."""
    line = f"📍 {scope_label(scope)}\n"
    if note:
        line += f"ℹ️ {note}\n"
    return line


def company_branch_names(db: Session, company_id: int) -> list:
    return [r[0] for r in db.query(Branch.name).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).all()]


def low_stock_query(db: Session, company_id: int, scope: Optional[AIScope], threshold: Optional[int] = None):
    """Zaxirasi kam mahsulotlar: `(Product.id, Product.name, qty)`.

    O'chirilgan mahsulotlar kirmaydi; qoldiq doiradagi omborlar bo'yicha yig'iladi. `threshold` berilmasa
    mahsulotning `min_stock` qiymati (0 bo'lsa 10) ishlatiladi."""
    qty = func.sum(StockLevel.quantity)
    q = (
        db.query(Product.id, Product.name, qty.label("qty"))
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(Product.company_id == company_id, Product.is_deleted.isnot(True))
    )
    if scope is not None:
        q = q.filter(StockLevel.warehouse_id.in_(list(scope.warehouse_ids)))
    limit = threshold if threshold is not None else func.coalesce(func.nullif(Product.min_stock, 0), DEFAULT_LOW_STOCK)
    return q.group_by(Product.id, Product.name, Product.min_stock).having(qty < limit)


def low_stock_count(db: Session, company_id: int, scope: Optional[AIScope], threshold: Optional[int] = None) -> int:
    """Zaxirasi kam MAHSULOTLAR soni (StockLevel qatorlari emas) — `get_low_stock` vositasi ro'yxati bilan bir xil
    qoida (`low_stock_query`: `min_stock=0` bo'lsa chegara `DEFAULT_LOW_STOCK`).

    T2.3: AI/Telegram HISOBOTLARIDAGI "kam qoldiq" soni — `stock_report.low_stock_count_for_scope` (yagona ta'rif:
    `min_stock > 0`, qoldiq <= min_stock); ai_service/ai_reports/ai_analytics shuni ishlatadi."""
    return low_stock_query(db, company_id, scope, threshold).count()
