"""T2.10 — Scheduler kunlik hisobot vaqti va Telegram xabar xavfsizligi.

Qamrov: `_due` oynasi (daqiqa tengligi yo'q), `claim_run` (unikal registr, failed/running qayta olish),
`send_tg_msg_async` (400 parse -> teglarsiz, 429 -> retry_after, xato matni qayd etiladi),
`telegram_text` (esc/split/strip_tags), muddati tugayotgan tovarlar (ombor bo'yicha guruhlash, 300 partiya),
kunlik hisobot (oyna ichida bir marta, restartdan keyin ham, xatoda failed + qayta urinish),
09:00/10:00/11:00/03:00/00:05 vazifalari oynada, o'lik kod yo'qligi, admin bot bo'laklash.
"""
import asyncio
import itertools
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

import app.database as app_database
import app.services.scheduler as sched
from app.admin_tg_bot.models import CompanyBot
from app.models.batch import Batch
from app.models.category import Category
from app.models.product import Product
from app.models.scheduler_run import SchedulerRun
from app.models.user import UserRole
from app.utils.report_utils import LOCAL_TZ
from app.utils.telegram_text import esc, split_html_message, strip_tags

_seq = itertools.count(1)
TODAY = date(2026, 10, 16)


def _at(h, m, s=0, d=TODAY):
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=LOCAL_TZ)


class _CommitOnClose(Session):
    """Test ulanishi bitta (SAVEPOINT lar ichma-ich), productionda esa har sessiya alohida ulanish.
    Sessiya yopilganda commit qilamiz, shunda registr (alohida sessiya) yozuvi tashqi sessiyaning
    rollback'i bilan yo'qolmaydi — productiondagi mustaqil ulanishlar xulqini taqlid qiladi."""

    def close(self):
        try:
            self.commit()
        except Exception:
            pass
        super().close()


@pytest.fixture
def sch(db, monkeypatch):
    """scheduler `SessionLocal` ni nom bo'yicha import qiladi — test ulanishiga yo'naltiramiz"""
    conn = app_database.SessionLocal.kw['bind']
    factory = sessionmaker(bind=conn, class_=_CommitOnClose, join_transaction_mode='create_savepoint',
                           expire_on_commit=False)
    monkeypatch.setattr(sched, 'SessionLocal', factory)
    return sched


def _runs(db, job=None):
    db.expire_all()
    q = db.query(SchedulerRun)
    if job:
        q = q.filter(SchedulerRun.job == job)
    return q.order_by(SchedulerRun.id).all()


# ─── 1. _due va _parse_hhmm ───

def test_due_window_boundaries():
    assert sched._due(_at(20, 0), 20, 0, 180) is True            # aynan vaqtida
    assert sched._due(_at(19, 59, 59), 20, 0, 180) is False      # hali erta
    assert sched._due(_at(20, 1), 20, 0, 180) is True            # daqiqa tushib qolgan — oynada
    assert sched._due(_at(20, 30), 20, 0, 180) is True
    assert sched._due(_at(22, 59, 59), 20, 0, 180) is True
    assert sched._due(_at(23, 0), 20, 0, 180) is False           # oyna tugadi
    assert sched._due(_at(0, 5), 0, 5, 1200) is True
    assert sched._due(_at(0, 4), 0, 5, 1200) is False
    assert sched._due(_at(20, 4, 59), 0, 5, 1200) is True
    assert sched._due(_at(20, 5), 0, 5, 1200) is False


def test_parse_hhmm_tolerates_loose_format():
    assert sched._parse_hhmm("20:00", (1, 1)) == (20, 0)
    assert sched._parse_hhmm("9:5", (1, 1)) == (9, 5)
    assert sched._parse_hhmm("25:00", (20, 0)) == (20, 0)
    assert sched._parse_hhmm("abc", (20, 0)) == (20, 0)
    assert sched._parse_hhmm(None, (17, 30)) == (17, 30)


# ─── 2. claim_run ───

def test_claim_run_unique_and_parallel_sessions(db):
    s2 = app_database.SessionLocal()
    try:
        assert sched.claim_run(db, 'j', 'global', TODAY) is True
        assert sched.claim_run(s2, 'j', 'global', TODAY) is False        # ikkinchi worker yutolmaydi
        assert sched.claim_run(db, 'j', 'company:1', TODAY) is True      # boshqa scope
        assert sched.claim_run(db, 'j', 'global', TODAY + timedelta(days=1)) is True   # boshqa kun
    finally:
        s2.close()
    assert len(_runs(db, 'j')) == 3


def test_claim_run_done_is_never_reclaimed(db):
    now = datetime(2026, 10, 16, 15, 0)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=now)
    sched.finish_run(db, 'j', 'global', TODAY, True, None, now=now)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=now + timedelta(hours=5)) is False
    assert _runs(db)[0].status == 'done'


def test_claim_run_failed_retried_with_delay_and_attempt_cap(db):
    t0 = datetime(2026, 10, 16, 15, 0)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t0)
    sched.finish_run(db, 'j', 'global', TODAY, False, 'HTTP 400: bad', now=t0)
    row = _runs(db)[0]
    assert row.status == 'failed' and 'HTTP 400' in row.detail and row.attempts == 1
    # kutish muddati o'tmagan
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t0 + timedelta(minutes=1)) is False
    # kutishdan keyin qayta olinadi
    t1 = t0 + timedelta(minutes=6)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t1) is True
    assert _runs(db)[0].attempts == 2 and _runs(db)[0].status == 'running'
    sched.finish_run(db, 'j', 'global', TODAY, False, 'x', now=t1)
    t2 = t1 + timedelta(minutes=6)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t2) is True      # 3-urinish
    sched.finish_run(db, 'j', 'global', TODAY, False, 'x', now=t2)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t2 + timedelta(minutes=30)) is False   # limit
    assert _runs(db)[0].attempts == 3


def test_claim_run_stale_running_reclaimed_fresh_not(db):
    t0 = datetime(2026, 10, 16, 15, 0)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t0)
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t0 + timedelta(minutes=5)) is False    # hali ishlayapti
    assert sched.claim_run(db, 'j', 'global', TODAY, now=t0 + timedelta(minutes=11)) is True    # worker o'lgan
    assert _runs(db)[0].attempts == 2


def test_claim_run_max_attempts_one_never_reclaims(db):
    t0 = datetime(2026, 10, 16, 15, 0)
    assert sched.claim_run(db, 'j', 'global', TODAY, max_attempts=1, now=t0)
    assert sched.claim_run(db, 'j', 'global', TODAY, max_attempts=1, now=t0 + timedelta(hours=1)) is False


def test_purge_old_runs(db, sch, monkeypatch):
    monkeypatch.setattr(sched, 'local_today', lambda: TODAY)
    assert sched.claim_run(db, 'old', 'global', TODAY - timedelta(days=31))
    assert sched.claim_run(db, 'new', 'global', TODAY - timedelta(days=5))
    sched.purge_old_runs()
    assert [r.job for r in _runs(db)] == ['new']


# ─── 3. telegram_text ───

def test_esc():
    assert esc('Kabel <USB-C> 1m & "x"') == 'Kabel &lt;USB-C&gt; 1m &amp; "x"'
    assert esc(None) == ''
    assert esc(5) == '5'


def test_strip_tags_keeps_plain_text_and_unescapes():
    assert strip_tags('<b>Salom</b> <i>dunyo</i> &lt;USB-C&gt; &amp; <a href="x">link</a>') == 'Salom dunyo <USB-C> & link'
    assert strip_tags('Kabel <USB-C> 1m') == 'Kabel <USB-C> 1m'       # noma'lum teg yo'qolmaydi
    assert strip_tags('') == ''


def test_split_short_and_empty():
    assert split_html_message('') == []
    assert split_html_message('salom') == ['salom']


def test_split_on_line_boundaries_and_limit():
    lines = [f'📦 <b>Mahsulot {i}</b> — miqdor {i}' for i in range(500)]
    chunks = split_html_message('\n'.join(lines), limit=3800)
    assert len(chunks) > 1
    assert all(len(c) <= 3800 for c in chunks)
    assert '\n'.join(chunks).split('\n') == lines                    # qatorlar buzilmagan, tartib saqlangan
    assert all(c.count('<b>') == c.count('</b>') for c in chunks)


def test_split_limit_is_capped_to_4096():
    chunks = split_html_message('a\n' * 6000, limit=99999)
    assert all(len(c) <= 4096 for c in chunks)


def test_split_single_long_line_hard_split_keeps_tags_balanced():
    long_line = '<b>' + ('x' * 9000) + '</b>'
    chunks = split_html_message(long_line, limit=3800)
    assert len(chunks) >= 3 and all(len(c) <= 3800 for c in chunks)
    for c in chunks:
        assert c.count('<b>') == c.count('</b>')
    assert strip_tags(''.join(chunks)) == 'x' * 9000


def test_split_hard_split_does_not_cut_entities():
    line = '&amp;' * 2000
    chunks = split_html_message(line, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert ''.join(chunks) == line


# ─── 4. send_tg_msg_async (httpx mock) ───

class _Resp:
    def __init__(self, status, text='', js=None):
        self.status_code = status
        self.text = text
        self._js = js

    def json(self):
        if self._js is None:
            raise ValueError
        return self._js


def _fake_client(monkeypatch, responses):
    """httpx.AsyncClient o'rniga; har post() navbatdagi javobni (yoki istisnoni) qaytaradi."""
    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append(json)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

    monkeypatch.setattr(sched.httpx, 'AsyncClient', FakeClient)
    return calls


def test_send_ok_single_call(monkeypatch):
    calls = _fake_client(monkeypatch, [_Resp(200)])
    assert asyncio.run(sched.send_tg_msg_async('t', '1', '<b>x</b>')) is True
    assert calls[0]['parse_mode'] == 'HTML'


def test_send_400_parse_entities_retries_without_tags(monkeypatch):
    calls = _fake_client(monkeypatch, [
        _Resp(400, '{"ok":false,"description":"Bad Request: can\'t parse entities: Unsupported start tag"}'),
        _Resp(200),
    ])
    errs = []
    ok = asyncio.run(sched.send_tg_msg_async('t', '1', '<b>Kabel</b> <USB-C> 1m', errors=errs))
    assert ok is True and errs == []
    assert len(calls) == 2
    assert 'parse_mode' not in calls[1] and calls[1]['text'] == 'Kabel <USB-C> 1m'


def test_send_400_other_error_recorded_with_response_text(monkeypatch):
    _fake_client(monkeypatch, [_Resp(400, 'Bad Request: chat not found')])
    errs = []
    assert asyncio.run(sched.send_tg_msg_async('t', '1', 'x', errors=errs)) is False
    assert len(errs) == 1 and 'HTTP 400' in errs[0] and 'chat not found' in errs[0]


def test_send_429_waits_retry_after_once(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(sched.asyncio, 'sleep', fake_sleep)
    calls = _fake_client(monkeypatch, [_Resp(429, 'Too Many Requests', {'parameters': {'retry_after': 7}}), _Resp(200)])
    assert asyncio.run(sched.send_tg_msg_async('t', '1', 'x')) is True
    assert slept == [7] and len(calls) == 2


def test_send_429_twice_fails(monkeypatch):
    async def fake_sleep(s):
        pass

    monkeypatch.setattr(sched.asyncio, 'sleep', fake_sleep)
    _fake_client(monkeypatch, [_Resp(429, 'x', {'parameters': {'retry_after': 1}}), _Resp(429, 'again', {'parameters': {'retry_after': 1}})])
    errs = []
    assert asyncio.run(sched.send_tg_msg_async('t', '1', 'x', errors=errs)) is False
    assert 'HTTP 429' in errs[0]


def test_send_network_error_recorded(monkeypatch):
    _fake_client(monkeypatch, [RuntimeError('connection reset')])
    errs = []
    assert asyncio.run(sched.send_tg_msg_async('t', '1', 'x', errors=errs)) is False
    assert 'connection reset' in errs[0]


def test_send_chunks_splits_long_text(monkeypatch):
    sent = []

    async def fake(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append(text)
        return True

    monkeypatch.setattr(sched, 'send_tg_msg_async', fake)
    text = '\n'.join(f'📦 <b>Tovar {i}</b>' for i in range(2000))
    assert asyncio.run(sched.send_tg_chunks('t', '1', text)) is True
    assert len(sent) > 1 and all(len(c) <= 4096 for c in sent)


def test_send_chunks_reports_failure(monkeypatch):
    async def fake(token, chat_id, text, parse_mode='HTML', errors=None):
        errors.append('HTTP 400: boom')
        return False

    monkeypatch.setattr(sched, 'send_tg_msg_async', fake)
    errs = []
    assert asyncio.run(sched.send_tg_chunks('t', '1', 'x', errors=errs)) is False
    assert errs == ['HTTP 400: boom']


# ─── yordamchilar: korxona + admin bot ───

def _company_with_bot(db, mk, scheduled_time='20:00', **bot_kw):
    c, b, w, u = mk.tenant()
    c.daily_report_enabled = False          # FCM bu testlarda shovqin bo'lmasin
    u.tg_chat_id = f'chat{next(_seq)}'
    bot = CompanyBot(company_id=c.id, bot_token=f'tok-{next(_seq)}', bot_type='admin',
                     scheduled_time=scheduled_time, notify_scheduled=True, is_active=True, **bot_kw)
    db.add(bot)
    db.flush()
    return c, b, w, u, bot


def _patch_report(monkeypatch, text='📊 <b>Hisobot</b>'):
    import app.services.ai_service as ai
    monkeypatch.setattr(ai, 'build_daily_report', lambda db, cid, name: text)


# ─── 5. Muddati tugayotgan tovarlar: ombor bo'yicha guruhlash, bo'laklash ───

def test_notify_expiring_300_batches_grouped_by_warehouse_and_chunked(db, mk, sch, monkeypatch):
    c, b1, w1, u, bot = _company_with_bot(db, mk, notify_expired_products=True, expired_days_before=15)
    b2 = mk.branch(c, name='Yunusobod filiali')
    w2 = mk.warehouse(c, b2, name='Yunusobod ombori')
    w1.name = 'Chilonzor ombori'
    cat = Category(name='Sut', company_id=c.id, is_perishable=True)
    db.add(cat)
    db.flush()
    p_special = Product(name='Kabel <USB-C> 1m & Co', sku='S-1', barcode='B-1', company_id=c.id,
                        cost_price=0, sale_price=0, product_type='simple', category_id=cat.id)
    db.add(p_special)
    db.flush()
    products = [p_special]
    for i in range(29):
        p = Product(name=f'Sut mahsuloti {i:02d} ' + 'N' * 20, sku=f'S-{i + 10}', barcode=f'B-{i + 10}', company_id=c.id,
                    cost_price=0, sale_price=0, product_type='simple', category_id=cat.id)
        db.add(p)
        products.append(p)
    db.flush()
    n = 0
    for p in products:
        for wh in (w1, w2):
            for k in range(5):
                db.add(Batch(product_id=p.id, warehouse_id=wh.id, company_id=c.id, lot_number=f'L{n}',
                             expiry_date=datetime.now() + timedelta(days=2 + k), initial_quantity=Decimal(3),
                             quantity=Decimal(3), purchase_price=Decimal(1)))
                n += 1
    db.flush()
    assert n == 300

    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append((token, chat_id, text))
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    asyncio.run(sched.notify_expiring_products())

    assert len(sent) == 1                                   # bitta rahbar -> send_tg_chunks bir marta
    text = sent[0][2]
    assert 'Ombor: Chilonzor ombori' in text and 'Filial: ' + b1.name in text
    assert 'Ombor: Yunusobod ombori' in text and 'Filial: Yunusobod filiali' in text
    assert 'Kabel &lt;USB-C&gt; 1m &amp; Co' in text and '<USB-C>' not in text     # escape qilingan
    assert text.count('📦') == 60                           # ombor x mahsulot (guruhlangan)
    chunks = split_html_message(text)
    assert len(chunks) > 1 and all(len(ch) <= 4096 for ch in chunks)
    # har bir bo'lak balanslangan teglar bilan
    assert all(ch.count('<b>') == ch.count('</b>') for ch in chunks)


def test_notify_expiring_special_name_delivered_without_400(db, mk, sch, monkeypatch):
    """Mahsulot nomi 'Kabel <USB-C> 1m' bo'lsa ham Telegram 400 bermaydi: nom escape qilingan."""
    c, b, w, u, bot = _company_with_bot(db, mk, notify_expired_products=True, expired_days_before=15)
    cat = Category(name='Sut', company_id=c.id, is_perishable=True)
    db.add(cat)
    db.flush()
    p = Product(name='Kabel <USB-C> 1m', sku='S-9', barcode='B-9', company_id=c.id, cost_price=0, sale_price=0,
                product_type='simple', category_id=cat.id)
    db.add(p)
    db.flush()
    db.add(Batch(product_id=p.id, warehouse_id=w.id, company_id=c.id, lot_number='L1',
                 expiry_date=datetime.now() + timedelta(days=3), initial_quantity=Decimal(1), quantity=Decimal(1),
                 purchase_price=Decimal(1)))
    db.flush()

    posted = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            posted.append(json)
            # Telegram HTML parseri: xom '<USB-C>' teg bo'lsa 400
            if '<USB-C>' in json['text']:
                return _Resp(400, "Bad Request: can't parse entities")
            return _Resp(200)

    monkeypatch.setattr(sched.httpx, 'AsyncClient', FakeClient)
    asyncio.run(sched.notify_expiring_products())
    assert len(posted) == 1 and 'Kabel &lt;USB-C&gt; 1m' in posted[0]['text']


# ─── 6. Kunlik hisobot: oyna, bir marta, registr ───

def _tick(at):
    asyncio.run(sched._scheduler_tick(at))


def test_report_sent_inside_window_once_per_day(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append((token, chat_id, text))
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)

    _tick(_at(19, 59))
    assert sent == []                                       # hali vaqt kelmagan
    _tick(_at(20, 1))                                       # 20:00 daqiqasi tushib qolgan
    assert len(sent) == 1 and sent[0][1] == u.tg_chat_id
    _tick(_at(20, 2))
    _tick(_at(20, 30))
    assert len(sent) == 1                                   # bir kunda bir marta
    rows = _runs(db, 'daily_report_tg')
    assert len(rows) == 1 and rows[0].status == 'done' and rows[0].scope == f'company:{c.id}'
    # ertasi kun yana yuboriladi
    _tick(_at(20, 0, d=TODAY + timedelta(days=1)))
    assert len(sent) == 2


def test_report_catches_up_at_20_30_when_minute_missed(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append(chat_id)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(20, 30))
    assert sent == [u.tg_chat_id]


def test_report_window_expired_is_skipped(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(*a, **k):
        sent.append(1)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(23, 30))
    assert sent == [] and _runs(db, 'daily_report_tg') == []


def test_report_not_resent_after_restart_or_other_worker(db, mk, sch, monkeypatch):
    """Registr DB'da: 'worker' qayta ishga tushsa yoki ikkinchi worker bo'lsa ham ikkinchi marta ketmaydi."""
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append(chat_id)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    # 4 worker bir vaqtda (ketma-ket, bir xil daqiqa): faqat bittasi yuboradi
    for _ in range(4):
        _tick(_at(20, 0))
    assert len(sent) == 1


def test_report_failure_recorded_and_retried_up_to_3(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    state = {'ok': False, 'n': 0}

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        state['n'] += 1
        if not state['ok']:
            errors.append('HTTP 400: Bad Request: chat not found')
            return False
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    # vaqtni registr uchun boshqaradigan soat
    clock = {'now': datetime(2026, 10, 16, 15, 0)}
    monkeypatch.setattr(sched, '_utcnow_naive', lambda: clock['now'])

    _tick(_at(20, 0))
    row = _runs(db, 'daily_report_tg')[0]
    assert row.status == 'failed' and 'chat not found' in row.detail and row.attempts == 1
    _tick(_at(20, 1))                                       # kutish muddati o'tmagan
    assert state['n'] == 1
    clock['now'] += timedelta(minutes=6)
    _tick(_at(20, 6))
    assert state['n'] == 2 and _runs(db, 'daily_report_tg')[0].attempts == 2
    state['ok'] = True                                      # bot tiklandi
    clock['now'] += timedelta(minutes=6)
    _tick(_at(20, 12))
    row = _runs(db, 'daily_report_tg')[0]
    assert row.status == 'done' and row.attempts == 3 and state['n'] == 3
    clock['now'] += timedelta(minutes=6)
    _tick(_at(20, 18))
    assert state['n'] == 3                                  # qayta yuborilmaydi


def test_report_failure_gives_up_after_3_attempts(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    _patch_report(monkeypatch)
    n = {'v': 0}

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        n['v'] += 1
        errors.append('network down')
        return False

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    clock = {'now': datetime(2026, 10, 16, 15, 0)}
    monkeypatch.setattr(sched, '_utcnow_naive', lambda: clock['now'])
    for i in range(6):
        _tick(_at(20, i * 7 % 50))
        clock['now'] += timedelta(minutes=6)
    assert n['v'] == 3
    assert _runs(db, 'daily_report_tg')[0].status == 'failed'


def test_report_build_error_sends_escaped_fallback(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='20:00')
    c.name = 'Do\'kon <A&B>'
    db.flush()
    import app.services.ai_service as ai

    def boom(*a, **k):
        raise RuntimeError('db down')

    monkeypatch.setattr(ai, 'build_daily_report', boom)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append(text)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(20, 0))
    assert len(sent) == 1 and 'Do\'kon &lt;A&amp;B&gt;' in sent[0] and '<A&B>' not in sent[0]
    assert 'hisobot yaratilmadi' in _runs(db, 'daily_report_tg')[0].detail


def test_report_time_with_loose_format_still_works(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk, scheduled_time='9:5')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append(1)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(9, 6))
    assert sent == [1]


def test_report_skipped_when_scheduled_disabled(db, mk, sch, monkeypatch):
    c, b, w, u, bot = _company_with_bot(db, mk)
    bot.notify_scheduled = False
    db.flush()
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(*a, **k):
        sent.append(1)
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(20, 5))
    assert sent == []


def test_report_two_companies_isolated_scopes(db, mk, sch, monkeypatch):
    c1, b1, w1, u1, bot1 = _company_with_bot(db, mk, scheduled_time='20:00')
    c2, b2, w2, u2, bot2 = _company_with_bot(db, mk, scheduled_time='21:00')
    _patch_report(monkeypatch)
    sent = []

    async def fake_chunks(token, chat_id, text, parse_mode='HTML', errors=None):
        sent.append((token, chat_id))
        return True

    monkeypatch.setattr(sched, 'send_tg_chunks', fake_chunks)
    _tick(_at(20, 10))
    assert sent == [(bot1.bot_token, u1.tg_chat_id)]        # 2-korxona vaqti kelmagan, begonaga ketmaydi
    _tick(_at(21, 10))
    assert sent == [(bot1.bot_token, u1.tg_chat_id), (bot2.bot_token, u2.tg_chat_id)]


# ─── 7. 09:00 / 10:00 / 11:00 / 03:00 / 00:05 vazifalari oynada ───

def _stub_daily_jobs(monkeypatch):
    calls = []

    async def debts():
        calls.append('debts')

    async def overdue():
        calls.append('overdue')

    async def expiring():
        calls.append('expiring')

    async def write_off():
        calls.append('write_off')

    monkeypatch.setattr(sched, 'process_daily_debts', debts)
    monkeypatch.setattr(sched, 'notify_managers_overdue', overdue)
    monkeypatch.setattr(sched, 'notify_expiring_products', expiring)
    monkeypatch.setattr(sched, 'auto_write_off_expired', write_off)
    monkeypatch.setattr(sched, '_cleanup_old_locations', lambda: calls.append('gps'))
    monkeypatch.setattr(sched, 'purge_old_runs', lambda: calls.append('purge'))
    return calls


def test_daily_jobs_run_in_window_once(db, sch, monkeypatch):
    calls = _stub_daily_jobs(monkeypatch)
    _tick(_at(0, 7))            # 00:05 daqiqasi tushib qolgan
    assert calls == ['write_off', 'purge']
    _tick(_at(3, 2))
    assert calls[-1] == 'gps'
    _tick(_at(9, 4))
    _tick(_at(10, 9))
    _tick(_at(11, 45))
    assert calls[2:] == ['debts', 'overdue', 'expiring'] or calls[-3:] == ['debts', 'overdue', 'expiring']
    n = len(calls)
    for hh, mm in [(9, 5), (10, 10), (11, 46), (3, 3), (0, 8)]:
        _tick(_at(hh, mm))
    assert len(calls) == n                                  # ikkinchi marta bajarilmadi
    names = {r.job for r in _runs(db)}
    assert {'auto_write_off', 'gps_cleanup', 'debt_reminder', 'overdue_debts', 'expiring_products'} <= names


def test_daily_jobs_not_run_outside_window(db, sch, monkeypatch):
    calls = _stub_daily_jobs(monkeypatch)
    _tick(_at(8, 59))           # 09:00/10:00/11:00 vazifalari hali erta (gps/write-off oynasi hali ochiq)
    assert 'debts' not in calls and 'overdue' not in calls and 'expiring' not in calls
    calls.clear()
    _tick(_at(17, 30, d=TODAY + timedelta(days=1)))    # 09:00 (6 s) oynasi tugagan, 10:00/11:00 ham
    assert calls == ['gps', 'write_off', 'purge']       # faqat 20 soatli oynalar (yangi kun registri)
    calls.clear()
    _tick(_at(23, 30, d=TODAY + timedelta(days=2)))    # barcha oynalar yopilgan
    assert calls == []


def test_daily_job_exception_marks_failed_and_loop_survives(db, sch, monkeypatch):
    calls = _stub_daily_jobs(monkeypatch)

    async def bad_write_off():
        raise RuntimeError('boom')

    monkeypatch.setattr(sched, 'auto_write_off_expired', bad_write_off)
    _tick(_at(0, 10))
    row = _runs(db, 'auto_write_off')[0]
    assert row.status == 'failed' and 'boom' in row.detail


def test_registry_failure_does_not_stop_loop(db, sch, monkeypatch):
    calls = _stub_daily_jobs(monkeypatch)
    monkeypatch.setattr(sched, 'claim_run', lambda *a, **k: False)
    _tick(_at(9, 1))
    assert calls == []


# ─── 8. Kod holati (o'lik kod, Mir-maza, lock-fayllar) ───

def test_dead_code_and_locks_removed():
    import inspect
    src = inspect.getsource(sched)
    assert not hasattr(sched, 'check_and_send_reports')
    assert not hasattr(sched, 'send_daily_report_for_company')
    assert not hasattr(sched, '_is_time')
    assert 'tempfile' not in src and '.lock' not in src
    assert 'last_report_dates' not in src and 'last_debt_date' not in src
    assert 'get_active_features' not in src


def test_marketplace_pull_in_thread_and_separate_loop():
    import inspect
    src = inspect.getsource(sched._marketplace_pull_once)
    assert 'asyncio.to_thread(pull_mirmaza_orders' in src
    assert 'create_task(_marketplace_pull_loop())' in inspect.getsource(sched.start_scheduler)
    assert 'pull_mirmaza_orders' not in inspect.getsource(sched._scheduler_tick)


def test_sleep_aligned_to_minute():
    import inspect
    assert '60 - datetime.now().second' in inspect.getsource(sched.start_scheduler)


def test_marketplace_pull_once_runs_pull_in_thread(db, mk, sch, monkeypatch):
    import threading
    import app.services.marketplace_service as mp
    c = mk.company()
    c.marketplace_agents_enabled = True
    db.flush()
    seen = {}

    def fake_pull(session):
        seen['thread'] = threading.current_thread()

    monkeypatch.setattr(mp, 'pull_mirmaza_orders', fake_pull)
    asyncio.run(sched._marketplace_pull_once())
    assert seen['thread'] is not threading.main_thread()


# ─── 9. Boshqa Telegram yuboruvchilar: sales.py / order_to_sale / admin bot ───

def test_sales_and_order_to_sale_messages_escape_dynamic_values():
    import inspect
    import app.routers.sales as sales_router
    import app.services.order_to_sale as ots
    import app.admin_tg_bot.notifications as notif
    # T3.x: sotuv xabari sales.py dan notifications.notify_new_sale ga ko'chgan — sales.py da xom f-string xabar qolmagan
    assert 'notify_new_sale' in inspect.getsource(sales_router)
    s = inspect.getsource(notif)
    assert '{esc(cashier.name if cashier else' in s and '{esc(cust_name)}' in s
    assert '{esc(e)}' in inspect.getsource(ots)


def test_ai_status_text_matches_default_time():
    from app.routers.ai_analytics import get_ai_status
    feats = get_ai_status()['features']
    assert not any('17:30' in f for f in feats)
    assert any('Telegram hisoboti' in f for f in feats)


def test_admin_bot_notification_chunks_and_plain_fallback(db, mk, monkeypatch):
    from aiogram.exceptions import TelegramBadRequest
    from app.admin_tg_bot import notifications
    c, b, w, u, bot = _company_with_bot(db, mk, notify_instant_sales=True)
    sent = []

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self.session = MagicMock()
            self.session.close = AsyncMock()

        async def send_message(self, chat_id, text, **kw):
            if kw.get('parse_mode', 'HTML') is not None and '<USB-C>' in text:
                raise TelegramBadRequest(method=MagicMock(), message="Bad Request: can't parse entities")
            sent.append((chat_id, text, kw))

    monkeypatch.setattr(notifications, 'SessionLocal', app_database.SessionLocal)
    monkeypatch.setattr(notifications, 'Bot', FakeBot)

    # 1) uzun xabar bo'laklanadi
    long_msg = '\n'.join(f'🧾 qator {i} <b>x</b>' for i in range(1000))
    asyncio.run(notifications.send_instant_notification(c.id, long_msg, 'sale'))
    assert len(sent) > 1 and all(len(t) <= 4096 for _, t, _ in sent)

    # 2) parse xatosida teglarsiz qayta
    sent.clear()
    asyncio.run(notifications.send_instant_notification(c.id, '<b>Kabel</b> <USB-C> 1m', 'sale'))
    assert len(sent) == 1 and sent[0][1] == 'Kabel <USB-C> 1m' and sent[0][2].get('parse_mode', 'x') is None


# ─── 10. Model va migratsiya ───

def test_model_and_migration_consistent():
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[2].joinpath('alembic/versions/t2_10_scheduler_runs.py').read_text(encoding='utf-8')
    assert "revision = 't2_10'" in src and "down_revision = 't2_8'" in src
    assert 'CREATE TABLE IF NOT EXISTS scheduler_runs' in src
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduler_runs_job_scope_date' in src
    assert 'DROP TABLE IF EXISTS scheduler_runs' in src
    cols = {c.name for c in SchedulerRun.__table__.columns}
    assert cols == {'id', 'job', 'scope', 'run_date', 'status', 'attempts', 'claimed_at', 'finished_at', 'detail'}
    idx = {i.name: i for i in SchedulerRun.__table__.indexes}
    assert idx['uq_scheduler_runs_job_scope_date'].unique is True
