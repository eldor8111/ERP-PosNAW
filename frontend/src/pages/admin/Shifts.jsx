import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';
import { useReportScope } from '../../hooks/useReportScope';
import { useBranches } from '../../hooks/useBranches';
import toast from 'react-hot-toast';
import ShiftCloseModal from '../../components/ShiftCloseModal';
import { tOr } from '../../utils/shiftBalances';

// C4.3: sana/son formati interfeys tiliga qarab (hardkod 'uz-UZ' emas)
const localeOf = (lang) => (lang === 'ru' ? 'ru-RU' : lang === 'en' ? 'en-GB' : 'uz-UZ');
const fmtNum = (v, loc = 'uz-UZ') => Number(v || 0).toLocaleString(loc);

const fmtDateTime = (dt, loc = 'uz-UZ') => {
  if (!dt) return '—';
  return new Date(dt).toLocaleString(loc, {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

const PAGE_SIZE = 50;
const HOURS_ROLES = ['admin', 'director', 'super_admin', 'manager', 'accountant']; // T4.7: ish soatlari hisoboti

const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

// T4.7: kassirlar ish soati (shifts jadvalidan). Faqat kassirlar uchun hisoblanadi.
function WorkHoursPanel({ branches, canFilterBranch }) {
  const { t, lang } = useLang();
  const fmtDt = (dt) => fmtDateTime(dt, localeOf(lang));
  const today = new Date();
  const [from, setFrom] = useState(isoDay(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [to, setTo] = useState(isoDay(today));
  const [branch, setBranch] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { date_from: from, date_to: to };
      if (branch && canFilterBranch) params.branch_id = branch;
      const { data } = await api.get('/staff-reports/work-hours', { params });
      setRows(data || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || tOr(t, 'staff.hours.loadError', "Ish soatlarini yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [from, to, branch, canFilterBranch, t]);

  useEffect(() => { load(); }, [load]);

  const inputCls = 'text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400';
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-x-auto">
      <div className="px-6 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-slate-700">{tOr(t, 'staff.hours.title', 'Ish soatlari')}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} className={inputCls} />
          <span className="text-slate-400">—</span>
          <input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} className={inputCls} />
          {canFilterBranch && branches.length > 0 && (
            <select value={branch} onChange={e => setBranch(e.target.value)} className={inputCls}>
              <option value="">{t('common.allBranches')}</option>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          )}
        </div>
      </div>
      <table className="min-w-full">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-100">
            {[t('shift.cashier'), tOr(t, 'staff.hours.shiftsCount', 'Smenalar soni'), tOr(t, 'staff.hours.totalHours', 'Jami soat'),
              tOr(t, 'staff.hours.avgHours', "O'rtacha smena (soat)"), tOr(t, 'staff.hours.openShift', 'Ochiq smena'),
              tOr(t, 'staff.hours.longShifts', 'Uzun smenalar')].map(h => (
              <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {rows.map(r => (
            <tr key={r.cashier_id} className="hover:bg-slate-50 transition-colors">
              <td className="px-6 py-4 text-sm font-medium text-slate-800">{r.cashier_name || '—'}</td>
              <td className="px-6 py-4 text-sm text-slate-600">{r.shifts_count}</td>
              <td className="px-6 py-4 text-sm font-semibold text-slate-800">{r.total_hours}</td>
              <td className="px-6 py-4 text-sm text-slate-600">{r.avg_shift_hours}</td>
              <td className="px-6 py-4 text-sm text-slate-600">
                {r.open_shift ? <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-700">{r.open_shift.hours} {tOr(t, 'staff.hours.unit', 'soat')}</span> : '—'}
              </td>
              <td className="px-6 py-4 text-sm">
                {r.long_shifts.length > 0 ? (
                  <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-700"
                    title={r.long_shifts.map(l => `${fmtDt(l.opened_at)} · ${l.hours} ${tOr(t, 'staff.hours.unit', 'soat')}`).join(', ')}>
                    ⚠ {r.long_shifts.length}
                  </span>
                ) : '—'}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-sm">{loading ? '...' : t('shift.noShifts')}</td></tr>
          )}
        </tbody>
      </table>
      <p className="px-6 py-3 text-xs text-slate-400 border-t border-slate-100">
        {tOr(t, 'staff.hours.note', "Ish soati faqat kassirlar smenasi bo'yicha hisoblanadi (omborchi va sotuvchilar uchun emas). 16 soatdan uzun yoki yopilmagan smena «uzun» deb belgilanadi.")}
      </p>
    </div>
  );
}
const BRANCH_ROLES = ['admin', 'director', 'super_admin'];       // filial tanlay oladiganlar
const FILTER_ROLES = ['admin', 'director', 'super_admin', 'manager']; // filial filtrini ko'radiganlar

// Farq ranglari: kamomad (manfiy) qizil, ortiqcha (musbat) ko'k
const diffClass = (d) => (Number(d) < 0 ? 'text-red-600' : Number(d) > 0 ? 'text-blue-600' : 'text-slate-400');

export default function Shifts() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const fmt = (v) => fmtNum(v, localeOf(lang));
  const fmtDt = (dt) => fmtDateTime(dt, localeOf(lang));
  const sumLabel = t('common.sum');
  const [shifts, setShifts] = useState([]);
  const [total, setTotal] = useState(0);
  const [activeShift, setActiveShift] = useState(null);
  const [modal, setModal] = useState(null); // 'open' | 'close'
  const [openingCash, setOpeningCash] = useState('');
  const [openBranch, setOpenBranch] = useState('');
  const [openWallet, setOpenWallet] = useState('');
  const [openWallets, setOpenWallets] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // T3.8: filiallar yagona hook'dan (nofaol filial ham nomi bilan ko'rinsin)
  const { branches } = useBranches({ includeInactive: true });
  const [filterBranch, setFilterBranch] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [zReport, setZReport] = useState(null);   // { loading, data, error }
  const [tab, setTab] = useState('list');            // T4.7: 'list' | 'hours'

  // T2.1: o'z filiali bilan cheklangan foydalanuvchida (menejer) filial filtri ma'nosiz — yashiriladi
  const reportScope = useReportScope();
  const canFilterBranch = FILTER_ROLES.includes(user?.role) && !reportScope.restricted;
  const mustPickBranch = BRANCH_ROLES.includes(user?.role) && !user?.branch_id;
  const activeBranches = branches.filter(b => b.is_active !== false);

  // Faol smena filtrga BOG'LANMAYDI: doim /shifts/current dan olinadi (UI-10)
  const loadActive = useCallback(async () => {
    try {
      const { data } = await api.get('/shifts/current', { _silent: true, _suppressToast: true });
      setActiveShift(data || null);
    } catch (err) {
      toast.error(err.response?.data?.detail || t('common.loadError'));
    }
  }, [t]);

  // X-Total-Count o'qilmasa (header ochilmagan) — sahifa to'liq bo'lsa yana bor deb hisoblaymiz
  const resolveTotal = (res, already) => {
    const header = Number(res.headers?.['x-total-count']);
    if (Number.isFinite(header) && header > 0) return header;
    return already + res.data.length + (res.data.length === PAGE_SIZE ? 1 : 0);
  };

  const buildParams = (skip) => {
    const p = new URLSearchParams({ skip: String(skip), limit: String(PAGE_SIZE) });
    if (filterBranch && canFilterBranch) p.set('branch_id', filterBranch);
    return p.toString();
  };

  const loadList = useCallback(async () => {
    try {
      const res = await api.get(`/shifts?${buildParams(0)}`);
      setShifts(res.data);
      setTotal(resolveTotal(res, 0));
    } catch (err) { console.error(err); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterBranch, canFilterBranch]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const res = await api.get(`/shifts?${buildParams(shifts.length)}`);
      setShifts(prev => [...prev, ...res.data]);
      setTotal(resolveTotal(res, shifts.length));
    } catch (err) { console.error(err); }
    finally { setLoadingMore(false); }
  };

  const load = useCallback(() => Promise.all([loadActive(), loadList()]), [loadActive, loadList]);

  useEffect(() => { loadActive(); }, [loadActive]);
  useEffect(() => { loadList(); }, [loadList]);

  const openOpenModal = () => {
    setOpeningCash(''); setOpenBranch(''); setOpenWallet(''); setError('');
    setModal('open');
    // Ixtiyoriy kassa tanlash: korxonaning faol, shaxsiy bo'lmagan kassalari
    // T2.8: faqat foydalanuvchining default (is_default) kassasi oldindan tanlanadi; bo'lmasa tanlanmagan holat
    // (ro'yxatning birinchi elementi avtomatik tanlanmaydi)
    api.get('/shifts/handover-wallets').then(r => {
      const list = r.data || [];
      setOpenWallets(list);
      const def = list.find(w => w.is_default && (!user?.branch_id || !w.branch_id || w.branch_id === user.branch_id));
      setOpenWallet(def ? String(def.id) : '');
    }).catch(() => setOpenWallets([]));
  };

  const handleOpen = async (e) => {
    e.preventDefault(); setError('');
    if (mustPickBranch && activeBranches.length > 1 && !openBranch) {
      setError(tOr(t, 'shift.selectBranch', 'Filialni tanlang'));
      return;
    }
    setSaving(true);
    try {
      const payload = { opening_cash: Number(openingCash) || 0 };
      if (openBranch) payload.branch_id = Number(openBranch);
      if (openWallet) payload.wallet_id = Number(openWallet);
      await api.post('/shifts/open', payload);
      setModal(null); setOpeningCash(''); load();
      toast.success(t('shift.openSuccess'));
    } catch (err) { setError(err.response?.data?.detail || t('auth.errGeneral')); }
    finally { setSaving(false); }
  };

  const openZReport = async (shiftId) => {
    setZReport({ loading: true, data: null, error: '' });
    try {
      const { data } = await api.get(`/shifts/${shiftId}/z-report`);
      setZReport({ loading: false, data, error: '' });
    } catch (err) {
      setZReport({ loading: false, data: null, error: err.response?.data?.detail || t('auth.errGeneral') });
    }
  };

  const walletsForBranch = openWallets.filter(w => {
    const b = openBranch ? Number(openBranch) : user?.branch_id;
    return !b || !w.branch_id || w.branch_id === b;
  });

  const openShifts = shifts.filter(s => s.status === 'open').length;
  const todayShifts = shifts.filter(s => {
    const d = new Date(s.opened_at);
    const today = new Date();
    return d.toDateString() === today.toDateString();
  }).length;

  const branchName = (s) => {
    if (s.branch_name) return s.branch_name;
    if (!s.branch_id) return '—';
    return branches.find(b => b.id === s.branch_id)?.name || `${t('purchase.filterBranch')} #${s.branch_id}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('shift.title')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('shift.open')} / {t('shift.close')}</p>
        </div>
        {activeShift ? (
          <button
            onClick={() => setModal('close')}
            className="inline-flex items-center gap-2 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9 10h6M9 14h6" />
            </svg>
            {t('shift.close')}
          </button>
        ) : (
          <button
            onClick={openOpenModal}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            {t('shift.open')}
          </button>
        )}
      </div>

      {HOURS_ROLES.includes(user?.role) && (
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
          {[['list', t('shift.title')], ['hours', tOr(t, 'staff.hours.title', 'Ish soatlari')]].map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-4 py-1.5 text-sm font-semibold rounded-lg transition-all ${tab === k ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
              {label}
            </button>
          ))}
        </div>
      )}

      {tab === 'hours' && HOURS_ROLES.includes(user?.role) && (
        <WorkHoursPanel branches={branches} canFilterBranch={canFilterBranch} />
      )}

      {tab === 'list' && (<>
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shift.activeShifts')}</div>
          <div className={`text-2xl font-bold mt-1 ${openShifts > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>{openShifts}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shift.todayShifts')}</div>
          <div className="text-2xl font-bold mt-1 text-blue-600">{todayShifts}</div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shift.totalShifts')}</div>
          <div className="text-2xl font-bold mt-1 text-slate-700">{total || shifts.length}</div>
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
            <div className="text-sm font-bold text-emerald-800">{t('shift.activeShiftExists')}</div>
            <div className="text-xs text-emerald-600 mt-0.5">
              {t('shift.started')}: {fmtDt(activeShift.opened_at)}
              <span className="mx-2">·</span>
              {t('shift.openingCashLabel')}: {fmt(activeShift.opening_cash)} {sumLabel}
              {activeShift.branch_name && (<><span className="mx-2">·</span>{activeShift.branch_name}</>)}
            </div>
          </div>
          <div className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-3 py-1.5 rounded-full">{t('shift.active')}</div>
        </div>
      )}

      {/* Shifts Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-x-auto">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">{t('shift.history')}</h3>
          <div className="flex items-center gap-3">
            {canFilterBranch && branches.length > 0 && (
              <select
                value={filterBranch}
                onChange={e => setFilterBranch(e.target.value)}
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                <option value="">🏢 {t('common.allBranches')}</option>
                {branches.map(b => (
                  <option key={b.id} value={b.id}>{b.name}{b.is_active === false ? ' (✕)' : ''}</option>
                ))}
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
              {[
                t('shift.cashier'), t('purchase.filterBranch'), t('shift.startTime'), t('shift.endTime'),
                t('shift.openingShort'), tOr(t, 'shift.expected', 'Kutilgan'), t('shift.closingShort'),
                tOr(t, 'shift.difference', 'Farq'), t('shift.status'),
              ].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {shifts.map(s => (
              <tr key={s.id} onClick={() => openZReport(s.id)} className="hover:bg-slate-50 transition-colors cursor-pointer">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold shrink-0">
                      {s.cashier_name?.[0]?.toUpperCase() || '?'}
                    </div>
                    <span className="text-sm font-medium text-slate-800">{s.cashier_name || '—'}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{branchName(s)}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{fmtDt(s.opened_at)}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{fmtDt(s.closed_at)}</td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">{fmt(s.opening_cash)} {sumLabel}</td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">
                  {s.expected_cash != null ? `${fmt(s.expected_cash)} ${sumLabel}` : '—'}
                </td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">
                  {s.closing_cash != null ? `${fmt(s.closing_cash)} ${sumLabel}` : '—'}
                </td>
                <td className={`px-6 py-4 text-sm font-medium ${diffClass(s.cash_difference)}`}>
                  {s.cash_difference != null ? `${Number(s.cash_difference) > 0 ? '+' : ''}${fmt(s.cash_difference)}` : '—'}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${
                    s.status === 'open' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {s.status === 'open' ? t('shift.active') : t('shift.closed')}
                  </span>
                </td>
              </tr>
            ))}
            {shifts.length === 0 && (
              <tr><td colSpan={9} className="px-6 py-12 text-center text-slate-400 text-sm">{t('shift.noShifts')}</td></tr>
            )}
          </tbody>
        </table>
        {shifts.length > 0 && shifts.length < total && (
          <div className="p-4 text-center border-t border-slate-100">
            <button
              onClick={loadMore} disabled={loadingMore}
              className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 disabled:opacity-60"
            >
              {loadingMore ? '...' : `${tOr(t, 'common.loadMore', 'Yana yuklash')} (${shifts.length}/${total})`}
            </button>
          </div>
        )}
      </div>

      </>)}

      {/* ── OPEN SHIFT MODAL ─────────────────────────────── */}
      {modal === 'open' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('shift.openShiftTitle')}</h3>
              <button onClick={() => setModal(null)} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleOpen} className="p-6 space-y-4">
              {mustPickBranch && activeBranches.length > 1 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    {tOr(t, 'shift.selectBranch', 'Filialni tanlang')} <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={openBranch} onChange={e => { setOpenBranch(e.target.value); setOpenWallet(''); }}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="">—</option>
                    {activeBranches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('shift.openingCashInputLabel')}</label>
                <input
                  type="number" min="0" autoFocus value={openingCash}
                  onChange={e => setOpeningCash(e.target.value)}
                  placeholder="0"
                  className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              {walletsForBranch.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    {tOr(t, 'shift.selectWallet', 'Kassani tanlang')}
                  </label>
                  <select
                    value={openWallet} onChange={e => setOpenWallet(e.target.value)}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="">—</option>
                    {walletsForBranch.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
              )}
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={() => setModal(null)} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : `✓ ${t('shift.open')}`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── CLOSE SHIFT MODAL ────────────────────────────── */}
      {modal === 'close' && activeShift && (
        <ShiftCloseModal
          shift={activeShift}
          onClosed={() => { setModal(null); load(); }}
          onCancel={() => setModal(null)}
        />
      )}

      {/* ── Z-HISOBOT MODALI ────────────────────────────── */}
      {zReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={() => setZReport(null)}>
          <style>{`@media print { body * { visibility: hidden !important; } #shift-z-report, #shift-z-report * { visibility: visible !important; } #shift-z-report { position: absolute; left: 0; top: 0; width: 100%; max-height: none !important; overflow: visible !important; box-shadow: none !important; } .no-print { display: none !important; } }`}</style>
          <div id="shift-z-report" className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">
                {tOr(t, 'shift.zReport', 'Z-hisobot')}{zReport.data ? ` #${zReport.data.shift.id}` : ''}
              </h3>
              <div className="flex items-center gap-2 no-print">
                {zReport.data && (
                  <button onClick={() => window.print()} className="px-3 py-1.5 text-xs font-semibold border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
                    🖨 Print
                  </button>
                )}
                <button onClick={() => setZReport(null)} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="p-6 space-y-4 text-sm">
              {zReport.loading && <div className="text-slate-400 text-center py-6">...</div>}
              {zReport.error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{zReport.error}</div>}
              {zReport.data && <ZReportBody data={zReport.data} t={t} />}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ZRow({ label, value, className = '' }) {
  return (
    <div className={`flex justify-between ${className}`}>
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold text-slate-800">{value}</span>
    </div>
  );
}

// {ptype: {cur: summa}} -> qatorlar ro'yxati
function PaymentRows({ map }) {
  const { lang } = useLang();
  const fmt = (v) => fmtNum(v, localeOf(lang));
  const rows = Object.entries(map || {}).flatMap(([ptype, cm]) =>
    Object.entries(cm || {}).map(([cur, amt]) => ({ key: `${ptype}-${cur}`, label: `${ptype} (${cur})`, amt })),
  );
  if (rows.length === 0) return <div className="text-slate-400 text-xs">—</div>;
  return rows.map(r => <ZRow key={r.key} label={r.label} value={`${fmt(r.amt)}`} />);
}

function ZReportBody({ data, t }) {
  const { lang } = useLang();
  const fmt = (v) => fmtNum(v, localeOf(lang));
  const fmtDt = (dt) => fmtDateTime(dt, localeOf(lang));
  const sumLabel = t('common.sum');
  const { shift, sales, returns, debt_payments: debts, cash } = data;
  const diff = cash.difference;
  return (
    <>
      <div className="p-4 bg-slate-50 rounded-xl space-y-1.5">
        <ZRow label={t('shift.cashier')} value={shift.cashier_name || '—'} />
        <ZRow label={t('purchase.filterBranch')} value={shift.branch_name || '—'} />
        <ZRow label={t('shift.startTime')} value={fmtDt(shift.opened_at)} />
        <ZRow label={t('shift.endTime')} value={fmtDt(shift.closed_at)} />
      </div>
      <div className="space-y-1.5">
        <div className="text-xs font-bold text-slate-500 uppercase">{t('shift.totalSales')}: {sales.count}</div>
        <ZRow label="Jami" value={`${fmt(sales.total_amount)} ${sumLabel}`} />
        <ZRow label="Chegirma" value={`${fmt(sales.discount_total)} ${sumLabel}`} />
        <PaymentRows map={sales.by_payment} />
      </div>
      <div className="space-y-1.5">
        <div className="text-xs font-bold text-slate-500 uppercase">Qaytarishlar: {returns.count}</div>
        <PaymentRows map={returns.by_payment} />
      </div>
      <div className="space-y-1.5">
        <div className="text-xs font-bold text-slate-500 uppercase">Qarz to'lovlari</div>
        <PaymentRows map={debts.by_payment} />
      </div>
      <div className="p-4 bg-slate-50 rounded-xl space-y-1.5">
        <ZRow label={t('shift.openingCashLabel')} value={`${fmt(cash.opening)} ${sumLabel}`} />
        <ZRow label={t('shift.cashSalesPlus')} value={`${fmt(cash.cash_sales)} ${sumLabel}`} />
        <ZRow label="Naqd qaytarish (-)" value={`${fmt(cash.returns_cash)} ${sumLabel}`} />
        <ZRow label="Qarz to'lovi (+)" value={`${fmt(cash.debt_cash)} ${sumLabel}`} />
        <ZRow label={tOr(t, 'shift.expected', 'Kutilgan')} value={`${fmt(cash.expected)} ${sumLabel}`} className="border-t border-slate-200 pt-1.5" />
        <ZRow label={t('shift.actualCash')} value={cash.counted != null ? `${fmt(cash.counted)} ${sumLabel}` : '—'} />
        {diff != null && (
          <ZRow
            label={diff < 0 ? tOr(t, 'shift.shortage', 'Kamomad') : diff > 0 ? tOr(t, 'shift.surplus', 'Ortiqcha') : tOr(t, 'shift.difference', 'Farq')}
            value={`${fmt(Math.abs(diff))} ${sumLabel}`}
            className={diff < 0 ? 'text-red-600' : diff > 0 ? 'text-blue-600' : ''}
          />
        )}
        {cash.handed_over != null && <ZRow label={t('shift.handOverCash')} value={`${fmt(cash.handed_over)} ${sumLabel}`} />}
      </div>
    </>
  );
}
