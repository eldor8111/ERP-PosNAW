import sys
import re

with open('D:/EcodeWeb/frontend/src/pages/admin/Operations.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. State changes
content = content.replace(
    "  const [msg, setMsg] = useState('');\n\n  const [form, setForm]",
    "  const [msg, setMsg] = useState('');\n  const [showPay, setShowPay] = useState(false);\n\n  const [form, setForm]"
)

# 2. save function signature
content = content.replace(
    "  const save = async () => {\n    if (!items.length)",
    "  const save = async (overridePayType) => {\n    const pType = typeof overridePayType === 'string' ? overridePayType : form.payment_type;\n    if (!items.length)"
)

content = content.replace(
    "      if (form.payment_type !== 'debt' && !form.wallet_id) { setErr(\"Kassani tanlang\"); return; }",
    "      if (pType !== 'debt' && !form.wallet_id) { setErr(\"Kassani tanlang\"); return; }"
)

content = content.replace(
    "        if (form.payment_type === 'cash') {",
    "        if (pType === 'cash') {"
)
content = content.replace(
    "        } else if (form.payment_type === 'card') {",
    "        } else if (pType === 'card') {"
)
content = content.replace(
    "        } else if (form.payment_type === 'mixed') {",
    "        } else if (pType === 'mixed') {"
)
content = content.replace(
    "          payment_type: form.payment_type,",
    "          payment_type: pType,"
)

content = content.replace(
    "      setItems([]); setNote(''); setForm({ supplier_id: '', customer_id: '', warehouse_id: '', received_amount: '', wallet_id: '', payment_type: 'debt', paid_cash: '', paid_card: '' });\n    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik yuz berdi'); } finally { setSaving(false); }\n  };",
    "      setItems([]); setNote(''); setForm({ supplier_id: '', customer_id: '', warehouse_id: '', received_amount: '', wallet_id: '', payment_type: 'debt', paid_cash: '', paid_card: '' });\n      setShowPay(false);\n    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik yuz berdi'); } finally { setSaving(false); }\n  };"
)

# 3. Remove inline payment inputs
# Customer
inline_cust = '''          {isCustomer && items.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
              <div className="text-sm font-bold text-slate-700 flex justify-between">
                <span>Jami qaytarilayotgan summa:</span>
                <span className="text-indigo-700">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))}</span>
              </div>

              <Lbl t="Qaytarish turi">
                <select value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })} className={ic}>
                  <option value="debt">Qarzdan chegirish</option>
                  <option value="cash">Naqd pul qaytarish</option>
                  <option value="card">Plastik kartaga qaytarish</option>
                  <option value="mixed">Aralash qaytarish</option>
                </select>
              </Lbl>

              {form.payment_type === 'mixed' && (
                <div className="grid grid-cols-2 gap-3 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                  <Lbl t="Naqd qaytarilgan">
                    <input type="number" min="0" step="any" value={form.paid_cash} onChange={e => setForm({ ...form, paid_cash: e.target.value })} className={ic} placeholder="Summa..." />
                  </Lbl>
                  <Lbl t="Karta orqali qaytarilgan">
                    <input type="number" min="0" step="any" value={form.paid_card} onChange={e => setForm({ ...form, paid_card: e.target.value })} className={ic} placeholder="Summa..." />
                  </Lbl>
                </div>
              )}

              {form.payment_type !== 'debt' && (
                <Lbl t="Qaysi kassadan chiqim qilish">
                  <select value={form.wallet_id} onChange={e => setForm({ ...form, wallet_id: e.target.value })} className={ic}>
                    <option value="">Tanlang...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)})</option>)}
                  </select>
                </Lbl>
              )}
            </div>
          )}'''
content = content.replace(inline_cust, '')

# Supplier
inline_supp = '''          {!isCustomer && items.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
              <div className="text-sm font-bold text-slate-700 flex justify-between">
                <span>Jami qaytarilayotgan summa:</span>
                <span className="text-indigo-700">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))}</span>
              </div>

              <Lbl t="Naqd qaytarilgan summa (agar bo'lsa)">
                <input type="number" min="0" step="any" value={form.received_amount} onChange={e => setForm({ ...form, received_amount: e.target.value })} className={ic} placeholder="Pul bergan bo'lsa kiriting..." />
              </Lbl>
              {Number(form.received_amount) > 0 && (
                <Lbl t="Qaysi kassaga kirim qilish">
                  <select value={form.wallet_id} onChange={e => setForm({ ...form, wallet_id: e.target.value })} className={ic}>
                    <option value="">Tanlang...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)})</option>)}
                  </select>
                </Lbl>
              )}
            </div>
          )}'''
content = content.replace(inline_supp, '')

# 4. Footer buttons
old_footer = '''      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white shrink-0">
        <div>
          {msg && <span className="text-emerald-600 text-sm font-bold">{msg}</span>}
          {err && <span className="text-red-500 text-sm font-bold">{err}</span>}
        </div>
        <div className="flex gap-3">
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
          <Btn onClick={save} disabled={saving}>{saving ? '...' : (t('common.save') || 'Saqlash')}</Btn>
        </div>
      </div>'''

new_footer = '''      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white shrink-0 shadow-[0_-1px_8px_rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-3">
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
          {msg && <span className="text-emerald-600 text-sm font-bold">{msg}</span>}
          {err && <span className="text-red-500 text-sm font-medium">{err}</span>}
        </div>
        <div className="flex items-center gap-3">
          {items.length > 0 && (
            <div className="text-sm text-slate-500 mr-2">
              Jami: <span className="font-bold text-slate-800 text-base">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))} so'm</span>
            </div>
          )}
          <Btn v="amber" disabled={saving || !items.length} onClick={() => save('debt')}>
            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            Qarzga yopish
          </Btn>
          <button disabled={saving || !items.length} onClick={() => { setErr(''); setShowPay(true); }}
            className="inline-flex items-center gap-2.5 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200 active:scale-95">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
            To'lovga o'tish
          </button>
        </div>
      </div>'''

content = content.replace(old_footer, new_footer)

modal_code = '''
      {showPay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
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
                    <input type="number" min="0" value={form.paid_cash} onChange={e => setForm({ ...form, paid_cash: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 block">Karta</label>
                    <input type="number" min="0" value={form.paid_card} onChange={e => setForm({ ...form, paid_card: e.target.value })} className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
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

content = content.replace(
    '    </div>\n  );\n}\n\n/* ══════════════════════════════════════════════════════════\n   SALE CREATE VIEW',
    modal_code + '\n    </div>\n  );\n}\n\n/* ══════════════════════════════════════════════════════════\n   SALE CREATE VIEW'
)

with open('D:/EcodeWeb/frontend/src/pages/admin/Operations.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
