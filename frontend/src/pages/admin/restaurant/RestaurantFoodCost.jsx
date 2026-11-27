import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ChevronDown, ChevronRight } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';

// R7.5: food cost nazorati. Tex karta tannarxi joriy ingredient narxidan hisoblanadi; kirimda (xarid, qo'lda kirim)
// yoki menyuda tannarx o'zgarsa server ta'sirlangan taomlarni eski / yangi tannarx bilan yozib qo'yadi.
// Backend: app/services/restaurant_costs.py, GET /restaurant/food-cost va /restaurant/food-cost/changes.

const money = v => Math.round(Number(v) || 0).toLocaleString('uz-UZ');
const pctFmt = v => (v == null ? '' : `${Number(v).toFixed(1)}%`);
const timeFmt = iso => (iso ? new Date(iso).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
const diffPct = (a, b) => (Number(a) > 0 ? ((Number(b) - Number(a)) / Number(a)) * 100 : null);
const errMsg = (err, fb) => {
  const d = err?.response?.data?.detail;
  return typeof d === 'string' ? d : d?.message || fb;
};

function Delta({ from, to }) {
  const d = diffPct(from, to);
  if (d == null || Math.abs(d) < 0.05) return null;
  return <span className={`ml-1 text-[11px] ${d > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>{d > 0 ? '+' : ''}{d.toFixed(1)}%</span>;
}

function ChangeRow({ ev, t }) {
  const [open, setOpen] = useState(ev.over_count > 0);
  const dishes = ev.dishes || [];
  return (
    <div className="px-4 py-2.5 text-sm">
      <div className="flex flex-wrap items-start gap-3">
        <button className="mt-0.5 text-slate-400 hover:text-slate-600" onClick={() => setOpen(o => !o)}>
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <span className="text-xs text-slate-500 w-28">{timeFmt(ev.created_at)}</span>
        <span className="text-xs text-slate-600 w-28">
          {t(`restFc.source.${ev.source}`)}{ev.reference_id ? ` #${ev.reference_id}` : ''}
        </span>
        <span className="flex-1 min-w-[200px] text-slate-800">
          {ev.ingredients.map(i => (
            <span key={i.product_id} className="mr-3 inline-block">
              {i.name}: {money(i.old)} {'->'} <b>{money(i.new)}</b><Delta from={i.old} to={i.new} />
            </span>
          ))}
        </span>
        {ev.over_count > 0
          ? <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[11px] font-semibold">{t('restFc.overN', { n: ev.over_count })}</span>
          : <span className="text-xs text-slate-500">{t('restFc.dishesN', { n: dishes.length })}</span>}
        <span className="text-xs text-slate-400 w-24 truncate text-right">{ev.user_name}</span>
      </div>
      {open && dishes.length > 0 && (
        <div className="mt-2 ml-7 border border-slate-100 rounded-lg overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="text-left px-3 py-1.5 font-semibold">{t('restFc.colDish')}</th>
                <th className="text-right px-3 py-1.5 font-semibold">{t('restFc.colCost')}</th>
                <th className="text-right px-3 py-1.5 font-semibold">{t('restFc.colFoodCost')}</th>
                <th className="text-right px-3 py-1.5 font-semibold">{t('restFc.colPrice')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {dishes.map(d => (
                <tr key={d.product_id} className={d.over ? 'bg-rose-50' : ''}>
                  <td className="px-3 py-1.5 text-slate-800">
                    {d.name}{d.kind === 'semi' && <span className="ml-1.5 text-slate-500">{t('restFc.semiMark')}</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {money(d.old_cost)} {'->'} <b>{money(d.new_cost)}</b><Delta from={d.old_cost} to={d.new_cost} />
                  </td>
                  <td className={`px-3 py-1.5 text-right tabular-nums ${d.over ? 'text-rose-700 font-semibold' : 'text-slate-700'}`}>
                    {d.new_pct == null ? '' : `${pctFmt(d.old_pct)} -> ${pctFmt(d.new_pct)}`}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{d.price == null ? '' : money(d.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function RestaurantFoodCost() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [changes, setChanges] = useState([]);
  const [onlyOver, setOnlyOver] = useState(true);

  const load = useCallback(() => {
    api.get('/restaurant/food-cost')
      .then(r => { setData(r.data); if (!r.data.over_count) setOnlyOver(false); })
      .catch(err => toast.error(errMsg(err, t('restFc.failed'))));
    api.get('/restaurant/food-cost/changes', { params: { limit: 30 }, _silent: true })
      .then(r => setChanges(r.data.items))
      .catch(() => {});
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => (data?.dishes || []).filter(d => !onlyOver || d.over), [data, onlyOver]);

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restFc.title')}</h1>
          <p className="text-sm text-slate-500">{t('restFc.desc')}</p>
        </div>
        {data && (
          <div className="text-sm text-slate-600">
            {t('restFc.threshold')}: <b className="text-slate-800">{pctFmt(data.threshold)}</b>
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 flex flex-wrap items-center gap-3">
          <span className="text-sm font-bold text-slate-800">{t('restFc.dishes')}</span>
          {data && data.over_count > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[11px] font-semibold">{t('restFc.overN', { n: data.over_count })}</span>
          )}
          <label className="ml-auto flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={onlyOver} onChange={e => setOnlyOver(e.target.checked)} />{t('restFc.onlyOver')}
          </label>
        </div>
        {data && rows.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-slate-400">{onlyOver ? t('restFc.noneOver') : t('restFc.noDishes')}</div>
        )}
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="text-left px-4 py-2 font-semibold">{t('restFc.colDish')}</th>
                  <th className="text-right px-3 py-2 font-semibold">{t('restFc.colPrice')}</th>
                  <th className="text-right px-3 py-2 font-semibold">{t('restFc.colCost')}</th>
                  <th className="text-right px-3 py-2 font-semibold">{t('restFc.colFoodCost')}</th>
                  <th className="text-right px-4 py-2 font-semibold">{t('restFc.colSuggested')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map(d => (
                  <tr key={d.product_id}>
                    <td className="px-4 py-2 text-slate-800">{d.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{d.no_price ? <span className="text-amber-700">{t('restFc.noPrice')}</span> : money(d.price)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-600">{money(d.cost)}</td>
                    <td className={`px-3 py-2 text-right tabular-nums font-semibold ${d.over ? 'text-rose-600' : 'text-emerald-700'}`}>{pctFmt(d.pct)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-700">{d.suggested_price ? money(d.suggested_price) : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-4 py-2 border-t border-slate-100 text-xs text-slate-500">
          {t('restFc.fixHint')} <Link className="text-blue-700 hover:underline" to="/admin/restaurant/menu">{t('restFc.toMenu')}</Link>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restFc.changes')}</div>
        {changes.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restFc.noChanges')}</div>}
        <div className="divide-y divide-slate-100">
          {changes.map(ev => <ChangeRow key={ev.id} ev={ev} t={t} />)}
        </div>
      </div>
    </div>
  );
}
