"""
Loyalty & Cashback Service
Mijoz sodiqlik ballari va keshbek logikasini boshqaradi.
"""
from decimal import Decimal
from app.models.customer import Customer
from app.models.sale import Sale


def restore_customer_after_sale(customer: Customer, sale: Sale) -> None:
    """
    Sotuvni bekor qilish yoki o'chirishda mijozning barcha ko'rsatkichlarini tiklaydi:
    qarz, ishlatilgan keshbek, qo'shilgan keshbek, total_spent, loyallik ballari.
    """
    exr = Decimal(str(getattr(sale, 'exchange_rate', 1) or 1))
    total = Decimal(str(sale.total_amount or 0))
    paid = Decimal(str(sale.paid_amount or 0))

    # 1. Qarzni tiklash
    debt_in_sale = total - paid
    if debt_in_sale > 0:
        customer.debt_balance = max(
            Decimal("0"),
            (customer.debt_balance or Decimal("0")) - debt_in_sale
        )

    # 2. Ishlatilgan keshbekni qaytarish (mijoz bonus_balance dan to'lagan edi)
    used_cashback = Decimal(str(getattr(sale, 'paid_cashback', 0) or 0))
    if used_cashback > 0:
        customer.bonus_balance = (customer.bonus_balance or Decimal("0")) + used_cashback

    # 3. Qo'shilgan keshbekni ayirish (xarid uchun berilgan edi)
    if getattr(customer, "cashback_percent", 0) and customer.cashback_percent > 0:
        earned_cashback = (total * exr * customer.cashback_percent) / Decimal("100")
        customer.bonus_balance = max(
            Decimal("0"),
            (customer.bonus_balance or Decimal("0")) - earned_cashback
        )

    # 4. Total spent tiklash
    customer.total_spent = max(
        Decimal("0"),
        (customer.total_spent or Decimal("0")) - (total * exr)
    )

    # 5. Loyallik ballari tiklash: ishlatilganini qaytarish, qo'shilganini ayirish
    points_used = getattr(sale, 'loyalty_points_used', 0) or 0
    points_earned = getattr(sale, 'loyalty_points_earned', 0) or 0
    if points_used > 0:
        customer.loyalty_points = (customer.loyalty_points or 0) + points_used
    if points_earned > 0:
        customer.loyalty_points = max(0, (customer.loyalty_points or 0) - points_earned)
