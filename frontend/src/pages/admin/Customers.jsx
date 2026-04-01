import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';

const emptyForm = { name: '', phone: '', debt_limit: '', loyalty_points: 0, card_number: '', cashback_percent: 0 };

const TIERS = {
  Gold:     { label: 'Gold',     cls: 'bg-amber-100 text-amber-700' },
  Silver:   { label: 'Silver',   cls: 'bg-slate-200 text-slate-700' },
  Bronze:   { label: 'Bronze',   cls: 'bg-orange-100 text-orange-700' },
  Standard: { label: 'Standard', cls: 'bg-slate-100 text-slate-500' },
};

function tierOf(pts) {
  if (pts >= 10000) return 'Gold';
  if (pts >= 5000) return 'Silver';
  if (pts >= 1000) return 'Bronze';
  return 'Standard';
}

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const Avatar = ({ name, size = 'sm' }) => {
  const sizes = { sm: 'w-8 h-8 text-sm', lg: 'w-12 h-12 text-lg' };
  const colors = ['bg-indigo-100 text-indigo-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-rose-100 text-rose-600', 'bg-amber-100 text-amber-600'];
  const color = colors[(name?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`${sizes[size]} ${color} rounded-full flex items-center justify-center font-bold shrink-0`}>
      {name?.charAt(0).toUpperCase()}
    </div>
  );
};

export default function Customers() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [payAmount, setPayAmount] = useState('');
  const [pointsDelta, setPointsDelta] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const load = (q = search) => {
    api.get(`/customers${q ? '?search=' + encodeURIComponent(q) : ''}`)
      .then(r => setCustomers(r.data))
      .catch(() => {});
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const t = setTimeout(() => load(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  const generateCard = () => {
    return '8888 ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000);
  };

  const openAdd = () => { setForm({ ...emptyForm, card_number: generateCard() }); setError(''); setModal('add'); };
  const openEdit = (c) => {
    setForm({ name: c.name, phone: c.phone || '', debt_limit: c.debt_limit || 0, loyalty_points: c.loyalty_points || 0, card_number: c.card_number || '', cashback_percent: c.cashback_percent || 0 });
    setSelected(c); setError(''); setModal('edit');
  };
  const openPay = (c) => { setSelected(c); setPayAmount(''); setError(''); setModal('pay'); };
  const openPoints = (c) => { setSelected(c); setPointsDelta(''); setError(''); setModal('points'); };
  const openHistory = async (c) => {
    setSelected(c); setModal('history'); setError(''); setLoadingHistory(true); setHistory([]);
    try {
      const { data } = await api.get(`/customers/${c.id}/history`);
      setHistory(data);
    } catch (err) {
      setError("Tarixni yuklashda xatolik yuz berdi");
    } finally {
      setLoadingHistory(false);
    }
  };
  const closeModal = () => { setModal(null); setSelected(null); setError(''); setHistory([]); };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload = { 
        name: form.name, 
        phone: form.phone || null, 
        debt_limit: form.debt_limit ? Number(form.debt_limit) : 0, 
        loyalty_points: form.loyalty_points ? Number(form.loyalty_points) : 0,
        card_number: form.card_number || null,
        cashback_percent: form.cashback_percent ? Number(form.cashback_percent) : 0
      };
      if (modal === 'add') await api.post('/customers', payload);
      else await api.put(`/customers/${selected.id}`, payload);
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuzaga keldi');
    } finally { setSaving(false); }
  };

  const handlePay = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post(`/customers/${selected.id}/pay-debt`, { amount: Number(payAmount), reason: "To'lov" });
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuzaga keldi');
    } finally { setSaving(false); }
  };

  const handleAdjustPoints = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post(`/customers/${selected.id}/adjust-points`, {
        delta: Number(pointsDelta),
        reason: 'Manual adjustment',
      });
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  const deleteCustomer = async (id) => {
    if (!confirm("Ushbu mijoz o'chirilsinmi?")) return;
    await api.delete(`/customers/${id}`);
    load();
  };

  const totalDebt = customers.reduce((s, c) => s + Number(c.debt_balance || 0), 0);
  const debtors = customers.filter(c => Number(c.debt_balance) > 0).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Mijozlar CRM</h1>
          <p className="text-slate-500 text-sm mt-0.5">Mijozlar, qarzlar va bonuslar boshqaruvi</p>
        </div>
        <button
          onClick={openAdd}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          Yangi mijoz
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 100 8 4 4 0 000-8zm8 2a2 2 0 110 4 2 2 0 010-4z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Jami Mijozlar</div>
            <div className="text-xl font-bold text-indigo-600 mt-0.5">{customers.length.toLocaleString()}</div>
          </div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Jami Qarzdorlik</div>
            <div className="text-xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} so'm</div>
          </div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Qarzdor Mijozlar</div>
            <div className="text-xl font-bold text-amber-600 mt-0.5">{debtors}</div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          className="w-full pl-11 pr-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white shadow-sm"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Ism yoki telefon raqami bo'yicha qidirish..."
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['Ism', 'Telefon', 'Qarzdorlik', 'Kredit limiti', 'Bonus / Keshbek', 'Harakat'].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {customers.map(c => (
              <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4">
                  <button
                    onClick={() => navigate(`/admin/customers/${c.id}`)}
                    className="flex items-center gap-3 hover:opacity-75 transition-opacity text-left"
                  >
                    <Avatar name={c.name} />
                    <span className="text-sm font-medium text-indigo-700 hover:underline">{c.name}</span>
                  </button>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{c.phone || '—'}</td>
                <td className="px-6 py-4">
                  <span className={`text-sm font-semibold ${Number(c.debt_balance) > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                    {fmt(c.debt_balance)} so'm
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{fmt(c.debt_limit)} so'm</td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-1">
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 text-amber-600 text-xs font-semibold rounded-lg w-fit">
                      <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      {fmt(c.bonus_balance || 0)} so'm
                    </span>
                    {(c.cashback_percent > 0) && (
                       <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit bg-indigo-100 text-indigo-700`}>
                         {Number(c.cashback_percent)}% keshbek
                       </span>
                    )}
                    {(c.loyalty_points > 0) && (
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${TIERS[tierOf(c.loyalty_points || 0)].cls}`}>
                        {TIERS[tierOf(c.loyalty_points || 0)].label} ({c.loyalty_points})
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1">
                    {Number(c.debt_balance) > 0 && (
                      <button
                        onClick={() => openPay(c)}
                        title="Qarz to'lash"
                        className="p-1.5 text-emerald-500 hover:bg-emerald-50 rounded-lg transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                        </svg>
                      </button>
                    )}
                    <button
                      onClick={() => openPoints(c)}
                      title="Bonus ballari"
                      className="p-1.5 text-amber-500 hover:bg-amber-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => openHistory(c)}
                      title="Tarix"
                      className="p-1.5 text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => openEdit(c)}
                      title="Tahrirlash"
                      className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => deleteCustomer(c.id)}
                      title="O'chirish"
                      className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {customers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-16 text-center">
                  <div className="flex flex-col items-center gap-2 text-slate-400">
                    <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <span className="text-sm">{search ? 'Qidiruv natijasi topilmadi' : "Hali mijoz yo'q"}</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {customers.length > 0 && (
          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500 bg-slate-50">
            <span>Jami <strong className="text-slate-700">{customers.length}</strong> ta mijoz</span>
            <span>Umumiy qarz: <strong className="text-red-500">{fmt(totalDebt)} so'm</strong></span>
          </div>
        )}
      </div>

      {/* ── ADD / EDIT MODAL ────────────────────────────────── */}
      {(modal === 'add' || modal === 'edit') && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">
                {modal === 'add' ? 'Yangi mijoz qo\'shish' : 'Mijozni tahrirlash'}
              </h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Ism va familiya <span className="text-red-500">*</span></label>
                  <input
                    required
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Javohir Toshmatov"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Telefon raqam</label>
                  <input
                    value={form.phone}
                    onChange={e => setForm({ ...form, phone: e.target.value })}
                    placeholder="+998 90 123 45 67"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Kredit limiti (so'm)</label>
                  <input
                    type="number" min="0"
                    value={form.debt_limit}
                    onChange={e => setForm({ ...form, debt_limit: e.target.value })}
                    placeholder="1000000"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Boshlang'ich bonus ballari</label>
                  <input
                    type="number" min="0"
                    value={form.loyalty_points}
                    onChange={e => setForm({ ...form, loyalty_points: e.target.value })}
                    placeholder="0"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Karta raqami</label>
                    <button 
                      type="button" 
                      onClick={() => setForm({ ...form, card_number: generateCard() })}
                      className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                    >
                      Generatsiya qilish
                    </button>
                  </div>
                  <input
                    value={form.card_number}
                    onChange={e => setForm({ ...form, card_number: e.target.value })}
                    placeholder="Masalan: 8888 1234 5678 9012"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Keshbek foizi (%)</label>
                  <input
                    type="number" min="0" max="100" step="0.1"
                    value={form.cashback_percent}
                    onChange={e => setForm({ ...form, cashback_percent: e.target.value })}
                    placeholder="Misol: 3.5"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                  Bekor qilish
                </button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? 'Saqlanmoqda...' : 'Saqlash'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── PAY DEBT MODAL ──────────────────────────────────── */}
      {modal === 'pay' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">Qarzni to'lash</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-5">
              <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-xl">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone}</div>
                  <div className="text-sm font-bold text-red-500 mt-0.5">Joriy qarz: {fmt(selected.debt_balance)} so'm</div>
                </div>
              </div>
              <form onSubmit={handlePay} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">To'lov miqdori (so'm) <span className="text-red-500">*</span></label>
                  <input
                    type="number" min="1" max={selected.debt_balance} required autoFocus
                    value={payAmount}
                    onChange={e => setPayAmount(e.target.value)}
                    placeholder={`Max: ${fmt(selected.debt_balance)} so'm`}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
                <div className="flex gap-3">
                  <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                    Bekor
                  </button>
                  <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                    {saving ? '...' : 'Tasdiqlash'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── LOYALTY POINTS MODAL ─────────────────────────────── */}
      {modal === 'points' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">Bonus ballarini sozlash</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-5">
              <div className="flex items-center gap-3 p-4 bg-amber-50 rounded-xl">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone || '—'}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-sm font-bold text-amber-600">Ballar: {selected.loyalty_points || 0}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${TIERS[tierOf(selected.loyalty_points || 0)].cls}`}>
                      {TIERS[tierOf(selected.loyalty_points || 0)].label}
                    </span>
                  </div>
                </div>
              </div>
              <form onSubmit={handleAdjustPoints} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    O'zgarish miqdori <span className="text-slate-400 font-normal">(musbat = qo'shish, manfiy = ayirish)</span>
                  </label>
                  <input
                    type="number" required autoFocus
                    value={pointsDelta}
                    onChange={e => setPointsDelta(e.target.value)}
                    placeholder="Masalan: 500 yoki -200"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                  {pointsDelta && (
                    <p className="text-xs text-slate-500 mt-1.5">
                      Natija: <strong className="text-slate-700">{Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta))} ball</strong>
                      {' → '}
                      <span className={`font-semibold ${TIERS[tierOf(Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta)))].cls.replace('bg-', 'text-').split(' ')[0]}`}>
                        {TIERS[tierOf(Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta)))].label}
                      </span>
                    </p>
                  )}
                </div>
                {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
                <div className="flex gap-3">
                  <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                    Bekor
                  </button>
                  <button type="submit" disabled={saving || !pointsDelta} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                    {saving ? '...' : 'Saqlash'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORY MODAL ────────────────────────────────────── */}
      {modal === 'history' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">Harid va to'lovlar tarixi</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">
              <div className="flex items-center gap-3 p-4 bg-white border border-slate-100 rounded-xl mb-6 shadow-sm">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone || 'Telefon raqam yo\'q'}</div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Joriy qarz</div>
                  <div className={`text-lg font-bold ${Number(selected.debt_balance) > 0 ? 'text-red-500' : 'text-slate-700'}`}>
                    {fmt(selected.debt_balance)} so'm
                  </div>
                </div>
              </div>

              {loadingHistory ? (
                <div className="py-12 flex justify-center">
                  <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
                </div>
              ) : error ? (
                <div className="p-4 bg-red-50 text-red-600 rounded-xl text-center text-sm">{error}</div>
              ) : history.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <svg className="w-12 h-12 mx-auto mb-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Tarix ma'lumotlari topilmadi
                </div>
              ) : (
                <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-slate-200">
                  {history.map((item, idx) => {
                    const isSale = item.type === 'sale';
                    const dateObj = new Date(item.date);
                    return (
                      <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                        <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-white bg-slate-50 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 shadow-sm">
                          {isSale ? (
                            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                            </svg>
                          )}
                        </div>
                        <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-slate-100 bg-white shadow-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded-md ${isSale ? 'bg-indigo-50 text-indigo-600' : 'bg-emerald-50 text-emerald-600'}`}>
                              {isSale ? 'Xarid' : "To'lov"}
                            </span>
                            <span className="text-xs text-slate-400 font-medium">
                              {dateObj.toLocaleDateString('uz-UZ')} {dateObj.toLocaleTimeString('uz-UZ', {hour: '2-digit', minute:'2-digit'})}
                            </span>
                          </div>
                          <div className="mt-2 text-slate-700">
                            {isSale ? (
                              <div className="space-y-1 text-sm">
                                <div className="flex justify-between">
                                  <span className="text-slate-500">Jami qiy.:</span>
                                  <span className="font-semibold">{fmt(item.amount)} so'm</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-slate-500">To'landi:</span>
                                  <span className="font-medium text-emerald-600">{fmt(item.paid)} so'm</span>
                                </div>
                                {item.debt > 0 && (
                                  <div className="flex justify-between border-t border-slate-100 pt-1 mt-1">
                                    <span className="text-slate-500">Qarzga:</span>
                                    <span className="font-bold text-red-500">{fmt(item.debt)} so'm</span>
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div className="flex justify-between items-center text-sm">
                                <span className="text-slate-500">To'langan miqdor:</span>
                                <span className="font-bold text-emerald-600 text-base">+{fmt(item.amount)} so'm</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-slate-100 bg-white rounded-b-2xl shrink-0">
              <button onClick={closeModal} className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl transition-colors">
                Yopish
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
