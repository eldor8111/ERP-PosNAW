import { useState, useEffect, useCallback } from 'react';
import { ChevronUp, ChevronDown, X, MapPin, Phone, Plus, Truck, Route as RouteIcon, Check, Ban, ExternalLink, Navigation } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { yandexMapsUrl, yandexRouteUrl } from '../../utils/maps';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const today = () => new Date().toLocaleDateString('sv-SE'); // YYYY-MM-DD, mahalliy vaqt
const errMsg = (e, t) => e.response?.data?.detail || t('common.error');

const inputCls = 'w-full px-3 py-2.5 border border-line rounded-xl text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-brand/40';
const ROUTE_COLOR = { planned: 'neutral', in_progress: 'warning', completed: 'success', cancelled: 'danger' };
const STOP_COLOR = { pending: 'neutral', confirmed: 'neutral', preparing: 'neutral', assigned: 'brand', on_way: 'warning', delivered: 'success', cancelled: 'danger' };
const FUEL_TYPES = ['petrol', 'diesel', 'gas', 'electric'];

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className={`bg-surface rounded-2xl shadow-2xl w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} max-h-[90vh] flex flex-col`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-line shrink-0">
          <h3 className="text-base font-bold text-ink-900">{title}</h3>
          <button onClick={onClose} className="text-ink-300 hover:text-ink-500"><X className="size-5" /></button>
        </div>
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-ink-500 mb-1.5">{label}</label>
      {children}
    </div>
  );
}

// Buyurtma guruhi qatori — marshrut yaratish va tafsilotlarda umumiy
function StopRow({ stop, index, t, children }) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl border border-line bg-surface">
      {index >= 0 && <div className="w-7 h-7 rounded-full bg-brand/10 text-brand text-xs font-bold flex items-center justify-center shrink-0">{index + 1}</div>}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-sm text-ink-900">{stop.customer_name}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${stop.source === 'sale' ? 'bg-brand/10 text-brand' : 'bg-sky-50 text-sky-600'}`}>
            {stop.source === 'sale' ? `${t('logistics.srcSale')} #${stop.sale_number}` : t('logistics.srcTelegram')}
          </span>
          {stop.status && <Badge color={STOP_COLOR[stop.status]} dot={false}>{t(`logistics.orderStatus.${stop.status}`)}</Badge>}
        </div>
        <div className="text-xs text-ink-500 mt-0.5 flex items-center gap-1">
          <MapPin className="size-3 shrink-0" />
          <span className="truncate">{stop.address || <span className="text-warning">{t('logistics.noAddress')}</span>}</span>
          {stop.lat != null && (
            <a href={yandexMapsUrl(stop.lat, stop.lng)} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
              className="shrink-0 inline-flex items-center gap-0.5 text-brand hover:underline ml-1">
              <ExternalLink className="size-3" />{t('logistics.map')}
            </a>
          )}
        </div>
        {stop.planned_date && <div className="text-[11px] text-ink-300 mt-0.5">📅 {stop.planned_date}{stop.note ? ` · ${stop.note}` : ''}</div>}
        <div className="text-xs text-ink-300 mt-0.5 flex items-center gap-3 flex-wrap">
          {stop.phone && <span className="flex items-center gap-1"><Phone className="size-3" />{stop.phone}</span>}
          <span className="tabular-nums">{fmt(stop.amount)}{stop.delivery_fee > 0 ? ` + ${fmt(stop.delivery_fee)}` : ''} {t('common.sum')}</span>
          {stop.collect_amount != null && <span className="tabular-nums font-semibold text-ink-500">{t('logistics.collect')}: {fmt(stop.collect_amount)}</span>}
          {stop.payment_type && <span>{stop.payment_type}</span>}
        </div>
      </div>
      {children && <div className="flex items-center gap-1 shrink-0">{children}</div>}
    </div>
  );
}

function move(list, i, dir) {
  const j = i + dir;
  if (j < 0 || j >= list.length) return list;
  const copy = [...list];
  [copy[i], copy[j]] = [copy[j], copy[i]];
  return copy;
}

const IconBtn = ({ onClick, disabled, title, children, danger }) => (
  <button type="button" onClick={onClick} disabled={disabled} title={title}
    className={`p-1.5 rounded-lg disabled:opacity-30 ${danger ? 'text-danger hover:bg-danger/10' : 'text-ink-500 hover:bg-surface-sunken'}`}>
    {children}
  </button>
);

/* ── Yangi marshrut ─────────────────────────────────────────────────────── */
function CreateRouteModal({ couriers, vehicles, onClose, onCreated }) {
  const { t } = useLang();
  const [available, setAvailable] = useState(null);
  const [selected, setSelected] = useState([]); // tartiblangan group_key'lar
  const [form, setForm] = useState({ route_date: today(), courier_id: '', vehicle_id: '', note: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/logistics/available-orders').then(r => setAvailable(r.data)).catch(() => setAvailable([]));
  }, []);

  const byKey = Object.fromEntries((available || []).map(a => [a.group_key, a]));
  const toggle = (k) => setSelected(s => s.includes(k) ? s.filter(x => x !== k) : [...s, k]);
  const onCourier = (id) => {
    const c = couriers.find(x => String(x.id) === id);
    setForm(f => ({ ...f, courier_id: id, vehicle_id: c?.vehicle_id ? String(c.vehicle_id) : f.vehicle_id }));
  };

  const submit = async () => {
    if (!form.courier_id || selected.length === 0) { toast.error(t('logistics.selectCourierAndOrders')); return; }
    setSaving(true);
    try {
      const { data } = await api.post('/logistics/routes', {
        route_date: form.route_date,
        courier_id: Number(form.courier_id),
        vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null,
        note: form.note || null,
        group_keys: selected,
      });
      onCreated(data);
    } catch (e) { toast.error(errMsg(e, t)); }
    finally { setSaving(false); }
  };

  const unselected = (available || []).filter(a => !selected.includes(a.group_key));

  return (
    <Modal title={t('logistics.newRoute')} onClose={onClose} wide>
      <div className="p-6 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label={t('logistics.routeDate')}>
            <input type="date" value={form.route_date} onChange={e => setForm(f => ({ ...f, route_date: e.target.value }))} className={inputCls} />
          </Field>
          <Field label={t('logistics.courier')}>
            <select value={form.courier_id} onChange={e => onCourier(e.target.value)} className={inputCls}>
              <option value="">—</option>
              {couriers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label={t('logistics.vehicle')}>
            <select value={form.vehicle_id} onChange={e => setForm(f => ({ ...f, vehicle_id: e.target.value }))} className={inputCls}>
              <option value="">—</option>
              {vehicles.map(v => <option key={v.id} value={v.id}>{v.plate_number}{v.model ? ` · ${v.model}` : ''}</option>)}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <div className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">{t('logistics.availableOrders')} ({unselected.length})</div>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {available === null && <div className="text-sm text-ink-300 py-6 text-center">...</div>}
              {available && unselected.length === 0 && <div className="text-sm text-ink-300 py-6 text-center">{t('logistics.noAvailable')}</div>}
              {unselected.map(a => (
                <button key={a.group_key} type="button" onClick={() => toggle(a.group_key)} className="w-full text-left">
                  <StopRow stop={{ ...a, status: null }} index={-1} t={t}>
                    <Plus className="size-4 text-brand" />
                  </StopRow>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">{t('logistics.routeStops')} ({selected.length})</div>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {selected.length === 0 && <div className="text-sm text-ink-300 py-6 text-center border border-dashed border-line rounded-xl">{t('logistics.pickOrdersHint')}</div>}
              {selected.map((k, i) => byKey[k] && (
                <StopRow key={k} stop={{ ...byKey[k], status: null }} index={i} t={t}>
                  <IconBtn onClick={() => setSelected(s => move(s, i, -1))} disabled={i === 0}><ChevronUp className="size-4" /></IconBtn>
                  <IconBtn onClick={() => setSelected(s => move(s, i, 1))} disabled={i === selected.length - 1}><ChevronDown className="size-4" /></IconBtn>
                  <IconBtn onClick={() => toggle(k)} danger><X className="size-4" /></IconBtn>
                </StopRow>
              ))}
            </div>
          </div>
        </div>

        <Field label={t('production.noteOptional')}>
          <input value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} className={inputCls} />
        </Field>

        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose} className="px-4 py-2.5 border border-line text-ink-500 text-sm font-medium rounded-xl hover:bg-surface-sunken">{t('common.cancel')}</button>
          <button onClick={submit} disabled={saving} className="px-5 py-2.5 bg-brand hover:bg-brand-deep disabled:opacity-60 text-white text-sm font-semibold rounded-xl">
            {saving ? t('common.saving') : t('logistics.createRoute')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ── Marshrut tafsilotlari ──────────────────────────────────────────────── */
function RouteDetailModal({ route: initial, onClose, onChanged }) {
  const { t } = useLang();
  const [route, setRoute] = useState(initial);
  const [order, setOrder] = useState(initial.stops.map(s => s.group_key));
  const [busy, setBusy] = useState(false);
  const byKey = Object.fromEntries(route.stops.map(s => [s.group_key, s]));
  const reordered = order.join() !== route.stops.map(s => s.group_key).join();

  const act = async (fn, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    try {
      const { data } = await fn();
      setRoute(data); setOrder(data.stops.map(s => s.group_key)); onChanged();
    } catch (e) { toast.error(errMsg(e, t)); }
    finally { setBusy(false); }
  };
  const base = `/logistics/routes/${route.id}`;
  const stopStatus = (k, status) => act(() => api.post(`${base}/stops/${encodeURIComponent(k)}/status`, { status }),
    status === 'cancelled' ? t('logistics.confirmStopCancel') : null);

  return (
    <Modal title={`${t('logistics.route')} ${route.number}`} onClose={onClose} wide>
      <div className="p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <Badge color={ROUTE_COLOR[route.status]}>{t(`logistics.status.${route.status}`)}</Badge>
          <span className="text-ink-500">{route.route_date}</span>
          <span className="flex items-center gap-1.5 text-ink-900 font-medium"><Truck className="size-4 text-ink-300" />{route.courier_name}{route.vehicle_plate ? ` · ${route.vehicle_plate}` : ''}</span>
          <span className="text-ink-500 tabular-nums">{route.stops_delivered}/{route.stops_total} {t('logistics.delivered')}</span>
          <span className="text-ink-500 tabular-nums">{t('logistics.toCollect')}: <b className="text-ink-900">{fmt(route.total_collect ?? route.total_amount + route.total_fee)}</b></span>
        </div>
        {route.note && <div className="text-sm text-ink-500 bg-surface-sunken rounded-xl px-3 py-2">{route.note}</div>}
        {(() => {
          const pts = order.map(k => byKey[k]).filter(s => s && s.lat != null && !['delivered', 'cancelled'].includes(s.status));
          return pts.length > 0 && (
            <a href={yandexRouteUrl(pts)} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline">
              <Navigation className="size-4" />{t('logistics.openRouteInYandex')} ({pts.length})
            </a>
          );
        })()}

        <div className="space-y-2">
          {order.map((k, i) => byKey[k] && (
            <StopRow key={k} stop={byKey[k]} index={i} t={t}>
              {route.status === 'planned' && <>
                <IconBtn onClick={() => setOrder(o => move(o, i, -1))} disabled={i === 0}><ChevronUp className="size-4" /></IconBtn>
                <IconBtn onClick={() => setOrder(o => move(o, i, 1))} disabled={i === order.length - 1}><ChevronDown className="size-4" /></IconBtn>
                <IconBtn onClick={() => setOrder(o => o.filter(x => x !== k))} disabled={order.length === 1} danger title={t('logistics.removeStop')}><X className="size-4" /></IconBtn>
              </>}
              {route.status === 'in_progress' && !['delivered', 'cancelled'].includes(byKey[k].status) && <>
                <button onClick={() => stopStatus(k, 'delivered')} disabled={busy}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-success/10 text-success hover:bg-success/20">
                  <Check className="size-3.5" />{t('logistics.markDelivered')}
                </button>
                <IconBtn onClick={() => stopStatus(k, 'cancelled')} disabled={busy} danger title={t('logistics.markFailed')}><Ban className="size-4" /></IconBtn>
              </>}
            </StopRow>
          ))}
        </div>

        <div className="flex flex-wrap justify-end gap-3 pt-2 border-t border-line">
          {route.status === 'planned' && <>
            <button onClick={() => act(() => api.post(`${base}/cancel`), t('logistics.confirmCancel'))} disabled={busy}
              className="px-4 py-2.5 text-danger text-sm font-medium rounded-xl hover:bg-danger/10">{t('logistics.cancelRoute')}</button>
            {reordered && <button onClick={() => act(() => api.put(`${base}/stops`, { group_keys: order }))} disabled={busy}
              className="px-4 py-2.5 border border-line text-ink-900 text-sm font-semibold rounded-xl hover:bg-surface-sunken">{t('logistics.saveOrder')}</button>}
            <button onClick={() => act(() => api.post(`${base}/start`))} disabled={busy || reordered}
              className="px-5 py-2.5 bg-brand hover:bg-brand-deep disabled:opacity-50 text-white text-sm font-semibold rounded-xl">{t('logistics.startRoute')}</button>
          </>}
          {route.status === 'in_progress' && (
            <button onClick={() => act(() => api.post(`${base}/complete`),
              route.stops_delivered + route.stops_cancelled < route.stops_total ? t('logistics.confirmCompletePartial') : null)} disabled={busy}
              className="px-5 py-2.5 bg-success hover:opacity-90 text-white text-sm font-semibold rounded-xl">{t('logistics.completeRoute')}</button>
          )}
        </div>
      </div>
    </Modal>
  );
}

/* ── Marshrutlar tab ────────────────────────────────────────────────────── */
function RoutesTab({ couriers, vehicles }) {
  const { t } = useLang();
  const [date, setDate] = useState(today());
  const [routes, setRoutes] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = useCallback(() => {
    api.get('/logistics/routes', { params: date ? { route_date: date } : {} })
      .then(r => setRoutes(r.data)).catch(() => setRoutes([]));
  }, [date]);
  useEffect(() => { load(); }, [load]);

  const open = async (row) => {
    try { const { data } = await api.get(`/logistics/routes/${row.id}`); setDetail(data); }
    catch (e) { toast.error(errMsg(e, t)); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className={`${inputCls} w-auto`} />
          {date && <button onClick={() => setDate('')} className="text-xs text-brand font-medium">{t('logistics.allDates')}</button>}
        </div>
        <button onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep">
          <Plus className="size-4" />{t('logistics.newRoute')}
        </button>
      </div>

      <DataTable
        rows={routes || []}
        emptyText={routes ? t('logistics.noRoutes') : '...'}
        onRowClick={open}
        columns={[
          { key: 'number', label: '№' },
          { key: 'route_date', label: t('logistics.routeDate') },
          { key: 'courier_name', label: t('logistics.courier') },
          { key: 'vehicle_plate', label: t('logistics.vehicle'), render: r => r.vehicle_plate || <span className="text-ink-300">—</span> },
          { key: 'progress', label: t('logistics.stops'), align: 'center', numeric: true, render: r => `${r.stops_delivered}/${r.stops_total}` },
          { key: 'total', label: t('logistics.toCollect'), align: 'right', numeric: true, render: r => fmt(r.total_collect ?? r.total_amount + r.total_fee) },
          { key: 'status', label: t('logistics.statusLabel'), align: 'center', render: r => <Badge color={ROUTE_COLOR[r.status]}>{t(`logistics.status.${r.status}`)}</Badge> },
        ]}
      />

      {showCreate && (
        <CreateRouteModal couriers={couriers} vehicles={vehicles} onClose={() => setShowCreate(false)}
          onCreated={(r) => { setShowCreate(false); setDate(r.route_date); load(); setDetail(r); }} />
      )}
      {detail && <RouteDetailModal key={detail.id} route={detail} onClose={() => setDetail(null)} onChanged={load} />}
    </div>
  );
}

/* ── Transport tab ──────────────────────────────────────────────────────── */
function VehiclesTab({ vehicles, reload }) {
  const { t } = useLang();
  const empty = { plate_number: '', model: '', capacity_kg: '', fuel_type: '' };
  const [modal, setModal] = useState(null); // null | {mode, vehicle?}
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);

  const openAdd = () => { setForm(empty); setModal({ mode: 'add' }); };
  const openEdit = (v) => {
    setForm({ plate_number: v.plate_number, model: v.model || '', capacity_kg: v.capacity_kg ?? '', fuel_type: v.fuel_type || '' });
    setModal({ mode: 'edit', vehicle: v });
  };
  const save = async () => {
    if (!form.plate_number.trim()) return;
    setSaving(true);
    const payload = {
      plate_number: form.plate_number, model: form.model || null,
      capacity_kg: form.capacity_kg === '' ? null : Number(form.capacity_kg), fuel_type: form.fuel_type || null,
    };
    try {
      if (modal.mode === 'add') await api.post('/logistics/vehicles', payload);
      else await api.put(`/logistics/vehicles/${modal.vehicle.id}`, payload);
      setModal(null); reload();
    } catch (e) { toast.error(errMsg(e, t)); }
    finally { setSaving(false); }
  };
  const deactivate = async (v) => {
    if (!window.confirm(t('logistics.confirmDeactivateVehicle'))) return;
    try { await api.delete(`/logistics/vehicles/${v.id}`); reload(); }
    catch (e) { toast.error(errMsg(e, t)); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={openAdd} className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep">
          <Plus className="size-4" />{t('logistics.addVehicle')}
        </button>
      </div>
      <DataTable
        rows={vehicles}
        emptyText={t('logistics.noVehicles')}
        onRowClick={openEdit}
        columns={[
          { key: 'plate_number', label: t('logistics.plateNumber'), render: v => <span className="font-mono font-semibold">{v.plate_number}</span> },
          { key: 'model', label: t('logistics.model'), render: v => v.model || '—' },
          { key: 'capacity_kg', label: t('logistics.capacity'), align: 'right', numeric: true, render: v => v.capacity_kg != null ? `${fmt(v.capacity_kg)} kg` : '—' },
          { key: 'fuel_type', label: t('logistics.fuelType'), render: v => v.fuel_type ? t(`logistics.fuel.${v.fuel_type}`) : '—' },
          {
            key: 'actions', label: '', align: 'right', render: v => (
              <button onClick={(e) => { e.stopPropagation(); deactivate(v); }} className="text-xs text-danger font-medium hover:underline">{t('logistics.deactivate')}</button>
            ),
          },
        ]}
      />
      {modal && (
        <Modal title={modal.mode === 'add' ? t('logistics.addVehicle') : t('common.edit')} onClose={() => setModal(null)}>
          <div className="p-6 space-y-4">
            <Field label={`${t('logistics.plateNumber')} *`}>
              <input value={form.plate_number} onChange={e => setForm(f => ({ ...f, plate_number: e.target.value }))} placeholder="01 A 123 BC" className={`${inputCls} font-mono uppercase`} />
            </Field>
            <Field label={t('logistics.model')}>
              <input value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} placeholder="Damas, Labo, Isuzu..." className={inputCls} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label={`${t('logistics.capacity')} (kg)`}>
                <input type="number" min="0" value={form.capacity_kg} onChange={e => setForm(f => ({ ...f, capacity_kg: e.target.value }))} className={inputCls} />
              </Field>
              <Field label={t('logistics.fuelType')}>
                <select value={form.fuel_type} onChange={e => setForm(f => ({ ...f, fuel_type: e.target.value }))} className={inputCls}>
                  <option value="">—</option>
                  {FUEL_TYPES.map(ft => <option key={ft} value={ft}>{t(`logistics.fuel.${ft}`)}</option>)}
                </select>
              </Field>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={() => setModal(null)} className="px-4 py-2.5 border border-line text-ink-500 text-sm font-medium rounded-xl hover:bg-surface-sunken">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving} className="px-5 py-2.5 bg-brand hover:bg-brand-deep disabled:opacity-60 text-white text-sm font-semibold rounded-xl">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function Logistics() {
  const { t } = useLang();
  const [tab, setTab] = useState('routes');
  const [couriers, setCouriers] = useState([]);
  const [vehicles, setVehicles] = useState([]);

  const loadVehicles = useCallback(() => {
    api.get('/logistics/vehicles').then(r => setVehicles(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    api.get('/couriers').then(r => setCouriers(r.data)).catch(() => {});
    loadVehicles();
  }, [loadVehicles]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-brand flex items-center justify-center shadow-lg shadow-brand/20">
          <RouteIcon className="size-5 text-white" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-ink-900">{t('logistics.title')}</h2>
          <p className="text-sm text-ink-500">{t('logistics.subtitle')}</p>
        </div>
      </div>

      <div className="flex bg-surface border border-line rounded-xl overflow-hidden shadow-sm w-fit">
        {[['routes', t('logistics.tabRoutes')], ['vehicles', t('logistics.tabVehicles')]].map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)}
            className={`px-5 py-2.5 text-sm font-semibold transition-all ${tab === v ? 'bg-brand text-white' : 'text-ink-500 hover:bg-surface-sunken'}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === 'routes' && <RoutesTab couriers={couriers} vehicles={vehicles} />}
      {tab === 'vehicles' && <VehiclesTab vehicles={vehicles} reload={loadVehicles} />}
    </div>
  );
}
