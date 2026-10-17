"""
Buyurtma "yetkazildi" bo'lganda avtomatik Sale (sotuv) yaratish.

Company.orders_auto_create_sale = True bo'lsa ishlaydi. create_sale
servisi qayta ishlatiladi — shu tufayli ombor (FIFO batch), kassa
harakati, wallet balansi, qarz (payment_type=debt bo'lsa) va boshqa
barcha sotuv mantig'i bir xil ishlaydi.

Idempotentlik: guruhdagi qatorlarga Order.sale_id yoziladi — bir guruh
uchun faqat bitta Sale yaratiladi.

delivery_fee Sale'ga (tovar tushumiga) KIRMAYDI — u alohida daromad
sifatida yoziladi (record_delivery_fee): naqd/karta bo'lsa kassaga kirim,
qarzga bo'lsa mijoz qarziga qo'shiladi.
"""
import logging
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.company import Company
from app.models.customer import Customer
from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet
from app.models.order import Order
from app.models.user import User, UserRole, UserStatus
from app.utils.telegram_text import esc


def _resolve_wallet(db: Session, user: User, branch_id=None):
    """T1.10: create_sale bilan bir xil yagona qoida (`resolve_wallet`): kassirning kassasi,
    filial kassasi, filialning ochiq kassasi. Shaxsiy (qo'l) kassa va boshqa filial kassasi tanlanmaydi."""
    from app.services.wallet_resolver import resolve_wallet
    return resolve_wallet(db, user, branch_id=branch_id, purpose="sale")


def record_delivery_fee(db: Session, sale, fee: Decimal, payment_type: str, user: User) -> None:
    """Yetkazish haqini moliyaga yozadi (sotuv bilan bir tranzaksiyada)."""
    if payment_type == "debt":
        customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
        if customer:
            customer.debt_balance = Decimal(str(customer.debt_balance or 0)) + fee
            balances = dict(customer.debt_balances or {})
            balances["UZS"] = float(Decimal(str(balances.get("UZS", 0))) + fee)
            customer.debt_balances = balances
            flag_modified(customer, "debt_balances")
        return

    # T1.9: yetkazish haqi sotuv filialiga yoziladi (amalni bajargan xodim filialiga emas)
    from app.services.sale_helpers import resolve_txn_branch
    branch_id = resolve_txn_branch(db, user, sale=sale)
    wallet = _resolve_wallet(db, user, branch_id=branch_id)
    desc = f"Yetkazish haqi — sotuv #{sale.number}"

    if branch_id:
        db.add(Transaction(
            branch_id=branch_id, company_id=user.company_id,
            wallet_id=wallet.id if wallet else None,
            type="income", amount=fee, payment_type=payment_type, currency_code="UZS",
            reference_type="delivery_fee", reference_id=sale.id, description=desc,
        ))
    if wallet:
        session = db.query(KassaSession).filter(
            KassaSession.wallet_id == wallet.id, KassaSession.status == "open",
        ).first()
        db.add(KassaMovement(
            wallet_id=wallet.id, company_id=user.company_id,
            session_id=session.id if session else None,
            direction="in", payment_type=payment_type, amount=fee, currency="UZS",
            reference_type="delivery_fee", reference_id=sale.id,
            description=desc, created_by=user.id,
        ))
        wallet.balance = Decimal(str(wallet.balance or 0)) + fee


def _order_branch_warehouse_id(db: Session, acting_user: User, branch_id, company_id):
    """T1.15: buyurtma filialining birinchi faol ombori (avto-sotuv shu filial omboridan yechilsin).
    Sotuvni yozayotgan xodim boshqa filial xodimi bo'lsa (ombor tekshiruvi 403 berardi) —
    `None`: eski xatti-harakat (xodim filiali omboridan) saqlanadi."""
    if not branch_id:
        return None
    role = getattr(acting_user.role, "value", acting_user.role)
    if role not in ("admin", "director", "super_admin") and acting_user.branch_id \
            and acting_user.branch_id != branch_id:
        return None
    from app.models.warehouse import Warehouse
    row = db.query(Warehouse.id).filter(
        Warehouse.company_id == company_id,
        Warehouse.branch_id == branch_id,
        Warehouse.is_active == True,  # noqa: E712
    ).order_by(Warehouse.id.asc()).first()
    return row[0] if row else None


def _pick_acting_user(db: Session, company_id: int, branch_id) -> "User | None":
    """T3.13: sotuvni yozuvchi xodim berilmagan bo'lsa — buyurtma filialidagi faol kassir/menejer,
    bo'lmasa admin/direktor, bo'lmasa korxonaning istalgan (eng kichik id li) xodimi."""
    if branch_id:
        user = db.query(User).filter(
            User.company_id == company_id,
            User.branch_id == branch_id,
            User.role.in_([UserRole.cashier, UserRole.manager]),
            User.status == UserStatus.active,
        ).order_by(User.id.asc()).first()
        if user:
            return user
    user = db.query(User).filter(
        User.company_id == company_id,
        User.role.in_([UserRole.admin, UserRole.director]),
    ).order_by(User.id.asc()).first()
    if user:
        return user
    return db.query(User).filter(User.company_id == company_id).order_by(User.id.asc()).first()


def _order_sale_warehouse_id(db: Session, company_id: int, first) -> int:
    """T3.13: avto-sotuv ombori — `Order.warehouse_id` (faol va shu korxonaniki bo'lsa), eski buyurtmalarda
    (NULL) buyurtma filialining do'kon ombori, u ham bo'lmasa T1.5 `resolve_warehouse` (filial savdo ombori;
    topilmasa 409 — boshqa filialga o'tilmaydi)."""
    from app.models.warehouse import Warehouse
    from app.services.shop_branch import pick_fulfillment_warehouse
    from app.services.warehouse_resolver import resolve_warehouse

    order_wh = getattr(first, "warehouse_id", None)
    if order_wh:
        row = db.query(Warehouse.id).filter(
            Warehouse.id == order_wh,
            Warehouse.company_id == company_id,
            Warehouse.is_active == True,  # noqa: E712
        ).first()
        if row:
            return row[0]
    wh = pick_fulfillment_warehouse(db, company_id, first.branch_id)
    if wh is not None:
        return wh.id
    return resolve_warehouse(db, company_id, branch_id=first.branch_id, purpose="order")


def maybe_create_sale_for_delivered_group(db: Session, orders: list, acting_user: User = None) -> None:
    """Background task: guruh yetkazilganda (sozlama yoqiq bo'lsa) Sale yaratadi.

    Xato yuz bersa yetkazish statusiga ta'sir qilmaydi — log + admin botga
    ogohlantirish yuboriladi.
    """
    try:
        if not orders:
            return
        first = orders[0]

        # Idempotentlik — allaqachon Sale yaratilgan bo'lsa chiqamiz
        if any(getattr(o, "sale_id", None) for o in orders):
            return

        # T0.36: buyurtma egasi korxona bevosita orders.company_id da
        customer_company_id = getattr(first, "company_id", None)
        if not customer_company_id:
            return

        company = db.query(Company).filter(Company.id == customer_company_id).first()
        if not company or company.orders_auto_create_sale is not True:
            return

        # Sotuvni kim nomidan yozamiz: mobil ilovadan kuryerning o'zi (naqd pul
        # uning qo'l kassasiga tushadi), aks holda T3.13: buyurtma filialidagi kassir/menejer,
        # bo'lmasa kompaniyaning admin/direktori
        if acting_user is not None and acting_user.company_id != company.id:
            acting_user = None
        acting_user = acting_user or _pick_acting_user(db, company.id, getattr(first, "branch_id", None))
        if not acting_user:
            return

        # T0.7: filialsiz korxona — tushum jim yo'qolmasin; buyurtma o'tkazib yuboriladi (HTTP xatosi yo'q)
        from app.services.tenant_guards import find_tx_branch
        if find_tx_branch(db, acting_user) is None:
            logging.getLogger(__name__).warning(
                "[order_to_sale] Korxona %s da filial yo'q — avto-sotuv o'tkazib yuborildi (guruh %s)",
                company.id, getattr(first, "order_group_id", None) or first.id,
            )
            return

        from app.schemas.sale import SaleCreate, SaleItemCreate

        items = [
            SaleItemCreate(
                product_id=o.product_id,
                quantity=Decimal(str(o.quantity)),
                unit_price=Decimal(str(o.unit_price or 0)),
                discount=Decimal("0"),
            )
            for o in orders
        ]
        total = sum(Decimal(str(o.total_amount or 0)) for o in orders)
        payment_type = (first.payment_type or "cash").strip().lower()
        if payment_type not in ("cash", "card", "debt"):
            payment_type = "cash"

        fee = Decimal(str(getattr(first, "delivery_fee", 0) or 0))
        note_parts = [f"Buyurtma yetkazildi (#{first.order_group_id or first.id})"]
        if fee > 0:
            note_parts.append(f"Yetkazish haqi: {fee:,.0f} so'm (alohida kirim)")

        data = SaleCreate(
            items=items,
            payment_type=payment_type,
            paid_amount=Decimal("0") if payment_type == "debt" else total,
            paid_cash=total if payment_type == "cash" else Decimal("0"),
            paid_card=total if payment_type == "card" else Decimal("0"),
            discount_amount=Decimal("0"),
            customer_id=first.customer_id,
            note=" | ".join(note_parts),
            # T3.13: ombor Order.warehouse_id dan; eski buyurtmada (NULL) buyurtma filialining do'kon ombori
            # (T1.5: filialda savdo ombori bo'lmasa 409 — boshqa filialga o'tilmaydi, xato admin botga boradi)
            warehouse_id=_order_sale_warehouse_id(db, company.id, first),
        )

        from app.services.sale_create import create_sale
        sale = create_sale(db=db, data=data, current_user=acting_user)
        if fee > 0:
            record_delivery_fee(db, sale, fee, payment_type, acting_user)

        for o in orders:
            o.sale_id = sale.id
        db.commit()

        # Admin botga xabar
        try:
            from app.admin_tg_bot.notifications import trigger_instant_notification
            from app.admin_tg_bot.message_utils import describe_location
            # T3.16: filial/ombor qatori (ko'p filialli korxonada) va filial menejeriga yuborish
            location = describe_location(db, warehouse_id=sale.warehouse_id, branch_id=sale.branch_id)
            trigger_instant_notification(
                company.id,
                f"📦➡️🧾 Buyurtma yetkazildi va sotuvga aylantirildi\n"
                + (f"{location}\n" if location else "")
                + f"Chek: #{sale.number}\n💰 {float(total):,.0f} so'm",
                "sale",
                sale.branch_id,
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[order_to_sale] Avto-sotuv yaratishda xato: {e}")
        try:
            from app.admin_tg_bot.notifications import trigger_instant_notification
            first = orders[0] if orders else None
            comp_id = first.customer.company_id if (first and first.customer) else None
            if comp_id:
                trigger_instant_notification(
                    comp_id,
                    f"⚠️ Buyurtma yetkazildi, lekin avto-sotuv yaratilmadi: {esc(e)}\n"
                    f"Guruh: {esc(getattr(first, 'order_group_id', '?'))} — POS orqali qo'lda kiriting.",
                    "sale",
                    getattr(first, "branch_id", None),
                )
        except Exception:
            pass
