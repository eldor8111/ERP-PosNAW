import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { Banknote, CreditCard, Gem, HandCoins, Landmark, PiggyBank } from 'lucide-react';

const fmt = v => Number(v || 0).toLocaleString('uz-UZ');
const fmtDate = d => d ? new Date(d).toLocaleString('uz-UZ') : '—';

const PT_CONFIG = {
  cash: { label: 'Naqd', icon: <Banknote className='w-5 h-5 text-emerald-500' />, bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', text: 'text-emerald-400', dot: 'bg-emerald-400' },
  card: { label: 'Karta', icon: <CreditCard className='w-5 h-5 text-blue-500' />, bg: 'bg-blue-500/15', border: 'border-blue-500/30', text: 'text-blue-400', dot: 'bg-blue-400' },
  uzcard: { label: 'UzCard', icon: <CreditCard className='w-5 h-5 text-amber-500' />, bg: 'bg-amber-500/15', border: 'border-amber-500/30', text: 'text-amber-400', dot: 'bg-amber-400' },
  humo: { label: 'Humo', icon: <CreditCard className='w-5 h-5 text-indigo-500' />, bg: 'bg-indigo-500/15', border: 'border-indigo-500/30', text: 'text-indigo-400', dot: 'bg-indigo-400' },
  click: { label: 'Click', icon: <CreditCard className='w-5 h-5 text-yellow-500' />, bg: 'bg-yellow-500/15', border: 'border-yellow-500/30', text: 'text-yellow-400', dot: 'bg-yellow-400' },
  payme: { label: 'Payme', icon: <CreditCard className='w-5 h-5 text-red-500' />, bg: 'bg-red-500/15', border: 'border-red-500/30', text: 'text-red-400', dot: 'bg-red-400' },
  uzum: { label: 'Uzum', icon: <CreditCard className='w-5 h-5 text-orange-500' />, bg: 'bg-orange-500/15', border: 'border-orange-500/30', text: 'text-orange-400', dot: 'bg-orange-400' },
  keshbek: { label: 'Keshbek', icon: <HandCoins className='w-5 h-5 text-purple-500' />, bg: 'bg-purple-500/15', border: 'border-purple-500/30', text: 'text-purple-400', dot: 'bg-purple-400' },
};
const getBalanceValue = (val) => {
  if (!val) return 0;
  if (Array.isArray(val)) {
    return val.reduce((sum, item) => sum + Number(item?.value || 0), 0);
  }
  return Number(val || 0);
};

const PT_LABELS = Object.fromEntries(Object.entries(PT_CONFIG).map(([k, v]) => [k, v.label]));
const PT_KEYS = Object.keys(PT_CONFIG);

const DIR_COLORS = { in: 'text-emerald-400', out: 'text-red-400' };
const REF_LABELS = {
  sale: 'Sotuv', supplier_payment: "Ta'minotchi to'lovi",
  expense: 'Xarajat', invest: 'Investitsiya',
  withdraw: 'Chiqarish', opening: 'Ochilish balansi',
  customer_payment: "Mijoz to'lovi",
  closing_inkasso: 'Kassa Yopilishi (Inkassatsiya)',
  closing_adjustment: 'Kassa Yopilishi (Qoldiq farqi)',
  transfer_in: 'Kassadan Qabul',
  transfer_out: "Kassaga O'tkazma",
  transfer_out_pending: "O'tkazma (Kutilmoqda)",
  transfer_rejected: "O'tkazma (Bekor qilingan)"
};

const inp = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';
const btn = (color = 'indigo') => `px-4 py-2 text-sm font-semibold rounded-xl text-white bg-${color}-600 hover:bg-${color}-700 transition-colors`;

/* ── Modal wrapper ── */
function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className={`bg-white rounded-2xl shadow-2xl w-full ${wide ? 'max-w-7xl' : 'max-w-md'} max-h-[90vh] flex flex-col`} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">✕</button>
        </div>
        <div className="p-6 overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
}

function KassaCard({ kassa, onRefresh, allKassalar = [] }) {
  const [modal, setModal] = useState(null);
  const [history, setHistory] = useState(null);
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);
  const [directionFilter, setDirectionFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState();
  const [closeResult, setCloseResult] = useState(null); // Z-report farqi
  const [pendingTransfers, setPendingTransfers] = useState([]);

  const filteredHistory = (history?.items && Array.isArray(history.items) ? history.items : []).filter(it => {
    if (directionFilter !== 'all' && it.direction !== directionFilter) return false;
    if (dateFilter && it.created_at.substring(0, 10) < dateFilter) return false;
    return true;
  });

  // Form states
  const [form, setForm] = useState({
    amount: '', payment_type: 'cash', currency: 'UZS', description: '',
    category_id: '', opening_balance: '', actual: {}, note: '',
    receiver_wallet_id: ''
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

  const loadPendingTransfers = useCallback(async () => {
    try {
      const r = await api.get(`/kassa/${kassa.id}/transfers/pending`);
      setPendingTransfers(r.data || []);
    } catch { setPendingTransfers([]); }
  }, [kassa.id]);

  const openModal = async (type) => {
    setForm({ amount: '', payment_type: 'cash', currency: 'UZS', description: '', category_id: '', opening_balance: '', actual: {}, note: '', receiver_wallet_id: '' });
    setCloseResult(null);
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
        // Blind Close: kassir kiritgan summani yuborish, hisoblanganni ko'rsatmasdan
        const actual_amounts = {};
        PT_KEYS.forEach(k => {
          if (form.actual[k]) {
            Object.entries(form.actual[k]).forEach(([curr, val]) => {
              if (val !== undefined && val !== '') {
                if (!actual_amounts[k]) actual_amounts[k] = {};
                actual_amounts[k][curr] = Number(val);
              }
            });
          }
        });
        const res = await api.post(`/kassa/${kassa.id}/close`, { actual_amounts, note: form.note });
        const diff = res.data?.difference || {};
        setCloseResult(diff);
        // Farq bo'lsa natijani ko'rsat, yo'q bo'lsa modalni yopamiz
        if (Object.keys(diff).length === 0) {
          toast.success('Kassa yopildi. Farq yo\'q ✅');
          setModal(null);
        } else {
          toast.success('Kassa yopildi. Farqni tekshiring 👇');
          // modal ochiq qoladi, faqat natija ko'rsatiladi
        }
      } else if (action === 'invest') {
        await api.post(`/kassa/${kassa.id}/invest`, { amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success("Investitsiya qo'shildi");
      } else if (action === 'withdraw') {
        await api.post(`/kassa/${kassa.id}/withdraw`, { amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success('Chiqarildi');
      } else if (action === 'expense') {
        await api.post('/kassa/do-expense', { wallet_id: kassa.id, category_id: Number(form.category_id), amount: Number(form.amount), payment_type: form.payment_type, description: form.description });
        toast.success('Xarajat qilindi');
      } else if (action === 'transfer') {
        if (!form.receiver_wallet_id || !form.amount) { toast.error("Qabul qiluvchi kassani va summani kiriting"); return; }
        const res = await api.post(`/kassa/${kassa.id}/transfer/out`, {
          receiver_wallet_id: Number(form.receiver_wallet_id),
          amount: Number(form.amount),
          currency: form.currency,
          payment_type: form.payment_type,
          note: form.note,
        });
        toast.success(`Transfer #${res.data.transfer_id} muvaffaqiyatli amalga oshirildi ✅`);
      }
      if (action !== 'close') setModal(null);
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  // Local style tokens — plain Tailwind palette only
  const field = "w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 cursor-pointer focus:ring-violet-500/30 focus:border-violet-500 transition-colors";
  const ghostBtn = "inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg border border-green-300 text-slate-700 hover:bg-green-50 hover:border-green-300 cursor-pointer transition-colors";
  const cancelBtn = "flex-1 py-2.5 border border-slate-200 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors cursor-pointer";
  const primaryBtn = "inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors cursor-pointer";

  const typeIcon = {
    cash: <HandCoins className="w-4 h-4" />,
    card: <CreditCard className="w-4 h-4" />,
    bank: <Banknote className="w-4 h-4" />,
  };

  return (
    <div className="rounded-2xl overflow-hidden border border-green-600/30 bg-white shadow-sm hover:shadow-md shadow-green-500/30 transition-shadow duration-200">
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-slate-50 border border-green-300 text-green-700">
              {typeIcon[kassa.type] || <HandCoins className="w-4 h-4" />}
            </span>

            <h3 className="text-[16px] leading-none font-semibold text-slate-900 tracking-tight">{kassa.name}</h3>

            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500">
              <span className={`w-1.5 h-1.5 rounded-full ${isOpen ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
              <span className='leading-none'>{isOpen ? 'ochiq' : 'yopiq'}</span>
            </span>
          </div>

          <div className="text-right">
            <div className="text-2xl font-bold text-slate-900 tabular-nums leading-none">{fmt(total)}</div>
            <div className="mt-1.5 text-[10px] font-medium uppercase tracking-wider text-slate-400">so'm</div>
          </div>
        </div>
      </div>

      {/* Payment type balances */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-4 px-5 py-4 border-t border-green-100 bg-green-50/60">
        {PT_KEYS.map(k => {
          const cfg = PT_CONFIG[k];
          const val = balances[k] || 0;
          return (
            <div key={k}>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-green-700 mb-1">{cfg.label}</div>
              <div className={`text-[15px] font-semibold tabular-nums ${val < 0 ? 'text-rose-600' : 'text-slate-900'}`}>
                {val && Array.isArray(val) ? (
                  val.map((item) => (
                    <span key={item.currency} className='flex flex-col'>
                      {fmt(item.value)} {item.currency}
                    </span>
                  ))
                ) : (
                  <span>{fmt(val)}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="px-5 py-4 border-t border-slate-100 flex flex-wrap gap-2">
        {!isOpen ? (
          <button onClick={() => openModal('open')} className={primaryBtn}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3l14 9-14 9V3z" /></svg>
            Ochish
          </button>
        ) : (
          <button onClick={() => openModal('close')} className={primaryBtn}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
            Yopish
          </button>
        )}
        <button onClick={() => openModal('invest')} className={ghostBtn}>
          <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>
          Kirim
        </button>
        <button onClick={() => openModal('withdraw')} className={ghostBtn}>
          <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>
          Chiqim
        </button>
        <button onClick={() => openModal('expense')} className={ghostBtn}>
          <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
          Xarajat
        </button>
        {isOpen && allKassalar.filter(k => k.id !== kassa.id).length > 0 && (
          <button onClick={() => openModal('transfer')} className={`${ghostBtn} border-violet-300 text-violet-700 hover:bg-violet-50 hover:border-violet-400`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
            Transfer
          </button>
        )}
        <button onClick={() => openModal('history')} className={`${ghostBtn} ml-auto`}>
          <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
          Tarix
        </button>
      </div>

      {/* Open modal */}
      {modal === 'open' && (
        <Modal title="Kassani ochish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Boshlang'ich naqd balans</label>
              <input type="number" className={field} value={form.opening_balance} onChange={e => setForm({ ...form, opening_balance: e.target.value })} placeholder="0" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Izoh</label>
              <input className={field} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} placeholder="Ixtiyoriy..." />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('open')} disabled={saving} className="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Ochish'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Close modal — BLIND CLOSE (kassir hisoblanganni ko'rmaydi) */}
      {modal === 'close' && (() => {
        return (
          <Modal title="Kassani yopish (Ko'r-ko'rona)" onClose={() => { setModal(null); setCloseResult(null); }} wide>
            <div className="space-y-5">
              {/* Farq natijasi (faqat yopishdan keyin chiqadi) */}
              {closeResult && (
                <div className="rounded-xl border p-4 bg-amber-50 border-amber-200">
                  <p className="text-sm font-bold text-amber-800 mb-3">⚖️ Z-Report: Kassa yopildi. Farq:</p>
                  {Object.entries(closeResult).length === 0 ? (
                    <p className="text-emerald-700 font-semibold">✅ Farq yo'q — hammasi to'g'ri!</p>
                  ) : (
                    <div className="space-y-1">
                      {Object.entries(closeResult).map(([ptype, currs]) =>
                        Object.entries(currs).map(([curr, diff]) => (
                          <div key={`${ptype}-${curr}`} className="flex justify-between text-sm">
                            <span className="text-amber-700 font-medium">{PT_CONFIG[ptype]?.label || ptype} ({curr})</span>
                            <span className={`font-bold ${diff > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                              {diff > 0 ? `−${fmt(diff)} (Kamomad)` : `+${fmt(Math.abs(diff))} (Ortiqcha)`}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                  <button onClick={() => { setModal(null); setCloseResult(null); onRefresh(); }}
                    className="mt-3 w-full py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold rounded-lg transition-colors">
                    Yopish ✓
                  </button>
                </div>
              )}

              {!closeResult && (
                <>
                  {/* Ogohlantirish */}
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-700">
                    ℹ️ <strong>Ko'r-ko'rona tekshiruv:</strong> Kassadagi hisoblangan summani <strong>ko'rsatmasdan</strong> faqat
                    siz sanagan summani kiriting. Tizim o'zi farqni hisoblab, Z-reportga yozadi.
                  </div>

                  <p className="text-sm text-slate-600 font-medium">Har bir to'lov turi uchun siz <strong>sanab</strong> chiqgan summani kiriting:</p>
                  <div className="overflow-x-auto rounded-xl border border-slate-200">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                          <th className="text-left px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">To'lov turi</th>
                          <th className="text-center px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Valyuta</th>
                          <th className="text-right px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Siz sanagan summa</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {PT_KEYS.map(k => {
                          const cfg = PT_CONFIG[k];
                          const bVal = balances[k];
                          // Agar bVal massiv bo'lsa, undagi barcha valyutalarni olamiz.
                          // Agar bo'sh bo'lsa yoki undefined bo'lsa, faqat UZS ko'rsatamiz.
                          let currencies = ['UZS'];
                          if (Array.isArray(bVal) && bVal.length > 0) {
                            currencies = bVal.map(item => item.currency);
                          }
                          
                          return currencies.map((curr, idx) => (
                            <tr key={`${k}-${curr}`} className="hover:bg-slate-50/50">
                              {idx === 0 ? (
                                <td rowSpan={currencies.length} className="px-3 py-2.5 text-slate-900 font-medium align-top bg-white/50">
                                  <div className="flex items-center gap-2">
                                    {cfg.icon}
                                    <span>{cfg.label}</span>
                                  </div>
                                </td>
                              ) : null}
                              <td className="px-3 py-2.5 text-center font-medium text-slate-600">
                                {curr}
                              </td>
                              <td className="px-3 py-2.5 text-right">
                                <input
                                  type="number"
                                  min="0"
                                  className="w-40 px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-right focus:outline-none focus:ring-2 focus:ring-violet-500/30 focus:border-violet-500"
                                  value={form.actual[k]?.[curr] !== undefined ? form.actual[k][curr] : ''}
                                  onChange={e => setForm({ 
                                    ...form, 
                                    actual: { 
                                      ...form.actual, 
                                      [k]: { ...(form.actual[k] || {}), [curr]: e.target.value } 
                                    } 
                                  })}
                                  placeholder={`0 ${curr}`}
                                />
                              </td>
                            </tr>
                          ));
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-600 block mb-1.5">Izoh</label>
                    <textarea rows={2} className={field} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} placeholder="Ixtiyoriy..." />
                  </div>
                  <div className="flex gap-3 pt-2">
                    <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
                    <button onClick={() => save('close')} disabled={saving} className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-sm font-bold disabled:opacity-50 transition-colors">
                      {saving ? 'Yopilmoqda...' : '🔒 Kassani Yopish'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </Modal>
        );
      })()}

      {/* Transfer modal */}
      {modal === 'transfer' && (
        <Modal title="💸 Kassadan kassaga o'tkazma" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div className="p-3 bg-violet-50 border border-violet-200 rounded-xl text-xs text-violet-700">
              ℹ️ <strong>Tezkor o'tkazma:</strong> Pul darhol ikkinchi kassaga o'tadi va ushbu kassadan yechiladi. Qabul qiluvchidan tasdiqlash talab etilmaydi.
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Qabul qiluvchi Kassa *</label>
              <select className={field} value={form.receiver_wallet_id} onChange={e => setForm({ ...form, receiver_wallet_id: e.target.value })}>
                <option value="">— Kassani tanlang —</option>
                {allKassalar.filter(k => k.id !== kassa.id).map(k => (
                  <option key={k.id} value={k.id}>{k.name} {!k.is_open ? '(yopiq)' : ''}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1.5">To'lov turi</label>
                <select className={field} value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })}>
                  {PT_KEYS.map(k => <option key={k} value={k}>{PT_LABELS[k]}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1.5">Valyuta</label>
                <select className={field} value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>
                  <option value="UZS">UZS (so'm)</option>
                  <option value="USD">USD (dollar)</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Summa *</label>
              <input type="number" min="1" className={field} value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="0" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Izoh</label>
              <input className={field} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} placeholder="Ixtiyoriy..." />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('transfer')} disabled={saving || !form.receiver_wallet_id || !form.amount}
                className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg text-sm font-bold disabled:opacity-50 transition-colors">
                {saving ? 'Yuborilmoqda...' : '📤 Yuborish'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Invest / Withdraw modal */}
      {(modal === 'invest' || modal === 'withdraw') && (
        <Modal title={modal === 'invest' ? 'Investitsiya' : 'Chiqarish'} onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">To'lov turi</label>
              <select className={field} value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })}>
                {PT_KEYS.map(k => <option key={k} value={k}>{PT_LABELS[k]}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Summa *</label>
              <input type="number" min="1" className={field} value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="0" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Izoh</label>
              <input className={field} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Ixtiyoriy..." />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save(modal)} disabled={saving || !form.amount} className="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Expense modal */}
      {modal === 'expense' && (
        <Modal title="Xarajat qilish" onClose={() => setModal(null)}>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Xarajat turi *</label>
              <select className={field} value={form.category_id} onChange={e => setForm({ ...form, category_id: e.target.value })}>
                <option value="">— Tanlang —</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">To'lov turi</label>
              <div className="flex flex-wrap gap-2">
                {PT_KEYS.map(k => (
                  <button key={k} type="button" onClick={() => setForm({ ...form, payment_type: k })}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${form.payment_type === k ? 'bg-slate-900 text-white border-slate-900' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'}`}>
                    {PT_LABELS[k]}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Summa *</label>
              <input type="number" min="1" className={field} value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} placeholder="0" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1.5">Izoh</label>
              <input className={field} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Ixtiyoriy..." />
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setModal(null)} className={cancelBtn}>Bekor</button>
              <button onClick={() => save('expense')} disabled={saving || !form.amount || !form.category_id} className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors">{saving ? '...' : 'Tasdiqlash'}</button>
            </div>
          </div>
        </Modal>
      )}

      {/* History modal */}
      {modal === 'history' && filteredHistory && (
        <Modal title="Kassa tarixi" onClose={() => setModal(null)} wide>
          <div className="space-y-6">
            
            {/* Header / Summary / Filters */}
            <div className="flex flex-col md:flex-row gap-5 items-start md:items-center justify-between bg-slate-50 p-4 rounded-2xl border border-slate-200">
              
              <div className="flex gap-4 items-center flex-1">
                <div className="relative">
                  <select className="pl-4 pr-9 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 appearance-none focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 shadow-sm transition-all" value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value)}>
                    <option value="all">🔄 Barcha</option>
                    <option value="in">↓ Kirimlar</option>
                    <option value="out">↑ Chiqimlar</option>
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </div>
                </div>

                <div className="relative">
                  <input type="date" className="pl-4 pr-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-all" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
                </div>
                {dateFilter && (
                  <button onClick={() => setDateFilter('')} className="text-xs font-bold text-rose-500 hover:text-rose-600 px-3 py-1.5 rounded-lg hover:bg-rose-100 transition-colors">Tozalash</button>
                )}
              </div>

              {/* Balans tahlili (Summary) */}
              <div className="flex gap-4 md:gap-8 bg-white px-5 py-3 rounded-xl shadow-sm border border-slate-100 items-center justify-end w-full md:w-auto">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jami Kirim</p>
                  <p className="text-sm font-bold text-emerald-600 mt-0.5 tabular-nums">+{fmt(history.summary.total_in)}</p>
                </div>
                <div className="w-px h-8 bg-slate-200"></div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Jami Chiqim</p>
                  <p className="text-sm font-bold text-rose-600 mt-0.5 tabular-nums">−{fmt(history.summary.total_out)}</p>
                </div>
                <div className="w-px h-8 bg-slate-200"></div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Balans</p>
                  <p className="text-sm font-extrabold text-slate-800 mt-0.5 tabular-nums">{fmt(history.summary.balance)}</p>
                </div>
              </div>

            </div>

            {/* Table */}
            <div className="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm bg-white">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-500">
                    <th className="px-5 py-4 font-bold text-[13px] uppercase tracking-wider">Tranzaksiya</th>
                    <th className="px-5 py-4 font-bold text-[13px] uppercase tracking-wider text-right">Summa</th>
                    <th className="px-5 py-4 font-bold text-[13px] uppercase tracking-wider">Tafsilotlar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredHistory.map(m => {
                    const isIn = m.direction === 'in';
                    const Icon = isIn ? (
                      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>
                    ) : (
                      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>
                    );
                    
                    return (
                      <tr key={m.id} className="hover:bg-slate-50/50 transition-colors group">
                        
                        <td className="px-5 py-4 align-top w-[20%] min-w-[170px]">
                          <div className="flex items-start gap-4">
                            <div className={`mt-0.5 p-2 rounded-xl flex-shrink-0 ${isIn ? 'bg-emerald-100/50 text-emerald-600' : 'bg-rose-100/50 text-rose-600'}`}>
                              {Icon}
                            </div>
                            <div>
                              <p className={`font-bold text-[16px] leading-tight ${isIn ? 'text-emerald-700' : 'text-rose-700'}`}>
                                {isIn ? 'Kirim' : 'Chiqim'}
                              </p>
                              <p className="text-[13px] text-slate-500 font-semibold mt-1.5 uppercase tracking-widest flex items-center gap-1.5">
                                {PT_CONFIG[m.payment_type]?.icon}
                                <span>{PT_CONFIG[m.payment_type]?.label || m.payment_type}</span>
                              </p>
                            </div>
                          </div>
                        </td>

                        <td className="px-5 py-4 align-top text-right w-[20%] min-w-[170px]">
                          <div className="flex flex-col items-end">
                            <p className={`font-black tabular-nums text-[18px] tracking-tight ${isIn ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {isIn ? '+' : '−'}{fmt(m.amount)}
                            </p>
                            <span className="inline-flex items-center justify-center mt-1.5 px-2.5 py-1 rounded text-[12px] font-bold bg-slate-100 text-slate-500">
                              {m.currency || 'UZS'}
                            </span>
                          </div>
                        </td>

                        <td className="px-5 py-4 align-top w-[60%]">
                          <div className="flex flex-col gap-2">
                            <div className="flex flex-wrap items-center gap-2.5">
                              <span className="inline-flex items-center justify-center px-2.5 py-1 rounded-md bg-indigo-50 border border-indigo-100 text-[13px] font-bold text-indigo-700 uppercase tracking-wide">
                                {REF_LABELS[m.reference_type] || m.reference_type}
                              </span>
                              <span className="text-[13px] font-semibold text-slate-400 flex items-center gap-1.5">
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                {fmtDate(m.created_at)}
                              </span>
                            </div>
                            
                            {m.description && (
                              <p className="text-[15px] font-medium text-slate-600 leading-snug mt-0.5 line-clamp-2">
                                {m.description}
                              </p>
                            )}
                          </div>
                        </td>
                        
                      </tr>
                    );
                  })}

                  {filteredHistory.length === 0 && (
                    <tr>
                      <td colSpan={3} className="px-5 py-16 text-center">
                        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-slate-50 border border-slate-100 text-slate-300 mb-4 shadow-sm">
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
                        </div>
                        <h4 className="text-[15px] font-bold text-slate-700">Ma'lumot topilmadi</h4>
                        <p className="text-sm font-medium text-slate-400 mt-1">Ushbu filtr bo'yicha hech qanday tranzaksiya mavjud emas.</p>
                      </td>
                    </tr>
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

  const load = () => api.get('/categories').then(r => setList(r.data)).catch(() => { });
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      await api.post('/categories', form);
      setForm({ name: '', description: '' }); load(); toast.success("Qo'shildi");
    } catch (ex) { toast.error(ex.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        <h3 className="font-bold text-slate-700 mb-4">Yangi xarajat turi</h3>
        <form onSubmit={save} className="flex gap-3">
          <input required className={inp} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Nomi (masalan: Maosh, Ijara...)" />
          <input className={inp} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Izoh (ixtiyoriy)" />
          <button type="submit" disabled={saving} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold whitespace-nowrap disabled:opacity-50">+ Qo'shish</button>
        </form>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full text-sm">
          <thead><tr className="bg-slate-50 border-b border-slate-100">
            {['#', 'Nomi', 'Izoh'].map(h => <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map((c, i) => <tr key={c.id} className="hover:bg-slate-50">
              <td className="px-5 py-3 text-slate-400">{i + 1}</td>
              <td className="px-5 py-3 font-semibold text-slate-800">{c.name}</td>
              <td className="px-5 py-3 text-slate-500">{c.description || '—'}</td>
            </tr>)}
            {list.length === 0 && <tr><td colSpan={3} className="px-5 py-8 text-center text-slate-400">Bo'sh</td></tr>}
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

  const load = async () => {
    await api.get('/kassa').then(r => setKassalar(r.data)).catch(() => { });
  };

  useEffect(() => { load(); }, []);

  const createKassa = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      await api.post('/kassa', { name: newForm.name, type: newForm.type, opening_balance: Number(newForm.opening_balance) || 0 });
      setShowNew(false); setNewForm({ name: '', type: 'cash', opening_balance: '' }); load(); toast.success('Kassa yaratildi');
    } catch (ex) { toast.error(ex.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const totalBalance = kassalar.reduce((s, k) => s + (k.balances?.total || 0), 0);
  const totalOpen = kassalar.filter(k => k.is_open).length;

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
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Yangi Kassa
          </button>
        )}
      </div>

      {/* Summary Cards */}
      {tab === 'kassalar' && kassalar.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Jami balans', value: fmt(totalBalance) + " so'm", icon: <Banknote className='w-5 h-5 text-indigo-600' />, bg: 'bg-indigo-50', border: 'border-indigo-100', text: 'text-indigo-600' },
            { label: 'Ochiq kassalar', value: totalOpen + ' ta', icon: <Gem className='w-5 h-5 text-emerald-600' />, bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600' },
            { label: 'Jami kassalar', value: kassalar.length + ' ta', icon: <Landmark className='w-5 h-5 text-slate-600' />, bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-700' },
          ].map(c => (
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
            className={`px-5 py-2 text-sm cursor-pointer font-bold rounded-lg transition-all ${tab === t.id ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'kassalar' && (
        <div className="grid grid-cols-1 gap-5">
          {kassalar.map(k => <KassaCard key={k.id} kassa={k} onRefresh={load} allKassalar={kassalar} />)}
          {kassalar.length === 0 && (
            <div className="bg-white rounded-2xl border-2 border-dashed border-slate-200 p-16 text-center">
              <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center text-3xl mx-auto mb-4">💰</div>
              <p className="font-bold text-slate-600">Hali kassa yaratilmagan</p>
              <p className="text-sm text-slate-400 mt-1">Yangi Kassa tugmasini bosib boshlang</p>
            </div>
          )}
        </div>
      )}

      {tab === 'categories' && <ExpenseCategoriesTab />}

      {/* New kassa modal */}
      {showNew && (
        <Modal title="Yangi Kassa yaratish" onClose={() => setShowNew(false)}>
          <form onSubmit={createKassa} className="space-y-4">
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Kassa nomi *</label>
              <input required className={inp} value={newForm.name} onChange={e => setNewForm({ ...newForm, name: e.target.value })} placeholder="Masalan: Asosiy Kassa" /></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Turi</label>
              <select className={inp} value={newForm.type} onChange={e => setNewForm({ ...newForm, type: e.target.value })}>
                <option value="cash">Naqd kassa</option>
                <option value="card">Terminal</option>
                <option value="bank">Bank hisob</option>
              </select></div>
            <div><label className="text-xs font-semibold text-slate-600 block mb-1">Boshlang'ich balans (so'm)</label>
              <input type="number" min="0" className={inp} value={newForm.opening_balance} onChange={e => setNewForm({ ...newForm, opening_balance: e.target.value })} placeholder="0" /></div>
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
