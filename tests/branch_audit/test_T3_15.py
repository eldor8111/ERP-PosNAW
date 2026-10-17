"""T3.15 — Scheduler va admin bot infratuzilmasi (ko'p worker).

Qamrov: background_leases ijarasi (olish/band/muddat o'tishi/yangilash/bo'shatish), run_as_leader
(faqat bitta rahbar, almashish), RUN_BACKGROUND_JOBS bayrog'i va app.worker, scheduler kunlik
vazifalarining ikki marta tick'da bir marta bajarilishi, admin bot reconcile (diff_bots + main sikli),
link_admin_by_phone ismni faqat bo'sh bo'lsa to'ldirishi, o'lik FCM kodining olib tashlanishi,
migratsiya va i18n kalitlari.
"""
import asyncio
import inspect
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session, sessionmaker

import app.database as app_database
import app.services.background_jobs as bg
import app.services.scheduler as sched
from app.admin_tg_bot import bot_manager
from app.models.background_job import BackgroundLease
from app.models.scheduler_run import SchedulerRun
from app.models.user import User, UserRole
from app.utils.report_utils import LOCAL_TZ

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
T0 = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)


# ─── 1. Ijara (lease) ───

def test_lease_second_holder_blocked_until_expiry_and_owner_renews(db):
    assert bg.try_acquire_lease('scheduler', 'A', ttl=60, now=T0) is True
    # boshqa holder muddat tugamaguncha ola olmaydi
    assert bg.try_acquire_lease('scheduler', 'B', ttl=60, now=T0 + timedelta(seconds=30)) is False
    # egasi yangilaydi (muddat uzayadi)
    assert bg.try_acquire_lease('scheduler', 'A', ttl=60, now=T0 + timedelta(seconds=50)) is True
    assert bg.try_acquire_lease('scheduler', 'B', ttl=60, now=T0 + timedelta(seconds=100)) is False
    # yangilangan muddat (50+60=110s) o'tgach B oladi
    assert bg.try_acquire_lease('scheduler', 'B', ttl=60, now=T0 + timedelta(seconds=111)) is True
    db.expire_all()
    assert db.get(BackgroundLease, 'scheduler').holder == 'B'
    # eski egasi endi olmaydi
    assert bg.try_acquire_lease('scheduler', 'A', ttl=60, now=T0 + timedelta(seconds=112)) is False


def test_lease_names_are_independent_and_release_is_owner_only(db):
    assert bg.try_acquire_lease('scheduler', 'A', now=T0) is True
    assert bg.try_acquire_lease('admin_bot', 'B', now=T0) is True
    bg.release_lease('scheduler', 'B')            # begona ijarani bo'shata olmaydi
    db.expire_all()
    assert db.get(BackgroundLease, 'scheduler').holder == 'A'
    bg.release_lease('scheduler', 'A')
    db.expire_all()
    assert db.get(BackgroundLease, 'scheduler') is None
    assert bg.try_acquire_lease('scheduler', 'B', now=T0) is True


def test_try_acquire_lease_db_error_returns_false(monkeypatch):
    def boom():
        raise RuntimeError('baza yo\'q')
    monkeypatch.setattr(bg._database, 'SessionLocal', boom)
    assert bg.try_acquire_lease('scheduler', 'A') is False


# ─── 2. run_as_leader ───

@pytest.fixture
def direct_thread(monkeypatch):
    """SQLite ulanishi bitta — to_thread o'rniga bevosita chaqiramiz (parallel foydalanish yo'q)."""
    async def fake(fn, *a, **k):
        return fn(*a, **k)
    monkeypatch.setattr(bg.asyncio, 'to_thread', fake)


def _leader(name, holder, started, monkeypatch=None, **kw):
    async def job():
        started.append(holder)
        try:
            await asyncio.sleep(3600)
        finally:
            started.append(holder + ':stopped')
    return job


def test_run_as_leader_only_one_runs_and_failover_on_release(db, direct_thread, monkeypatch):
    started = []
    holders = iter(['A', 'B'])
    monkeypatch.setattr(bg, 'process_holder', lambda: next(holders))

    async def scenario():
        a = asyncio.create_task(bg.run_as_leader('scheduler', _leader('scheduler', 'A', started), ttl=30, beat=0.05))
        await asyncio.sleep(0.15)
        b = asyncio.create_task(bg.run_as_leader('scheduler', _leader('scheduler', 'B', started), ttl=30, beat=0.05))
        await asyncio.sleep(0.3)
        assert started == ['A']                     # B rahbar emas
        a.cancel()                                  # A "o'ladi": finally ijarani bo'shatadi
        with pytest.raises(asyncio.CancelledError):
            await a
        await asyncio.sleep(0.3)
        assert 'A:stopped' in started and 'B' in started
        b.cancel()
        with pytest.raises(asyncio.CancelledError):
            await b

    asyncio.run(scenario())
    assert db.get(BackgroundLease, 'scheduler') is None   # oxirida ijara bo'shatilgan


def test_run_as_leader_stops_task_when_lease_lost_and_restarts_crashed_task(db, direct_thread, monkeypatch):
    started = []
    monkeypatch.setattr(bg, 'process_holder', lambda: 'A')
    crashes = {'n': 0}

    async def crashing():
        started.append('run')
        crashes['n'] += 1
        if crashes['n'] == 1:
            raise RuntimeError('yiqildi')
        await asyncio.sleep(3600)

    async def scenario():
        t = asyncio.create_task(bg.run_as_leader('admin_bot', crashing, ttl=30, beat=0.05))
        await asyncio.sleep(0.5)
        assert started.count('run') >= 2            # yiqilgan vazifa qayta ishga tushdi
        # ijara boshqaga o'tdi -> vazifa to'xtatiladi
        row = db.get(BackgroundLease, 'admin_bot')
        row.holder = 'Z'
        row.expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)
        db.flush()
        await asyncio.sleep(0.3)
        n = started.count('run')
        await asyncio.sleep(0.3)
        assert started.count('run') == n
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(scenario())


def test_run_as_leader_keeps_leading_through_transient_db_error(db, direct_thread, monkeypatch):
    monkeypatch.setattr(bg, 'process_holder', lambda: 'A')
    state = {'fail': False, 'starts': 0, 'stops': 0}
    real = bg._acquire

    def flaky(name, holder, ttl, now=None):
        if state['fail']:
            raise RuntimeError('vaqtinchalik xato')
        return real(name, holder, ttl, now)

    monkeypatch.setattr(bg, '_acquire', flaky)

    async def job():
        state['starts'] += 1
        try:
            await asyncio.sleep(3600)
        finally:
            state['stops'] += 1

    async def scenario():
        t = asyncio.create_task(bg.run_as_leader('scheduler', job, ttl=30, beat=0.05))
        await asyncio.sleep(0.2)
        state['fail'] = True
        await asyncio.sleep(0.3)
        assert state['starts'] == 1 and state['stops'] == 0   # ttl tugamadi — vazifa to'xtamaydi
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(scenario())


def test_process_holder_format_and_flag(monkeypatch):
    h = bg.process_holder()
    assert h == bg.process_holder()
    host_pid_rand = h.rsplit(':', 2)
    assert len(host_pid_rand) == 3 and host_pid_rand[1] == str(os.getpid()) and len(host_pid_rand[2]) == 6
    monkeypatch.delenv('RUN_BACKGROUND_JOBS', raising=False)
    assert bg.background_jobs_enabled() is True
    monkeypatch.setenv('RUN_BACKGROUND_JOBS', '0')
    assert bg.background_jobs_enabled() is False
    monkeypatch.setenv('RUN_BACKGROUND_JOBS', '1')
    assert bg.background_jobs_enabled() is True


def test_lifespan_uses_leader_and_respects_flag():
    import app.main as main_mod
    src = inspect.getsource(main_mod.lifespan)
    assert 'background_jobs_enabled()' in src
    assert 'run_as_leader("scheduler", start_scheduler)' in src
    assert 'run_as_leader("admin_bot", run_admin_bot_polling)' in src
    assert 'if task is None' in src          # RUN_BACKGROUND_JOBS=0 da None task'lar o'tkaziladi


def test_worker_runs_both_jobs_as_leader(monkeypatch):
    import app.worker as worker
    names = []

    async def fake_leader(name, factory, ttl=60, beat=15):
        names.append(name)

    monkeypatch.setattr(worker, 'run_as_leader', fake_leader)
    asyncio.run(worker.amain())
    assert sorted(names) == ['admin_bot', 'scheduler']


def test_mirmaza_pull_slot_is_guarded_by_short_lease(db, monkeypatch):
    monkeypatch.setattr(bg, 'process_holder', lambda: 'P1')
    assert sched._pull_slot_free() is True
    assert sched._pull_slot_free() is True            # o'zi yangilaydi
    monkeypatch.setattr(bg, 'process_holder', lambda: 'P2')
    assert sched._pull_slot_free() is False           # boshqa jarayon bir vaqtda tortmaydi
    monkeypatch.setattr(bg._database, 'SessionLocal', lambda: (_ for _ in ()).throw(RuntimeError('x')))
    assert sched._pull_slot_free() is True            # ijara xatosi tortishni to'xtatmaydi


# ─── 3. Scheduler: kunlik vazifa ikki marta tick'da bir marta ───

class _CommitOnClose(Session):
    def close(self):
        try:
            self.commit()
        except Exception:
            pass
        super().close()


@pytest.fixture
def sch(db, monkeypatch):
    conn = app_database.SessionLocal.kw['bind']
    factory = sessionmaker(bind=conn, class_=_CommitOnClose, join_transaction_mode='create_savepoint',
                           expire_on_commit=False)
    monkeypatch.setattr(sched, 'SessionLocal', factory)
    return sched


def test_scheduler_tick_twice_runs_daily_jobs_once(db, sch, monkeypatch):
    calls = []

    async def debts():
        calls.append('debts')

    async def noop():
        pass

    monkeypatch.setattr(sched, 'process_daily_debts', debts)
    monkeypatch.setattr(sched, 'notify_managers_overdue', noop)
    monkeypatch.setattr(sched, 'notify_expiring_products', noop)
    monkeypatch.setattr(sched, 'auto_write_off_expired', noop)
    monkeypatch.setattr(sched, '_cleanup_old_locations', lambda: None)
    monkeypatch.setattr(sched, 'purge_old_runs', lambda: None)
    at = datetime(2026, 10, 17, 9, 1, tzinfo=LOCAL_TZ)
    asyncio.run(sched._scheduler_tick(at))
    asyncio.run(sched._scheduler_tick(at))        # ikkinchi worker/iteratsiya
    assert calls == ['debts']
    rows = db.query(SchedulerRun).filter(SchedulerRun.job == 'debt_reminder').all()
    assert len(rows) == 1


def test_concurrent_claim_run_only_one_wins(db):
    s1, s2 = sessionmaker(bind=db.get_bind())(), sessionmaker(bind=db.get_bind())()
    try:
        d = date(2026, 10, 17)
        assert sched.claim_run(s1, 'debt_reminder', 'global', d) is True
        assert sched.claim_run(s2, 'debt_reminder', 'global', d) is False
    finally:
        s1.close()
        s2.close()


# ─── 4. Admin bot reconcile ───

class FakeTask:
    def __init__(self, done=False):
        self._done = done
        self.cancelled_flag = False

    def done(self):
        return self._done


def test_diff_bots_new_removed_changed_and_dead():
    t_ok, t_dead = FakeTask(), FakeTask(done=True)
    running = {1: ('tok1', t_ok), 2: ('tok2', t_ok), 3: ('tok3', t_ok), 4: ('tok4', t_dead), 5: ('tok5', t_ok)}
    desired = {1: 'tok1',          # o'zgarmagan
               2: 'tok2-new',      # token almashgan
               4: 'tok4',          # task to'xtab qolgan
               5: 'tok5',
               6: 'tok6'}          # yangi bot
    # 3 — o'chirilgan/nofaol (desired da yo'q)
    stop, start = bot_manager.diff_bots(running, desired)
    assert stop == [2, 3, 4]
    assert start == [(2, 'tok2-new'), (4, 'tok4'), (6, 'tok6')]


def test_diff_bots_empty_and_unchanged():
    assert bot_manager.diff_bots({}, {}) == ([], [])
    t = FakeTask()
    assert bot_manager.diff_bots({1: ('a', t)}, {1: 'a'}) == ([], [])
    assert bot_manager.diff_bots({}, {7: 'x'}) == ([], [(7, 'x')])
    assert bot_manager.diff_bots({1: ('a', t)}, {}) == ([1], [])


def test_main_reconcile_loop_adds_replaces_and_removes_bots(monkeypatch):
    desired = {}
    log = []

    async def fake_start_bot(token, cid):
        log.append(('start', cid, token))
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            log.append(('stop', cid, token))
            raise

    monkeypatch.setattr(bot_manager, 'start_bot', fake_start_bot)
    monkeypatch.setattr(bot_manager, 'create_tables', lambda: None)
    monkeypatch.setattr(bot_manager, '_load_desired_bots', lambda: dict(desired))
    monkeypatch.setattr(bot_manager, 'BOT_RECONCILE_INTERVAL', 0.05)

    async def scenario():
        t = asyncio.create_task(bot_manager.main())
        await asyncio.sleep(0.15)
        assert log == []                                  # faol bot yo'q — sikl davom etadi (return qilmaydi)
        assert not t.done()
        desired[1] = 'tokA'                               # yangi bot qo'shildi
        await asyncio.sleep(0.2)
        assert log == [('start', 1, 'tokA')]
        desired[1] = 'tokB'                               # token almashtirildi
        await asyncio.sleep(0.2)
        assert log[1:] == [('stop', 1, 'tokA'), ('start', 1, 'tokB')]   # avval eskisi to'xtaydi (Conflict yo'q)
        del desired[1]                                    # o'chirildi / nofaol
        await asyncio.sleep(0.2)
        assert log[-1] == ('stop', 1, 'tokB')
        n = len(log)
        await asyncio.sleep(0.2)
        assert len(log) == n
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(scenario())


def test_main_reconcile_backoff_for_invalid_token_and_shutdown_stops_all(monkeypatch, capsys):
    desired = {1: 'bad', 2: 'good'}
    starts = {'bad': 0, 'good': 0}
    stopped = []

    async def fake_start_bot(token, cid):
        starts[token] += 1
        if token == 'bad':
            raise RuntimeError('Unauthorized')
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            stopped.append(cid)
            raise

    monkeypatch.setattr(bot_manager, 'start_bot', fake_start_bot)
    monkeypatch.setattr(bot_manager, 'create_tables', lambda: None)
    monkeypatch.setattr(bot_manager, '_load_desired_bots', lambda: dict(desired))
    monkeypatch.setattr(bot_manager, 'BOT_RECONCILE_INTERVAL', 0.05)

    async def scenario():
        t = asyncio.create_task(bot_manager.main())
        await asyncio.sleep(0.8)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(scenario())
    assert starts['good'] == 1                    # sog'lom bot qayta ishga tushmaydi
    assert starts['bad'] <= 4                     # yaroqsiz token backoff bilan (har siklda emas)
    assert stopped == [2]                         # yopilishda polling to'xtatildi
    out = capsys.readouterr().out
    assert out.count("company 1: polling to'xtadi") == 1   # xato bir marta loglanadi


def test_start_bot_closes_session_on_cancel(monkeypatch):
    closed = []

    class FakeSession:
        async def close(self):
            closed.append(True)

    class FakeBot:
        def __init__(self, *a, **k):
            self.session = FakeSession()

    class FakeDp:
        def __init__(self):
            class _M:
                def middleware(self, *a, **k):
                    pass
            self.message = _M()

        async def start_polling(self, bot, handle_signals=True):
            assert handle_signals is False
            await asyncio.sleep(3600)

    monkeypatch.setattr(bot_manager, 'Bot', FakeBot)
    monkeypatch.setattr(bot_manager, 'create_dispatcher', lambda: FakeDp())
    monkeypatch.setattr(bot_manager, 'register_handlers', lambda dp, cid: None)

    async def scenario():
        t = asyncio.create_task(bot_manager.start_bot('1234567890:ABCDEF' + 'x' * 10, 1))
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(scenario())
    assert closed == [True]


def test_load_desired_bots_only_active_admin_bots(db, mk, monkeypatch):
    from app.admin_tg_bot.models import CompanyBot
    monkeypatch.setattr(bot_manager, 'SessionLocal', app_database.SessionLocal)
    a, b, c = mk.company(), mk.company(), mk.company()
    db.add_all([
        CompanyBot(company_id=a.id, bot_type='admin', bot_token='tokA', is_active=True),
        CompanyBot(company_id=b.id, bot_type='admin', bot_token='tokB', is_active=False),
        CompanyBot(company_id=c.id, bot_type='courier', bot_token='tokC', is_active=True),
    ])
    db.flush()
    assert bot_manager._load_desired_bots() == {a.id: 'tokA'}


# ─── 5. link_admin_by_phone: ism faqat bo'sh bo'lsa ───

def test_link_admin_by_phone_fills_name_only_when_blank(db, mk, monkeypatch):
    monkeypatch.setattr(bot_manager, 'SessionLocal', app_database.SessionLocal)
    a, _, _, _ = mk.tenant()
    admin = mk.user(a, role=UserRole.admin, name='Akmal', phone='+998901112233')
    user, status = bot_manager.link_admin_by_phone('+998901112233', '501', 'Ak 🔥', a.id)
    assert status == 'success'
    db.expire_all()
    assert db.get(User, admin.id).name == 'Akmal'         # mavjud ism almashmaydi

    b, _, _, _ = mk.tenant()
    blank = mk.user(b, role=UserRole.director, name='   ', phone='+998902223344')
    user, status = bot_manager.link_admin_by_phone('+998902223344', '502', 'Telegram Ismi', b.id)
    assert status == 'success'
    db.expire_all()
    assert db.get(User, blank.id).name == 'Telegram Ismi'  # bo'sh ism to'ldiriladi


def test_link_admin_by_phone_company_isolation_keeps_working(db, mk, monkeypatch):
    monkeypatch.setattr(bot_manager, 'SessionLocal', app_database.SessionLocal)
    a, _, _, _ = mk.tenant()
    b, _, _, _ = mk.tenant()
    admin_a = mk.user(a, role=UserRole.admin, name='A Admin', phone='+998903334455')
    # B korxona botida A admini topilmaydi
    assert bot_manager.link_admin_by_phone('+998903334455', '1', 'X', b.id) == (None, 'not_found')
    db.expire_all()
    assert db.get(User, admin_a.id).tg_chat_id is None and db.get(User, admin_a.id).name == 'A Admin'
    # o'z korxonasida ishlaydi
    assert bot_manager.link_admin_by_phone('+998903334455', '1', 'X', a.id)[1] == 'success'


# ─── 6. O'lik FCM kodi olib tashlangan ───

def test_fcm_dead_code_removed_but_column_and_fcm_service_kept(client, mk):
    src = inspect.getsource(sched)
    assert '_send_fcm_to_managers' not in src and 'erp_fcm_' not in src and 'fcm_token' not in src
    import app.routers.users as users_router
    usrc = inspect.getsource(users_router)
    assert 'fcm_token' not in usrc and 'FCMTokenUpdate' not in usrc
    c, b, w, u = mk.tenant()
    r = client.login(u).put('/api/users/me/fcm-token', json={'fcm_token': 'abc'})
    assert r.status_code in (404, 405)
    # ustun va mobil qurilmalar uchun fcm_service o'zgarmagan
    assert hasattr(User, 'fcm_token')
    import app.services.fcm_service as fcm_service
    assert hasattr(fcm_service, 'send_multicast_notification')
    import app.main as main_mod
    assert 'ADD COLUMN IF NOT EXISTS fcm_token' in inspect.getsource(main_mod)


# ─── 7. Migratsiya, model va i18n ───

def test_migration_and_model_match():
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_15_background_leases.py')
    src = open(path, encoding='utf-8').read()
    compile(src, path, 'exec')
    assert "revision = 't3_15'" in src and "down_revision = 't3_14'" in src
    assert 'CREATE TABLE IF NOT EXISTS background_leases' in src
    assert 'DROP TABLE IF EXISTS background_leases' in src
    cols = {c.name: c for c in BackgroundLease.__table__.columns}
    assert set(cols) == {'name', 'holder', 'expires_at'}
    assert cols['name'].primary_key and cols['expires_at'].type.timezone
    for col in ('name VARCHAR(60) PRIMARY KEY', 'holder VARCHAR(120) NOT NULL', 'expires_at TIMESTAMPTZ NOT NULL'):
        assert col in src
    import app.models as models
    assert models.BackgroundLease is BackgroundLease


def test_pending_i18n_keys_present_in_all_languages():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.15.json')
    data = json.load(open(path, encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) == {'settings.telegramBot.adminStartsIn30'}
    jsx = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'Settings.jsx'), encoding='utf-8').read()
    assert "settings.telegramBot.adminStartsIn30" in jsx and 'Bot 30 soniya' in jsx
