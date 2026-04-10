import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

/* ── helpers ──────────────────────────────────────── */
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const Avatar = ({ name, size = 'sm' }) => {
  const sizes = { sm: 'w-8 h-8 text-sm', lg: 'w-11 h-11 text-base' };
  const colors = ['bg-indigo-100 text-indigo-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-rose-100 text-rose-600', 'bg-amber-100 text-amber-600'];
  const c = colors[(name?.charCodeAt(0) || 0) % colors.length];
  return <div className={`${sizes[size]} ${c} rounded-full flex items-center justify-center font-bold shrink-0`}>{name?.charAt(0).toUpperCase()}</div>;
};

const StarRating = ({ value, onChange, readOnly = false }) => (
  <div className="flex gap-0.5">
    {[1,2,3,4,5].map(s => (
      <button key={s} type="button" disabled={readOnly}
        onClick={() => onChange && onChange(s)}
        className={`text-xl transition-colors ${(value || 0) >= s ? 'text-amber-400' : 'text-slate-200'} ${!readOnly && 'hover:text-amber-300 cursor-pointer'}`}>
        ★
      </button>
    ))}
  </div>
);

const inputCls = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500';

/* ══════════════════════════════════════════════════
   TAB 1 — MIJOZLAR
══════════════════════════════════════════════════ */
const TIERS = {
  Gold:     { label: 'Gold',     cls: 'bg-amber-100 text-amber-700' },
  Silver:   { label: 'Silver',   cls: 'bg-slate-200 text-slate-700' },
  Bronze:   { label: 'Bronze',   cls: 'bg-orange-100 text-orange-700' },
  Standard: { label: 'Standard', cls: 'bg-slate-100 text-slate-500' },
};
const tierOf = (pts) => pts >= 10000 ? 'Gold' : pts >= 5000 ? 'Silver' : pts >= 1000 ? 'Bronze' : 'Standard';
const emptyCustomer = { name: '', phone: '', debt_limit: '', loyalty_points: 0 };

function MijozlarTab() {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(emptyCustomer);
  const [payAmt, setPayAmt] = useState('');
  const [ptsDelta, setPtsDelta] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = (q = search) => api.get(`/customers${q ? '?search=' + encodeURIComponent(q) : ''}`).then(r => setList(r.data)).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => load(search), 400); return () => clearTimeout(t); }, [search]);

  const close = () => { setModal(null); setSel(null); setErr(''); };

  const handleSave = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try {
      const p = { name: form.name, phone: form.phone || null, debt_limit: Number(form.debt_limit)||0, loyalty_points: Number(form.loyalty_points)||0 };
      if (modal === 'add') await api.post('/customers', p);
      else await api.put(`/customers/${sel.id}`, p);
      close(); load();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const handlePay = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try { await api.post(`/customers/${sel.id}/pay-debt`, { amount: Number(payAmt), reason: "To'lov" }); close(); load(); }
    catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const handlePoints = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try { await api.post(`/customers/${sel.id}/adjust-points`, { delta: Number(ptsDelta), reason: 'Manual' }); close(); load(); }
    catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const del = async (id) => { if (!confirm(t('confirm.delete'))) return; await api.delete(`/customers/${id}`); load(); };

  const totalDebt = list.reduce((s, c) => s + Number(c.debt_balance || 0), 0);

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: t('customer.totalCustomers'), val: list.length, color: 'indigo' },
          { label: t('customer.totalDebt'), val: fmt(totalDebt) + ` ${t('common.sum')}`, color: 'red' },
          { label: t('customer.totalDebtors'), val: list.filter(c => Number(c.debt_balance) > 0).length, color: 'amber' },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
            <div className={`w-10 h-10 rounded-xl bg-${s.color}-100 flex items-center justify-center shrink-0`} />
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{s.label}</div>
              <div className={`text-xl font-bold text-${s.color}-600 mt-0.5`}>{s.val}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          <input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Qidirish..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <button onClick={() => { setForm(emptyCustomer); setErr(''); setModal('add-c'); }} className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
          Yangi Mijoz
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">
            {[t('common.name'), t('common.phone'), t('customer.debtBalance'), t('customer.creditLimit'), t('customer.bonusBalance'), ''].map(h => <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(c => (
              <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-4"><div className="flex items-center gap-2.5"><Avatar name={c.name}/><span className="text-sm font-medium text-slate-800">{c.name}</span></div></td>
                <td className="px-5 py-4 text-sm text-slate-500">{c.phone || '—'}</td>
                <td className="px-5 py-4 text-sm font-semibold"><span className={Number(c.debt_balance) > 0 ? 'text-red-500' : 'text-emerald-600'}>{fmt(c.debt_balance)} {t('common.sum')}</span></td>
                <td className="px-5 py-4 text-sm text-slate-500">{fmt(c.debt_limit)} {t('common.sum')}</td>
                <td className="px-5 py-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-amber-600">⭐ {c.loyalty_points}</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${TIERS[tierOf(c.loyalty_points||0)].cls}`}>{TIERS[tierOf(c.loyalty_points||0)].label}</span>
                  </div>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-1">
                    {Number(c.debt_balance) > 0 && <button onClick={() => { setSel(c); setPayAmt(''); setModal('pay'); }} title="Qarz to'lash" className="p-1.5 text-emerald-500 hover:bg-emerald-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg></button>}
                    <button onClick={() => { setSel(c); setPtsDelta(''); setModal('points'); }} title="Ballar" className="p-1.5 text-amber-500 hover:bg-amber-50 rounded-lg">⭐</button>
                    <button onClick={() => { setForm({ name: c.name, phone: c.phone||'', debt_limit: c.debt_limit||0, loyalty_points: c.loyalty_points||0 }); setSel(c); setModal('add-c'); }} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
                    <button onClick={() => del(c.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={6} className="px-5 py-12 text-center text-slate-400 text-sm">{t('customer.noCustomers')}</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Add/Edit Modal */}
      {modal === 'add-c' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{sel ? t('customer.editCustomer') : t('customer.addCustomer')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('common.name')} *</label>
                  <input required className={inputCls} value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="Javohir Toshmatov"/>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.phone') || 'Telefon'}</label>
                  <input className={inputCls} value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} placeholder="+998 90 123 45 67"/>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.creditLimit')} ({t('common.sum')})</label>
                  <input type="number" min="0" className={inputCls} value={form.debt_limit} onChange={e => setForm({...form, debt_limit: e.target.value})} placeholder="0"/>
                </div>
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? '...' : t('common.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Pay Modal */}
      {modal === 'pay' && sel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('customer.payDebt')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <form onSubmit={handlePay} className="p-6 space-y-4">
              <div className="p-3 bg-slate-50 rounded-xl text-sm">
                <div className="font-semibold text-slate-800">{sel.name}</div>
                <div className="text-red-500 font-bold mt-0.5">Qarz: {fmt(sel.debt_balance)} so'm</div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.paymentAmount')} *</label>
                <input type="number" min="1" max={sel.debt_balance} required autoFocus className={inputCls} value={payAmt} onChange={e => setPayAmt(e.target.value)} placeholder="Miqdor..."/>
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? '...' : t('common.confirm')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Points Modal */}
      {modal === 'points' && sel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('customer.loyaltyPoints')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <form onSubmit={handlePoints} className="p-6 space-y-4">
              <div className="p-3 bg-amber-50 rounded-xl text-sm">
                <div className="font-semibold">{sel.name}</div>
                <div className="text-amber-600 font-bold">⭐ {sel.loyalty_points} ball</div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">O'zgarish (+ yoki -)</label>
                <input type="number" required autoFocus className={inputCls} value={ptsDelta} onChange={e => setPtsDelta(e.target.value)} placeholder="Masalan: 500 yoki -200"/>
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
                <button type="submit" disabled={saving || !ptsDelta} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? '...' : t('common.save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   TAB 2 — YETKAZIB BERUVCHILAR
══════════════════════════════════════════════════ */
const emptySupplier = {
  name: '', inn: '', phone: '', email: ''
};

function SuppliersTab() {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(emptySupplier);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = (q = search) => api.get(`/suppliers${q ? '?search=' + encodeURIComponent(q) : ''}`).then(r => setList(r.data)).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => load(search), 400); return () => clearTimeout(t); }, [search]);

  const close = () => { setModal(null); setSel(null); setErr(''); };

  const openAdd = () => { setForm(emptySupplier); setSel(null); setErr(''); setModal('form'); };
  const openEdit = (s) => {
    setForm({
      name: s.name, inn: s.inn||'', phone: s.phone||'', email: s.email||''
    });
    setSel(s); setErr(''); setModal('form');
  };

  const handleSave = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try {
      const payload = { ...form };
      if (sel) await api.patch(`/suppliers/${sel.id}`, payload);
      else await api.post('/suppliers', payload);
      close(); load();
    } catch (ex) { setErr(ex.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!confirm(t('confirm.delete'))) return;
    await api.delete(`/suppliers/${id}`);
    load();
  };

  const totalDebt = list.reduce((s, c) => s + Number(c.debt_balance || 0), 0);

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center shrink-0 text-violet-600 font-bold text-lg">T</div>
          <div><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Jami Ta'minotchi</div><div className="text-xl font-bold text-violet-600 mt-0.5">{list.length}</div></div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center shrink-0 text-red-500 font-bold">₴</div>
          <div><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Jami Qarzdorlik</div><div className="text-xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} so'm</div></div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center shrink-0 text-amber-600 font-bold text-lg">★</div>
          <div><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">O'rt. Reyting</div>
            <div className="text-xl font-bold text-amber-600 mt-0.5">
              {list.filter(s => s.rating).length > 0
                ? (list.filter(s => s.rating).reduce((a, s) => a + Number(s.rating), 0) / list.filter(s => s.rating).length).toFixed(1)
                : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          <input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Qidirish..." value={search} onChange={e => setSearch(e.target.value)}/>
        </div>
        <button onClick={openAdd} className="px-4 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-xl transition-colors flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>
          Yangi Ta'minotchi
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">
            {['Ta\'minotchi','INN','Telefon','Qarz','To\'lov muddati','Reyting',''].map(h => <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(s => (
              <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2.5">
                    <Avatar name={s.name}/>
                    <div>
                      <div className="text-sm font-semibold text-slate-800">{s.name}</div>
                      {s.email && <div className="text-xs text-slate-400">{s.email}</div>}
                    </div>
                  </div>
                </td>
                <td className="px-5 py-4 text-sm font-mono text-slate-600">{s.inn || '—'}</td>
                <td className="px-5 py-4 text-sm text-slate-500">{s.phone || '—'}</td>
                <td className="px-5 py-4 text-sm font-semibold">
                  <span className={Number(s.debt_balance) > 0 ? 'text-red-500' : 'text-slate-400'}>{fmt(s.debt_balance)} so'm</span>
                </td>
                <td className="px-5 py-4 text-sm text-slate-500">{s.payment_terms} kun</td>
                <td className="px-5 py-4">
                  <StarRating value={s.rating} readOnly/>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-1">
                    <button onClick={() => openEdit(s)} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg" title="Tahrirlash"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
                    <button onClick={() => handleDelete(s.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg" title="O'chirish"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={7} className="px-5 py-12 text-center text-slate-400 text-sm">{t('common.noData')}</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Supplier Form Modal */}
      {modal === 'form' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{sel ? t('purchase.editSupplier') : t('purchase.newSupplier')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-5">
              {/* Asosiy ma'lumot */}
              <div>
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Asosiy ma'lumot</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-slate-600 mb-1.5">Nomi *</label>
                    <input required className={inputCls} value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="Kompaniya nomi"/>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1.5">INN</label>
                    <input className={inputCls} value={form.inn} onChange={e => setForm({...form, inn: e.target.value})} placeholder="123456789"/>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.phone') || 'Telefon'}</label>
                    <input className={inputCls} value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} placeholder="+998 90 123 45 67"/>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-slate-600 mb-1.5">Email</label>
                    <input type="email" className={inputCls} value={form.email} onChange={e => setForm({...form, email: e.target.value})} placeholder="info@company.uz"/>
                  </div>
                </div>
              </div>

              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
            </form>
            <div className="p-6 border-t border-slate-100 flex gap-3 shrink-0">
              <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
              <button onClick={handleSave} disabled={saving} className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? t('common.saving') : t('common.save')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   MAIN PAGE
══════════════════════════════════════════════════ */
const TABS = [
  { id: 'mijozlar', label: 'Mijozlar', icon: '👥', color: 'indigo' },
  { id: 'suppliers', label: "Yetkazib beruvchilar", icon: '🏭', color: 'violet' },
];

export default function Kontragentlar() {
  const { t } = useLang();
  const [tab, setTab] = useState('mijozlar');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('nav.kontragentlar')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('customer.title')} {t('common.list').toLowerCase()}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-5 py-2 text-sm font-semibold rounded-lg transition-all flex items-center gap-2 ${
              tab === t.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}>
            <span>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'mijozlar' && <MijozlarTab/>}
      {tab === 'suppliers' && <SuppliersTab/>}
    </div>
  );
}
