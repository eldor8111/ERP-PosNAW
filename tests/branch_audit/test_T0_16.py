"""T0.16 — Admin Telegram botni korxonaga bog'lab xavfsizlashtirish.

Tekshiriladi: bot korxonasiga a'zolik (access.py), begona korxona rahbariga
hisobot bermaslik, botdan foydalanuvchi yaratilmasligi, link_admin_by_phone
ismni o'zgartirmasligi, oluvchilar filtri, delete_user/unlink-telegram.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.database as app_database
from app.admin_tg_bot import bot_manager
from app.admin_tg_bot.access import get_company_admin_by_tg_id, get_report_recipients
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany


# ---------- yordamchilar ----------

@pytest.fixture
def bot_db(db, monkeypatch):
    """bot_manager `SessionLocal` ni nom bilan import qilgan — test sessiyasiga yo'naltiramiz."""
    monkeypatch.setattr(bot_manager, "SessionLocal", app_database.SessionLocal)
    return db


def uc(db, user, company, role=UserRole.director, is_active=True):
    row = UserCompany(user_id=user.id, company_id=company.id, role=role, is_active=is_active)
    db.add(row)
    db.flush()
    return row


def fake_message(tg_id=777, text=None, phone=None, full_name="TG Ismi"):
    m = MagicMock()
    m.from_user.id = tg_id
    m.from_user.full_name = full_name
    m.text = text
    m.answer = AsyncMock()
    if phone is not None:
        m.contact.user_id = tg_id
        m.contact.phone_number = phone
    else:
        m.contact = None
    return m


def fake_state():
    s = MagicMock()
    s.set_state = AsyncMock()
    s.clear = AsyncMock()
    s.update_data = AsyncMock()
    s.get_data = AsyncMock(return_value={})
    return s


def answered_text(msg):
    return "\n".join(str(c.args[0]) for c in msg.answer.await_args_list)


# ---------- access.py: a'zolik sharti ----------

def test_other_company_admin_is_not_found_for_bot_company(db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    admin_a.tg_chat_id = "100"
    db.flush()
    assert get_company_admin_by_tg_id(db, "100", a.id).id == admin_a.id   # o'z korxonasi — ishlaydi
    assert get_company_admin_by_tg_id(db, "100", b.id) is None            # begona korxona — yo'q


def test_multi_company_director_via_user_companies_is_found(db, mk):
    a, _, _, _ = mk.tenant()
    b, _, _, _ = mk.tenant()
    director = mk.user(a, role=UserRole.director, tg_chat_id="200")  # users.company_id = A
    uc(db, director, b, role=UserRole.director)                        # B da faol direktor
    assert get_company_admin_by_tg_id(db, "200", b.id).id == director.id
    assert director.id in {u.id for u in get_report_recipients(db, b.id)}


def test_inactive_membership_status_or_role_excluded(db, mk):
    a, _, _, _ = mk.tenant()
    b, _, _, _ = mk.tenant()
    # user_companies.is_active=False
    d1 = mk.user(a, role=UserRole.director, tg_chat_id="301")
    uc(db, d1, b, is_active=False)
    assert get_company_admin_by_tg_id(db, "301", b.id) is None
    # users.status != active (o'z korxonasida ham)
    d2 = mk.user(a, role=UserRole.admin, tg_chat_id="302", status=UserStatus.inactive)
    assert get_company_admin_by_tg_id(db, "302", a.id) is None
    d3 = mk.user(a, role=UserRole.admin, tg_chat_id="303", status=UserStatus.blocked)
    assert get_company_admin_by_tg_id(db, "303", a.id) is None
    # user_companies da rahbar emas (kassir) — garchi users.role admin bo'lsa ham
    d4 = mk.user(a, role=UserRole.admin, tg_chat_id="304")
    uc(db, d4, a, role=UserRole.cashier)
    assert get_company_admin_by_tg_id(db, "304", a.id) is None
    # users.role kassir, user_companies qatori yo'q
    d5 = mk.user(a, role=UserRole.cashier, tg_chat_id="305")
    assert get_company_admin_by_tg_id(db, "305", a.id) is None
    # Eski foydalanuvchi (user_companies qatori yo'q) — fallback B ishlaydi
    d6 = mk.user(a, role=UserRole.admin, tg_chat_id="306")
    assert get_company_admin_by_tg_id(db, "306", a.id).id == d6.id


def test_report_recipients_combinations(db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, admin_b = mk.tenant()
    admin_a.tg_chat_id = "1"
    admin_b.tg_chat_id = "2"
    inactive = mk.user(a, role=UserRole.director, tg_chat_id="3", status=UserStatus.inactive)
    cashier = mk.user(a, role=UserRole.cashier, tg_chat_id="4")
    no_tg = mk.user(a, role=UserRole.admin)
    ext = mk.user(b, role=UserRole.director, tg_chat_id="5")
    uc(db, ext, a, role=UserRole.admin)                      # B dan A ga faol admin
    gone = mk.user(b, role=UserRole.director, tg_chat_id="6")
    uc(db, gone, a, role=UserRole.admin, is_active=False)    # A dagi a'zoligi tugagan
    db.flush()

    ids = {u.id for u in get_report_recipients(db, a.id)}
    assert ids == {admin_a.id, ext.id}
    for u in (admin_b, inactive, cashier, no_tg, gone):
        assert u.id not in ids


# ---------- bot_manager: handlerlar ----------

def test_handlers_refuse_report_for_other_company_admin(bot_db, mk, monkeypatch):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    admin_a.tg_chat_id = "900"
    bot_db.flush()
    called = []
    monkeypatch.setattr(bot_manager, "get_daily_sales_report", lambda cid: called.append(cid) or {
        "date": "01.01.2026", "sales_count": 0, "total_amount": 0, "returns_count": 0,
        "returns_amount": 0, "net_amount": 0, "total_discount": 0, "avg_check": 0})
    monkeypatch.setattr(bot_manager, "get_monthly_sales_report", lambda cid: called.append(cid) or {
        "month": "2026-01", "sales_count": 0, "total_amount": 0, "returns_count": 0,
        "returns_amount": 0, "net_amount": 0, "total_discount": 0, "avg_check": 0, "daily_data": []})

    for handler in (bot_manager.cmd_start, bot_manager.handle_daily_report, bot_manager.handle_monthly_report):
        msg, state = fake_message(tg_id=900), fake_state()
        asyncio.run(handler(msg, state, b.id))                       # B korxona boti
        assert called == [], "begona korxona rahbariga hisobot tuzilmasligi kerak"
        assert "ro'yxatdan o'tmagansiz" in answered_text(msg)
        state.set_state.assert_awaited_with(bot_manager.RegisterStates.waiting_for_phone)

    # Ijobiy yo'l: o'z korxonasi boti — hisobot keladi
    msg, state = fake_message(tg_id=900), fake_state()
    asyncio.run(bot_manager.handle_daily_report(msg, state, a.id))
    assert called == [a.id]
    assert "Kunlik Sotuv Hisoboti" in answered_text(msg)


def test_uc_director_gets_report_from_bot_company(bot_db, mk, monkeypatch):
    a, _, _, _ = mk.tenant()
    b, _, _, _ = mk.tenant()
    director = mk.user(a, role=UserRole.director, tg_chat_id="901")
    uc(bot_db, director, b, role=UserRole.director)
    called = []
    monkeypatch.setattr(bot_manager, "get_monthly_sales_report", lambda cid: called.append(cid) or {
        "month": "2026-01", "sales_count": 1, "total_amount": 10, "returns_count": 0,
        "returns_amount": 0, "net_amount": 10, "total_discount": 0, "avg_check": 10, "daily_data": []})
    msg, state = fake_message(tg_id=901), fake_state()
    asyncio.run(bot_manager.handle_monthly_report(msg, state, b.id))
    assert called == [b.id]
    assert "Oylik Sotuv Hisoboti" in answered_text(msg)


# ---------- bot_manager: ro'yxatdan o'tish ----------

def test_process_contact_not_found_creates_no_user(bot_db, mk):
    a, _, _, _ = mk.tenant()
    before = bot_db.query(User).count()
    msg, state = fake_message(tg_id=555, phone="+998 90 111 22 33"), fake_state()
    asyncio.run(bot_manager.process_contact(msg, state, a.id))
    assert bot_db.query(User).count() == before
    assert bot_db.query(User).filter(User.tg_chat_id == "555").first() is None
    assert "veb-paneldan" in answered_text(msg)
    state.clear.assert_awaited()
    state.set_state.assert_not_awaited()   # ism/parol holatiga o'tilmaydi


def test_bot_has_no_self_registration_flow():
    assert not hasattr(bot_manager, "create_new_user")
    assert not hasattr(bot_manager, "process_name")
    assert not hasattr(bot_manager, "process_password")
    assert not hasattr(bot_manager.RegisterStates, "waiting_for_name")
    assert not hasattr(bot_manager.RegisterStates, "waiting_for_password")


def test_link_admin_by_phone_keeps_name_and_matches_exact_digits(bot_db, mk):
    a, _, _, _ = mk.tenant()
    admin = mk.user(a, role=UserRole.admin, name="Haqiqiy Ism", phone="+998901234567")
    # oxirgi 9 raqam: 901234567. "+998 (90) 123-45-67" ham mos kelishi kerak
    user, status = bot_manager.link_admin_by_phone("+998 (90) 123-45-67", "4242", "Telegram Nomi", a.id)
    assert status == "success" and user.id == admin.id
    bot_db.expire_all()
    fresh = bot_db.get(User, admin.id)
    assert fresh.tg_chat_id == "4242"
    assert fresh.name == "Haqiqiy Ism"      # Telegram ismi users.name ga yozilmaydi


def test_link_admin_by_phone_other_company_and_roles(bot_db, mk):
    a, _, _, _ = mk.tenant()
    b, _, _, _ = mk.tenant()
    admin_a = mk.user(a, role=UserRole.admin, phone="+998911111111")
    cashier_b = mk.user(b, role=UserRole.cashier, phone="+998922222222")
    # A korxona admini B korxona botiga — bu korxonada yo'q
    assert bot_manager.link_admin_by_phone("+998911111111", "1", None, b.id) == (None, "not_found")
    # B korxona kassiri — faqat rahbarlar
    assert bot_manager.link_admin_by_phone("+998922222222", "2", None, b.id) == (None, "not_allowed")
    # Tizimda yo'q raqam
    assert bot_manager.link_admin_by_phone("+998933333333", "3", None, b.id) == (None, "not_found")
    # Ko'p korxonali direktor (users.company_id = A, user_companies orqali B) — B botida ulanadi
    director = mk.user(a, role=UserRole.director, phone="+998944444444")
    uc(bot_db, director, b, role=UserRole.director)
    user, status = bot_manager.link_admin_by_phone("+998944444444", "4", None, b.id)
    assert status == "success" and user.id == director.id
    # T3.16: korxonadan bir nechta rahbar ulana oladi — B da ikkinchi rahbar ham muvaffaqiyatli ulanadi
    admin_b2 = mk.user(b, role=UserRole.admin, phone="+998955555555")
    user2, status2 = bot_manager.link_admin_by_phone("+998955555555", "5", None, b.id)
    assert status2 == "success" and user2.id == admin_b2.id
    # Nofaol admin ulana olmaydi
    bot_db.expire_all()
    inactive = mk.user(a, role=UserRole.admin, phone="+998966666666", status=UserStatus.inactive)
    assert bot_manager.link_admin_by_phone("+998966666666", "6", None, a.id) == (None, "not_found")
    assert admin_a.id and admin_b2.id and inactive.id


# ---------- users.py: delete_user va unlink-telegram ----------

def test_delete_user_clears_tg_chat_id(client, mk, db):
    a, _, _, admin_a = mk.tenant()
    target = mk.user(a, role=UserRole.director, tg_chat_id="777")
    r = client.login(admin_a).delete(f"/api/users/{target.id}")
    assert r.status_code == 204, r.text
    db.expire_all()
    fresh = db.get(User, target.id)
    assert fresh.status == UserStatus.inactive
    assert fresh.tg_chat_id is None


def test_delete_user_from_one_company_keeps_tg_for_other_active_company(client, mk, db):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    target = mk.user(b, role=UserRole.director, tg_chat_id="778")
    uc(db, target, a, role=UserRole.director)
    uc(db, target, b, role=UserRole.director)
    r = client.login(admin_a).delete(f"/api/users/{target.id}")
    assert r.status_code == 204, r.text
    db.expire_all()
    fresh = db.get(User, target.id)
    assert fresh.status == UserStatus.active and fresh.tg_chat_id == "778"  # B da faol — bog'lanish qoladi


def test_unlink_telegram_own_company_ok(client, mk, db):
    a, _, _, admin_a = mk.tenant()
    target = mk.user(a, role=UserRole.director, tg_chat_id="800")
    r = client.login(admin_a).post(f"/api/users/{target.id}/unlink-telegram")
    assert r.status_code == 200 and r.json() == {"ok": True}
    db.expire_all()
    assert db.get(User, target.id).tg_chat_id is None


def test_unlink_telegram_other_company_forbidden(client, mk, db):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    target = mk.user(b, role=UserRole.director, tg_chat_id="801")
    r = client.login(admin_a).post(f"/api/users/{target.id}/unlink-telegram")
    assert r.status_code in (403, 404)
    db.expire_all()
    assert db.get(User, target.id).tg_chat_id == "801"
    # Yo'q foydalanuvchi — 404
    assert client.login(admin_a).post("/api/users/999999/unlink-telegram").status_code == 404


def test_unlink_telegram_requires_admin_role(client, mk, db):
    a, _, _, _ = mk.tenant()
    cashier = mk.user(a, role=UserRole.cashier)
    target = mk.user(a, role=UserRole.director, tg_chat_id="802")
    r = client.login(cashier).post(f"/api/users/{target.id}/unlink-telegram")
    assert r.status_code == 403
    db.expire_all()
    assert db.get(User, target.id).tg_chat_id == "802"


# ---------- notifications.py / scheduler.py: oluvchilar ----------

def test_instant_notification_skips_inactive_and_foreign(db, mk, monkeypatch):
    from app.admin_tg_bot import notifications
    from app.admin_tg_bot.models import CompanyBot

    a, _, _, admin_a = mk.tenant()
    b, _, _, admin_b = mk.tenant()
    admin_a.tg_chat_id = "n1"
    admin_b.tg_chat_id = "n2"
    gone = mk.user(a, role=UserRole.director, tg_chat_id="n3", status=UserStatus.inactive)
    db.add(CompanyBot(company_id=a.id, bot_token="tok-a", bot_type="admin", notify_instant_sales=True))
    db.flush()

    sent = []

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self.session = MagicMock()
            self.session.close = AsyncMock()

        async def send_message(self, chat_id, text):
            sent.append(chat_id)

    monkeypatch.setattr(notifications, "SessionLocal", app_database.SessionLocal)
    monkeypatch.setattr(notifications, "Bot", FakeBot)
    asyncio.run(notifications.send_instant_notification(a.id, "test", "sale"))
    assert sent == ["n1"]           # nofaol (n3) va begona korxona (n2) chetlandi
    assert gone.id


def test_scheduler_uses_shared_recipients_helper():
    """scheduler.py da rahbarlarga xom `tg_chat_id.isnot(None)` so'rovi qolmagan."""
    import inspect
    from app.services import scheduler
    # T2.10: eski send_daily_report_for_company va sikl ichidagi dublikat bitta _send_company_tg_report ga birlashdi (4 -> 3)
    # T3.16: umumiy yordamchi nomi resolve_recipients(db, company_id, kind=...) bo'ldi (qarz / muddat / kunlik hisobot)
    src = inspect.getsource(scheduler)
    assert src.count("resolve_recipients(db, company.id, kind=") == 3
    assert "User.tg_chat_id.isnot(None)" not in src
