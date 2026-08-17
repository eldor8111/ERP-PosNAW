import os

def fix_sales_report():
    filepath = 'd:/ERP-PosNAW/app/routers/sales_report.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add Currency import
    if 'from app.models.currency import Currency' not in content:
        content = content.replace('from app.models.sale import', 'from app.models.currency import Currency\nfrom app.models.sale import')

    # Update daily_sales_report
    content = content.replace(
        "            func.sum(Sale.total_amount).label(\"total_amount\"),\n            func.sum(Sale.discount_amount).label(\"total_discount\"),\n            func.avg(Sale.total_amount).label(\"avg_check\"),\n        )",
        "            func.coalesce(Currency.code, 'UZS').label(\"currency\"),\n            func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)).label(\"total_amount\"),\n            func.sum(Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)).label(\"total_discount\"),\n            func.avg(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)).label(\"avg_check\"),\n        )\n        .outerjoin(Currency, Currency.id == Sale.currency_id)"
    )
    content = content.replace(
        "        q.group_by(func.date(Sale.created_at))\n        .order_by(func.date(Sale.created_at).desc())",
        "        q.group_by(func.date(Sale.created_at), func.coalesce(Currency.code, 'UZS'))\n        .order_by(func.date(Sale.created_at).desc())"
    )

    daily_return = """    
    # Merge currencies by date
    day_map = {}
    for r in rows:
        d = str(r.day)
        if d not in day_map:
            day_map[d] = {
                "date": d,
                "sales_count": 0,
                "total_amount": {},
                "total_discount": {},
                "avg_check": {}
            }
        
        curr = r.currency
        day_map[d]["sales_count"] += r.sales_count
        day_map[d]["total_amount"][curr] = float(r.total_amount or 0)
        day_map[d]["total_discount"][curr] = float(r.total_discount or 0)
        day_map[d]["avg_check"][curr] = float(r.avg_check or 0)
        
    return list(day_map.values())"""
    
    content = content.split("    return [")[0] + daily_return + "\n\n\n@router.get(\"/top-products\")" + content.split("@router.get(\"/top-products\")")[1]

    # Update top_products_report
    content = content.replace(
        "            func.sum(SaleItem.subtotal).label(\"total_revenue\"),\n            func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity).label(\"total_profit\"),\n        )\n        .join(SaleItem",
        "            func.coalesce(SaleItem.currency_code, 'UZS').label(\"currency\"),\n            func.sum(SaleItem.subtotal).label(\"total_revenue\"),\n            func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity).label(\"total_profit\"),\n        )\n        .join(SaleItem"
    )
    content = content.replace(
        "        q.group_by(Product.id, Product.name, Product.sku)\n        .order_by(func.sum(SaleItem.subtotal).desc())",
        "        q.group_by(Product.id, Product.name, Product.sku, func.coalesce(SaleItem.currency_code, 'UZS'))\n        .order_by(func.sum(SaleItem.subtotal).desc())"
    )

    top_return = """    
    # Merge currencies
    prod_map = {}
    for r in rows:
        pid = r.id
        if pid not in prod_map:
            prod_map[pid] = {
                "product_id": r.id,
                "product_name": r.name,
                "sku": r.sku,
                "total_qty": 0.0,
                "total_revenue": {},
                "total_profit": {}
            }
        
        curr = r.currency
        prod_map[pid]["total_qty"] += float(r.total_qty or 0)
        prod_map[pid]["total_revenue"][curr] = float(r.total_revenue or 0)
        prod_map[pid]["total_profit"][curr] = float(r.total_profit or 0)
        
    sorted_prods = sorted(prod_map.values(), key=lambda x: sum(x["total_revenue"].values()), reverse=True)[:limit]
    for idx, p in enumerate(sorted_prods):
        p["rank"] = idx + 1
        
    return sorted_prods"""
    
    content = content.split("@router.get(\"/cashier-report\")")[0].split("    return [")[0] + top_return + "\n\n\n@router.get(\"/cashier-report\")" + content.split("@router.get(\"/cashier-report\")")[1]

    # Update cashier_report
    content = content.replace(
        "            func.coalesce(func.sum(Sale.total_amount), 0).label(\"total_amount\"),\n            func.coalesce(func.sum(Sale.discount_amount), 0).label(\"total_discount\"),\n            func.coalesce(func.avg(Sale.total_amount), 0).label(\"avg_check\"),\n        )",
        "            func.coalesce(Currency.code, 'UZS').label(\"currency\"),\n            func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label(\"total_amount\"),\n            func.coalesce(func.sum(Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label(\"total_discount\"),\n            func.coalesce(func.avg(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label(\"avg_check\"),\n        )\n        .outerjoin(Currency, Currency.id == Sale.currency_id)"
    )
    content = content.replace(
        "        q.group_by(User.id, User.name)\n        .order_by(func.sum(Sale.total_amount).desc())",
        "        q.group_by(User.id, User.name, func.coalesce(Currency.code, 'UZS'))\n        .order_by(func.sum(Sale.total_amount).desc())"
    )

    cashier_return = """
    # Merge currencies
    cashier_map = {}
    for r in rows:
        cid = r.id
        if cid not in cashier_map:
            cashier_map[cid] = {
                "cashier_id": r.id,
                "cashier_name": r.name,
                "sales_count": 0,
                "total_amount": {},
                "total_discount": {},
                "avg_check": {}
            }
        
        curr = r.currency
        cashier_map[cid]["sales_count"] += r.sales_count
        cashier_map[cid]["total_amount"][curr] = float(r.total_amount or 0)
        cashier_map[cid]["total_discount"][curr] = float(r.total_discount or 0)
        cashier_map[cid]["avg_check"][curr] = float(r.avg_check or 0)
        
    return list(cashier_map.values())"""
    
    content = content.split("@router.get(\"/abc-xyz\")")[0].split("    return [")[0] + cashier_return + "\n\n\n@router.get(\"/abc-xyz\")" + content.split("@router.get(\"/abc-xyz\")")[1]

    # Update abc-xyz analysis
    # Keep UZS for revenue grouping, but we'll modify it slightly
    content = content.replace(
        "            func.sum(SaleItem.subtotal).label(\"revenue\"),\n",
        "            func.sum(SaleItem.subtotal * func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)).label(\"revenue\"),\n"
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_sales_report()
print('sales_report.py fixed')
