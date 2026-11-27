import { useState, useEffect, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
import { Maximize2 } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R4.2: oshxona ekrani (KDS). Planshet yoki brauzerli televizorda ochiladi. Backend: app/routers/restaurant_kds.py.
// Har 5 soniyada yangilanadi. Taomni bosish: yuborildi -> tayyorlanmoqda -> tayyor. Norma (tex karta) oshsa
// kartochka sariq, ikki baravar oshsa qizil — rang yonida yozuv ham bor.

const POLL_MS = 5000;
const NEXT = { sent: 'cooking', cooking: 'ready' };
const ITEM_STYLE = {
  sent: 'bg-white', cooking: 'bg-blue-50', ready: 'bg-emerald-50 text-emerald-800',
  cancelled: 'bg-rose-50 text-rose-700 line-through',
};

const mmss = sec => {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};
const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });

function Card({ card, now, onItem, onBulk, hideReady, t }) {
  const items = hideReady ? card.items.filter(i => i.status !== 'ready') : card.items;
  // kechikish: tayyor bo'lmagan taomlar bo'yicha eng katta "o'tgan vaqt / norma"
  let worst = 0;
  for (const i of card.items) {
    if (!['sent', 'cooking'].includes(i.status) || !i.norm_min || !i.sent_at) continue;
    worst = Math.max(worst, (now - Date.parse(i.sent_at)) / 60000 / i.norm_min);
  }
  const level = worst > 2 ? 'late2' : worst > 1 ? 'late1' : 'ok';
  const border = level === 'late2' ? 'border-rose-500' : level === 'late1' ? 'border-amber-500' : 'border-slate-200';
  const elapsed = card.first_sent_at ? (now - Date.parse(card.first_sent_at)) / 1000 : 0;
  const pending = card.items.filter(i => i.status === 'sent').map(i => i.id);
  const notReady = card.items.filter(i => ['sent', 'cooking'].includes(i.status)).map(i => i.id);
  if (items.length === 0) return null;
  return (
    <div className={`bg-white border-2 ${border} rounded-xl flex flex-col`}>
      <div className="px-3 py-2 border-b border-slate-100 flex items-start justify-between gap-2">
        <div>
          <div className="text-lg font-bold text-slate-900 leading-tight">
            #{card.daily_no} {card.table_name ? `· ${t('restKds.table')} ${card.table_name}` : `· ${t(`restOrd.type.${card.order_type}`)}`}
          </div>
          <div className="text-xs text-slate-500">{card.waiter_name}{card.guests ? ` · ${card.guests} ${t('restKds.guests')}` : ''}</div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold tabular-nums text-slate-800">{mmss(elapsed)}</div>
          {level !== 'ok' && (
            <div className={`text-[11px] font-semibold ${level === 'late2' ? 'text-rose-700' : 'text-amber-700'}`}>
              {t(level === 'late2' ? 'restKds.veryLate' : 'restKds.late')}
            </div>
          )}
        </div>
      </div>
      {card.comment && <div className="px-3 py-1 text-xs text-slate-600 border-b border-slate-100">{card.comment}</div>}
      <div className="flex-1 divide-y divide-slate-100">
        {items.map(i => (
          <button key={i.id} disabled={!NEXT[i.status]} onClick={() => onItem(i)}
                  className={`w-full text-left px-3 py-2 ${ITEM_STYLE[i.status] || ''} disabled:cursor-default`}>
            <div className="flex items-baseline gap-2">
              <span className="text-base font-semibold">{qtyFmt(i.quantity)} x {i.name}</span>
              {i.course > 1 && <span className="text-[11px] text-slate-500">{i.course}-{t('restKds.course')}</span>}
              <span className="ml-auto text-[11px] font-semibold uppercase">{t(`restOrd.item.${i.status}`)}</span>
            </div>
            {i.modifiers?.length > 0 && <div className="text-sm font-semibold text-blue-800">{i.modifiers.join(', ')}</div>}
            {i.comment && <div className="text-sm text-amber-800">{i.comment}</div>}
            {i.status === 'cancelled' && i.cancel_reason && (
              <div className="text-[11px] no-underline">{t(`restOrd.reason.${String(i.cancel_reason).split(':')[0]}`)}</div>
            )}
          </button>
        ))}
      </div>
      <div className="p-2 grid grid-cols-2 gap-2 border-t border-slate-100">
        <button disabled={!pending.length} onClick={() => onBulk(pending, 'cooking')}
                className="py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold disabled:opacity-40">{t('restKds.start')}</button>
        <button disabled={!notReady.length} onClick={() => onBulk(notReady, 'ready')}
                className="py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold disabled:opacity-40">{t('restKds.allReady')}</button>
      </div>
    </div>
  );
}

export default function RestaurantKds() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [stations, setStations] = useState([]);
  const [station, setStation] = useState(() => { try { return localStorage.getItem('kds_station') || ''; } catch { return ''; } });
  const [data, setData] = useState(null);
  const [hideReady, setHideReady] = useState(false);
  const [now, setNow] = useState(Date.now());
  const offset = useRef(0);   // server soati bilan farq

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  useEffect(() => { api.get('/restaurant/stations').then(r => setStations(r.data.filter(s => s.is_active))).catch(() => {}); }, []);

  const load = useCallback(() => {
    if (!branchId) return;
    const params = { branch_id: branchId };
    if (station) params.station = station;
    api.get('/restaurant/kds', { params, _silent: true })
      .then(r => {
        offset.current = Date.parse(r.data.server_time) - Date.now();
        setData(r.data);
      })
      .catch(err => { if (err.response?.status === 403) toast.error(err.response.data?.detail || t('restKds.noAccess')); });
  }, [branchId, station, t]);

  useEffect(() => {
    load();
    const p = setInterval(load, POLL_MS);
    return () => clearInterval(p);
  }, [load]);
  useEffect(() => {
    const c = setInterval(() => setNow(Date.now() + offset.current), 1000);
    return () => clearInterval(c);
  }, []);

  const pickStation = v => {
    setStation(v);
    try { localStorage.setItem('kds_station', v); } catch { /* saqlash ixtiyoriy */ }
  };

  const change = async (ids, status) => {
    try {
      await api.post('/restaurant/kds/status', { item_ids: ids, status });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('restKds.failed'));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-bold text-slate-800 mr-2">{t('restKds.title')}</h1>
        <div className="flex flex-wrap gap-1">
          {[{ v: '', name: t('restKds.allStations') }, ...stations.map(s => ({ v: String(s.id), name: s.name })),
            { v: 'none', name: t('restKds.noStation') }].map(s => (
            <button key={s.v || 'all'} onClick={() => pickStation(s.v)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-semibold ${station === s.v ? 'bg-slate-800 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}>
              {s.name}
            </button>
          ))}
        </div>
        {branches.length > 1 && (
          <select className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white" value={branchId ?? ''}
                  onChange={e => setBranchId(Number(e.target.value))}>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
        <label className="flex items-center gap-1 text-sm text-slate-600 ml-auto">
          <input type="checkbox" checked={hideReady} onChange={e => setHideReady(e.target.checked)} />{t('restKds.hideReady')}
        </label>
        <button title={t('restKds.fullscreen')} className="p-2 rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => document.documentElement.requestFullscreen?.().catch(() => {})}>
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {data?.totals?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="text-slate-500">{t('restKds.totals')}:</span>
          {data.totals.map(x => <span key={x.name} className="font-semibold text-slate-800">{x.name} {qtyFmt(x.quantity)}</span>)}
        </div>
      )}

      {data && data.cards.length === 0 && (
        <div className="py-20 text-center text-slate-400">{t('restKds.empty')}</div>
      )}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-3 items-start">
        {data?.cards.map(c => (
          <Card key={c.order_id} card={c} now={now} hideReady={hideReady} t={t}
                onItem={i => change([i.id], NEXT[i.status])} onBulk={change} />
        ))}
      </div>
    </div>
  );
}
