import { useState, useEffect, useCallback, useMemo } from 'react';
import toast from 'react-hot-toast';
import { Search, X, Ban, RotateCcw } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R1.5: stop-list. Taomni filial bo'yicha vaqtincha sotuvdan olish (sabab, qachongacha), "qoldi N porsiya"
// hisoblagichi, ingredient yetishmasligi va avtomatik stop sozlamasi. Backend: app/routers/restaurant_stops.py.
// Buyurtma ekrani ham shu ro'yxatdan oladi, backend esa chekka qo'shishda qayta tekshiradi.

const REFRESH_MS = 15000;
const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btnPrimary = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50';
const btnGhost = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold disabled:opacity-50';
const UNTIL = ['none', '1h', '3h', 'today', 'custom'];

const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });
const timeFmt = iso => (iso ? new Date(iso).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');

function untilFrom(mode, custom) {
  const now = new Date();
  if (mode === '1h') return new Date(now.getTime() + 3600e3).toISOString();
  if (mode === '3h') return new Date(now.getTime() + 3 * 3600e3).toISOString();
  if (mode === 'today') { const d = new Date(now); d.setHours(23, 59, 0, 0); return d.toISOString(); }
  if (mode === 'custom' && custom) return new Date(custom).toISOString();
  return null;
}

function StopModal({ item, current, onClose, onSave, t }) {
  const [stopped, setStopped] = useState(current ? current.stopped : true);
  const [reason, setReason] = useState(current?.reason || '');
  const [untilMode, setUntilMode] = useState(current?.until ? 'custom' : 'none');
  const [custom, setCustom] = useState(() => {
    if (!current?.until) return '';
    const d = new Date(current.until);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60e3).toISOString().slice(0, 16);
  });
  const [useCounter, setUseCounter] = useState(current?.remaining != null);
  const [remaining, setRemaining] = useState(current?.remaining != null ? String(current.remaining) : '');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    await onSave({
      stopped, reason: stopped ? reason : null,
      until: stopped ? untilFrom(untilMode, custom) : null,
      remaining: useCounter ? Number(String(remaining || 0).replace(',', '.')) : null,
    });
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className="bg-white rounded-xl border border-slate-200 w-full max-w-md mt-16" onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{item.name}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <input type="checkbox" checked={stopped} onChange={e => setStopped(e.target.checked)} />{t('restStop.stopNow')}
          </label>
          {stopped && (
            <>
              <input className={inputCls} value={reason} maxLength={200} placeholder={t('restStop.reasonPh')}
                     onChange={e => setReason(e.target.value)} />
              <div>
                <span className="block text-xs font-semibold text-slate-600 mb-1">{t('restStop.until')}</span>
                <div className="flex flex-wrap gap-1.5">
                  {UNTIL.map(m => (
                    <button key={m} type="button" onClick={() => setUntilMode(m)}
                            className={`px-2.5 py-1.5 rounded-lg border text-xs ${untilMode === m ? 'border-blue-600 bg-blue-50 text-blue-800 font-semibold' : 'border-slate-200 text-slate-600'}`}>
                      {t(`restStop.until.${m}`)}
                    </button>
                  ))}
                </div>
                {untilMode === 'custom' && (
                  <input type="datetime-local" className={`${inputCls} mt-2`} value={custom} onChange={e => setCustom(e.target.value)} />
                )}
              </div>
            </>
          )}
          <div className="border-t border-slate-100 pt-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <input type="checkbox" checked={useCounter} onChange={e => setUseCounter(e.target.checked)} />{t('restStop.counter')}
            </label>
            <p className="text-xs text-slate-500 mt-1">{t('restStop.counterHint')}</p>
            {useCounter && (
              <input className={`${inputCls} mt-2`} inputMode="decimal" value={remaining} placeholder={t('restStop.portionsLeft')}
                     onChange={e => setRemaining(e.target.value)} />
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button className={btnGhost} onClick={onClose}>{t('restStop.cancel')}</button>
            <button className={btnPrimary} disabled={busy || (untilMode === 'custom' && stopped && !custom)} onClick={save}>{t('restStop.save')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function RestaurantStopList() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [data, setData] = useState(null);
  const [menu, setMenu] = useState([]);
  const [q, setQ] = useState('');
  const [edit, setEdit] = useState(null);     // {item, current}

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const load = useCallback(() => {
    if (!branchId) return;
    api.get('/restaurant/stop-list', { params: { branch_id: branchId }, _silent: true })
      .then(r => setData(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restStop.failed')));
  }, [branchId, t]);
  useEffect(() => { load(); const p = setInterval(load, REFRESH_MS); return () => clearInterval(p); }, [load]);
  useEffect(() => { api.get('/restaurant/menu/items', { params: { kind: 'dish,goods' } }).then(r => setMenu(r.data)).catch(() => {}); }, []);

  const byId = useMemo(() => Object.fromEntries((data?.stops || []).map(s => [s.product_id, s])), [data]);
  const lowIds = useMemo(() => new Set((data?.low || []).map(x => x.product_id)), [data]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return menu.filter(m => !s || m.name.toLowerCase().includes(s));
  }, [menu, q]);
  const canEdit = !!data?.can_edit;

  const save = async (item, body) => {
    try {
      await api.put(`/restaurant/stop-list/${item.id}`, { branch_id: branchId, ...body });
      toast.success(t('restStop.saved'));
      setEdit(null);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restStop.failed')); }
  };
  const unstop = async pid => {
    try {
      await api.delete(`/restaurant/stop-list/${pid}`, { params: { branch_id: branchId } });
      toast.success(t('restStop.backOnSale'));
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restStop.failed')); }
  };
  const setAuto = async v => {
    try {
      await api.put('/restaurant/settings', { auto_stop_on_no_stock: v });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restStop.failed')); }
  };
  const openEdit = (pid, name) => setEdit({ item: { id: pid, name }, current: byId[pid] || null });

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restStop.title')}</h1>
          <p className="text-sm text-slate-500">{t('restStop.desc')}</p>
        </div>
        {branches.length > 1 && (
          <select className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restStop.stopped')}</div>
        <div className="divide-y divide-slate-100">
          {data && data.stops.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restStop.noneStopped')}</div>}
          {(data?.stops || []).map(s => (
            <div key={s.product_id} className={`px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm ${s.effective ? '' : 'opacity-60'}`}>
              <span className="font-semibold text-slate-800 min-w-[140px]">{s.name}</span>
              {s.effective
                ? <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[11px] font-semibold">{t('restStop.badgeStop')}</span>
                : s.expired && <span className="text-[11px] text-slate-500">{t('restStop.expired')}</span>}
              {s.remaining != null && <span className="text-xs text-slate-700">{t('restStop.left')}: {qtyFmt(s.remaining)}</span>}
              {s.reason && <span className="text-xs text-slate-600">{s.reason}</span>}
              {s.until && !s.expired && <span className="text-xs text-slate-500">{t('restStop.untilShort')} {timeFmt(s.until)}</span>}
              <span className="ml-auto text-[11px] text-slate-400">{s.updated_by} {timeFmt(s.updated_at)}</span>
              {canEdit && (
                <>
                  <button className={btnGhost} onClick={() => openEdit(s.product_id, s.name)}>{t('restStop.edit')}</button>
                  <button className={btnGhost} onClick={() => unstop(s.product_id)}><RotateCcw className="w-4 h-4" />{t('restStop.backOnSale')}</button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 flex flex-wrap items-center gap-3">
          <span className="text-sm font-bold text-slate-800">{t('restStop.lowTitle')}</span>
          <label className="ml-auto flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={!!data?.auto_stop} disabled={!data} onChange={e => setAuto(e.target.checked)} />
            {t('restStop.autoStop')}
          </label>
        </div>
        <p className="px-4 pt-2 text-xs text-slate-500">{t('restStop.lowHint')}</p>
        <div className="divide-y divide-slate-100">
          {data && data.low.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restStop.noneLow')}</div>}
          {(data?.low || []).map(x => (
            <div key={x.product_id} className="px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm">
              <span className="font-semibold text-slate-800 min-w-[140px]">{x.name}</span>
              <span className="text-xs text-amber-800">
                {x.missing.map(m => `${m.name}: ${qtyFmt(m.have)} / ${qtyFmt(m.need)} ${m.unit || ''}`).join(', ')}
              </span>
              {canEdit && !byId[x.product_id]?.effective && (
                <button className={`${btnGhost} ml-auto`} onClick={() => openEdit(x.product_id, x.name)}><Ban className="w-4 h-4" />{t('restStop.stop')}</button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="p-3 border-b border-slate-100 flex items-center gap-2">
          <span className="text-sm font-bold text-slate-800 whitespace-nowrap">{t('restStop.allMenu')}</span>
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className={`${inputCls} pl-9`} value={q} onChange={e => setQ(e.target.value)} placeholder={t('restStop.search')} />
          </div>
        </div>
        <div className="divide-y divide-slate-100 max-h-[480px] overflow-y-auto">
          {shown.map(m => {
            const s = byId[m.id];
            const off = data?.unavailable?.includes(m.id);
            const portions = data?.portions?.[String(m.id)];
            return (
              <div key={m.id} className="px-4 py-2 flex items-center gap-3 text-sm">
                <span className={`flex-1 ${off ? 'text-rose-700 font-semibold' : 'text-slate-800'}`}>{m.name}</span>
                {off && <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[11px] font-semibold">{t('restStop.badgeStop')}</span>}
                {!off && s?.remaining != null && <span className="text-xs text-slate-700">{t('restStop.left')}: {qtyFmt(s.remaining)}</span>}
                {!off && lowIds.has(m.id) && <span className="text-xs text-amber-700">{t('restStop.badgeLow')}</span>}
                {portions != null && !lowIds.has(m.id) && <span className="text-[11px] text-slate-400">{t('restStop.enoughFor')} {portions}</span>}
                {canEdit && (s
                  ? <button className="text-xs text-blue-700 hover:underline" onClick={() => openEdit(m.id, m.name)}>{t('restStop.edit')}</button>
                  : <button className="text-xs text-blue-700 hover:underline" onClick={() => openEdit(m.id, m.name)}>{t('restStop.stop')}</button>)}
              </div>
            );
          })}
        </div>
      </div>

      {edit && <StopModal item={edit.item} current={edit.current} t={t} onClose={() => setEdit(null)} onSave={body => save(edit.item, body)} />}
    </div>
  );
}
