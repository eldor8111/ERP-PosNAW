import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Smartphone, UserPlus, Wallet, ShieldOff, Battery, Image as ImageIcon, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import MultiMap from '../../components/MultiMap';
import AssignCustomersModal from './AssignCustomersModal';

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

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function getVisitMeta(v, idx) {
  const isWarn = v.within_radius === false;
  const hasOrder = (v.order_sum && v.order_sum > 0) || v.result === 'sale' || v.result === 'order';
  const isPayment = v.result === 'payment';
  const isClosed = v.result === 'closed';
  const isRefused = v.result === 'refused' || v.result === 'no_need';

  if (isWarn) {
    return {
      color: '#EF4444',
      badge: idx + 1,
      subLabel: `⚠️ ${v.distance_m ?? 0}m`,
      statusText: "Radius buzilgan",
      tag: "Shubhali",
      isWarning: true,
      category: 'warning',
      badgeCls: 'bg-red-500 text-white',
      cardBorder: 'border-red-400 bg-red-50/30',
      pillCls: 'bg-red-100 text-red-700',
    };
  }
  if (hasOrder) {
    return {
      color: '#10B981',
      badge: idx + 1,
      subLabel: v.order_sum ? `${fmt(v.order_sum)} so'm` : "Buyurtma",
      statusText: "Buyurtma olindi",
      tag: "Buyurtma",
      isWarning: false,
      category: 'order',
      badgeCls: 'bg-emerald-600 text-white',
      cardBorder: 'border-emerald-300 hover:border-emerald-500 bg-emerald-50/20',
      pillCls: 'bg-emerald-100 text-emerald-800 font-bold',
    };
  }
  if (isPayment) {
    return {
      color: '#8B5CF6',
      badge: idx + 1,
      subLabel: "To'lov",
      statusText: "To'lov olindi",
      tag: "To'lov",
      isWarning: false,
      category: 'payment',
      badgeCls: 'bg-purple-600 text-white',
      cardBorder: 'border-purple-300 hover:border-purple-500',
      pillCls: 'bg-purple-100 text-purple-700',
    };
  }
  if (isClosed) {
    return {
      color: '#F59E0B',
      badge: idx + 1,
      subLabel: "Yopiq",
      statusText: "Do'kon yopiq",
      tag: "Yopiq",
      isWarning: false,
      category: 'closed',
      badgeCls: 'bg-amber-500 text-white',
      cardBorder: 'border-amber-300',
      pillCls: 'bg-amber-100 text-amber-800',
    };
  }
  if (isRefused) {
    return {
      color: '#F87171',
      badge: idx + 1,
      subLabel: "Rad etildi",
      statusText: "Rad etildi",
      tag: "Rad",
      isWarning: false,
      category: 'refused',
      badgeCls: 'bg-red-400 text-white',
      cardBorder: 'border-red-200',
      pillCls: 'bg-red-100 text-red-700',
    };
  }
  return {
    color: '#0284C7',
    badge: idx + 1,
    subLabel: "Tashrif",
    statusText: "Tashrif buyurildi",
    tag: "Tashrif",
    isWarning: false,
    category: 'visited',
    badgeCls: 'bg-sky-600 text-white',
    cardBorder: 'border-line hover:border-sky-400',
    pillCls: 'bg-sky-100 text-sky-800',
  };
}

function buildVisitPopupHtml(v, meta, idx) {
  return `
    <div style="font-family:Inter,system-ui,sans-serif;min-width:220px;padding:3px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:4px;">
        <span style="font-size:11px;font-weight:800;color:${meta.color};background:${meta.color}15;border:1px solid ${meta.color}40;padding:2px 8px;border-radius:12px;">#${idx + 1} · ${esc(meta.statusText)}</span>
        <span style="font-size:11px;color:#64748B;font-weight:600;">${hm(v.at)}${v.out ? `–${hm(v.out)}` : ''}</span>
      </div>
      <div style="font-size:14px;font-weight:700;color:#0F172A;line-height:1.3;margin-bottom:2px;">${esc(v.customer)}</div>
      ${v.territory ? `<div style="font-size:11px;color:#64748B;font-weight:600;">🏙 ${esc(v.territory)}</div>` : ''}
      ${v.address ? `<div style="font-size:11px;color:#64748B;margin-top:2px;">📍 ${esc(v.address)}</div>` : ''}
      <div style="margin-top:6px;padding-top:6px;border-top:1px solid #E2E8F0;display:flex;flex-direction:column;gap:3px;">
        ${v.duration_min != null ? `<div style="font-size:11px;color:#334155;">⏱ Vaqt: <b>${v.duration_min} daqiqa</b> do'konda bo'lgan</div>` : ''}
        ${v.order_sum ? `<div style="font-size:12px;font-weight:700;color:#059669;background:#ECFDF5;padding:4px 8px;border-radius:6px;margin-top:2px;">🛒 Buyurtma: ${fmt(v.order_sum)} so'm</div>` : ''}
        ${v.distance_m != null ? `<div style="font-size:11px;color:${v.within_radius === false ? '#DC2626;font-weight:700;' : '#64748B;'}">Masofa: ${v.distance_m} m ${v.within_radius === false ? '(⚠️ Radius buzilgan)' : '(Do\'kon ichida)'}</div>` : ''}
        ${v.note ? `<div style="font-size:11px;color:#475569;background:#F8FAFC;border:1px solid #E2E8F0;padding:4px 6px;border-radius:6px;margin-top:3px;">💬 "${esc(v.note)}"</div>` : ''}
      </div>
    </div>
  `;
}

/* ── Jonli xarita + kunlik trek ─────────────────────────────────────────── */
function LiveTab() {
  const { t } = useLang();
  const [live, setLive] = useState(null);
  const [sel, setSel] = useState(null);
  const [day, setDay] = useState(today());
  const [trackData, setTrackData] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [activeMarkerId, setActiveMarkerId] = useState(null);
  const [filter, setFilter] = useState('all'); // all, order, visited, warning

  const loadLive = useCallback(() => api.get('/field-staff/live', { _silent: true }).then(r => setLive(r.data)).catch(() => setLive([])), []);
  useEffect(() => {
    loadLive();
    const id = setInterval(loadLive, 30000);
    return () => clearInterval(id);
  }, [loadLive]);

  useEffect(() => {
    if (!sel) return;
    setActiveMarkerId(null);
    setFilter('all');
    api.get('/field-staff/track', { params: { user_id: sel, day } }).then(r => setTrackData(r.data)).catch(() => setTrackData(null));
  }, [sel, day]);

  const markers = useMemo(() => {
    if (sel && trackData) {
      const vm = trackData.visits.filter(v => v.lat != null).map((v, idx) => {
        const meta = getVisitMeta(v, idx);
        return {
          id: `v${v.id}`,
          lat: v.lat,
          lng: v.lng,
          label: v.customer,
          subLabel: meta.subLabel,
          badge: meta.badge,
          color: meta.color,
          isWarning: meta.isWarning,
          htmlPopup: buildVisitPopupHtml(v, meta, idx),
          title: `${v.customer} · ${meta.statusText}`,
        };
      });
      const dm = trackData.deliveries.filter(d => d.lat != null).map((d) => ({
        id: `d${d.id}`,
        lat: d.lat,
        lng: d.lng,
        label: `Yetkazish`,
        subLabel: hm(d.at),
        badge: '🚚',
        color: '#2554C7',
        title: `🚚 Yetkazildi · ${hm(d.at)}${d.distance_m != null ? ` · ${d.distance_m} m` : ''}`,
      }));
      const lastPt = trackData.points.at(-1);
      const liveMarker = lastPt ? [{
        id: 'last',
        lat: lastPt[0],
        lng: lastPt[1],
        label: `${trackData.user.name} (Jonli)`,
        subLabel: hm(lastPt[2]),
        badge: '📍',
        color: '#4F46E5',
        isLive: true,
        title: `Jonli joy: ${trackData.user.name} (${hm(lastPt[2])})`,
      }] : [];
      return [...vm, ...dm, ...liveMarker];
    }
    return (live || []).filter(s => s.last).map((s) => ({
      id: s.id,
      lat: s.last.lat,
      lng: s.last.lng,
      label: s.name,
      subLabel: s.last.battery != null ? `🔋${s.last.battery}%` : ago(s.last.at, t),
      badge: s.role === 'agent' ? 'A' : 'K',
      color: liveColor(s),
      isLive: s.on_shift && (minsAgo(s.last.at) ?? 999) <= 10,
      title: `${s.name} · ${ago(s.last.at, t)}`,
      htmlPopup: `
        <div style="font-family:Inter,system-ui,sans-serif;min-width:180px;padding:3px;">
          <div style="font-weight:700;font-size:13px;color:#0F172A;">${esc(s.name)}</div>
          <div style="font-size:11px;color:#64748B;margin-top:2px;">${esc(t(`role.${s.role}`))} · ${s.on_shift ? '🟢 Smenada' : '⚪ Smenadan tashqari'}</div>
          <div style="font-size:11px;color:#475569;margin-top:4px;">⏱ Oxirgi signal: <b>${ago(s.last.at, t)}</b></div>
          ${s.last.battery != null ? `<div style="font-size:11px;color:#475569;">🔋 Batareya: <b>${s.last.battery}%</b></div>` : ''}
          <div style="font-size:11px;color:#059669;margin-top:2px;">📍 Bugungi tashriflar: <b>${s.today_visits ?? s.today_delivered ?? 0}</b></div>
        </div>
      `,
    }));
  }, [sel, trackData, live, t]);

  const path = useMemo(() => (sel && trackData ? trackData.points.map(p => [p[0], p[1]]) : []), [sel, trackData]);

  // Statistikalar (agent uchun)
  const stats = useMemo(() => {
    if (!trackData) return null;
    const visits = trackData.visits || [];
    const totalOrderSum = visits.reduce((a, v) => a + (v.order_sum || 0), 0);
    const orderCount = visits.filter(v => (v.order_sum && v.order_sum > 0) || v.result === 'sale' || v.result === 'order').length;
    const warnCount = visits.filter(v => v.within_radius === false).length;
    return {
      distanceKm: trackData.total_distance_km ?? 0,
      totalVisits: visits.length,
      orderCount,
      totalOrderSum,
      warnCount,
    };
  }, [trackData]);

  const filteredVisits = useMemo(() => {
    if (!trackData?.visits) return [];
    return trackData.visits.filter((v, idx) => {
      const meta = getVisitMeta(v, idx);
      if (filter === 'order') return meta.category === 'order';
      if (filter === 'visited') return meta.category === 'visited';
      if (filter === 'warning') return meta.category === 'warning';
      return true;
    });
  }, [trackData, filter]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      {/* Chap tomon: Karta va Ranglar afsonasi */}
      <div className="xl:col-span-2 space-y-2">
        <MultiMap
          markers={markers}
          path={path}
          height={580}
          activeMarkerId={activeMarkerId}
          onMarkerClick={(id) => setActiveMarkerId(id)}
          fitKey={sel ? `${sel}-${day}-${trackData?.points.length}` : `live-${live?.length}`}
        />

        {/* Ranglar afsonasi (Legend) */}
        {sel && trackData ? (
          <div className="flex items-center justify-between flex-wrap gap-2 px-3 py-2 bg-surface border border-line rounded-xl text-xs text-ink-700">
            <span className="font-semibold text-ink-900">Belgilar ma'nosi:</span>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-emerald-500 shrink-0" /><span className="font-medium">Buyurtma olingan</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-sky-500 shrink-0" /><span>Faqat tashrif</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-purple-500 shrink-0" /><span>To'lov</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-amber-500 shrink-0" /><span>Yopiq</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-500 shrink-0" /><span className="text-danger font-semibold">Radius buzilgan</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-indigo-600 shrink-0" /><span>Jonli joy</span></div>
          </div>
        ) : (
          <div className="flex items-center gap-3 px-3 py-2 bg-surface border border-line rounded-xl text-xs text-ink-700">
            <span className="font-semibold text-ink-900">Xodim holati:</span>
            <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-600 shrink-0 animate-pulse" /><span>Faol (Smenada)</span></div>
            <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-600 shrink-0" /><span>Kutmoqda (&gt;10 min)</span></div>
            <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-slate-400 shrink-0" /><span>Smenadan tashqari</span></div>
          </div>
        )}
      </div>

      {/* O'ng tomon: Xodimlar ro'yxati yoki Tanlangan xodim treki */}
      <div className="space-y-3 max-h-[640px] overflow-y-auto pr-1">
        {sel && trackData ? (
          <>
            {/* Navigatsiya va sana tanlash */}
            <div className="flex items-center justify-between gap-2">
              <button
                onClick={() => { setSel(null); setTrackData(null); setActiveMarkerId(null); }}
                className="inline-flex items-center gap-1 text-sm text-brand font-semibold hover:underline"
              >
                ← {t('fieldStaff.allStaff')}
              </button>
              <input
                type="date"
                value={day}
                max={today()}
                onChange={e => setDay(e.target.value)}
                className="px-3 py-1.5 border border-line rounded-lg text-sm bg-surface font-medium"
              />
            </div>

            {/* Agent qisqacha ma'lumot va KPI bloklari */}
            <div className="bg-surface border border-line rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-bold text-base text-ink-900">{trackData.user.name}</div>
                  <div className="text-xs text-ink-500 mt-0.5">
                    {trackData.shifts.length === 0 ? t('fieldStaff.noShift') : trackData.shifts.map((s, i) => (
                      <span key={i}>⏱ Smena: {hm(s.started_at)} — {s.ended_at ? hm(s.ended_at) : 'hozir'}</span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => setActiveMarkerId('last')}
                  className="px-2.5 py-1 text-xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg border border-indigo-200"
                >
                  📍 Jonli joy
                </button>
              </div>

              {/* 4 ta KPI ko'rsatkichlari */}
              {stats && (
                <div className="grid grid-cols-2 gap-2 pt-1 border-t border-line">
                  <div className="bg-surface-sunken p-2.5 rounded-xl">
                    <div className="text-[11px] text-ink-500 font-medium">Jami masofa</div>
                    <div className="text-base font-bold text-ink-900 tabular-nums">🚗 {stats.distanceKm} km</div>
                  </div>
                  <div className="bg-surface-sunken p-2.5 rounded-xl">
                    <div className="text-[11px] text-ink-500 font-medium">Buyurtmalar</div>
                    <div className="text-base font-bold text-emerald-700 tabular-nums">{stats.orderCount} / {stats.totalVisits} ta</div>
                  </div>
                  <div className="bg-surface-sunken p-2.5 rounded-xl col-span-2">
                    <div className="text-[11px] text-ink-500 font-medium">Olingan buyurtma summasi</div>
                    <div className="text-base font-bold text-emerald-700 tabular-nums">💰 {fmt(stats.totalOrderSum)} so'm</div>
                  </div>
                </div>
              )}
            </div>

            {/* Filtr tugmalari */}
            <div className="flex items-center gap-1 bg-surface-sunken p-1 rounded-xl text-xs font-semibold">
              <button
                onClick={() => setFilter('all')}
                className={`flex-1 py-1.5 rounded-lg transition-all ${filter === 'all' ? 'bg-surface text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-900'}`}
              >
                Barchasi ({trackData.visits.length})
              </button>
              <button
                onClick={() => setFilter('order')}
                className={`flex-1 py-1.5 rounded-lg transition-all ${filter === 'order' ? 'bg-emerald-600 text-white shadow-sm' : 'text-emerald-700 hover:text-emerald-900'}`}
              >
                🛒 Savdo ({stats?.orderCount || 0})
              </button>
              {stats?.warnCount > 0 && (
                <button
                  onClick={() => setFilter('warning')}
                  className={`flex-1 py-1.5 rounded-lg transition-all ${filter === 'warning' ? 'bg-danger text-white shadow-sm' : 'text-danger hover:text-danger/80'}`}
                >
                  ⚠️ Shubhali ({stats.warnCount})
                </button>
              )}
            </div>

            {/* Tashriflar ro'yxati (Timeline) */}
            <div className="space-y-2">
              {filteredVisits.map((v) => {
                const idx = trackData.visits.indexOf(v);
                const meta = getVisitMeta(v, idx);
                const isSelected = activeMarkerId === `v${v.id}`;

                return (
                  <div
                    key={v.id}
                    onClick={() => setActiveMarkerId(`v${v.id}`)}
                    className={`bg-surface border rounded-xl p-3 text-sm cursor-pointer transition-all ${
                      isSelected
                        ? 'ring-2 ring-brand shadow-md border-brand'
                        : meta.cardBorder
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2 min-w-0">
                        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-extrabold shrink-0 mt-0.5 ${meta.badgeCls}`}>
                          {idx + 1}
                        </span>
                        <div className="min-w-0">
                          <span className="font-bold text-ink-900 block truncate">{v.customer}</span>
                          {v.territory && <span className="text-[11px] text-ink-500 block truncate">🏙 {v.territory}</span>}
                          {v.address && <span className="text-[11px] text-ink-400 block truncate">📍 {v.address}</span>}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="text-xs font-semibold text-ink-700 block">{hm(v.at)}{v.out ? `–${hm(v.out)}` : ''}</span>
                        {v.duration_min != null && <span className="text-[10px] text-ink-400 block">⏱ {v.duration_min} daq</span>}
                      </div>
                    </div>

                    {/* Holat va narx nishonlari */}
                    <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-line/60 text-xs">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${meta.pillCls}`}>
                          {meta.statusText}
                        </span>
                        {v.order_sum ? (
                          <span className="font-bold text-emerald-700 tabular-nums">
                            {fmt(v.order_sum)} so'm
                          </span>
                        ) : null}
                      </div>

                      <div className="flex items-center gap-2">
                        {v.within_radius === false ? (
                          <span className="text-danger font-semibold text-[11px]">
                            ⚠️ {v.distance_m ?? 0}m uzoq
                          </span>
                        ) : v.distance_m != null ? (
                          <span className="text-ink-400 text-[11px]">{v.distance_m}m</span>
                        ) : null}

                        {v.has_photo && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setPhoto(`/field-staff/visits/${v.id}/photo`); }}
                            className="p-1 text-brand hover:bg-brand/10 rounded-md"
                            title="Tashrif rasmini ko'rish"
                          >
                            <ImageIcon className="size-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {v.note && (
                      <div className="mt-2 text-xs text-ink-600 bg-surface-sunken p-1.5 rounded-lg italic">
                        "{v.note}"
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Kuryer yetkazishlari */}
              {trackData.deliveries.map(d => (
                <div
                  key={d.id}
                  onClick={() => setActiveMarkerId(`d${d.id}`)}
                  className={`bg-surface border rounded-xl px-3 py-2.5 text-sm flex items-center justify-between cursor-pointer transition-all ${
                    activeMarkerId === `d${d.id}` ? 'ring-2 ring-brand border-brand' : 'border-line hover:border-brand/40'
                  }`}
                >
                  <span className="font-medium text-ink-900">🚚 Yetkazildi: {hm(d.at)}{d.distance_m != null ? ` · ${d.distance_m} m` : ''}</span>
                  {d.has_photo && (
                    <button
                      onClick={(e) => { e.stopPropagation(); setPhoto(`/field-staff/proofs/${d.id}/photo`); }}
                      className="text-brand p-1"
                    >
                      <ImageIcon className="size-4" />
                    </button>
                  )}
                </div>
              ))}

              {filteredVisits.length === 0 && trackData.deliveries.length === 0 && (
                <div className="text-sm text-ink-300 text-center py-8">{t('fieldStaff.noActivity')}</div>
              )}
            </div>
          </>
        ) : (
          /* Barcha xodimlar umumiy ro'yxati */
          <>
            <div className="text-sm font-bold text-ink-900 px-1 flex items-center justify-between">
              <span>{t('fieldStaff.allStaff')} ({live?.length ?? 0})</span>
              <span className="text-xs font-normal text-ink-500">Real vaqt</span>
            </div>
            {live && live.length === 0 && <div className="text-sm text-ink-300 text-center py-10">{t('fieldStaff.empty')}</div>}
            {(live || []).map(s => (
              <button
                key={s.id}
                onClick={() => setSel(s.id)}
                className="w-full text-left bg-surface border border-line rounded-xl px-4 py-3 hover:border-brand/60 hover:shadow-sm transition-all"
              >
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: liveColor(s) }} />
                  <span className="font-semibold text-ink-900 flex-1 truncate">{s.name}</span>
                  <Badge color={s.role === 'agent' ? 'brand' : 'warning'} dot={false}>{t(`role.${s.role}`)}</Badge>
                </div>
                <div className="flex items-center justify-between mt-1.5 text-xs text-ink-500">
                  <span>{s.on_shift ? `🟢 ${t('fieldStaff.onShift')} · ${ago(s.last?.at, t)}` : `⚪ ${t('fieldStaff.offShift')}`}</span>
                  <span className="flex items-center gap-2 font-medium">
                    {s.role === 'agent' ? `📍 ${s.today_visits} ta tashrif` : `🚚 ${s.today_delivered} ta yetkazildi`}
                    {s.last?.battery != null && (
                      <span className={`flex items-center gap-0.5 ${s.last.battery < 20 ? 'text-danger font-bold' : ''}`}>
                        <Battery className="size-3.5" />{s.last.battery}%
                      </span>
                    )}
                  </span>
                </div>
                <div className="mt-2 text-right">
                  <span className="text-xs text-brand font-semibold hover:underline">Kunlik marshrutni ko'rish →</span>
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
  const [assigning, setAssigning] = useState(null);
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
        { key: 'customers', label: t('fieldStaff.customers'), render: u => u.role === 'agent' ? (
          <button onClick={() => setAssigning(u)}
            className={`text-xs font-semibold px-2.5 py-1 rounded-lg ${u.customers_count ? 'bg-brand/10 text-brand' : 'bg-warning/10 text-warning'}`}>
            {u.customers_count ? `${u.customers_count} ${t('fieldStaff.customersShort')}` : t('fieldStaff.assignCustomers')}
          </button>
        ) : <span className="text-ink-300">—</span> },
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
      {assigning && <AssignCustomersModal agent={assigning} onClose={() => setAssigning(null)} onSaved={() => { setAssigning(null); load(); }} />}
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
