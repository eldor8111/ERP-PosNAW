"""Ko'p filial auditi (TZ) testlari uchun umumiy muhit.

Haqiqiy modellardan SQLite baza (xotirada, FK yoqilgan) quriladi; har bir test
o'z tranzaksiyasida ishlaydi va oxirida bekor qilinadi, shuning uchun testlar
bir-biriga ta'sir qilmaydi. Ishga tushirish (loyiha ildizidan):

    python -m pytest tests/branch_audit -q

Eslatma: app kodi `db.commit()` chaqirsa, u SAVEPOINT sifatida bajariladi va
test oxirida baribir bekor bo'ladi. `SessionLocal()` ni to'g'ridan-to'g'ri
ochadigan kod (scheduler, fon vazifalari) ham shu test bazasiga ulanadi.
"""
import itertools
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://u:p@localhost:5999/x')
os.environ.setdefault('SECRET_KEY', 'test-secret-' + 'x' * 32)

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as app_database
import app.main  # noqa: F401 — barcha modellar ro'yxatdan o'tadi
from app.core.dependencies import get_current_user, get_current_user_allow_expired
from app.database import Base, get_db
from app.main import app
from app.models.branch import Branch
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus
from app.models.warehouse import Warehouse


@compiles(JSONB, 'sqlite')
def _jsonb(t, c, **k):
    return 'JSON'


@compiles(ARRAY, 'sqlite')
def _arr(t, c, **k):
    return 'JSON'


engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})


@event.listens_for(engine, 'connect')
def _on_connect(dbapi, rec):
    dbapi.isolation_level = None          # pysqlite SAVEPOINT tuzatmasi (SQLAlchemy hujjati)
    dbapi.execute('PRAGMA foreign_keys=ON')


@event.listens_for(engine, 'begin')
def _on_begin(conn):
    conn.exec_driver_sql('BEGIN')


Base.metadata.create_all(engine)
_seq = itertools.count(1)


@pytest.fixture
def db():
    """Har test uchun alohida tranzaksiya; oxirida hammasi bekor qilinadi."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode='create_savepoint', expire_on_commit=False)
    # To'g'ridan-to'g'ri SessionLocal() ochadigan kod ham shu ulanishga tushsin
    orig_local = app_database.SessionLocal
    app_database.SessionLocal = sessionmaker(bind=conn, join_transaction_mode='create_savepoint', expire_on_commit=False)
    try:
        yield session
    finally:
        app_database.SessionLocal = orig_local
        session.close()
        trans.rollback()
        conn.close()


class Maker:
    """Test ma'lumotlarini tez yaratish: ikki korxona, filiallar, omborlar, xodimlar."""

    def __init__(self, db):
        self.db = db

    def company(self, name=None, **kw):
        n = next(_seq)
        c = Company(name=name or f'Korxona {n}', org_code=kw.pop('org_code', f'K{n:05d}'), **kw)
        self.db.add(c)
        self.db.flush()
        return c

    def branch(self, company, name=None, **kw):
        b = Branch(name=name or f'Filial {next(_seq)}', company_id=company.id, **kw)
        self.db.add(b)
        self.db.flush()
        return b

    def warehouse(self, company, branch=None, name=None, **kw):
        w = Warehouse(name=name or f'Ombor {next(_seq)}', company_id=company.id,
                      branch_id=branch.id if branch else None, **kw)
        self.db.add(w)
        self.db.flush()
        return w

    def user(self, company, role=UserRole.admin, branch=None, **kw):
        n = next(_seq)
        u = User(name=kw.pop('name', f'Xodim {n}'), phone=kw.pop('phone', f'9989{n:08d}'),
                 hashed_password=kw.pop('hashed_password', 'x'), role=role,
                 company_id=company.id if company else None,
                 branch_id=branch.id if branch else None,
                 status=kw.pop('status', UserStatus.active), **kw)
        self.db.add(u)
        self.db.flush()
        return u

    def tenant(self, role=UserRole.admin):
        """Bitta korxona: filial + ombor + xodim. (company, branch, warehouse, user) qaytaradi."""
        c = self.company()
        b = self.branch(c)
        w = self.warehouse(c, b)
        u = self.user(c, role=role, branch=b)
        return c, b, w, u


@pytest.fixture
def mk(db):
    return Maker(db)


@pytest.fixture
def client(db):
    """FastAPI TestClient; `client.login(user)` bilan so'rovlar shu foydalanuvchi nomidan ketadi."""
    from fastapi.testclient import TestClient

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    c = TestClient(app)

    def login(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_allow_expired] = lambda: user
        return c

    c.login = login
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
