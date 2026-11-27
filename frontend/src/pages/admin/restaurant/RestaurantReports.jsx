import { useState, useEffect, useCallback, useMemo } from 'react';
import toast from 'react-hot-toast';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';

// Restoran hisobotlari (TZ 12-bo'lim: 1, 2, 4, 8). Backend: app/routers/restaurant_reports.py.
// KPI qatori (stat tile) + jadvallar; grafik yo'q — raqamlar matn rangida, holat ranglari faqat yozuv bilan.

const pad = n => String(n).padStart(2, '0');
const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const money = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const compact = v => {
  const n = Number(v) || 0;
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)} mlrd`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)} mln`;
  if (a >= 1e4) return `${(n / 1e3).toFixed(0)} ming`;
  return money(n);
};
const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });
const inputCls = 'px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800';

function Tile({ label, value, sub }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-4 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-semibold text-slate-900 tabular-nums mt-0.5">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function Table({ title, cols, rows, empty, t }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>{cols.map(c => <th key={c.key} className={`px-3 py-2 ${c.num ? 'text-right' : 'text-left'}`}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={cols.length} className="px-3 py-6 text-center text-slate-400">{empty || t('restRep.noData')}</td></tr>}
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                {cols.map(c => (
                  <td key={c.key} className={`px-3 py-2 ${c.num ? 'text-right tabular-nums' : ''} text-slate-700`}>
                    {c.render ? c.render(r) : r[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function RestaurantReports() {
  const { t } = useLang();
  const { branches } = useBranch();
  const features = useCompanyFeatures();
  const alertPct = features?.restaurant_settings?.food_cost_alert_pct ?? 35;
  const today = iso(new Date());
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [branchId, setBranchId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState('revenue');

  const load = useCallback(() => {
    setLoading(true);
    const params = { date_from: from, date_to: to };
    if (branchId) params.branch_id = branchId;
    api.get('/restaurant/reports/summary', { params })
      .then(r => setData(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restRep.loadFailed')))
      .finally(() => setLoading(false));
  }, [from, to, branchId, t]);
  useEffect(() => { load(); }, [load]);

  const quick = days => {
    const d = new Date();
    const end = iso(d);
    d.setDate(d.getDate() - days);
    setFrom(iso(d));
    setTo(days === 1 ? iso(d) : end);
  };
  const monthStart = () => { const d = new Date(); setFrom(iso(new Date(d.getFullYear(), d.getMonth(), 1))); setTo(iso(d)); };

  const dishes = useMemo(() => {
    const rows = [...(data?.dishes || [])];
    rows.sort((a, b) => (Number(b[sortKey]) || 0) - (Number(a[sortKey]) || 0));
    return rows;
  }, [data, sortKey]);

  const k = data?.kpi;
  const fcCell = r => (r.food_cost_pct == null ? '' : (
    <span className={r.food_cost_pct > alertPct ? 'text-rose-700 font-semibold' : ''}>
      {r.food_cost_pct}%{r.food_cost_pct > alertPct ? ` · ${t('restRep.aboveLimit')}` : ''}
    </span>
  ));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{t('restRep.title')}</h1>
        <p className="text-sm text-slate-500">{t('restRep.desc')}</p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-slate-500">{t('restRep.from')}<br />
          <input type="date" className={inputCls} value={from} max={to} onChange={e => setFrom(e.target.value)} />
        </label>
        <label className="text-xs text-slate-500">{t('restRep.to')}<br />
          <input type="date" className={inputCls} value={to} min={from} max={today} onChange={e => setTo(e.target.value)} />
        </label>
        {branches.length > 1 && (
          <select className={inputCls} value={branchId} onChange={e => setBranchId(e.target.value)}>
            <option value="">{t('restRep.allBranches')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
        <div className="flex gap-1">
          <button className={inputCls} onClick={() => { setFrom(today); setTo(today); }}>{t('restRep.today')}</button>
          <button className={inputCls} onClick={() => quick(1)}>{t('restRep.yesterday')}</button>
          <button className={inputCls} onClick={() => quick(6)}>{t('restRep.last7')}</button>
          <button className={inputCls} onClick={monthStart}>{t('restRep.thisMonth')}</button>
        </div>
        {loading && <span className="text-xs text-slate-400">{t('restRep.loading')}</span>}
      </div>

      {k && (
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
          <Tile label={t('restRep.revenue')} value={compact(k.revenue)}
                sub={k.refunded > 0 ? `${t('restRep.refunded')} ${money(k.refunded)}` : null} />
          <Tile label={t('restRep.checks')} value={money(k.checks)} sub={`${t('restRep.avgCheck')} ${money(k.avg_check)}`} />
          <Tile label={t('restRep.guests')} value={money(k.guests)} sub={`${t('restRep.perGuest')} ${money(k.avg_per_guest)}`} />
          <Tile label={t('restRep.service')} value={compact(k.service)} sub={`${t('restRep.tips')} ${money(k.tips)}`} />
          <Tile label={t('restRep.discounts')} value={compact(k.discounts)} sub={`${t('restRep.cancels')} ${k.cancels} · ${money(k.cancel_amount)}`} />
          <Tile label={t('restRep.foodCost')} value={k.food_cost_pct == null ? '-' : `${k.food_cost_pct}%`}
                sub={k.food_cost_pct != null && k.food_cost_pct > alertPct ? t('restRep.aboveLimit') : null} />
        </div>
      )}

      {data && (
        <div className="grid lg:grid-cols-2 gap-4">
          <Table t={t} title={t('restRep.payments')}
                 cols={[{ key: 'type', label: t('restRep.payType') }, { key: 'amount', label: t('restRep.amount'), num: true, render: r => money(r.amount) }]}
                 rows={Object.entries(data.payments).map(([type, amount]) => ({ type: t(`restOrd.pay.${type}`), amount }))} />
          <Table t={t} title={t('restRep.byType')}
                 cols={[{ key: 'type', label: t('restRep.orderType') }, { key: 'checks', label: t('restRep.checks'), num: true },
                        { key: 'revenue', label: t('restRep.revenue'), num: true, render: r => money(r.revenue) }]}
                 rows={Object.entries(data.by_type).map(([type, v]) => ({ type: t(`restOrd.type.${type}`), ...v }))} />
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            {t('restRep.sortBy')}
            {['revenue', 'qty', 'profit', 'food_cost_pct'].map(s => (
              <button key={s} onClick={() => setSortKey(s)}
                      className={`px-2 py-1 rounded ${sortKey === s ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600'}`}>
                {t(`restRep.sort.${s}`)}
              </button>
            ))}
          </div>
          <Table t={t} title={t('restRep.dishes')} rows={dishes}
                 cols={[{ key: 'name', label: t('restRep.dish') },
                        { key: 'qty', label: t('restRep.qty'), num: true, render: r => qtyFmt(r.qty) },
                        { key: 'revenue', label: t('restRep.revenue'), num: true, render: r => money(r.revenue) },
                        { key: 'cost', label: t('restRep.cost'), num: true, render: r => money(r.cost) },
                        { key: 'profit', label: t('restRep.profit'), num: true, render: r => money(r.profit) },
                        { key: 'food_cost_pct', label: t('restRep.foodCost'), num: true, render: fcCell }]} />
          <Table t={t} title={t('restRep.waiters')} rows={data.waiters}
                 cols={[{ key: 'name', label: t('restRep.waiter') },
                        { key: 'checks', label: t('restRep.checks'), num: true },
                        { key: 'revenue', label: t('restRep.revenue'), num: true, render: r => money(r.revenue) },
                        { key: 'avg_check', label: t('restRep.avgCheck'), num: true, render: r => money(r.avg_check) },
                        { key: 'guests', label: t('restRep.guests'), num: true },
                        { key: 'tips', label: t('restRep.tips'), num: true, render: r => money(r.tips) },
                        { key: 'discounts', label: t('restRep.discounts'), num: true, render: r => money(r.discounts) },
                        { key: 'cancels', label: t('restRep.cancels'), num: true, render: r => `${r.cancels} · ${money(r.cancel_amount)}` }]} />
          <Table t={t} title={t('restRep.cancellations')} rows={data.cancellations} empty={t('restRep.noCancels')}
                 cols={[{ key: 'at', label: t('restRep.time'), render: r => (r.at ? new Date(r.at.endsWith('Z') || r.at.includes('+') ? r.at : `${r.at}Z`).toLocaleString() : '') },
                        { key: 'daily_no', label: '#', render: r => `#${r.daily_no}` },
                        { key: 'name', label: t('restRep.dish') },
                        { key: 'quantity', label: t('restRep.qty'), num: true, render: r => qtyFmt(r.quantity) },
                        { key: 'amount', label: t('restRep.amount'), num: true, render: r => money(r.amount) },
                        { key: 'reason', label: t('restRep.reason'), render: r => { const [code, ...rest] = String(r.reason || '').split(': '); return `${t(`restOrd.reason.${code}`)}${rest.length ? `: ${rest.join(': ')}` : ''}`; } },
                        { key: 'write_off', label: t('restRep.writeOff'), render: r => (r.write_off ? t('restRep.yes') : '') },
                        { key: 'cancelled_by', label: t('restRep.who'), render: r => [r.cancelled_by, r.approved_by && `${t('restRep.approved')}: ${r.approved_by}`].filter(Boolean).join(' · ') }]} />
          <Table t={t} title={t('restRep.discountList')} rows={data.discounts} empty={t('restRep.noDiscounts')}
                 cols={[{ key: 'daily_no', label: '#', render: r => `#${r.daily_no}` },
                        { key: 'waiter', label: t('restRep.waiter') },
                        { key: 'amount', label: t('restRep.amount'), num: true, render: r => `${money(r.amount)}${r.pct ? ` (${r.pct}%)` : ''}` },
                        { key: 'total', label: t('restRep.checkTotal'), num: true, render: r => money(r.total) },
                        { key: 'reason', label: t('restRep.reason') }]} />
        </div>
      )}
    </div>
  );
}
