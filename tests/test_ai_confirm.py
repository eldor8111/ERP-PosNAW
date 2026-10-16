"""AI Copilot HIGH xavf darajasidagi amallar va /ai/confirm xavfsizlik testlari.

Test qilinadigan talablar:
1. Barcha yozadigan tool'lar (create_product, create_customer, update_customer,
   update_product, create_sale, record_debt_payment, record_new_debt) HIGH darajada.
2. Tasdiqlashsiz bazaga hech narsa yozilmaydi — faqat pending_actions ga saqlanadi.
3. Ikki marta tasdiqlash rad etiladi (idempotentlik).
4. Muddati o'tgan (TTL) tasdiqlash rad etiladi.
5. Boshqa foydalanuvchi kartochkasini tasdiqlash rad etiladi.
6. Boshqa korxona (tenant) kartochkasini tasdiqlash rad etiladi.
7. Ruxsatsiz rol (masalan, kassir) HIGH amalni tasdiqlashga uringanda rad etiladi.
8. Klient argumentlarni almashtira olmaydi — faqat serverda saqlangan argumentlar bajariladi.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401
from app.models.company import Company
from app.models.user import User, UserRole
from app.models.product import Product
from app.models.customer import Customer
from app.models.pending_action import PendingAction
from app.models.ai_audit import AIAuditLog
from app.services.ai_tools_registry import AIToolRegistry
from app.services.ai_tools_crud import (
    CreateProductTool,
    CreateCustomerTool,
    UpdateCustomerTool,
    UpdateProductTool,
)
from app.services.ai_tools_sales import CreateSaleTool
from app.services.ai_tools_registry import RecordDebtPaymentTool, RecordNewDebtTool
from app.routers import ai_analytics


# ───────────────────────── 1. Xavf darajalari ─────────────────────────

def test_all_write_tools_are_high_risk():
    write_tools = [
        CreateProductTool,
        CreateCustomerTool,
        UpdateCustomerTool,
        UpdateProductTool,
        CreateSaleTool,
        RecordDebtPaymentTool,
        RecordNewDebtTool,
    ]
    for tool in write_tools:
        assert tool.risk_level == "HIGH", f"{tool.name} tool'i HIGH risk_level ga ega bo'lishi shart"


# ───────────────────────── DB Fixture ─────────────────────────

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Kerakli jadvallarni yaratamiz
    Company.__table__.create(bind=engine)
    User.__table__.create(bind=engine)
    Product.__table__.create(bind=engine)
    Customer.__table__.create(bind=engine)
    AIAuditLog.__table__.create(bind=engine)
    PendingAction.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    # Test korxona va foydalanuvchilar
    c1 = Company(id=1, name="Korxona 1")
    c2 = Company(id=2, name="Korxona 2")
    db.add_all([c1, c2])
    db.commit()

    u_admin = User(id=10, name="Admin User", phone="+998901111110", email="admin@c1.uz", company_id=1, role=UserRole.admin, hashed_password="pw")
    u_admin2 = User(id=11, name="Admin 2", phone="+998901111111", email="admin2@c1.uz", company_id=1, role=UserRole.admin, hashed_password="pw")
    u_cashier = User(id=12, name="Cashier User", phone="+998901111112", email="cashier@c1.uz", company_id=1, role=UserRole.cashier, hashed_password="pw")
    u_other_company = User(id=20, name="C2 Admin", phone="+998902222220", email="admin@c2.uz", company_id=2, role=UserRole.admin, hashed_password="pw")

    db.add_all([u_admin, u_admin2, u_cashier, u_other_company])
    db.commit()

    yield db
    db.close()


# ───────────────────────── 2. HIGH tool tasdiqlashsiz yozmasligi ─────────────────────────

def test_execute_tool_creates_pending_action_without_writing_to_entity_tables(db_session):
    admin = db_session.query(User).filter(User.id == 10).first()

    result = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Kutilayotgan Mijoz", "phone": "+998901234567"},
        user=admin,
        prompt="Yangi mijoz qo'sh",
        conversation_id="conv-1",
    )

    # 1. Mijozlar jadvaliga yozilmagan bo'lishi kerak
    cust = db_session.query(Customer).filter(Customer.name == "Kutilayotgan Mijoz").first()
    assert cust is None, "Tasdiqlanmagan amal mijozlar jadvaliga yozilmasligi kerak!"

    # 2. pending_actions jadvalida yozuv paydo bo'lishi kerak
    action_info = result.get("action", {})
    assert action_info.get("type") == "confirm_action"
    action_id = action_info.get("confirmation_id")
    assert action_id is not None

    pending = db_session.query(PendingAction).filter(PendingAction.id == action_id).first()
    assert pending is not None
    assert pending.status == "pending"
    assert pending.tool_name == "create_customer"
    assert pending.tool_arguments == {"name": "Kutilayotgan Mijoz", "phone": "+998901234567"}
    assert pending.company_id == 1
    assert pending.user_id == 10
    exp = pending.expires_at.replace(tzinfo=timezone.utc) if pending.expires_at.tzinfo is None else pending.expires_at
    assert exp > datetime.now(timezone.utc)


# ───────────────────────── 3. /ai/confirm muvaffaqiyatli ijro ─────────────────────────

def test_confirm_executes_successfully_and_records_entity(db_session):
    admin = db_session.query(User).filter(User.id == 10).first()

    # Pending action yaratamiz
    result = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Tasdiqlangan Mijoz", "phone": "+998907777777"},
        user=admin,
    )
    action_id = result["action"]["confirmation_id"]

    req = ai_analytics.ConfirmRequest(pending_action_id=action_id)
    confirm_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin)

    assert "Muvaffaqiyatli" in str(confirm_res) or "qo'shildi" in str(confirm_res) or "action" in confirm_res

    # Mijoz yaratilganini tekshiramiz
    cust = db_session.query(Customer).filter(Customer.name == "Tasdiqlangan Mijoz").first()
    assert cust is not None
    assert cust.phone == "+998907777777"
    assert cust.company_id == 1

    # PendingAction holati 'executed' bo'lganini tekshiramiz
    pending = db_session.query(PendingAction).filter(PendingAction.id == action_id).first()
    assert pending.status == "executed"
    assert pending.executed_at is not None


# ───────────────────────── 4. Ikki marta tasdiqlash rad etilishi (Idempotentlik) ─────────────────────────

def test_double_confirmation_fails(db_session):
    admin = db_session.query(User).filter(User.id == 10).first()

    res = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Bir Martalik Mijoz"},
        user=admin,
    )
    action_id = res["action"]["confirmation_id"]
    req = ai_analytics.ConfirmRequest(confirmation_id=action_id)

    # 1-marta tasdiqlash
    first_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin)
    assert "qo'shildi" in first_res.get("reply", "")

    # 2-marta tasdiqlash
    second_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin)
    assert "allaqachon tasdiqlangan" in second_res.get("reply", "")

    # Mijozlar soni faqat 1 ta bo'lishi kerak
    count = db_session.query(Customer).filter(Customer.name == "Bir Martalik Mijoz").count()
    assert count == 1


# ───────────────────────── 5. Muddati o'tgan (TTL) tasdiqlash ─────────────────────────

def test_expired_confirmation_fails(db_session):
    admin = db_session.query(User).filter(User.id == 10).first()

    past_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    pending = PendingAction(
        id="expired-action-123",
        company_id=1,
        user_id=10,
        tool_name="create_customer",
        tool_arguments={"name": "Kechikkan Mijoz"},
        description="Test",
        status="pending",
        created_at=past_time - timedelta(minutes=5),
        expires_at=past_time,
    )
    db_session.add(pending)
    db_session.commit()

    req = ai_analytics.ConfirmRequest(pending_action_id="expired-action-123")
    res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin)

    assert "muddati o'tib ketgan" in res.get("reply", "").lower()
    # Bazada status expired ga o'zgarishi kerak
    db_session.refresh(pending)
    assert pending.status == "expired"

    # Mijoz yaratilmagan bo'lishi kerak
    assert db_session.query(Customer).filter(Customer.name == "Kechikkan Mijoz").first() is None


# ───────────────────────── 6. Boshqa foydalanuvchi tasdiqlashga urinishi ─────────────────────────

def test_different_user_confirmation_fails(db_session):
    admin1 = db_session.query(User).filter(User.id == 10).first()
    admin2 = db_session.query(User).filter(User.id == 11).first()

    res = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Maxfiy Mijoz"},
        user=admin1,
    )
    action_id = res["action"]["confirmation_id"]

    # admin2 (boshqa user) tasdiqlashga urinadi
    req = ai_analytics.ConfirmRequest(confirmation_id=action_id)
    err_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin2)

    assert "faqat uni boshlagan foydalanuvchi" in err_res.get("reply", "")
    assert db_session.query(Customer).filter(Customer.name == "Maxfiy Mijoz").first() is None


# ───────────────────────── 7. Boshqa korxona (tenant) tasdiqlashga urinishi ─────────────────────────

def test_cross_company_confirmation_fails(db_session):
    admin1 = db_session.query(User).filter(User.id == 10).first()
    c2_admin = db_session.query(User).filter(User.id == 20).first()

    res = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Kompaniya 1 Mijoz"},
        user=admin1,
    )
    action_id = res["action"]["confirmation_id"]

    # c2_admin (Kompaniya 2) tasdiqlashga urinadi
    req = ai_analytics.ConfirmRequest(pending_action_id=action_id)
    err_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=c2_admin)

    assert "boshqa korxona" in err_res.get("reply", "").lower() or "faqat uni boshlagan" in err_res.get("reply", "").lower()
    assert db_session.query(Customer).filter(Customer.name == "Kompaniya 1 Mijoz").first() is None


# ───────────────────────── 8. Kassir HIGH amalni tasdiqlashga urinishi ─────────────────────────

def test_cashier_cannot_confirm_high_risk_action(db_session):
    cashier = db_session.query(User).filter(User.id == 12).first()

    # Pending action to'g'ridan-to'g'ri kassir nomidan yaratilgan deylik (yoki fake)
    pending = PendingAction(
        id="cashier-action-999",
        company_id=1,
        user_id=12,
        tool_name="create_product",
        tool_arguments={"name": "Kassir Mahsuloti", "sale_price": 50000},
        description="Test",
        status="pending",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(pending)
    db_session.commit()

    req = ai_analytics.ConfirmRequest(pending_action_id="cashier-action-999")
    res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=cashier)

    assert "ruxsat yo'q" in res.get("reply", "").lower()
    assert db_session.query(Product).filter(Product.name == "Kassir Mahsuloti").first() is None


# ───────────────────────── 9. Klient argumentlarni almashtira olmasligi ─────────────────────────

def test_client_cannot_tamper_with_arguments(db_session):
    admin = db_session.query(User).filter(User.id == 10).first()

    res = AIToolRegistry.execute_tool(
        db=db_session,
        name="create_customer",
        kwargs={"name": "Haqiqiy Mijoz", "phone": "+998901111111"},
        user=admin,
    )
    action_id = res["action"]["confirmation_id"]

    # ConfirmRequest faqat confirmation_id/pending_action_id qabul qiladi
    # Klient so'roviga boshqa maydonlar qo'shilsa ham, endpoint ularni olmaydi
    req = ai_analytics.ConfirmRequest(pending_action_id=action_id)

    confirm_res = ai_analytics.confirm_ai_action(request=req, db=db_session, current_user=admin)

    # Bazadagi mijoz serverda saqlangan argumentlar bilan yaratilgan
    cust = db_session.query(Customer).filter(Customer.name == "Haqiqiy Mijoz").first()
    assert cust is not None
    assert cust.phone == "+998901111111"
