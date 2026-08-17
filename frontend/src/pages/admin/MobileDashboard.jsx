import { useLang } from '../../context/LangContext';
import { useState, useEffect } from 'react';
import api from '../../api/axios';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

function KpiCard({ label, value, sub, color = 'indigo', icon }) {
  const { t } = useLang();
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    emerald: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    red: 'bg-red-50 text-red-500 border-red-100',
    amber: 'bg-amber-50 text-amber-600 border-amber-100',
  };
  return (
    <div className={`rounded-2xl border p-5 ${colors[color]}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-70">{label}</span>
        <div className="w-9 h-9 rounded-xl bg-white/60 flex items-center justify-center">{icon}</div>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs mt-1 opacity-70">{sub}</div>}
    </div>
  );
}

export default function MobileDashboard() {
  const { t } = useLang();
  const [summary, setSummary] = useState(null);
  const [topProducts, setTopProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, tp] = await Promise.all([
        api.get('/mobile/dashboard/summary'),
        api.get('/mobile/dashboard/top-products'),
      ]);
      setSummary(s.data);
      setTopProducts(tp.data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 60000); // auto-refresh every minute
    return () => clearInterval(timer);
  }, []);

  const maxQty = topProducts.length ? Math.max(...topProducts.map(p => p.sold_quantity)) : 1;

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-lg mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Mobil Ko'rinish</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {lastUpdated
              ? `Yangilangan: ${lastUpdated.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}`
              : 'Bugungi holat'}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2.5 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors shadow-sm"
          title="Yangilash"
        >
          <svg
            className={`w-5 h-5 text-slate-600 ${loading ? 'animate-spin' : ''}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {/* Date badge */}
      <div className="bg-indigo-600 text-white rounded-2xl p-4 flex items-center gap-3">
        <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
        <div>
          <div className="text-xs font-semibold opacity-80">Bugungi sana</div>
          <div className="font-bold">
            {new Date().toLocaleDateString('uz-UZ', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      {summary && (
        <div className="grid grid-cols-1 gap-4">
          <KpiCard
            label="Bugungi sotuv"
            value={`${fmt(summary.today_sales)} so'm`}
            color="indigo"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            }
          />
          <KpiCard
            label="Kassadagi naqd pul"
            value={`${fmt(summary.cash_in_register)} so'm`}
            color="emerald"
            sub="To'liq to'langan miqdor"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            }
          />
          <KpiCard
            label="Qarzga berilgan"
            value={`${fmt(summary.debt_sales)} so'm`}
            color="red"
            sub="Bugun to'lanmagan sotuvlar"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />
        </div>
      )}

      {/* Efficiency bar */}
      {summary && summary.today_sales > 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-700">Naqd / Qarz nisbati</span>
            <span className="text-xs text-slate-500">
              {Math.round((summary.cash_in_register / summary.today_sales) * 100)}% naqd
            </span>
          </div>
          <div className="h-3 bg-slate-100 rounded-full overflow-hidden flex">
            <div
              className="bg-emerald-500 transition-all duration-700"
              style={{ width: `${Math.round((summary.cash_in_register / summary.today_sales) * 100)}%` }}
            />
            <div
              className="bg-red-400 transition-all duration-700"
              style={{ width: `${Math.round((summary.debt_sales / summary.today_sales) * 100)}%` }}
            />
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-emerald-500 rounded-full inline-block" /> Naqd</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-red-400 rounded-full inline-block" /> Qarz</span>
          </div>
        </div>
      )}

      {/* Top products */}
      {topProducts.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <h3 className="text-sm font-bold text-slate-800 mb-4">Eng ko'p sotilgan mahsulotlar</h3>
          <div className="space-y-3">
            {topProducts.map((p, i) => (
              <div key={p.id} className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                  i === 0 ? 'bg-amber-100 text-amber-600' :
                  i === 1 ? 'bg-slate-200 text-slate-600' :
                  i === 2 ? 'bg-orange-100 text-orange-600' :
                  'bg-slate-100 text-slate-500'
                }`}>
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-slate-700 truncate">{p.name}</span>
                    <span className="text-xs font-bold text-slate-500 ml-2 shrink-0">{fmt(p.sold_quantity)} dona</span>
                  </div>
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-700"
                      style={{ width: `${(p.sold_quantity / maxQty) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick links */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-4">Tezkor havolalar</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Dashboard', path: '/admin/dashboard', color: 'indigo' },
            { label: 'Hisobotlar', path: '/admin/reports', color: 'violet' },
            { label: 'Moliya', path: '/admin/finance', color: 'emerald' },
            { label: 'Mijozlar', path: '/admin/customers', color: 'amber' },
          ].map(({ label, path, color }) => (
            <a
              key={path}
              href={path}
              className={`flex items-center justify-center py-3 rounded-xl text-sm font-semibold transition-colors ${
                color === 'indigo' ? 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100' :
                color === 'violet' ? 'bg-violet-50 text-violet-700 hover:bg-violet-100' :
                color === 'emerald' ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' :
                'bg-amber-50 text-amber-700 hover:bg-amber-100'
              }`}
            >
              {label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
