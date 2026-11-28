import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// Restoran bosh sahifasi (TZ 12-bo'lim oxiri): bugungi tushum, ochiq stollar va cheklar, oshxona navbati,
// kechikayotgan taomlar, bugungi bronlar, stop-list. Backend: GET /restaurant/reports/dashboard (30 s yangilanadi).

const REFRESH_MS = 30000;
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
const hhmm = iso => { const d = new Date(iso); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };

function Tile({ label, value, sub, alert, to }) {
  const body = (
    <div className={`bg-white border rounded-xl px-4 py-3 h-full ${alert ? 'border-rose-300' : 'border-slate-200'} ${to ? 'hover:bg-slate-50' : ''}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-xl font-semibold tabular-nums mt-0.5 ${alert ? 'text-rose-700' : 'text-slate-900'}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

function Panel({ title, to, linkLabel, children }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2">
        <span className="text-sm font-bold text-slate-800">{title}</span>
        {to && <Link to={to} className="ml-auto text-xs text-blue-700 hover:underline">{linkLabel}</Link>}
      </div>
      {children}
    </div>
  );
}

export default function RestaurantDashboard() {
  const { t } = useLang();
  const { branches } = useBranch();
  const [branchId, setBranchId] = useState('');
  const [data, setData] = useState(null);
  const [updated, setUpdated] = useState(null);

  const load = useCallback(() => {
    const params = branchId ? { branch_id: branchId } : {};
    api.get('/restaurant/reports/dashboard', { params, _silent: true })
      .then(r => { setData(r.data); setUpdated(new Date()); })
      .catch(err => toast.error(err.response?.data?.detail || t('restDash.failed'), { id: 'rest-dash' }));
  }, [branchId, t]);
  useEffect(() => { load(); const p = setInterval(load, REFRESH_MS); return () => clearInterval(p); }, [load]);

  const d = data;
  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restDash.title')}</h1>
          <p className="text-sm text-slate-500">
            {t('restDash.desc')}{updated ? ` ${t('restDash.updated')} ${hhmm(updated.toISOString())}` : ''}
          </p>
        </div>
        {branches.length > 1 && (
          <select className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white" value={branchId} onChange={e => setBranchId(e.target.value)}>
            <option value="">{t('restDash.allBranches')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>

      {d && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Tile label={t('restDash.revenue')} value={compact(d.today.revenue)} to="/admin/restaurant/reports"
                sub={`${t('restDash.checks')} ${d.today.checks}, ${t('restDash.avg')} ${money(d.today.avg_check)}`} />
          <Tile label={t('restDash.openChecks')} value={money(d.open.checks)} to="/admin/restaurant/orders"
                sub={`${t('restDash.sum')} ${money(d.open.sum)}`} />
          <Tile label={t('restDash.busyTables')} value={`${d.open.busy_tables} / ${d.open.tables}`} to="/admin/restaurant/orders"
                sub={d.open.prechecked ? `${t('restDash.billRequested')} ${d.open.prechecked}` : null} />
          <Tile label={t('restDash.kitchenQueue')} value={money(d.kitchen.queue)} to="/admin/restaurant/kds"
                sub={d.kitchen.ready_waiting ? `${t('restDash.readyWaiting')} ${d.kitchen.ready_waiting}` : null} />
          <Tile label={t('restDash.late')} value={money(d.kitchen.late)} alert={d.kitchen.late > 0} to="/admin/restaurant/kds" />
          <Tile label={t('restDash.reservations')} value={money(d.reservations.count)} to="/admin/restaurant/reservations"
                sub={`${t('restDash.guests')} ${d.reservations.guests}${d.reservations.arrived ? `, ${t('restDash.arrived')} ${d.reservations.arrived}` : ''}`} />
        </div>
      )}

      {d && (
        <div className="grid lg:grid-cols-2 gap-4">
          <Panel title={t('restDash.lateTitle')} to="/admin/restaurant/kds" linkLabel={t('restDash.toKds')}>
            {d.kitchen.late_items.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restDash.noLate')}</div>}
            <div className="divide-y divide-slate-100">
              {d.kitchen.late_items.map((x, i) => (
                <div key={i} className="px-4 py-2 flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-semibold text-slate-800 flex-1 min-w-[120px]">{x.name} <span className="font-normal text-slate-500">x{qtyFmt(x.quantity)}</span></span>
                  <span className="text-xs text-slate-600">{x.table ? `${t('restDash.table')} ${x.table}` : `#${x.daily_no}`}</span>
                  {x.station && <span className="text-xs text-slate-500">{x.station}</span>}
                  <span className="text-xs text-rose-700 font-semibold tabular-nums">{x.minutes} {t('restDash.min')} ({t('restDash.norm')} {x.norm})</span>
                </div>
              ))}
            </div>
            {d.kitchen.stations.length > 0 && (
              <div className="px-4 py-2 border-t border-slate-100 flex flex-wrap gap-3 text-xs text-slate-600">
                {d.kitchen.stations.map(s => (
                  <span key={s.station_id ?? 'none'}>{s.name}: {s.queue}{s.late ? <span className="text-rose-700"> ({t('restDash.lateShort')} {s.late})</span> : ''}</span>
                ))}
              </div>
            )}
          </Panel>

          <Panel title={t('restDash.resTitle')} to="/admin/restaurant/reservations" linkLabel={t('restDash.toReservations')}>
            {d.reservations.items.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restDash.noRes')}</div>}
            <div className="divide-y divide-slate-100 max-h-80 overflow-y-auto">
              {d.reservations.items.map(r => (
                <div key={r.id} className="px-4 py-2 flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-semibold tabular-nums w-12">{hhmm(r.starts_at)}</span>
                  <span className="flex-1 min-w-[120px] text-slate-800">{r.name}</span>
                  <span className="text-xs text-slate-600">{r.tables.join(', ')}</span>
                  <span className="text-xs text-slate-600">{r.guests} {t('restDash.ppl')}</span>
                  {r.deposit_held > 0 && <span className="text-xs text-slate-600">{t('restDash.deposit')} {money(r.deposit_held)}</span>}
                  <span className="text-[11px] text-slate-500">{t(`restRes.st.${r.status}`)}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title={t('restDash.stopTitle')} to="/admin/restaurant/stop-list" linkLabel={t('restDash.toStop')}>
            <div className="px-4 py-3 space-y-2 text-sm">
              <div>
                <span className="text-xs text-slate-500">{t('restDash.stopped')}: </span>
                {d.stop_list.stopped.length ? <span className="text-rose-700">{d.stop_list.stopped.join(', ')}</span> : <span className="text-slate-400">{t('restDash.none')}</span>}
              </div>
              <div>
                <span className="text-xs text-slate-500">{t('restDash.lowStock')}: </span>
                {d.stop_list.low.length ? <span className="text-amber-800">{d.stop_list.low.join(', ')}</span> : <span className="text-slate-400">{t('restDash.none')}</span>}
              </div>
            </div>
          </Panel>

          <Panel title={t('restDash.todayTitle')} to="/admin/restaurant/reports" linkLabel={t('restDash.toReports')}>
            <div className="px-4 py-3 grid grid-cols-2 gap-y-1.5 text-sm">
              <span className="text-slate-500">{t('restDash.guests')}</span><span className="text-right tabular-nums">{money(d.today.guests)}</span>
              <span className="text-slate-500">{t('restDash.foodCost')}</span><span className="text-right tabular-nums">{d.today.food_cost_pct == null ? '-' : `${d.today.food_cost_pct}%`}</span>
              <span className="text-slate-500">{t('restDash.discounts')}</span><span className="text-right tabular-nums">{money(d.today.discounts)}</span>
              <span className="text-slate-500">{t('restDash.cancels')}</span><span className="text-right tabular-nums">{money(d.today.cancels)}</span>
              <span className="text-slate-500">{t('restDash.withoutTable')}</span><span className="text-right tabular-nums">{money(d.open.without_table)}</span>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
