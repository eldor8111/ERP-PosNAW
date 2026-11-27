import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { X, Plus, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R8.1: stol bron qilish. Kun bo'yicha jadval (stollar x soatlar) va ro'yxat; bir stolga vaqt kesishsa server rad
// etadi (409 TABLE_BUSY). Depozit bron paytida kassaga kirim qilinadi va chek yopilganda o'zi hisobga olinadi.
// Backend: app/routers/restaurant_reservations.py.

const HOUR_W = 64;
const ROW_H = 40;
const DURATIONS = [60, 90, 120, 180, 240];
const PAY_TYPES = ['cash', 'card', 'uzcard', 'humo', 'click', 'payme', 'uzum'];
const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btn = 'inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold disabled:opacity-50';
const btnPrimary = `${btn} bg-blue-600 hover:bg-blue-700 text-white`;
const btnGhost = `${btn} border border-slate-200 bg-white hover:bg-slate-50 text-slate-700`;
const btnDanger = `${btn} border border-rose-200 bg-white hover:bg-rose-50 text-rose-700`;
const BLOCK = {
  booked: 'bg-blue-50 border-blue-400 text-blue-900',
  arrived: 'bg-emerald-50 border-emerald-500 text-emerald-900',
  no_show: 'bg-slate-50 border-slate-300 text-slate-500',
  cancelled: 'bg-slate-50 border-slate-300 text-slate-400 line-through',
};

const money = v => Math.round(Number(v) || 0).toLocaleString('uz-UZ');
const pad = n => String(n).padStart(2, '0');
const isoDate = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hhmm = iso => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const addDays = (s, n) => { const d = new Date(`${s}T12:00:00`); d.setDate(d.getDate() + n); return isoDate(d); };
const errMsg = (err, fb) => {
  const d = err?.response?.data?.detail;
  return typeof d === 'string' ? d : d?.message || fb;
};

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className={`bg-white rounded-xl border border-slate-200 w-full ${wide ? 'max-w-2xl' : 'max-w-md'} mt-10`} onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-slate-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

function FormModal({ branchId, tables, init, canPay, defaultDuration, onClose, onSaved, t }) {
  const editing = !!init?.id;
  const [f, setF] = useState(() => ({
    date: init?.date, time: init?.time || '19:00', duration: String(init?.duration_min || defaultDuration || 120),
    guests: String(init?.guests || 2), table_ids: init?.table_ids || [], name: init?.name || '', phone: init?.phone || '',
    note: init?.note || '', deposit: '', deposit_type: 'cash',
  }));
  const [busy, setBusy] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const toggle = id => set('table_ids', f.table_ids.includes(id) ? f.table_ids.filter(x => x !== id) : [...f.table_ids, id]);

  useEffect(() => {
    if (!f.date || !/^\d{2}:\d{2}$/.test(f.time)) return undefined;
    const h = setTimeout(() => {
      api.get('/restaurant/reservations/free-tables', {
        params: { branch_id: branchId, starts_at: `${f.date}T${f.time}:00`, duration_min: Number(f.duration) || 120, exclude_id: init?.id },
        _silent: true,
      }).then(r => setBusy(r.data.busy)).catch(() => setBusy([]));
    }, 250);
    return () => clearTimeout(h);
  }, [branchId, f.date, f.time, f.duration, init?.id]);

  const seats = tables.filter(x => f.table_ids.includes(x.id)).reduce((s, x) => s + (x.seats || 0), 0);
  const clash = f.table_ids.some(id => busy.includes(id));

  const save = async () => {
    setSaving(true);
    const body = {
      starts_at: `${f.date}T${f.time}:00`, duration_min: Number(f.duration) || 120, guests: Number(f.guests) || 1,
      table_ids: f.table_ids, name: f.name, phone: f.phone || null, note: f.note || null,
    };
    try {
      if (editing) await api.put(`/restaurant/reservations/${init.id}`, body);
      else {
        const dep = Number(String(f.deposit || '').replace(/\s/g, '').replace(',', '.'));
        await api.post('/restaurant/reservations', {
          ...body, branch_id: branchId, ...(dep > 0 ? { deposit_amount: dep, deposit_type: f.deposit_type } : {}),
        });
      }
      toast.success(t('restRes.saved'));
      onSaved();
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d?.code === 'TABLE_BUSY') toast.error(d.message, { duration: 7000 });
      else toast.error(errMsg(err, t('restRes.failed')));
    }
    setSaving(false);
  };

  return (
    <Modal wide title={editing ? t('restRes.editTitle') : t('restRes.newTitle')} onClose={onClose}>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label={t('restRes.date')}><input type="date" className={inputCls} value={f.date} onChange={e => set('date', e.target.value)} /></Field>
        <Field label={t('restRes.time')}><input type="time" step="900" className={inputCls} value={f.time} onChange={e => set('time', e.target.value)} /></Field>
        <Field label={t('restRes.duration')}>
          <select className={inputCls} value={f.duration} onChange={e => set('duration', e.target.value)}>
            {[...new Set([...DURATIONS, Number(f.duration)])].sort((a, b) => a - b).map(m => (
              <option key={m} value={m}>{m >= 60 ? `${Math.floor(m / 60)} ${t('restRes.h')}${m % 60 ? ` ${m % 60} ${t('restRes.m')}` : ''}` : `${m} ${t('restRes.m')}`}</option>
            ))}
          </select>
        </Field>
        <Field label={t('restRes.guests')}><input className={inputCls} inputMode="numeric" value={f.guests} onChange={e => set('guests', e.target.value.replace(/\D/g, ''))} /></Field>
      </div>
      <div>
        <span className="block text-xs font-semibold text-slate-600 mb-1">
          {t('restRes.tables')} {f.table_ids.length > 0 && <span className="font-normal text-slate-500">({t('restRes.seats')}: {seats})</span>}
        </span>
        <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
          {tables.map(tb => {
            const on = f.table_ids.includes(tb.id);
            const isBusy = busy.includes(tb.id);
            return (
              <button key={tb.id} type="button" onClick={() => toggle(tb.id)}
                      className={`px-2.5 py-1.5 rounded-lg border text-xs ${on ? (isBusy ? 'border-rose-500 bg-rose-50 text-rose-800 font-semibold' : 'border-blue-600 bg-blue-50 text-blue-800 font-semibold') : isBusy ? 'border-slate-200 text-slate-400 bg-slate-50' : 'border-slate-200 text-slate-700'}`}>
                {tb.name} <span className="opacity-60">{tb.seats}</span>{isBusy && <span className="ml-1">{t('restRes.busyMark')}</span>}
              </button>
            );
          })}
        </div>
        {clash && <p className="text-xs text-rose-700 mt-1">{t('restRes.clash')}</p>}
        {Number(f.guests) > seats && seats > 0 && <p className="text-xs text-amber-700 mt-1">{t('restRes.fewSeats')}</p>}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label={t('restRes.name')}><input className={inputCls} value={f.name} maxLength={120} onChange={e => set('name', e.target.value)} /></Field>
        <Field label={t('restRes.phone')}><input className={inputCls} value={f.phone} maxLength={30} inputMode="tel" placeholder="+998" onChange={e => set('phone', e.target.value)} /></Field>
      </div>
      <Field label={t('restRes.note')}><input className={inputCls} value={f.note} maxLength={500} placeholder={t('restRes.notePh')} onChange={e => set('note', e.target.value)} /></Field>
      {!editing && canPay && (
        <div className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-3">
          <Field label={t('restRes.deposit')}><input className={inputCls} inputMode="decimal" value={f.deposit} placeholder="0" onChange={e => set('deposit', e.target.value)} /></Field>
          <Field label={t('restRes.depositType')}>
            <select className={inputCls} value={f.deposit_type} onChange={e => set('deposit_type', e.target.value)}>
              {PAY_TYPES.map(p => <option key={p} value={p}>{t(`restOrd.pay.${p}`)}</option>)}
            </select>
          </Field>
          <p className="col-span-2 text-[11px] text-slate-500">{t('restRes.depositHint')}</p>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onClose}>{t('restRes.close')}</button>
        <button className={btnPrimary} disabled={saving || !f.date || !f.name.trim() || f.table_ids.length === 0 || clash} onClick={save}>{t('restRes.save')}</button>
      </div>
    </Modal>
  );
}

function DetailModal({ res, canPay, onClose, onEdit, onChanged, t }) {
  const navigate = useNavigate();
  const [refund, setRefund] = useState(true);
  const [reason, setReason] = useState('');
  const [dep, setDep] = useState('');
  const [depType, setDepType] = useState('cash');
  const [busy, setBusy] = useState(false);
  const started = new Date(res.starts_at) <= new Date();
  const run = async (path, body, okMsg, after) => {
    setBusy(true);
    try {
      const r = await api.post(`/restaurant/reservations/${res.id}${path}`, body);
      toast.success(okMsg);
      onChanged();
      if (after) after(r.data);
    } catch (err) { toast.error(errMsg(err, t('restRes.failed'))); }
    setBusy(false);
  };
  return (
    <Modal title={`${res.name}, ${hhmm(res.starts_at)}`} onClose={onClose}>
      <div className="text-sm space-y-1 text-slate-700">
        <div>{t('restRes.status')}: <b>{t(`restRes.st.${res.status}`)}</b></div>
        <div>{t('restRes.time')}: {hhmm(res.starts_at)} - {hhmm(res.ends_at)}, {t('restRes.guests')}: {res.guests}</div>
        <div>{t('restRes.tables')}: {res.table_names.join(', ')}</div>
        {res.phone && <div>{t('restRes.phone')}: <a className="text-blue-700" href={`tel:${res.phone}`}>{res.phone}</a></div>}
        {res.note && <div>{t('restRes.note')}: {res.note}</div>}
        {res.deposit_amount > 0 && (
          <div>{t('restRes.deposit')}: {money(res.deposit_amount)} ({t(`restOrd.pay.${res.deposit_type}`)}), {t(`restRes.dep.${res.deposit_status}`)}</div>
        )}
        {res.remind_channel && <div className="text-xs text-slate-500">{t('restRes.reminded')}: {t(`restRes.ch.${res.remind_channel}`)}</div>}
        {res.created_by_name && <div className="text-xs text-slate-500">{t('restRes.createdBy')}: {res.created_by_name}</div>}
      </div>
      {res.status === 'booked' && (
        <div className="space-y-3 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap gap-2">
            <button className={btnPrimary} disabled={busy}
                    onClick={() => run('/arrive', {}, t('restRes.arrivedOk'), () => navigate('/admin/restaurant/orders'))}>{t('restRes.arrive')}</button>
            <button className={btnGhost} disabled={busy} onClick={onEdit}>{t('restRes.edit')}</button>
            {started && <button className={btnGhost} disabled={busy} onClick={() => run('/no-show', null, t('restRes.noShowOk'))}>{t('restRes.noShow')}</button>}
          </div>
          {canPay && !res.deposit_status && (
            <div className="flex gap-2 items-end">
              <Field label={t('restRes.deposit')}><input className={inputCls} inputMode="decimal" value={dep} onChange={e => setDep(e.target.value)} /></Field>
              <select className={`${inputCls} w-32`} value={depType} onChange={e => setDepType(e.target.value)}>
                {PAY_TYPES.map(p => <option key={p} value={p}>{t(`restOrd.pay.${p}`)}</option>)}
              </select>
              <button className={btnGhost} disabled={busy || !(Number(dep) > 0)}
                      onClick={() => run('/deposit', { amount: Number(dep), type: depType }, t('restRes.depositOk'))}>{t('restRes.takeDeposit')}</button>
            </div>
          )}
          <div className="space-y-2 border-t border-slate-100 pt-3">
            <input className={inputCls} value={reason} maxLength={200} placeholder={t('restRes.cancelReason')} onChange={e => setReason(e.target.value)} />
            {res.deposit_held > 0 && (
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input type="checkbox" checked={refund} onChange={e => setRefund(e.target.checked)} />{t('restRes.refundOnCancel')} ({money(res.deposit_held)})
              </label>
            )}
            <button className={btnDanger} disabled={busy}
                    onClick={() => run('/cancel', { reason: reason || null, refund_deposit: refund }, t('restRes.cancelledOk'), onClose)}>{t('restRes.cancelBooking')}</button>
          </div>
        </div>
      )}
      {res.status !== 'booked' && res.deposit_held > 0 && canPay && (
        <button className={btnGhost} disabled={busy} onClick={() => run('/refund-deposit', null, t('restRes.refundOk'))}>
          {t('restRes.refundDeposit')} ({money(res.deposit_held)})
        </button>
      )}
    </Modal>
  );
}

export default function RestaurantReservations() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [day, setDay] = useState(() => isoDate(new Date()));
  const [data, setData] = useState(null);
  const [showClosed, setShowClosed] = useState(false);
  const [form, setForm] = useState(null);     // {init}
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const load = useCallback(() => {
    if (!branchId) return;
    api.get('/restaurant/reservations', { params: { branch_id: branchId, date: day } })
      .then(r => setData(r.data))
      .catch(err => toast.error(errMsg(err, t('restRes.failed'))));
  }, [branchId, day, t]);
  useEffect(() => { load(); const p = setInterval(load, 30000); return () => clearInterval(p); }, [load]);

  const items = useMemo(() => (data?.items || []).filter(r => showClosed || r.status === 'booked' || r.status === 'arrived'), [data, showClosed]);
  const range = useMemo(() => {
    let lo = 9, hi = 24;
    for (const r of items) {
      const s = new Date(r.starts_at);
      const e = new Date(r.ends_at);
      if (isoDate(s) === day) lo = Math.min(lo, s.getHours());
      if (isoDate(e) === day) hi = Math.max(hi, e.getHours() + (e.getMinutes() ? 1 : 0));
    }
    return { lo, hi: Math.min(24, hi) };
  }, [items, day]);
  const dayStart = useMemo(() => new Date(`${day}T00:00:00`), [day]);
  const xOf = d => ((d - dayStart) / 3600e3 - range.lo) * HOUR_W;
  const width = (range.hi - range.lo) * HOUR_W;
  const booked = items.filter(r => r.status === 'booked');
  const guests = booked.reduce((s, r) => s + r.guests, 0);
  const editRes = r => {
    const s = new Date(r.starts_at);
    setDetail(null);
    setForm({ init: { ...r, date: isoDate(s), time: hhmm(r.starts_at) } });
  };
  const newAt = (tableId, hour) => setForm({ init: { date: day, time: hour != null ? `${pad(hour)}:00` : '19:00', table_ids: tableId ? [tableId] : [] } });

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restRes.title')}</h1>
          <p className="text-sm text-slate-500">{t('restRes.desc')}</p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {branches.length > 1 && (
            <select className="px-2 py-2 border border-slate-200 rounded-lg text-sm" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          )}
          <button className={btnPrimary} onClick={() => newAt(null, null)}><Plus className="w-4 h-4" />{t('restRes.new')}</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button className={btnGhost} onClick={() => setDay(d => addDays(d, -1))}><ChevronLeft className="w-4 h-4" /></button>
        <input type="date" className="px-3 py-2 border border-slate-200 rounded-lg text-sm" value={day} onChange={e => e.target.value && setDay(e.target.value)} />
        <button className={btnGhost} onClick={() => setDay(d => addDays(d, 1))}><ChevronRight className="w-4 h-4" /></button>
        <button className={btnGhost} onClick={() => setDay(isoDate(new Date()))}>{t('restRes.today')}</button>
        <span className="text-sm text-slate-600 ml-2">{t('restRes.summary', { n: booked.length, g: guests })}</span>
        <label className="ml-auto flex items-center gap-2 text-xs text-slate-600">
          <input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)} />{t('restRes.showClosed')}
        </label>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
        <div className="flex" style={{ minWidth: width + 112 }}>
          <div className="w-28 shrink-0 border-r border-slate-100">
            <div className="h-8 border-b border-slate-100" />
            {(data?.tables || []).map(tb => (
              <div key={tb.id} className="px-2 flex items-center text-xs border-b border-slate-50" style={{ height: ROW_H }}>
                <span className="font-semibold text-slate-800 truncate">{tb.name}</span>
                <span className="ml-1 text-slate-400">{tb.seats}</span>
              </div>
            ))}
          </div>
          <div className="relative" style={{ width }}>
            <div className="flex h-8 border-b border-slate-100">
              {Array.from({ length: range.hi - range.lo }, (_, i) => (
                <div key={i} className="text-[11px] text-slate-500 border-l border-slate-100 pl-1 pt-2" style={{ width: HOUR_W }}>{pad(range.lo + i)}:00</div>
              ))}
            </div>
            {(data?.tables || []).map(tb => (
              <div key={tb.id} className="relative border-b border-slate-50" style={{ height: ROW_H }}>
                {Array.from({ length: range.hi - range.lo }, (_, i) => (
                  <button key={i} className="absolute top-0 h-full border-l border-slate-50 hover:bg-slate-50" title={t('restRes.new')}
                          style={{ left: i * HOUR_W, width: HOUR_W }} onClick={() => newAt(tb.id, range.lo + i)} />
                ))}
                {items.filter(r => r.table_ids.includes(tb.id)).map(r => {
                  const left = Math.max(0, xOf(new Date(r.starts_at)));
                  const right = Math.min(width, xOf(new Date(r.ends_at)));
                  if (right <= 0 || left >= width) return null;
                  return (
                    <button key={r.id} onClick={() => setDetail(r)}
                            className={`absolute top-1 bottom-1 rounded-md border text-left px-1.5 overflow-hidden ${BLOCK[r.status]}`}
                            style={{ left: left + 1, width: Math.max(18, right - left - 2) }}>
                      <div className="text-[11px] font-semibold leading-tight truncate">{hhmm(r.starts_at)} {r.name}</div>
                      <div className="text-[10px] leading-tight truncate opacity-80">{r.guests} {t('restRes.ppl')}{r.deposit_held > 0 ? `, ${t('restRes.depShort')} ${money(r.deposit_held)}` : ''}</div>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        {data && data.tables.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restRes.noTables')}</div>}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restRes.list')}</div>
        {items.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restRes.none')}</div>}
        <div className="divide-y divide-slate-100">
          {items.map(r => (
            <button key={r.id} onClick={() => setDetail(r)} className="w-full px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm text-left hover:bg-slate-50">
              <span className="font-semibold tabular-nums w-24">{hhmm(r.starts_at)} - {hhmm(r.ends_at)}</span>
              <span className="flex-1 min-w-[140px] text-slate-800">{r.name}{r.phone ? <span className="text-slate-500">, {r.phone}</span> : null}</span>
              <span className="text-xs text-slate-600">{r.table_names.join(', ')}</span>
              <span className="text-xs text-slate-600">{r.guests} {t('restRes.ppl')}</span>
              {r.deposit_amount > 0 && <span className="text-xs text-slate-600">{t('restRes.depShort')} {money(r.deposit_amount)}</span>}
              <span className={`text-[11px] px-1.5 py-0.5 rounded border ${BLOCK[r.status]}`}>{t(`restRes.st.${r.status}`)}</span>
            </button>
          ))}
        </div>
      </div>

      {form && data && (
        <FormModal branchId={branchId} tables={data.tables} init={form.init} canPay={data.can_take_payment}
                   defaultDuration={data.default_duration_min} t={t}
                   onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />
      )}
      {detail && (
        <DetailModal res={detail} canPay={!!data?.can_take_payment} t={t} onClose={() => setDetail(null)}
                     onEdit={() => editRes(detail)}
                     onChanged={() => { setDetail(null); load(); }} />
      )}
    </div>
  );
}
