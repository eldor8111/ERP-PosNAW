import React, { useState, useEffect } from 'react';
import api from '../../api/axios';
import {
  AlertTriangle, PackageX, Clock, CheckCircle,
  RefreshCw, ChevronRight, Box, Calendar
} from 'lucide-react';
import { useLang } from '../../context/LangContext';
import useCompanyFeatures from '../../hooks/useCompanyFeatures';
import { Link } from 'react-router-dom';

function AlertCard({ icon: Icon, color, title, count, desc }) {
  const colors = {
    red:    { bg: 'bg-red-50',    border: 'border-red-200',    text: 'text-red-700',    icon: 'text-red-500',    dot: 'bg-red-500' },
    amber:  { bg: 'bg-amber-50',  border: 'border-amber-200',  text: 'text-amber-700',  icon: 'text-amber-500',  dot: 'bg-amber-500' },
    blue:   { bg: 'bg-blue-50',   border: 'border-blue-200',   text: 'text-blue-700',   icon: 'text-blue-500',   dot: 'bg-blue-500' },
    emerald:{ bg: 'bg-emerald-50',border: 'border-emerald-200',text: 'text-emerald-700',icon: 'text-emerald-500',dot: 'bg-emerald-500' },
  }[color];
  return (
    <div className={`p-4 rounded-xl border ${colors.bg} ${colors.border}`}>
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl bg-white/70 flex items-center justify-center ${colors.icon}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className={`text-2xl font-bold ${colors.text}`}>{count}</div>
          <div className={`text-xs font-semibold ${colors.text} opacity-80`}>{title}</div>
        </div>
      </div>
      <p className={`text-xs mt-2 ${colors.text} opacity-70`}>{desc}</p>
    </div>
  );
}

export default function Alerts() {
  const { t } = useLang();
  const [lowStock, setLowStock] = useState([]);
  const [expiring, setExpiring] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('expiring');
  const features = useCompanyFeatures();
  const [raw, setRaw] = useState({ shortages: [], low_stock: [] });
  const [distributors, setDistributors] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      const [ls, exp, rw, dist] = await Promise.all([
        api.get('/inventory/stock?low_stock_only=true&limit=200').then(r => r.data).catch(() => []),
        api.get('/inventory/expiring-batches').then(r => r.data).catch(() => []),
        features?.manufacturing
          ? api.get('/production/alerts', { _silent: true }).then(r => r.data).catch(() => null) : null,
        features?.distribution
          ? api.get('/customers/distributors-report', { params: { days: 30 }, _silent: true }).then(r => r.data.items).catch(() => []) : [],
      ]);
      setLowStock(ls);
      setExpiring(exp);
      setRaw(rw || { shortages: [], low_stock: [] });
      // Limitdan oshgan yoki 90% ga yetgan distribyutorlar
      setDistributors((dist || []).filter(d => d.over_limit || (d.limit_usage ?? 0) >= 90)
        .sort((a, b) => (b.limit_usage ?? 0) - (a.limit_usage ?? 0)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (features !== null) load(); }, [features]); // eslint-disable-line react-hooks/exhaustive-deps
  const rawCount = raw.shortages.length + raw.low_stock.length;

  const expired = expiring.filter(e => e.is_expired);
  const soonExpiring = expiring.filter(e => !e.is_expired && e.days_left <= 7);
  const willExpire = expiring.filter(e => !e.is_expired && e.days_left > 7);

  const daysBadge = (days) => {
    if (days < 0) return <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-bold rounded-full">{t('alert.expired')}</span>;
    if (days === 0) return <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-bold rounded-full">{t('alert.expiresToday')}</span>;
    if (days <= 3) return <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full">{t('alert.daysLeft', { days })}</span>;
    if (days <= 7) return <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-semibold rounded-full">{t('alert.daysLeft', { days })}</span>;
    return <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full">{t('alert.daysLeft', { days })}</span>;
  };

  const writeOff = async (batchId) => {
    if (!window.confirm(t('alert.confirmWriteOff'))) return;
    try {
      await api.post('/inventory/write-off-expired', { batch_ids: [batchId] });
      load();
    } catch(e) {
      alert(e?.response?.data?.detail || t('alert.genericError'));
    }
  };

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('alert.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('alert.subtitle')}</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {t('common.refresh')}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <AlertCard icon={PackageX}     color="red"     title={t('alert.expiredTitle')}     count={expired.length}      desc={t('alert.expiredDesc')} />
        <AlertCard icon={AlertTriangle} color="amber"  title={t('alert.soonExpiringTitle')}      count={soonExpiring.length} desc={t('alert.soonExpiringDesc')} />
        <AlertCard icon={Clock}        color="blue"    title={t('alert.reminderTitle')}          count={willExpire.length}   desc={t('alert.reminderDesc')} />
        <AlertCard icon={Box}          color={lowStock.length > 0 ? 'amber' : 'emerald'} title={t('alert.lowStockTitle')} count={lowStock.length} desc={t('alert.lowStockDesc')} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-xl mb-5 w-fit">
        {[
          { id: 'expiring', label: `${t('alert.expiryTab')} (${expiring.length})` },
          { id: 'lowstock', label: `${t('alert.lowStockTab')} (${lowStock.length})` },
          ...(features?.manufacturing ? [{ id: 'raw', label: `${t('alert.rawTab')} (${rawCount})` }] : []),
          ...(features?.distribution ? [{ id: 'dist', label: `${t('alert.distTab')} (${distributors.length})` }] : []),
        ].map(tb => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
              tab === tb.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : tab === 'raw' ? (
        rawCount === 0 ? (
          <div className="flex flex-col items-center py-16 text-slate-400">
            <CheckCircle className="w-12 h-12 mb-3 text-emerald-400" />
            <p className="font-semibold text-slate-600">{t('alert.rawOk')}</p>
          </div>
        ) : (
          <div className="space-y-5">
            {raw.shortages.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">{t('alert.rawShortageTitle')}</h3>
                {raw.shortages.map(s => (
                  <div key={`${s.product_id}-${s.warehouse_id}`} className="flex items-center justify-between gap-3 p-4 bg-red-50 border border-red-200 rounded-xl">
                    <div className="min-w-0">
                      <div className="font-semibold text-slate-800 text-sm">{s.product_name}</div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {t('alert.warehouse')}: <b>{s.warehouse_name || '—'}</b> &nbsp;|&nbsp;
                        {t('alert.rawNeed')}: <b>{s.required} {s.unit}</b> &nbsp;|&nbsp;
                        {t('alert.remaining')}: <b>{s.available}</b>
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5 truncate">{t('alert.rawForOrders')}: {s.orders.join(', ')}</div>
                    </div>
                    <span className="shrink-0 px-2.5 py-1 bg-red-100 text-red-700 text-xs font-bold rounded-full">−{s.shortage} {s.unit}</span>
                  </div>
                ))}
              </div>
            )}
            {raw.low_stock.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">{t('alert.rawLowTitle')}</h3>
                {raw.low_stock.map(s => (
                  <div key={s.product_id} className="flex items-center justify-between p-4 bg-amber-50 border border-amber-200 rounded-xl">
                    <div className="font-semibold text-slate-800 text-sm">{s.product_name}</div>
                    <div className="text-xs text-slate-500">
                      {t('alert.remaining')}: <b className="text-amber-700">{s.quantity} {s.unit}</b> &nbsp;|&nbsp; {t('alert.min')}: <b>{s.min_stock}</b>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Link to="/admin/purchases" className="inline-flex items-center gap-1 text-sm font-semibold text-blue-600 hover:underline">
              {t('alert.rawOrderMore')} <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        )
      ) : tab === 'dist' ? (
        distributors.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-slate-400">
            <CheckCircle className="w-12 h-12 mb-3 text-emerald-400" />
            <p className="font-semibold text-slate-600">{t('alert.distOk')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {distributors.map(d => (
              <Link key={d.id} to={`/admin/customers/${d.id}`}
                className={`flex items-center justify-between gap-3 p-4 rounded-xl border ${d.over_limit ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                <div className="min-w-0">
                  <div className="font-semibold text-slate-800 text-sm">{d.name}{d.territory ? <span className="font-normal text-slate-500"> · {d.territory}</span> : null}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {t('alert.distDebt')}: <b>{Number(d.debt).toLocaleString('uz-UZ')}</b> / {t('alert.distLimit')}: <b>{Number(d.debt_limit).toLocaleString('uz-UZ')}</b>
                  </div>
                </div>
                <span className={`shrink-0 px-2.5 py-1 text-xs font-bold rounded-full ${d.over_limit ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                  {d.over_limit ? t('alert.distOver') : `${d.limit_usage}%`}
                </span>
              </Link>
            ))}
          </div>
        )
      ) : tab === 'expiring' ? (
        expiring.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-slate-400">
            <CheckCircle className="w-12 h-12 mb-3 text-emerald-400" />
            <p className="font-semibold text-slate-600">{t('alert.allProductsValid')}</p>
            <p className="text-sm mt-1">{t('alert.noExpiringProducts')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {expiring.map(item => (
              <div
                key={item.batch_id}
                className={`flex items-center justify-between p-4 rounded-xl border transition-all ${
                  item.is_expired
                    ? 'bg-red-50 border-red-200'
                    : item.days_left <= 7
                    ? 'bg-amber-50 border-amber-200'
                    : 'bg-white border-slate-200'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${
                    item.is_expired ? 'bg-red-500' : item.days_left <= 7 ? 'bg-amber-500' : 'bg-blue-400'
                  }`} />
                  <div>
                    <div className="font-semibold text-slate-800 text-sm">
                      {item.product_name}
                      {item.variant_name && <span className="text-slate-500 font-normal ml-1">({item.variant_name})</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(item.expiry_date).toLocaleDateString('uz-UZ')}
                      </span>
                      <span className="text-xs text-slate-500">
                        {t('common.quantity')}: <b>{item.quantity}</b>
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {daysBadge(item.days_left)}
                  {item.is_expired && (
                    <button
                      onClick={() => writeOff(item.batch_id)}
                      className="px-3 py-1.5 text-xs font-semibold text-red-600 bg-white border border-red-200 rounded-lg hover:bg-red-50"
                    >
                      {t('alert.writeOff')}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        lowStock.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-slate-400">
            <CheckCircle className="w-12 h-12 mb-3 text-emerald-400" />
            <p className="font-semibold text-slate-600">{t('alert.allProductsSufficient')}</p>
            <p className="text-sm mt-1">{t('alert.noLowStockProducts')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {lowStock.map(item => (
              <div key={`${item.product_id}-${item.variant_id || 0}`}
                className="flex items-center justify-between p-4 bg-amber-50 border border-amber-200 rounded-xl"
              >
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
                  <div>
                    <div className="font-semibold text-slate-800 text-sm">
                      {item.product_name || `${t('alert.productHash')}${item.product_id}`}
                      {item.variant_name && <span className="text-slate-500 font-normal ml-1">({item.variant_name})</span>}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {t('alert.warehouse')}: <b>{item.warehouse_name || '—'}</b> &nbsp;|&nbsp;
                      {t('alert.remaining')}: <b className="text-amber-700">{item.quantity}</b>
                      {item.min_stock_level && <> &nbsp;|&nbsp; {t('alert.min')}: <b>{item.min_stock_level}</b></>}
                    </div>
                  </div>
                </div>
                <a href="/admin/ombor" className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-amber-700 bg-white border border-amber-200 rounded-lg hover:bg-amber-50">
                  {t('alert.warehouse')} <ChevronRight className="w-3.5 h-3.5" />
                </a>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
