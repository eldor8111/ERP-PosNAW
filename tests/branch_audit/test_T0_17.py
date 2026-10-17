"""T0.17 — /auth/link-telegram o'chirildi; kuryer botida kontakt egasi tekshiruvi;
unlink-telegram endpointi."""
import pytest

from app.models.courier import Courier
from app.models.user import UserRole
from app.routers import courier_bot

TOKEN = "bot-token-t017"
PHONE = "998901112233"


@pytest.fixture
def sent(monkeypatch):
    msgs = []

    async def fake_send(token, chat_id, text, reply_markup=None):
        msgs.append((chat_id, text))

    monkeypatch.setattr(courier_bot, "_send_message", fake_send)
    return msgs


def _setup(db, mk, tg=None, phone=PHONE):
    c = mk.company()
    c.courier_bot_token = TOKEN
    db.flush()
    cour = Courier(company_id=c.id, name="Kuryer", phone=phone, is_active=True, tg_chat_id=tg)
    db.add(cour)
    db.flush()
    return c, cour


def _contact(client, from_id, contact_uid, phone=PHONE, chat_id=None):
    contact = {"phone_number": "+" + phone, "first_name": "X"}
    if contact_uid is not None:
        contact["user_id"] = contact_uid
    return client.post(f"/api/courier-bot/webhook/{TOKEN}", json={"message": {
        "chat": {"id": chat_id or from_id}, "from": {"id": from_id}, "contact": contact}})


def test_link_telegram_endpoint_removed(client):
    r = client.post("/api/auth/link-telegram", json={"phone": PHONE, "chat_id": "1"})
    assert r.status_code in (404, 405)


def test_own_contact_links(client, db, mk, sent):
    _, cour = _setup(db, mk)
    r = _contact(client, 555, 555)
    assert r.json() == {"ok": True}
    db.refresh(cour)
    assert cour.tg_chat_id == "555"


def test_foreign_contact_rejected(client, db, mk, sent):
    _, cour = _setup(db, mk)
    r = _contact(client, 666, 555)  # begona (forward) kontakt
    assert r.json() == {"ok": True}
    db.refresh(cour)
    assert cour.tg_chat_id is None
    assert any("o'zingizning" in t for _, t in sent)


def test_contact_without_user_id_rejected(client, db, mk, sent):
    _, cour = _setup(db, mk)
    _contact(client, 666, None)
    db.refresh(cour)
    assert cour.tg_chat_id is None


def test_occupied_courier_not_overwritten_then_relink_after_unlink(client, db, mk, sent):
    c, cour = _setup(db, mk, tg="111")
    _contact(client, 222, 222)
    db.refresh(cour)
    assert cour.tg_chat_id == "111"
    assert any("boshqa Telegram" in t for _, t in sent)

    admin = mk.user(c, role=UserRole.admin)
    r = client.login(admin).post(f"/api/couriers/{cour.id}/unlink-telegram")
    assert r.status_code == 200 and r.json() == {"ok": True}
    db.refresh(cour)
    assert cour.tg_chat_id is None

    _contact(client, 222, 222)
    db.refresh(cour)
    assert cour.tg_chat_id == "222"


def test_same_chat_other_courier_rejected(client, db, mk, sent):
    c, cour = _setup(db, mk)
    other = Courier(company_id=c.id, name="Boshqa", phone="998907778899", is_active=True, tg_chat_id="777")
    db.add(other)
    db.flush()
    _contact(client, 777, 777)
    db.refresh(cour)
    assert cour.tg_chat_id is None


def test_unlink_other_company_404(client, db, mk, sent):
    _, cour = _setup(db, mk, tg="111")
    _, _, _, admin_b = mk.tenant()
    r = client.login(admin_b).post(f"/api/couriers/{cour.id}/unlink-telegram")
    assert r.status_code == 404
    db.refresh(cour)
    assert cour.tg_chat_id == "111"
