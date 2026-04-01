import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useAuth } from '../../context/AuthContext';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const fmtDt = (dt) => {
  if (!dt) return '—';
  return new Date(dt).toLocaleString('uz-UZ', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

export default function Shifts() {
  const { user } = useAuth();
  const [shifts, setShifts] = useState([]);
  const [activeShift, setActiveShift] = useState(null);
  const [modal, setModal] = useState(null); // 'open' | 'close'
  const [openingCash, setOpeningCash] = useState('');
  const [closingCash, setClosingCash] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [branches, setBranches] = useState([]);
  const [filterBranch, setFilterBranch] = useState('');

  const load = async () => {
    try {
      const params = filterBranch ? `?branch_id=${filterBranch}` : '';
      const { data } = await api.get(`/shifts${params}`);
      setShifts(data);
      setActiveShift(data.find(s => s.cashier_id === user?.id && s.status === 'open') || null);
    } catch (err) { console.error(err); }
  };

  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [filterBranch]);

  const handleOpen = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.post('/shifts/open', { opening_cash: Number(openingCash) || 0 });
      setModal(null); setOpeningCash(''); load();
    } catch (err) { setError(err.response?.data?.detail || 'Xatolik yuz berdi'); }
    finally { setSaving(false); }
  };

  const handleClose = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.post(`/shifts/${activeShift.id}/close`, { closing_cash: Number(closingCash) });
      setModal(null); setClosingCash(''); load();
    } catch (err) { setError(err.response?.data?.detail || 'Xatolik yuz berdi'); }
    finally { setSaving(false); }
  };

  const openShifts = shifts.filter(s => s.status === 'open').length;
  const todayShifts = shifts.filter(s => {
    const d = new Date(s.opened_at);
    const today = new Date();
    return d.toDateString() === today.toDateString();
  }).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Smena boshqaruvi</h1>
          <p className="text-slate-500 text-sm mt-0.5">Kassir smenalarini ochish va yopish</p>
        </div>
        {activeShift ? (
          <button
            onClick={() => { setClosingCash(''); setError(''); setModal('close'); }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9 10h6M9 14h6" />
            </svg>
            Smenani yopish
          </button>
        ) : (
          <button
            onClick={() => { setOpeningCash(''); setError(''); setModal('open'); }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            Smena ochish
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Ochiq smenalar</div>
          <div className={`text-2xl font-bold mt-1 ${openShifts > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>{openShifts}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Bugun (smenalar)</div>
          <div className="text-2xl font-bold mt-1 text-indigo-600">{todayShifts}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Jami smenalar</div>
          <div className="text-2xl font-bold mt-1 text-slate-700">{shifts.length}</div>
        </div>
      </div>

      {/* Active shift banner */}
      {activeShift && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-emerald-800">Sizning faol smenangiz mavjud</div>
            <div className="text-xs text-emerald-600 mt-0.5">
              Boshlangan: {fmtDt(activeShift.opened_at)}
              <span className="mx-2">·</span>
              Ochilish kassasi: {fmt(activeShift.opening_cash)} so'm
            </div>
          </div>
          <div className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-3 py-1.5 rounded-full">
            Faol
          </div>
        </div>
      )}

      {/* Shifts Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">Barcha smenalar</h3>
          <div className="flex items-center gap-3">
            {branches.length > 0 && (
              <select
                value={filterBranch}
                onChange={e => setFilterBranch(e.target.value)}
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                <option value="">🏢 Barcha filiallar</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            )}
            <button onClick={load} className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['Kassir', 'Filial', 'Boshlangan', 'Tugatilgan', 'Kirish kassa', 'Chiqish kassa', 'Holat'].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {shifts.map(s => (
              <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0">
                      {s.cashier_name?.[0]?.toUpperCase() || '?'}
                    </div>
                    <span className="text-sm font-medium text-slate-800">{s.cashier_name || '—'}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">
                  {s.branch_id ? (branches.find(b => b.id === s.branch_id)?.name || `Filial #${s.branch_id}`) : '—'}
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">{fmtDt(s.opened_at)}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{fmtDt(s.closed_at)}</td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">{fmt(s.opening_cash)} so'm</td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">
                  {s.closing_cash != null ? `${fmt(s.closing_cash)} so'm` : '—'}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${
                    s.status === 'open' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {s.status === 'open' ? 'Ochiq' : 'Yopiq'}
                  </span>
                </td>
              </tr>
            ))}
            {shifts.length === 0 && (
              <tr><td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-sm">Smenalar yo'q</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── OPEN SHIFT MODAL ───────────────────────────────── */}
      {modal === 'open' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">Smena ochish</h3>
              <button onClick={() => setModal(null)} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleOpen} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Boshlang'ich kassadagi pul (so'm)</label>
                <input
                  type="number" min="0" autoFocus value={openingCash}
                  onChange={e => setOpeningCash(e.target.value)}
                  placeholder="0"
                  className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : 'Ochish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── CLOSE SHIFT MODAL ──────────────────────────────── */}
      {modal === 'close' && activeShift && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">Smenani yopish</h3>
              <button onClick={() => setModal(null)} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleClose} className="p-6 space-y-4">
              <div className="p-4 bg-slate-50 rounded-xl text-sm space-y-1.5">
                <div className="flex justify-between text-slate-600">
                  <span>Boshlangan:</span>
                  <span className="font-medium text-slate-800">{fmtDt(activeShift.opened_at)}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Kirish kassa:</span>
                  <span className="font-medium text-slate-800">{fmt(activeShift.opening_cash)} so'm</span>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  Yopilishdagi kassadagi pul (so'm) <span className="text-red-500">*</span>
                </label>
                <input
                  type="number" min="0" required autoFocus value={closingCash}
                  onChange={e => setClosingCash(e.target.value)}
                  placeholder="Hozirgi kassadagi pul miqdori..."
                  className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : 'Yopish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
