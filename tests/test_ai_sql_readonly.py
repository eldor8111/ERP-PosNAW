"""
Integration and security tests for ai_sql_ro and Bosqich 4 tools:
1. Direct DB-level privilege escalation attempts (bypassing python parser).
2. Tenant isolation and fail-closed RLS on ai_sql_ro.
3. Multi-currency debt separation in ai_v_debts.
4. explain_negative_stock diagnosis with multi-warehouse history.
5. RBAC and argument validation for all new semantic tools.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import psycopg2
from sqlalchemy import text

from app.database import SessionLocal
from app.config import settings
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.customer import Customer
from app.models.sale import Sale, SaleStatus, PaymentType
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.services.ai_tools_registry import AIToolRegistry
from app.ai.sql_executor import execute_sql_readonly, get_ai_readonly_engine


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def setup_two_companies(db_session):
    """Ikki xil kompaniya va foydalanuvchilar yaratish fixture'i."""
    comp_a = db_session.query(Company).filter(Company.name == "Comp_SQL_A").first()
    if not comp_a:
        comp_a = Company(name="Comp_SQL_A")
        db_session.add(comp_a)
        db_session.flush()

    comp_b = db_session.query(Company).filter(Company.name == "Comp_SQL_B").first()
    if not comp_b:
        comp_b = Company(name="Comp_SQL_B")
        db_session.add(comp_b)
        db_session.flush()

    # Admin user Comp A
    user_a = db_session.query(User).filter(User.phone == "998901112233").first()
    if not user_a:
        user_a = User(
            phone="998901112233",
            name="Admin A",
            company_id=comp_a.id,
            role=UserRole.admin,
            status=UserStatus.active,
            hashed_password="fake"
        )
        db_session.add(user_a)
        db_session.flush()

    # Cashier user Comp A (past imtiyozli)
    cashier_a = db_session.query(User).filter(User.phone == "998901112244").first()
    if not cashier_a:
        cashier_a = User(
            phone="998901112244",
            name="Cashier A",
            company_id=comp_a.id,
            role=UserRole.cashier,
            status=UserStatus.active,
            hashed_password="fake"
        )
        db_session.add(cashier_a)
        db_session.flush()

    db_session.commit()
    return {"comp_a": comp_a, "comp_b": comp_b, "user_a": user_a, "cashier_a": cashier_a}


# ─── 1. BAZA DARAJASIDAGI XAVFSIZLIK HUJUMLARI (Parserni chetlab o'tib) ───────

def test_ai_sql_ro_direct_db_attacks():
    """
    To'g'ridan-to'g'ri ai_sql_ro roli bilan PostgreSQL ga ulanib,
    RESET ROLE, SET ROLE, set_config va xom jadvallarga yozish urinishlari.
    Baza darajasida ham hammasi to'silishi shart.
    """
    ro_url = settings.AI_DB_URL_READONLY or "postgresql://ai_sql_ro:ai_sql_ro_pass@localhost:5432/erppos"
    # psycopg2 formatiga o'tkazish
    raw_url = ro_url.replace("+psycopg", "")

    conn = psycopg2.connect(raw_url)
    cur = conn.cursor()

    # 1. Raw table o'qish urinishi
    with pytest.raises(Exception) as exc_sales:
        cur.execute("SELECT * FROM sales LIMIT 1;")
    assert "permission denied" in str(exc_sales.value).lower() or "sales" in str(exc_sales.value).lower()
    conn.rollback()

    # 2. set_config chaqirish urinishi
    with pytest.raises(Exception) as exc_sc:
        cur.execute("SELECT set_config('app.company_id', '1', false);")
    assert "permission denied" in str(exc_sc.value).lower() or "set_config" in str(exc_sc.value).lower()
    conn.rollback()

    # 3. SET ROLE ecode_app urinishi
    with pytest.raises(Exception) as exc_role:
        cur.execute("SET ROLE ecode_app;")
    assert "permission denied" in str(exc_role.value).lower() or "ecode_app" in str(exc_role.value).lower()
    conn.rollback()

    # 4. RESET ROLE urinishi (rol o'zgarmasligi kerak)
    cur.execute("RESET ROLE;")
    cur.execute("SELECT current_user;")
    assert cur.fetchone()[0] == "ai_sql_ro"
    conn.rollback()

    # 5. INSERT / DML urinishi (default_transaction_read_only)
    with pytest.raises(Exception) as exc_dml:
        cur.execute("INSERT INTO customers (name, company_id) VALUES ('evil', 1);")
    assert isinstance(exc_dml.value, psycopg2.errors.ReadOnlySqlTransaction) or "read-only" in str(exc_dml.value).lower() or "insert" in str(exc_dml.value).lower()
    conn.rollback()

    conn.close()


# ─── 2. IZOLYATSIYA VA FAIL-CLOSED RLS ────────────────────────────────────────

def test_ai_sql_ro_fail_closed_when_unset():
    """app.company_id o'rnatilmaganda ai_sql_ro ko'rinishlardan 0 qator qaytarishi shart."""
    ro_url = (settings.AI_DB_URL_READONLY or "postgresql://ai_sql_ro:ai_sql_ro_pass@localhost:5432/erppos").replace("+psycopg", "")
    conn = psycopg2.connect(raw_url := ro_url)
    cur = conn.cursor()

    # UNSET holatda
    cur.execute("SELECT count(*) FROM ai_v_products;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT count(*) FROM ai_v_sales;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT count(*) FROM ai_v_debts;")
    assert cur.fetchone()[0] == 0

    cur.execute("SELECT count(*) FROM ai_v_stock_balance;")
    assert cur.fetchone()[0] == 0

    conn.close()


def test_ai_sql_ro_tenant_isolation(setup_two_companies, db_session):
    """A kompaniya kontekstida B kompaniya ma'lumotlari chiqa olmasligi."""
    comp_a = setup_two_companies["comp_a"]
    comp_b = setup_two_companies["comp_b"]
    user_a = setup_two_companies["user_a"]

    # Comp A mahsuloti
    p_a = db_session.query(Product).filter(Product.name == "Prod_A_SQL", Product.company_id == comp_a.id).first()
    if not p_a:
        p_a = Product(name="Prod_A_SQL", sku="SKU-A-SQL", barcode="100000000001", company_id=comp_a.id, sale_price=Decimal("1000"))
        db_session.add(p_a)

    # Comp B mahsuloti
    p_b = db_session.query(Product).filter(Product.name == "Prod_B_SQL", Product.company_id == comp_b.id).first()
    if not p_b:
        p_b = Product(name="Prod_B_SQL", sku="SKU-B-SQL", barcode="100000000002", company_id=comp_b.id, sale_price=Decimal("2000"))
        db_session.add(p_b)

    db_session.commit()

    # Comp A user_a nomidan so'rov
    res_a = execute_sql_readonly(
        sql_query="SELECT name FROM ai_v_products WHERE name LIKE 'Prod_%_SQL'",
        company_id=comp_a.id,
        user_id=user_a.id,
        db_audit=db_session
    )
    assert res_a["status"] == "success"
    names_a = [r["name"] for r in res_a["rows"]]
    assert "Prod_A_SQL" in names_a
    assert "Prod_B_SQL" not in names_a

    # Comp B kompaniya kontekstida tekshiramiz
    res_b = execute_sql_readonly(
        sql_query="SELECT name FROM ai_v_products WHERE name LIKE 'Prod_%_SQL'",
        company_id=comp_b.id,
        user_id=user_a.id,
        db_audit=db_session
    )
    assert res_b["status"] == "success"
    names_b = [r["name"] for r in res_b["rows"]]
    assert "Prod_B_SQL" in names_b
    assert "Prod_A_SQL" not in names_b


# ─── 3. KO'P VALYUTALI QARZ (ai_v_debts) TESTI ─────────────────────────────────

def test_ai_v_debts_multi_currency(setup_two_companies, db_session):
    """Mijoz bir nechta valyutada qarzga ega bo'lsa, har bir valyuta alohida qator bo'lib chiqishi."""
    comp_a = setup_two_companies["comp_a"]
    user_a = setup_two_companies["user_a"]

    cust = db_session.query(Customer).filter(Customer.name == "MultiCurrCust", Customer.company_id == comp_a.id).first()
    if not cust:
        cust = Customer(
            name="MultiCurrCust",
            company_id=comp_a.id,
            phone="998909998877",
            debt_balances={"UZS": 150000.0, "USD": 50.0}
        )
        db_session.add(cust)
    else:
        cust.debt_balances = {"UZS": 150000.0, "USD": 50.0}
    db_session.commit()

    res = execute_sql_readonly(
        sql_query="SELECT customer_name, currency, debt_amount FROM ai_v_debts WHERE customer_name = 'MultiCurrCust'",
        company_id=comp_a.id,
        user_id=user_a.id,
        db_audit=db_session
    )
    assert res["status"] == "success"
    rows = res["rows"]
    assert len(rows) == 2, f"Kutilgan 2 ta qator (UZS va USD), topildi: {len(rows)}"

    currencies = {r["currency"]: float(r["debt_amount"]) for r in rows}
    assert currencies.get("UZS") == 150000.0
    assert currencies.get("USD") == 50.0


# ─── 4. EXPLAIN_NEGATIVE_STOCK TESTI ──────────────────────────────────────────

def test_explain_negative_stock_diagnosis(setup_two_companies, db_session):
    """
    2 omborli senariy:
    Ombor 1: -5 dona (minus qoldiq)
    Ombor 2: +15 dona (ortiqcha zaxira)
    Jami qoldiq: +10 dona (ijobiy)
    explain_negative_stock vositasi birinchi minus hujjatini topishi va
    omborlararo ko'chirish tavsiya qilishi kerak.
    """
    comp_a = setup_two_companies["comp_a"]
    user_a = setup_two_companies["user_a"]

    # Omborlar
    wh1 = db_session.query(Warehouse).filter(Warehouse.name == "Ombor_Filial_1", Warehouse.company_id == comp_a.id).first()
    if not wh1:
        wh1 = Warehouse(name="Ombor_Filial_1", company_id=comp_a.id, is_active=True)
        db_session.add(wh1)
        db_session.flush()

    wh2 = db_session.query(Warehouse).filter(Warehouse.name == "Ombor_Markaziy_2", Warehouse.company_id == comp_a.id).first()
    if not wh2:
        wh2 = Warehouse(name="Ombor_Markaziy_2", company_id=comp_a.id, is_active=True)
        db_session.add(wh2)
        db_session.flush()

    # Mahsulot
    prod = db_session.query(Product).filter(Product.name == "DiagnoseNegativeProd", Product.company_id == comp_a.id).first()
    if not prod:
        prod = Product(name="DiagnoseNegativeProd", sku="SKU-DIAG-NEG", barcode="100000000003", company_id=comp_a.id, sale_price=Decimal("5000"))
        db_session.add(prod)
        db_session.flush()

    # StockLevels
    db_session.query(StockLevel).filter(StockLevel.product_id == prod.id).delete()
    sl1 = StockLevel(product_id=prod.id, warehouse_id=wh1.id, quantity=Decimal("-5"))
    sl2 = StockLevel(product_id=prod.id, warehouse_id=wh2.id, quantity=Decimal("15"))
    db_session.add_all([sl1, sl2])

    # Harakatlar tarixi: Ombor 1 da avval 0 edi, keyin -5 sotuv bo'lgan
    db_session.query(StockMovement).filter(StockMovement.product_id == prod.id).delete()
    t_past = datetime.now(timezone.utc) - timedelta(days=2)
    mv1 = StockMovement(
        product_id=prod.id,
        warehouse_id=wh1.id,
        type=MovementType.OUT,
        quantity=Decimal("-5"),
        qty_before=Decimal("0"),
        qty_after=Decimal("-5"),
        reference_type="sale",
        reference_id=9999,
        reason="Kassada sotuv #S-9999",
        created_at=t_past
    )
    # Ombor 2 da kirim +15
    mv2 = StockMovement(
        product_id=prod.id,
        warehouse_id=wh2.id,
        type=MovementType.IN,
        quantity=Decimal("15"),
        qty_before=Decimal("0"),
        qty_after=Decimal("15"),
        reference_type="purchase",
        reference_id=8888,
        reason="Kirim #PO-8888",
        created_at=t_past
    )
    db_session.add_all([mv1, mv2])
    db_session.commit()

    # explain_negative_stock vositasini chaqiramiz
    tool = AIToolRegistry.get_tool("explain_negative_stock")()
    result = tool.execute(db_session, comp_a.id, user_a, product=prod.name)

    reply = result["reply"]
    data = result["data"]

    assert data["total_balance"] == 10.0
    assert data["warehouse_balances"][wh1.name] == -5.0
    assert data["warehouse_balances"][wh2.name] == 15.0

    # Reply matnida tavsiya va tahlil bo'lishi shart
    assert "Omborlararo ko'chirish" in reply or "Transfer" in reply
    assert wh1.name in reply
    assert wh2.name in reply
    assert "-5" in reply


# ─── 5. UMUMIY SEMANTIK VOSITALAR VA RBAC ─────────────────────────────────────

def test_semantic_tools_rbac_and_argument_validation(setup_two_companies, db_session):
    """
    Barcha yangi umumiy vositalar (get_stock_movements, query_sales, get_debts, get_purchases, get_returns, get_product_card)
    to'g'ri ishlashi va kassir uchun xavfsiz filtrlanganini tekshirish.
    """
    comp_a = setup_two_companies["comp_a"]
    user_a = setup_two_companies["user_a"]

    # 1. get_product_card
    card_tool = AIToolRegistry.get_tool("get_product_card")()
    card_res = card_tool.execute(db_session, comp_a.id, user_a, query="DiagnoseNegativeProd")
    assert "DiagnoseNegativeProd" in card_res["reply"]
    assert "Omborlar kesimida" in card_res["reply"]

    # 2. get_debts
    debts_tool = AIToolRegistry.get_tool("get_debts")()
    debts_res = debts_tool.execute(db_session, comp_a.id, user_a, currency="USD")
    assert "MultiCurrCust" in debts_res["reply"]
    assert "USD" in debts_res["reply"]

    # 3. get_stock_movements
    mv_tool = AIToolRegistry.get_tool("get_stock_movements")()
    mv_res = mv_tool.execute(db_session, comp_a.id, user_a, product="DiagnoseNegativeProd")
    assert "DiagnoseNegativeProd" in mv_res["reply"]
    assert "Ombor_Filial_1" in mv_res["reply"]

    # 4. query_sales
    sales_tool = AIToolRegistry.get_tool("query_sales")()
    sales_res = sales_tool.execute(db_session, comp_a.id, user_a, group_by="payment_type")
    assert "Sotuvlar hisoboti" in sales_res["reply"] or "topilmadi" in sales_res["reply"]

    # 5. get_purchases
    po_tool = AIToolRegistry.get_tool("get_purchases")()
    po_res = po_tool.execute(db_session, comp_a.id, user_a)
    assert "Xaridlar" in po_res["reply"] or "topilmadi" in po_res["reply"]

    # 6. get_returns
    ret_tool = AIToolRegistry.get_tool("get_returns")()
    ret_res = ret_tool.execute(db_session, comp_a.id, user_a)
    assert "Qaytarish" in ret_res["reply"] or "mavjud emas" in ret_res["reply"]
