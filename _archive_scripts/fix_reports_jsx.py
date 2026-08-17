import os

def fix_reports_jsx():
    filepath = 'd:/ERP-PosNAW/frontend/src/pages/admin/Reports.jsx'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # In Sales table
    # <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtS(s.total_amount)}</td>
    content = content.replace(
        "{fmtS(s.total_amount)}</td>\n                          <td className=\"px-5 py-3.5 text-sm text-slate-500\">{s.discount_amount > 0 ? fmtS(s.discount_amount) : '—'}</td>",
        "{fmtRowDebt(s.total_amount, s.currency_code)}</td>\n                          <td className=\"px-5 py-3.5 text-sm text-slate-500\">{s.discount_amount > 0 ? fmtRowDebt(s.discount_amount, s.currency_code) : '—'}</td>"
    )

    # Sales export
    content = content.replace(
        "salesData.map(s => [s.number, s.cashier_name, fmtS(s.total_amount), s.payment_type, new Date(s.created_at).toLocaleDateString('uz-UZ')])",
        "salesData.map(s => [s.number, s.cashier_name, fmtRowDebt(s.total_amount, s.currency_code), s.payment_type, new Date(s.created_at).toLocaleDateString('uz-UZ')])"
    )

    # In product-sales table
    content = content.replace(
        "profitData.map(r => [r.product_name, r.category_name, fmt(r.qty_sold), fmtS(r.revenue), fmtS(r.cost), fmtS(r.profit), pct(r.margin_pct)])",
        "profitData.map(r => [r.product_name, r.category_name, fmt(r.qty_sold), fmtDebt(r.revenue), fmtDebt(r.cost), fmtDebt(r.profit), pct(r.margin_pct)])"
    )
    content = content.replace(
        "['JAMI', '', '', fmtS(profitData.reduce((a, r) => a + r.revenue, 0)), fmtS(profitData.reduce((a, r) => a + r.cost, 0)), fmtS(profitData.reduce((a, r) => a + r.profit, 0)), '']",
        "['JAMI', '', '', '', '', '', '']"
    )

    # Profit table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-semibold text-rose-600\">{fmtS(r.cost)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtS(r.profit)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtDebt(r.revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-semibold text-rose-600\">{fmtDebt(r.cost)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtDebt(r.profit)}</td>"
    )

    # Cashier table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-bold text-slate-800\">{fmtS(r.total_amount)}</td>\n                        <td className=\"px-5 py-3.5 text-sm text-slate-500\">{fmtS(r.total_discount)}</td>\n                        <td className=\"px-5 py-3.5 text-sm text-indigo-600\">{fmtS(r.avg_check)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-bold text-slate-800\">{fmtDebt(r.total_amount)}</td>\n                        <td className=\"px-5 py-3.5 text-sm text-slate-500\">{fmtDebt(r.total_discount)}</td>\n                        <td className=\"px-5 py-3.5 text-sm text-indigo-600\">{fmtDebt(r.avg_check)}</td>"
    )

    # Purchases table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-bold text-slate-800\">{fmtS(r.total_amount)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-bold text-slate-800\">{fmtDebt(r.total_amount)}</td>"
    )

    # Product-sales (Sotuv) tab
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.total_revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtS(r.total_profit)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtDebt(r.total_revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtDebt(r.total_profit)}</td>"
    )

    # Batches table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtS(r.profit)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtDebt(r.revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtDebt(r.profit)}</td>"
    )

    # Top products table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.total_revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtS(r.total_profit)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtDebt(r.total_revenue)}</td>\n                        <td className=\"px-5 py-3.5 text-sm font-bold text-indigo-600\">{fmtDebt(r.total_profit)}</td>"
    )

    # ABC table
    content = content.replace(
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.revenue)}</td>",
        "<td className=\"px-5 py-3.5 text-sm font-semibold text-emerald-600\">{fmtS(r.revenue)}</td>"  # Kept as is since abc logic converts everything to UZS equivalent float
    )

    # Profit & Loss
    content = content.replace(
        "<div className=\"text-2xl font-bold text-slate-800\">{fmtS(plData.gross_revenue)}</div>",
        "<div className=\"text-2xl font-bold text-slate-800\">{fmtDebt(plData.gross_revenue)}</div>"
    )
    content = content.replace(
        "<div className=\"text-2xl font-bold text-slate-800\">{fmtS(plData.returns)}</div>",
        "<div className=\"text-2xl font-bold text-slate-800\">{fmtDebt(plData.returns)}</div>"
    )
    content = content.replace(
        "<div className=\"text-3xl font-bold text-indigo-600\">{fmtS(plData.revenue)}</div>",
        "<div className=\"text-3xl font-bold text-indigo-600\">{fmtDebt(plData.revenue)}</div>"
    )
    content = content.replace(
        "<span className=\"font-bold text-slate-800\">{fmtS(plData.cogs)}</span>",
        "<span className=\"font-bold text-slate-800\">{fmtDebt(plData.cogs)}</span>"
    )
    content = content.replace(
        "<span className=\"font-bold text-slate-800\">{fmtS(plData.gross_profit)}</span>",
        "<span className=\"font-bold text-slate-800\">{fmtDebt(plData.gross_profit)}</span>"
    )
    content = content.replace(
        "<span className=\"font-semibold text-slate-800\">{fmtS(c.total)}</span>",
        "<span className=\"font-semibold text-slate-800\">{fmtDebt(c.total)}</span>"
    )
    content = content.replace(
        "<span className=\"font-bold text-slate-800\">{fmtS(plData.expenses.total)}</span>",
        "<span className=\"font-bold text-slate-800\">{fmtDebt(plData.expenses.total)}</span>"
    )
    content = content.replace(
        "<span className=\"font-bold text-slate-800\">{fmtS(plData.net_profit)}</span>",
        "<span className=\"font-bold text-slate-800\">{fmtDebt(plData.net_profit)}</span>"
    )
    content = content.replace(
        "<div className=\"text-2xl font-bold text-emerald-600\">{fmtS(plData.net_profit)}</div>",
        "<div className=\"text-2xl font-bold text-emerald-600\">{fmtDebt(plData.net_profit)}</div>"
    )
    content = content.replace(
        "<span className=\"font-bold text-slate-800\">{fmtS(plData.gross_profit)}</span>",
        "<span className=\"font-bold text-slate-800\">{fmtDebt(plData.gross_profit)}</span>"
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_reports_jsx()
print('Reports.jsx fixed')
