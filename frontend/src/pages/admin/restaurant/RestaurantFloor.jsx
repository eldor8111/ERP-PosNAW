import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import toast from 'react-hot-toast';
import { Plus, Save, Trash2, X } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';
import { useAuth } from '../../../context/AuthContext';

// R2: zallar va stollar. Stollarni sudrab joylash va o'lchamini o'zgartirish (pointer events: sichqoncha va sensor).
// Backend: app/routers/restaurant_floor.py. Stol holatlari (band, hisob so'ralgan) R3 cheklari bilan qo'shiladi.

const CELL = 28;          // 1 katak = 28px
const GRID_MAX = 200;
const SIZE_MAX = 20;
const EDIT_ROLES = ['super_admin', 'admin', 'director', 'manager'];

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btnPrimary = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50';
const btnGhost = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold disabled:opacity-50';

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-slate-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

function HallModal({ hall, branchId, onClose, onSaved, t }) {
  const [name, setName] = useState(hall?.name || '');
  const [svc, setSvc] = useState(hall?.service_pct ?? '');
  const [saving, setSaving] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    const body = { name: name.trim() };
    if (svc === '' || svc === null) { if (hall) body.clear_service_pct = true; }
    else body.service_pct = Number(String(svc).replace(',', '.'));
    setSaving(true);
    try {
      if (hall) await api.put(`/restaurant/halls/${hall.id}`, body);
      else await api.post('/restaurant/halls', { ...body, branch_id: branchId });
      toast.success(t('restFloor.saved'));
      onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('restFloor.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const deactivate = async () => {
    if (!window.confirm(t('restFloor.confirmHallOff'))) return;
    try {
      await api.put(`/restaurant/halls/${hall.id}`, { is_active: false });
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || t('restFloor.saveFailed')); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center p-4" onMouseDown={onClose}>
      <form onSubmit={save} onMouseDown={e => e.stopPropagation()}
            className="bg-white rounded-xl border border-slate-200 w-full max-w-sm mt-20 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-800">{hall ? t('restFloor.editHall') : t('restFloor.addHall')}</h3>
          <button type="button" onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <Field label={t('restFloor.hallName')}>
          <input className={inputCls} value={name} onChange={e => setName(e.target.value)} maxLength={100} autoFocus />
        </Field>
        <Field label={t('restFloor.servicePct')}>
          <input className={inputCls} inputMode="decimal" value={svc} onChange={e => setSvc(e.target.value)} placeholder={t('restFloor.servicePctHint')} />
        </Field>
        <div className="flex justify-between gap-2 pt-1">
          {hall ? <button type="button" className="text-sm text-rose-600 hover:underline" onClick={deactivate}>{t('restFloor.hallOff')}</button> : <span />}
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>{t('restFloor.cancel')}</button>
            <button type="submit" className={btnPrimary} disabled={saving || !name.trim()}>{t('restFloor.save')}</button>
          </div>
        </div>
      </form>
    </div>
  );
}

function TablePanel({ table, onChange, onSave, onDelete, onClose, t }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-800">{t('restFloor.table')} {table.name}</h3>
        <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label={t('restFloor.tableName')}>
          <input className={inputCls} value={table.name} maxLength={50} onChange={e => onChange({ name: e.target.value })} />
        </Field>
        <Field label={t('restFloor.seats')}>
          <input className={inputCls} inputMode="numeric" value={table.seats} onChange={e => onChange({ seats: e.target.value })} />
        </Field>
        <Field label={t('restFloor.width')}>
          <input className={inputCls} inputMode="numeric" value={table.w} onChange={e => onChange({ w: clamp(parseInt(e.target.value, 10) || 1, 1, SIZE_MAX) })} />
        </Field>
        <Field label={t('restFloor.height')}>
          <input className={inputCls} inputMode="numeric" value={table.h} onChange={e => onChange({ h: clamp(parseInt(e.target.value, 10) || 1, 1, SIZE_MAX) })} />
        </Field>
      </div>
      <div className="flex gap-2">
        {['rect', 'round'].map(s => (
          <button key={s} type="button" onClick={() => onChange({ shape: s })}
                  className={`flex-1 px-2 py-1.5 rounded-lg border text-xs font-semibold ${table.shape === s ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200 text-slate-600'}`}>
            {t(`restFloor.shape.${s}`)}
          </button>
        ))}
      </div>
      <div className="flex justify-between">
        <button type="button" className="inline-flex items-center gap-1 text-sm text-rose-600 hover:underline" onClick={onDelete}>
          <Trash2 className="w-4 h-4" />{t('restFloor.removeTable')}
        </button>
        <button type="button" className={btnPrimary} onClick={onSave}>{t('restFloor.save')}</button>
      </div>
    </div>
  );
}

export default function RestaurantFloor() {
  const { t } = useLang();
  const { user } = useAuth();
  const canEdit = EDIT_ROLES.includes(user?.role);
  const { branches, currentBranchId, assignedBranchId } = useBranch();

  const [branchId, setBranchId] = useState(null);
  const [halls, setHalls] = useState([]);
  const [hallId, setHallId] = useState(null);
  const [tables, setTables] = useState([]);       // joriy zal stollari (lokal, sudrash uchun)
  const [dirty, setDirty] = useState(false);
  const [selected, setSelected] = useState(null);
  const [hallModal, setHallModal] = useState(null);   // {hall|null}
  const [loading, setLoading] = useState(false);
  const drag = useRef(null);

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const load = useCallback((keepHall, selectId = null) => {
    if (!branchId) return Promise.resolve();
    setLoading(true);
    return api.get('/restaurant/halls', { params: { branch_id: branchId } })
      .then(r => {
        setHalls(r.data);
        const h = r.data.find(x => x.id === keepHall) || r.data[0] || null;
        setHallId(h?.id ?? null);
        setTables(h ? h.tables.map(x => ({ ...x })) : []);
        setDirty(false);
        setSelected(selectId);
      })
      .catch(err => toast.error(err.response?.data?.detail || t('restFloor.loadFailed')))
      .finally(() => setLoading(false));
  }, [branchId, t]);

  useEffect(() => { load(); }, [load]);

  const hall = halls.find(h => h.id === hallId) || null;

  const selectHall = (id) => {
    if (dirty && !window.confirm(t('restFloor.unsaved'))) return;
    const h = halls.find(x => x.id === id);
    setHallId(id);
    setTables(h ? h.tables.map(x => ({ ...x })) : []);
    setDirty(false);
    setSelected(null);
  };

  const size = useMemo(() => {
    const w = Math.max(30, ...tables.map(x => x.x + x.w + 2));
    const h = Math.max(18, ...tables.map(x => x.y + x.h + 2));
    return { w: Math.min(w, GRID_MAX), h: Math.min(h, GRID_MAX) };
  }, [tables]);

  // ── sudrash va o'lcham ──
  const onPointerDown = (e, tb, mode) => {
    if (!canEdit) { setSelected(tb.id); return; }
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = { id: tb.id, mode, sx: e.clientX, sy: e.clientY, x: tb.x, y: tb.y, w: tb.w, h: tb.h, moved: false };
    setSelected(tb.id);
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = Math.round((e.clientX - d.sx) / CELL);
    const dy = Math.round((e.clientY - d.sy) / CELL);
    if (!dx && !dy && !d.moved) return;
    d.moved = true;
    setTables(ts => ts.map(x => {
      if (x.id !== d.id) return x;
      if (d.mode === 'move') return { ...x, x: clamp(d.x + dx, 0, GRID_MAX - x.w), y: clamp(d.y + dy, 0, GRID_MAX - x.h) };
      return { ...x, w: clamp(d.w + dx, 1, SIZE_MAX), h: clamp(d.h + dy, 1, SIZE_MAX) };
    }));
    setDirty(true);
  };
  const onPointerUp = () => { drag.current = null; };

  const saveLayout = async () => {
    if (!hall) return;
    try {
      await api.put(`/restaurant/halls/${hall.id}/layout`, {
        tables: tables.map(x => ({ id: x.id, x: x.x, y: x.y, w: x.w, h: x.h, shape: x.shape })),
      });
      toast.success(t('restFloor.layoutSaved'));
      load(hall.id);
    } catch (err) { toast.error(err.response?.data?.detail || t('restFloor.saveFailed')); }
  };

  const addTable = async () => {
    if (!hall) return;
    if (dirty) await saveLayout();
    try {
      const r = await api.post(`/restaurant/halls/${hall.id}/tables`, {});
      await load(hall.id, r.data.id);
    } catch (err) { toast.error(err.response?.data?.detail || t('restFloor.saveFailed')); }
  };

  const sel = tables.find(x => x.id === selected) || null;
  const patchSel = (p) => { setTables(ts => ts.map(x => (x.id === selected ? { ...x, ...p } : x))); };
  const saveTable = async () => {
    if (!sel) return;
    try {
      // boshqa stollarning saqlanmagan joylashuvi yo'qolmasin
      if (dirty) {
        await api.put(`/restaurant/halls/${hall.id}/layout`, {
          tables: tables.map(x => ({ id: x.id, x: x.x, y: x.y, w: x.w, h: x.h, shape: x.shape })),
        });
      }
      await api.put(`/restaurant/tables/${sel.id}`, {
        name: String(sel.name).trim(), seats: parseInt(sel.seats, 10) || 1, shape: sel.shape,
        x: sel.x, y: sel.y, w: sel.w, h: sel.h,
      });
      toast.success(t('restFloor.saved'));
      load(hall.id, sel.id);
    } catch (err) { toast.error(err.response?.data?.detail || t('restFloor.saveFailed')); }
  };
  const removeTable = async () => {
    if (!sel || !window.confirm(`${t('restFloor.confirmRemove')}: ${sel.name}?`)) return;
    try {
      await api.delete(`/restaurant/tables/${sel.id}`);
      load(hall.id);
    } catch (err) { toast.error(err.response?.data?.detail || t('restFloor.saveFailed')); }
  };

  const seatsTotal = tables.reduce((s, x) => s + (parseInt(x.seats, 10) || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restFloor.title')}</h1>
          <p className="text-sm text-slate-500">{t('restFloor.desc')}</p>
        </div>
        {branches.length > 1 && (
          <select className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white" value={branchId ?? ''}
                  onChange={e => { if (!dirty || window.confirm(t('restFloor.unsaved'))) { setBranchId(Number(e.target.value)); } }}>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200">
        {halls.map(h => (
          <button key={h.id} onClick={() => selectHall(h.id)} onDoubleClick={() => canEdit && setHallModal({ hall: h })}
                  className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${h.id === hallId ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {h.name}
            {h.service_pct != null && <span className="ml-1 text-[11px] text-slate-400">{h.service_pct}%</span>}
          </button>
        ))}
        {canEdit && (
          <button onClick={() => setHallModal({ hall: null })} className="px-3 py-2 text-sm text-slate-500 hover:text-blue-700 inline-flex items-center gap-1">
            <Plus className="w-4 h-4" />{t('restFloor.addHall')}
          </button>
        )}
      </div>

      {loading && <div className="py-10 text-center text-sm text-slate-400">{t('restFloor.loading')}</div>}
      {!loading && !hall && <div className="py-10 text-center text-sm text-slate-400">{t('restFloor.noHalls')}</div>}

      {!loading && hall && (
        <div className="grid lg:grid-cols-[1fr_280px] gap-4 items-start">
          <div className="bg-white border border-slate-200 rounded-xl">
            <div className="px-3 py-2 flex flex-wrap items-center gap-2 border-b border-slate-100">
              <span className="text-xs text-slate-500">{t('restFloor.tablesCount')}: <b className="text-slate-700">{tables.length}</b></span>
              <span className="text-xs text-slate-500">{t('restFloor.seatsTotal')}: <b className="text-slate-700">{seatsTotal}</b></span>
              <div className="flex-1" />
              {canEdit && (
                <>
                  <button className={btnGhost} onClick={() => setHallModal({ hall })}>{t('restFloor.editHall')}</button>
                  <button className={btnGhost} onClick={addTable}><Plus className="w-4 h-4" />{t('restFloor.addTable')}</button>
                  <button className={btnPrimary} onClick={saveLayout} disabled={!dirty}><Save className="w-4 h-4" />{t('restFloor.saveLayout')}</button>
                </>
              )}
            </div>
            <div className="overflow-auto p-3" style={{ maxHeight: '70vh' }}>
              <div
                className="relative select-none touch-none bg-slate-50 border border-slate-100 rounded-lg"
                style={{
                  width: size.w * CELL, height: size.h * CELL,
                  backgroundImage: 'linear-gradient(to right, rgba(148,163,184,.18) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,.18) 1px, transparent 1px)',
                  backgroundSize: `${CELL}px ${CELL}px`,
                }}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerLeave={onPointerUp}
                onPointerDown={() => setSelected(null)}
              >
                {tables.map(tb => (
                  <div key={tb.id}
                       onPointerDown={e => onPointerDown(e, tb, 'move')}
                       className={`absolute flex flex-col items-center justify-center border-2 text-slate-700 bg-white ${canEdit ? 'cursor-move' : 'cursor-pointer'} ${tb.shape === 'round' ? 'rounded-full' : 'rounded-lg'} ${tb.id === selected ? 'border-blue-600' : 'border-slate-300'}`}
                       style={{ left: tb.x * CELL + 2, top: tb.y * CELL + 2, width: tb.w * CELL - 4, height: tb.h * CELL - 4 }}>
                    <span className="text-sm font-bold leading-none">{tb.name}</span>
                    <span className="text-[10px] text-slate-400 mt-0.5">{tb.seats}</span>
                    {canEdit && tb.id === selected && (
                      <span onPointerDown={e => onPointerDown(e, tb, 'resize')}
                            className="absolute -right-1.5 -bottom-1.5 w-3.5 h-3.5 bg-blue-600 rounded-sm cursor-nwse-resize" />
                    )}
                  </div>
                ))}
              </div>
            </div>
            {canEdit && <p className="px-3 pb-3 text-[11px] text-slate-500">{t('restFloor.dragHint')}</p>}
          </div>

          {sel && canEdit && (
            <TablePanel table={sel} onChange={p => { patchSel(p); if ('w' in p || 'h' in p || 'shape' in p) setDirty(true); }}
                        onSave={saveTable} onDelete={removeTable} onClose={() => setSelected(null)} t={t} />
          )}
        </div>
      )}

      {hallModal && (
        <HallModal hall={hallModal.hall} branchId={branchId} t={t}
                   onClose={() => setHallModal(null)}
                   onSaved={() => { setHallModal(null); load(hallModal.hall?.id ?? hallId); }} />
      )}
    </div>
  );
}
