import re

with open('D:/EcodeWeb/frontend/src/pages/admin/Operations.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

modal_code = '''
      {showPay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowPay(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-800">Kassadan to'lov</h3>
              <button onClick={() => setShowPay(false)} className="p-1.5 hover:bg-slate-100 rounded-xl text-slate-400 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 text-center">
                <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">Qaytarilayotgan summa</div>
                <div className="text-3xl font-black text-indigo-700">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))} <span className="text-lg font-normal text-indigo-400">so'm</span></div>
              </div>
              
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">To'lov turi</label>
                <select value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 focus:outline-none transition-colors">
                  <option value="cash">Naqd</option>
                  <option value="card">Plastik karta</option>
                  <option value="mixed">Aralash</option>
                </select>
              </div>

              {form.payment_type === 'mixed' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 block">Naqd</label>
                    <input type="number" min="0" step="any" value={form.paid_cash} onChange={e => setForm({ ...form, paid_cash: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 block">Karta</label>
                    <input type="number" min="0" step="any" value={form.paid_card} onChange={e => setForm({ ...form, paid_card: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
                  </div>
                </div>
              )}

              {form.payment_type !== 'debt' && (
                <div>
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Kassa / Hisob</label>
                  <select value={form.wallet_id} onChange={e => setForm({ ...form, wallet_id: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 focus:outline-none transition-colors">
                    <option value="">Tanlang...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)})</option>)}
                  </select>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <Btn v="ghost" onClick={() => setShowPay(false)}>Bekor qilish</Btn>
                <button onClick={() => save(form.payment_type)} disabled={saving} className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200 active:scale-95">
                  {saving ? 'Tasdiqlanmoqda...' : 'Tasdiqlash'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
'''

content = re.sub(
    r'(\s*</div>\s*</div>\s*\);\s*}\s*function QaytarishlarTab)',
    lambda m: modal_code + m.group(1),
    content
)

with open('D:/EcodeWeb/frontend/src/pages/admin/Operations.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added modal successfully")
