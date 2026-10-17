"""T1.14 — Hujjat raqamlari: korxona/filial prefiksi va atomar hisoblagich.

Qamrov: parallel (20 oqim) takrorlanmaslik; korxona/filial/tur/kun izolyatsiyasi; 9999 dan keyin
10000; o'chirilgan hujjat raqami qayta ishlatilmaydi; rollbackda hisoblagich ham bekor;
qaytarish "R" prefiksi va is_return_doc; 00:30 Toshkent sanasi; eski format bilan to'qnashmaslik;
marketplace PO raqami; POST /sales dagi kutilmagan IntegrityError -> 409; ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_14.py -q -p no:cacheprovider
"""
import itertools
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.services.document_numbers as docnum
from app.models.document_counter import DocumentCounter
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem
from app.models.user import UserRole
from app.schemas.sale import SaleCreate
from app.services.document_numbers import next_document_number
from app.services.sale_create import create_sale
from app.utils.report_utils import is_return_doc

_seq = itertools.count(1)
D = date(2026, 10, 14)


def _num(db, c, b, t="S", d=D):
    return next_document_number(db, company_id=c.id, branch_id=b.id if b else None, doc_type=t, on_date=d)


def _seqno(number):
    return int(number.rsplit("-", 1)[1])


def tashkent_str():
    return docnum.tashkent_today().strftime("%Y%m%d")


# ── 1. Format, parallellik, izolyatsiya ──────────────────────────────────────

def test_format_and_sequence(db, mk):
    c, b, _, _ = mk.tenant()
    assert _num(db, c, b) == f"S20261014-{c.id}-{b.id}-0001"
    assert _num(db, c, b) == f"S20261014-{c.id}-{b.id}-0002"
    # filialsiz hujjat: branch_id = 0
    assert _num(db, c, None, "PO") == f"PO20261014-{c.id}-0-0001"


def test_counters_are_isolated(db, mk):
    ca, ba, _, _ = mk.tenant()
    cb, bb, _, _ = mk.tenant()
    ba2 = mk.branch(ca)
    assert _seqno(_num(db, ca, ba)) == 1
    assert _seqno(_num(db, ca, ba)) == 2
    # boshqa korxona, boshqa filial, boshqa tur, boshqa kun — har biri 1 dan
    assert _seqno(_num(db, cb, bb)) == 1
    assert _seqno(_num(db, ca, ba2)) == 1
    assert _seqno(_num(db, ca, ba, "TR")) == 1
    assert _seqno(_num(db, ca, ba, d=date(2026, 10, 15))) == 1
    # asl hisoblagich ta'sirlanmagan
    assert _seqno(_num(db, ca, ba)) == 3


def test_parallel_numbers_are_unique():
    """20 ta alohida sessiya/ulanish (haqiqiy parallellik) bir xil korxona+filial uchun."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(f"sqlite:///{path}", connect_args={"timeout": 60, "check_same_thread": False})
    try:
        DocumentCounter.__table__.create(eng)
        Session = sessionmaker(bind=eng, expire_on_commit=False)
        results, errors = [], []
        barrier = threading.Barrier(20)

        def worker():
            s = Session()
            try:
                barrier.wait(timeout=30)
                n = next_document_number(s, company_id=7, branch_id=3, doc_type="S", on_date=D)
                s.commit()
                results.append(n)
            except Exception as e:  # pragma: no cover
                errors.append(e)
                s.rollback()
            finally:
                s.close()

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        assert not errors, errors
        assert len(results) == 20 and len(set(results)) == 20
        assert sorted(_seqno(n) for n in results) == list(range(1, 21))
        assert all(n.startswith("S20261014-7-3-") for n in results)
    finally:
        eng.dispose()
        try:
            os.remove(path)
        except OSError:
            pass


# ── 2. 9999 dan keyin ────────────────────────────────────────────────────────

def test_after_9999_goes_to_10000(db, mk):
    c, b, _, _ = mk.tenant()
    db.add(DocumentCounter(company_id=c.id, branch_id=b.id, doc_type="S", period="20261014", last_value=9999))
    db.flush()
    n1 = _num(db, c, b)
    n2 = _num(db, c, b)
    assert n1 == f"S20261014-{c.id}-{b.id}-10000"
    assert n2 == f"S20261014-{c.id}-{b.id}-10001"
    assert n1 != f"S20261014-{c.id}-{b.id}-9999"


# ── 3. O'chirish: raqam qayta ishlatilmaydi ──────────────────────────────────

def _stocked_product(db, c, wh, qty=50):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T114-{n}", barcode=f"B114-{n}", company_id=c.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def test_transfer_number_not_reused_after_delete(db, mk):
    from app.models.transfer import StockTransfer
    from app.schemas.transfer import TransferCreate
    from app.services.transfer_service import create_transfer

    c, b, wh1, u = mk.tenant()
    wh2 = mk.warehouse(c, b, name="Ombor 2")
    p = _stocked_product(db, c, wh1)

    def new_tr():
        data = TransferCreate(from_warehouse_id=wh1.id, to_warehouse_id=wh2.id,
                              items=[{"product_id": p.id, "quantity": 1}])
        return create_transfer(db, data, u.id, c.id)

    t1, t2 = new_tr(), new_tr()
    assert t1.number == f"TR{tashkent_str()}-{c.id}-{b.id}-0001"
    assert t2.number.endswith("-0002")
    # birinchisi o'chiriladi (count+1 bo'lsa keyingisi 0002 bilan to'qnashardi)
    db.delete(t1)
    db.flush()
    t3 = new_tr()
    assert t3.number.endswith("-0003")
    assert len({t2.number, t3.number}) == 2
    assert db.query(StockTransfer).count() == 2


def test_inventory_count_number_not_reused_after_delete(db, mk):
    from app.models.inventory_count import InventoryCount
    from app.services.inventory_count_service import create_inventory_count

    c, b, wh, u = mk.tenant()

    def new_count():
        return create_inventory_count(
            db, SimpleNamespace(warehouse_id=wh.id, note=None, category_id=None, category_ids=None),
            u.id, c.id,
        )

    d1 = new_count()
    assert d1.number == f"IC{tashkent_str()}-{c.id}-{b.id}-0001"
    d1.status = "cancelled"   # bir omborda bitta ochiq revizya bo'lishi uchun
    db.flush()
    d2 = new_count()
    assert d2.number.endswith("-0002")
    d2.status = "cancelled"
    db.delete(d1)
    db.flush()
    d3 = new_count()
    assert d3.number.endswith("-0003")   # eski: count+1 = 2 -> to'qnashuv
    assert db.query(InventoryCount).count() == 2


def test_production_number(db, mk):
    from app.models.bom import BOM, BOMItem
    from app.schemas.production import ProductionOrderCreate
    from app.services.production_service import create_production_order

    c, b, wh1, u = mk.tenant()
    wh2 = mk.warehouse(c, mk.branch(c), name="Tayyor ombor")
    raw = _stocked_product(db, c, wh1)
    fin = _stocked_product(db, c, wh2, qty=0)
    bom = BOM(product_id=fin.id, name="R", company_id=c.id)
    db.add(bom)
    db.flush()
    db.add(BOMItem(bom_id=bom.id, component_product_id=raw.id, quantity_per_unit=Decimal("1")))
    db.flush()
    db.refresh(bom)
    data = ProductionOrderCreate(bom_id=bom.id, planned_quantity=Decimal("2"),
                                 warehouse_id=wh1.id, target_warehouse_id=wh2.id)
    o1 = create_production_order(db, data, u.id, c.id)
    o2 = create_production_order(db, data, u.id, c.id)
    assert o1.number == f"MO{tashkent_str()}-{c.id}-{b.id}-0001"   # filial — xom ashyo ombori filiali
    assert o2.number.endswith("-0002")


def test_purchase_order_number(db, mk):
    from app.services.purchase_order_service import generate_po_number
    c, b, _, _ = mk.tenant()
    assert generate_po_number(db, c.id, b.id) == f"PO{tashkent_str()}-{c.id}-{b.id}-0001"
    assert generate_po_number(db, c.id, b.id).endswith("-0002")


# ── 4. Rollback ──────────────────────────────────────────────────────────────

def test_rollback_rolls_back_counter(db, mk):
    c, b, _, _ = mk.tenant()
    assert _seqno(_num(db, c, b)) == 1
    sp = db.begin_nested()
    assert _seqno(_num(db, c, b)) == 2
    sp.rollback()                        # sotuv tranzaksiyasi bekor — hisoblagich ham
    assert _seqno(_num(db, c, b)) == 2   # bo'shliq yo'q


# ── 5. Sotuv va qaytarish ────────────────────────────────────────────────────

def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal(0), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _sell(db, wh, user, product, qty=2):
    amount = Decimal(qty) * Decimal(1000)
    return create_sale(db, SaleCreate(
        items=[{"product_id": product.id, "quantity": qty, "unit_price": 1000}], payment_type="cash",
        warehouse_id=wh.id, paid_amount=amount, payments=[{"type": "cash", "amount": amount}],
    ), user)


def test_sale_and_return_numbers_and_return_doc(db, client, mk):
    c, b, wh, u = mk.tenant(UserRole.admin)
    _wallet(db, c, b)
    p = _stocked_product(db, c, wh)
    s1 = _sell(db, wh, u, p)
    s2 = _sell(db, wh, u, p)
    day = tashkent_str()
    assert s1.number == f"S{day}-{c.id}-{b.id}-0001"
    assert s2.number == f"S{day}-{c.id}-{b.id}-0002"

    item = db.query(SaleItem).filter(SaleItem.sale_id == s1.id).first()
    r = client.login(u).post(f"/api/sales/{s1.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": 1}], "payment_type": "cash",
    })
    assert r.status_code == 200, r.text
    ret = db.query(Sale).filter(Sale.original_sale_id == s1.id).one()
    assert ret.number == f"R{day}-{c.id}-{b.id}-0001"
    assert ret.number.startswith("R")
    # hisobotlar/smena qaytarishni "R" bilan taniydi
    ids_ret = {i for (i,) in db.query(Sale.id).filter(is_return_doc()).all()}
    assert ret.id in ids_ret and s1.id not in ids_ret and s2.id not in ids_ret
    # sotuv va qaytarish hisoblagichlari alohida
    assert _seqno(s2.number) == 2 and _seqno(ret.number) == 1


def test_direct_return_sale_number(db, mk):
    from app.services.sale_return import create_return_sale
    c, b, wh, u = mk.tenant(UserRole.admin)
    w = _wallet(db, c, b)
    p = _stocked_product(db, c, wh)
    ret = create_return_sale(db, SaleCreate(
        items=[{"product_id": p.id, "quantity": 1, "unit_price": 1000}], payment_type="cash",
        warehouse_id=wh.id, wallet_id=w.id, paid_amount=Decimal(1000), payments=[{"type": "cash", "amount": 1000}],
    ), u)
    assert ret.number == f"R{tashkent_str()}-{c.id}-{b.id}-0001"


# ── 6. Toshkent vaqti ────────────────────────────────────────────────────────

class _FakeDT(datetime):
    """2026-10-14 19:30 UTC = 2026-10-15 00:30 Toshkent."""
    @classmethod
    def now(cls, tz=None):
        base = datetime(2026, 10, 14, 19, 30, tzinfo=timezone.utc)
        return base.astimezone(tz) if tz else base


def test_tashkent_date_at_0030(monkeypatch):
    monkeypatch.setattr(docnum, "datetime", _FakeDT)
    assert docnum.tashkent_today() == date(2026, 10, 15)


def test_number_uses_tashkent_day(db, mk, monkeypatch):
    monkeypatch.setattr(docnum, "datetime", _FakeDT)
    c, b, _, _ = mk.tenant()
    n = next_document_number(db, company_id=c.id, branch_id=b.id, doc_type="S")
    assert n == f"S20261015-{c.id}-{b.id}-0001"      # UTC bo'yicha 20261014 bo'lardi


# ── 7. Eski format bilan to'qnashmaslik ──────────────────────────────────────

def test_old_format_numbers_coexist(db, client, mk):
    c, b, wh, u = mk.tenant(UserRole.admin)
    day = tashkent_str()
    old = Sale(number=f"S{day}0001", cashier_id=u.id, company_id=c.id, warehouse_id=wh.id,
               total_amount=Decimal(1000), paid_amount=Decimal(1000),
               payment_type=PaymentType.cash)
    db.add(old)
    db.flush()
    new_no = _num(db, c, b, d=date.fromisoformat(f"{day[:4]}-{day[4:6]}-{day[6:]}"))
    assert new_no != old.number and "-" in new_no and "-" not in old.number
    # eski hujjat ochiladi va qidiruv ishlaydi
    cl = client.login(u)
    assert cl.get(f"/api/sales/{old.id}").status_code == 200
    r = cl.get("/api/sales/", params={"search": f"S{day}0001"})
    assert r.status_code == 200, r.text


def test_number_columns_are_40_chars():
    from app.models.inventory_count import InventoryCount
    from app.models.production_order import ProductionOrder
    from app.models.purchase_order import PurchaseOrder
    from app.models.transfer import StockTransfer
    for m in (Sale, StockTransfer, InventoryCount, ProductionOrder, PurchaseOrder):
        assert m.__table__.c.number.type.length == 40


# ── 8. Marketplace agenti xaridi ─────────────────────────────────────────────

def test_marketplace_po_uses_shared_sequence(db, mk, monkeypatch):
    from app.models.marketplace import MarketplaceProduct, MarketplaceProductStatus
    from app.models.purchase_order import PurchaseOrder
    from app.models.user import UserStatus
    from app.routers import marketplace_admin as ma
    from app.services import marketplace_service as mp

    monkeypatch.setattr(mp, "notify_agent", lambda **k: None)
    monkeypatch.setattr(mp, "category_name_map", lambda: {})
    c, b, wh, admin = mk.tenant(UserRole.admin)
    agent = mk.user(c, role=UserRole.marketplace_agent, branch=b)
    agent.status = UserStatus.active
    db.flush()

    def approve(n):
        p = MarketplaceProduct(company_id=c.id, agent_id=agent.id, name=f"MP {n}", price=Decimal(100),
                               qty=Decimal(5), category_id=1, barcode=f"MPB{n}-{next(_seq)}", images=[],
                               status=MarketplaceProductStatus.review)
        db.add(p)
        db.flush()
        ma.approve_product(p.id, BackgroundTasks(), None, db, admin)
        db.refresh(p)
        return db.query(PurchaseOrder).filter(PurchaseOrder.id == p.purchase_order_id).one()

    po1, po2 = approve(1), approve(2)
    assert "PO-AG" not in po1.number and "PO-AG" not in po2.number
    assert po1.number == f"PO{tashkent_str()}-{c.id}-{b.id}-0001"
    assert po2.number.endswith("-0002")


# ── 9. POST /sales: kutilmagan IntegrityError -> 409 ─────────────────────────

def test_make_sale_integrity_error_returns_409(db, client, mk, monkeypatch):
    from app.routers import sales as sales_router
    c, b, wh, u = mk.tenant(UserRole.cashier)

    def boom(**kw):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(sales_router, "create_sale", boom)
    p = _stocked_product(db, c, wh)
    r = client.login(u).post("/api/sales/", json={
        "items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
        "warehouse_id": wh.id, "paid_amount": 1000,
    })
    assert r.status_code == 409, r.text
    assert "ziddiyat" in r.json()["detail"]


# ── 10. Ikki korxona izolyatsiyasi (raqamlar va resurslar) ───────────────────

def test_two_companies_isolation(db, client, mk):
    ca, ba, wha, ua = mk.tenant(UserRole.admin)
    cb, bb, whb, ub = mk.tenant(UserRole.admin)
    _wallet(db, ca, ba)
    _wallet(db, cb, bb)
    pa = _stocked_product(db, ca, wha)
    pb = _stocked_product(db, cb, whb)
    sa = _sell(db, wha, ua, pa)
    sb = _sell(db, whb, ub, pb)
    # ikkala korxona ham o'z hisoblagichida 0001 oladi, raqamlar korxona bo'yicha farqlanadi
    assert _seqno(sa.number) == 1 and _seqno(sb.number) == 1
    assert sa.number != sb.number and f"-{ca.id}-" in sa.number and f"-{cb.id}-" in sb.number
    # A foydalanuvchisi B ning sotuvini ko'ra olmaydi, o'zinikini ko'radi
    cl = client.login(ua)
    assert cl.get(f"/api/sales/{sb.id}").status_code in (403, 404)
    r = cl.get(f"/api/sales/{sa.id}")
    assert r.status_code == 200 and r.json()["number"] == sa.number
