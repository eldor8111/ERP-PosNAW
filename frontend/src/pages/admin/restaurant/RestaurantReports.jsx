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

// ── Tahliliy hisobotlar (3, 5, 6, 7, 9): GET /restaurant/reports/analytics ──
const TABS = ['summary', 'menu', 'load', 'tables', 'kitchen', 'stock'];
const CLASSES = ['star', 'plowhorse', 'puzzle', 'dog'];
// ketma-ket (sequential) ko'k shkala, och -> to'q; 0 = fon
const HEAT = ['#cce3fd', '#9dc8f7', '#6aabf1', '#338ced', '#1b64be', '#0e3d7e'];
const mins = v => (v == null ? '-' : `${Number(v).toLocaleString('uz-UZ', { maximumFractionDigits: 1 })}`);

function Heatmap({ load, t }) {
  const [metric, setMetric] = useState('checks');
  const m = load[metric];
  const active = load.by_hour.map((v, h) => (v > 0 ? h : null)).filter(h => h != null);
  const lo = active.length ? Math.min(8, active[0]) : 8;
  const hi = active.length ? Math.max(23, active[active.length - 1]) : 23;
  const hours = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
  const max = Math.max(0, ...m.flat().map(Number));
  const step = v => (v > 0 && max > 0 ? Math.min(HEAT.length - 1, Math.floor((v / max) * HEAT.length - 1e-9)) : -1);
  const fmt = v => (metric === 'revenue' ? compact(v) : money(v));
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-slate-800">{t('restAn.heatTitle')}</span>
        <div className="ml-auto flex gap-1">
          {['checks', 'revenue', 'guests'].map(k => (
            <button key={k} onClick={() => setMetric(k)}
                    className={`px-2 py-1 rounded text-xs ${metric === k ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600'}`}>
              {t(`restAn.metric.${k}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th />
              {hours.map(h => <th key={h} className="text-[10px] font-normal text-slate-500 w-9">{String(h).padStart(2, '0')}</th>)}
            </tr>
          </thead>
          <tbody>
            {m.map((row, wd) => (
              <tr key={wd}>
                <td className="text-xs text-slate-600 pr-2 whitespace-nowrap">{t(`restAn.wd.${wd}`)}</td>
                {hours.map(h => {
                  const v = Number(row[h]) || 0;
                  const s = step(v);
                  return (
                    <td key={h} title={`${t(`restAn.wd.${wd}`)} ${String(h).padStart(2, '0')}:00, ${t(`restAn.metric.${metric}`)}: ${fmt(v)}`}
                        className="w-9 h-7 rounded text-center text-[10px] tabular-nums"
                        style={{ background: s < 0 ? '#f1f5f9' : HEAT[s], color: s >= 3 ? '#ffffff' : '#0f172a' }}>
                      {v > 0 && metric !== 'revenue' ? v : ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span>{t('restAn.less')}</span>
        {HEAT.map(c => <span key={c} className="w-5 h-3 rounded-sm" style={{ background: c }} />)}
        <span>{t('restAn.more')} ({fmt(max)})</span>
        {load.peak && load.peak.checks > 0 && (
          <span className="ml-auto text-slate-600">{t('restAn.peak')}: {t(`restAn.wd.${load.peak.weekday}`)} {String(load.peak.hour).padStart(2, '0')}:00</span>
        )}
      </div>
    </div>
  );
}

function AnalyticsView({ tab, data, t }) {
  if (tab === 'menu') {
    const me = data.menu;
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-500">{t('restAn.menuDesc')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {CLASSES.map(c => (
            <div key={c} className="bg-white border border-slate-200 rounded-xl px-4 py-3">
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-bold text-slate-800">{t(`restAn.class.${c}`)}</span>
                <span className="text-xl font-semibold tabular-nums text-slate-900">{me.groups?.[c] ?? 0}</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{t(`restAn.advice.${c}`)}</p>
            </div>
          ))}
        </div>
        {me.popularity_threshold != null && (
          <p className="text-xs text-slate-500">{t('restAn.thresholds', { pop: me.popularity_threshold, margin: money(me.margin_threshold) })}</p>
        )}
        <Table t={t} title={t('restAn.menuTable')} rows={me.items}
               cols={[{ key: 'name', label: t('restRep.dish') },
                      { key: 'class', label: t('restAn.group'), render: r => <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-xs font-semibold">{t(`restAn.class.${r.class}`)}</span> },
                      { key: 'qty', label: t('restRep.qty'), num: true, render: r => qtyFmt(r.qty) },
                      { key: 'share_pct', label: t('restAn.share'), num: true, render: r => `${r.share_pct}%` },
                      { key: 'margin', label: t('restAn.margin'), num: true, render: r => money(r.margin) },
                      { key: 'profit', label: t('restRep.profit'), num: true, render: r => money(r.profit) },
                      { key: 'food_cost_pct', label: t('restRep.foodCost'), num: true, render: r => (r.food_cost_pct == null ? '' : `${r.food_cost_pct}%`) }]} />
      </div>
    );
  }
  if (tab === 'load') {
    const l = data.load;
    return (
      <div className="space-y-4">
        <Heatmap load={l} t={t} />
        <Table t={t} title={t('restAn.byWeekday')} rows={l.by_weekday.map((v, wd) => ({ wd, checks: v, days: l.weekday_days[wd] }))}
               cols={[{ key: 'wd', label: t('restAn.weekday'), render: r => t(`restAn.wd.${r.wd}`) },
                      { key: 'checks', label: t('restRep.checks'), num: true },
                      { key: 'avg', label: t('restAn.perDay'), num: true, render: r => (r.days ? (r.checks / r.days).toFixed(1) : '-') }]} />
      </div>
    );
  }
  if (tab === 'tables') {
    const s = data.tables.summary;
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label={t('restAn.turns')} value={money(s.turns)} sub={`${t('restAn.tablesN')} ${s.tables}`} />
          <Tile label={t('restAn.turnsPerTableDay')} value={s.turns_per_table_day} />
          <Tile label={t('restAn.avgSit')} value={`${mins(s.avg_minutes)} ${t('restAn.min')}`} />
          <Tile label={t('restAn.idle')} value={money(s.idle_tables)} />
        </div>
        <Table t={t} title={t('restAn.tablesTitle')} rows={data.tables.rows}
               cols={[{ key: 'name', label: t('restAn.table'), render: r => `${r.name} (${r.hall})` },
                      { key: 'seats', label: t('restAn.seats'), num: true },
                      { key: 'turns', label: t('restAn.turns'), num: true },
                      { key: 'turns_per_day', label: t('restAn.perDay'), num: true },
                      { key: 'avg_minutes', label: t('restAn.avgSit'), num: true, render: r => mins(r.avg_minutes) },
                      { key: 'revenue', label: t('restRep.revenue'), num: true, render: r => money(r.revenue) },
                      { key: 'avg_check', label: t('restRep.avgCheck'), num: true, render: r => money(r.avg_check) },
                      { key: 'revenue_per_seat', label: t('restAn.perSeat'), num: true, render: r => money(r.revenue_per_seat) }]} />
      </div>
    );
  }
  if (tab === 'kitchen') {
    const k = data.kitchen;
    const lateCell = r => <span className={r.late_pct > 0 ? 'text-rose-700 font-semibold' : ''}>{r.late} ({r.late_pct}%)</span>;
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label={t('restAn.cooked')} value={money(k.summary.items)} />
          <Tile label={t('restAn.avgCook')} value={`${mins(k.summary.avg_minutes)} ${t('restAn.min')}`} sub={`P90 ${mins(k.summary.p90_minutes)} ${t('restAn.min')}`} />
          <Tile label={t('restAn.avgWait')} value={`${mins(k.summary.avg_wait)} ${t('restAn.min')}`} />
          <Tile label={t('restAn.late')} value={`${k.summary.late_pct}%`} sub={`${k.summary.late} ${t('restAn.itemsShort')}`} />
        </div>
        <Table t={t} title={t('restAn.byStation')} rows={k.stations}
               cols={[{ key: 'name', label: t('restAn.station') },
                      { key: 'items', label: t('restAn.cooked'), num: true },
                      { key: 'avg_minutes', label: t('restAn.avgCook'), num: true, render: r => mins(r.avg_minutes) },
                      { key: 'p90_minutes', label: 'P90', num: true, render: r => mins(r.p90_minutes) },
                      { key: 'avg_wait', label: t('restAn.avgWait'), num: true, render: r => mins(r.avg_wait) },
                      { key: 'late', label: t('restAn.late'), num: true, render: lateCell }]} />
        <Table t={t} title={t('restAn.byDish')} rows={k.dishes}
               cols={[{ key: 'name', label: t('restRep.dish') },
                      { key: 'items', label: t('restAn.cooked'), num: true },
                      { key: 'avg_minutes', label: t('restAn.avgCook'), num: true, render: r => mins(r.avg_minutes) },
                      { key: 'norm', label: t('restAn.norm'), num: true, render: r => (r.norm ? mins(r.norm) : '') },
                      { key: 'late', label: t('restAn.late'), num: true, render: lateCell }]} />
      </div>
    );
  }
  if (tab === 'stock') {
    const st = data.stock;
    const s = st.summary;
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-500">{t('restAn.stockDesc')} {st.warehouses.map(w => w.name).join(', ')}</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Tile label={t('restAn.stockValue')} value={compact(s.value)} />
          <Tile label={t('restAn.theoretical')} value={compact(s.theoretical_cost)} />
          <Tile label={t('restAn.writeoff')} value={compact(s.writeoff_cost)} />
          <Tile label={t('restAn.variance')} value={compact(s.variance_cost)} sub={s.variance_pct != null ? `${s.variance_pct}%` : null} />
          <Tile label={t('restAn.negative')} value={money(s.negative)} />
        </div>
        <Table t={t} title={t('restAn.stockTable')} rows={st.rows}
               cols={[{ key: 'name', label: t('restAn.ingredient'), render: r => <span className={r.negative ? 'text-rose-700 font-semibold' : ''}>{r.name}{r.kind === 'semi' ? ` (${t('restAn.semi')})` : ''}</span> },
                      { key: 'stock', label: t('restAn.stockQty'), num: true, render: r => <span className={r.negative ? 'text-rose-700 font-semibold' : ''}>{qtyFmt(r.stock)} {r.unit || ''}</span> },
                      { key: 'theoretical', label: t('restAn.theoretical'), num: true, render: r => qtyFmt(r.theoretical) },
                      { key: 'writeoff', label: t('restAn.writeoff'), num: true, render: r => (r.writeoff ? qtyFmt(r.writeoff) : '') },
                      { key: 'variance', label: t('restAn.variance'), num: true, render: r => (r.variance ? <span className={r.variance < 0 ? 'text-rose-700' : ''}>{r.variance > 0 ? '+' : ''}{qtyFmt(r.variance)}</span> : '') },
                      { key: 'actual', label: t('restAn.actual'), num: true, render: r => qtyFmt(r.actual) },
                      { key: 'variance_pct', label: t('restAn.variancePct'), num: true, render: r => (r.variance_pct == null ? '' : `${r.variance_pct}%`) },
                      { key: 'variance_cost', label: t('restAn.varianceCost'), num: true, render: r => (r.variance_cost ? money(r.variance_cost) : '') }]} />
        <p className="text-xs text-slate-500">{t('restAn.stockHint')}</p>
      </div>
    );
  }
  return null;
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
  const [tab, setTab] = useState('summary');
  const [an, setAn] = useState(null);
  const [anLoading, setAnLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const params = { date_from: from, date_to: to };
    if (branchId) params.branch_id = branchId;
    api.get('/restaurant/reports/summary', { params })
      .then(r => setData(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restRep.loadFailed')))
      .finally(() => setLoading(false));
  }, [from, to, branchId, t]);
  useEffect(() => { if (tab === 'summary') load(); }, [load, tab]);

  const loadAnalytics = useCallback(() => {
    setAnLoading(true);
    const params = { date_from: from, date_to: to };
    if (branchId) params.branch_id = branchId;
    api.get('/restaurant/reports/analytics', { params })
      .then(r => setAn(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restRep.loadFailed')))
      .finally(() => setAnLoading(false));
  }, [from, to, branchId, t]);
  useEffect(() => { if (tab !== 'summary') loadAnalytics(); }, [tab, loadAnalytics]);

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
        {(loading || anLoading) && <span className="text-xs text-slate-400">{t('restRep.loading')}</span>}
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map(x => (
          <button key={x} onClick={() => setTab(x)}
                  className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === x ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {t(`restAn.tab.${x}`)}
          </button>
        ))}
      </div>

      {tab !== 'summary' && an && <AnalyticsView tab={tab} data={an} t={t} />}

      {tab === 'summary' && k && (
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

      {tab === 'summary' && data && (
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

      {tab === 'summary' && data && (
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
