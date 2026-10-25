import { useState, useEffect, useRef, useMemo } from 'react';
import { useLang } from '../../context/LangContext';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import {
  Store,
  Zap,
  Sparkles,
  Crown,
  Package,
  Warehouse,
  Users,
  Building2,
  Bike,
  Truck,
  BarChart3,
  Factory,
  Share2,
  Pencil,
  Trash2,
  Check,
  X,
  AlertTriangle,
  TrendingUp,
  Activity,
  CreditCard,
  Wallet,
  Clock,
  Calendar,
  Pill,
  RefreshCw,
  Download,
  MapPin,
  FlaskConical,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
const fmtMoney = (v) => Number(v || 0).toLocaleString('uz-UZ');

const ROLE_LABELS = {
  super_admin: 'Super Admin', admin: 'Admin', director: 'Direktor',
  manager: 'Menejer', accountant: 'Buxgalter', warehouse: 'Omborchi', cashier: 'Kassir',
};
const ROLE_COLORS = {
  super_admin: 'bg-blue-100 text-blue-700', admin: 'bg-red-100 text-red-700',
  director: 'bg-violet-100 text-violet-700', manager: 'bg-blue-100 text-blue-700',
  accountant: 'bg-green-100 text-green-700', warehouse: 'bg-amber-100 text-amber-700',
  cashier: 'bg-blue-100 text-blue-700',
};

const Ic = ({ d, cls = "w-4 h-4" }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
  </svg>
);

/* ─── Korxonani butunlay o'chirish (oldindan ko'rish + nom/kod bilan tasdiqlash) ─── */
const PURGE_LABELS = ['users', 'branches', 'warehouses', 'products', 'customers', 'sales', 'purchase_orders', 'expenses'];

function DeleteCompanyModal({ company, onClose, onDeleted }) {
  const { t } = useLang();
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [step, setStep] = useState('');
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const code = company.code || company.org_code || '';
  const target = (code || company.name || '').trim();
  const matches = confirm.trim().toLowerCase() === target.toLowerCase();

  useEffect(() => {
    api.get(`/super-admin/companies/${company.id}/delete-preview`)
      .then(r => setPreview(r.data))
      .catch(e => setError(e.response?.data?.detail || t('superAdmin.errorOccurred')));
  }, [company.id]);

  const doDelete = async () => {
    if (!matches || deleting) return;
    setDeleting(true); setError(''); setStep('');
    try {
      // O'chirish serverda fonda ishlaydi (minglab yozuv bo'lishi mumkin) — holatini kuzatamiz
      const r = await api.delete(`/super-admin/companies/${company.id}`, { params: { confirm: confirm.trim() } });
      const jobId = r.data?.job_id;
      for (;;) {
        await new Promise(res => setTimeout(res, 2000));
        if (!alive.current) return;
        let job;
        try { job = (await api.get(`/super-admin/purge-jobs/${jobId}`)).data; }
        catch { continue; }   // vaqtinchalik tarmoq xatosi — qayta so'raymiz
        if (job.status === 'done') {
          toast.success(`${company.name}: ${t('superAdmin.companyDeleted')}`);
          onDeleted();
          return;
        }
        if (job.status === 'error') throw new Error(job.error);
        setStep(job.step || '');
      }
    } catch (e) {
      if (!alive.current) return;
      setError(e.response?.data?.detail || e.message || t('superAdmin.deleteError'));
      setDeleting(false); setStep('');
    }
  };

  const counts = preview?.counts || {};
  const others = (preview?.total || 0) - PURGE_LABELS.reduce((s, k) => s + (counts[k] || 0), 0) - (counts.companies || 0);

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => !deleting && onClose()}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="p-6">
          <div className="w-12 h-12 rounded-2xl bg-red-100 flex items-center justify-center mb-4">
            <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-6 h-6 text-red-600" />
          </div>
          <h4 className="font-black text-slate-800 text-lg mb-1">{t('superAdmin.deleteCompanyTitle')}</h4>
          <p className="text-sm text-slate-500 mb-4">
            <span className="font-semibold text-slate-800">{company.name}</span>
            {code && <span className="font-mono font-bold text-blue-600 ml-1.5">({code})</span>}
            {' '}{t('superAdmin.deleteCompanyWarning')}
          </p>

          <div className="bg-red-50 border border-red-100 rounded-xl p-3 mb-4 text-sm">
            {!preview && !error && <div className="text-slate-400 text-xs">{t('common.loading')}</div>}
            {preview && (
              <>
                <div className="font-semibold text-red-700 mb-2">{t('superAdmin.deleteCompanyWillRemove')}</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-700">
                  {PURGE_LABELS.filter(k => counts[k]).map(k => (
                    <div key={k} className="flex justify-between"><span>{t(`superAdmin.purge.${k}`)}</span><b>{counts[k].toLocaleString('uz-UZ')}</b></div>
                  ))}
                  {others > 0 && (
                    <div className="flex justify-between col-span-2 text-slate-500"><span>{t('superAdmin.purge.other')}</span><b>{others.toLocaleString('uz-UZ')}</b></div>
                  )}
                </div>
                {/* Boshqa korxonalarga tegishli (umumiy) yozuvlar o'chirilmaydi — ularning filialiga ko'chiriladi */}
                {Object.keys(preview.moved || {}).length > 0 && (
                  <div className="mt-2 pt-2 border-t border-red-100 text-xs text-amber-700 space-y-0.5">
                    {Object.entries(preview.moved).map(([k, n]) => (
                      <div key={k}>
                        <span className="font-semibold">{t(`superAdmin.purge.${k}`) === `superAdmin.purge.${k}` ? k : t(`superAdmin.purge.${k}`)}</span>
                        {': '}{t('superAdmin.purge.moved', { n: Number(n).toLocaleString('uz-UZ') })}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <label className="text-xs text-slate-600 font-medium">
            {t('superAdmin.deleteCompanyTypeToConfirm', { value: target })}
          </label>
          <input
            value={confirm}
            onChange={e => { setConfirm(e.target.value); setError(''); }}
            onKeyDown={e => e.key === 'Enter' && doDelete()}
            placeholder={target}
            autoFocus
            disabled={deleting}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-red-300"
          />
          {deleting && (
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-600 bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
              <div className="w-3.5 h-3.5 border-2 border-red-500 border-t-transparent rounded-full animate-spin shrink-0" />
              <span>{step || t('superAdmin.deleting')}</span>
            </div>
          )}
          {error && <div className="mt-3 text-xs text-red-600 bg-red-50 px-3 py-2 rounded-xl border border-red-100">{error}</div>}
        </div>
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex gap-2 justify-end">
          <button onClick={onClose} disabled={deleting} className="px-5 py-2.5 bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-xl disabled:opacity-50">{t('common.cancel')}</button>
          <button onClick={doDelete} disabled={!matches || !preview || deleting}
            className="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-bold rounded-xl shadow-sm disabled:opacity-40 transition-all">
            {deleting ? t('superAdmin.deleting') : t('superAdmin.deleteCompanyButton')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Company Detail Drawer (o'ng tomondan siljib chiqadigan katta panel) ─── */
function CompanyDetailPanel({ companyId, companyName, onClose, initialTab = 'branches' }) {
  const { t } = useLang();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [tab, setTab] = useState(initialTab);
  const [visible, setVisible] = useState(false);

  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  // T3.2: filial/ombor formalari
  const [branchForm, setBranchForm] = useState(null);   // {id?, name, address, phone}
  const [whForm, setWhForm] = useState(null);           // {id?, name, type, branch_id, is_active}
  const [whRefresh, setWhRefresh] = useState(0);

  useEffect(() => {
    setTimeout(() => setVisible(true), 10);
    setLoading(true);
    setLoadError(false);
    api.get(`/super-admin/companies/${companyId}`)
      .then(r => setDetail(r.data))
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [companyId]);

  // Yozuvdan keyin tafsilotni jimgina yangilash (spinner va tab holati o'zgarmaydi)
  const reloadDetail = async () => {
    try {
      const r = await api.get(`/super-admin/companies/${companyId}`);
      setDetail(r.data);
      setWhRefresh(n => n + 1);
    } catch { /* eski ma'lumot qoladi */ }
  };

  const toggleBranchActive = async (b) => {
    if (b.is_active && !window.confirm(tf('superAdmin.confirmDeactivateBranch', "Filialni nofaol qilasizmi?"))) return;
    try {
      await api.patch(`/super-admin/branches/${b.id}`, { is_active: !b.is_active });
      toast.success(tf('superAdmin.saved', 'Saqlandi'));
      await reloadDetail();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('superAdmin.errorOccurred'));
    }
  };

  const toggleMarketplaceAgents = async () => {
    if (!detail) return;
    try {
      setLoading(true);
      await api.put(`/super-admin/companies/${companyId}`, { marketplace_agents_enabled: !detail.marketplace_agents_enabled });
      const r = await api.get(`/super-admin/companies/${companyId}`);
      setDetail(r.data);
      toast.success(detail.marketplace_agents_enabled ? "Marketplace Agent o'chirildi" : "Marketplace Agent yoqildi");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setVisible(false);
    setTimeout(onClose, 280);
  };


  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className={`flex-1 bg-black/30 backdrop-blur-sm transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleClose}
      />
      {/* Drawer */}
      <div className={`w-full max-w-2xl bg-white h-full flex flex-col shadow-2xl transition-transform duration-300 ease-out ${visible ? 'translate-x-0' : 'translate-x-full'}`}>

        {/* ── Header ── */}
        <div className="shrink-0 bg-gradient-to-r from-blue-600 to-violet-600 px-6 py-5 text-white">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center font-black text-xl">
                {companyName?.[0]?.toUpperCase()}
              </div>
              <div>
                <h2 className="text-lg font-black leading-tight">{companyName}</h2>
                {detail && (
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    {detail.region && (
                      <span className="flex items-center gap-1 text-xs bg-white/20 px-2 py-0.5 rounded-full">
                        <Ic d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" cls="w-3 h-3" />
                        {detail.region}
                        {detail.district && ` · ${detail.district}`}
                      </span>
                    )}
                    {detail.phone && (
                      <span className="text-xs text-white/70">{detail.phone}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
            <button onClick={handleClose} className="w-8 h-8 flex items-center justify-center rounded-xl bg-white/20 hover:bg-white/30 text-white shrink-0">
              <Ic d="M6 18L18 6M6 6l12 12" />
            </button>
          </div>

          {/* Stats row */}
          {detail && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
              {[
                { label: t('superAdmin.branches'), value: detail.stats?.branches_total ?? detail.stats?.branches ?? 0,
                  sub: `${detail.stats?.branches_active ?? 0}/${detail.stats?.branches_total ?? detail.stats?.branches ?? 0} ${tf('superAdmin.activeOfTotal', 'faol / jami')}` },
                { label: t('superAdmin.employees'), value: detail.stats?.users ?? 0,
                  sub: `${tf('superAdmin.noBranchOf', 'shundan filialsiz')}: ${detail.stats?.users_no_branch ?? 0}` },
                { label: t('superAdmin.warehouses'), value: detail.stats?.warehouses ?? 0,
                  sub: detail.stats?.warehouses_no_branch ? `${tf('superAdmin.noBranchOf', 'shundan filialsiz')}: ${detail.stats.warehouses_no_branch}` : null },
                { label: t('common.balance'), value: `${Number(detail.balance || 0).toLocaleString('uz-UZ')} s` },
              ].map(s => (
                <div key={s.label} className="bg-white/15 rounded-xl px-3 py-2 text-center">
                  <div className="text-lg font-black">{s.value}</div>
                  <div className="text-xs text-white/70 mt-0.5">{s.label}</div>
                  {s.sub && <div className="text-[10px] text-white/60 mt-0.5">{s.sub}</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Tabs ── */}
        <div className="shrink-0 flex gap-1 px-5 pt-4 pb-2 border-b border-slate-100">
          {[
            { id: 'branches', label: `${t('superAdmin.branches')} (${detail?.branches?.length || 0})`, icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16' },
            { id: 'users', label: `${t('superAdmin.employees')} (${detail?.stats?.users ?? 0})`, icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0' },
            { id: 'warehouses', label: `${t('superAdmin.warehouses')} (${detail?.stats?.warehouses ?? 0})`, icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
            { id: 'tariff', label: t('superAdmin.tariffReport'), icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2-2h-2a2 2 0 01-2-2z' },
            { id: 'packages', label: 'Paketlar', icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
            { id: 'settings', label: t('common.settings'), icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
          ].map(tb => (
            <button key={tb.id} onClick={() => setTab(tb.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${tab === tb.id ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'}`}>
              <Ic d={tb.icon} cls="w-3.5 h-3.5" />
              {tb.label}
            </button>
          ))}
        </div>

        {/* ── Body ── */}
        {loading ? (
          <div className="flex-1 flex justify-center items-center">
            <div className="w-9 h-9 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400 px-6">
            <div className="w-14 h-14 rounded-2xl bg-red-100 text-red-500 flex items-center justify-center">
              <Ic d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-7 h-7" />
            </div>
            <p className="text-sm font-semibold text-slate-600">{t('superAdmin.dataLoadError')}</p>
            <button
              onClick={() => { setLoadError(false); setLoading(true); api.get(`/super-admin/companies/${companyId}`).then(r => setDetail(r.data)).catch(() => setLoadError(true)).finally(() => setLoading(false)); }}
              className="text-xs px-4 py-2 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded-xl font-semibold transition-all"
            >
              {t('superAdmin.retry')}
            </button>
          </div>
        ) : !detail ? (
          <div className="flex-1 flex items-center justify-center text-slate-400">{t('common.noData')}</div>
        ) : (
          <div className="flex-1 overflow-y-auto px-5 py-4">

            {/* ── FILIALLAR ── */}
            {tab === 'branches' && (
              <div className="space-y-2">
                <div className="flex justify-end">
                  <button onClick={() => setBranchForm({ name: '', address: '', phone: '' })}
                    className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm">
                    + {tf('superAdmin.addBranch', 'Filial')}
                  </button>
                </div>
                {detail.branches?.length === 0 && (
                  <div className="text-center text-slate-400 py-16">{t('superAdmin.noBranches')}</div>
                )}
                {detail.branches?.map((b) => (
                  <div key={b.id} className="p-4 bg-slate-50 hover:bg-blue-50/50 rounded-2xl border border-slate-100 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm shrink-0">
                        {b.name?.[0]?.toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-800 text-sm">{b.name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 ${b.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                            {b.is_active ? t('common.active') : t('common.inactive')}
                          </span>
                        </div>
                        {b.address && (
                          <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-400">
                            <Ic d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" cls="w-3 h-3 shrink-0" />
                            {b.address}
                          </div>
                        )}
                        {b.phone && (
                          <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-400">
                            <Ic d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" cls="w-3 h-3 shrink-0" />
                            {b.phone}
                          </div>
                        )}
                      </div>
                      <div className="text-right shrink-0 flex gap-4">
                        <div>
                          <div className="text-sm font-bold text-blue-700">{b.users_count}</div>
                          <div className="text-xs text-slate-400">{t('superAdmin.employee')}</div>
                        </div>
                        <div>
                          <div className="text-sm font-bold text-violet-700">{b.warehouses_count ?? 0}</div>
                          <div className="text-xs text-slate-400">{t('superAdmin.warehouses')}</div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 mt-3 justify-end">
                      <button onClick={() => setBranchForm({ id: b.id, name: b.name || '', address: b.address || '', phone: b.phone || '' })}
                        className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-600">
                        {t('common.edit')}
                      </button>
                      <button onClick={() => toggleBranchActive(b)}
                        className={`px-3 py-1.5 text-xs font-semibold rounded-lg border ${b.is_active ? 'bg-white border-red-200 text-red-600 hover:bg-red-50' : 'bg-white border-emerald-200 text-emerald-700 hover:bg-emerald-50'}`}>
                        {b.is_active ? tf('superAdmin.deactivate', 'Nofaol qilish') : tf('superAdmin.activate', 'Faollashtirish')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── OMBORLAR ── */}
            {tab === 'warehouses' && (
              <DrawerWarehouses
                branches={detail.branches || []}
                unassigned={detail.unassigned_warehouses || []}
                refreshKey={whRefresh}
                onAdd={(branchId) => setWhForm({ name: '', type: 'main', branch_id: branchId ?? '', is_active: true })}
                onEdit={(w, branchId) => setWhForm({ id: w.id, name: w.name, type: w.type || 'main', branch_id: branchId ?? '', is_active: true })}
              />
            )}

            {/* ── XODIMLAR ── */}
            {tab === 'users' && (
              <DrawerCompanyUsers companyId={companyId} branches={detail.branches || []} noBranchCount={detail.stats?.users_no_branch ?? 0} />
            )}

            {/* ── TARIF HISOBOTI ── */}
            {tab === 'tariff' && (
              <DrawerTariffReport detail={detail} />
            )}

            {/* ── PAKETLAR ── */}
            {tab === 'packages' && (
              <DrawerPackagesPanel companyId={companyId} />
            )}

            {/* ── SOZLAMALAR ── */}
            {tab === 'settings' && (
              <div className="space-y-4">
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 flex items-center justify-between">
                  <div>
                    <h4 className="font-bold text-slate-800 text-sm">Marketplace Agentlari</h4>
                    <p className="text-xs text-slate-500 mt-1">Ushbu korxona uchun marketplace agentlari modulini yoqish</p>
                  </div>
                  <button
                    onClick={toggleMarketplaceAgents}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${detail.marketplace_agents_enabled ? 'bg-blue-600' : 'bg-slate-300'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${detail.marketplace_agents_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {branchForm && (
        <BranchFormModal
          form={branchForm}
          companyId={companyId}
          onClose={() => setBranchForm(null)}
          onSaved={async () => { setBranchForm(null); await reloadDetail(); }}
        />
      )}
      {whForm && (
        <WarehouseFormModal
          form={whForm}
          companyId={companyId}
          branches={detail?.branches || []}
          onClose={() => setWhForm(null)}
          onSaved={async () => { setWhForm(null); await reloadDetail(); }}
        />
      )}
    </div>
  );
}

/* T3.2: korxonaning barcha xodimlari — filtr: Barchasi / Filialsiz / har bir filial */
function DrawerCompanyUsers({ companyId, branches, noBranchCount }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [filter, setFilter] = useState('');   // '' = barchasi, 'none' = filialsiz, aks holda filial id
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setLoading(true);
    setFetchError(false);
    const params = filter === 'none' ? { no_branch: true } : filter ? { branch_id: filter } : {};
    api.get(`/super-admin/companies/${companyId}/users`, { params })
      .then(r => setUsers(r.data || []))
      .catch(() => setFetchError(true))
      .finally(() => setLoading(false));
  }, [companyId, filter, attempt]);

  return (
    <div className="space-y-3">
      <select value={filter} onChange={e => setFilter(e.target.value)}
        className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-slate-50">
        <option value="">{tf('superAdmin.allUsers', 'Barchasi')}</option>
        <option value="none">{tf('superAdmin.noBranchUsers', 'Filialsiz')} ({noBranchCount})</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>

      {loading && <div className="flex justify-center py-10"><div className="w-7 h-7 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" /></div>}
      {!loading && fetchError && (
        <div className="flex flex-col items-center justify-center py-10 gap-2">
          <div className="w-10 h-10 rounded-xl bg-red-100 text-red-500 flex items-center justify-center">
            <Ic d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-5 h-5" />
          </div>
          <p className="text-sm text-red-500 font-semibold">{t('superAdmin.employeesLoadError')}</p>
          <button onClick={() => setAttempt(n => n + 1)}
            className="text-xs px-3 py-1.5 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded-lg font-semibold">
            {t('superAdmin.retry')}
          </button>
        </div>
      )}
      {!loading && !fetchError && users.length === 0 && (
        <p className="text-slate-400 text-sm text-center py-10">{t('superAdmin.noEmployeesInBranch')}</p>
      )}
      {!loading && !fetchError && users.map(u => (
        <div key={u.id} className="flex items-center gap-3 p-4 bg-slate-50 hover:bg-blue-50/50 rounded-2xl border border-slate-100 transition-colors">
          <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold shrink-0">
            {u.name?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-bold text-slate-800 text-sm">{u.name}</div>
            <div className="text-xs text-slate-400 mt-0.5">
              {u.phone} · {u.branch_name || tf('superAdmin.noBranchUsers', 'Filialsiz')}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${ROLE_COLORS[u.role] || 'bg-slate-100 text-slate-500'}`}>
              {ROLE_LABELS[u.role] || u.role}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
              {u.status === 'active' ? t('common.active') : t('common.inactive')}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* T3.2: omborlar ro'yxati — har bir filial bo'yicha (GET /super-admin/branches/{id}) + filialsizlar */
function DrawerWarehouses({ branches, unassigned, refreshKey, onAdd, onEdit }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [byBranch, setByBranch] = useState({});   // {branchId: [warehouse]}
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all(branches.map(b =>
      api.get(`/super-admin/branches/${b.id}`)
        .then(r => [b.id, r.data.warehouses || []])
        .catch(() => [b.id, []])
    )).then(rows => { if (!cancelled) setByBranch(Object.fromEntries(rows)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [branches.map(b => b.id).join(','), refreshKey]);

  const whRow = (w, branchId) => (
    <div key={w.id} className="flex items-center gap-3 px-3 py-2 bg-white rounded-xl border border-slate-100">
      <div className="flex-1 min-w-0">
        <span className="text-sm font-semibold text-slate-700">{w.name}</span>
        <span className="ml-2 text-xs text-slate-400">{w.type}</span>
        {w.is_default && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 font-semibold">default</span>}
      </div>
      <button onClick={() => onEdit(w, branchId)}
        className="px-3 py-1 text-xs font-semibold rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-600">
        {t('common.edit')}
      </button>
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => onAdd(null)}
          className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm">
          + {tf('superAdmin.addWarehouse', 'Ombor')}
        </button>
      </div>
      {loading && <div className="flex justify-center py-6"><div className="w-6 h-6 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" /></div>}
      {branches.map(b => (
        <div key={b.id} className="p-3 bg-slate-50 rounded-2xl border border-slate-100 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-800 text-sm">{b.name}</span>
            <button onClick={() => onAdd(b.id)} className="text-xs font-semibold text-blue-600 hover:text-blue-800">
              + {tf('superAdmin.addWarehouse', 'Ombor')}
            </button>
          </div>
          {(byBranch[b.id] || []).map(w => whRow(w, b.id))}
          {!loading && (byBranch[b.id] || []).length === 0 && (
            <p className="text-xs text-slate-400">{tf('superAdmin.noWarehouses', "Omborlar yo'q")}</p>
          )}
        </div>
      ))}
      {unassigned.length > 0 && (
        <div className="p-3 bg-amber-50 rounded-2xl border border-amber-100 space-y-2">
          <div className="font-bold text-amber-800 text-sm">{tf('superAdmin.warehousesNoBranch', 'Filialsiz omborlar')} ({unassigned.length})</div>
          {unassigned.map(w => whRow(w, null))}
        </div>
      )}
    </div>
  );
}

const WH_TYPES = ['main', 'shop', 'transit', 'returns', 'raw_material', 'wip'];
const FIELD_CLS = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-slate-50';

function FormShell({ title, onClose, onSubmit, saving, children }) {
  const { t } = useLang();
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <form onClick={e => e.stopPropagation()} onSubmit={onSubmit}
        className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 font-black text-slate-800">{title}</div>
        <div className="px-5 py-4 space-y-3">{children}</div>
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex gap-2 justify-end">
          <button type="button" onClick={onClose} disabled={saving}
            className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-xl">
            {t('common.cancel')}
          </button>
          <button type="submit" disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl disabled:opacity-50">
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </form>
    </div>
  );
}

function BranchFormModal({ form, companyId, onClose, onSaved }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [f, setF] = useState(form);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { toast.error(tf('superAdmin.nameRequired', 'Nomi kiritilishi shart')); return; }
    setSaving(true);
    const body = { name: f.name.trim(), address: f.address.trim() || null, phone: f.phone.trim() || null };
    try {
      if (f.id) await api.patch(`/super-admin/branches/${f.id}`, body);
      else await api.post(`/super-admin/companies/${companyId}/branches`, body);
      toast.success(tf('superAdmin.saved', 'Saqlandi'));
      await onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('superAdmin.errorOccurred'));
      setSaving(false);
    }
  };
  return (
    <FormShell title={f.id ? tf('superAdmin.editBranch', 'Filialni tahrirlash') : tf('superAdmin.addBranch', 'Filial')}
      onClose={onClose} onSubmit={submit} saving={saving}>
      <label className="block text-xs font-semibold text-slate-500">{tf('superAdmin.branchName', 'Filial nomi')}
        <input className={`${FIELD_CLS} mt-1`} value={f.name} maxLength={100} autoFocus onChange={e => setF({ ...f, name: e.target.value })} />
      </label>
      <label className="block text-xs font-semibold text-slate-500">{t('common.address')}
        <input className={`${FIELD_CLS} mt-1`} value={f.address} maxLength={200} onChange={e => setF({ ...f, address: e.target.value })} />
      </label>
      <label className="block text-xs font-semibold text-slate-500">{t('common.phone')}
        <input className={`${FIELD_CLS} mt-1`} value={f.phone} maxLength={20} onChange={e => setF({ ...f, phone: e.target.value })} />
      </label>
    </FormShell>
  );
}

function WarehouseFormModal({ form, companyId, branches, onClose, onSaved }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [f, setF] = useState(form);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { toast.error(tf('superAdmin.nameRequired', 'Nomi kiritilishi shart')); return; }
    setSaving(true);
    const body = { name: f.name.trim(), type: f.type, branch_id: f.branch_id === '' ? null : Number(f.branch_id) };
    try {
      if (f.id) await api.patch(`/super-admin/warehouses/${f.id}`, body);
      else await api.post(`/super-admin/companies/${companyId}/warehouses`, body);
      toast.success(tf('superAdmin.saved', 'Saqlandi'));
      await onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('superAdmin.errorOccurred'));
      setSaving(false);
    }
  };
  return (
    <FormShell title={f.id ? tf('superAdmin.editWarehouse', 'Omborni tahrirlash') : tf('superAdmin.addWarehouse', 'Ombor')}
      onClose={onClose} onSubmit={submit} saving={saving}>
      <label className="block text-xs font-semibold text-slate-500">{tf('superAdmin.warehouseName', 'Ombor nomi')}
        <input className={`${FIELD_CLS} mt-1`} value={f.name} maxLength={100} autoFocus onChange={e => setF({ ...f, name: e.target.value })} />
      </label>
      <label className="block text-xs font-semibold text-slate-500">{t('common.type')}
        <select className={`${FIELD_CLS} mt-1`} value={f.type} onChange={e => setF({ ...f, type: e.target.value })}>
          {WH_TYPES.map(x => <option key={x} value={x}>{x}</option>)}
        </select>
      </label>
      <label className="block text-xs font-semibold text-slate-500">{t('superAdmin.branches')}
        <select className={`${FIELD_CLS} mt-1`} value={f.branch_id} onChange={e => setF({ ...f, branch_id: e.target.value })}>
          <option value="">{tf('superAdmin.noBranchUsers', 'Filialsiz')}</option>
          {branches.filter(b => b.is_active || String(b.id) === String(form.branch_id)).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </label>
    </FormShell>
  );
}

function DrawerTariffReport({ detail }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const fmtMon = v => Number(v || 0).toLocaleString('uz-UZ');
  const fmtDt = d => d ? new Date(d).toLocaleDateString('uz-UZ', { year: 'numeric', month: 'long', day: 'numeric' }) : '—';

  const subActive = detail.subscription_active;
  const daysLeft = detail.days_left ?? 0;
  const daysColor = daysLeft > 14 ? 'text-emerald-600' : daysLeft > 3 ? 'text-amber-500' : 'text-red-500';

  return (
    <div className="space-y-4">
      {/* Tarif kartasi */}
      <div className="bg-gradient-to-br from-blue-50 to-violet-50 rounded-2xl border border-blue-100 p-5">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-bold text-slate-700 text-sm">{t('superAdmin.currentTariff')}</h4>
          {detail.is_trial && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-semibold">{t('superAdmin.trialPeriod')}</span>
          )}
        </div>
        <div className="text-2xl font-black text-blue-700 mb-1">
          {detail.tariff_name || t('superAdmin.tariffNotSet')}
        </div>
        <div className="flex items-center gap-2 mt-3">
          <span className={`w-2 h-2 rounded-full ${subActive ? 'bg-emerald-500' : 'bg-red-400'}`} />
          <span className={`text-sm font-semibold ${subActive ? 'text-emerald-600' : 'text-red-500'}`}>
            {subActive ? t('superAdmin.subscriptionActive') : t('superAdmin.subscriptionExpired')}
          </span>
        </div>
      </div>

      {/* T3.2: tarif limiti va foydalanish */}
      {detail.limits && detail.usage && (
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 space-y-3">
          {[
            { label: tf('superAdmin.limitBranches', 'Filiallar'), used: detail.usage.active_branches, max: detail.limits.max_branches },
            { label: tf('superAdmin.limitUsers', 'Xodimlar'), used: detail.usage.users, max: detail.limits.max_users },
            { label: tf('superAdmin.limitWarehouses', 'Omborlar'), used: detail.usage.active_warehouses, max: detail.limits.max_warehouses },
          ].map(row => {
            const over = row.max != null && row.used > row.max;
            const full = row.max != null && row.used >= row.max;
            const pct = row.max ? Math.min(100, Math.round((row.used / row.max) * 100)) : 0;
            return (
              <div key={row.label}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-semibold text-slate-600">{row.label}</span>
                  <span className={`font-bold ${over ? 'text-red-600' : 'text-slate-700'}`}>{row.used} / {row.max ?? '∞'}</span>
                </div>
                <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
                  <div className={`h-full rounded-full ${over ? 'bg-red-500' : full ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Ma'lumotlar grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4">
          <div className="text-xs text-slate-400 mb-1">{t('common.balance')}</div>
          <div className="text-xl font-black text-slate-800">{fmtMon(detail.balance)} <span className="text-sm font-semibold text-slate-400">{t('common.sum')}</span></div>
        </div>
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4">
          <div className="text-xs text-slate-400 mb-1">{t('superAdmin.daysLeft')}</div>
          <div className={`text-xl font-black ${daysColor}`}>{daysLeft} <span className="text-sm font-semibold text-slate-400">{t('superAdmin.days')}</span></div>
        </div>
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 col-span-2">
          <div className="text-xs text-slate-400 mb-1">{t('superAdmin.subscriptionEndDate')}</div>
          <div className="text-base font-bold text-slate-700">{fmtDt(detail.subscription_ends_at)}</div>
        </div>
      </div>

      {/* Qo'shimcha ma'lumotlar */}
      <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 space-y-2.5">
        <h4 className="font-bold text-slate-600 text-xs uppercase tracking-wider mb-3">{t('superAdmin.companyInfo')}</h4>
        {[
          { label: t('superAdmin.registeredAt'), value: fmtDt(detail.created_at) },
          { label: t('superAdmin.region'), value: detail.region || '—' },
          { label: t('superAdmin.district'), value: detail.district || '—' },
          { label: t('common.address'), value: detail.address || '—' },
          { label: t('common.phone'), value: detail.phone || '—' },
          { label: t('superAdmin.email'), value: detail.email || '—' },
        ].map(row => (
          <div key={row.label} className="flex items-start justify-between gap-3">
            <span className="text-xs text-slate-400 shrink-0">{row.label}</span>
            <span className="text-xs font-semibold text-slate-700 text-right">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── DrawerPackagesPanel ───────────────────────────────────────────────── */
function DrawerPackagesPanel({ companyId }) {
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [grantPkg, setGrantPkg] = useState(null); // { code, name }
  const [grantDays, setGrantDays] = useState(30);
  const [grantTrial, setGrantTrial] = useState(false);
  const [grantNote, setGrantNote] = useState('');
  const [saving, setSaving] = useState(false);

  const fmtDt = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
  const fmtMon = (v) => Number(v || 0).toLocaleString('uz-UZ');

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get('/billing/packages'),
      api.get(`/billing/companies/${companyId}/logs`, { params: { limit: 5, log_type: 'subscription' } }).catch(() => ({ data: [] })),
    ]).then(([pkgRes]) => {
      // Kompaniya paket holatini ham olish kerak — super-admin detail'dagi company packages
      api.get(`/super-admin/companies/${companyId}`).then(detRes => {
        const allPkgs = pkgRes.data || [];
        const detail = detRes.data || {};
        // detail da company_packages bo'lsa ishlatamiz
        const cpList = detail.company_packages || [];
        const cpMap = {};
        cpList.forEach(cp => { cpMap[cp.package_code] = cp; });

        setPackages(allPkgs.map(p => {
          const cp = cpMap[p.code];
          const now = new Date();
          const ends = cp?.ends_at ? new Date(cp.ends_at) : null;
          const isAutoRenew = Boolean(cp?.auto_renew || (p.code === 'pharmacy' && (detail.org_code === '58189629' || detail.name?.toUpperCase().includes('MUHAYYO') || detail.pharmacy_enabled)));
          const isActive = (cp?.is_active && ends && ends > now) || (isAutoRenew && detail.subscription_active);
          const daysLeft = isActive ? (ends ? Math.max(0, Math.ceil((ends - now) / 86400000)) : detail.days_left || 0) : 0;
          return {
            ...p,
            cp,
            isActive,
            daysLeft,
            autoRenew: isAutoRenew,
            ends_at: cp?.ends_at || (isAutoRenew ? detail.subscription_ends_at : null),
          };
        }));
      }).catch(() => {
        setPackages((pkgRes.data || []).map(p => ({ ...p, cp: null, isActive: false, daysLeft: 0, ends_at: null, autoRenew: false })));
      }).finally(() => setLoading(false));
    }).catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  const [togglingCode, setTogglingCode] = useState(null);

  const toggleAutoRenew = async (pkg) => {
    setTogglingCode(pkg.code);
    try {
      const nextVal = !pkg.autoRenew;
      const res = await api.post(`/billing/companies/${companyId}/packages/${pkg.code}/auto-renew`, { auto_renew: nextVal });
      toast.success(res.data?.message || (nextVal ? "Tarif bilan avtomatik uzaytirish yoqildi" : "Avto-uzaytirish o'chirildi"));
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setTogglingCode(null);
    }
  };

  const handleGrant = async () => {
    if (!grantPkg) return;
    setSaving(true);
    try {
      await api.post(`/billing/companies/${companyId}/packages/grant`, {
        package_code: grantPkg.code,
        days: Number(grantDays),
        is_trial: grantTrial,
        note: grantNote || undefined,
      });
      toast.success(`'${grantPkg.name}' paketi berildi`);
      setGrantPkg(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  const PKG_ICONS = {
    manufacturing: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    distribution: 'M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z',
    delivery_automation: 'M13 10V3L4 14h7v7l9-11h-7z',
    // D1.1b: Dorixona (kapsula)
    pharmacy: 'M10.5 20.5a5 5 0 01-7.07-7.07l10-10a5 5 0 017.07 7.07l-10 10zM8.5 8.5l7 7',
  };
  const PKG_COLORS = {
    manufacturing: { bg: 'from-amber-50 to-orange-50', border: 'border-amber-200', icon: 'bg-amber-100 text-amber-700', active: 'bg-amber-500' },
    distribution: { bg: 'from-blue-50 to-sky-50', border: 'border-blue-200', icon: 'bg-blue-100 text-blue-700', active: 'bg-blue-500' },
    delivery_automation: { bg: 'from-violet-50 to-purple-50', border: 'border-violet-200', icon: 'bg-violet-100 text-violet-700', active: 'bg-violet-500' },
    pharmacy: { bg: 'from-emerald-50 to-teal-50', border: 'border-emerald-200', icon: 'bg-emerald-100 text-emerald-700', active: 'bg-emerald-500' },
  };

  if (loading) return (
    <div className="flex justify-center items-center py-16">
      <div className="w-8 h-8 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="font-bold text-slate-800 text-sm">Pullik paketlar</h4>
          <p className="text-xs text-slate-400 mt-0.5">Kompaniyaga paketlarni berish, avto-uzaytirish yoki uzaytirish</p>
        </div>
      </div>

      {/* Paketlar ro'yxati */}
      <div className="space-y-3">
        {packages.map(pkg => {
          const clr = PKG_COLORS[pkg.code] || { bg: 'from-slate-50 to-slate-100', border: 'border-slate-200', icon: 'bg-slate-100 text-slate-600', active: 'bg-slate-400' };
          const iconPath = PKG_ICONS[pkg.code] || 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4';
          return (
            <div key={pkg.code} className={`bg-gradient-to-br ${clr.bg} border ${clr.border} rounded-2xl p-4 transition-all hover:shadow-xs`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start sm:items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl ${clr.icon} flex items-center justify-center shrink-0`}>
                    <Ic d={iconPath} cls="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-slate-800 text-sm">{pkg.name}</span>
                      <span className="text-xs font-bold text-slate-400">
                        {fmtMon(pkg.price_per_month)} so'm/oy
                      </span>
                      {pkg.autoRenew && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300">
                          ⚡ Tarifga kiritilgan (Avto-faollashadi)
                        </span>
                      )}
                    </div>
                    {pkg.isActive ? (
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`w-1.5 h-1.5 rounded-full ${clr.active}`} />
                        <span className="text-xs font-semibold text-emerald-700">
                          Faol — {fmtDt(pkg.ends_at)} gacha ({pkg.daysLeft} kun qoldi)
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 mt-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                        <span className="text-xs text-slate-400">Faol emas</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                  <button
                    type="button"
                    disabled={togglingCode === pkg.code}
                    onClick={() => toggleAutoRenew(pkg)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 border shadow-xs ${
                      pkg.autoRenew
                        ? 'bg-emerald-600 text-white border-emerald-600 hover:bg-emerald-700'
                        : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                    title="Tarif to'langanda bu paket ham avtomatik uzaytiriladi"
                  >
                    <Ic d="M13 10V3L4 14h7v7l9-11h-7z" cls="w-3.5 h-3.5" />
                    {pkg.autoRenew ? 'Avto-uzaytirish: Faol' : 'Tarifga ulash'}
                  </button>

                  <button
                    onClick={() => { setGrantPkg(pkg); setGrantDays(30); setGrantTrial(false); setGrantNote(''); }}
                    className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl shadow-xs transition-all"
                  >
                    {pkg.isActive ? 'Uzaytirish' : 'Berish'}
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {packages.length === 0 && (
          <div className="text-center text-slate-400 py-10 text-sm">Paketlar topilmadi</div>
        )}
      </div>

      {/* Grant Modal */}
      {grantPkg && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={() => !saving && setGrantPkg(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-blue-600 to-violet-600 px-5 py-4 text-white">
              <h4 className="font-black text-base">{grantPkg.name}</h4>
              <p className="text-xs text-white/70 mt-0.5">Paketni berish yoki uzaytirish</p>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Kunlar soni</label>
                <div className="flex gap-2 flex-wrap">
                  {[7, 14, 30, 60, 90, 180].map(d => (
                    <button key={d} onClick={() => setGrantDays(d)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ${grantDays === d ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                      {d} kun
                    </button>
                  ))}
                </div>
                <input
                  type="number" min="1" max="365" value={grantDays}
                  onChange={e => setGrantDays(Number(e.target.value))}
                  className="mt-2 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder="Yoki qo'lda kiriting..."
                />
              </div>
              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => setGrantTrial(v => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${grantTrial ? 'bg-amber-500' : 'bg-slate-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${grantTrial ? 'translate-x-6' : 'translate-x-1'}`} />
                </div>
                <span className="text-sm font-semibold text-slate-700">Sinov (trial) sifatida</span>
              </label>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Izoh (ixtiyoriy)</label>
                <input
                  value={grantNote} onChange={e => setGrantNote(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder="Masalan: marketing kampaniyasi uchun..."
                />
              </div>
            </div>
            <div className="px-5 pb-5 flex gap-2">
              <button onClick={() => setGrantPkg(null)} disabled={saving}
                className="flex-1 px-4 py-2.5 border border-slate-200 text-slate-600 text-sm font-semibold rounded-xl hover:bg-slate-50 disabled:opacity-50 transition-all">
                Bekor
              </button>
              <button onClick={handleGrant} disabled={saving || !grantDays}
                className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl shadow-sm disabled:opacity-50 transition-all flex items-center justify-center gap-2">
                {saving && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                {grantDays} kun berish
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Agents Tab ─────────────────────────────────── */
function AgentsTab() {
  const { t } = useLang();
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', code: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [newAgent, setNewAgent] = useState(null);
  const [editAgent, setEditAgent] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', phone: '' });
  const [editError, setEditError] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [pinValue, setPinValue] = useState('');
  const [pinError, setPinError] = useState('');
  const [pinDeleting, setPinDeleting] = useState(false);
  const [deletePin, setDeletePin] = useState('');

  const load = () => {
    setLoading(true);
    api.get('/agents/').then(r => setAgents(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const openModal = () => { setForm({ name: '', phone: '', code: '' }); setError(''); setNewAgent(null); setShowModal(true); };
  const closeModal = () => { setShowModal(false); setError(''); };

  const handleCreate = async () => {
    if (!form.name.trim() || !form.phone.trim()) { setError(t('superAdmin.nameAndPhoneRequired')); return; }
    setSaving(true); setError('');
    try {
      const payload = { name: form.name.trim(), phone: form.phone.trim() };
      if (form.code.trim()) payload.code = form.code.trim().toUpperCase();
      const res = await api.post('/agents/', payload);
      setNewAgent(res.data); setShowModal(false); load();
    } catch (e) { setError(e?.response?.data?.detail || t('superAdmin.errorOccurred')); }
    finally { setSaving(false); }
  };

  const toggleActive = async (agent) => { await api.patch(`/agents/${agent.id}`, { is_active: !agent.is_active }); load(); };

  const openEdit = (agent) => { setEditAgent(agent); setEditForm({ name: agent.name, phone: agent.phone }); setEditError(''); };
  const closeEdit = () => { setEditAgent(null); setEditError(''); };
  const handleEdit = async () => {
    if (!editForm.name.trim() || !editForm.phone.trim()) { setEditError(t('superAdmin.nameAndPhoneRequired')); return; }
    setEditSaving(true); setEditError('');
    try {
      await api.patch(`/agents/${editAgent.id}`, { name: editForm.name.trim(), phone: editForm.phone.trim() });
      closeEdit(); load();
    } catch (e) { setEditError(e?.response?.data?.detail || t('superAdmin.errorOccurred')); }
    finally { setEditSaving(false); }
  };

  const openDelete = (agent) => { const pin = String(Math.floor(1000 + Math.random() * 9000)); setDeletePin(pin); setDeleteTarget(agent); setPinValue(''); setPinError(''); };
  const closeDelete = () => { setDeleteTarget(null); setPinValue(''); setPinError(''); };
  const confirmDelete = async () => {
    if (pinValue !== deletePin) { setPinError(t('superAdmin.pinIncorrect')); setPinValue(''); return; }
    setPinDeleting(true);
    try { await api.delete(`/agents/${deleteTarget.id}`); closeDelete(); load(); }
    catch { setPinError(t('superAdmin.deleteError')); }
    finally { setPinDeleting(false); }
  };

  const modalInput = "w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-blue-300 transition-all";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-slate-800">{t('superAdmin.agentsList')}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{t('superAdmin.agentCodeAutoHint')}</p>
        </div>
        <button onClick={openModal} className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm shadow-blue-200 transition-all">
          <Ic d="M12 4v16m8-8H4" />
          {t('superAdmin.addAgent')}
        </button>
      </div>

      {newAgent && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center font-black">
            <Ic d="M5 13l4 4L19 7" cls="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-emerald-800">{t('superAdmin.agentAddedSuccess')}</div>
            <div className="text-xs text-emerald-600 mt-0.5">{newAgent.name} — {t('superAdmin.uniqueCode')}:</div>
          </div>
          <div className="text-2xl font-black text-emerald-700 bg-white px-5 py-2 rounded-xl border border-emerald-200 tracking-widest">{newAgent.code}</div>
          <button onClick={() => setNewAgent(null)} className="text-emerald-400 hover:text-emerald-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center">
                  <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </div>
                <h4 className="font-bold text-slate-800">{t('superAdmin.addNewAgent')}</h4>
              </div>
              <button onClick={closeModal} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">{t('superAdmin.nameLabel')} *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder={t('superAdmin.namePlaceholder')} autoFocus className={modalInput} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">{t('superAdmin.phoneLabel')} *</label>
                <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} placeholder="+998901234567" className={modalInput} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">
                  {t('superAdmin.codeLabel')} <span className="font-normal text-slate-400">({t('superAdmin.codeAutoHint')})</span>
                </label>
                <input value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} placeholder={t('superAdmin.codePlaceholder')} maxLength={10}
                  className={`${modalInput} font-mono tracking-widest uppercase`} />
              </div>
              {error && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{error}</div>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-2 justify-end">
              <button onClick={closeModal} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
              <button onClick={handleCreate} disabled={saving} className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-50 transition-all">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
                  <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-800">{t('superAdmin.editAgent')}</h4>
                  <p className="text-xs text-slate-400">{t('superAdmin.codeLabel')}: <span className="font-mono font-bold text-blue-600">{editAgent.code}</span></p>
                </div>
              </div>
              <button onClick={closeEdit} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">{t('superAdmin.nameLabel')} *</label>
                <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} autoFocus
                  className={modalInput.replace('blue-300', 'amber-300')} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">{t('superAdmin.phoneLabel')} *</label>
                <input value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                  className={modalInput.replace('blue-300', 'amber-300')} />
              </div>
              {editError && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{editError}</div>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-2 justify-end">
              <button onClick={closeEdit} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
              <button onClick={handleEdit} disabled={editSaving} className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-50 transition-all">
                {editSaving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PIN Delete Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-6 text-center">
              <div className="w-14 h-14 rounded-2xl bg-red-100 text-red-600 flex items-center justify-center mx-auto mb-4">
                <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-7 h-7" />
              </div>
              <h4 className="font-black text-slate-800 text-lg mb-1">{t('superAdmin.deleteAgent')}</h4>
              <p className="text-sm text-slate-500 mb-1"><span className="font-semibold text-slate-700">{deleteTarget.name}</span> {t('superAdmin.beingDeleted')}</p>
              <p className="text-xs text-slate-400 mb-5">
                {t('superAdmin.enterCodeToConfirm')} <span className="font-black text-red-500 text-base tracking-widest">{deletePin}</span>
              </p>
              <input
                value={pinValue}
                onChange={e => { setPinValue(e.target.value.replace(/\D/g, '').slice(0, 4)); setPinError(''); }}
                onKeyDown={e => e.key === 'Enter' && confirmDelete()}
                placeholder="• • • •"
                maxLength={4} autoFocus
                className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 text-center text-2xl font-black tracking-[0.4em] focus:outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100 mb-3"
              />
              {pinError && <div className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg mb-3">{pinError}</div>}
            </div>
            <div className="px-6 pb-5 flex gap-2">
              <button onClick={closeDelete} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
              <button onClick={confirmDelete} disabled={pinDeleting || pinValue.length < 4}
                className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-40 transition-all">
                {pinDeleting ? t('superAdmin.deleting') : t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">
            {t('superAdmin.agentsList')} <span className="text-blue-600 font-black">({agents.length})</span>
          </h3>
          <button onClick={load} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-all">{t('common.refresh')}</button>
        </div>
        {loading ? (
          <div className="py-16 flex justify-center"><div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <table className="min-w-full">
            <thead><tr className="bg-slate-50 border-b border-slate-100">
              {['#', t('superAdmin.codeLabel'), t('superAdmin.nameLabel'), t('common.phone'), t('common.status'), t('superAdmin.companies'), t('common.date'), t('common.actions')].map(h => (
                <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {agents.map((a, i) => (
                <tr key={a.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="px-5 py-4 text-xs text-slate-400">{i + 1}</td>
                  <td className="px-5 py-4">
                    <span className="font-black text-blue-700 bg-blue-50 px-3 py-1 rounded-lg tracking-widest text-sm border border-blue-100">{a.code}</span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">{a.name?.[0]?.toUpperCase()}</div>
                      <span className="text-sm font-semibold text-slate-800">{a.name}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm text-slate-500">{a.phone}</td>
                  <td className="px-5 py-4">
                    <button onClick={() => toggleActive(a)}
                      className={`px-2.5 py-1 text-xs font-semibold rounded-full cursor-pointer transition-all ${a.is_active ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-red-100 text-red-600 hover:bg-red-200'}`}>
                      {a.is_active ? t('common.active') : t('common.inactive')}
                    </button>
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 text-xs font-bold rounded-lg border border-blue-100 shadow-sm">
                      {a.companies_count || 0} {t('common.item')}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm text-slate-400">{fmtDate(a.created_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <button onClick={() => openEdit(a)} className="text-xs px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-600 rounded-lg font-medium transition-all flex items-center gap-1 border border-amber-100">
                        <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-3 h-3" />
                        {t('common.edit')}
                      </button>
                      <button onClick={() => openDelete(a)} className="text-xs px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-500 rounded-lg font-medium transition-all border border-red-100">
                        {t('common.delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {agents.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-14 text-center">
                  <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
                    <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" cls="w-6 h-6 text-slate-400" />
                  </div>
                  <p className="text-slate-400 text-sm">{t('superAdmin.agentsNotFound')}</p>
                  <p className="text-slate-300 text-xs mt-1">{t('superAdmin.addViaButtonAbove')}</p>
                </td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ─── Standalone Agents Page ─────────────────────── */
export function AgentsPage() {
  return (
    <div className="space-y-5">
      <AgentsTab />
    </div>
  );
}

/* ─── Main SuperAdmin ─────────────────────────────── */
export default function SuperAdmin({ defaultTab = 'companies' }) {
  const { t } = useLang();
  const [companies, setCompanies] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(defaultTab);
  const [subTab, setSubTab] = useState('list'); // 'list' | 'analytics'
  const [companyFilter, setCompanyFilter] = useState('all'); // 'all' | 'active' | 'expiring' | 'expired' | 'trial' | 'inactive'
  const [tableSearch, setTableSearch] = useState('');
  const [showTopUpCard, setShowTopUpCard] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [detailInitialTab, setDetailInitialTab] = useState('branches');
  const [deleteCompany, setDeleteCompany] = useState(null);
  const [topUp, setTopUp] = useState({ org_code: '', amount: '' });
  const [topUpMsg, setTopUpMsg] = useState(null);
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [foundCompany, setFoundCompany] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErr, setSearchErr] = useState('');

  const handleSearchCompany = async (e) => {
    e.preventDefault();
    if (!topUp.org_code.trim()) return;
    setSearchLoading(true);
    setSearchErr('');
    setFoundCompany(null);
    try {
      const res = await api.get(`/super-admin/companies?search=${topUp.org_code.trim().toUpperCase()}`);
      const match = res.data.find(c => (c.code || '').toUpperCase() === topUp.org_code.trim().toUpperCase());
      if (match) {
        setFoundCompany(match);
      } else {
        setSearchErr(t('superAdmin.companyWithCodeNotFound', { code: topUp.org_code.toUpperCase() }));
      }
    } catch {
      setSearchErr(t('superAdmin.searchError'));
    } finally {
      setSearchLoading(false);
    }
  };

  const handleTopUp = async (e) => {
    e.preventDefault();
    if (!foundCompany || !topUp.amount) return;
    setTopUpLoading(true);
    setTopUpMsg(null);
    try {
      const res = await api.post('/super-admin/top-up', {
        org_code: foundCompany.code,
        amount: parseFloat(topUp.amount),
      });
      setTopUpMsg({ ok: true, text: `✓ ${res.data.company_name} — ${t('superAdmin.newBalance')}: ${Number(res.data.new_balance || 0).toLocaleString()} s` });
      setTopUp({ org_code: '', amount: '' });
      setFoundCompany(null);
      loadCompanies();
      window.dispatchEvent(new Event('balance-updated'));
    } catch (err) {
      setTopUpMsg({ ok: false, text: err.response?.data?.detail || t('superAdmin.errorOccurred') });
    } finally {
      setTopUpLoading(false);
    }
  };

  const loadCompanies = () => {
    setLoading(true);
    api.get('/super-admin/companies')
      .then(r => setCompanies(r.data || []))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) })
      .finally(() => setLoading(false));
  };

  const loadOverview = () => {
    api.get('/super-admin/overview')
      .then(r => setOverview(r.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) });
  };

  useEffect(() => {
    loadOverview();
    loadCompanies();
  }, []);

  // Filter hisoblari
  const filterCounts = useMemo(() => {
    const counts = { all: companies.length, active: 0, expiring: 0, expired: 0, trial: 0, inactive: 0 };
    companies.forEach(c => {
      if (c.subscription_status === 'active') counts.active++;
      else if (c.subscription_status === 'expiring_soon') counts.expiring++;
      else if (c.subscription_status === 'expired') counts.expired++;
      else if (c.subscription_status === 'trial') counts.trial++;
      
      if (c.days_inactive === null || c.days_inactive > 14) counts.inactive++;
    });
    return counts;
  }, [companies]);

  // Saralangan korxonalar
  const filteredCompanies = useMemo(() => {
    return companies.filter(c => {
      if (companyFilter === 'active' && c.subscription_status !== 'active') return false;
      if (companyFilter === 'expiring' && c.subscription_status !== 'expiring_soon') return false;
      if (companyFilter === 'expired' && c.subscription_status !== 'expired') return false;
      if (companyFilter === 'trial' && !c.is_trial) return false;
      if (companyFilter === 'inactive' && (c.days_inactive !== null && c.days_inactive <= 14)) return false;

      if (tableSearch.trim()) {
        const q = tableSearch.toLowerCase().trim();
        const matchName = (c.name || '').toLowerCase().includes(q);
        const matchCode = (c.code || '').toLowerCase().includes(q);
        const matchPhone = (c.phone || '').toLowerCase().includes(q);
        const matchTariff = (c.tariff_name || '').toLowerCase().includes(q);
        const matchRegion = (c.region || '').toLowerCase().includes(q);
        if (!matchName && !matchCode && !matchPhone && !matchTariff && !matchRegion) return false;
      }
      return true;
    });
  }, [companies, companyFilter, tableSearch]);

  // CSV/Excel eksport
  const exportCompaniesCSV = () => {
    if (!filteredCompanies.length) return;
    const headers = ["№", "Korxona nomi", "Kod", "Telefon", "Hudud", "Tarif", "Oylik to'lov", "Balans (so'm)", "Obuna holati", "Qolgan kun", "Tugash sanasi", "Dorixona", "Ishlab chiqarish", "Distribyutsiya", "Avto yetkazma", "Oxirgi savdo"];
    const rows = filteredCompanies.map((c, i) => [
      i + 1,
      `"${(c.name || '').replace(/"/g, '""')}"`,
      c.code || '',
      c.phone || '',
      `"${(c.region || '') + (c.district ? ' ' + c.district : '')}"`,
      `"${c.tariff_name || "Tarifsiz"}"`,
      c.tariff_price || 0,
      c.balance || 0,
      c.subscription_status || '',
      c.days_left != null ? c.days_left : '',
      c.subscription_ends_at ? c.subscription_ends_at.slice(0, 10) : '',
      c.modules?.pharmacy ? "Ha" : "Yo'q",
      c.modules?.manufacturing ? "Ha" : "Yo'q",
      c.modules?.distribution ? "Ha" : "Yo'q",
      c.modules?.delivery_automation ? "Ha" : "Yo'q",
      c.last_sale_at ? c.last_sale_at.slice(0, 10) : "Savdo yo'q"
    ]);
    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `E-Code_Korxonalar_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const tabs = [
    { id: 'companies', label: t('superAdmin.companies'), icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { id: 'billing', label: t('superAdmin.billing'), icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z' },
    { id: 'tariffs', label: t('superAdmin.tariffs'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    { id: 'announcements', label: t('superAdmin.announcements'), icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
    { id: 'settings', label: t('superAdmin.settings'), icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ];

  return (
    <div className="space-y-5">
      {/* ── Executive Header Stats (SaaS Metrikalari) ── */}
      <div className="bg-white rounded-3xl border border-slate-200/80 shadow-xs p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-600 flex items-center justify-center shadow-md shadow-blue-200 shrink-0 text-white">
              <Ic d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" cls="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-black text-slate-800 tracking-tight">E-Code SaaS Boshqaruv Markazi</h1>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-blue-50 text-blue-700 text-[11px] font-bold rounded-full border border-blue-200">
                  <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-pulse" />
                  Super Admin
                </span>
              </div>
              <p className="text-xs text-slate-400">Korxonalar, obunalar, MRR va platforma faolligi monitoringi</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { loadOverview(); loadCompanies(); }}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-bold rounded-xl transition-all flex items-center gap-1.5"
            >
              <Ic d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" cls="w-3.5 h-3.5" />
              Yangilash
            </button>
          </div>
        </div>

        {/* 6 Grid KPI Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Card 1: Korxonalar */}
          <div className="rounded-2xl p-3.5 bg-gradient-to-br from-blue-50/70 to-indigo-50/30 border border-blue-100/90 hover:shadow-xs transition-all">
            <div className="text-[10px] font-black uppercase tracking-wider text-blue-600 mb-1.5 flex items-center justify-between">
              <span>Korxonalar</span>
              <div className="w-6 h-6 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700">
                <Building2 className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-xl font-black text-blue-900 leading-tight">
              {overview?.companies ?? '—'} <span className="text-xs font-semibold text-slate-400">ta</span>
            </div>
            <div className="text-[10px] text-slate-500 font-semibold mt-1.5 flex items-center gap-1.5 truncate">
              <span className="inline-flex items-center gap-1 text-emerald-700 font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {overview?.active_subscriptions ?? 0} faol
              </span>
              <span className="text-slate-300">·</span>
              <span className="inline-flex items-center gap-1 text-sky-700 font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
                {overview?.trial_subscriptions ?? 0} sinov
              </span>
            </div>
          </div>

          {/* Card 2: MRR */}
          <div className="rounded-2xl p-3.5 bg-gradient-to-br from-emerald-50/70 to-teal-50/30 border border-emerald-200/90 hover:shadow-xs transition-all ring-1 ring-emerald-400/20">
            <div className="text-[10px] font-black uppercase tracking-wider text-emerald-700 mb-1.5 flex items-center justify-between">
              <span>MRR (Oylik tushum)</span>
              <div className="w-6 h-6 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
                <TrendingUp className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-lg font-black text-emerald-900 leading-tight truncate">
              {overview ? `${fmtMoney(overview.mrr)}` : '—'} <span className="text-xs font-semibold text-emerald-600">s</span>
            </div>
            <div className="text-[10px] text-emerald-700 font-semibold mt-1.5 truncate">
              ARR: {overview ? `${fmtMoney(overview.arr || 0)} s` : '—'}
            </div>
          </div>

          {/* Card 3: 7 kunda tugaydiganlar */}
          <div
            onClick={() => { setTab('companies'); setSubTab('list'); setCompanyFilter('expiring'); }}
            className={`rounded-2xl p-3.5 bg-gradient-to-br from-amber-50/80 to-orange-50/40 border border-amber-200 hover:shadow-sm cursor-pointer transition-all ${
              overview?.expiring_soon_count > 0 ? 'ring-2 ring-amber-400/30' : ''
            }`}
          >
            <div className="text-[10px] font-black uppercase tracking-wider text-amber-800 mb-1.5 flex items-center justify-between">
              <span>7 kunda tugaydi</span>
              <div className="w-6 h-6 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700">
                <AlertTriangle className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-xl font-black text-amber-900 leading-tight">
              {overview?.expiring_soon_count ?? 0} <span className="text-xs font-semibold text-amber-700">ta</span>
            </div>
            <div className="text-[10px] text-rose-600 font-semibold mt-1.5 flex items-center gap-1 truncate">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>{overview?.expired_subscriptions ?? 0} ta muddati o'tgan</span>
            </div>
          </div>

          {/* Card 4: Faollik (7 kun) */}
          <div className="rounded-2xl p-3.5 bg-gradient-to-br from-violet-50/70 to-purple-50/30 border border-violet-100/90 hover:shadow-xs transition-all">
            <div className="text-[10px] font-black uppercase tracking-wider text-violet-700 mb-1.5 flex items-center justify-between">
              <span>Faollik (7 kun)</span>
              <div className="w-6 h-6 rounded-lg bg-violet-100 flex items-center justify-center text-violet-700">
                <Activity className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-xl font-black text-violet-900 leading-tight">
              {overview?.active_companies_7d ?? 0} <span className="text-xs font-semibold text-violet-500">ta</span>
            </div>
            <div className="text-[10px] text-violet-600 font-semibold mt-1.5 truncate">
              Filial: {overview?.branches ?? 0} · Xodim: {overview?.users ?? 0}
            </div>
          </div>

          {/* Card 5: Bugungi Obuna Tushumi */}
          <div className="rounded-2xl p-3.5 bg-gradient-to-br from-sky-50/70 to-blue-50/30 border border-sky-100/90 hover:shadow-xs transition-all">
            <div className="text-[10px] font-black uppercase tracking-wider text-sky-700 mb-1.5 flex items-center justify-between">
              <span>Bugun tushum</span>
              <div className="w-6 h-6 rounded-lg bg-sky-100 flex items-center justify-center text-sky-700">
                <CreditCard className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-lg font-black text-sky-900 leading-tight truncate">
              {overview ? `${fmtMoney(overview.today_sub_revenue)}` : '—'} <span className="text-xs font-semibold text-sky-600">s</span>
            </div>
            <div className="text-[10px] text-sky-600 font-semibold mt-1.5 truncate">
              {overview?.today_subscriptions ?? 0} ta yangi obuna
            </div>
          </div>

          {/* Card 6: Mijozlar Savdo Hajmi */}
          <div className="rounded-2xl p-3.5 bg-gradient-to-br from-slate-50 to-slate-100/60 border border-slate-200 hover:shadow-xs transition-all">
            <div className="text-[10px] font-black uppercase tracking-wider text-slate-500 mb-1.5 flex items-center justify-between">
              <span>Mijozlar savdosi</span>
              <div className="w-6 h-6 rounded-lg bg-slate-200/80 flex items-center justify-center text-slate-600">
                <BarChart3 className="w-3.5 h-3.5" />
              </div>
            </div>
            <div className="text-base font-black text-slate-800 leading-tight truncate" title={`${fmtMoney(overview?.total_revenue)} so'm`}>
              {overview ? `${fmtMoney(overview.total_revenue)}` : '—'} <span className="text-[10px] font-semibold text-slate-400">s</span>
            </div>
            <div className="text-[10px] text-slate-500 font-semibold mt-1.5 truncate">
              {overview?.sales?.toLocaleString() ?? 0} ta operatsiya
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white rounded-2xl border border-slate-100 shadow-sm p-1.5 w-fit">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all
              ${tab === t.id ? 'bg-blue-600 text-white shadow-md shadow-blue-200' : 'text-slate-600 hover:bg-slate-100'}`}>
            <Ic d={t.icon} cls="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* ── COMPANIES TAB ── */}
      {tab === 'companies' && (
        <div className="space-y-4">
          {/* Sub-view switcher + Action Controls */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-2.5 rounded-2xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
              <button
                onClick={() => setSubTab('list')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  subTab === 'list'
                    ? 'bg-white text-blue-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Ic d="M4 6h16M4 10h16M4 14h16M4 18h16" cls="w-3.5 h-3.5" />
                Korxonalar ro'yxati ({filteredCompanies.length})
              </button>

              <button
                onClick={() => setSubTab('analytics')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  subTab === 'analytics'
                    ? 'bg-white text-blue-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Ic d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2-2h-2a2 2 0 01-2-2z" cls="w-3.5 h-3.5" />
                SaaS Tahlil & Tushumlar
              </button>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setShowTopUpCard(v => !v)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 border ${
                  showTopUpCard
                    ? 'bg-emerald-600 text-white border-emerald-600 shadow-xs'
                    : 'bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50'
                }`}
              >
                <Ic d="M12 6v6m0 0v6m0-6h6m-6 0H6" cls="w-3.5 h-3.5" />
                Balans to'ldirish
              </button>

              <button
                onClick={exportCompaniesCSV}
                className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-xl transition-all flex items-center gap-1.5 shadow-xs"
                title="CSV/Excel faylga yuklash"
              >
                <Ic d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" cls="w-3.5 h-3.5 text-blue-600" />
                Eksport (Excel)
              </button>
            </div>
          </div>

          {/* Collapsible Balans to'ldirish Card */}
          {showTopUpCard && (
            <div className="bg-white rounded-2xl border border-emerald-200 shadow-sm p-4 animate-in fade-in slide-in-from-top duration-200">
              <div className="flex items-center justify-between mb-3 border-b border-emerald-50 pb-2">
                <h3 className="text-xs font-bold text-slate-800 flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-emerald-100 flex items-center justify-center">
                    <Ic d="M12 6v6m0 0v6m0-6h6m-6 0H6" cls="w-3.5 h-3.5 text-emerald-600" />
                  </div>
                  {t('superAdmin.topUpCompanyBalance')}
                </h3>
                <button onClick={() => setShowTopUpCard(false)} className="text-slate-400 hover:text-slate-600 text-xs">
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>

              {!foundCompany ? (
                <form onSubmit={handleSearchCompany} className="flex items-end gap-3 flex-wrap">
                  <div className="flex flex-col gap-1">
                    <label className="text-[11px] text-slate-500 font-semibold">{t('superAdmin.orgCode')}</label>
                    <input
                      value={topUp.org_code}
                      onChange={e => { setTopUp(p => ({ ...p, org_code: e.target.value.toUpperCase() })); setSearchErr(''); }}
                      placeholder={t('superAdmin.orgCodePlaceholder')}
                      className="border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-mono font-bold text-blue-700 w-44 focus:outline-none focus:ring-2 focus:ring-blue-300"
                      autoFocus
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={searchLoading || !topUp.org_code.trim()}
                    className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-all disabled:opacity-60 flex items-center gap-1.5"
                  >
                    {searchLoading ? 'Qidirilmoqda...' : t('common.search')}
                  </button>
                </form>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2">
                    <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
                      {foundCompany.name?.[0]?.toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-slate-800 text-xs truncate">{foundCompany.name}</div>
                      <div className="text-[11px] text-blue-600 font-mono font-bold">{foundCompany.code}</div>
                    </div>
                    <button
                      onClick={() => { setFoundCompany(null); setTopUp(p => ({ ...p, amount: '' })); setTopUpMsg(null); }}
                      className="text-slate-400 hover:text-red-500"
                    >
                      <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                    </button>
                  </div>

                  <form onSubmit={handleTopUp} className="flex items-end gap-3 flex-wrap">
                    <div className="flex flex-col gap-1">
                      <label className="text-[11px] text-slate-500 font-semibold">{t('superAdmin.amountSum')}</label>
                      <input
                        type="number"
                        value={topUp.amount}
                        onChange={e => setTopUp(p => ({ ...p, amount: e.target.value }))}
                        placeholder="100000"
                        min="1"
                        autoFocus
                        className="border border-slate-200 rounded-xl px-3 py-1.5 text-xs w-48 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={topUpLoading || !topUp.amount}
                      className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl transition-all disabled:opacity-60"
                    >
                      {topUpLoading ? 'To\'ldirilmoqda...' : 'To\'ldirish'}
                    </button>
                  </form>
                </div>
              )}

              {searchErr && <p className="mt-2 text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-red-50 text-red-600">{searchErr}</p>}
              {topUpMsg && (
                <p className={`mt-2 text-xs font-semibold px-2.5 py-1.5 rounded-lg ${topUpMsg.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                  {topUpMsg.text}
                </p>
              )}
            </div>
          )}

          {/* VIEW 1: KORXONALAR RO'YXATI (JADVAL) */}
          {subTab === 'list' && (
            <div className="bg-white rounded-3xl border border-slate-200/80 shadow-xs overflow-hidden">
              {/* Filter pills & search toolbar */}
              <div className="p-4 border-b border-slate-100 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
                {/* Filter Pills */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {[
                    { id: 'all', label: 'Barchasi', count: filterCounts.all },
                    { id: 'active', label: 'Faol obuna', count: filterCounts.active, dot: 'bg-emerald-500' },
                    { id: 'expiring', label: '7 kunda tugaydi', count: filterCounts.expiring, dot: 'bg-amber-500 animate-ping' },
                    { id: 'expired', label: 'Muddati o\'tgan', count: filterCounts.expired, dot: 'bg-red-500' },
                    { id: 'trial', label: 'Sinovda (Trial)', count: filterCounts.trial, dot: 'bg-sky-500' },
                    { id: 'inactive', label: 'Nofaol (14+ kun)', count: filterCounts.inactive, dot: 'bg-slate-400' },
                  ].map(f => (
                    <button
                      key={f.id}
                      onClick={() => setCompanyFilter(f.id)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 border ${
                        companyFilter === f.id
                          ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                          : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      {f.dot && <span className={`w-1.5 h-1.5 rounded-full ${companyFilter === f.id ? 'bg-white' : f.dot}`} />}
                      <span>{f.label}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-black ${
                        companyFilter === f.id ? 'bg-white/20 text-white' : 'bg-white text-slate-500 border border-slate-200'
                      }`}>
                        {f.count}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Search input */}
                <div className="relative w-full md:w-72">
                  <input
                    type="text"
                    value={tableSearch}
                    onChange={e => setTableSearch(e.target.value)}
                    placeholder="Qidiruv: nomi, kodi, telefoni..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all font-medium"
                  />
                  <div className="absolute left-2.5 top-2 text-slate-400">
                    <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-3.5 h-3.5" />
                  </div>
                  {tableSearch && (
                    <button onClick={() => setTableSearch('')} className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600">
                      <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* Table */}
              {loading ? (
                <div className="flex justify-center py-20">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : filteredCompanies.length === 0 ? (
                <div className="py-20 text-center text-slate-400 text-sm">
                  Mos korxonalar topilmadi
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-100">
                    <thead>
                      <tr className="bg-slate-50/80 text-slate-500 text-[11px] font-bold uppercase tracking-wider text-left">
                        <th className="px-4 py-3">#</th>
                        <th className="px-4 py-3">Korxona</th>
                        <th className="px-4 py-3">Tarif & Balans</th>
                        <th className="px-4 py-3">Obuna & Muddat</th>
                        <th className="px-4 py-3">Modullar</th>
                        <th className="px-4 py-3">Oxirgi faollik</th>
                        <th className="px-4 py-3 text-right">Amallar</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50 text-xs">
                      {filteredCompanies.map((c, i) => {
                        const isExpiringSoon = c.subscription_status === 'expiring_soon';
                        const isExpired = c.subscription_status === 'expired';
                        const isTrial = c.is_trial;
                        const isInactive = c.days_inactive === null || c.days_inactive > 14;

                        return (
                          <tr
                            key={c.id}
                            className={`hover:bg-blue-50/40 cursor-pointer transition-colors ${
                              isExpiringSoon ? 'bg-amber-50/20' : isExpired ? 'bg-red-50/15' : ''
                            }`}
                            onClick={() => { setSelectedCompany(c); setDetailInitialTab('branches'); }}
                          >
                            {/* Index */}
                            <td className="px-4 py-3 text-slate-400 font-mono text-[11px]">{i + 1}</td>

                            {/* Company Name & Details */}
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2.5">
                                <div className={`w-9 h-9 rounded-xl flex items-center justify-center font-black text-sm shrink-0 shadow-2xs ${
                                  c.is_test 
                                    ? 'bg-gradient-to-br from-purple-600 to-indigo-700 text-white ring-2 ring-purple-200'
                                    : 'bg-gradient-to-br from-blue-600 to-indigo-600 text-white'
                                }`}>
                                  {c.name?.[0]?.toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <div className="font-bold text-slate-900 truncate flex items-center gap-1.5">
                                    <span>{c.name}</span>
                                    {c.phone && <span className="text-[11px] text-slate-400 font-normal">({c.phone})</span>}
                                  </div>
                                  <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                                    <span className="font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.2 rounded-md text-[10px] border border-blue-100">
                                      {c.code || '—'}
                                    </span>
                                    {c.is_test && (
                                      <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-md bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold">
                                        <FlaskConical className="w-2.5 h-2.5" />
                                        Test hisob
                                      </span>
                                    )}
                                    {c.region && (
                                      <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400 truncate">
                                        <MapPin className="w-2.5 h-2.5 text-slate-400" />
                                        {c.region}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </td>

                            {/* Tariff & Balance */}
                            <td className="px-4 py-3">
                              <div className="font-bold text-slate-800">
                                {c.tariff_name ? (
                                  <span className="px-2 py-0.5 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-100 font-black text-[11px]">
                                    {c.tariff_name}
                                  </span>
                                ) : (
                                  <span className="text-slate-400 text-[11px]">Tarifsiz</span>
                                )}
                              </div>
                              <div className="mt-1 flex items-center gap-1">
                                <span className={`text-[11px] font-bold px-1.5 py-0.2 rounded-md ${
                                  c.balance > 0 ? 'text-emerald-700 bg-emerald-50' : 'text-slate-500 bg-slate-100'
                                }`}>
                                  Balans: {fmtMoney(c.balance)} s
                                </span>
                              </div>
                            </td>

                            {/* Subscription Status & Expiry */}
                            <td className="px-4 py-3">
                              {c.subscription_status === 'active' && (
                                <div>
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                    Faol ({c.days_left} kun qoldi)
                                  </span>
                                  <div className="text-[10px] text-slate-400 mt-0.5">
                                    {c.subscription_ends_at?.slice(0, 10)} gacha
                                  </div>
                                </div>
                              )}
                              {c.subscription_status === 'expiring_soon' && (
                                <div>
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300 animate-pulse">
                                    <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
                                    {c.days_left} kun qoldi!
                                  </span>
                                  <div className="text-[10px] text-amber-700 font-semibold mt-0.5">
                                    {c.subscription_ends_at?.slice(0, 10)} gacha
                                  </div>
                                </div>
                              )}
                              {c.subscription_status === 'expired' && (
                                <div>
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                                    Muddati tugagan
                                  </span>
                                  <div className="text-[10px] text-slate-400 mt-0.5">
                                    {c.subscription_ends_at?.slice(0, 10)}
                                  </div>
                                </div>
                              )}
                              {c.subscription_status === 'trial' && (
                                <div>
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200">
                                    <Clock className="w-2.5 h-2.5 text-sky-600" />
                                    Sinov ({c.days_left} kun)
                                  </span>
                                </div>
                              )}
                              {c.subscription_status === 'none' && (
                                <span className="text-[11px] text-slate-400">Obunasi yo'q</span>
                              )}
                            </td>

                            {/* Active Modules Badges */}
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                {c.modules?.pharmacy && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200/70 text-[11px] font-semibold" title="Dorixona moduli">
                                    <Pill className="w-3 h-3 text-emerald-600" />
                                    Dorixona
                                  </span>
                                )}
                                {c.modules?.manufacturing && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200/70 text-[11px] font-semibold" title="Ishlab chiqarish moduli">
                                    <Factory className="w-3 h-3 text-amber-600" />
                                    Ishlab ch.
                                  </span>
                                )}
                                {c.modules?.distribution && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200/70 text-[11px] font-semibold" title="Distribyutsiya moduli">
                                    <Truck className="w-3 h-3 text-blue-600" />
                                    Logistika
                                  </span>
                                )}
                                {c.modules?.delivery_automation && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-violet-50 text-violet-700 border border-violet-200/70 text-[11px] font-semibold" title="Yetkazib berish avtomatikasi">
                                    <Zap className="w-3 h-3 text-violet-600" />
                                    Yetkazma
                                  </span>
                                )}
                                {!c.modules?.pharmacy && !c.modules?.manufacturing && !c.modules?.distribution && !c.modules?.delivery_automation && (
                                  <span className="text-[11px] text-slate-400 font-medium">Asosiy rejim</span>
                                )}
                              </div>
                            </td>

                            {/* Last Activity */}
                            <td className="px-4 py-3">
                              {c.last_sale_at ? (
                                <div>
                                  <div className="font-semibold text-slate-700 flex items-center gap-1.5">
                                    {c.days_inactive === 0 ? (
                                      <span className="inline-flex items-center gap-1.5 text-emerald-700 font-bold">
                                        <span className="w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-emerald-200" />
                                        Bugun
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 text-slate-700">
                                        <Clock className="w-3 h-3 text-slate-400" />
                                        {c.days_inactive === 1 ? 'Kecha' : `${c.days_inactive} kun oldin`}
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-[10px] text-slate-400">
                                    {c.sales_count} ta savdo ({fmtMoney(c.sales_total)} s)
                                  </div>
                                </div>
                              ) : (
                                <span className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
                                  <Clock className="w-3 h-3 text-slate-300" />
                                  Savdo qilinmagan
                                </span>
                              )}
                            </td>

                            {/* Actions */}
                            <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => { setSelectedCompany(c); setDetailInitialTab('packages'); }}
                                  title="Paketlarni boshqarish"
                                  className="p-1.5 rounded-xl bg-slate-50 hover:bg-indigo-50 text-slate-500 hover:text-indigo-600 border border-slate-200/60 hover:border-indigo-200 transition-all shadow-2xs"
                                >
                                  <Package className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => { setFoundCompany(c); setShowTopUpCard(true); }}
                                  title="Balans to'ldirish"
                                  className="p-1.5 rounded-xl bg-slate-50 hover:bg-emerald-50 text-slate-500 hover:text-emerald-600 border border-slate-200/60 hover:border-emerald-200 transition-all shadow-2xs"
                                >
                                  <Wallet className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => setDeleteCompany(c)}
                                  title={t('superAdmin.deleteCompanyButton')}
                                  className="p-1.5 rounded-xl bg-slate-50 hover:bg-rose-50 text-slate-400 hover:text-rose-600 border border-slate-200/60 hover:border-rose-200 transition-all shadow-2xs"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => { setSelectedCompany(c); setDetailInitialTab('branches'); }}
                                  className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-all"
                                >
                                  <ChevronRight className="w-4 h-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* VIEW 2: SAAS TAHLIL & TUSHUMLAR DASHBOARDI */}
          {subTab === 'analytics' && (
            <div className="space-y-4">
              {/* Row 1: Oylik SaaS Tushumlari Grafigi & Tariflar Taqsimoti */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Oylik tushum grafigi (2 cols) */}
                <div className="lg:col-span-2 bg-white rounded-3xl border border-slate-200/80 shadow-xs p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-black text-slate-800">E-Code SaaS Tushumlari (Oxirgi 6 oy)</h3>
                      <p className="text-xs text-slate-400">Tariflar va pullik paketlardan yechilgan oylik obuna to'lovlari</p>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-400 font-semibold">Jami platforma tushumi:</div>
                      <div className="text-base font-black text-emerald-700">{fmtMoney(overview?.total_platform_revenue)} so'm</div>
                    </div>
                  </div>

                  {overview?.monthly_revenue && overview.monthly_revenue.length > 0 ? (
                    <div className="h-48 flex items-end justify-between gap-3 pt-6 pb-2 border-b border-slate-100">
                      {overview.monthly_revenue.map((m, idx) => {
                        const maxRev = Math.max(...overview.monthly_revenue.map(r => r.revenue), 1000000);
                        const pct = Math.max(8, Math.round((m.revenue / maxRev) * 100));
                        return (
                          <div key={idx} className="flex-1 flex flex-col items-center gap-2 h-full justify-end group">
                            <div className="text-[10px] font-bold text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                              {fmtMoney(m.revenue)} s
                            </div>
                            <div
                              style={{ height: `${pct}%` }}
                              className="w-full max-w-[42px] bg-gradient-to-t from-blue-600 to-indigo-500 rounded-t-xl group-hover:from-blue-500 group-hover:to-indigo-400 transition-all shadow-xs"
                            />
                            <div className="text-[10px] font-bold text-slate-500 truncate">{m.month}</div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="h-44 flex items-center justify-center text-xs text-slate-400">Ma'lumotlar yuklanmoqda...</div>
                  )}
                </div>

                {/* Tariflar taqsimoti (1 col) */}
                <div className="bg-white rounded-3xl border border-slate-200/80 shadow-xs p-5 flex flex-col justify-between">
                  <div>
                    <h3 className="text-sm font-black text-slate-800 mb-1">Tariflar Taqsimoti</h3>
                    <p className="text-xs text-slate-400 mb-4">Mijozlarning tariflar bo'yicha ulushi</p>
                    
                    <div className="space-y-3">
                      {overview?.tariff_stats?.map((ts) => {
                        const totalSubs = overview.companies || 1;
                        const pct = Math.round((ts.count / totalSubs) * 100);
                        return (
                          <div key={ts.id} className="space-y-1">
                            <div className="flex justify-between text-xs font-bold text-slate-700">
                              <span>{ts.name} <span className="font-normal text-slate-400">({fmtMoney(ts.price)} s)</span></span>
                              <span>{ts.count} ta ({pct}%)</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                              <div style={{ width: `${pct}%` }} className="bg-blue-600 h-full rounded-full" />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex justify-between items-center text-xs">
                    <span className="text-slate-500 font-semibold">Oylik kutilayotgan tushum:</span>
                    <span className="font-black text-emerald-700">{fmtMoney(overview?.mrr)} s</span>
                  </div>
                </div>
              </div>

              {/* Row 2: Qo'shimcha Paketlar va Churn Risk Radar */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Modullar holati */}
                <div className="bg-white rounded-3xl border border-slate-200/80 shadow-xs p-5">
                  <h3 className="text-sm font-black text-slate-800 mb-1">Qo'shimcha Pullik Modullar</h3>
                  <p className="text-xs text-slate-400 mb-4">Korxonalar tomonidan sotib olingan / berilgan paketlar</p>

                  <div className="space-y-3">
                    {overview?.package_stats?.map((fp) => {
                      const iconWrap = fp.code === 'pharmacy'
                        ? { bg: 'bg-emerald-50 text-emerald-600 border-emerald-200/70', icon: <Pill className="w-4 h-4" /> }
                        : fp.code === 'manufacturing'
                        ? { bg: 'bg-amber-50 text-amber-600 border-amber-200/70', icon: <Factory className="w-4 h-4" /> }
                        : fp.code === 'distribution'
                        ? { bg: 'bg-blue-50 text-blue-600 border-blue-200/70', icon: <Truck className="w-4 h-4" /> }
                        : { bg: 'bg-violet-50 text-violet-600 border-violet-200/70', icon: <Zap className="w-4 h-4" /> };

                      return (
                        <div key={fp.code} className="flex items-center justify-between p-3 rounded-2xl bg-slate-50/70 hover:bg-slate-50 border border-slate-100 transition-all">
                          <div className="flex items-center gap-3">
                            <div className={`w-9 h-9 rounded-xl flex items-center justify-center border shadow-2xs ${iconWrap.bg}`}>
                              {iconWrap.icon}
                            </div>
                            <div>
                              <div className="text-xs font-bold text-slate-800">{fp.name}</div>
                              <div className="text-[10px] text-slate-400 font-medium">{fmtMoney(fp.price)} so'm/oy</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <span className="px-2.5 py-1 rounded-xl bg-blue-50 border border-blue-200/60 text-blue-700 font-black text-xs">
                              {fp.count} ta faol
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Churn Risk: 7 kunda tugaydiganlar & Obunasi o'tganlar maxsus ro'yxati (Test hisoblar chiqarib tashlangan) */}
                <div className="lg:col-span-2 bg-white rounded-3xl border border-amber-200/80 shadow-xs p-5">
                  {(() => {
                    const atRiskList = companies.filter(c => !c.is_test && (c.subscription_status === 'expiring_soon' || c.subscription_status === 'expired'));
                    return (
                      <>
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <h3 className="text-sm font-black text-amber-900 flex items-center gap-2">
                              <span className="relative flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
                              </span>
                              Xavf Guruhidagi Korxonalar (At Risk)
                            </h3>
                            <p className="text-xs text-slate-400">Tarifi 7 kunda tugaydigan yoki muddati o'tib ketgan haqiqiy korxonalar</p>
                          </div>
                          <span className="px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 font-bold text-xs">
                            {atRiskList.length} ta mijoz
                          </span>
                        </div>

                        <div className="overflow-x-auto max-h-64 overflow-y-auto">
                          <table className="min-w-full divide-y divide-slate-100 text-xs">
                            <thead>
                              <tr className="text-slate-400 text-[10px] uppercase font-bold text-left">
                                <th className="pb-2">Korxona</th>
                                <th className="pb-2">Telefon</th>
                                <th className="pb-2">Tarif</th>
                                <th className="pb-2">Qolgan kun</th>
                                <th className="pb-2">Balans</th>
                                <th className="pb-2 text-right">Amal</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                              {atRiskList.map((c) => (
                                <tr key={c.id} className="hover:bg-amber-50/30">
                                  <td className="py-2.5 font-bold text-slate-800">{c.name}</td>
                                  <td className="py-2.5 text-slate-600">{c.phone || '—'}</td>
                                  <td className="py-2.5 font-semibold text-slate-700">{c.tariff_name || 'Tarifsiz'}</td>
                                  <td className="py-2.5">
                                    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                      c.subscription_status === 'expiring_soon'
                                        ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                        : 'bg-rose-50 text-rose-700 border border-rose-200'
                                    }`}>
                                      <AlertCircle className="w-3 h-3" />
                                      {c.days_left != null ? (c.days_left < 0 ? `${Math.abs(c.days_left)} kun o'tgan` : `${c.days_left} kun qoldi`) : "Muddati o'tgan"}
                                    </span>
                                  </td>
                                  <td className="py-2.5 font-mono font-bold text-slate-700">{fmtMoney(c.balance)} s</td>
                                  <td className="py-2.5 text-right">
                                    <button
                                      onClick={() => { setSelectedCompany(c); setDetailInitialTab('packages'); }}
                                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-50 hover:bg-blue-50 text-slate-700 hover:text-blue-700 border border-slate-200/60 hover:border-blue-200 font-bold text-[10px] transition-all shadow-2xs"
                                    >
                                      <RefreshCw className="w-3 h-3" />
                                      Uzaytirish
                                    </button>
                                  </td>
                                </tr>
                              ))}
                              {atRiskList.length === 0 && (
                                <tr>
                                  <td colSpan={6} className="py-8 text-center text-slate-400">
                                    Hozirda xavf guruhidagi korxonalar yo'q. Barcha obunalar faol!
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── BILLING TAB ── */}
      {tab === 'billing' && <BillingTab />}

      {/* ── TARIFLAR TAB ── */}
      {tab === 'tariffs' && <TariffsTab />}

      {/* ── SETTINGS TAB ── */}
      {tab === 'settings' && <SettingsTab />}

      {/* ── BILDIRISH NOMALAR TAB ── */}
      {tab === 'announcements' && <AnnouncementsTab companies={companies} />}

      {/* Korxonani butunlay o'chirish */}
      {deleteCompany && (
        <DeleteCompanyModal
          company={deleteCompany}
          onClose={() => setDeleteCompany(null)}
          onDeleted={() => { setDeleteCompany(null); loadCompanies(); loadOverview(); }}
        />
      )}

      {/* Company Detail Modal */}
      {selectedCompany && (
        <CompanyDetailPanel
          companyId={selectedCompany.id}
          companyName={selectedCompany.name}
          initialTab={detailInitialTab}
          onClose={() => { setSelectedCompany(null); setDetailInitialTab('branches'); }}
        />
      )}
    </div>
  );
}

/* ─── BILLING TAB ───────────────────────────────────── */
const BILLING_PAGE_SIZE = 15;

function BillingTab() {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionModal, setActionModal] = useState(null); // { company, type: 'trial'|'subscribe'|'topup' }
  const [subForm, setSubForm] = useState({ tariff_id: '', months: 1 });
  const [topupForm, setTopupForm] = useState({ amount: '', note: '' });
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get('/billing/companies'),
      api.get('/billing/tariffs?all=true'),
    ]).then(([r1, r2]) => {
      setList(r1.data);
      setTariffs(r2.data);
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) }).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const activateTrial = async (c) => {
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${c.id}/activate-trial`);
      alert(r.data.message);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); setActionModal(null); }
  };

  const doTopUp = async () => {
    const amount = Number(topupForm.amount);
    if (!amount || amount <= 0) return alert(t('superAdmin.enterAmount'));
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${actionModal.company.id}/top-up`, {
        amount,
        note: topupForm.note || undefined,
      });
      alert(r.data.message);
      load();
      setActionModal(null);
    } catch (e) {
      alert(e.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); }
  };

  const activateSubscription = async () => {
    if (!subForm.tariff_id) return alert(t('superAdmin.selectTariffAlert'));
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${actionModal.company.id}/subscribe`, {
        tariff_id: Number(subForm.tariff_id),
        months: Number(subForm.months),
      });
      alert(r.data.message + `\n${t('superAdmin.chargedFromBalance')}: ${fmtMoney(r.data.charged)} ${t('common.sum')}`);
      load();
      setActionModal(null);
    } catch (e) {
      alert(e.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); }
  };

  const statusBadge = (c) => {
    if (!c.subscription_active) return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-600">{t('superAdmin.expired')}</span>;
    if (c.is_trial) return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700">{t('superAdmin.trial')} ({c.days_left}{t('superAdmin.dayShort')})</span>;
    return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700">{t('common.active')} ({c.days_left}{t('superAdmin.dayShort')})</span>;
  };

  const filtered = list.filter(c => {
    const q = search.toLowerCase();
    if (q && !c.name?.toLowerCase().includes(q) && !c.org_code?.toLowerCase().includes(q)) return false;
    if (dateFrom && c.created_at && c.created_at < dateFrom) return false;
    if (dateTo && c.created_at && c.created_at.slice(0, 10) > dateTo) return false;
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / BILLING_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * BILLING_PAGE_SIZE, safePage * BILLING_PAGE_SIZE);

  const handleSearch = (val) => { setSearch(val); setPage(1); };
  const handleDateFrom = (val) => { setDateFrom(val); setPage(1); };
  const handleDateTo = (val) => { setDateTo(val); setPage(1); };
  const handleClearFilters = () => { setSearch(''); setDateFrom(''); setDateTo(''); setPage(1); };

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-slate-800 flex items-center gap-2">
          <span className="w-7 h-7 bg-blue-100 rounded-lg flex items-center justify-center">
            <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-4 h-4 text-blue-600" />
          </span>
          {t('superAdmin.companiesBilling')}
          <span className="text-xs font-normal text-slate-400">({filtered.length}/{list.length})</span>
          {filtered.length > 0 && (
            <span className="text-xs font-normal text-slate-400 ml-1">
              — {t('superAdmin.pageOf', { page: safePage })}
            </span>
          )}
        </h3>
        <button onClick={load} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg font-semibold text-slate-600 transition-all">
          {t('common.refresh')}
        </button>
      </div>

      {/* Filter qatori */}
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder={t('superAdmin.companyNameOrCode')}
          value={search}
          onChange={e => handleSearch(e.target.value)}
          className="flex-1 min-w-[180px] text-sm border border-slate-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-blue-300 bg-white"
        />
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>{t('common.from')}:</span>
          <input type="date" value={dateFrom} onChange={e => handleDateFrom(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-300 bg-white" />
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>{t('common.to')}:</span>
          <input type="date" value={dateTo} onChange={e => handleDateTo(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-300 bg-white" />
        </div>
        {(search || dateFrom || dateTo) && (
          <button onClick={handleClearFilters}
            className="text-xs px-2.5 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg font-semibold border border-red-100 transition-all">
            {t('superAdmin.clear')}
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-100">
              <tr>
                {[t('superAdmin.companyLabel'), t('superAdmin.createdAt'), t('common.balance'), t('superAdmin.tariff'), t('superAdmin.subscriptionStatus'), t('superAdmin.endDate'), t('common.actions')].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {paginated.length === 0 && (
                <tr><td colSpan={7} className="text-center py-10 text-slate-400 text-sm">{t('superAdmin.nothingFound')}</td></tr>
              )}
              {paginated.map((c, idx) => (
                <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="text-xs text-slate-300 w-5 shrink-0">{(safePage - 1) * BILLING_PAGE_SIZE + idx + 1}</span>
                      <div>
                        <div className="font-semibold text-slate-800">{c.name}</div>
                        <div className="text-xs text-slate-400 font-mono">{c.org_code}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {c.created_at ? new Date(c.created_at).toLocaleDateString('uz-UZ') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-black text-sm ${c.balance < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                      {fmtMoney(c.balance)} s
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{c.tariff_name || '—'}</td>
                  <td className="px-4 py-3">{statusBadge(c)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {c.subscription_ends_at ? new Date(c.subscription_ends_at).toLocaleDateString('uz-UZ') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'trial' }); }}
                        className="text-xs px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-700 rounded-lg font-semibold border border-amber-100 transition-all"
                      >
                        {t('superAdmin.trial7Days')}
                      </button>
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'subscribe' }); setSubForm({ tariff_id: c.tariff_id || '', months: 1 }); }}
                        className="text-xs px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg font-semibold border border-blue-100 transition-all"
                      >
                        {t('superAdmin.subscription')}
                      </button>
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'topup' }); setTopupForm({ amount: '', note: '' }); }}
                        className="text-xs px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg font-semibold border border-emerald-100 transition-all"
                      >
                        + {t('superAdmin.money')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pagination Controls ── */}
      {!loading && filtered.length > BILLING_PAGE_SIZE && (
        <div className="px-5 py-3 border-t border-slate-100 flex items-center justify-between bg-white">
          <span className="text-sm text-slate-500">
            {t('superAdmin.ofCompanies', { count: filtered.length })}{' '}
            <span className="font-semibold text-slate-700">
              {(safePage - 1) * BILLING_PAGE_SIZE + 1}–{Math.min(safePage * BILLING_PAGE_SIZE, filtered.length)}
            </span>{' '}
            {t('common.shown')}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={safePage === 1}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors font-medium"
            >
              ‹ {t('common.prev')}
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .slice(
                Math.max(0, safePage - 3),
                Math.min(totalPages, safePage + 2)
              )
              .map(p => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-9 h-9 rounded-lg text-sm font-semibold transition-colors ${
                    p === safePage
                      ? 'bg-blue-600 text-white font-bold shadow-sm shadow-blue-200'
                      : 'border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {p}
                </button>
              ))}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors font-medium"
            >
              {t('common.next')} ›
            </button>
          </div>
        </div>
      )}

      {/* Action Modal */}
      {actionModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-slate-800">
                {actionModal.type === 'trial' ? t('superAdmin.trial7DaysFull') : actionModal.type === 'topup' ? t('superAdmin.topUpBalance') : t('superAdmin.activateSubscription')}
              </h3>
              <button onClick={() => setActionModal(null)} className="text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>

            <div className="bg-slate-50 rounded-xl p-3 mb-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-black text-sm">
                {actionModal.company.name?.[0]?.toUpperCase()}
              </div>
              <div>
                <div className="font-semibold text-slate-800 text-sm">{actionModal.company.name}</div>
                <div className="text-xs text-slate-400">{t('common.balance')}: <span className="font-bold text-emerald-700">{fmtMoney(actionModal.company.balance)} s</span></div>
              </div>
            </div>

            {actionModal.type === 'trial' ? (
              <div className="mb-5">
                <p className="text-sm text-slate-600">{t('superAdmin.trialGrantPrefix')} <span className="font-bold text-amber-600">{t('superAdmin.trial7DaysFree')}</span> {t('superAdmin.trialGrantSuffix')}</p>
              </div>
            ) : actionModal.type === 'topup' ? (
              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.amountSum')}</label>
                  <input
                    type="number" min="1" placeholder={t('superAdmin.amountPlaceholderExample')}
                    value={topupForm.amount}
                    onChange={e => setTopupForm(p => ({ ...p, amount: e.target.value }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.noteOptional')}</label>
                  <input
                    type="text" placeholder={t('superAdmin.paymentReasonPlaceholder')}
                    value={topupForm.note}
                    onChange={e => setTopupForm(p => ({ ...p, note: e.target.value }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.tariff')}</label>
                  <select value={subForm.tariff_id} onChange={e => setSubForm(p => ({ ...p, tariff_id: e.target.value }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                    <option value="">— {t('superAdmin.selectTariff')} —</option>
                    {tariffs.filter(t => t.price_per_month > 0).map(t => (
                      <option key={t.id} value={t.id}>{t.name} — {fmtMoney(t.price_per_month)} {t('superAdmin.sumPerMonth')}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.durationMonths')}</label>
                  <select value={subForm.months} onChange={e => setSubForm(p => ({ ...p, months: Number(e.target.value) }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                    {[1, 2, 3, 6, 12].map(m => <option key={m} value={m}>{m} {t('superAdmin.month')}</option>)}
                  </select>
                </div>
                {subForm.tariff_id && (
                  <div className="bg-blue-50 rounded-xl p-3 text-sm">
                    <span className="text-slate-500">{t('superAdmin.totalCharged')}: </span>
                    <span className="font-black text-blue-700">
                      {fmtMoney((tariffs.find(t => String(t.id) === String(subForm.tariff_id))?.price_per_month || 0) * subForm.months)} {t('common.sum')}
                    </span>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <button onClick={() => setActionModal(null)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm transition-all">{t('common.cancel')}</button>
              <button
                onClick={actionModal.type === 'trial' ? () => activateTrial(actionModal.company) : actionModal.type === 'topup' ? doTopUp : activateSubscription}
                disabled={saving}
                className={`flex-1 py-2.5 text-white font-bold rounded-xl text-sm transition-all disabled:opacity-50 ${actionModal.type === 'topup' ? 'bg-emerald-600 hover:bg-emerald-700 shadow-lg shadow-emerald-200' : 'bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-200'}`}
              >
                {saving ? t('common.saving') : actionModal.type === 'trial' ? t('superAdmin.giveTrial') : actionModal.type === 'topup' ? t('superAdmin.addBalance') : t('superAdmin.enableSubscription')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Settings Tab ───────────────────────────────── */
function SettingsTab() {
  const { t } = useLang();
  const FIELDS = [
    { key: 'card_number', label: t('superAdmin.cardNumberLabel'), placeholder: '8600 0000 0000 0000', icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z' },
    { key: 'card_owner', label: t('superAdmin.cardOwnerLabel'), placeholder: 'Abdualimov Eldorbek', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { key: 'tg_username', label: t('superAdmin.telegramUsernameLabel'), placeholder: 'eldorservices', icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z' },
    { key: 'phone', label: t('superAdmin.phoneDisplayLabel'), placeholder: '+998 88 911 81 71', icon: 'M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z' },
    { key: 'phone_raw', label: t('superAdmin.phoneRawLabel'), placeholder: '+998889118171', icon: 'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1' },
  ];

  const [saved, setSaved] = useState({});     // DB dagi haqiqiy qiymatlar
  const [draft, setDraft] = useState({});     // Modal ichidagi tahrir
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    api.get('/super-admin/platform-settings')
      .then(r => {
        const map = {};
        r.data.forEach(({ key, value }) => { map[key] = value || ''; });
        setSaved(map);
      })
      .catch(() => setError(t('superAdmin.settingsLoadError')))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const openEdit = () => { setDraft({ ...saved }); setSaveOk(false); setError(''); setEditOpen(true); };
  const closeEdit = () => setEditOpen(false);

  const handleSave = async () => {
    setSaving(true); setSaveOk(false); setError('');
    try {
      await api.put('/super-admin/platform-settings', { values: draft });
      setSaved({ ...draft });
      setSaveOk(true);
      setTimeout(() => { setSaveOk(false); setEditOpen(false); }, 1500);
    } catch {
      setError(t('superAdmin.saveError'));
    } finally { setSaving(false); }
  };

  return (
    <>
      {/* ── Read-only view ── */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 max-w-2xl">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-md shadow-blue-200">
              <Ic d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" cls="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-black text-slate-800">{t('superAdmin.platformSettings')}</h2>
              <p className="text-xs text-slate-400">{t('superAdmin.cardTelegramPhoneNumbers')}</p>
            </div>
          </div>
          <button
            onClick={openEdit}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-sm shadow-blue-200 transition-all"
          >
            <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-3.5 h-3.5" />
            {t('common.edit')}
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-10">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Karta preview */}
            <div className="bg-slate-900 rounded-2xl p-5 mb-4">
              <div className="text-slate-400 text-[10px] font-semibold uppercase tracking-widest mb-3">{t('superAdmin.paymentCard')}</div>
              <div className="text-white font-mono text-xl font-bold tracking-[0.2em] mb-1">
                {saved.card_number || '— — — —'}
              </div>
              <div className="text-slate-400 text-sm">{saved.card_owner || '—'}</div>
            </div>
            {/* Aloqa */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#eaf6fd] rounded-xl px-4 py-3">
                <div className="text-[10px] text-slate-400 font-semibold uppercase mb-1">Telegram</div>
                <div className="text-[#2AABEE] font-bold text-sm">@{saved.tg_username || '—'}</div>
              </div>
              <div className="bg-emerald-50 rounded-xl px-4 py-3">
                <div className="text-[10px] text-slate-400 font-semibold uppercase mb-1">{t('admin.dict.phone') || t('common.phone')}</div>
                <div className="text-emerald-700 font-bold text-sm">{saved.phone || '—'}</div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Edit Modal ── */}
      {editOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-black text-slate-800">{t('superAdmin.editSettings')}</h3>
              <button onClick={closeEdit} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>

            {/* Fields */}
            <div className="px-6 py-5 space-y-4 max-h-[60vh] overflow-y-auto">
              {FIELDS.map(f => (
                <div key={f.key}>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{f.label}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Ic d={f.icon} cls="w-4 h-4" />
                    </div>
                    {f.key === 'card_number' ? (
                      <input
                        value={draft[f.key] || ''}
                        onChange={e => {
                          const raw = e.target.value.replace(/\D/g, '').slice(0, 16);
                          const formatted = raw.replace(/(.{4})/g, '$1 ').trim();
                          setDraft(v => ({ ...v, card_number: formatted }));
                        }}
                        placeholder={f.placeholder}
                        maxLength={19}
                        inputMode="numeric"
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono tracking-widest"
                      />
                    ) : (
                      <input
                        value={draft[f.key] || ''}
                        onChange={e => setDraft(v => ({ ...v, [f.key]: e.target.value }))}
                        placeholder={f.placeholder}
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
                      />
                    )}
                  </div>
                </div>
              ))}
              {error && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{error}</div>}
              {saveOk && <div className="text-xs text-emerald-700 bg-emerald-50 px-4 py-2.5 rounded-xl border border-emerald-200 font-semibold">✓ {t('superAdmin.savedExclaim')}</div>}
            </div>

            {/* Footer */}
            <div className="px-6 pb-5 flex gap-3">
              <button onClick={closeEdit} className="flex-1 py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 font-semibold rounded-xl text-sm transition-all">
                {t('common.cancel')}
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-blue-200 text-sm transition-all">
                {saving ? t('common.saving') : `💾 ${t('common.save')}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
/* ─── TARIFLAR TAB ───────────────────────────────────── */
function TariffsTab() {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const unitTxt = tf('tariffs.unit', 'ta');
  const unlimitedTxt = tf('tariffs.limitUnlimited', 'Cheksiz');
  // Cheksiz qoidasi backend bilan bir xil: NULL yoki >= 9999
  const isUnl = (v) => v == null || v >= 9999;
  const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const defaultForm = {
    name: '',
    description: '',
    price_per_month: 0,
    duration_days: 30,
    max_users: 10,
    max_branches: 2,
    max_warehouses: 1,
    max_products: 0,
    max_agents: 0,
    max_couriers: 0,
    max_monthly_orders: 0,
    max_production_orders: 0,
    min_duration_months: 1,
    has_pnl_compare: false,
    has_manufacturing: false,
    has_distribution: false,
    sort_order: 0,
    bhm_percent: '',
  };
  const [form, setForm] = useState(defaultForm);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.get('/billing/tariffs?all=true').then(r => setTariffs(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const openNew = () => {
    setEditItem(null);
    setForm(defaultForm);
    setShowForm(true);
  };

  const openEdit = (tariff) => {
    setEditItem(tariff);
    setForm({
      name: tariff.name || '',
      description: tariff.description || '',
      price_per_month: tariff.price_per_month || 0,
      duration_days: tariff.duration_days || 30,
      max_users: tariff.max_users ?? 10,
      max_branches: tariff.max_branches ?? 2,
      max_warehouses: tariff.max_warehouses ?? 1,
      max_products: tariff.max_products ?? 0,
      max_agents: tariff.max_agents ?? 0,
      max_couriers: tariff.max_couriers ?? 0,
      max_monthly_orders: tariff.max_monthly_orders ?? 0,
      max_production_orders: tariff.max_production_orders ?? 0,
      min_duration_months: tariff.min_duration_months ?? 1,
      has_pnl_compare: !!tariff.has_pnl_compare,
      has_manufacturing: !!tariff.has_manufacturing,
      has_distribution: !!tariff.has_distribution,
      sort_order: tariff.sort_order ?? 0,
      bhm_percent: tariff.bhm_percent ?? '',
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.name.trim()) return alert(t('superAdmin.enterTariffName'));
    setSaving(true);
    try {
      if (editItem) {
        await api.put(`/billing/tariffs/${editItem.id}`, form);
      } else {
        await api.post('/billing/tariffs', form);
      }
      load();
      setShowForm(false);
    } catch (e) {
      alert(e.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); }
  };

  const deactivate = async (id) => {
    if (!confirm(t('superAdmin.confirmDeleteTariff'))) return;
    await api.delete(`/billing/tariffs/${id}`).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('superAdmin.errorOccurred')) });
    load();
  };

  const inp = "w-full border border-slate-200 rounded-xl px-3 py-2 text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-300";

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-slate-800 flex items-center gap-2">
            <span className="w-7 h-7 bg-blue-100 rounded-lg flex items-center justify-center">
              <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-4 h-4 text-blue-600" />
            </span>
            {t('superAdmin.tariffs')}
          </h3>
          <button onClick={openNew} className="text-xs px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold transition-all flex items-center gap-1.5 cursor-pointer">
            <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" /> {t('superAdmin.newTariff')}
          </button>
        </div>
        {loading ? (
          <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
            {tariffs.map(tariff => {
              const nameLower = (tariff.name || '').toLowerCase();
              let tierBadge = 'Distribyutor Start';
              let badgeCls = 'bg-sky-600 text-white shadow-xs';
              let borderCls = 'border-sky-200 hover:border-sky-400 hover:shadow-xl hover:shadow-sky-500/10';
              let bgCls = 'bg-white';
              let priceColor = 'text-sky-700';
              let iconBg = 'bg-sky-50 text-sky-600 border border-sky-200';
              let accentBar = 'from-sky-500 via-blue-500 to-sky-600';
              let IconComp = Zap;

              if (nameLower.includes('mini')) {
                tierBadge = "Kichik Do'kon";
                badgeCls = 'bg-emerald-600 text-white shadow-xs';
                borderCls = 'border-emerald-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10';
                bgCls = 'bg-white';
                priceColor = 'text-emerald-700';
                iconBg = 'bg-emerald-50 text-emerald-600 border border-emerald-200';
                accentBar = 'from-emerald-500 via-teal-500 to-emerald-600';
                IconComp = Store;
              } else if (nameLower.includes('pro')) {
                tierBadge = 'Distribyutor Pro (VIP)';
                badgeCls = 'bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-xs';
                borderCls = 'border-violet-200 hover:border-violet-400 hover:shadow-xl hover:shadow-violet-500/10';
                bgCls = 'bg-white';
                priceColor = 'text-violet-700';
                iconBg = 'bg-violet-50 text-violet-600 border border-violet-200';
                accentBar = 'from-violet-600 via-purple-600 to-indigo-600';
                IconComp = Crown;
              } else if (nameLower.includes('standart')) {
                tierBadge = 'Distribyutor Standart';
                badgeCls = 'bg-blue-600 text-white shadow-md shadow-blue-500/30';
                borderCls = 'border-blue-400 ring-2 ring-blue-500/30 hover:border-blue-600 hover:shadow-xl hover:shadow-blue-500/15';
                bgCls = 'bg-gradient-to-br from-blue-50/40 via-white to-indigo-50/30';
                priceColor = 'text-blue-700';
                iconBg = 'bg-blue-50 text-blue-600 border border-blue-200';
                accentBar = 'from-blue-600 via-indigo-600 to-blue-500';
                IconComp = Sparkles;
              }

              return (
                <div key={tariff.id} className={`rounded-3xl border-2 overflow-hidden flex flex-col justify-between transition-all duration-300 shadow-sm ${bgCls} ${borderCls}`}>
                  {/* Yuqori accent chiziq */}
                  <div className={`h-1.5 w-full bg-gradient-to-r ${accentBar}`} />

                  <div className="p-6 flex-1 flex flex-col justify-between">
                    <div>
                      {/* Top Header & Price */}
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-4 border-b border-slate-100">
                        <div className="flex items-start gap-3.5">
                          <div className={`w-12 h-12 rounded-2xl ${iconBg} flex items-center justify-center shadow-xs shrink-0`}>
                            <IconComp size={24} />
                          </div>
                          <div>
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="font-black text-slate-900 text-xl tracking-tight">{tariff.name}</h4>
                              <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-black uppercase tracking-wider ${badgeCls}`}>
                                {tierBadge}
                              </span>
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${tariff.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                {tariff.is_active ? t('common.active') : t('common.inactive')}
                              </span>
                            </div>
                            {tariff.description && (
                              <p className="text-xs text-slate-500 mt-1 leading-relaxed max-w-sm">{tariff.description}</p>
                            )}
                          </div>
                        </div>

                        {/* Price */}
                        <div className="sm:text-right shrink-0 bg-slate-50/80 sm:bg-transparent p-3 sm:p-0 rounded-2xl">
                          <div className="flex items-baseline sm:justify-end gap-1">
                            <span className="text-2xl sm:text-3xl font-black text-slate-900">
                              {tariff.price_per_month === 0 ? t('superAdmin.free') : `${fmtMoney(tariff.price_per_month)} s`}
                            </span>
                            {tariff.price_per_month > 0 && <span className="text-xs font-bold text-slate-400">/{t('superAdmin.month')}</span>}
                          </div>
                          <div className="text-[11px] font-semibold text-slate-500 mt-1 flex items-center sm:justify-end gap-2">
                            <span>⏱ {tariff.duration_days} kun</span>
                            {tariff.min_duration_months > 1 && (
                              <span className="text-blue-700 font-bold bg-blue-50 px-2 py-0.5 rounded-md">Min: {tariff.min_duration_months} oy</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* 2-Column Limits & Modules Specs Grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-5">
                        {/* Chap ustun: Resurs kvotalari */}
                        <div className="bg-slate-50/70 border border-slate-100 rounded-2xl p-3.5 space-y-2">
                          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                            {tf('tariffs.resourceLimits', 'Resurs limitlari')}
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Package size={15} className="text-amber-600 shrink-0" />
                              {tf('tariffs.productLimit', 'Tovar limiti:')}
                            </span>
                            <span className="font-black text-slate-900">
                              {tariff.max_products > 0 ? `${tariff.max_products.toLocaleString('uz-UZ')} ${unitTxt}` : unlimitedTxt}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Warehouse size={15} className="text-blue-600 shrink-0" />
                              {tf('tariffs.warehouseLimit', 'Omborlar:')}
                            </span>
                            <span className="font-black text-slate-900">
                              {tariff.max_warehouses && tariff.max_warehouses < 9999 ? `${tariff.max_warehouses} ${unitTxt}` : unlimitedTxt}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Users size={15} className="text-indigo-600 shrink-0" />
                              {tf('tariffs.userLimit', 'Xodimlar:')}
                            </span>
                            <span className="font-black text-slate-900">
                              {isUnl(tariff.max_users) ? unlimitedTxt : `${tariff.max_users} ${unitTxt}`}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Building2 size={15} className="text-slate-600 shrink-0" />
                              {tf('tariffs.branchLimit', 'Filiallar:')}
                            </span>
                            <span className="font-black text-slate-900">
                              {isUnl(tariff.max_branches) ? unlimitedTxt : `${tariff.max_branches} ${unitTxt}`}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Bike size={15} className="text-violet-600 shrink-0" />
                              {tf('tariffs.agentLimit', 'Savdo agentlari:')}
                            </span>
                            {/* T3.9: max_agents == null va tarifda tarqatish bo'lsa — cheksiz (Tariflar.jsx bilan bir xil) */}
                            <span className="font-black text-blue-700">
                              {tariff.max_agents > 0 ? `${tariff.max_agents} ${unitTxt}` : (tariff.max_agents == null && tariff.has_distribution ? unlimitedTxt : `0 ${unitTxt}`)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-slate-600 font-medium">
                              <Truck size={15} className="text-sky-600 shrink-0" />
                              {tf('tariffs.courierLimit', 'Kuryerlar:')}
                            </span>
                            <span className="font-black text-blue-700">
                              {tariff.max_couriers > 0 ? `${tariff.max_couriers} ${unitTxt}` : (tariff.max_couriers == null && tariff.has_distribution ? unlimitedTxt : `0 ${unitTxt}`)}
                            </span>
                          </div>
                        </div>

                        {/* O'ng ustun: Modullar */}
                        <div className="bg-slate-50/70 border border-slate-100 rounded-2xl p-3.5 space-y-2 flex flex-col justify-between">
                          <div>
                            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                              {tf('tariffs.systemModules', 'Tizim modullari')}
                            </div>
                            <div className="flex items-center justify-between text-xs py-1">
                              <span className="flex items-center gap-2 text-slate-600 font-medium">
                                <BarChart3 size={15} className="text-blue-600 shrink-0" />
                                {tf('tariffs.module.pnlCompare', 'P&L 2 davr solishtirish:')}
                              </span>
                              <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                                tariff.has_pnl_compare ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                              }`}>
                                {tariff.has_pnl_compare ? <><Check size={12} /> {tf('tariffs.has', 'Bor')}</> : <><X size={12} /> {tf('tariffs.hasNot', "Yo'q")}</>}
                              </span>
                            </div>
                            <div className="flex items-center justify-between text-xs py-1">
                              <span className="flex items-center gap-2 text-slate-600 font-medium">
                                <Factory size={15} className="text-amber-600 shrink-0" />
                                {tf('tariffs.module.manufacturing', 'Ishlab chiqarish:')}
                              </span>
                              <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                                tariff.has_manufacturing ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                              }`}>
                                {tariff.has_manufacturing ? <><Check size={12} /> {tf('tariffs.has', 'Bor')}</> : <><X size={12} /> {tf('tariffs.hasNot', "Yo'q")}</>}
                              </span>
                            </div>
                            <div className="flex items-center justify-between text-xs py-1">
                              <span className="flex items-center gap-2 text-slate-600 font-medium">
                                <Share2 size={15} className="text-purple-600 shrink-0" />
                                {tf('tariffs.module.distribution', 'Distribyutsiya:')}
                              </span>
                              <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                                tariff.has_distribution ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                              }`}>
                                {tariff.has_distribution ? <><Check size={12} /> {tf('tariffs.has', 'Bor')}</> : <><X size={12} /> {tf('tariffs.hasNot', "Yo'q")}</>}
                              </span>
                            </div>
                          </div>

                          {tariff.bhm_percent != null && tariff.price_per_month > 0 && (
                            <div className="pt-2 border-t border-dashed border-slate-200">
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 border border-blue-100 rounded-lg text-[11px] text-blue-700 font-semibold">
                                BHM ulushi: <span className="font-black">{tariff.bhm_percent}%</span>
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Boshqaruv tugmalari */}
                    <div className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-100">
                      <button onClick={() => openEdit(tariff)} className="py-2.5 px-4 text-xs font-bold bg-white hover:bg-blue-600 hover:text-white text-slate-700 border border-slate-200 hover:border-blue-600 rounded-xl transition-all shadow-2xs cursor-pointer flex items-center justify-center gap-2">
                        <Pencil size={14} />
                        {t('common.edit')}
                      </button>
                      <button onClick={() => deactivate(tariff.id)} className="py-2.5 px-4 text-xs font-bold bg-white hover:bg-red-600 hover:text-white text-red-600 border border-red-200 hover:border-red-600 rounded-xl transition-all shadow-2xs cursor-pointer flex items-center justify-center gap-2">
                        <Trash2 size={14} />
                        {t('common.delete')}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
            {tariffs.length === 0 && (
              <div className="col-span-full py-14 text-center text-slate-400 text-sm font-semibold">
                {t('superAdmin.noTariffsYet')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tarif Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-800 text-lg">{editItem ? t('superAdmin.editTariff') : t('superAdmin.newTariff')}</h3>
              <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600 cursor-pointer"><Ic d="M6 18L18 6M6 6l12 12" /></button>
            </div>
            <div className="space-y-4">
              {/* Asosiy */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.nameLabel')} *</label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className={inp} placeholder={t('superAdmin.tariffNamePlaceholder')} />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.descriptionLabel')}</label>
                  <input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} className={inp} placeholder={t('superAdmin.shortDescriptionPlaceholder')} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.priceSumPerMonth')}</label>
                  <input type="number" value={form.price_per_month} onChange={e => setForm(p => ({ ...p, price_per_month: Number(e.target.value) }))} className={inp} min="0" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.durationDays')}</label>
                  <input type="number" value={form.duration_days} onChange={e => setForm(p => ({ ...p, duration_days: Number(e.target.value) }))} className={inp} min="1" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.bhmPercentLabel')}</label>
                  <input type="number" value={form.bhm_percent} onChange={e => setForm(p => ({ ...p, bhm_percent: e.target.value === '' ? '' : Number(e.target.value) }))} className={inp} min="0" step="0.1" placeholder={t('superAdmin.bhmPercentPlaceholder')} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-600 mb-1">{t('superAdmin.minDurationMonths')}</label>
                  <input type="number" value={form.min_duration_months} onChange={e => setForm(p => ({ ...p, min_duration_months: Math.max(1, Number(e.target.value)) }))} className={inp} min="1" max="24" />
                </div>
              </div>

              {/* Cheklovlar va kvotalar */}
              <div className="border-t border-slate-100 pt-3">
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-400 mb-2.5">
                  {t('superAdmin.limitsAndQuotas')}
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxEmployees')}</label>
                    <input type="number" value={form.max_users} onChange={e => setForm(p => ({ ...p, max_users: Number(e.target.value) }))} className={inp} min="1" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxBranches')}</label>
                    <input type="number" value={form.max_branches} onChange={e => setForm(p => ({ ...p, max_branches: Number(e.target.value) }))} className={inp} min="1" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxWarehouses')}</label>
                    <input type="number" value={form.max_warehouses} onChange={e => setForm(p => ({ ...p, max_warehouses: Number(e.target.value) }))} className={inp} min="1" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxProducts')}</label>
                    <input type="number" value={form.max_products} onChange={e => setForm(p => ({ ...p, max_products: Number(e.target.value) }))} className={inp} min="0" placeholder="0 = cheksiz" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxAgents')}</label>
                    <input type="number" value={form.max_agents} onChange={e => setForm(p => ({ ...p, max_agents: Number(e.target.value) }))} className={inp} min="0" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxCouriers')}</label>
                    <input type="number" value={form.max_couriers} onChange={e => setForm(p => ({ ...p, max_couriers: Number(e.target.value) }))} className={inp} min="0" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxMonthlyOrders')}</label>
                    <input type="number" value={form.max_monthly_orders} onChange={e => setForm(p => ({ ...p, max_monthly_orders: Number(e.target.value) }))} className={inp} min="0" />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-500 mb-1">{t('superAdmin.maxProductionOrders')}</label>
                    <input type="number" value={form.max_production_orders} onChange={e => setForm(p => ({ ...p, max_production_orders: Number(e.target.value) }))} className={inp} min="0" />
                  </div>
                </div>
              </div>

              {/* Modullar va imkoniyatlar */}
              <div className="border-t border-slate-100 pt-3">
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-400 mb-2.5">
                  {t('superAdmin.featuresTitle')}
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  <label className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.has_pnl_compare}
                      onChange={e => setForm(p => ({ ...p, has_pnl_compare: e.target.checked }))}
                      className="w-4 h-4 text-blue-600 rounded"
                    />
                    <span className="text-xs font-bold text-slate-700">{t('superAdmin.hasPnlCompare')}</span>
                  </label>
                  <label className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.has_manufacturing}
                      onChange={e => setForm(p => ({ ...p, has_manufacturing: e.target.checked }))}
                      className="w-4 h-4 text-amber-600 rounded"
                    />
                    <span className="text-xs font-bold text-slate-700">{t('superAdmin.hasManufacturing')}</span>
                  </label>
                  <label className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.has_distribution}
                      onChange={e => setForm(p => ({ ...p, has_distribution: e.target.checked }))}
                      className="w-4 h-4 text-purple-600 rounded"
                    />
                    <span className="text-xs font-bold text-slate-700">{t('superAdmin.hasDistribution')}</span>
                  </label>
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5 border-t border-slate-100 pt-4">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm transition-all cursor-pointer">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-sm shadow-lg shadow-blue-200 transition-all disabled:opacity-50 cursor-pointer">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── ANNOUNCEMENTS TAB ────────────────────────────── */
function AnnouncementsTab({ companies }) {
  const { t } = useLang();
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ title: '', message: '', company_id: '', expires_at: '' });
  const [questions, setQuestions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [editId, setEditId] = useState(null);

  // Results view
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [resultsData, setResultsData] = useState(null);
  const [resultsLoading, setResultsLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.get('/super-admin/announcements')
      .then(r => setAnnouncements(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('superAdmin.announcementsLoadError')))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const openModal = (ann = null) => {
    if (ann && ann.id) {
      setEditId(ann.id);
      setForm({
        title: ann.title || '',
        message: ann.message || '',
        company_id: ann.company_id || '',
        expires_at: ann.expires_at ? ann.expires_at.slice(0, 16) : ''
      });
      setQuestions([]);
    } else {
      setEditId(null);
      setForm({ title: '', message: '', company_id: '', expires_at: '' });
      setQuestions([]);
    }
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditId(null);
  };

  const save = async () => {
    if (!form.title.trim() || !form.message.trim()) return toast.error(t('superAdmin.titleAndTextRequired'));
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        message: form.message.trim(),
        company_id: form.company_id ? Number(form.company_id) : null,
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null
      };

      if (!editId && questions.length > 0) {
        payload.questions = questions.map(q => ({
          text: q.text,
          question_type: q.question_type,
          options: q.options ? q.options.filter(o => o.trim()) : null
        }));
      }

      if (editId) {
        await api.patch(`/super-admin/announcements/${editId}`, payload);
        toast.success(t('superAdmin.edited'));
      } else {
        await api.post('/super-admin/announcements', payload);
        toast.success(t('superAdmin.created'));
      }
      closeModal();
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('superAdmin.errorOccurred'));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (ann) => {
    try {
      await api.patch(`/super-admin/announcements/${ann.id}`, { is_active: !ann.is_active });
      load();
    } catch (e) {
      toast.error(t('superAdmin.statusChangeError'));
    }
  };

  const deleteAnn = async (id) => {
    if (!window.confirm(t('superAdmin.confirmDelete'))) return;
    try {
      await api.delete(`/super-admin/announcements/${id}`);
      toast.success(t('superAdmin.deleted'));
      load();
    } catch (e) {
      toast.error(t('common.error'));
    }
  };

  const openResults = async (id) => {
    setShowResultsModal(true);
    setResultsLoading(true);
    setResultsData(null);
    try {
      const r = await api.get(`/super-admin/announcements/${id}/survey-results`);
      setResultsData(r.data);
    } catch (e) {
      toast.error(t('superAdmin.resultsLoadError'));
      setShowResultsModal(false);
    } finally {
      setResultsLoading(false);
    }
  };

  const inp = "w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 transition-all bg-slate-50 focus:bg-white";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-slate-800">{t('superAdmin.announcements')}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{t('superAdmin.announcementsHint')}</p>
        </div>
        <button onClick={() => openModal()} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-all flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
          {t('superAdmin.createNew')}
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 flex justify-center"><div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : announcements.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">{t('superAdmin.noAnnouncementsYet')}</div>
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['#', t('superAdmin.titleLabel'), t('superAdmin.recipients'), t('common.status'), t('superAdmin.deadline'), t('common.created'), t('common.actions')].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {announcements.map((a, i) => (
                <tr key={a.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-5 py-3 text-xs text-slate-400">{i + 1}</td>
                  <td className="px-5 py-3 font-semibold text-slate-800">{a.title}</td>
                  <td className="px-5 py-3">
                    {a.company_id ? (
                      <span className="text-blue-700 font-semibold bg-blue-50 px-2 py-0.5 rounded text-xs">{a.company_name || t('superAdmin.oneCompany')}</span>
                    ) : (
                      <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded text-xs">{t('superAdmin.everyone')}</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <button onClick={() => toggleActive(a)} className={`px-2.5 py-1 text-xs font-bold rounded-full ${a.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                      {a.is_active ? t('common.active') : t('common.inactive')}
                    </button>
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500">
                    {a.expires_at ? new Date(a.expires_at).toLocaleString('uz-UZ') : t('superAdmin.noDeadline')}
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-400">
                    {new Date(a.created_at).toLocaleDateString('uz-UZ')}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex gap-2">
                      {a.has_survey && (
                        <button onClick={() => openResults(a.id)} className="text-blue-500 hover:text-blue-600 font-medium text-xs px-2 py-1 bg-blue-50 rounded-lg">{t('superAdmin.results')}</button>
                      )}
                      <button onClick={() => openModal(a)} className="text-amber-500 hover:text-amber-600 font-medium text-xs px-2 py-1 bg-amber-50 rounded-lg">{t('common.edit')}</button>
                      <button onClick={() => deleteAnn(a.id)} className="text-red-500 hover:text-red-600 font-medium text-xs px-2 py-1 bg-red-50 rounded-lg">{t('common.delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <h3 className="font-bold text-slate-800">{editId ? t('common.edit') : t('superAdmin.newAnnouncement')}</h3>
              <button onClick={closeModal} className="text-slate-400 hover:text-slate-600"><svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.titleLabel')} *</label>
                <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} className={inp} placeholder={t('superAdmin.mainTitlePlaceholder')} autoFocus />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.textLabel')} *</label>
                <textarea value={form.message} onChange={e => setForm(p => ({ ...p, message: e.target.value }))} className={`${inp} min-h-[100px] resize-y`} placeholder={t('superAdmin.detailedTextPlaceholder')} />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.whoReceivesLabel')}</label>
                <select value={form.company_id} onChange={e => setForm(p => ({ ...p, company_id: e.target.value }))} className={inp}>
                  <option value="">{t('superAdmin.allCompaniesGlobal')}</option>
                  {companies.map(c => (
                    <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1.5">{t('superAdmin.expiryDateOptional')}</label>
                <input type="datetime-local" value={form.expires_at} onChange={e => setForm(p => ({ ...p, expires_at: e.target.value }))} className={inp} />
                <p className="text-xs text-slate-400 mt-1">{t('superAdmin.autoHideHint')}</p>
              </div>

              {!editId && (
                <div className="border-t border-slate-100 pt-4 mt-2">
                  <div className="flex items-center justify-between mb-3">
                    <label className="block text-xs font-bold text-slate-500">{t('superAdmin.surveyQuestionsOptional')}</label>
                    <button
                      onClick={() => setQuestions([...questions, { text: '', question_type: 'text', options: ['', ''] }])}
                      className="text-xs text-blue-600 font-bold bg-blue-50 px-2 py-1 rounded-lg hover:bg-blue-100 transition-all"
                    >
                      + {t('superAdmin.addQuestion')}
                    </button>
                  </div>
                  
                  {questions.length > 0 ? (
                    <div className="space-y-4 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                      {questions.map((q, qIndex) => (
                        <div key={qIndex} className="p-3 bg-slate-50 rounded-xl border border-slate-100 relative">
                          <button 
                            onClick={() => setQuestions(questions.filter((_, i) => i !== qIndex))}
                            className="absolute top-2 right-2 w-6 h-6 flex items-center justify-center bg-white rounded-md text-red-500 hover:bg-red-50 shadow-sm transition-all"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                          </button>
                          
                          <div className="mb-2 pr-8">
                            <input 
                              placeholder={t('superAdmin.questionTextPlaceholder')}
                              value={q.text} 
                              onChange={(e) => {
                                const nq = [...questions];
                                nq[qIndex].text = e.target.value;
                                setQuestions(nq);
                              }}
                              className="w-full text-sm font-semibold bg-transparent border-b border-slate-200 pb-1 focus:outline-none focus:border-blue-400"
                            />
                          </div>
                          <div className="flex gap-2 mb-2">
                            <select 
                              value={q.question_type}
                              onChange={(e) => {
                                const nq = [...questions];
                                nq[qIndex].question_type = e.target.value;
                                setQuestions(nq);
                              }}
                              className="text-xs bg-white border border-slate-200 rounded px-2 py-1 outline-none focus:border-blue-300"
                            >
                              <option value="text">{t('superAdmin.textAnswer')}</option>
                              <option value="single_choice">{t('superAdmin.singleChoice')}</option>
                              <option value="multiple_choice">{t('superAdmin.multipleChoice')}</option>
                            </select>
                          </div>
                          
                          {['single_choice', 'multiple_choice'].includes(q.question_type) && (
                            <div className="space-y-1.5 mt-2">
                              {q.options.map((opt, oIndex) => (
                                <div key={oIndex} className="flex gap-1.5 items-center">
                                  <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
                                  <input 
                                    placeholder={t('superAdmin.optionPlaceholder')}
                                    value={opt}
                                    onChange={(e) => {
                                      const nq = [...questions];
                                      nq[qIndex].options[oIndex] = e.target.value;
                                      setQuestions(nq);
                                    }}
                                    className="flex-1 text-xs bg-white border border-slate-200 rounded px-2 py-1 outline-none focus:border-blue-300"
                                  />
                                  {q.options.length > 2 && (
                                    <button 
                                      onClick={() => {
                                        const nq = [...questions];
                                        nq[qIndex].options = nq[qIndex].options.filter((_, i) => i !== oIndex);
                                        setQuestions(nq);
                                      }}
                                      className="text-slate-400 hover:text-red-500 transition-colors"
                                    >
                                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                                    </button>
                                  )}
                                </div>
                              ))}
                              <button 
                                onClick={() => {
                                  const nq = [...questions];
                                  nq[qIndex].options.push('');
                                  setQuestions(nq);
                                }}
                                className="text-[10px] text-blue-500 font-bold px-2 py-1 hover:bg-blue-50 rounded mt-1 transition-colors"
                              >
                                + {t('superAdmin.addOption')}
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-6 bg-slate-50 rounded-xl border border-slate-100 border-dashed text-slate-400 text-sm">
                      {t('superAdmin.noSurveyQuestionsYet')}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-2 shrink-0">
              <button onClick={closeModal} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm transition-all">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-sm shadow-lg shadow-blue-200 transition-all disabled:opacity-50">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results Modal */}
      {showResultsModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50 rounded-t-2xl">
              <h3 className="font-bold text-slate-800 flex items-center gap-2">
                <span className="w-8 h-8 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                </span>
                {t('superAdmin.surveyResults')}
              </h3>
              <button onClick={() => setShowResultsModal(false)} className="text-slate-400 hover:text-slate-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              {resultsLoading ? (
                <div className="py-16 flex justify-center"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
              ) : !resultsData ? (
                <div className="py-16 text-center text-slate-400">{t('common.noData')}</div>
              ) : (
                <div className="space-y-6">
                  {resultsData.results && resultsData.results.map((q) => {
                    const totalAnswers = q.answers ? q.answers.length : 0;
                    
                    let optionCounts = {};
                    if (q.options) {
                      q.options.forEach(opt => optionCounts[opt] = 0);
                    }
                    if (q.type !== 'text' && q.answers) {
                      q.answers.forEach(ans => {
                        let val = ans.answer;
                        if (typeof val === 'string' && val.startsWith('[') && val.endsWith(']')) {
                          try { val = JSON.parse(val); } catch (e) {}
                        }
                        let arr = Array.isArray(val) ? val : [val];
                        arr.forEach(v => {
                          if (optionCounts[v] !== undefined) optionCounts[v]++;
                          else optionCounts[v] = 1;
                        });
                      });
                    }

                    return (
                      <div key={q.question_id} className="border border-slate-100 rounded-xl overflow-hidden">
                        <div className="bg-slate-50 px-4 py-3 border-b border-slate-100">
                          <h4 className="font-bold text-slate-700 text-sm">{q.text}</h4>
                          <span className="text-[10px] uppercase font-bold text-slate-400 mt-1 block">
                            {q.type === 'text' ? t('superAdmin.textType') : q.type === 'single_choice' ? t('superAdmin.singleChoiceType') : t('superAdmin.multipleChoiceType')} ({t('superAdmin.answersCount', { count: totalAnswers })})
                          </span>
                        </div>
                        <div className="p-4 bg-white">
                          {q.type === 'text' ? (
                            <div className="space-y-2 max-h-[200px] overflow-y-auto custom-scrollbar pr-2">
                              {q.answers && q.answers.length > 0 ? (
                                q.answers.map((ans, idx) => (
                                  <div key={idx} className="text-sm text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                                    <div className="flex justify-between items-center mb-1">
                                      <span className="font-semibold text-xs text-slate-700">{ans.company_name} - {ans.user_name}</span>
                                      <span className="text-[10px] text-slate-400">{ans.date ? new Date(ans.date).toLocaleString('ru-RU', { hour: '2-digit', minute:'2-digit', day:'2-digit', month:'2-digit', year:'numeric' }) : ''}</span>
                                    </div>
                                    <div>{ans.answer}</div>
                                  </div>
                                ))
                              ) : (
                                <div className="text-xs text-slate-400 text-center py-2">{t('superAdmin.noAnswers')}</div>
                              )}
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {q.options && q.options.map((opt, idx) => {
                                const count = optionCounts[opt] || 0;
                                const percent = totalAnswers > 0 ? Math.round((count / totalAnswers) * 100) : 0;
                                return (
                                  <div key={idx} className="space-y-1">
                                    <div className="flex justify-between text-xs font-semibold text-slate-600">
                                      <span>{opt}</span>
                                      <span>{count} {t('common.item')} ({percent}%)</span>
                                    </div>
                                    <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                                      <div 
                                        className="h-full bg-blue-500 rounded-full transition-all duration-500" 
                                        style={{ width: `${percent}%` }}
                                      ></div>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
