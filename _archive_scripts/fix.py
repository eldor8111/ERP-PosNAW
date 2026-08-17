import os

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'from app.models.currency import Currency' not in content:
        content = content.replace('from app.models.sale import', 'from app.models.currency import Currency\nfrom app.models.sale import')

    # Replace currency_code grouped with coalesce
    content = content.replace('Sale.currency_code', "func.coalesce(Currency.code, 'UZS')")
    
    # Fix today_rows
    content = content.replace(
        "func.coalesce(func.sum(Sale.total_amount), 0)\n    ).filter(",
        "func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0)\n    ).outerjoin(Currency, Currency.id == Sale.currency_id).filter("
    )
    
    # Fix month_rows
    content = content.replace(
        "func.coalesce(func.sum(Sale.total_amount), 0)\n    ).filter(",
        "func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0)\n    ).outerjoin(Currency, Currency.id == Sale.currency_id).filter("
    )
    
    # Fix cashier_q
    content = content.replace(
        "func.coalesce(func.sum(Sale.total_amount), 0).label(\"total\"))\n        .join(Sale, Sale.cashier_id == User.id)",
        "func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label(\"total\"))\n        .join(Sale, Sale.cashier_id == User.id)\n        .outerjoin(Currency, Currency.id == Sale.currency_id)"
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_file('d:/ERP-PosNAW/app/routers/reports.py')
print('reports.py fixed')

def fix_shifts():
    filepath = 'd:/ERP-PosNAW/app/routers/shifts.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'from app.models.currency import Currency' not in content:
        content = content.replace('from app.models.sale import', 'from app.models.currency import Currency\nfrom app.models.sale import')

    content = content.replace('Sale.currency_code', "func.coalesce(Currency.code, 'UZS')")
    
    # In shifts, we use SalePayment joined with Sale.
    # So we can just outerjoin Currency.
    content = content.replace(
        ").join(Sale, SalePayment.sale_id == Sale.id).filter(",
        ").join(Sale, SalePayment.sale_id == Sale.id).outerjoin(Currency, Currency.id == Sale.currency_id).filter("
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_shifts()
print('shifts.py fixed')
