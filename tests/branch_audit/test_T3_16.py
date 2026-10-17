"""T3.16 — Filial bo'yicha Telegram bildirishnomalar va hisobotlar.

Qamrov: xabarda filial/ombor qatori (`describe_location`), oluvchilar (`resolve_recipients`: rol, filial,
UserCompany, takrorlar, daily_report_recipients, notify_branch_managers), botga ulanish (menejer, ikkinchi
direktor, begona odam), hisobotlar filial kesimida, "kam zaxira" soni, sotuv xabari javobni kutdirmasligi,
parallel yuborish, qarz eslatmasi admin bot tokeni bilan, bot sozlamalari qisman yangilanishi, frontend kalitlari.
"""
import asyncio
import inspect
import itertools
import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

import app.admin_tg_bot.notifications as notifications
import app.database as app_database
import app.routers.finance as fin
import app.routers.sales as sales_router
import app.services.scheduler as sched
from app.admin_tg_bot import bot_manager
from app.admin_tg_bot.bot_schemas import CompanyBotSettingsUpdate
from app.admin_tg_bot.message_utils import describe_location
from app.admin_tg_bot.models import CompanyBot
from app.admin_tg_bot.recipients import resolve_recipients
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.moliya import Expense, ExpenseCategory, Wallet
from app.models.product import Product, ProductStatus
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany
from app.utils.report_utils import LOCAL_TZ, low_stock_product_count, sales_summary, local_today

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _now():
    return datetime.now(LOCAL_TZ)


def _bot(db, company, **kw):
    b = CompanyBot(company_id=company.id, bot_token=f"tok-{next(_seq)}:{'x' * 10}", bot_type="admin",
                   is_active=True, **kw)
    db.add(b)
    db.flush()
    return b


def _uc(db, user, company, role=UserRole.manager, branch=None, is_active=True):
    row = UserCompany(user_id=user.id, company_id=company.id, role=role, is_active=is_active,
                      branch_id=branch.id if branch else None)
    db.add(row)
    db.flush()
    return row


def _sale(db, user, company, warehouse, amount, customer=None, number=None):
    s = Sale(number=number or f"ST316-{next(_seq)}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), paid_cash=Decimal(amount), payment_type=PaymentType.cash,
             status=SaleStatus.completed, created_at=_now(), customer_id=customer.id if customer else None)
    db.add(s)
    db.flush()
    return s


def _tg(user, chat):
    user.tg_chat_id = chat
    return user


@pytest.fixture
def three(db, mk):
    """A korxona: 3 faol filial (Chilonzor, Yunusobod, Sergeli) + omborlar; admin, direktor, 3 menejer."""
    ca = mk.company()
    bs = [mk.branch(ca, name=n) for n in ("Chilonzor", "Yunusobod", "Sergeli")]
    ws = [mk.warehouse(ca, b, name=f"Ombor {b.name}") for b in bs]
    admin = _tg(mk.user(ca, role=UserRole.admin, name="Admin A"), f"adm{next(_seq)}")
    director = _tg(mk.user(ca, role=UserRole.director, name="Direktor A"), f"dir{next(_seq)}")
    mgrs = [_tg(mk.user(ca, role=UserRole.manager, branch=b, name=f"Menejer {b.name}"), f"mgr{next(_seq)}")
            for b in bs]
    bot = _bot(db, ca)
    db.flush()
    return dict(ca=ca, bs=bs, ws=ws, admin=admin, director=director, mgrs=mgrs, bot=bot)


class FakeBot:
    """aiogram Bot o'rniga: yuborilgan xabarlarni yig'adi (ixtiyoriy kechikish bilan)."""
    sent = []
    delay = 0.0
    inits = []

    def __init__(self, *args, **kwargs):
        FakeBot.inits.append(kwargs)
        self.session = MagicMock()
        self.session.close = AsyncMock()

    async def send_message(self, chat_id, text, **kw):
        if FakeBot.delay:
            await asyncio.sleep(FakeBot.delay)
        FakeBot.sent.append((chat_id, text))


@pytest.fixture
def fakebot(db, monkeypatch):
    FakeBot.sent, FakeBot.delay, FakeBot.inits = [], 0.0, []
    monkeypatch.setattr(notifications, "SessionLocal", app_database.SessionLocal)
    monkeypatch.setattr(notifications, "Bot", FakeBot)
    return FakeBot


@pytest.fixture
def bot_db(db, monkeypatch):
    monkeypatch.setattr(bot_manager, "SessionLocal", app_database.SessionLocal)
    return db


@pytest.fixture
def sch(db, monkeypatch):
    monkeypatch.setattr(sched, "SessionLocal", app_database.SessionLocal)
    return sched


# ─── 1. describe_location: filial/ombor qatori ───────────────────────────────

def test_describe_location_multi_branch_shows_branch_and_warehouse(db, three):
    t = three
    line = describe_location(db, warehouse_id=t['ws'][0].id, branch_id=t['bs'][0].id)
    assert line == "🏬 Filial: Chilonzor · Ombor: Ombor Chilonzor"
    # filial berilmasa ombor orqali topiladi
    assert describe_location(db, warehouse_id=t['ws'][1].id).startswith("🏬 Filial: Yunusobod")


def test_describe_location_hidden_for_single_branch_and_unknown(db, mk):
    c, b, w, _ = mk.tenant()                       # bitta filial
    assert describe_location(db, warehouse_id=w.id, branch_id=b.id) == ""
    assert describe_location(db) == ""
    # ikkinchi filial yopilgan (nofaol) bo'lsa ham ko'rsatilmaydi — faol filiallar soni 1
    b2 = mk.branch(c, name="Yopilgan", is_active=False)
    assert describe_location(db, branch_id=b2.id) == ""


def test_describe_location_foreign_branch_not_leaked_and_escaped(db, mk, three):
    other_c, other_b, other_w, _ = mk.tenant()
    t = three
    # A ombori + B filiali: begona filial nomi chiqmaydi
    line = describe_location(db, warehouse_id=t['ws'][0].id, branch_id=other_b.id)
    assert other_b.name not in line
    t['bs'][0].name = "Fil<ial> & Co"
    db.flush()
    assert "Fil&lt;ial&gt; &amp; Co" in describe_location(db, warehouse_id=t['ws'][0].id, branch_id=t['bs'][0].id)
    # warehouse_id None (eski sotuv) va filial yo'q -> qator yashiriladi ("Filial: —" yo'q)
    assert describe_location(db, warehouse_id=None, branch_id=None) == ""


def test_describe_location_includes_wallet(db, three):
    t = three
    w = Wallet(name="Asosiy kassa", type="cash", balance=Decimal(0), company_id=t['ca'].id,
               branch_id=t['bs'][2].id, is_active=True)
    db.add(w)
    db.flush()
    line = describe_location(db, branch_id=t['bs'][2].id, wallet_id=w.id)
    assert line == "🏬 Filial: Sergeli · Kassa: Asosiy kassa"


# ─── 2. resolve_recipients: rol / filial / UserCompany / sozlamalar ──────────

def _ids(users):
    return {u.id for u in users}


def test_recipients_instant_leaders_plus_branch_manager_only(db, mk, three):
    t = three
    cashier = _tg(mk.user(t['ca'], role=UserRole.cashier, branch=t['bs'][0]), "csh1")
    # begona korxona rahbari
    cb, _, _, ub = mk.tenant()
    _tg(ub, "foreign1")
    db.flush()

    got = _ids(resolve_recipients(db, t['ca'].id, branch_id=t['bs'][0].id, kind="sale"))
    assert got == {t['admin'].id, t['director'].id, t['mgrs'][0].id}
    assert cashier.id not in got and ub.id not in got
    # boshqa filial menejeri — o'z filialiga faqat
    got2 = _ids(resolve_recipients(db, t['ca'].id, branch_id=t['bs'][1].id, kind="finance"))
    assert got2 == {t['admin'].id, t['director'].id, t['mgrs'][1].id}
    # filial berilmasa menejerlar yo'q
    assert _ids(resolve_recipients(db, t['ca'].id, kind="sale")) == {t['admin'].id, t['director'].id}


def test_recipients_notify_branch_managers_false_excludes_managers(db, three):
    t = three
    t['bot'].notify_branch_managers = False
    db.flush()
    got = _ids(resolve_recipients(db, t['ca'].id, branch_id=t['bs'][0].id, kind="sale"))
    assert got == {t['admin'].id, t['director'].id}


def test_recipients_user_company_member_and_inactive(db, mk, three):
    t = three
    # ko'p korxonali: uy korxonasi — boshqa, A da faol menejer (Yunusobod)
    home, _, _, _ = mk.tenant()
    multi = _tg(mk.user(home, role=UserRole.manager, name="Ko'p korxonali"), "multi1")
    _uc(db, multi, t['ca'], role=UserRole.manager, branch=t['bs'][1])
    # UserCompany orqali ikkinchi direktor (uy korxonasi — boshqa)
    dir2 = _tg(mk.user(home, role=UserRole.cashier, name="Direktor 2"), "dir2")
    _uc(db, dir2, t['ca'], role=UserRole.director)
    # nofaol a'zolik
    gone = _tg(mk.user(home, role=UserRole.admin), "gone1")
    _uc(db, gone, t['ca'], role=UserRole.admin, is_active=False)
    got = _ids(resolve_recipients(db, t['ca'].id, branch_id=t['bs'][1].id, kind="sale"))
    assert multi.id in got and dir2.id in got and gone.id not in got
    # uy korxonasida (home) A xodimlari ko'rinmaydi
    # uy korxonasida u filialsiz menejer -> A filiali xabari unga o'sha yerdan bormaydi
    assert multi.id not in _ids(resolve_recipients(db, home.id, branch_id=t['bs'][1].id, kind="sale"))


def test_recipients_blocked_and_no_chat_excluded_and_deduped(db, mk, three):
    t = three
    blocked = _tg(mk.user(t['ca'], role=UserRole.admin, status=UserStatus.blocked), "blk1")
    no_chat = mk.user(t['ca'], role=UserRole.director)
    _tg(mk.user(t['ca'], role=UserRole.admin), t['admin'].tg_chat_id)           # bir xil tg_chat_id
    got = resolve_recipients(db, t['ca'].id, kind="sale")
    assert blocked.id not in _ids(got) and no_chat.id not in _ids(got)
    assert len([u for u in got if u.tg_chat_id == t['admin'].tg_chat_id]) == 1


def test_recipients_daily_report_recipients_matrix(db, three):
    t = three
    c = t['ca']

    def who(kind, branch=None, **kw):
        return _ids(resolve_recipients(db, c.id, branch_id=branch, kind=kind, **kw))

    leaders = {t['admin'].id, t['director'].id}
    c.daily_report_recipients = "owners_and_admins"
    db.flush()
    assert who("daily_report") == leaders
    assert who("daily_report", t['bs'][0].id) == leaders              # menejer jadvalli xabarni olmaydi
    assert who("debt") == leaders and who("expiry") == leaders

    c.daily_report_recipients = "owners"
    db.flush()
    assert who("daily_report") == {t['director'].id}
    assert who("debt") == {t['director'].id} and who("expiry") == {t['director'].id}
    # zudlik bilan yuboriladigan xabarlarga ta'sir qilmaydi
    assert who("sale") == leaders

    c.daily_report_recipients = "all_managers"
    db.flush()
    assert who("daily_report") == leaders                              # filialsiz -> menejerlar yo'q
    assert who("daily_report", t['bs'][0].id) == leaders | {t['mgrs'][0].id}
    assert who("daily_report", t['bs'][0].id, managers_only=True) == {t['mgrs'][0].id}
    t['bot'].notify_branch_managers = False
    db.flush()
    assert who("daily_report", t['bs'][0].id, managers_only=True) == set()

    with pytest.raises(ValueError):
        resolve_recipients(db, c.id, kind="nomalum")


def test_recipients_manager_without_branch_gets_nothing(db, mk, three):
    t = three
    free = _tg(mk.user(t['ca'], role=UserRole.manager), "free1")          # filialsiz menejer
    assert free.id not in _ids(resolve_recipients(db, t['ca'].id, branch_id=t['bs'][0].id, kind="sale"))


# ─── 3. Botga ulanish ────────────────────────────────────────────────────────

def test_manager_links_by_phone_including_user_company(bot_db, mk):
    c, b, w, _ = mk.tenant()
    mgr = mk.user(c, role=UserRole.manager, branch=b, phone="+998901110011")
    user, status = bot_manager.link_admin_by_phone("+998 90 111 00 11", "tg-m1", None, c.id)
    assert status == "success" and user.id == mgr.id
    # ko'p korxonali foydalanuvchi: uy korxonasi — boshqa, user_companies orqali menejer
    other, _, _, _ = mk.tenant()
    multi = mk.user(other, role=UserRole.cashier, phone="+998902220022")
    _uc(bot_db, multi, c, role=UserRole.manager, branch=b)
    user, status = bot_manager.link_admin_by_phone("+998902220022", "tg-m2", None, c.id)
    assert status == "success" and user.id == multi.id


def test_second_director_links_but_stranger_cannot(bot_db, mk):
    c, b, w, admin = mk.tenant()
    mk.user(c, role=UserRole.director, phone="+998903330033")
    d2 = mk.user(c, role=UserRole.director, phone="+998904440044")
    assert bot_manager.link_admin_by_phone("+998903330033", "tg-d1", None, c.id)[1] == "success"
    user, status = bot_manager.link_admin_by_phone("+998904440044", "tg-d2", None, c.id)
    assert status == "success" and user.id == d2.id                  # already_registered qaytmaydi
    # T0.16: tizimda yo'q raqam — yangi foydalanuvchi YARATILMAYDI
    n = bot_db.query(User).count()
    assert bot_manager.link_admin_by_phone("+998909990099", "tg-x", None, c.id) == (None, "not_found")
    assert bot_db.query(User).count() == n
    # begona korxona odami bu korxona botiga ulana olmaydi
    c2, _, _, _ = mk.tenant()
    mk.user(c2, role=UserRole.director, phone="+998905550055")
    assert bot_manager.link_admin_by_phone("+998905550055", "tg-y", None, c.id) == (None, "not_found")
    # kassir ruxsat etilmagan rol
    mk.user(c, role=UserRole.cashier, phone="+998906660066")
    assert bot_manager.link_admin_by_phone("+998906660066", "tg-z", None, c.id) == (None, "not_allowed")


# ─── 4. Hisobotlar: filial kesimi ────────────────────────────────────────────

def test_sales_summary_branch_filters_sum_to_company_total(db, three):
    t = three
    for i, (w, amt) in enumerate(zip(t['ws'], (1000, 2500, 400))):
        _sale(db, t['admin'], t['ca'], w, amt)
        _sale(db, t['admin'], t['ca'], w, amt)
    start = datetime.combine(local_today(), datetime.min.time()).replace(tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    whole = sales_summary(db, t['ca'].id, start, end)
    parts = [sales_summary(db, t['ca'].id, start, end, wh_ids=[w.id]) for w in t['ws']]
    assert whole['count'] == 6 and sum(p['count'] for p in parts) == 6
    assert sum(p['gross'] for p in parts) == whole['gross'] == 7800
    assert sales_summary(db, t['ca'].id, start, end, wh_ids=[])['count'] == 0


def test_bot_reports_by_branch(bot_db, three):
    t = three
    _sale(bot_db, t['admin'], t['ca'], t['ws'][0], 1000)
    _sale(bot_db, t['admin'], t['ca'], t['ws'][1], 2000)
    _sale(bot_db, t['admin'], t['ca'], t['ws'][1], 3000)
    whole = bot_manager.get_daily_sales_report(t['ca'].id)
    b0 = bot_manager.get_daily_sales_report(t['ca'].id, branch_id=t['bs'][0].id)
    b1 = bot_manager.get_daily_sales_report(t['ca'].id, branch_id=t['bs'][1].id)
    b2 = bot_manager.get_daily_sales_report(t['ca'].id, branch_id=t['bs'][2].id)
    assert whole['sales_count'] == 3 and whole['total_amount'] == 6000
    assert (b0['sales_count'], b1['sales_count'], b2['sales_count']) == (1, 2, 0)
    assert b0['total_amount'] + b1['total_amount'] + b2['total_amount'] == whole['total_amount']
    assert b1['branch_name'] == "Yunusobod"
    m_whole = bot_manager.get_monthly_sales_report(t['ca'].id)
    m1 = bot_manager.get_monthly_sales_report(t['ca'].id, branch_id=t['bs'][1].id)
    assert m_whole['sales_count'] == 3 and m1['sales_count'] == 2
    assert sum(d['count'] for d in m1['daily_data']) == 2 and m1['total_amount'] == 5000


def _fake_message(tg_id, text=None):
    m = MagicMock()
    m.from_user.id = tg_id
    m.from_user.full_name = "TG"
    m.text = text
    m.answer = AsyncMock()
    return m


def _fake_state():
    s = MagicMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    return s


def _answers(msg):
    return "\n".join(str(c.args[0]) for c in msg.answer.await_args_list)


def test_manager_gets_only_own_branch_report_from_bot(bot_db, three):
    t = three
    _sale(bot_db, t['admin'], t['ca'], t['ws'][0], 1000)
    _sale(bot_db, t['admin'], t['ca'], t['ws'][1], 9000)
    mgr = t['mgrs'][0]
    mgr.tg_chat_id = "7001"
    bot_db.flush()
    msg, state = _fake_message(7001), _fake_state()
    asyncio.run(bot_manager.handle_daily_report(msg, state, t['ca'].id))
    text = _answers(msg)
    assert "Kunlik Sotuv Hisoboti" in text and "Filial: <b>Chilonzor</b>" in text
    assert "1,000.0 UZS" in text and "9,000" not in text and "10,000" not in text
    # filialsiz menejer
    t['mgrs'][2].branch_id = None
    t['mgrs'][2].tg_chat_id = "7003"
    bot_db.flush()
    msg2 = _fake_message(7003)
    asyncio.run(bot_manager.handle_monthly_report(msg2, _fake_state(), t['ca'].id))
    assert "filial biriktirilmagan" in _answers(msg2)


def test_admin_with_multiple_branches_gets_branch_picker_and_callback(bot_db, three):
    from aiogram.types import InlineKeyboardMarkup
    t = three
    _sale(bot_db, t['admin'], t['ca'], t['ws'][0], 1000)
    _sale(bot_db, t['admin'], t['ca'], t['ws'][1], 2000)
    t['admin'].tg_chat_id = "8001"
    bot_db.flush()
    msg, state = _fake_message(8001), _fake_state()
    asyncio.run(bot_manager.handle_daily_report(msg, state, t['ca'].id))
    kb = msg.answer.await_args.kwargs['reply_markup']
    assert isinstance(kb, InlineKeyboardMarkup)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas[0] == "rep:daily:all"
    assert set(datas[1:]) == {f"rep:daily:{b.id}" for b in t['bs']}

    # tugma: bitta filial
    cb = MagicMock()
    cb.data = f"rep:daily:{t['bs'][1].id}"
    cb.from_user.id = 8001
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    asyncio.run(bot_manager.handle_report_callback(cb, t['ca'].id))
    out = str(cb.message.answer.await_args.args[0])
    assert "Filial: <b>Yunusobod</b>" in out and "2,000.0 UZS" in out and "1,000" not in out
    # tugma: barcha filiallar
    cb.data = "rep:monthly:all"
    asyncio.run(bot_manager.handle_report_callback(cb, t['ca'].id))
    out = str(cb.message.answer.await_args.args[0])
    assert "Barcha filiallar" in out and "3,000.0 UZS" in out


def test_report_callback_forged_requests_rejected(bot_db, mk, three):
    t = three
    t['mgrs'][0].tg_chat_id = "9001"
    other_c, other_b, _, other_admin = mk.tenant()
    other_admin.tg_chat_id = "9002"
    bot_db.flush()

    def press(tg_id, data, company_id):
        cb = MagicMock()
        cb.data = data
        cb.from_user.id = tg_id
        cb.answer = AsyncMock()
        cb.message.answer = AsyncMock()
        asyncio.run(bot_manager.handle_report_callback(cb, company_id))
        return cb

    # menejer boshqa filialni so'raydi
    cb = press(9001, f"rep:daily:{t['bs'][1].id}", t['ca'].id)
    cb.message.answer.assert_not_awaited() and cb.answer.assert_awaited()
    assert cb.answer.await_args.kwargs.get('show_alert') is True
    # menejer "all" so'raydi
    cb = press(9001, "rep:daily:all", t['ca'].id)
    cb.message.answer.assert_not_awaited()
    # begona korxona rahbari (B) A botida
    cb = press(9002, "rep:daily:all", t['ca'].id)
    cb.message.answer.assert_not_awaited()
    # admin begona korxona filialini so'raydi
    t['admin'].tg_chat_id = "9003"
    bot_db.flush()
    cb = press(9003, f"rep:daily:{other_b.id}", t['ca'].id)
    cb.message.answer.assert_not_awaited()
    # buzilgan callback
    cb = press(9003, "rep:zzz:1", t['ca'].id)
    cb.message.answer.assert_not_awaited()
    # ijobiy yo'l: menejer o'z filiali
    cb = press(9001, f"rep:daily:{t['bs'][0].id}", t['ca'].id)
    cb.message.answer.assert_awaited()


def test_single_branch_admin_gets_report_without_picker(bot_db, mk):
    c, b, w, admin = mk.tenant()
    admin.tg_chat_id = "6001"
    bot_db.flush()
    msg = _fake_message(6001)
    asyncio.run(bot_manager.handle_daily_report(msg, _fake_state(), c.id))
    assert "Kunlik Sotuv Hisoboti" in _answers(msg) and "Filial:" not in _answers(msg)


def test_register_handlers_registers_report_callback():
    src = inspect.getsource(bot_manager.register_handlers)
    assert 'F.data.startswith("rep:")' in src


# ─── 5. "Kam zaxira" soni ────────────────────────────────────────────────────

def _product(db, company, name, min_stock=0, **kw):
    p = Product(name=name, sku=f"SK{next(_seq)}", barcode=f"BC{next(_seq)}", company_id=company.id,
                cost_price=0, sale_price=0, product_type="simple", min_stock=min_stock, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    db.add(StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(qty)))
    db.flush()


def test_low_stock_product_count_rules(db, mk):
    c = mk.company()
    b = mk.branch(c)
    w1, w2, w3 = (mk.warehouse(c, b) for _ in range(3))
    dead_wh = mk.warehouse(c, b, is_active=False)
    # bir mahsulot 3 omborda kam -> 1 marta sanaladi (jami 6 < 10)
    p1 = _product(db, c, "Sut")
    for w in (w1, w2, w3):
        _stock(db, p1, w, 2)
    assert low_stock_product_count(db, c.id) == 1
    # min_stock=50, qoldiq 30 -> kam
    p2 = _product(db, c, "Un", min_stock=50)
    _stock(db, p2, w1, 30)
    assert low_stock_product_count(db, c.id) == 2
    # min_stock=0 -> chegara 10 (15 yetarli, 9 kam)
    p3 = _product(db, c, "Shakar")
    _stock(db, p3, w1, 15)
    assert low_stock_product_count(db, c.id) == 2
    p4 = _product(db, c, "Tuz")
    _stock(db, p4, w1, 9)
    assert low_stock_product_count(db, c.id) == 3
    # o'chirilgan / nofaol mahsulot sanalmaydi
    p5 = _product(db, c, "Eski", is_deleted=True)
    _stock(db, p5, w1, 1)
    p6 = _product(db, c, "Arxiv", status=ProductStatus.archived)
    _stock(db, p6, w1, 1)
    assert low_stock_product_count(db, c.id) == 3
    # nofaol ombor qatori hisobga kirmaydi
    p7 = _product(db, c, "Nofaol ombor")
    _stock(db, p7, dead_wh, 1)
    assert low_stock_product_count(db, c.id) == 3
    # omborlar bo'yicha cheklash va bo'sh ro'yxat
    assert low_stock_product_count(db, c.id, [w2.id]) == 1          # w2 da faqat Sut (2 < 10)
    assert low_stock_product_count(db, c.id, []) == 0
    # begona korxona tovari sanalmaydi
    c2 = mk.company()
    b2 = mk.branch(c2)
    w_other = mk.warehouse(c2, b2)
    _stock(db, _product(db, c2, "Begona"), w_other, 1)
    assert low_stock_product_count(db, c.id) == 3
    assert low_stock_product_count(db, c2.id) == 1


# ─── 6. Kunlik hisobot matni ─────────────────────────────────────────────────

def test_daily_report_branch_section_scope_and_debt(db, three):
    from app.services.ai_scope import _make_scope
    from app.services.ai_service import build_daily_report
    t = three
    ca = t['ca']
    _sale(db, t['admin'], ca, t['ws'][0], 1000)
    _sale(db, t['admin'], ca, t['ws'][1], 2000)
    full = build_daily_report(db, ca.id, ca.name)
    assert "FILIALLAR KESIMI" in full and "MOLIYAVIY HOLAT" in full
    no_branches = build_daily_report(db, ca.id, ca.name, include_branches=False)
    assert "FILIALLAR KESIMI" not in no_branches and "MOLIYAVIY HOLAT" in no_branches
    # filial hisoboti: qarz bo'limisiz, o'z filiali raqamlari
    scope = _make_scope(db, ca.id, [t['bs'][0].id], True)
    br = build_daily_report(db, ca.id, ca.name, scope=scope, include_branches=False)
    assert "MOLIYAVIY HOLAT" not in br and "Chilonzor" in br
    assert "Tranzaksiyalar soni: <b>1 ta</b>" in br


def test_daily_report_stock_section_text_and_alert_switch(db, mk):
    from app.services.ai_service import build_daily_report
    c, b, w, u = mk.tenant()
    for i in range(3):
        _stock(db, _product(db, c, f"Kam {i}", min_stock=100), w, 1)
    text = build_daily_report(db, c.id, c.name)
    assert "3 ta mahsulot zaxirasi kritik" in text and "turdagi" not in text
    c.low_stock_alert = False
    db.flush()
    off = build_daily_report(db, c.id, c.name)
    assert "ZAXIRA HOLATI" not in off and "kritik" not in off


# ─── 7. Zudlik bilan xabar: filial qatori, oluvchilar, asinxron ──────────────

def test_notify_new_sale_has_branch_line_and_goes_to_branch_manager(db, three, fakebot):
    t = three
    cust = Customer(name="Mijoz <1>", company_id=t['ca'].id)
    db.add(cust)
    db.flush()
    sale = _sale(db, t['admin'], t['ca'], t['ws'][0], 250000, customer=cust)
    asyncio.run(notifications.notify_new_sale(sale.id))
    by_chat = dict(fakebot.sent)
    text = by_chat[t['admin'].tg_chat_id]
    assert "🏬 Filial: Chilonzor · Ombor: Ombor Chilonzor" in text
    assert "Yangi Sotuv" in text and "250,000 UZS" in text and "Mijoz &lt;1&gt;" in text
    # oluvchilar: admin, direktor, Chilonzor menejeri — boshqa filial menejerlari emas
    assert set(by_chat) == {t['admin'].tg_chat_id, t['director'].tg_chat_id, t['mgrs'][0].tg_chat_id}
    # bot sessiyasiga timeout berilgan (10 soniya)
    assert fakebot.inits and fakebot.inits[0]['session'].timeout == notifications.BOT_REQUEST_TIMEOUT == 10


def test_notify_new_sale_manager_off_and_single_branch(db, mk, three, fakebot):
    t = three
    t['bot'].notify_branch_managers = False
    db.flush()
    sale = _sale(db, t['admin'], t['ca'], t['ws'][1], 1000)
    asyncio.run(notifications.notify_new_sale(sale.id))
    assert t['mgrs'][1].tg_chat_id not in dict(fakebot.sent)
    assert set(dict(fakebot.sent)) == {t['admin'].tg_chat_id, t['director'].tg_chat_id}

    # bitta filialli korxona: "Filial:" qatori yo'q
    fakebot.sent.clear()
    c, b, w, u = mk.tenant()
    u.tg_chat_id = "single1"
    _bot(db, c)
    s2 = _sale(db, u, c, w, 500)
    asyncio.run(notifications.notify_new_sale(s2.id))
    assert fakebot.sent and "Filial:" not in fakebot.sent[0][1] and "🏬" not in fakebot.sent[0][1]


def test_notify_new_sale_unknown_sale_and_disabled_setting(db, three, fakebot):
    t = three
    asyncio.run(notifications.notify_new_sale(10 ** 9))                  # topilmadi -> xatosiz
    t['bot'].notify_instant_sales = False
    db.flush()
    sale = _sale(db, t['admin'], t['ca'], t['ws'][0], 1)
    asyncio.run(notifications.notify_new_sale(sale.id))
    assert fakebot.sent == []


def test_send_instant_notification_parallel_and_failure_isolated(db, three, fakebot):
    t = three
    fakebot.delay = 0.3
    t0 = time.time()
    asyncio.run(notifications.send_instant_notification(t['ca'].id, "salom", "sale", t['bs'][0].id))
    elapsed = time.time() - t0
    assert len(fakebot.sent) == 3
    assert elapsed < 0.8                      # ketma-ket bo'lsa 0.9+ soniya

    # bitta oluvchiga yuborish xato bersa, qolganlariga ketadi
    fakebot.sent.clear()
    fakebot.delay = 0.0
    orig = FakeBot.send_message

    async def flaky(self, chat_id, text, **kw):
        if chat_id == t['admin'].tg_chat_id:
            raise RuntimeError("Forbidden: bot was blocked")
        return await orig(self, chat_id, text, **kw)

    FakeBot.send_message = flaky
    try:
        asyncio.run(notifications.send_instant_notification(t['ca'].id, "salom", "sale", t['bs'][0].id))
    finally:
        FakeBot.send_message = orig
    assert t['admin'].tg_chat_id not in dict(fakebot.sent) and len(fakebot.sent) == 2


def test_trigger_instant_notification_does_not_block_caller(monkeypatch):
    started, done = threading.Event(), threading.Event()

    async def slow(company_id, text, notif_type, branch_id=None):
        started.set()
        await asyncio.sleep(1.0)
        done.set()

    monkeypatch.setattr(notifications, "send_instant_notification", slow)
    t0 = time.time()
    notifications.trigger_instant_notification(1, "x", "sale", 5)       # event loop yo'q (threadpool kabi)
    assert time.time() - t0 < 0.5
    assert started.wait(3) and not done.is_set()                         # fon thread'da ishlayapti
    assert done.wait(5)


def test_make_sale_does_not_wait_for_telegram(db, mk, monkeypatch):
    """Mezon 4: make_sale javobi Telegramga bog'liq emas — notify_new_sale faqat background_tasks ga qo'shiladi."""
    c, b, w, user = mk.tenant(role=UserRole.cashier)
    sale = _sale(db, user, c, w, 1000)

    async def slow_notify(sale_id):
        await asyncio.sleep(3)

    monkeypatch.setattr(sales_router, "notify_new_sale", slow_notify)
    monkeypatch.setattr(sales_router, "create_sale", lambda **kw: sale)
    bt = BackgroundTasks()
    request = SimpleNamespace(client=None, headers={})
    data = SimpleNamespace(items=[object()])
    t0 = time.time()
    out = sales_router.make_sale(data=data, request=request, background_tasks=bt, db=db,
                                 current_user=user, ctx=SimpleNamespace(branch_id=None))
    assert time.time() - t0 < 1.0
    assert out.id == sale.id
    assert [(task.func, task.args) for task in bt.tasks] == [(slow_notify, (sale.id,))]
    assert inspect.iscoroutinefunction(notifications.notify_new_sale)


def test_sales_router_source_has_no_blocking_telegram_call():
    src = inspect.getsource(sales_router.make_sale)
    assert "background_tasks.add_task(notify_new_sale, sale.id)" in src
    assert "trigger_instant_notification" not in src


# ─── 8. Moliya endpointlari: filial qatori va fon yuborish ───────────────────

def _wallet(db, company, branch, name="Kassa"):
    w = Wallet(name=name, type="cash", balance=Decimal(100000), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    return w


def test_create_expense_notification_has_branch_and_runs_in_background(client, db, three, monkeypatch):
    t = three
    calls = []
    monkeypatch.setattr(fin, "trigger_instant_notification", lambda *a, **k: calls.append(a))
    cat = ExpenseCategory(name="Ijara <x>", company_id=t['ca'].id)
    db.add(cat)
    wal = _wallet(db, t['ca'], t['bs'][2], name="Sergeli kassa")
    db.flush()
    r = client.login(t['admin']).post('/api/finance/expenses', json={
        "category_id": cat.id, "amount": 300, "wallet_id": wal.id, "branch_id": t['bs'][1].id,
        "description": "Ijara"})
    assert r.status_code == 201, r.text
    assert len(calls) == 1
    company_id, msg, kind, branch_id = calls[0]
    assert company_id == t['ca'].id and kind == "finance" and branch_id == t['bs'][1].id
    assert "🏬 Filial: Yunusobod · Kassa: Sergeli kassa" in msg and "Ijara &lt;x&gt;" in msg


def test_create_expense_foreign_wallet_404_no_notification(client, db, mk, three, monkeypatch):
    t = three
    calls = []
    monkeypatch.setattr(fin, "trigger_instant_notification", lambda *a, **k: calls.append(a))
    cb, bb, wb, ub = mk.tenant()
    cat = ExpenseCategory(name="Ijara", company_id=cb.id)
    db.add(cat)
    wal_a = _wallet(db, t['ca'], t['bs'][0])
    db.flush()
    r = client.login(ub).post('/api/finance/expenses', json={"category_id": cat.id, "amount": 10, "wallet_id": wal_a.id})
    assert r.status_code == 404
    assert calls == []


def test_expense_single_branch_company_has_no_location_line(client, db, mk, monkeypatch):
    c, b, w, u = mk.tenant()
    calls = []
    monkeypatch.setattr(fin, "trigger_instant_notification", lambda *a, **k: calls.append(a))
    cat = ExpenseCategory(name="Ijara", company_id=c.id)
    db.add(cat)
    wal = _wallet(db, c, b)
    db.flush()
    r = client.login(u).post('/api/finance/expenses', json={"category_id": cat.id, "amount": 5, "wallet_id": wal.id})
    assert r.status_code == 201, r.text
    assert "Filial:" not in calls[0][1] and "Yangi Xarajat" in calls[0][1]


def test_customer_debt_payment_notification_has_branch(client, db, three, monkeypatch):
    t = three
    calls = []
    monkeypatch.setattr(fin, "trigger_instant_notification", lambda *a, **k: calls.append(a))
    cust = Customer(name="Qarzdor", company_id=t['ca'].id, debt_balance=Decimal(5000), debt_balances={"UZS": 5000.0})
    db.add(cust)
    wal = _wallet(db, t['ca'], t['bs'][1], name="Yunusobod kassa")
    db.flush()
    r = client.login(t['admin']).post(f'/api/finance/customer-debts/{cust.id}/pay',
                                      json={"amount": 500, "wallet_id": wal.id})
    assert r.status_code == 200, r.text
    assert len(calls) == 1
    company_id, msg, kind, branch_id = calls[0]
    assert kind == "finance" and branch_id == t['bs'][1].id and company_id == t['ca'].id
    assert "Filial: Yunusobod" in msg and "Kassa: Yunusobod kassa" in msg and "Qarz To'lovi" in msg


def test_finance_endpoints_use_background_tasks():
    for fn in (fin.create_expense, fin.record_customer_debt_payment):
        assert "background_tasks" in inspect.signature(fn).parameters
        assert "background_tasks.add_task(trigger_instant_notification" in inspect.getsource(fn)


# ─── 9. Scheduler: qarz eslatmasi admin bot orqali, hisobot oluvchilari ─────

def _overdue_sale(db, user, company, warehouse):
    cust = Customer(name="Qarzdor", company_id=company.id, debt_balance=Decimal(7000), debt_balances={"UZS": 7000.0})
    db.add(cust)
    db.flush()
    s = Sale(number=f"ST316-{next(_seq)}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             total_amount=Decimal(7000), paid_amount=Decimal(0), paid_cash=Decimal(0), payment_type=PaymentType.debt,
             status=SaleStatus.completed, created_at=_now(), customer_id=cust.id,
             debt_due_date=local_today() - timedelta(days=3))
    db.add(s)
    db.flush()
    return s


def test_overdue_debt_alert_uses_admin_bot_token(db, mk, sch, monkeypatch):
    c, b, w, u = mk.tenant()
    c.tg_bot_token = None                       # mijoz boti yo'q
    u.tg_chat_id = "ow1"
    bot = _bot(db, c)
    _overdue_sale(db, u, c, w)
    # mijoz boti bor, lekin admin bot yo'q korxona: Telegram ketmaydi
    c2, b2, w2, u2 = mk.tenant()
    c2.tg_bot_token = "customer-bot-token"
    u2.tg_chat_id = "ow2"
    _overdue_sale(db, u2, c2, w2)
    sent = []

    async def fake(token, chat_id, text, parse_mode="HTML", errors=None):
        sent.append((token, chat_id, text))
        return True

    monkeypatch.setattr(sched, "send_tg_msg_async", fake)
    asyncio.run(sched.notify_managers_overdue())
    assert [(s[0], s[1]) for s in sent] == [(bot.bot_token, "ow1")]
    assert "Muddati o'tgan qarzlar" in sent[0][2] and "7,000" in sent[0][2]


def test_overdue_debt_alert_respects_recipients_setting(db, three, sch, monkeypatch):
    t = three
    t['ca'].daily_report_recipients = "owners"
    _overdue_sale(db, t['admin'], t['ca'], t['ws'][0])
    sent = []

    async def fake(token, chat_id, text, parse_mode="HTML", errors=None):
        sent.append(chat_id)
        return True

    monkeypatch.setattr(sched, "send_tg_msg_async", fake)
    asyncio.run(sched.notify_managers_overdue())
    assert sent == [t['director'].tg_chat_id]               # mezon 8 (qarz eslatmasi ham)


def test_send_tg_msg_async_logs_response_text_on_403(monkeypatch, caplog):
    class Resp:
        status_code = 403
        text = '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return Resp()

    monkeypatch.setattr(sched.httpx, "AsyncClient", FakeClient)
    errs = []
    with caplog.at_level("ERROR"):
        assert asyncio.run(sched.send_tg_msg_async("t", "1", "x", errors=errs)) is False
    assert "403" in caplog.text and "bot was blocked" in caplog.text
    assert errs and "bot was blocked" in errs[0]


def _capture_chunks(monkeypatch):
    sent = []

    async def fake(token, chat_id, text, parse_mode="HTML", errors=None):
        sent.append((token, chat_id, text))
        return True

    monkeypatch.setattr(sched, "send_tg_chunks", fake)
    return sent


def test_daily_report_leaders_get_company_report_and_owners_only_setting(db, three, sch, monkeypatch):
    t = three
    sent = _capture_chunks(monkeypatch)
    _sale(db, t['admin'], t['ca'], t['ws'][0], 1000)
    _sale(db, t['admin'], t['ca'], t['ws'][1], 2000)
    ok, detail = asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert ok and {s[1] for s in sent} == {t['admin'].tg_chat_id, t['director'].tg_chat_id}
    assert all("FILIALLAR KESIMI" in s[2] and "MOLIYAVIY HOLAT" in s[2] for s in sent)
    assert all(s[0] == t['bot'].bot_token for s in sent)

    # report_by_branch o'chiq -> filiallar bo'limi chiqmaydi
    sent.clear()
    t['bot'].report_by_branch = False
    db.flush()
    asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert sent and all("FILIALLAR KESIMI" not in s[2] for s in sent)

    # daily_report_recipients = owners -> faqat direktor (mezon 8)
    sent.clear()
    t['ca'].daily_report_recipients = "owners"
    db.flush()
    asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert {s[1] for s in sent} == {t['director'].tg_chat_id}


def test_daily_report_branch_manager_gets_own_branch_without_debt(db, three, sch, monkeypatch):
    t = three
    sent = _capture_chunks(monkeypatch)
    t['ca'].daily_report_recipients = "all_managers"
    _sale(db, t['admin'], t['ca'], t['ws'][0], 1000)
    _sale(db, t['admin'], t['ca'], t['ws'][1], 2000)
    _sale(db, t['admin'], t['ca'], t['ws'][1], 3000)
    db.flush()
    ok, detail = asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert ok and "5/5" in detail                                  # 2 rahbar + 3 menejer
    by_chat = {s[1]: s[2] for s in sent}
    assert set(by_chat) == {t['admin'].tg_chat_id, t['director'].tg_chat_id} | {m.tg_chat_id for m in t['mgrs']}
    mgr_text = by_chat[t['mgrs'][1].tg_chat_id]                    # Yunusobod: 2 ta sotuv, 5 000
    assert "MOLIYAVIY HOLAT" not in mgr_text and "FILIALLAR KESIMI" not in mgr_text
    assert "Tranzaksiyalar soni: <b>2 ta</b>" in mgr_text and "5,000 so'm" in mgr_text
    assert "Tranzaksiyalar soni: <b>3 ta</b>" in by_chat[t['admin'].tg_chat_id]
    # notify_branch_managers o'chiq -> menejerlarga hisobot ketmaydi
    sent.clear()
    t['bot'].notify_branch_managers = False
    db.flush()
    asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert {s[1] for s in sent} == {t['admin'].tg_chat_id, t['director'].tg_chat_id}


def test_daily_report_default_setting_does_not_message_managers(db, three, sch, monkeypatch):
    t = three
    sent = _capture_chunks(monkeypatch)
    asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert not ({s[1] for s in sent} & {m.tg_chat_id for m in t['mgrs']})


def test_daily_report_isolated_between_companies(db, mk, three, sch, monkeypatch):
    t = three
    sent = _capture_chunks(monkeypatch)
    cb, bb, wb, ub = mk.tenant()
    ub.tg_chat_id = "b-admin"
    bot_b = _bot(db, cb)
    _sale(db, ub, cb, wb, 777)
    asyncio.run(sched._send_company_tg_report(db, t['ca'], t['bot']))
    assert "b-admin" not in {s[1] for s in sent}
    assert not any("777" in s[2] for s in sent)
    sent.clear()
    asyncio.run(sched._send_company_tg_report(db, cb, bot_b))
    assert {s[1] for s in sent} == {"b-admin"} and "777" in sent[0][2]


def test_expiring_products_branch_manager_gets_only_own_branch(db, three, sch, monkeypatch):
    from app.models.batch import Batch
    from app.models.category import Category
    t = three
    sent = []

    async def fake(token, chat_id, text, parse_mode="HTML", errors=None):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(sched, "send_tg_chunks", fake)
    t['ca'].daily_report_recipients = "all_managers"
    t['bot'].notify_expired_products = True
    t['bot'].expired_days_before = 10
    cat = Category(name="Sut", company_id=t['ca'].id, is_perishable=True)
    db.add(cat)
    db.flush()
    for i, w in enumerate(t['ws'][:2]):
        p = _product(db, t['ca'], f"Sut {i}", category_id=cat.id)
        db.add(Batch(product_id=p.id, warehouse_id=w.id, company_id=t['ca'].id, lot_number=f"L{i}",
                     expiry_date=datetime.now() + timedelta(days=2), initial_quantity=Decimal(1),
                     quantity=Decimal(1), purchase_price=Decimal(1)))
    db.flush()
    asyncio.run(sched.notify_expiring_products())
    by_chat = dict(sent)
    admin_text = by_chat[t['admin'].tg_chat_id]
    assert "Filial: Chilonzor" in admin_text and "Filial: Yunusobod" in admin_text
    m0 = by_chat[t['mgrs'][0].tg_chat_id]
    assert "Filial: Chilonzor" in m0 and "Yunusobod" not in m0
    assert t['mgrs'][2].tg_chat_id not in by_chat              # Sergeli'da partiya yo'q


# ─── 10. Bot sozlamalari API ─────────────────────────────────────────────────

def test_bot_settings_put_is_partial_and_new_fields(client, db, three):
    t = three
    bot = t['bot']
    bot.notify_scheduled = True
    bot.scheduled_time = "19:30"
    bot.expired_days_before = 14
    db.flush()
    url = f"/api/companies/{t['ca'].id}/admin-bot/settings"
    r = client.login(t['admin']).put(url, json={"notify_branch_managers": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['notify_branch_managers'] is False and body['report_by_branch'] is True
    db.refresh(bot)
    assert bot.scheduled_time == "19:30" and bot.expired_days_before == 14 and bot.notify_scheduled is True
    # eski frontend: hamma eski maydonni yuboradi — yangilari o'zgarmaydi
    r = client.login(t['admin']).put(url, json={
        "notify_instant_sales": False, "notify_instant_finance": True, "notify_scheduled": False,
        "scheduled_time": "21:00", "notify_expired_products": True, "expired_days_before": 7})
    assert r.status_code == 200
    db.refresh(bot)
    assert bot.notify_instant_sales is False and bot.scheduled_time == "21:00"
    assert bot.notify_branch_managers is False and bot.report_by_branch is True
    r = client.login(t['admin']).put(url, json={"report_by_branch": False})
    assert r.status_code == 200 and r.json()['report_by_branch'] is False


def test_bot_settings_foreign_company_forbidden(client, db, mk, three):
    t = three
    cb, bb, wb, ub = mk.tenant()
    r = client.login(ub).put(f"/api/companies/{t['ca'].id}/admin-bot/settings", json={"report_by_branch": False})
    assert r.status_code == 403
    db.refresh(t['bot'])
    assert t['bot'].report_by_branch is True


def test_bot_settings_schema_defaults_are_none():
    s = CompanyBotSettingsUpdate()
    assert s.model_dump(exclude_unset=True) == {}
    assert CompanyBotSettingsUpdate(notify_branch_managers=False).model_dump(exclude_unset=True) == {
        "notify_branch_managers": False}


def test_company_daily_report_recipients_validated(client, db, three):
    t = three
    url = f"/api/companies/{t['ca'].id}"
    c = client.login(t['admin'])
    assert c.put(url, json={"daily_report_recipients": "hamma"}).status_code == 422
    for v in ("owners", "all_managers", "owners_and_admins"):
        r = c.put(url, json={"daily_report_recipients": v})
        assert r.status_code == 200, r.text
        assert r.json()['daily_report_recipients'] == v


def test_company_bot_columns_default_true(db, mk):
    c = mk.company()
    bot = _bot(db, c)
    db.refresh(bot)
    assert bot.notify_branch_managers is True and bot.report_by_branch is True


# ─── 11. Migratsiya va frontend ──────────────────────────────────────────────

def test_migration_adds_two_boolean_columns():
    import py_compile
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_16_company_bots_branch_notify.py')
    py_compile.compile(path, doraise=True)
    src = open(path, encoding='utf-8').read()
    assert "revision = 't3_16'" in src and "down_revision = 't3_15'" in src
    for col in ("notify_branch_managers", "report_by_branch"):
        assert f"'{col}'" in src
    assert src.count("server_default=sa.true()") == 2 and src.count("nullable=False") == 2


def test_frontend_new_keys_in_all_languages_and_used():
    with open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.16.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {"uz", "ru", "en"}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    assert all(v.strip() for lang in data.values() for v in lang.values())
    with open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'Settings.jsx'), encoding='utf-8') as f:
        jsx = f.read()
    for key in data['uz']:
        assert f"'{key}'" in jsx, key
    # kalitlar lug'atlarga birlashtirilgan (pending fayl o'chirilgan) va takrorlanmagan
    for lang in ("uz", "ru", "en"):
        with open(os.path.join(ROOT, 'frontend', 'src', 'i18n', f'{lang}.js'), encoding='utf-8') as f:
            dict_src = f.read()
        for key in data[lang]:
            assert dict_src.count(f"'{key}':") == 1, (lang, key)
    for field in ("notify_branch_managers", "report_by_branch", "daily_report_recipients"):
        assert field in jsx
    for mode in ("owners_and_admins", "owners", "all_managers"):
        assert f'value="{mode}"' in jsx
