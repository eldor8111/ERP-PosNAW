import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { Banknote, CreditCard, Gem, HandCoins, Landmark, PiggyBank } from 'lucide-react';

const fmt = v => Number(v || 0).toLocaleString('uz-UZ');
const fmtDate = d => d ? new Date(d).toLocaleString('uz-UZ') : '—';

const PT_CONFIG = {
  cash:    { label: 'Naqd',    icon: <Banknote className='w-5 h-5 text-emerald-500' />, bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', text: 'text-emerald-400', dot: 'bg-emerald-400' },
  card:    { label: 'Karta',   icon: <CreditCard className='w-5 h-5 text-blue-500' />, bg: 'bg-blue-500/15',    border: 'border-blue-500/30',    text: 'text-blue-400',    dot: 'bg-blue-400'    },
  uzcard:  { label: 'UzCard',  icon: <CreditCard className='w-5 h-5 text-amber-500' />, bg: 'bg-amber-500/15',   border: 'border-amber-500/30',   text: 'text-amber-400',   dot: 'bg-amber-400'   },
  humo:    { label: 'Humo',    icon: <CreditCard className='w-5 h-5 text-indigo-500' />, bg: 'bg-indigo-500/15',  border: 'border-indigo-500/30',  text: 'text-indigo-400',  dot: 'bg-indigo-400'  },
  click:   { label: 'Click',   icon: <CreditCard className='w-5 h-5 text-yellow-500' />, bg: 'bg-yellow-500/15',  border: 'border-yellow-500/30',  text: 'text-yellow-400',  dot: 'bg-yellow-400'  },
  payme:   { label: 'Payme',   icon: <CreditCard className='w-5 h-5 text-red-500' />, bg: 'bg-red-500/15',     border: 'border-red-500/30',     text: 'text-red-400',     dot: 'bg-red-400'     },
  uzum:    { label: 'Uzum',    icon: <CreditCard className='w-5 h-5 text-orange-500' />, bg: 'bg-orange-500/15',  border: 'border-orange-500/30',  text: 'text-orange-400',  dot: 'bg-orange-400'  },
  keshbek: { label: 'Keshbek', icon: <HandCoins className='w-5 h-5 text-purple-500' />, bg: 'bg-purple-500/15',  border: 'border-purple-500/30',  text: 'text-purple-400',  dot: 'bg-purple-400'  },
};
const PT_LABELS = Object.fromEntries(Object.entries(PT_CONFIG).map(([k,v])=>[k, v.icon+' '+v.label]));
const PT_KEYS = Object.keys(PT_CONFIG);

const DIR_COLORS = { in: 'text-emerald-400', out: 'text-red-400' };
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

/* ─────────────────────────────────────────────────────────
   Kassa Card — redesign notes
   Palette (muted, ledger/receipt inspired — used sparingly):
     ink        #16181C   primary text
     ink-soft   #565B63   secondary text
     ink-faint  #9A9EA6   labels / captions
     line       #E7E5DF   hairline borders
     line-soft  #F0EEE8   subtle fills
     paper      #FAF9F6   inset surfaces
     accent     #1F5C4E   deep emerald — "in" / open / primary
     gold       #8C6A38   brass — "out" (withdraw, neutral outflow)
     rust       #A24A3B   muted terracotta — expense / negative
   Type: UI text in the app's default sans; all money figures in
   font-mono with tabular-nums, to read like a real ledger.
   Signature: a dashed "tear line" under the header, standing in
   for a receipt perforation — the one deliberate flourish.
   ───────────────────────────────────────────────────────── */

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
    const r = await api.get('/kassa/categories');
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
        await api.post('/kassa/do-expense', { wallet_id: kassa.id, category_id: Number(form.category_id), amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success('Xarajat qilindi');
      }
      setModal(null);
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  // Local style tokens (self-contained, doesn't rely on the old `inp` constant)
  const field = "w-full px-3 py-2 bg-white border border-[#E7E5DF] rounded-lg text-sm text-[#16181C] placeholder:text-[#B7B4AA] focus:outline-none focus:ring-2 focus:ring-[#1F5C4E]/25 focus:border-[#1F5C4E] transition-colors";
  const ghostBtn = "inline-flex items-center gap-1.5 px-3.5 py-2 text-[13px] font-medium rounded-lg border border-[#E7E5DF] text-[#3C4048] hover:border-[#CFCBBF] hover:bg-[#FAF9F6] transition-colors";
  const cancelBtn = "flex-1 py-2.5 border border-[#E7E5DF] text-[#3C4048] rounded-lg text-sm font-medium hover:bg-[#FAF9F6] transition-colors";

  const typeIcon = {
    cash: <HandCoins className="w-3.5 h-3.5" />,
    card: <CreditCard className="w-3.5 h-3.5" />,
    bank: <Banknote className="w-3.5 h-3.5" />,
  };

  return (
    <div className="rounded-2xl overflow-hidden border border-[#E7E5DF] bg-white shadow-[0_1px_2px_rgba(22,24,28,0.04)] hover:shadow-[0_4px_16px_rgba(22,24,28,0.06)] hover:border-[#D8D5CB] transition-all duration-200">

      {/* Header — quiet, no gradient */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-[#E2DFD3] text-[#565B63]">
                {typeIcon[kassa.type] || <HandCoins className="w-3.5 h-3.5" />}
              </span>
              <h3 className="text-[15px] font-semibold text-[#16181C] tracking-tight">{kassa.name}</h3>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#565B63]">
              <span className={`w-1.5 h-1.5 rounded-full ${isOpen ? 'bg-[#1F5C4E] animate-pulse' : 'bg-[#C7C4B9]'}`} />
              {isOpen ? 'Ochiq' : 'Yopiq'}
            </span>
          </div>
          <div className="text-right">
            <div className="font-mono text-2xl font-semibold text-[#16181C] tabular-nums leading-none">{fmt(total)}</div>
            <div className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-[#9A9EA6]">so'm</div>
          </div>
        </div>
      </div>

      {/* Signature: receipt tear line */}
      <div
        className="h-px w-full"
        style={{ backgroundImage: 'repeating-linear-gradient(90deg, #DEDBD0 0, #DEDBD0 5px, transparent 5px, transparent 10px)' }}
      />

      {/* Payment type balances — ledger strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y sm:divide-y-0 divide-[#EFEDE6] border-b border-[#EFEDE6] bg-[#FCFBF9]">
        {PT_KEYS.map(k => {
          const cfg = PT_CONFIG[k];
          const val = balances[k] || 0;
          return (
            <div key={k} className="px-4 py-3">
              <div className="text-[10px] font-medium uppercase tracking-wider text-[#9A9EA6] mb-1">{cfg.label}</div>
              <div className={`font-mono text-sm font-semibold tabular-nums ${val < 0 ? 'text-[#A24A3B]' : val > 0 ? 'text-[#16181C]' : 'text-[#C7C4B9]'}`}>
                {fmt(val)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="bg-white px-4 py-3 flex flex-wrap gap-2">
        {!isOpen ? (
          <button onClick={() => openModal('open')} className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-[#16181C] hover:bg-[#262930] text-white text-[13px] font-medium rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3l14 9-14 9V3z"/></svg>
            Ochish
          </button>
        ) : (
          <button onClick={() => openModal('close')} className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-[#16181C] hover:bg-[#262930] text-white text-[13px] font-medium rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
            Yopish
          </button>
        )}
        <button onClick={() => openModal('invest')} className={ghostBtn}>
          <svg className="w-4 h-4 text-[#1F5C4E]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3"/></svg>
          Kirim
        </button>
        <button onClick={() => openModal('withdraw')} className={ghostBtn}>
          <svg className="w-4 h-4 text-[#8C6A38]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
          Chiqim
        </button>
        <button onClick={() => openModal('expense')} className={ghostBtn}>
          <svg className="w-4 h-4 text-[#A24A3B]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
          Xarajat
        </button>
        <button onClick={() => openModal('history')} className={`${ghostBtn} ml-auto`}>
          <svg className="w-4 h-4 text-[#565B63]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
          Tarix
        </button>
      </div>

      {/* Open modal */}
      {modal === 'open' && (
        <Modal title="Kassani ochish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Boshlang'ich naqd balans</label>
              <input type="number" className={field} value={form.opening_balance} onChange={e => setForm({...form, opening_balance: e.target.value})} placeholder="0"/>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Izoh</label>
              <input className={field} value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Ixtiyoriy..."/>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('open')} disabled={saving} className="flex-1 py-2.5 bg-[#1F5C4E] hover:bg-[#194B40] text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Ochish'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Close modal */}
      {modal === 'close' && (
        <Modal title="Kassani yopish" onClose={() => setModal(null)} wide>
          <div className="space-y-4">
            <p className="text-sm text-[#565B63]">Har bir to'lov turi uchun haqiqiy summa kiriting:</p>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#E7E5DF]">
                  <th className="text-left px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-[#9A9EA6]">To'lov turi</th>
                  <th className="text-right px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-[#9A9EA6]">Hisoblangan</th>
                  <th className="text-right px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-[#9A9EA6]">Haqiqiy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F0EEE8]">
                {PT_KEYS.map(k => (
                  <tr key={k}>
                    <td className="px-3 py-2.5 text-[#16181C]">{PT_LABELS[k]}</td>
                    <td className="px-3 py-2.5 text-right font-mono font-medium tabular-nums text-[#16181C]">{fmt(balances[k])}</td>
                    <td className="px-3 py-2.5">
                      <input type="number" className="w-32 px-2 py-1.5 bg-white border border-[#E7E5DF] rounded-md text-sm text-right font-mono focus:outline-none focus:ring-2 focus:ring-[#1F5C4E]/25 focus:border-[#1F5C4E]"
                        value={form.actual[k] || ''} onChange={e => setForm({...form, actual: {...form.actual, [k]: e.target.value}})} placeholder={fmt(balances[k])}/>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Izoh</label>
              <textarea rows={2} className={field} value={form.note} onChange={e => setForm({...form, note: e.target.value})} placeholder="Ixtiyoriy..."/>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('close')} disabled={saving} className="flex-1 py-2.5 bg-[#16181C] hover:bg-[#262930] text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Yopish'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Invest / Withdraw modal */}
      {(modal === 'invest' || modal === 'withdraw') && (
        <Modal title={modal === 'invest' ? 'Investitsiya' : 'Chiqarish'} onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">To'lov turi</label>
              <select className={field} value={form.payment_type} onChange={e => setForm({...form, payment_type: e.target.value})}>
                {PT_KEYS.map(k => <option key={k} value={k}>{PT_LABELS[k]}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Summa *</label>
              <input type="number" min="1" className={`${field} font-mono`} value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} placeholder="0"/>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Izoh</label>
              <input className={field} value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Ixtiyoriy..."/>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save(modal)} disabled={saving || !form.amount} className="flex-1 py-2.5 bg-[#16181C] hover:bg-[#262930] text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Expense modal */}
      {modal === 'expense' && (
        <Modal title="Xarajat qilish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Xarajat turi *</label>
              <select className={field} value={form.category_id} onChange={e => setForm({...form, category_id: e.target.value})}>
                <option value="">— Tanlang —</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">To'lov turi</label>
              <div className="flex flex-wrap gap-2">
                {PT_KEYS.map(k => (
                  <button key={k} type="button" onClick={() => setForm({...form, payment_type: k})}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${form.payment_type===k ? 'bg-[#16181C] text-white border-[#16181C]' : 'bg-white border-[#E7E5DF] text-[#565B63] hover:border-[#CFCBBF]'}`}>
                    {PT_LABELS[k]}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Summa *</label>
              <input type="number" min="1" className={`${field} font-mono`} value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} placeholder="0"/>
            </div>
            <div>
              <label className="text-xs font-medium text-[#565B63] block mb-1.5">Izoh</label>
              <input className={field} value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Ixtiyoriy..."/>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('expense')} disabled={saving || !form.amount || !form.category_id} className="flex-1 py-2.5 bg-[#A24A3B] hover:bg-[#8B3F32] text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* History modal */}
      {modal === 'history' && history && (
        <Modal title="Kassa tarixi" onClose={() => setModal(null)} wide>
          <div className="space-y-4">
            <div className="grid grid-cols-3 divide-x divide-[#E7E5DF] border border-[#E7E5DF] rounded-xl overflow-hidden">
              {[
                { l: 'Jami kirim', v: history.summary.total_in, color: '#1F5C4E' },
                { l: 'Jami chiqim', v: history.summary.total_out, color: '#A24A3B' },
                { l: 'Balans', v: history.summary.balance, color: '#16181C' },
              ].map(s => (
                <div key={s.l} className="px-4 py-3 bg-[#FCFBF9]">
                  <div className="text-[10px] font-medium uppercase tracking-wider text-[#9A9EA6] mb-1">{s.l}</div>
                  <div className="font-mono text-base font-semibold tabular-nums" style={{ color: s.color }}>{fmt(s.v)}</div>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto rounded-xl border border-[#E7E5DF]">
              <table className="min-w-full text-sm">
                <thead className="bg-[#FCFBF9] border-b border-[#E7E5DF]">
                  <tr>
                    {['Yo\'nalish','To\'lov turi','Summa','Tur','Izoh','Sana'].map(h => (
                      <th key={h} className="px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-[#9A9EA6]">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F0EEE8]">
                  {history.items.map(m => {
                    const dirColor = m.direction === 'in' ? '#1F5C4E' : '#A24A3B';
                    return (
                      <tr key={m.id} className="hover:bg-[#FCFBF9] transition-colors">
                        <td className="px-3 py-2.5 font-medium" style={{ color: dirColor }}>{m.direction === 'in' ? '↓ Kirim' : '↑ Chiqim'}</td>
                        <td className="px-3 py-2.5 text-[#3C4048]">{PT_LABELS[m.payment_type] || m.payment_type}</td>
                        <td className="px-3 py-2.5 font-mono font-semibold tabular-nums" style={{ color: dirColor }}>{fmt(m.amount)}</td>
                        <td className="px-3 py-2.5 text-[#9A9EA6] text-xs">{REF_LABELS[m.reference_type] || m.reference_type}</td>
                        <td className="px-3 py-2.5 text-[#565B63] max-w-[180px] truncate">{m.description || '—'}</td>
                        <td className="px-3 py-2.5 text-[#9A9EA6] text-xs whitespace-nowrap font-mono">{fmtDate(m.created_at)}</td>
                      </tr>
                    );
                  })}
                  {history.items.length === 0 && (
                    <tr><td colSpan={6} className="px-3 py-8 text-center text-[#9A9EA6]">Ma'lumot topilmadi</td></tr>
                  )}
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

  const load = () => api.get('/categories').then(r => setList(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      await api.post('/categories', form);
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
  { id: 'kassalar', label: 'Kassalar' },
  { id: 'categories', label: 'Xarajat turlari' },
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

  const totalBalance = kassalar.reduce((s,k) => s + (k.balances?.total||0), 0);
  const totalOpen = kassalar.filter(k=>k.is_open).length;

  return (
    <div className="space-y-6">
      {/* Premium Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            Kassa boshqaruvi
          </h1>
          <p className="text-slate-400 text-sm">Barcha kassalar va to'lov turlari</p>
        </div>
        {tab === 'kassalar' && (
          <button onClick={() => setShowNew(true)} className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white text-sm font-bold rounded-lg shadow-md hover:shadow-indigo-200 transition-all">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            Yangi Kassa
          </button>
        )}
      </div>

      {/* Summary Cards */}
      {tab === 'kassalar' && kassalar.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label:'Jami balans',    value: fmt(totalBalance)+" so'm", icon: <Banknote className='w-5 h-5 text-indigo-600' />, bg:'bg-indigo-50',  border:'border-indigo-100', text:'text-indigo-600'  },
            { label:'Ochiq kassalar', value: totalOpen+' ta',            icon: <Gem className='w-5 h-5 text-emerald-600' />, bg:'bg-emerald-50', border:'border-emerald-100', text:'text-emerald-600' },
            { label:'Jami kassalar',  value: kassalar.length+' ta',      icon: <Landmark className='w-5 h-5 text-slate-600' />, bg:'bg-slate-50',   border:'border-slate-200',  text:'text-slate-700'   },
          ].map(c=>(
            <div key={c.label} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4 hover:shadow-md transition-shadow">
              <div className={`w-11 h-11 rounded-xl ${c.bg} border ${c.border} flex items-center justify-center text-xl`}>{c.icon}</div>
              <div>
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{c.label}</div>
                <div className={`text-lg font-black ${c.text}`}>{c.value}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-5 py-2 text-sm cursor-pointer font-bold rounded-lg transition-all ${tab===t.id ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'kassalar' && (
        <div className="grid grid-cols-1 gap-5">
          {kassalar.map(k => <KassaCard key={k.id} kassa={k} onRefresh={load}/>)}
          {kassalar.length === 0 && (
            <div className="bg-white rounded-2xl border-2 border-dashed border-slate-200 p-16 text-center">
              <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center text-3xl mx-auto mb-4">💰</div>
              <p className="font-bold text-slate-600">Hali kassa yaratilmagan</p>
              <p className="text-sm text-slate-400 mt-1">Yangi Kassa tugmasini bosib boshlang</p>
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
