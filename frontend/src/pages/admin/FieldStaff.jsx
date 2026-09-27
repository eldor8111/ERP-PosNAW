import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Smartphone, UserPlus, Wallet, ShieldOff, Battery, Image as ImageIcon, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import MultiMap from '../../components/MultiMap';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const hm = (iso) => iso ? new Date(iso).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : '—';
const today = () => new Date().toLocaleDateString('sv-SE');
const minsAgo = (iso) => iso ? Math.round((Date.now() - new Date(iso).getTime()) / 60000) : null;

function ago(iso, t) {
  const min = minsAgo(iso);
  if (min == null) return t('fieldStaff.never');
  if (min < 1) return t('fieldStaff.justNow');
  if (min < 60) return `${min} ${t('fieldStaff.minAgo')}`;
  if (min < 1440) return `${Math.round(min / 60)} ${t('fieldStaff.hourAgo')}`;
  return new Date(iso).toLocaleDateString('uz-UZ');
}

// Holat: smenada va oxirgi nuqta yangi — yashil; smenada lekin signal eski — sariq; smenadan tashqari — kulrang
const liveColor = (s) => !s.on_shift ? '#9AA3B2' : (minsAgo(s.last?.at) ?? 999) <= 10 ? '#1E8E5A' : '#B7791F';

function PhotoModal({ url, onClose }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let obj;
    api.get(url, { responseType: 'blob' }).then(r => { obj = URL.createObjectURL(r.data); setSrc(obj); }).catch(() => toast.error('Rasm yuklanmadi'));
    return () => { if (obj) URL.revokeObjectURL(obj); };
  }, [url]);
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <button className="absolute top-4 right-4 text-white"><X className="size-7" /></button>
      {src ? <img src={src} alt="" className="max-h-full max-w-full rounded-xl" /> : <div className="text-white">…</div>}
    </div>
  );
}

/* ── Jonli xarita + kunlik trek ─────────────────────────────────────────── */
function LiveTab() {
  const { t } = useLang();
  const [live, setLive] = useState(null);
  const [sel, setSel] = useState(null);
  const [day, setDay] = useState(today());
  const [trackData, setTrackData] = useState(null);
  const [photo, setPhoto] = useState(null);

  const loadLive = useCallback(() => api.get('/field-staff/live', { _silent: true }).then(r => setLive(r.data)).catch(() => setLive([])), []);
  useEffect(() => {
    loadLive();
    const id = setInterval(loadLive, 30000);
    return () => clearInterval(id);
  }, [loadLive]);

  useEffect(() => {
    if (!sel) return;
    api.get('/field-staff/track', { params: { user_id: sel, day } }).then(r => setTrackData(r.data)).catch(() => setTrackData(null));
  }, [sel, day]);

  const markers = useMemo(() => {
    if (sel && trackData) {
      const vm = trackData.visits.filter(v => v.lat != null).map(v => ({
        id: `v${v.id}`, lat: v.lat, lng: v.lng, label: v.customer,
        color: v.within_radius === false ? '#C93A3A' : '#1E8E5A',
        title: `${v.customer} · ${hm(v.at)}${v.distance_m != null ? ` · ${v.distance_m} m` : ''}`,
      }));
      const dm = trackData.deliveries.filter(d => d.lat != null).map(d => ({
        id: `d${d.id}`, lat: d.lat, lng: d.lng, label: `🚚 ${hm(d.at)}`, color: '#2554C7',
      }));
      const lastPt = trackData.points.at(-1);
      return [...vm, ...dm, ...(lastPt ? [{ id: 'last', lat: lastPt[0], lng: lastPt[1], label: trackData.user.name, color: '#1B1F27' }] : [])];
    }
    return (live || []).filter(s => s.last).map(s => ({
      id: s.id, lat: s.last.lat, lng: s.last.lng, label: s.name, color: liveColor(s),
      title: `${s.name} · ${ago(s.last.at, t)}`,
    }));
  }, [sel, trackData, live, t]);
  const path = useMemo(() => (sel && trackData ? trackData.points.map(p => [p[0], p[1]]) : []), [sel, trackData]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div className="xl:col-span-2">
        <MultiMap markers={markers} path={path} height={560} fitKey={sel ? `${sel}-${day}-${trackData?.points.length}` : `live-${live?.length}`} />
      </div>
      <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
        {sel && trackData ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <button onClick={() => { setSel(null); setTrackData(null); }} className="text-sm text-brand font-medium">← {t('fieldStaff.allStaff')}</button>
              <input type="date" value={day} max={today()} onChange={e => setDay(e.target.value)} className="px-3 py-1.5 border border-line rounded-lg text-sm bg-surface" />
            </div>
            <div className="bg-surface border border-line rounded-2xl p-4">
              <div className="font-bold text-ink-900">{trackData.user.name}</div>
              <div className="text-xs text-ink-500 mt-1">
                {trackData.shifts.length === 0 ? t('fieldStaff.noShift') : trackData.shifts.map((s, i) => <div key={i}>{t('fieldStaff.shift')}: {hm(s.started_at)} — {s.ended_at ? hm(s.ended_at) : t('fieldStaff.now')}</div>)}
                <div>{t('fieldStaff.gpsPoints')}: {trackData.points.length}</div>
              </div>
            </div>
            {trackData.visits.map(v => (
              <div key={v.id} className={`bg-surface border rounded-xl px-3 py-2.5 text-sm ${v.within_radius === false ? 'border-danger/40' : 'border-line'}`}>
                <div className="flex justify-between gap-2">
                  <span className="font-semibold text-ink-900 truncate">{v.customer}</span>
                  <span className="text-ink-500 shrink-0">{hm(v.at)}{v.out ? `–${hm(v.out)}` : ''}</span>
                </div>
                <div className="flex items-center justify-between mt-0.5 text-xs">
                  <span className={v.within_radius === false ? 'text-danger' : 'text-ink-500'}>
                    {v.distance_m != null ? `${v.distance_m} m` : '—'}{v.within_radius === false ? ` · ${t('fieldStaff.unverified')}` : ''}
                    {v.result ? ` · ${t(`m.result.${v.result}`)}` : ''}
                  </span>
                  {v.has_photo && <button onClick={() => setPhoto(`/field-staff/visits/${v.id}/photo`)} className="text-brand"><ImageIcon className="size-4" /></button>}
                </div>
              </div>
            ))}
            {trackData.deliveries.map(d => (
              <div key={d.id} className="bg-surface border border-line rounded-xl px-3 py-2.5 text-sm flex items-center justify-between">
                <span>🚚 {hm(d.at)}{d.distance_m != null ? ` · ${d.distance_m} m` : ''}</span>
                {d.has_photo && <button onClick={() => setPhoto(`/field-staff/proofs/${d.id}/photo`)} className="text-brand"><ImageIcon className="size-4" /></button>}
              </div>
            ))}
            {trackData.visits.length === 0 && trackData.deliveries.length === 0 && <div className="text-sm text-ink-300 text-center py-6">{t('fieldStaff.noActivity')}</div>}
          </>
        ) : (
          <>
            {live && live.length === 0 && <div className="text-sm text-ink-300 text-center py-10">{t('fieldStaff.empty')}</div>}
            {(live || []).map(s => (
              <button key={s.id} onClick={() => setSel(s.id)} className="w-full text-left bg-surface border border-line rounded-xl px-4 py-3 hover:border-brand/40">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: liveColor(s) }} />
                  <span className="font-semibold text-ink-900 flex-1 truncate">{s.name}</span>
                  <Badge color={s.role === 'agent' ? 'brand' : 'warning'} dot={false}>{t(`role.${s.role}`)}</Badge>
                </div>
                <div className="flex items-center justify-between mt-1 text-xs text-ink-500">
                  <span>{s.on_shift ? `${t('fieldStaff.onShift')} · ${ago(s.last?.at, t)}` : t('fieldStaff.offShift')}</span>
                  <span className="flex items-center gap-2">
                    {s.role === 'agent' ? `${t('fieldStaff.visitsToday')}: ${s.today_visits}` : `${t('fieldStaff.deliveredToday')}: ${s.today_delivered}`}
                    {s.last?.battery != null && <span className={`flex items-center gap-0.5 ${s.last.battery < 20 ? 'text-danger' : ''}`}><Battery className="size-3.5" />{s.last.battery}%</span>}
                  </span>
                </div>
              </button>
            ))}
          </>
        )}
      </div>
      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
    </div>
  );
}

/* ── Hisobot ─────────────────────────────────────────────────────────────── */
function ReportTab() {
  const { t } = useLang();
  const [range, setRange] = useState(() => {
    const to = new Date(); const from = new Date(); from.setDate(from.getDate() - 6);
    return { from: from.toLocaleDateString('sv-SE'), to: to.toLocaleDateString('sv-SE') };
  });
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get('/field-staff/report', { params: { date_from: range.from, date_to: range.to } }).then(r => setData(r.data)).catch(() => setData(null));
  }, [range]);
  const inputCls = 'px-3 py-2 border border-line rounded-xl text-sm bg-surface';

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <input type="date" value={range.from} max={range.to} onChange={e => setRange(r => ({ ...r, from: e.target.value }))} className={inputCls} />
        <span className="text-ink-300">—</span>
        <input type="date" value={range.to} min={range.from} onChange={e => setRange(r => ({ ...r, to: e.target.value }))} className={inputCls} />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-ink-900 mb-2">{t('fieldStaff.agents')}</h3>
        <DataTable rows={data?.agents || []} emptyText={data ? t('fieldStaff.empty') : '…'} columns={[
          { key: 'name', label: t('common.name') },
          { key: 'plan', label: t('fieldStaff.planDone'), align: 'right', numeric: true, render: r => r.planned ? (
            <span className={r.plan_pct < 70 ? 'text-danger font-semibold' : ''}>{r.planned_done}/{r.planned} ({r.plan_pct}%)</span>) : '—' },
          { key: 'visits', label: t('fieldStaff.visits'), align: 'right', numeric: true },
          { key: 'unverified', label: t('fieldStaff.unverifiedCol'), align: 'right', numeric: true, render: r => r.unverified ? <span className="text-danger font-semibold">{r.unverified}</span> : 0 },
          { key: 'orders', label: t('fieldStaff.orders'), align: 'right', numeric: true, render: r => `${r.orders} · ${fmt(r.orders_sum)}` },
          { key: 'collected', label: t('fieldStaff.collected'), align: 'right', numeric: true, render: r => fmt(r.collected) },
          { key: 'cash_on_hand', label: t('fieldStaff.cashOnHand'), align: 'right', numeric: true, render: r => <span className={r.cash_on_hand > 0 ? 'text-warning font-semibold' : ''}>{fmt(r.cash_on_hand)}</span> },
        ]} />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-ink-900 mb-2">{t('fieldStaff.couriers')}</h3>
        <DataTable rows={data?.couriers || []} emptyText={data ? t('fieldStaff.empty') : '…'} columns={[
          { key: 'name', label: t('common.name') },
          { key: 'delivered', label: t('fieldStaff.delivered'), align: 'right', numeric: true },
          { key: 'failed', label: t('fieldStaff.failed'), align: 'right', numeric: true, render: r => r.failed ? <span className="text-danger">{r.failed}</span> : 0 },
          { key: 'cash_on_hand', label: t('fieldStaff.cashOnHand'), align: 'right', numeric: true, render: r => <span className={r.cash_on_hand > 0 ? 'text-warning font-semibold' : ''}>{fmt(r.cash_on_hand)}</span> },
        ]} />
      </div>
    </div>
  );
}

/* ── Xodimlar va qurilmalar ──────────────────────────────────────────────── */
function StaffTab() {
  const { t } = useLang();
  const [staff, setStaff] = useState(null);
  const load = useCallback(() => api.get('/field-staff/users').then(r => setStaff(r.data)).catch(() => setStaff([])), []);
  useEffect(() => { load(); }, [load]);

  const revoke = async (device) => {
    if (!window.confirm(t('fieldStaff.confirmRevoke'))) return;
    try { await api.post(`/field-staff/devices/${device.id}/revoke`); toast.success(t('fieldStaff.revoked')); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-4">
      <div className="text-sm text-ink-500 bg-surface border border-line rounded-2xl px-4 py-3">{t('fieldStaff.howTo')}</div>
      <DataTable rows={staff || []} emptyText={staff ? t('fieldStaff.empty') : '…'} columns={[
        { key: 'name', label: t('common.name'), render: u => <div><div className="font-medium text-ink-900">{u.name}</div><div className="text-xs text-ink-300">{u.phone}</div></div> },
        { key: 'role', label: t('fieldStaff.role'), render: u => <Badge color={u.role === 'agent' ? 'brand' : 'warning'} dot={false}>{t(`role.${u.role}`)}</Badge> },
        { key: 'wallet', label: t('fieldStaff.cashOnHand'), align: 'right', numeric: true, render: u => u.wallet
          ? <span className={`inline-flex items-center gap-1 ${u.wallet.balance > 0 ? 'text-warning font-semibold' : ''}`}><Wallet className="size-3.5" />{fmt(u.wallet.balance)}</span>
          : <span className="text-ink-300">—</span> },
        { key: 'devices', label: t('fieldStaff.devices'), render: u => u.devices.length === 0
          ? <span className="text-ink-300 text-xs">{t('fieldStaff.notLoggedIn')}</span>
          : (
            <div className="space-y-1">
              {u.devices.map(d => (
                <div key={d.id} className="flex items-center gap-2 text-xs">
                  <span className={d.revoked ? 'text-ink-300 line-through' : 'text-ink-900'}>{d.model || d.platform || 'Qurilma'}</span>
                  <span className="text-ink-300">· {ago(d.last_seen_at, t)}{d.app_version ? ` · v${d.app_version}` : ''}</span>
                  {!d.revoked && <button onClick={() => revoke(d)} title={t('fieldStaff.revoke')} className="text-danger hover:bg-danger/10 rounded p-0.5"><ShieldOff className="size-3.5" /></button>}
                </div>
              ))}
            </div>
          ) },
      ]} />
    </div>
  );
}

export default function FieldStaff() {
  const { t } = useLang();
  const [tab, setTab] = useState('live');
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brand flex items-center justify-center shadow-lg shadow-brand/20"><Smartphone className="size-5 text-white" /></div>
          <div>
            <h2 className="text-lg font-bold text-ink-900">{t('fieldStaff.title')}</h2>
            <p className="text-sm text-ink-500">{t('fieldStaff.subtitle')}</p>
          </div>
        </div>
        <Link to="/admin/employees" className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep">
          <UserPlus className="size-4" />{t('fieldStaff.add')}
        </Link>
      </div>
      <div className="flex bg-surface border border-line rounded-xl overflow-hidden shadow-sm w-fit">
        {[['live', t('fieldStaff.tabLive')], ['report', t('fieldStaff.tabReport')], ['staff', t('fieldStaff.tabStaff')]].map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} className={`px-5 py-2.5 text-sm font-semibold transition-all ${tab === v ? 'bg-brand text-white' : 'text-ink-500 hover:bg-surface-sunken'}`}>{l}</button>
        ))}
      </div>
      {tab === 'live' && <LiveTab />}
      {tab === 'report' && <ReportTab />}
      {tab === 'staff' && <StaffTab />}
    </div>
  );
}
