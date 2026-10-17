from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.sale import Sale
from app.services.document_numbers import next_document_number
import logging
import os
import requests

_logger = logging.getLogger(__name__)


def generate_sale_number(db: Session, company_id: int, branch_id=None) -> str:
    """Sotuv raqami (T1.14): `S{YYYYMMDD}-{korxona}-{filial}-{NNNN}`, atomar hisoblagich bilan."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="S")


def generate_return_number(db: Session, company_id: int, branch_id=None) -> str:
    """Qaytarish raqami (T1.14). "R" bilan boshlanishi SHART: hisobotlar/smena
    (`Sale.number.like("R%")`, `startswith("R")`) qaytarishni shu bilan aniqlaydi."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="R")


def send_tg_sync(token, chat_id, text, filepath=None):
    try:
        if filepath and os.path.exists(filepath):
            with open(filepath, "rb") as doc:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                    files={"document": doc},
                    timeout=10
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5
            )
    except Exception as e:
        _logger.error("[TG] Telegram xabarnomasi yuborishda xato: %s", e)


def _branch_override(branch_price, price_type):
    """Filial narxi (T4.3): `wholesale` turi uchun `wholesale_price`, `sale` uchun `sale_price`;
    `cost` turi uchun filial narxi qo'llanmaydi. Mos ustun NULL bo'lsa — None (korxona narxi)."""
    if branch_price is None or price_type == "cost":
        return None
    val = branch_price.wholesale_price if price_type == "wholesale" else branch_price.sale_price
    return val if val is not None else None


def resolve_price(item_data, product, customer_price, customer=None, branch_price=None):
    """Narx prioriteti: frontend > individual narx > filial narxi > price_type > sale_price."""
    price_type = "sale"
    if customer:
        price_type = getattr(customer, "price_type", "sale") or "sale"

    if item_data.unit_price is not None:
        return item_data.unit_price
    if customer_price:
        return customer_price.price
    _bp = _branch_override(branch_price, price_type)
    if _bp is not None:
        return _bp
    if price_type == "wholesale":
        return product.wholesale_price or product.sale_price
    if price_type == "cost":
        return product.cost_price or product.sale_price
    return product.sale_price


_PRICE_FIELDS = (("sale_price", "sale_currency"), ("wholesale_price", "wholesale_currency"),
                 ("cost_price", "cost_currency"))


def _list_price(product, customer_price, customer, branch_price=None):
    """Ro'yxat narxi: mijozning individual narxi > filial narxi (T4.3) > `customer.price_type` bo'yicha mahsulot narxi."""
    if customer_price:
        return Decimal(str(customer_price.price)), "customer_price"
    price_type = (getattr(customer, "price_type", None) or "sale") if customer else "sale"
    _bp = _branch_override(branch_price, price_type)
    if _bp is not None:
        return Decimal(str(_bp)), "branch_price"
    if price_type == "wholesale":
        return product.wholesale_price or product.sale_price, "price_type"
    if price_type == "cost":
        return product.cost_price or product.sale_price, "price_type"
    return product.sale_price, "sale_price"


def _is_standard_list_price(item_data, product, unit_price) -> bool:
    """`unit_price` mahsulotning standart ro'yxat narxlaridan biriga teng (va valyuta mos) mi."""
    item_cur = (getattr(item_data, "currency_code", None) or "UZS").upper()
    for price_f, cur_f in _PRICE_FIELDS:
        val = getattr(product, price_f, None)
        if val is None:
            continue
        prod_cur = (getattr(product, cur_f, None) or "UZS").upper()
        if prod_cur == item_cur and Decimal(str(val)) == Decimal(str(unit_price)):
            return True
    return False


def price_is_override(item_data, product, customer_price, customer=None, branch_price=None):
    """T4.6: klient narxi ro'yxat narxidan (individual narx > filial narxi > price_type > sale_price) PAST bo'lsa
    ro'yxat narxini qaytaradi, aks holda `None` (override emas). Narx yuborilmagan yoki `price_manual is False`
    bo'lsa server ro'yxat narxini qo'llaydi — override yo'q. Valyutalar mos kelmasa solishtirib bo'lmaydi -> None."""
    client_price = getattr(item_data, "unit_price", None)
    if client_price is None or getattr(item_data, "price_manual", None) is False:
        return None
    list_price, _src = _list_price(product, customer_price, customer, branch_price)
    if list_price is None:
        return None
    item_cur = (getattr(item_data, "currency_code", None) or "UZS").upper()
    prod_cur = (getattr(product, "sale_currency", None) or "UZS").upper()
    if item_cur != prod_cur:
        return None
    if Decimal(str(client_price)) < Decimal(str(list_price)):
        return Decimal(str(list_price))
    return None


def _can_change_price(user) -> bool:
    """`permissions["sales"]["change_price"] is False` bo'lsa aniq taqiqlangan; aks holda ruxsat."""
    perms = getattr(user, "permissions", None) if user is not None else None
    if not isinstance(perms, dict):
        return True
    sales = perms.get("sales")
    if isinstance(sales, dict) and sales.get("change_price") is False:
        return False
    return True


PRICE_CHANGE_FORBIDDEN = "Narxni o'zgartirishga ruxsat yo'q"


def resolve_item_pricing(item_data, product, customer_price, customer=None, current_user=None, branch_price=None):
    """Sotuv qatori narxi va chegirmasi (T3.19) -> `(unit_price, discount, source)`.

    Ro'yxat narxi: `customer_price` > `customer.price_type` (wholesale/cost) > `sale_price`.
      - `unit_price` yo'q yoki `price_manual is False` -> ro'yxat narxi.
      - `price_manual is True` -> klient narxi (permissions.sales.change_price == False bo'lsa 403).
      - `price_manual is None` (eski klientlar): individual narx bor va klient narxi mahsulotning standart
        ro'yxat narxlaridan biriga teng (valyuta mos) bo'lsa — klient shunchaki ro'yxat narxini yuborgan,
        individual narx qo'llanadi; aks holda narx qo'lda deb olinadi.
    Chegirma: qatorda chegirma 0 bo'lsa va mijozda `discount_percent > 0` bo'lsa avto-chegirma;
    qatorda chegirma bor (aksiya/qo'lda) bo'lsa jamlanmaydi.
    """
    list_price, source = _list_price(product, customer_price, customer, branch_price)
    client_price = getattr(item_data, "unit_price", None)
    manual = getattr(item_data, "price_manual", None)

    if client_price is None or manual is False:
        unit_price = list_price
    elif manual is True:
        if not _can_change_price(current_user):
            raise HTTPException(status_code=403, detail=PRICE_CHANGE_FORBIDDEN)
        unit_price, source = client_price, "manual"
    elif (customer_price or source == "branch_price") and _is_standard_list_price(item_data, product, client_price):
        # eski klient ro'yxat narxini (korxona narxi) yuborgan — individual/filial narxi qo'llanadi
        unit_price = list_price
    else:
        if (list_price is None or Decimal(str(client_price)) != Decimal(str(list_price)))                 and not _can_change_price(current_user):
            raise HTTPException(status_code=403, detail=PRICE_CHANGE_FORBIDDEN)
        unit_price, source = client_price, "manual"

    discount = Decimal(str(getattr(item_data, "discount", 0) or 0))
    pct = Decimal(str(getattr(customer, "discount_percent", 0) or 0)) if customer else Decimal("0")
    if discount == 0 and pct > 0:
        qty = Decimal(str(getattr(item_data, "quantity", 0) or 0))
        discount = (Decimal(str(unit_price)) * qty * pct / Decimal("100")).quantize(Decimal("0.01"))
    return unit_price, discount, source


def _warehouse_branch_id(db, company_id, warehouse_id, only_active=False):
    """Ombor filiali — ombor ham, filial ham faqat `company_id` korxonasidan (T1.9). Topilmasa None.
    `only_active=True` (T1.12) — nofaol (yopilgan) filial o'tkazib yuboriladi."""
    if not warehouse_id or company_id is None:
        return None
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    q = db.query(Branch.id).join(Warehouse, Warehouse.branch_id == Branch.id).filter(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == company_id,
        Branch.company_id == company_id,
    )
    if only_active:
        q = q.filter(Branch.is_active == True)  # noqa: E712
    row = q.first()
    return row[0] if row else None


USER_BRANCH_CLOSED = "Filialingiz yopilgan. Administrator bilan bog'laning."
WAREHOUSE_BRANCH_CLOSED = "Ombor filiali yopilgan"


def assert_user_branch_active(db, user):
    """T1.12: xodimning joriy filiali yopilgan (nofaol) bo'lsa HTTP 409. Filiali yo'q xodim — o'tadi.
    Joriy filial `effective_branch_id` (X-Branch-Id / joriy korxonadagi biriktirilgan filial)."""
    from app.core.branch_context import effective_branch_id
    from app.models.branch import Branch

    eff = effective_branch_id(db, user)
    if eff is None:
        return None
    active = db.query(Branch.is_active).filter(Branch.id == eff).scalar()
    if active is False:
        raise HTTPException(status_code=409, detail=USER_BRANCH_CLOSED)
    return eff


def assert_warehouses_branch_active(db, warehouse_ids):
    """T1.12: ombor(lar) filiali yopilgan bo'lsa HTTP 400 "Ombor filiali yopilgan"
    (bitta so'rov; filialsiz omborlar tekshirilmaydi)."""
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    ids = {int(w) for w in (warehouse_ids or ()) if w}
    if not ids:
        return
    closed = db.query(Warehouse.id).join(Branch, Branch.id == Warehouse.branch_id).filter(
        Warehouse.id.in_(ids), Branch.is_active == False,  # noqa: E712
    ).first()
    if closed:
        raise HTTPException(status_code=400, detail=WAREHOUSE_BRANCH_CLOSED)


def resolve_branch_id(db, current_user, warehouse_id=None, prefer_warehouse=False):
    """Operatsiya (sotuv/tranzaksiya) filialini topish (T1.9; T2.2: yagona `resolve_money_branch_id` ga yupqa o'ram).

    Tartib: ombor filiali (ombor ham, filial ham faqat o'z korxonasidan, faol) -> joriy filial (T1.2
    `effective_branch_id`; yopilgan bo'lsa 409, T1.12) -> korxonaning asosiy/birinchi faol filiali (T1.4).
    `prefer_warehouse` eski chaqiruvlar uchun qoldirilgan (endi har doim ombor birinchi).
    Filial topilmasa avvalgidek `None` (chaqiruvchilar shunga tayanadi).
    """
    from fastapi import HTTPException
    from app.services.branch_attribution import NO_ACTIVE_BRANCH, NO_BRANCH, resolve_money_branch_id

    try:
        return resolve_money_branch_id(db, current_user, warehouse_id=warehouse_id, check_user_branch_active=True)
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail in (NO_BRANCH, NO_ACTIVE_BRANCH):
            return None
        raise


def branch_of_sale(db, sale):
    """Sotuv filiali: `sale.branch_id` snapshot'i, bo'lmasa (eski qator) ombor filiali."""
    if sale is None:
        return None
    if getattr(sale, "branch_id", None):
        return sale.branch_id
    return _warehouse_branch_id(db, getattr(sale, "company_id", None), getattr(sale, "warehouse_id", None))


SALE_MIXED_BRANCH = "Bir chekdagi barcha qatorlar bitta filial omboridan bo'lishi kerak"
SALE_WAREHOUSE_BRANCH_CHANGE = "Sotuvni boshqa filial omboriga faqat admin/direktor o'tkaza oladi"


def assert_sale_items_one_branch(db, user, warehouse_id, item_warehouse_ids, *, company_id=None):
    """`items[].warehouse_id` sarlavha omboriga bir filialdan bo'lishi shart (T1.9), aks holda 400.

    Qator ombori sarlavhadan farq qilsa-yu, filiali bir xil bo'lsa — mumkin. Filialsiz (NULL) omborlar
    faqat sarlavha ombori ham filialsiz bo'lsa mos keladi.
    """
    from app.models.warehouse import Warehouse

    extra = {int(w) for w in (item_warehouse_ids or ()) if w and int(w) != int(warehouse_id or 0)}
    if not extra:
        return
    cid = company_id if company_id is not None else user.company_id
    header_branch = db.query(Warehouse.branch_id).filter(Warehouse.id == warehouse_id).scalar() if warehouse_id else None
    rows = db.query(Warehouse.id, Warehouse.branch_id).filter(
        Warehouse.id.in_(extra), Warehouse.company_id == cid,
    ).all()
    if any(b != header_branch for _, b in rows):
        raise HTTPException(status_code=400, detail=SALE_MIXED_BRANCH)


def resolve_txn_branch(db, user, *, sale=None, warehouse_id=None, wallet=None):
    """Tranzaksiya filiali — operatsiya joyidan, amalni bajargan xodimdan emas (T1.9).

    Tartib: `sale.branch_id` → ombor filiali (`warehouse_id` yoki `sale.warehouse_id`) →
    `wallet.branch_id` → `user` ning joriy filiali → korxonaning birinchi faol filiali (`ORDER BY id`).
    Barcha filiallar `user.company_id` korxonasiniki bo'lishi shart. Topilmasa `None`.
    """
    from app.core.branch_context import effective_branch_id
    from app.models.branch import Branch

    company_id = getattr(user, "company_id", None)

    def _own(branch_id):
        if not branch_id:
            return None
        row = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
        return row[0] if row else None

    found = _own(getattr(sale, "branch_id", None)) if sale is not None else None
    if found:
        return found
    wh_id = warehouse_id or (getattr(sale, "warehouse_id", None) if sale is not None else None)
    found = _warehouse_branch_id(db, company_id, wh_id)
    if found:
        return found
    if wallet is not None:
        found = _own(getattr(wallet, "branch_id", None))
        if found:
            return found
    eff = effective_branch_id(db, user)
    if eff is not None:
        return eff
    if company_id is None:
        return None
    row = db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id.asc()).first()
    return row[0] if row else None


def validate_sale_warehouses(db: Session, user, warehouse_ids, *, company_id=None):
    """Sotuvdagi ombor ID lari (sarlavha va qatorlar) ni bitta so'rovda tekshiradi (T0.13).

    Qoidalar (`tenant_guards.get_company_warehouse(enforce_branch=True)` bilan bir xil):
      - ombor `company_id` (berilmasa `user.company_id`) korxonasiniki va faol bo'lishi shart,
        aks holda 404 "Ombor topilmadi";
      - rol admin/director/super_admin bo'lmasa va `user.branch_id` bor bo'lsa, ombor
        shu filialniki bo'lishi shart, aks holda 403. Filialsiz foydalanuvchida faqat
        korxona va faollik tekshiriladi.
    Qaytaradi: {warehouse_id: Warehouse}.
    """
    from app.models.warehouse import Warehouse
    from app.services.tenant_guards import (
        BRANCH_FREE_ROLES, WAREHOUSE_NOT_FOUND, WAREHOUSE_OTHER_BRANCH,
    )

    ids = {int(i) for i in (warehouse_ids or []) if i}
    if not ids:
        return {}
    cid = company_id if company_id is not None else user.company_id
    found = {
        w.id: w for w in db.query(Warehouse).filter(
            Warehouse.id.in_(ids),
            Warehouse.company_id == cid,
        ).all()
    }
    # T1.2: ruxsat etilgan filiallar joriy korxona bo'yicha (X-Branch-Id / uc.branch_id ∪ user_branches,
    # legacy users.branch_id faqat shu korxonaniki bo'lsa) — begona korxona filiali hisobga olinmaydi.
    allowed_ids = frozenset()
    if user.role not in BRANCH_FREE_ROLES:
        from app.core.branch_context import effective_branch_ids
        allowed_ids = effective_branch_ids(db, user)
    for wid in sorted(ids):
        wh = found.get(wid)
        if not wh or wh.is_active is False:
            raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
        if allowed_ids and wh.branch_id not in allowed_ids:
            raise HTTPException(status_code=403, detail=WAREHOUSE_OTHER_BRANCH)
    return found


def validate_sale_warehouse(db: Session, user, warehouse_id, *, company_id=None):
    """Bitta omborni tekshiradi (`validate_sale_warehouses` ning yakka varianti); Warehouse qaytaradi."""
    from app.services.tenant_guards import WAREHOUSE_NOT_FOUND

    if not warehouse_id:
        raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
    return validate_sale_warehouses(db, user, [warehouse_id], company_id=company_id)[int(warehouse_id)]


# Filial bo'yicha cheklanmaydigan rollar (korxona filtri baribir qoladi)
_SALE_ALL_BRANCH_ROLES = ("admin", "director", "super_admin")


def apply_sale_branch_filter(q, db: Session, user):
    """Sotuv so'roviga filial ruxsatini qo'shadi (`list_sales` bilan bir xil qoida).

    - admin/director/super_admin: cheklovsiz (korxona filtri chaqiruvchida qoladi).
    - boshqa rollar, filial(lar)i bor (T1.2: joriy korxona bo'yicha uc.branch_id ∪ user_branches,
      legacy users.branch_id): `Sale.branch_id` shu filiallarniki (T1.9); branch_id yo'q eski
      sotuvlarda — ombori shu filiallarniki yoki (ombori ham yo'q) faqat o'zi yaratgan bo'lsa.
    - boshqa rollar, filiali yo'q: faqat o'zi yaratgan sotuvlar.
    """
    from app.core.branch_context import effective_branch_ids
    from app.models.warehouse import Warehouse

    role = getattr(user.role, "value", user.role)
    if role in _SALE_ALL_BRANCH_ROLES:
        return q
    allowed_ids = effective_branch_ids(db, user)
    if not allowed_ids:
        return q.filter(Sale.cashier_id == user.id)
    branch_wh_ids = db.query(Warehouse.id).filter(
        Warehouse.branch_id.in_(list(allowed_ids)),
        Warehouse.company_id == user.company_id,
    )
    # T1.9: filial `Sale.branch_id` snapshot'idan (ombori yo'q sotuv ham o'z filialida ko'rinadi);
    # branch_id hali to'ldirilmagan eski qatorlar uchun avvalgi qoida (ombor / o'zi yaratgan) qoladi.
    return q.filter(or_(
        Sale.branch_id.in_(list(allowed_ids)),
        and_(Sale.branch_id.is_(None), or_(
            Sale.warehouse_id.in_(branch_wh_ids.scalar_subquery()),
            and_(Sale.warehouse_id.is_(None), Sale.cashier_id == user.id),
        )),
    ))


def assert_sale_branch_access(db: Session, user, sale) -> None:
    """Sotuv foydalanuvchi filialiga tegishli bo'lmasa 404 (mavjudligini oshkor qilmaslik uchun)."""
    allowed = apply_sale_branch_filter(
        db.query(Sale.id).filter(Sale.id == sale.id), db, user
    ).first()
    if not allowed:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")


def resolve_cashier_wallet_id(db: Session, user):
    """Kassirning sotuv tushumi tushadigan kassasi (hamyon) ID si; topilmasa `None`.

    Tartib: `user_wallets` dan joriy korxonaning faol kassasi (`is_default DESC`, so'ng
    eng kichik id); bo'lmasa korxonaning birinchi ochiq va faol kassasi.
    `create_sale` va smena inkassatsiyasi (T0.28) bir xil qoidadan foydalanadi.
    """
    from sqlalchemy import text
    from app.models.moliya import Wallet

    wallet_id = None
    try:
        # SAVEPOINT — user_wallets jadvali bo'lmasa butun tranzaksiya bekor bo'lmasin
        with db.begin_nested():
            row = db.execute(
                text(
                    "SELECT uw.wallet_id FROM user_wallets uw JOIN wallets w ON w.id = uw.wallet_id "
                    "WHERE uw.user_id=:uid AND w.company_id=:cid AND w.is_active = true "
                    "ORDER BY uw.is_default DESC, uw.wallet_id ASC LIMIT 1"
                ),
                {"uid": user.id, "cid": user.company_id},
            ).fetchone()
            wallet_id = row[0] if row else None
    except Exception:
        wallet_id = None
    if not wallet_id:
        w = db.query(Wallet).filter(
            Wallet.company_id == user.company_id,
            Wallet.is_open == True,  # noqa: E712
            Wallet.is_active == True,  # noqa: E712
        ).order_by(Wallet.id.asc()).first()
        wallet_id = w.id if w else None
    return wallet_id


REFUND_NO_WALLET = "Qaytarish uchun ochiq kassa topilmadi"
# Boshqa kassani tanlay oladigan rollar (qolganlar faqat o'ziga biriktirilgan kassani)
_REFUND_ANY_WALLET_ROLES = ("admin", "director", "manager", "super_admin")


def resolve_refund_wallet(db: Session, user, requested_wallet_id=None, original_sale=None):
    """Qaytarishda pul chiqadigan kassani (Wallet, `with_for_update`) aniqlaydi (T0.31).

    Tartib (korxonadagi "birinchi ochiq kassa" fallback'i YO'Q):
      1. `requested_wallet_id` berilgan bo'lsa: shu korxonaning faol va ochiq kassasi
         (404 / 400 "Kassa yopiq"); admin/director/manager bo'lmasa `user_wallets` da
         biriktirilgan bo'lishi shart, aks holda 403;
      2. foydalanuvchining `user_wallets` dagi kassalari (default birinchi), ochiq va faol;
      3. asl sotuv kassasi (`KassaMovement`/`Transaction`, `reference_type="sale"`), ochiq bo'lsa;
      4. aks holda 400 "Qaytarish uchun ochiq kassa topilmadi".
    """
    from app.models.moliya import KassaMovement, Transaction, Wallet
    from app.models.user import UserWallet
    from app.services.tenant_guards import get_company_wallet

    company_id = user.company_id
    role = getattr(user.role, "value", user.role)

    if requested_wallet_id:
        wallet = get_company_wallet(db, company_id, requested_wallet_id)
        if role not in _REFUND_ANY_WALLET_ROLES:
            attached = db.query(UserWallet.wallet_id).filter(
                UserWallet.user_id == user.id, UserWallet.wallet_id == wallet.id,
            ).first()
            if not attached:
                raise HTTPException(status_code=403, detail="Bu kassa sizga biriktirilmagan")
        return wallet

    def _usable(wallet_id):
        if not wallet_id:
            return None
        return db.query(Wallet).filter(
            Wallet.id == wallet_id,
            Wallet.company_id == company_id,
            Wallet.is_active == True,  # noqa: E712
            Wallet.is_open == True,  # noqa: E712
        ).with_for_update().first()

    own_ids = [r[0] for r in db.query(UserWallet.wallet_id).filter(
        UserWallet.user_id == user.id,
    ).order_by(UserWallet.is_default.desc(), UserWallet.wallet_id.asc()).all()]
    for wid in own_ids:
        wallet = _usable(wid)
        if wallet is not None:
            return wallet

    if original_sale is not None:
        km_ids = [r[0] for r in db.query(KassaMovement.wallet_id).filter(
            KassaMovement.company_id == company_id,
            KassaMovement.reference_type == "sale",
            KassaMovement.reference_id == original_sale.id,
            KassaMovement.wallet_id.isnot(None),
        ).order_by(KassaMovement.id.asc()).all()]
        tx_ids = [r[0] for r in db.query(Transaction.wallet_id).filter(
            Transaction.company_id == company_id,
            Transaction.reference_type == "sale",
            Transaction.reference_id == original_sale.id,
            Transaction.wallet_id.isnot(None),
        ).order_by(Transaction.id.asc()).all()]
        for wid in km_ids + tx_ids:
            wallet = _usable(wid)
            if wallet is not None:
                return wallet

    raise HTTPException(status_code=400, detail=REFUND_NO_WALLET)


def refresh_original_sale_status(db: Session, original_sale, customer=None) -> None:
    """Asl sotuv statusini qaytarilgan MIQDOR asosida yangilaydi (T0.31).

    Hammasi qaytarilsa `refunded` (yetkazma bekor, `customer` berilsa ball/bonus qaytariladi),
    qisman bo'lsa `partial_refund`. `SaleItem.returned_quantity` allaqachon oshirilgan bo'lishi kerak.
    """
    from app.models.sale import SaleItem, SaleStatus

    all_items = db.query(SaleItem).filter(SaleItem.sale_id == original_sale.id).all()
    total_qty = sum(Decimal(str(si.quantity or 0)) for si in all_items)
    total_returned = sum(Decimal(str(si.returned_quantity or 0)) for si in all_items)
    if total_qty <= 0:
        return
    if total_returned >= total_qty:
        original_sale.status = SaleStatus.refunded  # type: ignore
        from app.services.sale_delivery_service import cancel_sale_delivery
        cancel_sale_delivery(db, original_sale.id, "Sotuv to'liq qaytarildi")

        # To'liq qaytarilganda berilgan/ishlatilgan ball va bonus ham qaytariladi —
        # aks holda mijoz tovarni qaytarib, ball/bonusni saqlab qolgan bo'lardi.
        if customer:
            earned = int(original_sale.loyalty_points_earned or 0)
            if earned > 0:
                customer.loyalty_points = max(0, (customer.loyalty_points or 0) - earned)

            used = int(original_sale.loyalty_points_used or 0)
            if used > 0:
                customer.loyalty_points = (customer.loyalty_points or 0) + used

            spent_bonus = Decimal(str(original_sale.paid_cashback or 0))
            if spent_bonus > 0:
                customer.bonus_balance = (customer.bonus_balance or Decimal("0")) + spent_bonus

            earned_bonus = Decimal(str(original_sale.cashback_earned or 0))
            if earned_bonus > 0:
                customer.bonus_balance = max(Decimal("0"), (customer.bonus_balance or Decimal("0")) - earned_bonus)
    elif total_returned > 0:
        original_sale.status = SaleStatus.partial_refund  # type: ignore
