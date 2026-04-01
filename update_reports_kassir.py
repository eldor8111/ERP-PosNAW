import re

# ────────────────────────────────────────────────────────────────
#  1. Add Kassa Balance cards to Reports.jsx Kassir tab
# ────────────────────────────────────────────────────────────────
REPORTS_PATH = 'frontend/src/pages/admin/Reports.jsx'

with open(REPORTS_PATH, 'r', encoding='utf-8') as f:
    reports_code = f.read()

# Add cashBalance state + useEffect near top of component
if 'cashBalance' not in reports_code:
    # after setCashierData line in state defs
    reports_code = reports_code.replace(
        'const [cashierData, setCashierData] = useState([]);',
        'const [cashierData, setCashierData] = useState([]);\n  const [cashBalance, setCashBalance] = useState(null);'
    )
    # add fetch inside cashier tab loading
    reports_code = reports_code.replace(
        "} else if (tab === 'cashier') {\n        const r = await api.get(`/reports/cashier-report${qs()}`);\n        setCashierData(r.data);",
        "} else if (tab === 'cashier') {\n        const r = await api.get(`/reports/cashier-report${qs()}`);\n        setCashierData(r.data);\n        try { const cb = await api.get('/finance/cash-balance'); setCashBalance(cb.data); } catch {}"
    )

# Add balance summary cards right after the Kassir hisoboti header section
KASSIR_HEADER_END = '            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />\n            {loading ? <Spinner /> : ('

KASSIR_CARDS = """            {cashBalance && (
              <div className="grid grid-cols-3 gap-4 px-6 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-blue-50/30">
                <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm">
                  <div className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">Jami Kirim</div>
                  <div className="text-2xl font-black text-emerald-600">{Number(cashBalance.total_income || 0).toLocaleString('ru-RU')} s</div>
                </div>
                <div className="bg-white rounded-xl p-4 border border-red-100 shadow-sm">
                  <div className="text-xs font-bold text-red-500 uppercase tracking-widest mb-1">Jami Chiqim</div>
                  <div className="text-2xl font-black text-red-500">{Number(cashBalance.total_expense || 0).toLocaleString('ru-RU')} s</div>
                </div>
                <div className={`rounded-xl p-4 border shadow-sm ${cashBalance.balance >= 0 ? 'bg-white border-blue-100' : 'bg-red-50 border-red-200'}`}>
                  <div className="text-xs font-bold text-blue-600 uppercase tracking-widest mb-1">Kassadagi Balans</div>
                  <div className={`text-2xl font-black ${cashBalance.balance >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{Number(cashBalance.balance || 0).toLocaleString('ru-RU')} s</div>
                </div>
              </div>
            )}
"""

if 'Kassadagi Balans' not in reports_code:
    target = '            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />\n            {loading ? <Spinner /> : ('
    # find the one inside the cashier section (after Kassir hisoboti comment)
    kassir_block_start = reports_code.find('{/* ── Kassir hisoboti ── */}')
    kassir_block = reports_code[kassir_block_start:]
    first_date_filter = kassir_block.find(target)
    if first_date_filter != -1:
        insert_pos = kassir_block_start + first_date_filter
        reports_code = reports_code[:insert_pos] + KASSIR_CARDS + reports_code[insert_pos:]
        print("Kassir kassa balance cards added.")
    else:
        print("Target not found in Kassir block! Checking...")
        print(repr(kassir_block[:300]))

with open(REPORTS_PATH, 'w', encoding='utf-8') as f:
    f.write(reports_code)

print("Reports.jsx updated.")
