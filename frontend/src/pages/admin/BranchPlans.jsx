import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';
import { useBranches } from '../../hooks/useBranches';
import { tOr } from '../../utils/shiftBalances';

// T4.7: filial va sotuvchi oylik savdo rejasi, bajarilish foizi va reyting.
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const WRITE_ROLES = ['admin', 'director', 'super_admin'];

// Foiz bo'yicha rang: qizil <70%, sariq 70-100%, yashil >=100%
const tone = (p) => (p == null ? 'slate' : p >= 100 ? 'emerald' : p >= 70 ? 'amber' : 'red');
const BAR = { slate: 'bg-slate-300', emerald: 'bg-emerald-500', amber: 'bg-amber-400', red: 'bg-red-500' };
const TEXT = { slate: 'text-slate-400', emerald: 'text-emerald-600', amber: 'text-amber-600', red: 'text-red-600' };

const currentMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

function Percent({ value }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  const c = tone(value);
  return (
    <div className="flex items-center gap-2 min-w-[7rem]">
      <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full ${BAR[c]}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      <span className={`text-xs font-bold ${TEXT[c]}`}>{value}%</span>
    </div>
  );
}

function TargetModal({ branches, month, onClose, onSaved }) {
  const { t } = useLang();
  const [branchId, setBranchId] = useState(branches[0]?.id ? String(branches[0].id) : '');
  const [userId, setUserId] = useState('');
  const [sellers, setSellers] = useState([]);
  const [amount, setAmount] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setUserId('');
    if (!branchId) { setSellers([]); return; }
    api.get('/users/', { params: { branch_id: branchId }, _silent: true, _suppressToast: true })
      .then(r => setSellers(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
      .catch(() => setSellers([]));
  }, [branchId]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!branchId) return setError(tOr(t, 'plan.pickBranch', 'Filialni tanlang'));
    if (amount === '' || Number(amount) < 0) return setError(tOr(t, 'plan.amountInvalid', "Reja summasi noto'g'ri"));
    setSaving(true);
    try {
      await api.put('/branch-plans/targets', {
        branch_id: Number(branchId), month, revenue_target: Number(amount),
        user_id: userId ? Number(userId) : null,
      });
      toast.success(tOr(t, 'plan.saved', 'Reja saqlandi'));
      onSaved();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === 'string' ? d : tOr(t, 'plan.saveError', "Rejani saqlab bo'lmadi"));
    } finally { setSaving(false); }
  };

  const inputCls = 'w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-slate-800">{tOr(t, 'plan.setTitle', 'Reja belgilash')} · {month}</h3>
        {error && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">{error}</div>}
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1.5">{tOr(t, 'plan.branch', 'Filial')}</label>
          <select value={branchId} onChange={e => setBranchId(e.target.value)} className={inputCls}>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1.5">{tOr(t, 'plan.seller', 'Sotuvchi')}</label>
          <select value={userId} onChange={e => setUserId(e.target.value)} className={inputCls}>
            <option value="">{tOr(t, 'plan.wholeBranch', 'Butun filial rejasi')}</option>
            {sellers.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1.5">{tOr(t, 'plan.revenueTarget', "Savdo rejasi (so'm)")}</label>
          <input type="number" min="0" step="1" autoFocus value={amount} onChange={e => setAmount(e.target.value)}
            placeholder="300000000" className={inputCls} />
        </div>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 text-sm font-semibold text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50">
            {t('common.cancel')}
          </button>
          <button type="submit" disabled={saving}
            className="flex-1 py-2.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl disabled:opacity-60">
            {saving ? '...' : t('common.save')}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function BranchPlans() {
  const { user } = useAuth();
  const { t } = useLang();
  const { branches } = useBranches();
  const [month, setMonth] = useState(currentMonth());
  const [rows, setRows] = useState([]);
  const [sellers, setSellers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const canWrite = WRITE_ROLES.includes(user?.role);
  const activeBranches = branches.filter(b => b.is_active !== false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s] = await Promise.all([
        api.get('/branch-plans/progress', { params: { month } }),
        api.get('/branch-plans/sellers', { params: { month } }),
      ]);
      setRows(p.data || []);
      setSellers(s.data || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || tOr(t, 'plan.loadError', "Rejalarni yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [month, t]);

  useEffect(() => { load(); }, [load]);

  const totalTarget = rows.reduce((a, r) => a + (r.target || 0), 0);
  const totalFact = rows.filter(r => r.target != null).reduce((a, r) => a + r.fact, 0);
  const totalPercent = totalTarget > 0 ? Math.round(totalFact / totalTarget * 10000) / 100 : null;

  const th = 'px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider';
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{tOr(t, 'plan.title', 'Reja va KPI')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{tOr(t, 'plan.subtitle', "Filial va sotuvchilarning oylik savdo rejasi, bajarilishi va reyting")}</p>
        </div>
        <div className="flex items-center gap-2">
          <input type="month" value={month} onChange={e => e.target.value && setMonth(e.target.value)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400" />
          {canWrite && (
            <button onClick={() => setModal(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm">
              + {tOr(t, 'plan.setTitle', 'Reja belgilash')}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{tOr(t, 'plan.target', 'Reja')}</div>
          <div className="text-2xl font-bold mt-1 text-slate-700">{fmt(totalTarget)}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{tOr(t, 'plan.fact', 'Fakt')}</div>
          <div className="text-2xl font-bold mt-1 text-blue-600">{fmt(totalFact)}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{tOr(t, 'plan.percent', 'Bajarilish')}</div>
          <div className={`text-2xl font-bold mt-1 ${TEXT[tone(totalPercent)]}`}>{totalPercent == null ? '—' : `${totalPercent}%`}</div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-x-auto">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-700">{tOr(t, 'plan.branchRanking', 'Filiallar reytingi')}</h3>
        </div>
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['#', tOr(t, 'plan.branch', 'Filial'), tOr(t, 'plan.target', 'Reja'), tOr(t, 'plan.fact', 'Fakt'),
                tOr(t, 'plan.percent', 'Bajarilish'), tOr(t, 'plan.remaining', 'Qoldi'),
                tOr(t, 'plan.forecast', 'Prognoz'), tOr(t, 'plan.daysLeft', 'Qolgan kun')].map(h => (
                <th key={h} className={th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {rows.map(r => (
              <tr key={r.branch_id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 text-sm font-bold text-slate-500">{r.rank ?? '—'}</td>
                <td className="px-4 py-3 text-sm font-medium text-slate-800">{r.branch_name}</td>
                <td className="px-4 py-3 text-sm text-slate-700">{r.target != null ? fmt(r.target) : <span className="text-slate-400">{tOr(t, 'plan.noPlan', "Reja yo'q")}</span>}</td>
                <td className="px-4 py-3 text-sm font-semibold text-slate-800">{fmt(r.fact)}</td>
                <td className="px-4 py-3"><Percent value={r.percent} /></td>
                <td className="px-4 py-3 text-sm text-slate-600">{r.remaining != null ? fmt(r.remaining) : '—'}</td>
                <td className="px-4 py-3 text-sm text-slate-600">{r.forecast != null ? fmt(r.forecast) : '—'}</td>
                <td className="px-4 py-3 text-sm text-slate-600">{r.days_left}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="px-6 py-10 text-center text-slate-400 text-sm">{loading ? '...' : tOr(t, 'plan.empty', "Ma'lumot yo'q")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-x-auto">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-700">{tOr(t, 'plan.sellers', 'Sotuvchilar')}</h3>
        </div>
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {[tOr(t, 'plan.seller', 'Sotuvchi'), tOr(t, 'plan.branch', 'Filial'), tOr(t, 'plan.target', 'Reja'),
                tOr(t, 'plan.fact', 'Fakt'), tOr(t, 'plan.percent', 'Bajarilish')].map(h => (
                <th key={h} className={th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {sellers.map(r => (
              <tr key={`${r.branch_id}-${r.user_id}`} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 text-sm font-medium text-slate-800">{r.user_name || '—'}</td>
                <td className="px-4 py-3 text-sm text-slate-500">{r.branch_name}</td>
                <td className="px-4 py-3 text-sm text-slate-700">{r.target != null ? fmt(r.target) : '—'}</td>
                <td className="px-4 py-3 text-sm font-semibold text-slate-800">{fmt(r.fact)}</td>
                <td className="px-4 py-3"><Percent value={r.percent} /></td>
              </tr>
            ))}
            {sellers.length === 0 && (
              <tr><td colSpan={5} className="px-6 py-10 text-center text-slate-400 text-sm">{loading ? '...' : tOr(t, 'plan.empty', "Ma'lumot yo'q")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {modal && (
        <TargetModal branches={activeBranches} month={month} onClose={() => setModal(false)}
          onSaved={() => { setModal(false); load(); }} />
      )}
    </div>
  );
}
