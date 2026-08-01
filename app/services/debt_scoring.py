from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime, date
from typing import List, Dict, Any

from app.models.customer import Customer
from app.models.sale import Sale

def calculate_debt_score(customer_id: int, db: Session) -> Dict[str, Any]:
    """
    Kredit skoring algoritmi.
    Max bal: 100
    Base bal: 50
    Kategoriya:
      80-100 -> Ishonchli
      50-79  -> O'rtacha
      0-49   -> Xavfli
    """
    score = 50
    pattern_desc = "Yetarli ma'lumot yo'q"
    
    # 1. Barcha qarz savdolarini olamiz
    debt_sales = db.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.total_amount > Sale.paid_amount
    ).all()

    # Agar umuman qarzi bo'lmagan bo'lsa
    if not debt_sales:
        return {
            "score": 100,
            "label": "Ishonchli",
            "color": "green",
            "pattern": "Hech qachon qarz olmagan / Vaqtida to'lagan",
            "avg_delay_days": 0
        }

    total_debt = sum(float(s.total_amount - s.paid_amount) for s in debt_sales)
    overdue_count = 0
    max_delay = 0

    today = date.today()

    for s in debt_sales:
        if s.debt_due_date:
            delay = (today - s.debt_due_date).days
            if delay > 0:
                overdue_count += 1
                if delay > max_delay:
                    max_delay = delay
    
    if overdue_count == 0:
        score += 25
        pattern_desc = "Har doim vaqtida to'laydi"
    elif max_delay <= 3:
        score += 15
        pattern_desc = "Biroz kechiktirib to'laydi (1-3 kun)"
    elif max_delay <= 7:
        score -= 15
        pattern_desc = "Kechiktirib to'laydi (4-7 kun)"
    else:
        score -= 30
        pattern_desc = "Ko'p kechiktiradi (7+ kun)"
        
    if overdue_count > 0:
        score -= 20  # Hali ham to'lanmagan qarzi bor

    # Cheklovlar
    if score > 100: score = 100
    if score < 0: score = 0

    if score >= 80:
        label = "Ishonchli"
        color = "green"
    elif score >= 50:
        label = "O'rtacha"
        color = "orange"
    else:
        label = "Xavfli"
        color = "red"

    return {
        "score": score,
        "label": label,
        "color": color,
        "pattern": pattern_desc,
        "avg_delay_days": max_delay,
        "total_debt": total_debt,
        "overdue_count": overdue_count
    }

def categorize_customers(db: Session, company_id: int):
    customers = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.debt_balance > 0
    ).all()
    
    results = []
    total_debt = 0
    total_overdue = 0
    
    for c in customers:
        score_data = calculate_debt_score(c.id, db)
        
        # Eng eski qarzni topish
        oldest_debt = db.query(Sale).filter(
            Sale.customer_id == c.id,
            Sale.total_amount > Sale.paid_amount
        ).order_by(Sale.created_at.asc()).first()
        
        due_date = str(oldest_debt.debt_due_date) if oldest_debt and oldest_debt.debt_due_date else None
        days_remaining = (oldest_debt.debt_due_date - date.today()).days if oldest_debt and oldest_debt.debt_due_date else 0
        
        total_debt += float(c.debt_balance)
        if score_data['overdue_count'] > 0:
            total_overdue += 1
            
        results.append({
            "id": c.id,
            "name": c.name,
            "debt": float(c.debt_balance),
            "due_date": due_date,
            "days_remaining": days_remaining,
            "trust_score": score_data['score'],
            "trust_label": score_data['label'],
            "trust_color": score_data['color'],
            "avg_delay_days": score_data['avg_delay_days'],
            "payment_pattern": score_data['pattern']
        })
        
    return {
        "total_debtors": len(results),
        "total_debt": total_debt,
        "overdue_count": total_overdue,
        "customers": results
    }
