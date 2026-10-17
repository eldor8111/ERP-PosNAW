"""T2.11 — moliya va filial oqimlari uchun avtomatik testlar.

Qamrov: kassa yopilishidagi kamomad (difference_summary JSON), `branch_day_summary` (filial kesimi,
Filialsiz, korxona izolyatsiyasi), kunlik hisobotdagi `[ FILIALLAR KESIMI ]` bo'limi (2+ filial,
bitta filial, 10 dan ortiq filial, HTML escape), 1C eksport (eski 9 ustun joyida, yangilari oxirida,
branch_id filtri, XML, qaytarishlar manfiy) va moliya tranzaksiyalarining filial/korxona filtri.
"""
import csv
import io
import itertools
import json
from datetime import datetime
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.shift import Shift
from app.models.user import UserRole
from app.services.ai_service import MAX_BRANCH_LINES, build_daily_report
from app.services.branch_daily_summary import UNASSIGNED_LABEL, branch_day_summary
from app.utils.report_utils import LOCAL_TZ, local_today

_seq = itertools.count(1)
PERIOD = {'date_from': '2020-01-01', 'date_to': '2099-12-31'}
OLD_HEADER = ["Raqam", "Sana", "Kassir", "Jami summa", "Chegirma", "To'lov turi", "Valyuta", "Kurs", "Turi"]


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _now():
    """Toshkent devor vaqti (hisobotlar kun chegarasi shu bo'yicha)."""
    return datetime.now(LOCAL_TZ)


def _sale(db, user, company, warehouse, amount, refund=False):
    n = next(_seq)
    s = Sale(number=f"{'R' if refund else 'S'}T211-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), paid_cash=Decimal(amount), payment_type=PaymentType.cash,
             status=SaleStatus.refunded if refund else SaleStatus.completed, created_at=_now())
    db.add(s)
    db.flush()
    return s


def _expense(db, company, branch, amount, voided=False):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.company_id == company.id).first()
    if cat is None:
        cat = ExpenseCategory(name="Kommunal", company_id=company.id)
        db.add(cat)
        db.flush()
    e = Expense(branch_id=branch.id, category_id=cat.id, amount=Decimal(amount), company_id=company.id,
                created_at=_now(), voided_at=_now() if voided else None)
    db.add(e)
    db.flush()
    return e


def _closed_shift(db, user, company, branch):
    s = Shift(cashier_id=user.id, branch_id=branch.id, company_id=company.id, status="closed",
              opened_at=_now(), closed_at=_now())
    db.add(s)
    db.flush()
    return s


def _wallet(db, company, branch, is_open=False, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(0), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=True, is_open=is_open)
    db.add(w)
    db.flush()
    return w


def _closed_session(db, company, wallet, branch, diff):
    """Yopilgan kassa sessiyasi (kamomad `diff` JSON bilan)."""
    s = KassaSession(wallet_id=wallet.id, company_id=company.id, branch_id=branch.id if branch else None,
                     status="closed", opened_at=_now(), closed_at=_now(), difference_summary=diff)
    db.add(s)
    db.flush()
    return s


def _jwt(user):
    return {'Authorization': 'Bearer ' + create_access_token(
        {'sub': str(user.id), 'company_id': user.company_id, 'role': user.role.value})}


@pytest.fixture
def two(db, mk):
    """A korxona: ikki faol filial (Yunusobod, Chilonzor), omborlar, admin. B korxona: o'z filiali."""
    ca = mk.company()
    b1 = mk.branch(ca, name="Yunusobod")
    b2 = mk.branch(ca, name="Chilonzor")
    w1 = mk.warehouse(ca, b1)
    w2 = mk.warehouse(ca, b2)
    admin = mk.user(ca, role=UserRole.admin)
    cb, bb, whb, ub = mk.tenant()
    return dict(ca=ca, b1=b1, b2=b2, w1=w1, w2=w2, admin=admin, cb=cb, bb=bb, whb=whb, ub=ub)


def _seed_day(db, t):
    """Yunusobod: sotuv 5000 (+qaytarish 1000), xarajat 700, 1 smena, kamomad 300.
    Chilonzor: sotuv 2000, xarajat 100. B korxonada alohida yozuvlar (A hisobotiga tushmasligi kerak)."""
    _sale(db, t['admin'], t['ca'], t['w1'], 5000)
    _sale(db, t['admin'], t['ca'], t['w1'], 1000, refund=True)
    _sale(db, t['admin'], t['ca'], t['w2'], 2000)
    _expense(db, t['ca'], t['b1'], 700)
    _expense(db, t['ca'], t['b2'], 100)
    _expense(db, t['ca'], t['b1'], 99999, voided=True)             # bekor qilingan — sanalmaydi
    _closed_shift(db, t['admin'], t['ca'], t['b1'])
    _closed_session(db, t['ca'], _wallet(db, t['ca'], t['b1']), t['b1'], {'cash': {'UZS': 300.0}})
    # B korxona
    _sale(db, t['ub'], t['cb'], t['whb'], 777777)
    _expense(db, t['cb'], t['bb'], 555555)
    _closed_shift(db, t['ub'], t['cb'], t['bb'])
    _closed_session(db, t['cb'], _wallet(db, t['cb'], t['bb']), t['bb'], {'cash': {'UZS': 424242.0}})


# ── 1. close_kassa: kamomad difference_summary ga JSON sifatida yoziladi ─────

def test_close_kassa_records_shortage_and_difference_summary(client, db, mk):
    c, b, wh, admin = mk.tenant()
    k = _wallet(db, c, b)
    cl = client.login(admin)
    assert cl.post(f'/api/kassa/{k.id}/open', json={'opening_balance': 100000}).status_code == 200
    r = cl.post(f'/api/kassa/{k.id}/close', json={'actual_amounts': {'cash': {'UZS': 95000}}})
    assert r.status_code == 200, r.text
    assert r.json()['difference'] == {'cash': {'UZS': 5000.0}}

    db.expire_all()
    sess = db.query(KassaSession).filter(KassaSession.wallet_id == k.id).one()
    assert sess.status == 'closed'
    assert sess.difference_summary == {'cash': {'UZS': 5000.0}}
    json.dumps(sess.difference_summary)                                    # Decimal emas — JSON'ga o'tadi
    assert isinstance(sess.difference_summary['cash']['UZS'], float)
    assert sess.expected_summary['cash'] == [{'currency': 'UZS', 'value': 100000.0}]

    adj = db.query(KassaMovement).filter(KassaMovement.wallet_id == k.id,
                                         KassaMovement.reference_type == 'closing_adjustment').one()
    assert adj.direction == 'out' and Decimal(str(adj.amount)) == 5000
    db.refresh(k)
    assert Decimal(str(k.balance)) == 0                                    # 100000 - 95000 inkasso - 5000 kamomad


def test_close_kassa_foreign_wallet_is_404(client, db, mk):
    c, b, wh, admin = mk.tenant()
    c2, b2, _, _u2 = mk.tenant()
    foreign = _wallet(db, c2, b2, is_open=True)
    r = client.login(admin).post(f'/api/kassa/{foreign.id}/close', json={'actual_amounts': {'cash': {'UZS': 0}}})
    assert r.status_code == 404


# ── 2. branch_day_summary ────────────────────────────────────────────────────

def test_branch_day_summary_per_branch(db, two):
    _seed_day(db, two)
    rows = {r['name']: r for r in branch_day_summary(db, two['ca'].id, local_today())}
    assert set(rows) == {"Yunusobod", "Chilonzor"}                          # B korxona filiali ko'rinmaydi
    y, ch = rows["Yunusobod"], rows["Chilonzor"]
    assert y['net'] == 4000 and y['expense'] == 700                         # 5000 - 1000 qaytarish; void yo'q
    assert y['shifts_closed'] == 1 and y['shortage'] == 300 and y['surplus'] == 0
    assert ch['net'] == 2000 and ch['expense'] == 100
    assert ch['shifts_closed'] == 0 and ch['shortage'] == 0


def test_branch_day_summary_unassigned_and_surplus(db, two):
    _sale(db, two['admin'], two['ca'], None, 900)                          # omborsiz sotuv -> Filialsiz
    _closed_session(db, two['ca'], _wallet(db, two['ca'], two['b2']), two['b2'], {'cash': {'UZS': -250.0}})
    rows = {r['name']: r for r in branch_day_summary(db, two['ca'].id, local_today())}
    assert rows[UNASSIGNED_LABEL]['net'] == 900 and rows[UNASSIGNED_LABEL]['branch_id'] is None
    assert rows["Chilonzor"]['surplus'] == 250 and rows["Chilonzor"]['shortage'] == 0


def test_branch_day_summary_other_day_is_empty(db, two):
    _seed_day(db, two)
    from datetime import timedelta
    rows = branch_day_summary(db, two['ca'].id, local_today() - timedelta(days=3))
    assert all(r['net'] == 0 and r['expense'] == 0 and r['shifts_closed'] == 0 for r in rows)


def test_branch_day_summary_company_isolation(db, two):
    _seed_day(db, two)
    rows = branch_day_summary(db, two['cb'].id, local_today())
    assert [r['name'] for r in rows] == [two['bb'].name]
    assert rows[0]['net'] == 777777 and rows[0]['expense'] == 555555 and rows[0]['shortage'] == 424242


# ── 3. Kunlik hisobot: [ FILIALLAR KESIMI ] ──────────────────────────────────

def test_daily_report_has_branch_breakdown(db, two):
    _seed_day(db, two)
    text = build_daily_report(db, two['ca'].id, two['ca'].name)
    assert "[ FILIALLAR KESIMI ]" in text
    assert "Yunusobod" in text and "Chilonzor" in text
    assert "4,000 so'm" in text and "2,000 so'm" in text                  # tushum
    assert "700 so'm" in text and "100 so'm" in text                      # xarajat
    assert "Kassa kamomadi" in text and "300 so'm" in text
    assert "777,777" not in text and "555,555" not in text                # B korxona ma'lumoti yo'q
    assert len(text) < 4096


def test_daily_report_single_branch_has_no_section(db, mk):
    c, b, wh, u = mk.tenant()
    _sale(db, u, c, wh, 1500)
    text = build_daily_report(db, c.id, c.name)
    assert "FILIALLAR" not in text and "1,500 so'm" in text


def test_daily_report_escapes_branch_names(db, two):
    two['b1'].name = "<b>Bad</b> & Co"
    db.flush()
    text = build_daily_report(db, two['ca'].id, two['ca'].name)
    assert "&lt;b&gt;Bad&lt;/b&gt; &amp; Co" in text and "<b>Bad</b> & Co" not in text


def test_daily_report_truncates_many_branches(db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    total = MAX_BRANCH_LINES + 3
    for i in range(total):
        mk.branch(c, name=f"Filial-{i:02d}")
    text = build_daily_report(db, c.id, c.name)
    assert text.count("🏬") == MAX_BRANCH_LINES
    assert "…yana 3 ta filial" in text
    assert len(text) < 4096


# ── 4. 1C eksport ────────────────────────────────────────────────────────────

def _csv(r):
    return list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))


def test_1c_csv_old_columns_intact_new_at_end(client, db, two):
    _sale(db, two['admin'], two['ca'], two['w1'], 5000)
    r = client.get('/api/reports/1c-export', params={**PERIOD, 'format': 'csv'}, headers=_jwt(two['admin']))
    assert r.status_code == 200, r.text
    rows = _csv(r)
    assert rows[0][:9] == OLD_HEADER                                       # eski 9 ustun joyida
    assert rows[0][9:] and "Ombor" in rows[0][9:] and "Filial" in rows[0][9:]
    fi, oi = rows[0].index("Filial"), rows[0].index("Ombor")
    assert rows[1][fi] == "Yunusobod" and rows[1][oi] == two['w1'].name
    assert rows[1][3] == "5000.00"


def test_1c_branch_filter_only_that_branch(client, db, two):
    _sale(db, two['admin'], two['ca'], two['w1'], 5000)
    _sale(db, two['admin'], two['ca'], two['w2'], 2000)
    _sale(db, two['ub'], two['cb'], two['whb'], 123)                       # B korxona
    h = _jwt(two['admin'])
    rows = _csv(client.get('/api/reports/1c-export', params={**PERIOD, 'branch_id': two['b2'].id}, headers=h))
    assert [x[3] for x in rows[1:]] == ["2000.00"]
    allrows = _csv(client.get('/api/reports/1c-export', params=PERIOD, headers=h))
    assert sorted(x[3] for x in allrows[1:]) == ["2000.00", "5000.00"]     # 123 yo'q


def test_1c_xml_has_branch_attribute(client, db, two):
    _sale(db, two['admin'], two['ca'], two['w1'], 5000)
    r = client.get('/api/reports/1c-export', params={**PERIOD, 'format': 'xml'}, headers=_jwt(two['admin']))
    assert r.status_code == 200
    body = r.content.decode()
    assert 'branch="Yunusobod"' in body and f'warehouse="{two["w1"].name}"' in body
    assert body.index('type="sale"') < body.index('branch=')              # eski atributlar oldin


def test_1c_include_returns_negative(client, db, two):
    _sale(db, two['admin'], two['ca'], two['w1'], 5000)
    _sale(db, two['admin'], two['ca'], two['w1'], 1000, refund=True)
    h = _jwt(two['admin'])
    plain = _csv(client.get('/api/reports/1c-export', params=PERIOD, headers=h))
    assert [x[3] for x in plain[1:]] == ["5000.00"]
    full = _csv(client.get('/api/reports/1c-export', params={**PERIOD, 'include_returns': 'true'}, headers=h))
    assert sorted(x[3] for x in full[1:]) == ["-1000.00", "5000.00"]


# ── 5. Moliya tranzaksiyalari: filial va korxona filtri ──────────────────────

def _tx(db, company, branch, amount, tx_type="income"):
    t = Transaction(company_id=company.id, branch_id=branch.id, type=tx_type, amount=Decimal(amount),
                    reference_type="manual", description="t211")
    db.add(t)
    db.flush()
    return t


def test_finance_transactions_branch_filter_and_isolation(client, db, two):
    _tx(db, two['ca'], two['b1'], 111)
    _tx(db, two['ca'], two['b2'], 222)
    _tx(db, two['cb'], two['bb'], 999)
    cl = client.login(two['admin'])
    allr = cl.get('/api/finance/transactions')
    assert allr.status_code == 200, allr.text
    assert sorted(float(x['amount']) for x in allr.json()) == [111.0, 222.0]       # B yozuvi ko'rinmaydi
    one = cl.get('/api/finance/transactions', params={'branch_id': two['b2'].id})
    assert [float(x['amount']) for x in one.json()] == [222.0]
    foreign = cl.get('/api/finance/transactions', params={'branch_id': two['bb'].id})
    assert foreign.status_code in (403, 404) or foreign.json() == []
