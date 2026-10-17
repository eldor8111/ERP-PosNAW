"""PUT /auth/me — foydalanuvchi o'z profilini (ism, email, parol) tahrirlaydi."""
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole


def test_update_name_and_email(client, mk):
    c, b, w, u = mk.tenant()
    r = client.login(u).put('/api/auth/me', json={'name': '  Mirzo Badullayev ', 'email': 'Mirzo@Example.com'})
    assert r.status_code == 200, r.text
    assert r.json()['name'] == 'Mirzo Badullayev'
    assert r.json()['email'] == 'mirzo@example.com'
    assert r.json()['company_id'] == c.id


def test_short_name_and_bad_email_rejected(client, mk):
    c, b, w, u = mk.tenant()
    assert client.login(u).put('/api/auth/me', json={'name': 'A'}).status_code == 400
    assert client.login(u).put('/api/auth/me', json={'email': 'notanemail'}).status_code == 400


def test_email_busy_in_another_user(client, mk):
    c, b, w, u = mk.tenant()
    other = mk.user(c, role=UserRole.cashier, email='busy@example.com')
    r = client.login(u).put('/api/auth/me', json={'email': 'busy@example.com'})
    assert r.status_code == 400
    assert other.email == 'busy@example.com'


def test_password_change_requires_current(client, mk, db):
    c, b, w, u = mk.tenant()
    u.hashed_password = hash_password('eski123')
    db.flush()
    r = client.login(u).put('/api/auth/me', json={'current_password': 'xato', 'new_password': 'yangi123'})
    assert r.status_code == 400
    r = client.login(u).put('/api/auth/me', json={'current_password': 'eski123', 'new_password': '123'})
    assert r.status_code == 400
    r = client.login(u).put('/api/auth/me', json={'current_password': 'eski123', 'new_password': 'yangi123'})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert verify_password('yangi123', db.get(User, u.id).hashed_password)


def test_phone_cannot_be_changed_here(client, mk):
    c, b, w, u = mk.tenant()
    phone = u.phone
    r = client.login(u).put('/api/auth/me', json={'name': 'Yangi Ism', 'phone': '998900000000'})
    assert r.status_code == 200
    assert r.json()['phone'] == phone
