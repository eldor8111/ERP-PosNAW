"""Bosqich 3: Semantik Ko'rinishlar (ai_v_*), Ombor Qoldiqlari va Tenant Izolyatsiyasi Testlari.

Ushbu test to'plami quyidagilarni tekshiradi:
1. Fail-closed RLS: app.company_id o'rnatilmaganda barcha 9 ta ko'rinish 0 qator qaytaradi.
2. Qat'iy tenant izolyatsiyasi: Kompaniya A va B ma'lumotlari bir-biriga aslo aralashmaydi.
3. Ombor qoldiqlari va harakatlari:
   - ai_v_stock_movements da running_balance (yig'ilgan qoldiq) har bir ombor bo'yicha hisoblanadi.
   - Minusga tushgan tovar holati: 2 ombor, bitta omborda minus (-5), ikkinchisida (15), jami qoldiq (10).
   - 5 ta asosiy hujjat turi: sotuv, xarid, qaytarish, ko'chirish, inventarizatsiya.
   - Kontragentlar (mijoz va ta'minotchi nomlari) to'g'ri bog'lanishi.
4. SMS vositalari HIGH xavf darajasi va pending_actions orqali tasdiqlash:
   - send_customer_sms va draft_sms_campaign HIGH riskda.
   - Kartochkada qabul qiluvchilar soni va xabar matni namunasi ko'rinishi.
   - read_only=False bo'lishining sababi: SMS yuborilganda SMSLog jadvaliga yoziladi.
5. Cross-company ID buzishga urinishlar (tampering):
   - Kompaniya A foydalanuvchisi Kompaniya B mijoz/tovar/ombor ID lari bilan amal yaratsa rad etiladi.
   - Kompaniya A foydalanuvchisi Kompaniya B amalini tasdiqlashga urinsa rad etiladi.
6. AI analitika va xulosalar izolyatsiyasi:
   - /ai/weekly-chart, /ai/debt-analytics, /ai/recommendations endpointlari faqat joriy korxona ma'lumotlarini qaytaradi.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine
from app.models.user import User, UserRole
from app.models.pending_action import PendingAction
from app.services.ai_tools_registry import AIToolRegistry, validate_arguments_company_ownership
from app.routers.ai_analytics import (
    confirm_ai_action,
    ConfirmRequest,
    get_weekly_chart,
    get_debt_analytics,
    get_ai_recommendations,
)


ALL_SEMANTIC_VIEWS = [
    "ai_v_sales",
    "ai_v_sale_items",
    "ai_v_products",
    "ai_v_customers",
    "ai_v_debts",
    "ai_v_stock_balance",
    "ai_v_stock_movements",
    "ai_v_purchases",
    "ai_v_returns",
]


@pytest.fixture()
def seeded_db():
    """PostgreSQL bazasida Kompaniya A (201) va Kompaniya B (202) uchun to'liq test muhitini yaratish."""
    if engine.dialect.name != "postgresql":
        pytest.skip("Ushbu testlar PostgreSQL va RLS imkoniyatlarini talab qiladi")

    with engine.connect() as conn:
        trans = conn.begin()
        db = Session(bind=conn)

        # 1. Kompaniyalar
        conn.execute(text("""
            INSERT INTO companies (id, name, balance)
            VALUES 
            (201, 'Kompaniya A', 0.0),
            (202, 'Kompaniya B', 0.0)
            ON CONFLICT (id) DO NOTHING
        """))

        # 2. Foydalanuvchilar
        conn.execute(text("""
            INSERT INTO users (id, company_id, name, phone, hashed_password, role, status)
            VALUES 
            (2011, 201, 'Admin A', '+998901111111', 'hash', 'admin', 'active'),
            (2021, 202, 'Admin B', '+998902222222', 'hash', 'admin', 'active')
            ON CONFLICT (id) DO NOTHING
        """))

        # 3. Valyutalar
        conn.execute(text("""
            INSERT INTO currencies (id, company_id, name, code, rate, is_default, is_active)
            VALUES
            (2011, 201, 'So''m', 'UZS', 1.0, true, true),
            (2021, 202, 'So''m', 'UZS', 1.0, true, true)
            ON CONFLICT (id) DO NOTHING
        """))

        # 4. Omborlar (Kompaniya A da 2 ta: Asosiy va Filial; Kompaniya B da 1 ta)
        conn.execute(text("""
            INSERT INTO warehouses (id, company_id, name)
            VALUES
            (2011, 201, 'Ombor A1 Asosiy'),
            (2012, 201, 'Ombor A2 Filial'),
            (2021, 202, 'Ombor B1 Asosiy')
            ON CONFLICT (id) DO NOTHING
        """))

        # 5. Mijozlar va qarzdorlik
        conn.execute(text("""
            INSERT INTO customers (id, company_id, name, phone, debt_balance)
            VALUES
            (2011, 201, 'Mijoz A1', '+998901111111', 150000.0),
            (2021, 202, 'Mijoz B1', '+998902222222', 250000.0)
            ON CONFLICT (id) DO NOTHING
        """))

        # 6. Yetkazib beruvchilar
        conn.execute(text("""
            INSERT INTO suppliers (id, company_id, name, phone)
            VALUES
            (2011, 201, 'Ta''minotchi A1', '+998911111111'),
            (2021, 202, 'Ta''minotchi B1', '+998922222222')
            ON CONFLICT (id) DO NOTHING
        """))

        # 7. Mahsulotlar (Kompaniya A da Sut va Non, Kompaniya B da Choy)
        conn.execute(text("""
            INSERT INTO products (id, company_id, name, sku, barcode, unit, product_type, sale_price, cost_price, sale_currency, cost_currency, is_deleted)
            VALUES
            (2011, 201, 'Mahsulot A1 Sut', 'SKU-A1', '111111', 'dona', 'standard', 12000, 9000, 'UZS', 'UZS', false),
            (2012, 201, 'Mahsulot A2 Non', 'SKU-A2', '111112', 'dona', 'standard', 5000, 3500, 'UZS', 'UZS', false),
            (2021, 202, 'Mahsulot B1 Choy', 'SKU-B1', '222221', 'dona', 'standard', 25000, 18000, 'UZS', 'UZS', false)
            ON CONFLICT (id) DO NOTHING
        """))

        # 8. Qoldiqlar (Stock Levels): Mahsulot A1 Ombor 1 da -5.0 (minus), Ombor 2 da 15.0 -> Jami 10.0
        # Mahsulot A2 Ombor 1 da 3.0 (< 10) -> kam qolgan tovar tavsiyasi uchun
        conn.execute(text("""
            INSERT INTO stock_levels (id, product_id, warehouse_id, quantity)
            VALUES
            (2011, 2011, 2011, -5.0),
            (2012, 2011, 2012, 15.0),
            (2013, 2012, 2011, 3.0),
            (2021, 2021, 2021, 50.0)
            ON CONFLICT (id) DO NOTHING
        """))

        # 9. Sotuvlar va Qaytarishlar (Kompaniya A da bitta sotuv, bitta qaytarish R-2011)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(text(f"""
            INSERT INTO sales (id, company_id, number, customer_id, warehouse_id, cashier_id, total_amount, paid_amount, currency_id, status, payment_type, created_at)
            VALUES
            (2011, 201, 'S-2011', 2011, 2011, 2011, 180000, 30000, 2011, 'completed', 'cash', '{today_str}'),
            (2012, 201, 'R-2011', 2011, 2011, 2011, 12000, 12000, 2011, 'refunded', 'cash', '{today_str}'),
            (2021, 202, 'S-2021', 2021, 2021, 2021, 250000, 0, 2021, 'completed', 'debt', '{today_str}')
            ON CONFLICT (id) DO NOTHING
        """))

        # 10. Sotuv tarkibi (Sale Items)
        conn.execute(text("""
            INSERT INTO sale_items (id, sale_id, product_id, quantity, unit_price, cost_price, subtotal)
            VALUES
            (2011, 2011, 2011, 15, 12000, 9000, 180000),
            (2021, 2021, 2021, 10, 25000, 18000, 250000)
            ON CONFLICT (id) DO NOTHING
        """))

        # 11. Xarid buyurtmalari (Purchase Orders)
        conn.execute(text("""
            INSERT INTO purchase_orders (id, company_id, number, supplier_id, warehouse_id, total_amount, paid_amount, status, currency, created_by)
            VALUES
            (2011, 201, 'PO-2011', 2011, 2011, 90000, 90000, 'received', 'UZS', 2011),
            (2012, 201, 'PO-2012', 2011, 2012, 180000, 180000, 'received', 'UZS', 2011),
            (2021, 202, 'PO-2021', 2021, 2021, 900000, 500000, 'received', 'UZS', 2021)
            ON CONFLICT (id) DO NOTHING
        """))

        # 12. Ko'chirish va Inventarizatsiya hujjatlari
        conn.execute(text("""
            INSERT INTO stock_transfers (id, number, from_warehouse_id, to_warehouse_id, status, created_by)
            VALUES
            (2011, 'TR-2011', 2011, 2012, 'received', 2011)
            ON CONFLICT (id) DO NOTHING
        """))
        conn.execute(text("""
            INSERT INTO inventory_counts (id, number, warehouse_id, status, created_by)
            VALUES
            (2011, 'INV-2011', 2011, 'completed', 2011)
            ON CONFLICT (id) DO NOTHING
        """))

        # 13. Ombor harakatlari (Stock Movements):
        # Ombor 1: 10 IN (PO-2011), 15 OUT (S-2011) => qoldiq -5
        # Ombor 2: 20 IN (PO-2012), 5 OUT (S-2011) => qoldiq 15
        # Ko'chirish (TRANSFER_OUT: TR-2011), Qaytarish (RETURN: R-2011), Inventarizatsiya (ADJUST: INV-2011)
        conn.execute(text("""
            INSERT INTO stock_movements (id, product_id, warehouse_id, type, qty_before, qty_after, quantity, reference_type, reference_id, created_at)
            VALUES
            (2011, 2011, 2011, 'IN', 0, 10, 10, 'purchase', 2011, '2026-10-01 10:00:00'),
            (2012, 2011, 2011, 'OUT', 10, -5, 15, 'sale', 2011, '2026-10-01 11:00:00'),
            (2013, 2011, 2012, 'IN', 0, 20, 20, 'purchase', 2012, '2026-10-01 10:30:00'),
            (2014, 2011, 2012, 'OUT', 20, 15, 5, 'sale', 2011, '2026-10-01 12:00:00'),
            (2015, 2012, 2011, 'TRANSFER_OUT', 10, 5, 5, 'transfer', 2011, '2026-10-02 10:00:00'),
            (2016, 2011, 2011, 'RETURN', -5, -4, 1, 'sale', 2012, '2026-10-02 11:00:00'),
            (2017, 2011, 2011, 'ADJUST', -4, -4, 0, 'inventory', 2011, '2026-10-02 12:00:00'),
            (2021, 2021, 2021, 'IN', 0, 50, 50, 'purchase', 2021, '2026-10-01 10:00:00')
            ON CONFLICT (id) DO NOTHING
        """))

        yield conn, db

        trans.rollback()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fail-closed RLS: app.company_id o'rnatilmaganda 0 qator
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_views_fail_closed_when_unset(seeded_db):
    conn, _ = seeded_db
    conn.execute(text("SET LOCAL ROLE ai_readonly"))
    conn.execute(text("SELECT set_config('app.company_id', '', true)"))

    for view_name in ALL_SEMANTIC_VIEWS:
        count = conn.execute(text(f"SELECT count(*) FROM {view_name}")).scalar()
        assert count == 0, f"Fail-closed buzildi: {view_name} app.company_id o'rnatilmaganda 0 bo'lishi shart, ammo {count} qaytdi!"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Qat'iy Tenant Izolyatsiyasi (Kompaniya A va B)
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_views_strict_tenant_isolation(seeded_db):
    conn, _ = seeded_db
    conn.execute(text("SET LOCAL ROLE ai_readonly"))

    # A) Kompaniya A (201) sessiyasi
    conn.execute(text("SELECT set_config('app.company_id', '201', true)"))
    for view_name in ALL_SEMANTIC_VIEWS:
        # 1. Barcha qaytgan qatorlarning company_id si 201 bo'lishi kerak
        rows = conn.execute(text(f"SELECT DISTINCT company_id FROM {view_name}")).fetchall()
        for r in rows:
            assert r[0] == 201, f"{view_name} da Kompaniya 201 sessiyasida boshqa korxona ma'lumoti chiqdi: {r[0]}"

        # 2. Kompaniya B (202) ID si bilan qidirilganda doimo 0 qaytishi kerak
        b_count = conn.execute(text(f"SELECT count(*) FROM {view_name} WHERE company_id = 202")).scalar()
        assert b_count == 0, f"{view_name} da Kompaniya B ma'lumotlari sizib chiqdi!"

    # B) Kompaniya B (202) sessiyasi
    conn.execute(text("SELECT set_config('app.company_id', '202', true)"))
    for view_name in ALL_SEMANTIC_VIEWS:
        rows = conn.execute(text(f"SELECT DISTINCT company_id FROM {view_name}")).fetchall()
        for r in rows:
            assert r[0] == 202, f"{view_name} da Kompaniya 202 sessiyasida boshqa korxona ma'lumoti chiqdi: {r[0]}"

        a_count = conn.execute(text(f"SELECT count(*) FROM {view_name} WHERE company_id = 201")).scalar()
        assert a_count == 0, f"{view_name} da Kompaniya A ma'lumotlari sizib chiqdi!"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ombor Qoldiqlari, Running Balance va Minusga Tushgan Tovar Tekshiruvi
# ─────────────────────────────────────────────────────────────────────────────

def test_stock_movements_running_balance_and_negative_stock(seeded_db):
    conn, _ = seeded_db
    conn.execute(text("SET LOCAL ROLE ai_readonly"))
    conn.execute(text("SELECT set_config('app.company_id', '201', true)"))

    # 1. ai_v_stock_balance tekshiruvi:
    # Mahsulot A1 (Sut):
    # - Ombor A1 da: quantity = -5.0
    # - Ombor A2 da: quantity = 15.0
    # - Har ikkala qatorda total_quantity (barcha omborlar jami) = 10.0
    sb_rows = conn.execute(text("""
        SELECT warehouse_name, quantity, total_quantity, sale_currency, cost_currency, total_cost_value
        FROM ai_v_stock_balance
        WHERE product_name = 'Mahsulot A1 Sut'
        ORDER BY warehouse_name ASC
    """)).fetchall()

    assert len(sb_rows) == 2, f"Kutilgan 2 ta ombor qoldig'i, ammo {len(sb_rows)} ta qaytdi"
    ombor1, ombor2 = sb_rows[0], sb_rows[1]

    # Ombor A1 Asosiy (minus holati)
    assert ombor1[0] == "Ombor A1 Asosiy"
    assert Decimal(str(ombor1[1])) == Decimal("-5.000")
    assert Decimal(str(ombor1[2])) == Decimal("10.000") # Jami qoldiq: -5 + 15 = 10
    assert ombor1[3] == "UZS"
    assert ombor1[4] == "UZS"
    assert Decimal(str(ombor1[5])) == Decimal("-45000.0000000") # -5 * 9000

    # Ombor A2 Filial (musbat holat)
    assert ombor2[0] == "Ombor A2 Filial"
    assert Decimal(str(ombor2[1])) == Decimal("15.000")
    assert Decimal(str(ombor2[2])) == Decimal("10.000") # Jami qoldiq bir xil
    assert Decimal(str(ombor2[5])) == Decimal("135000.0000000") # 15 * 9000

    # 2. ai_v_stock_movements xronologiyasi va running_balance tekshiruvi
    sm_rows = conn.execute(text("""
        SELECT warehouse_name, document_type, document_number, counterparty, signed_quantity, running_balance
        FROM ai_v_stock_movements
        WHERE product_name = 'Mahsulot A1 Sut'
        ORDER BY warehouse_name ASC, id ASC
    """)).fetchall()

    # Ombor 1 harakatlari:
    # Harakat 1 (xarid): +10 -> running_balance = 10
    # Harakat 2 (sotuv): -15 -> running_balance = -5
    ombor1_moves = [m for m in sm_rows if m[0] == "Ombor A1 Asosiy"]
    assert len(ombor1_moves) >= 2
    assert ombor1_moves[0][1] == "xarid"
    assert ombor1_moves[0][2] == "PO-2011"
    assert ombor1_moves[0][3] == "Ta'minotchi A1"
    assert Decimal(str(ombor1_moves[0][4])) == Decimal("10.000")
    assert Decimal(str(ombor1_moves[0][5])) == Decimal("10.000")

    assert ombor1_moves[1][1] == "sotuv"
    assert ombor1_moves[1][2] == "S-2011"
    assert ombor1_moves[1][3] == "Mijoz A1"
    assert Decimal(str(ombor1_moves[1][4])) == Decimal("-15.000")
    assert Decimal(str(ombor1_moves[1][5])) == Decimal("-5.000") # Minusga tushdi

    # Ombor 2 harakatlari:
    # Harakat 1 (xarid): +20 -> running_balance = 20
    # Harakat 2 (sotuv): -5 -> running_balance = 15
    ombor2_moves = [m for m in sm_rows if m[0] == "Ombor A2 Filial"]
    assert len(ombor2_moves) >= 2
    assert ombor2_moves[0][1] == "xarid"
    assert ombor2_moves[0][2] == "PO-2012"
    assert Decimal(str(ombor2_moves[0][4])) == Decimal("20.000")
    assert Decimal(str(ombor2_moves[0][5])) == Decimal("20.000")

    assert ombor2_moves[1][1] == "sotuv"
    assert Decimal(str(ombor2_moves[1][4])) == Decimal("-5.000")
    assert Decimal(str(ombor2_moves[1][5])) == Decimal("15.000")

    # 3. Hujjat turlari to'liqligi tekshiruvi:
    all_doc_types = conn.execute(text("SELECT DISTINCT document_type FROM ai_v_stock_movements")).fetchall()
    doc_types_set = {d[0] for d in all_doc_types}
    for expected_type in ["sotuv", "xarid", "qaytarish", "ko'chirish", "inventarizatsiya"]:
        assert expected_type in doc_types_set, f"Hujjat turi '{expected_type}' ai_v_stock_movements da topilmadi!"


# ─────────────────────────────────────────────────────────────────────────────
# 4. SMS Vositalari HIGH Xavf Darajasi va Tasdiqlash Nazorati
# ─────────────────────────────────────────────────────────────────────────────

def test_sms_tools_high_risk_and_action_card(seeded_db):
    _, db = seeded_db
    user_a = User(id=2011, company_id=201, role=UserRole.admin, name="Admin A")

    # A) send_customer_sms va draft_sms_campaign HIGH riskda bo'lishi
    sms_tool = AIToolRegistry.get_tool("send_customer_sms")
    campaign_tool = AIToolRegistry.get_tool("draft_sms_campaign")

    assert sms_tool.risk_level == "HIGH"
    assert campaign_tool.risk_level == "HIGH"
    assert sms_tool.read_only == False
    assert campaign_tool.read_only == False

    # B) send_customer_sms chaqirilganda darhol SMS jo'natmasdan PendingAction yaratishi
    res = AIToolRegistry.execute_tool(
        db=db,
        name="send_customer_sms",
        kwargs={"customer_id": 2011, "message": "Hurmatli mijoz, sizda 150 000 so'm nasiya mavjud."},
        user=user_a,
        prompt="Mijozga qarzini eslat"
    )

    assert res.get("action", {}).get("type") == "confirm_action"
    pending_id = res.get("action", {}).get("pending_action_id")
    assert pending_id, "pending_action_id qaytishi shart"

    # Kartochka va tavsifda qabul qiluvchilar soni va xabar matni namunasi ko'rinishi
    pa = db.query(PendingAction).filter(PendingAction.id == pending_id).first()
    assert pa is not None
    assert "1 ta mijozga" in pa.description
    assert "Hurmatli mijoz" in pa.description
    assert pa.status == "pending"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Cross-company ID Buzishga Urinishlar (Tampering Rejection)
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_company_id_tampering_rejected(seeded_db):
    _, db = seeded_db
    user_a = User(id=2011, company_id=201, role=UserRole.admin, name="Admin A")
    user_b = User(id=2021, company_id=202, role=UserRole.admin, name="Admin B")

    # 1. Kompaniya A foydalanuvchisi Kompaniya B mijoz ID si (2021) bilan amal yaratishga urinishi
    res_cust = AIToolRegistry.execute_tool(
        db=db,
        name="send_customer_sms",
        kwargs={"customer_id": 2021, "message": "Hujum"},
        user=user_a,
        prompt="Boshqa korxona mijoziga SMS"
    )
    assert "Xavfsizlik xatosi" in res_cust.get("reply", "")

    # 2. Kompaniya A foydalanuvchisi Kompaniya B tovar ID si (2021) bilan sotuv yaratishga urinishi
    res_prod = AIToolRegistry.execute_tool(
        db=db,
        name="create_sale",
        kwargs={"customer_id": 2011, "items": [{"product_id": 2021, "quantity": 1, "unit_price": 25000}]},
        user=user_a,
        prompt="Boshqa korxona tovarini sotish"
    )
    assert "Xavfsizlik xatosi" in res_prod.get("reply", "")

    # 3. Kompaniya A foydalanuvchisi Kompaniya B ning pending_action amalini tasdiqlashga urinishi
    pa_b = PendingAction(
        id="cross_pa_test",
        company_id=202,
        user_id=2021,
        tool_name="update_customer",
        tool_arguments={"customer_id": 2021, "new_phone": "+998909999999"},
        description="Mijozni yangilash",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(pa_b)
    db.flush()

    confirm_res = confirm_ai_action(
        request=ConfirmRequest(pending_action_id="cross_pa_test"),
        db=db,
        current_user=user_a
    )
    assert "Boshqa korxona amalini tasdiqlash taqiqlangan" in confirm_res.get("reply", "")


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Analitika va Insights Endpointlari Izolyatsiyasi
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_analytics_and_insights_isolation(seeded_db):
    _, db = seeded_db
    user_a = User(id=2011, company_id=201, role=UserRole.admin, name="Admin A")
    user_b = User(id=2021, company_id=202, role=UserRole.admin, name="Admin B")

    # 1. Weekly chart izolyatsiyasi
    chart_a = get_weekly_chart(db=db, current_user=user_a)
    chart_b = get_weekly_chart(db=db, current_user=user_b)
    total_a = sum(d["amount"] for d in chart_a["chart"])
    total_b = sum(d["amount"] for d in chart_b["chart"])
    assert total_a == 180000.0, f"Kompaniya A savdosi 180 000 bo'lishi kerak, ammo {total_a} chiqdi"
    assert total_b == 250000.0, f"Kompaniya B savdosi 250 000 bo'lishi kerak, ammo {total_b} chiqdi"

    # 2. Qarz tahlili (debt analytics) izolyatsiyasi
    debt_a = get_debt_analytics(db=db, current_user=user_a)
    debt_b = get_debt_analytics(db=db, current_user=user_b)
    assert float(debt_a.get("total_debt", 0)) == 150000.0
    assert float(debt_b.get("total_debt", 0)) == 250000.0

    # 3. AI tavsiyalari (recommendations) izolyatsiyasi
    recs_a = get_ai_recommendations(db=db, current_user=user_a)
    recs_b = get_ai_recommendations(db=db, current_user=user_b)
    types_a = [r["type"] for r in recs_a["recommendations"]]
    types_b = [r["type"] for r in recs_b["recommendations"]]

    # Kompaniya A da tovar qoldig'i 10 dan kam bo'lgan ombor bor (-5 + 15 = 10, ombor1 da -5 < 10)
    assert "low_stock" in types_a
    # Kompaniya B da qoldiq 50 ta (10 dan ko'p), shuning uchun low_stock bo'lmasligi kerak
    assert "low_stock" not in types_b
