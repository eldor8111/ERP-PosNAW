import os

def fix_finance_report():
    filepath = 'd:/ERP-PosNAW/app/routers/finance_report.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'from app.models.currency import Currency' not in content:
        content = content.replace('from app.models.sale import', 'from app.models.currency import Currency\nfrom app.models.sale import')

    # 1. Update /expenses
    # Expense has no currency, so we assume UZS or we leave it as float since UI expects a dict if we format it as dict.
    # Actually, we can return it as float if the frontend expects float, or we can just return float. But the user wants everything to be multi-currency aware.
    # We will leave /expenses untouched because it has no currency. But /profit-loss expenses should be dict.

    # 2. Update /profit (product profit)
    # It groups by Product.id. We must add currency grouping.
    content = content.replace(
        "            Product.sku,\n            Category.name.label(\"category_name\"),",
        "            Product.sku,\n            Category.name.label(\"category_name\"),\n            func.coalesce(SaleItem.currency_code, 'UZS').label(\"currency\"),"
    )
    content = content.replace(
        "        q.group_by(Product.id, Product.name, Product.sku, Category.name)\n        .order_by(profit_expr.desc())",
        "        q.group_by(Product.id, Product.name, Product.sku, Category.name, func.coalesce(SaleItem.currency_code, 'UZS'))\n        .order_by(profit_expr.desc())"
    )

    profit_return = """
    # Merge currencies
    prod_map = {}
    for r in rows:
        pid = r.id
        if pid not in prod_map:
            prod_map[pid] = {
                "product_id": r.id,
                "product_name": r.name,
                "sku": r.sku,
                "category_name": r.category_name or "—",
                "qty_sold": 0.0,
                "revenue": {},
                "cost": {},
                "profit": {}
            }
        
        curr = r.currency
        prod_map[pid]["qty_sold"] += float(r.qty_sold or 0)
        prod_map[pid]["revenue"][curr] = float(r.revenue or 0)
        prod_map[pid]["cost"][curr] = float(r.cost or 0)
        prod_map[pid]["profit"][curr] = float(r.profit or 0)
        
    for p in prod_map.values():
        total_rev = sum(p["revenue"].values())
        total_profit = sum(p["profit"].values())
        p["margin_pct"] = round(total_profit / total_rev * 100, 1) if total_rev > 0 else 0
        
    return list(prod_map.values())"""
    
    content = content.split("@router.get(\"/batches\")")[0].split("    return [")[0] + profit_return + "\n\n\n@router.get(\"/batches\")" + content.split("@router.get(\"/batches\")")[1]

    # 3. Update /batches
    content = content.replace(
        "            sold_qty_expr.label(\"sold_qty\"),\n            revenue_expr.label(\"revenue\"),\n            profit_expr.label(\"profit\"),\n        )",
        "            func.coalesce(SaleItem.currency_code, 'UZS').label(\"currency\"),\n            sold_qty_expr.label(\"sold_qty\"),\n            revenue_expr.label(\"revenue\"),\n            profit_expr.label(\"profit\"),\n        )"
    )
    content = content.replace(
        "    rows = q.group_by(Batch.id, Product.name).order_by(Batch.created_at.desc()).all()",
        "    rows = q.group_by(Batch.id, Product.name, func.coalesce(SaleItem.currency_code, 'UZS')).order_by(Batch.created_at.desc()).all()"
    )

    batches_return = """
    # Merge currencies
    batch_map = {}
    for r in rows:
        bid = r.id
        if bid not in batch_map:
            batch_map[bid] = {
                "batch_id": r.id,
                "product_name": r.product_name,
                "lot_number": r.lot_number or "N/A",
                "initial_quantity": float(r.initial_quantity or 0),
                "remaining_quantity": float(r.remaining_quantity or 0),
                "purchase_price": float(r.purchase_price or 0),
                "sold_qty": 0.0,
                "revenue": {},
                "profit": {}
            }
        
        curr = r.currency
        batch_map[bid]["sold_qty"] += float(r.sold_qty)
        batch_map[bid]["revenue"][curr] = float(r.revenue)
        batch_map[bid]["profit"][curr] = float(r.profit)
        
    for b in batch_map.values():
        total_rev = sum(b["revenue"].values())
        total_profit = sum(b["profit"].values())
        b["margin_pct"] = round(total_profit / total_rev * 100, 1) if total_rev > 0 else 0
        
    return list(batch_map.values())"""
    
    content = content.split("@router.get(\"/customer-debts\")")[0].split("    return [")[0] + batches_return + "\n\n\n@router.get(\"/customer-debts\")" + content.split("@router.get(\"/customer-debts\")")[1]

    # 4. Update /profit-loss
    pl_start = content.find("@router.get(\"/profit-loss\")")
    pl_content = content[pl_start:]
    
    # We will entirely replace the profit_loss_statement logic.
    new_pl = """@router.get("/profit-loss")
def profit_loss_statement(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    \"\"\"Foyda va Zarar hisoboti\"\"\"
    from app.models.moliya import ExpenseCategory

    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    def get_sales_by_currency(status):
        rows = (
            db.query(func.coalesce(Currency.code, 'UZS').label("currency"), func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label("amount"))
            .outerjoin(Currency, Currency.id == Sale.currency_id)
            .filter(Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, Sale.status == status)
            .group_by(func.coalesce(Currency.code, 'UZS'))
            .all()
        )
        return {r.currency: float(r.amount) for r in rows}

    gross_revenue = get_sales_by_currency(SaleStatus.completed)
    total_returns = get_sales_by_currency(SaleStatus.refunded)
    
    net_revenue = {}
    for c, amt in gross_revenue.items():
        net_revenue[c] = amt - total_returns.get(c, 0)

    # COGS from SaleItems
    cogs_rows = (
        db.query(
            func.coalesce(SaleItem.currency_code, 'UZS').label("currency"),
            func.coalesce(func.sum(
                case(
                    (Sale.status == SaleStatus.completed, SaleItem.cost_price * SaleItem.quantity),
                    (Sale.status == SaleStatus.refunded, -SaleItem.cost_price * SaleItem.quantity),
                    else_=0,
                )
            ), 0).label("cogs")
        )
        .join(Sale)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start, Sale.created_at < end,
            Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]),
        )
        .group_by(func.coalesce(SaleItem.currency_code, 'UZS'))
        .all()
    )
    cogs = {r.currency: float(r.cogs) for r in cogs_rows}

    gross_profit = {}
    for c, rev in net_revenue.items():
        gross_profit[c] = rev - cogs.get(c, 0)
        
    for c, cost in cogs.items():
        if c not in gross_profit:
            gross_profit[c] = -cost

    # Expenses (only UZS)
    exp_rows = (
        db.query(
            func.coalesce(ExpenseCategory.name, "Boshqa").label("cat"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .filter(Expense.company_id == cid, Expense.created_at >= start, Expense.created_at < end)
        .group_by(ExpenseCategory.name)
        .all()
    )
    expenses_by_cat = [{"name": r.cat, "total": {"UZS": float(r.total)}} for r in exp_rows]
    total_expenses = {"UZS": sum(r["total"]["UZS"] for r in expenses_by_cat)}

    net_profit = {}
    for c, gp in gross_profit.items():
        net_profit[c] = gp - total_expenses.get(c, 0)
        
    for c, exp in total_expenses.items():
        if c not in net_profit:
            net_profit[c] = gross_profit.get(c, 0) - exp

    uzs_net_rev = net_revenue.get("UZS", 0)
    uzs_gp = gross_profit.get("UZS", 0)
    uzs_np = net_profit.get("UZS", 0)
    
    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "revenue": net_revenue,
        "gross_revenue": gross_revenue,
        "returns": total_returns,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(uzs_gp / (uzs_net_rev if uzs_net_rev else 1) * 100, 2),
        "expenses": {
            "total": total_expenses,
            "by_category": expenses_by_cat,
        },
        "net_profit": net_profit,
        "net_margin_pct": round(uzs_np / (uzs_net_rev if uzs_net_rev else 1) * 100, 2),
    }
"""
    content = content[:pl_start] + new_pl
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_finance_report()
print('finance_report.py fixed')
