import { useState, useEffect } from 'react';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import { openZReport } from '../api/hippoLocal';
import { useLang } from '../i18n';

export default function ShiftOpenModal({ onOpened, onCancel }) {
  const { user } = useAuth();
  const { t } = useLang();
  const [cash, setCash] = useState('');
  const [saving, setSaving] = useState(false);
  // Filiali biriktirilmagan xodim (masalan, admin) uchun filial tanlash (T1.11)
  const [branches, setBranches] = useState([]);
  const [branchId, setBranchId] = useState('');
  const needBranch = !user?.branch_id && branches.length > 1;

  useEffect(() => {
    if (user?.branch_id) return;
    api.get('/branches').then(r => setBranches((r.data || []).filter(b => b.is_active !== false))).catch(() => {});
  }, [user?.branch_id]);

  const handleOpen = async (e) => {
    e.preventDefault();
    if (needBranch && !branchId) {
      toast.error(t('shift.selectBranch'));
      return;
    }
    setSaving(true);
    try {
      const payload = { opening_cash: Number(cash) || 0 };
      if (branchId) payload.branch_id = Number(branchId);
      await api.post('/shifts/open', payload);
      toast.success(t('shift.openSuccess'));

      // ── Hippo Z-report ochish (BEVOSITA localhost:8081) ────────────────
      try {
        const fiskalEnabled = JSON.parse(localStorage.getItem('fiskalSend') || 'false');
        const factoryId     = JSON.parse(localStorage.getItem('fiskalId')   || 'null');
        if (fiskalEnabled && factoryId) {
          await openZReport(factoryId);
        }
      } catch (hippoErr) {
        console.warn('[Hippo] Z-report ochishda xato:', hippoErr?.message);
      }
      // ─────────────────────────────────────────────────────────────────────

      onOpened();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('api.error.generic'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="font-bold text-slate-800">{t('shift.notOpenTitle')}</h3>
              <p className="text-xs text-slate-500">{t('shift.notOpenHint')}</p>
            </div>
          </div>
        </div>
        <form onSubmit={handleOpen} className="p-6 space-y-4">
          {needBranch && (
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                {t('shift.selectBranch')} <span className="text-red-500">*</span>
              </label>
              <select
                value={branchId} onChange={e => setBranchId(e.target.value)}
                className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="">—</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              {t('shift.openingCashInputLabel')}
            </label>
            <input
              type="number" min="0" autoFocus value={cash}
              onChange={e => setCash(e.target.value)}
              placeholder="0"
              className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div className="flex gap-3">
            {onCancel && (
              <button type="button" onClick={onCancel}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
            )}
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
              {saving ? '...' : `✓ ${t('shift.openShiftTitle')}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
