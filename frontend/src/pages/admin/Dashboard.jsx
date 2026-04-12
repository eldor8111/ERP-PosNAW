import { useState, useEffect } from 'react';
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Line, ComposedChart, ReferenceLine,
} from 'recharts';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

const fmt = (val) => {
  if (!val) return "0 so'm";
  const n = Number(val);
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + " mlrd";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + " mln";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + " K";
  return n.toLocaleString('uz-UZ') + " so'm";
};

const fmtFull = (val) => {
  if (!val) return "0 so'm";
  return Number(val).toLocaleString('uz-UZ') + " so'm";
};

function KpiCard({ label, value, sub, icon, gradient, iconBg, badge }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl p-6 text-white ${gradient}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white/70">{label}</p>
          <p className="mt-2 text-2xl font-bold truncate">{value}</p>
          {sub && <p className="mt-1 text-sm text-white/60">{sub}</p>}
        </div>
        <div className="flex flex-col items-end gap-2 ml-3">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${iconBg}`}>
            {icon}
          </div>
          {badge != null && (
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
              badge > 0 ? 'bg-white/20 text-white' : badge < 0 ? 'bg-red-500/30 text-white' : 'bg-white/10 text-white/60'
            }`}>
              {badge > 0 ? `+${badge}%` : badge < 0 ? `${badge}%` : '—'}
            </span>
          )}
        </div>
      </div>
      <div className="absolute -bottom-4 -right-4 w-24 h-24 rounded-full bg-white/10" />
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  const { t } = useLang();
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 shadow-xl">
      <p className="text-slate-400 text-xs mb-1">{label}</p>
      <p className="text-white text-sm font-semibold">{fmtFull(payload[0]?.value)}</p>
      {payload[1] && <p className="text-slate-300 text-xs mt-0.5">{payload[1]?.value} {t('dashboard.salesCount')}</p>}
    </div>
  );
};

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [warehouses, setWarehouses] = useState([]);
  const [branches, setBranches] = useState([]);
  const [warehouseId, setWarehouseId] = useState(() => {
    const saved = localStorage.getItem('dashboard_warehouse_id');
    return saved ? Number(saved) : '';
  });
  const [branchId, setBranchId] = useState(() => {
    const saved = localStorage.getItem('dashboard_branch_id');
    return saved ? Number(saved) : '';
  });

  useEffect(() => {
    if (user?.role !== 'super_admin') {
      api.get('/warehouses').then(r => setWarehouses(r.data)).catch(() => {});
      api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch(() => {});
    }
  }, [user]);

  const load = (showSpinner = false) => {
    if (user?.role === 'super_admin') return;
    if (showSpinner) setLoading(true);
    setError(null);
    const params = {};
    if (warehouseId) params.warehouse_id = warehouseId;
    if (branchId) params.branch_id = branchId;
    api.get('/reports/dashboard', { params })
      .then(res => { setData(res.data); setError(null); })
      .catch(err => {
        const msg = err?.response?.data?.detail || err?.message || "Noma'lum xato";
        setError(msg);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(true);
    const interval = setInterval(() => load(false), 120_000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseId, branchId]);

  const handleWarehouseChange = (e) => {
    const val = e.target.value;
    setWarehouseId(val ? Number(val) : '');
    if (val) localStorage.setItem('dashboard_warehouse_id', val);
    else localStorage.removeItem('dashboard_warehouse_id');
  };

  const handleBranchChange = (e) => {
    const val = e.target.value;
    setBranchId(val ? Number(val) : '');
    if (val) localStorage.setItem('dashboard_branch_id', val);
    else localStorage.removeItem('dashboard_branch_id');
  };

  // super_admin uchun — dashboard ko'rsatilmaydi, to'g'ridan-to'g'ri redirect
  if (user?.role === 'super_admin') {
    return <Navigate to="/admin/super-admin" replace />;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-14 h-14 border-4 border-indigo-100 rounded-full" />
            <div className="absolute inset-0 w-14 h-14 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-slate-500 text-sm font-medium">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center bg-white rounded-2xl p-8 shadow-sm border border-slate-100 max-w-sm">
          <div className="w-14 h-14 bg-rose-50 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-slate-700 font-semibold text-lg">{t('dashboard.errorTitle')}</p>
          <p className="text-slate-400 text-sm mt-1 mb-5">{t('dashboard.errorDesc')}</p>
          <button onClick={load} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors shadow-lg shadow-indigo-200">
            {t('common.refresh')}
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;
  const kpis = [
    {
      label: t('dashboard.todaySales'),
      value: fmt(data.today?.sales),
      sub: `${data.today?.orders ?? 0} ${t('common.item')} ${t('sale.title').toLowerCase()}`,
      badge: data.today?.change_pct,
      gradient: "bg-linear-to-br from-indigo-500 to-indigo-700",
      iconBg: "bg-white/20",
      icon: (
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      label: t('dashboard.totalSales'),
      value: fmt(data.monthly?.sales),
      sub: `${data.monthly?.orders ?? 0} ${t('common.item')} ${t('sale.title').toLowerCase()}`,
      gradient: "bg-linear-to-br from-emerald-500 to-emerald-700",
      iconBg: "bg-white/20",
      icon: (
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      ),
    },
    {
      label: t('dashboard.profit'),
      value: fmt(data.monthly?.profit),
      sub: t('common.summary'),
      gradient: "bg-linear-to-br from-violet-500 to-violet-700",
      iconBg: "bg-white/20",
      icon: (
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
        </svg>
      ),
    },
    {
      label: t('dashboard.lowStock'),
      value: `${data.inventory?.low_stock_count ?? 0} ${t('common.item')}`,
      sub: `${t('product.outOfStock')}: ${data.inventory?.dead_stock_count ?? 0} ${t('common.item')}`,
      gradient: "bg-linear-to-br from-rose-500 to-rose-700",
      iconBg: "bg-white/20",
      icon: (
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
    },
    {
      label: t('customer.totalDebt'),
      value: fmt(data.debts?.total_debt),
      sub: data.debts?.overdue_count > 0
        ? `⚠ ${data.debts.overdue_count} ${t('common.item')} ${t('common.warning').toLowerCase()}`
        : `${data.debts?.debtor_count ?? 0} ${t('common.item')} ${t('customer.totalDebtors').toLowerCase()}`,
      gradient: data.debts?.overdue_count > 0
        ? "bg-linear-to-br from-orange-500 to-red-600"
        : "bg-linear-to-br from-amber-500 to-amber-700",
      iconBg: "bg-white/20",
      icon: (
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          {branches.length > 0 && (
            <div className="relative">
              <select
                value={branchId}
                onChange={handleBranchChange}
                className="text-sm border border-slate-200 rounded-xl pl-8 pr-3 py-2 bg-white text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 appearance-none cursor-pointer"
              >
                <option value="">{t('common.allBranches')}</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
              </svg>
            </div>
          )}
          {warehouses.length > 1 && (
            <div className="relative">
              <select
                value={warehouseId}
                onChange={handleWarehouseChange}
                className="text-sm border border-slate-200 rounded-xl pl-8 pr-3 py-2 bg-white text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 appearance-none cursor-pointer"
              >
                <option value="">{t('common.allWarehouses')}</option>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
              <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
            </div>
          )}
        </div>
        <button
          onClick={() => load(false)}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 bg-white border border-slate-200 hover:border-indigo-300 rounded-xl px-3 py-2 transition-colors shadow-sm"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {t('common.refresh')}
        </button>
      </div>
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-5">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Weekly Trend */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-slate-800">{t('dashboard.recentSales')}</h3>
              <p className="text-sm text-slate-400 mt-0.5">{t('common.today')} - 7 {t('common.date').toLowerCase()}</p>
            </div>
            <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.weekly_trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="amount" stroke="#6366f1" strokeWidth={2.5}
                fill="url(#colorArea)" dot={{ fill: '#6366f1', r: 3 }} activeDot={{ r: 5 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Top Products */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-semibold text-slate-800">{t('dashboard.topProducts')}</h3>
              <p className="text-sm text-slate-400 mt-0.5">{t('common.thisMonth')}</p>
            </div>
            <div className="w-8 h-8 bg-emerald-50 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
              </svg>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.top_products?.slice(0, 7)} layout="vertical" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis dataKey="name" type="category" width={110} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="revenue" fill="#10b981" radius={[0, 6, 6, 0]} maxBarSize={20} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Monthly 30-day trend */}
      <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-base font-semibold text-slate-800">{t('dashboard.monthlyTrend')}</h3>
            <p className="text-sm text-slate-400 mt-0.5">{t('dashboard.monthlyTrendDesc')}</p>
          </div>
          <div className="w-8 h-8 bg-violet-50 rounded-lg flex items-center justify-center">
            <svg className="w-4 h-4 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
        </div>
        {data.monthly_trend?.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data.monthly_trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.9} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.6} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 9 }} axisLine={false} tickLine={false} interval={4} />
              <YAxis tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={data.monthly_trend.reduce((a,d)=>a+d.amount,0)/data.monthly_trend.length} stroke="#e879f9" strokeDasharray="4 2" strokeWidth={1.5} />
              <Bar dataKey="amount" fill="url(#barGrad)" radius={[4,4,0,0]} maxBarSize={28} />
              <Line type="monotone" dataKey="amount" stroke="#7c3aed" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-40 text-slate-300 text-sm">{t('common.noData')}</div>
        )}
      </div>

      {/* Cashier Performance + Low Stock row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Kassir samaradorligi */}
        {data.cashier_performance?.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
              <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-800">{t('dashboard.cashierPerformance')}</h3>
                <p className="text-sm text-slate-400">{t('dashboard.cashierPerformanceMonth')}</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">#</th>
                    <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('shift.cashier')}</th>
                    <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('sale.title')}</th>
                    <th className="text-right text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">{t('common.total')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {data.cashier_performance.map((c, i) => (
                    <tr key={c.name} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                      <td className="px-6 py-3.5">
                        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                          i === 0 ? 'bg-amber-100 text-amber-700' :
                          i === 1 ? 'bg-slate-100 text-slate-600' :
                          i === 2 ? 'bg-orange-100 text-orange-600' : 'bg-slate-50 text-slate-400'
                        }`}>{i + 1}</span>
                      </td>
                      <td className="px-4 py-3.5 text-sm font-medium text-slate-800">{c.name}</td>
                      <td className="px-4 py-3.5 text-center text-sm text-slate-500">{c.count} {t('dashboard.salesCount')}</td>
                      <td className="px-6 py-3.5 text-right text-sm font-semibold text-emerald-600">{fmt(c.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Kam qoldiqli mahsulotlar */}
        {data.low_stock?.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
              <div className="w-8 h-8 bg-rose-50 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-800">{t('dashboard.lowStockProducts')}</h3>
                <p className="text-sm text-slate-400">{data.low_stock.length} {t('dashboard.lowStockBelowMin')}</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">{t('product.title')}</th>
                    <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('product.stock')}</th>
                    <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('product.minStock')}</th>
                    <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('common.status')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {data.low_stock.slice(0, 8).map((item, i) => (
                    <tr key={item.product_id} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                      <td className="px-6 py-3.5">
                        <span className="text-sm font-medium text-slate-800">{item.name}</span>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <span className={`text-sm font-bold ${item.qty <= 0 ? 'text-rose-600' : 'text-amber-600'}`}>
                          {item.qty}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-center text-sm text-slate-400">{item.min_stock}</td>
                      <td className="px-4 py-3.5 text-center">
                        {item.qty <= 0 ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-100 text-rose-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />{t('product.outOfStock')}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />{t('product.lowStock')}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
