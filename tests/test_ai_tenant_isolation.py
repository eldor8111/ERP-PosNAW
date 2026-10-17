"""AI Copilot va Semantic View'lar Tenant (Korxona) Izolyatsiyasi Testlari (Part B).

Test qilinadigan talablar:
1. ai_readonly roli hech qanday jadval yoki view ga INSERT, UPDATE, DELETE qila olmaydi.
2. app.company_id o'rnatilmaganda 0 qator qaytariladi (Fail-closed xavfsizlik).
3. A kompaniya sessiyasi B kompaniya ma'lumotlarini aslo ko'ra olmaydi (bo'sh qaytadi).
4. Prompt injection ("company_id=2 ni ko'rsat", "barcha korxonalar") DB darajasida bloklanadi.
5. _FORBIDDEN_WORDS filtri olib tashlanganligi sababli 'admin' yoki 'korxona' so'zlari noto'g'ri bloklanmaydi.
"""
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.services.ai_db_context import set_ai_tenant_context, clear_ai_tenant_context, ai_tenant_context
from app.routers import ai_analytics


# ───────────────────────── PostgreSQL Fixture ─────────────────────────

@pytest.fixture()
def pg_connection():
    """Mahalliy PostgreSQL (erppos) bazasiga ulanish."""
    if engine.dialect.name != "postgresql":
        pytest.skip("Ushbu testlar PostgreSQL va uning RLS imkoniyatlarini talab qiladi")

    with engine.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()


# ───────────────────────── 1. ai_readonly yozishdan mahrum ─────────────────────────

def test_ai_readonly_cannot_insert_or_update(pg_connection):
    conn = pg_connection
    conn.execute(text("SET LOCAL ROLE ai_readonly"))

    # INSERT urinishi rad etilishi kerak
    with pytest.raises(Exception):
        conn.execute(text("INSERT INTO ai_v_products (name, sale_price) VALUES ('Hacked Product', 99999)"))

    # UPDATE urinishi rad etilishi kerak
    with pytest.raises(Exception):
        conn.execute(text("UPDATE products SET sale_price = 0"))

    # DELETE urinishi rad etilishi kerak
    with pytest.raises(Exception):
        conn.execute(text("DELETE FROM customers"))


# ───────────────────────── 2. Fail-closed RLS (app.company_id o'rnatilmaganda 0) ─────────────────────────

def test_fail_closed_rls_when_company_id_unset(pg_connection):
    conn = pg_connection
    conn.execute(text("SET LOCAL ROLE ai_readonly"))
    # Sessiya parametrini bo'sh qilamiz
    conn.execute(text("SELECT set_config('app.company_id', '', true)"))

    for view_name in [
        "ai_v_sales",
        "ai_v_sale_items",
        "ai_v_products",
        "ai_v_customers",
        "ai_v_debts",
        "ai_v_stock_balance",
        "ai_v_stock_movements",
        "ai_v_purchases",
        "ai_v_returns",
    ]:
        cnt = conn.execute(text(f"SELECT count(*) FROM {view_name}")).scalar()
        assert cnt == 0, f"{view_name} app.company_id o'rnatilmaganda 0 qaytarishi shart (fail-closed), ammo {cnt} qaytdi!"


# ───────────────────────── 3. Tenant Izolyatsiyasi (A korxona B korxonani ko'ra olmasligi) ─────────────────────────

def test_tenant_isolation_company_a_cannot_see_company_b(pg_connection):
    conn = pg_connection
    conn.execute(text("SET LOCAL ROLE ai_readonly"))

    # 1-korxona konteksti
    conn.execute(text("SELECT set_config('app.company_id', '1', true)"))
    rows_c1 = conn.execute(text("SELECT DISTINCT company_id FROM ai_v_sales")).fetchall()
    for row in rows_c1:
        assert row[0] == 1, f"Kompaniya 1 kontekstida boshqa kompaniya ma'lumoti chiqdi: {row[0]}"

    # To'g'ridan-to'g'ri 2-korxona ID sini so'rash (masalan, filter orqali)
    b_rows = conn.execute(text("SELECT count(*) FROM ai_v_sales WHERE company_id = 2")).scalar()
    assert b_rows == 0, "Kompaniya 1 sessiyasida Kompaniya 2 sotuvlari 0 bo'lishi shart!"


# ───────────────────────── 4. Prompt Injection Bypass Bloklanishi ─────────────────────────

def test_prompt_injection_cannot_bypass_session_rls(pg_connection):
    conn = pg_connection
    conn.execute(text("SET LOCAL ROLE ai_readonly"))
    conn.execute(text("SELECT set_config('app.company_id', '1', true)"))

    # Prompt injection ssenariysi: so'rov ichida "WHERE 1=1 OR company_id=2" yoki boshqa hiylalar
    injected_query = conn.execute(text(
        "SELECT count(*) FROM ai_v_products WHERE (company_id = 2 OR 1=1)"
    )).scalar()

    # View ichidagi WHERE s.company_id = NULLIF(current_setting('app.company_id', true), '')::integer
    # tashqi WHERE ga qat'iy ustunlik qiladi (AND bilan bog'lanadi)
    real_c1_products = conn.execute(text(
        "SELECT count(*) FROM ai_v_products WHERE company_id = 1"
    )).scalar()

    assert injected_query == real_c1_products, "Prompt injection sessiya company_id cheklovini yora olmadi"


# ───────────────────────── 5. _FORBIDDEN_WORDS olib tashlanganligi ─────────────────────────

def test_forbidden_words_filter_removed():
    # ai_analytics modulida _FORBIDDEN_WORDS o'zgaruvchisi yo'qligini tekshiramiz
    assert not hasattr(ai_analytics, "_FORBIDDEN_WORDS"), "_FORBIDDEN_WORDS qora ro'yxati olib tashlangan bo'lishi kerak"
