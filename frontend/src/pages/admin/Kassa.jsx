import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';

const fmt = v => Number(v || 0).toLocaleString('uz-UZ');
const fmtDate = d => d ? new Date(d).toLocaleString('uz-UZ') : '—';

const PT_LABELS = {
  cash: '💵 Naqd', card: '💳 Karta', uzcard: '🟢 UzCard',
  humo: '🔵 Humo', click: '🟡 Click', payme: '🔴 Payme',
  uzum: '🟠 Uzum', keshbek: '🎁 Keshbek',
};
const PT_KEYS = Object.keys(PT_LABELS);

const DIR_COLORS = { in: 'text-emerald-600', out: 'text-red-500' };
const REF_LABELS = {
  sale: 'Sotuv', supplier_payment: "Ta'minotchi to'lovi",
  expense: 'Xarajat', invest: 'Investitsiya',
  withdraw: 'Chiqarish', opening: 'Ochilish balansi',
  customer_payment: "Mijoz to'lovi",
};

const inp = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';
const btn = (color='indigo') => `px-4 py-2 text-sm font-semibold rounded-xl text-white bg-${color}-600 hover:bg-${color}-700 transition-colors`;

/* ── Modal wrapper ── */
function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className={`bg-white rounded-2xl shadow-2xl w-full ${wide ? 'max-w-3xl' : 'max-w-md'} max-h-[90vh] flex flex-col`} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">✕</button>
        </div>
        <div className="p-6 overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
}

/* ── Kassa Card ── */
function KassaCard({ kassa, onRefresh }) {
  const [modal, setModal] = useState(null);
  const [history, setHistory] = useState(null);
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);

  // Form states
  const [form, setForm] = useState({
    amount: '', payment_type: 'cash', description: '',
    category_id: '', opening_balance: '', actual: {}, note: ''
  });

  const balances = kassa.balances || {};
  const total = balances.total || 0;
  const isOpen = kassa.is_open;

  const loadHistory = useCallback(async () => {
    const r = await api.get(`/kassa/${kassa.id}/history`, { params: { limit: 30 } });
    setHistory(r.data);
  }, [kassa.id]);

  const loadCategories = useCallback(async () => {
    const r = await api.get('/kassa/expense-categories/list');
    setCategories(r.data);
  }, []);

  const openModal = async (type) => {
    setForm({ amount: '', payment_type: 'cash', description: '', category_id: '', opening_balance: '', actual: {}, note: '' });
    if (type === 'history') await loadHistory();
    if (type === 'expense') await loadCategories();
    setModal(type);
  };

  const save = async (action) => {
    setSaving(true);
    try {
      if (action === 'open') {
        await api.post(`/kassa/${kassa.id}/open`, { opening_balance: Number(form.opening_balance) || 0, note: form.note });
        toast.success('Kassa ochildi');
      } else if (action === 'close') {
        const actual = {};
        PT_KEYS.forEach(k => { actual[k] = Number(form.actual[k] || 0); });
        await api.post(`/kassa/${kassa.id}/close`, { actual_amounts: actual, note: form.note });
        toast.success('Kassa yopildi');
      } else if (action === 'invest') {
        await api.post(`/kassa/${kassa.id}/invest`, { amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success("Investitsiya qo'shildi");
      } else if (action === 'withdraw') {
        await api.post(`/kassa/${kassa.id}/withdraw`, { amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success('Chiqarildi');
      } else if (action === 'expense') {
        await api.post('/kassa/expense', { wallet_id: kassa.id, category_id: Number(form.category_id), amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success('Xarajat qilindi');
      }
      setModal(null);
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-indigo-50 to-slate-50 border-b border-slate-100">
        <div>
          <h3 className="text-lg font-bold text-slate-800">{kassa.name}</h3>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${isOpen ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>
            {isOpen ? '⚡ Ochiq' : '🔒 Yopiq'}
          </span>
        </div>
        <div className="text-2xl font-black text-indigo-700">{fmt(total)} <span className="text-sm font-medium text-slate-400">so'm</span></div>
      </div>

      {/* Payment type balances */}
      <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {PT_KEYS.map(k => (
          <div key={k} className="bg-slate-50 rounded-xl p-3 flex flex-col">
            <span className="text-xs text-slate-500">{PT_LABELS[k]}</span>
            <span className={`text-sm font-bold mt-0.5 ${(balances[k] || 0) < 0 ? 'text-red-500' : 'text-slate-800'}`}>{fmt(balances[k])} so'm</span>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="px-4 pb-4 flex flex-wrap gap-2">
        {!isOpen ? (
          <button onClick={() => openModal('open')} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl">▶ Ochish</button>
        ) : (
          <button onClick={() => openModal('close')} className="px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white text-sm font-semibold rounded-xl">🔒 Yopish</button>
        )}
        <button onClick={() => openModal('invest')} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl">↓ Investitsiya</button>
        <button onClick={() => openModal('withdraw')} className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold rounded-xl">↑ Chiqarish</button>
        <button onClick={() => openModal('expense')} className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-xl">💸 Xarajat</button>
        <button onClick={() => openModal('history')} className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-sm font-semibold rounded-xl">📋 Tarixi</button>
      </div>

      {/* Open modal */}
      {modal === 'open' && (
        <Modal title="Kassani ochish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Boshlang'ich naqd balans</label>
              <input type="number" className={inp} value={form.opening_balance} onChange={e => setForm({...form, opening_balance: e.target.value})} placeholder="0"/></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Izoh</label>
              <input className={inp} value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Ixtiyoriy..."/></div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm">Bekor</button>
              <button onClick={() => save('open')} disabled={saving} className="flex-1 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold disabled:opacity-50">{saving ? '...' : '✅ Ochish'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Close modal */}
      {modal === 'close' && (
        <Modal title="🔒 Kassani yopish" onClose={() => setModal(null)} wide>
          <div className="space-y-4">
            <p className="text-sm text-slate-500">Har bir to'lov turi uchun haqiqiy summa kiriting:</p>
            <table className="w-full text-sm">
              <thead><tr className="bg-slate-50"><th className="text-left px-3 py-2">To'lov turi</th><th className="text-right px-3 py-2">Hisoblangan</th><th className="text-right px-3 py-2">Haqiqiy</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {PT_KEYS.map(k => (
                  <tr key={k}>
                    <td className="px-3 py-2">{PT_LABELS[k]}</td>
                    <td className="px-3 py-2 text-right font-semibold">{fmt(balances[k])} so'm</td>
                    <td className="px-3 py-2"><input type="number" className="w-32 px-2 py-1.5 border border-slate-200 rounded-lg text-sm text-right"
                      value={form.actual[k] || ''} onChange={e => setForm({...form, actual: {...form.actual, [k]: e.target.value}})} placeholder={fmt(balances[k])}/></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Izoh</label>
              <textarea rows={2} className={inp} value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Ixtiyoriy..."/></div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm">Bekor</button>
              <button onClick={() => save('close')} disabled={saving} className="flex-1 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold disabled:opacity-50">{saving ? '...' : '🔒 Yopish'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Invest / Withdraw modal */}
      {(modal === 'invest' || modal === 'withdraw') && (
        <Modal title={modal === 'invest' ? '↓ Investitsiya' : '↑ Chiqarish'} onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">To'lov turi</label>
              <select className={inp} value={form.payment_type} onChange={e => setForm({...form, payment_type: e.target.value})}>
                {PT_KEYS.map(k => <option key={k} value={k}>{PT_LABELS[k]}</option>)}
              </select></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Summa *</label>
              <input type="number" min="1" className={inp} value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} placeholder="0"/></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Izoh</label>
              <input className={inp} value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Ixtiyoriy..."/></div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm">Bekor</button>
              <button onClick={() => save(modal)} disabled={saving || !form.amount} className={`flex-1 py-2.5 ${modal==='invest'?'bg-blue-600':'bg-amber-600'} text-white rounded-xl text-sm font-semibold disabled:opacity-50`}>{saving ? '...' : 'Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Expense modal */}
      {modal === 'expense' && (
        <Modal title="💸 Xarajat qilish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Xarajat turi *</label>
              <select className={inp} value={form.category_id} onChange={e => setForm({...form, category_id: e.target.value})}>
                <option value="">— Tanlang —</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">To'lov turi</label>
              <div className="flex flex-wrap gap-2">
                {PT_KEYS.map(k => <button key={k} type="button" onClick={() => setForm({...form, payment_type: k})}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all ${form.payment_type===k?'bg-red-600 text-white border-red-600':'bg-white border-slate-200 text-slate-600 hover:border-red-300'}`}>{PT_LABELS[k]}</button>)}
              </div></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Summa *</label>
              <input type="number" min="1" className={inp} value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} placeholder="0"/></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Izoh</label>
              <input className={inp} value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Ixtiyoriy..."/></div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm">Bekor</button>
              <button onClick={() => save('expense')} disabled={saving || !form.amount || !form.category_id} className="flex-1 py-2.5 bg-red-600 text-white rounded-xl text-sm font-semibold disabled:opacity-50">{saving ? '...' : '💸 Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* History modal */}
      {modal === 'history' && history && (
        <Modal title="📋 Kassa tarixi" onClose={() => setModal(null)} wide>
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {[{l:'Jami kirim', v:history.summary.total_in, c:'emerald'},{l:'Jami chiqim', v:history.summary.total_out, c:'red'},{l:'Balans', v:history.summary.balance, c:'indigo'}].map(s => (
                <div key={s.l} className={`bg-${s.c}-50 rounded-xl p-3`}>
                  <div className="text-xs text-slate-500">{s.l}</div>
                  <div className={`text-lg font-bold text-${s.c}-600`}>{fmt(s.v)} so'm</div>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-100">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50"><tr>
                  {['Yo\'nalish','To\'lov turi','Summa','Tur','Izoh','Sana'].map(h => <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">{h}</th>)}
                </tr></thead>
                <tbody className="divide-y divide-slate-50">
                  {history.items.map(m => (
                    <tr key={m.id} className="hover:bg-slate-50">
                      <td className="px-3 py-2.5"><span className={`font-bold ${DIR_COLORS[m.direction]}`}>{m.direction==='in'?'↓ Kirim':'↑ Chiqim'}</span></td>
                      <td className="px-3 py-2.5">{PT_LABELS[m.payment_type] || m.payment_type}</td>
                      <td className={`px-3 py-2.5 font-bold ${DIR_COLORS[m.direction]}`}>{fmt(m.amount)} so'm</td>
                      <td className="px-3 py-2.5 text-slate-500 text-xs">{REF_LABELS[m.reference_type] || m.reference_type}</td>
                      <td className="px-3 py-2.5 text-slate-500 max-w-[180px] truncate">{m.description || '—'}</td>
                      <td className="px-3 py-2.5 text-slate-400 text-xs whitespace-nowrap">{fmtDate(m.created_at)}</td>
                    </tr>
                  ))}
                  {history.items.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">Ma'lumot topilmadi</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ── ExpenseCategories Tab ── */
function ExpenseCategoriesTab() {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ name: '', description: '' });
  const [saving, setSaving] = useState(false);

  const load = () => api.get('/kassa/expense-categories/list').then(r => setList(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      await api.post('/kassa/expense-categories/list', form);
      setForm({ name: '', description: '' }); load(); toast.success("Qo'shildi");
    } catch(ex) { toast.error(ex.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        <h3 className="font-bold text-slate-700 mb-4">Yangi xarajat turi</h3>
        <form onSubmit={save} className="flex gap-3">
          <input required className={inp} value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="Nomi (masalan: Maosh, Ijara...)"/>
          <input className={inp} value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Izoh (ixtiyoriy)"/>
          <button type="submit" disabled={saving} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold whitespace-nowrap disabled:opacity-50">+ Qo'shish</button>
        </form>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full text-sm">
          <thead><tr className="bg-slate-50 border-b border-slate-100">
            {['#','Nomi','Izoh'].map(h => <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map((c,i) => <tr key={c.id} className="hover:bg-slate-50">
              <td className="px-5 py-3 text-slate-400">{i+1}</td>
              <td className="px-5 py-3 font-semibold text-slate-800">{c.name}</td>
              <td className="px-5 py-3 text-slate-500">{c.description || '—'}</td>
            </tr>)}
            {list.length===0 && <tr><td colSpan={3} className="px-5 py-8 text-center text-slate-400">Bo'sh</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main Page ── */
const TABS = [
  { id: 'kassalar', label: '💰 Kassalar' },
  { id: 'categories', label: '📂 Xarajat turlari' },
];

export default function Kassa() {
  const [tab, setTab] = useState('kassalar');
  const [kassalar, setKassalar] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [newForm, setNewForm] = useState({ name: '', type: 'cash', opening_balance: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.get('/kassa').then(r => setKassalar(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const createKassa = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      await api.post('/kassa', { name: newForm.name, type: newForm.type, opening_balance: Number(newForm.opening_balance) || 0 });
      setShowNew(false); setNewForm({ name: '', type: 'cash', opening_balance: '' }); load(); toast.success('Kassa yaratildi');
    } catch (ex) { toast.error(ex.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">💰 Kassa</h1>
          <p className="text-slate-500 text-sm mt-0.5">To'lov turlari bo'yicha kassa boshqaruvi</p>
        </div>
        {tab === 'kassalar' && (
          <button onClick={() => setShowNew(true)} className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            Yangi Kassa
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-5 py-2 text-sm font-semibold rounded-lg transition-all ${tab===t.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'kassalar' && (
        <div className="space-y-4">
          {kassalar.map(k => <KassaCard key={k.id} kassa={k} onRefresh={load}/>)}
          {kassalar.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-12 text-center text-slate-400">
              <div className="text-4xl mb-3">💰</div>
              <p className="font-semibold">Hali kassa yaratilmagan</p>
              <p className="text-sm mt-1">Yangi Kassa tugmasini bosing</p>
            </div>
          )}
        </div>
      )}

      {tab === 'categories' && <ExpenseCategoriesTab/>}

      {/* New kassa modal */}
      {showNew && (
        <Modal title="Yangi Kassa yaratish" onClose={() => setShowNew(false)}>
          <form onSubmit={createKassa} className="space-y-4">
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Kassa nomi *</label>
              <input required className={inp} value={newForm.name} onChange={e => setNewForm({...newForm, name: e.target.value})} placeholder="Masalan: Asosiy Kassa"/></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Turi</label>
              <select className={inp} value={newForm.type} onChange={e => setNewForm({...newForm, type: e.target.value})}>
                <option value="cash">Naqd kassa</option>
                <option value="card">Terminal</option>
                <option value="bank">Bank hisob</option>
              </select></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Boshlang'ich balans (so'm)</label>
              <input type="number" min="0" className={inp} value={newForm.opening_balance} onChange={e => setNewForm({...newForm, opening_balance: e.target.value})} placeholder="0"/></div>
            <div className="flex gap-3 pt-2">
              <button type="button" onClick={() => setShowNew(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm">Bekor</button>
              <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-50">{saving ? '...' : 'Yaratish'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
