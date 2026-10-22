import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  MapPin, Navigation, Users, CheckCircle2, AlertTriangle, Battery, Smartphone,
  DollarSign, Calendar, Filter, RefreshCw, ChevronRight, UserPlus, ShieldOff,
  Search, TrendingUp, Clock, Store, Eye, X, ArrowUpRight, Award, PieChart,
  FileText, Download, Phone, Check, AlertCircle, ShoppingBag, Truck, CheckSquare,
  BarChart3, Layers, Compass
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import MultiMap from '../../components/MultiMap';
import AssignCustomersModal from './AssignCustomersModal';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const hm = (iso) => (iso ? new Date(iso).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : '—');
const today = () => new Date().toLocaleDateString('sv-SE');
const minsAgo = (iso) => (iso ? Math.round((Date.now() - new Date(iso).getTime()) / 60000) : null);

function ago(iso, t) {
  const min = minsAgo(iso);
  if (min == null) return t ? t('fieldStaff.never') : 'Hech qachon';
  if (min < 1) return t ? t('fieldStaff.justNow') : 'Hozirgina';
  if (min < 60) return `${min} ${t ? t('fieldStaff.minAgo') : 'daq oldin'}`;
  if (min < 1440) return `${Math.round(min / 60)} ${t ? t('fieldStaff.hourAgo') : 'soat oldin'}`;
  return new Date(iso).toLocaleDateString('uz-UZ');
}

const liveColor = (s) =>
  !s.on_shift ? '#9AA3B2' : (minsAgo(s.last?.at) ?? 999) <= 10 ? '#10B981' : '#F59E0B';

function PhotoModal({ url, onClose }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let obj;
    api
      .get(url, { responseType: 'blob' })
      .then((r) => {
        obj = URL.createObjectURL(r.data);
        setSrc(obj);
      })
      .catch(() => toast.error('Rasm yuklanmadi'));
    return () => {
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [url]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <button className="absolute top-5 right-5 text-white/80 hover:text-white p-2 rounded-full bg-white/10 transition-colors">
        <X className="size-6" />
      </button>
      {src ? (
        <img src={src} alt="Visit proof" className="max-h-[90vh] max-w-[90vw] object-contain rounded-2xl shadow-2xl border border-white/10" />
      ) : (
        <div className="flex flex-col items-center gap-2 text-white">
          <RefreshCw className="size-8 animate-spin" />
          <span className="text-sm">Rasm yuklanmoqda...</span>
        </div>
      )}
    </div>
  );
}

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

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
      statusText: 'Radius buzilgan',
      tag: 'Shubhali',
      isWarning: true,
      category: 'warning',
      badgeCls: 'bg-red-500 text-white',
      cardBorder: 'border-red-400 bg-red-50/40',
      pillCls: 'bg-red-100 text-red-700 font-semibold',
    };
  }
  if (hasOrder) {
    return {
      color: '#10B981',
      badge: idx + 1,
      subLabel: v.order_sum ? `${fmt(v.order_sum)} so'm` : 'Buyurtma',
      statusText: 'Buyurtma olindi',
      tag: 'Buyurtma',
      isWarning: false,
      category: 'order',
      badgeCls: 'bg-emerald-600 text-white',
      cardBorder: 'border-emerald-300 hover:border-emerald-500 bg-emerald-50/30',
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
      cardBorder: 'border-purple-300 hover:border-purple-500 bg-purple-50/20',
      pillCls: 'bg-purple-100 text-purple-700 font-medium',
    };
  }
  if (isClosed) {
    return {
      color: '#F59E0B',
      badge: idx + 1,
      subLabel: 'Yopiq',
      statusText: "Do'kon yopiq",
      tag: 'Yopiq',
      isWarning: false,
      category: 'closed',
      badgeCls: 'bg-amber-500 text-white',
      cardBorder: 'border-amber-300 bg-amber-50/20',
      pillCls: 'bg-amber-100 text-amber-800 font-medium',
    };
  }
  if (isRefused) {
    return {
      color: '#F87171',
      badge: idx + 1,
      subLabel: 'Rad etildi',
      statusText: 'Rad etildi',
      tag: 'Rad',
      isWarning: false,
      category: 'refused',
      badgeCls: 'bg-red-400 text-white',
      cardBorder: 'border-red-200 bg-red-50/20',
      pillCls: 'bg-red-100 text-red-700',
    };
  }
  return {
    color: '#0284C7',
    badge: idx + 1,
    subLabel: 'Tashrif',
    statusText: 'Tashrif buyurildi',
    tag: 'Tashrif',
    isWarning: false,
    category: 'visited',
    badgeCls: 'bg-sky-600 text-white',
    cardBorder: 'border-slate-200 hover:border-sky-400 bg-white',
    pillCls: 'bg-sky-100 text-sky-800 font-medium',
  };
}

function buildVisitPopupHtml(v, meta, idx) {
  return `
    <div style="font-family:Inter,system-ui,sans-serif;min-width:230px;padding:4px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:6px;">
        <span style="font-size:11px;font-weight:800;color:${meta.color};background:${meta.color}15;border:1px solid ${meta.color}40;padding:2px 8px;border-radius:12px;">#${idx + 1} • ${esc(meta.statusText)}</span>
        <span style="font-size:11px;color:#64748B;font-weight:600;">${hm(v.at)}${v.out ? `—${hm(v.out)}` : ''}</span>
      </div>
      <div style="font-size:14px;font-weight:700;color:#0F172A;line-height:1.3;margin-bottom:3px;">${esc(v.customer)}</div>
      ${v.territory ? `<div style="font-size:11px;color:#64748B;font-weight:600;">📍 ${esc(v.territory)}</div>` : ''}
      ${v.address ? `<div style="font-size:11px;color:#64748B;margin-top:2px;">🏢 ${esc(v.address)}</div>` : ''}
      <div style="margin-top:8px;padding-top:6px;border-top:1px solid #E2E8F0;display:flex;flex-direction:column;gap:3px;">
        ${v.duration_min != null ? `<div style="font-size:11px;color:#334155;">⏱ Vaqt: <b>${v.duration_min} daqiqa</b> do'konda bo'lgan</div>` : ''}
        ${v.order_sum ? `<div style="font-size:12px;font-weight:700;color:#059669;background:#ECFDF5;padding:4px 8px;border-radius:6px;margin-top:2px;">🛒 Buyurtma: ${fmt(v.order_sum)} so'm</div>` : ''}
        ${v.distance_m != null ? `<div style="font-size:11px;color:${v.within_radius === false ? '#DC2626;font-weight:700;' : '#64748B;'}">Masofa: ${v.distance_m} m ${v.within_radius === false ? '(⚠️ Radius buzilgan)' : "(Do'kon ichida)"}</div>` : ''}
        ${v.note ? `<div style="font-size:11px;color:#475569;background:#F8FAFC;border:1px solid #E2E8F0;padding:4px 6px;border-radius:6px;margin-top:3px;">💬 "${esc(v.note)}"</div>` : ''}
      </div>
    </div>
  `;
}

/* =========================================================================
   TAB 1: JONLI XARITA VA MONITORING
   ========================================================================= */
function LiveTab({ liveStaff, selectedAgent, setSelectedAgent, day, setDay }) {
  const { t } = useLang();
  const [trackData, setTrackData] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [activeMarkerId, setActiveMarkerId] = useState(null);
  const [filter, setFilter] = useState('all'); // all, order, visited, warning

  useEffect(() => {
    if (!selectedAgent) {
      setTrackData(null);
      return;
    }
    setActiveMarkerId(null);
    setFilter('all');
    api
      .get('/field-staff/track', { params: { user_id: selectedAgent, day } })
      .then((r) => setTrackData(r.data))
      .catch(() => setTrackData(null));
  }, [selectedAgent, day]);

  const markers = useMemo(() => {
    if (selectedAgent && trackData) {
      const vm = (trackData.visits || [])
        .filter((v) => v.lat != null)
        .map((v, idx) => {
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
            title: `${v.customer} • ${meta.statusText}`,
          };
        });

      const dm = (trackData.deliveries || [])
        .filter((d) => d.lat != null)
        .map((d) => ({
          id: `d${d.id}`,
          lat: d.lat,
          lng: d.lng,
          label: 'Yetkazish',
          subLabel: hm(d.at),
          badge: '🚚',
          color: '#2563EB',
          title: `🚚 Yetkazildi • ${hm(d.at)}${d.distance_m != null ? ` • ${d.distance_m} m` : ''}`,
        }));

      const lastPt = trackData.points?.at(-1);
      const liveMarker = lastPt
        ? [
            {
              id: 'last',
              lat: lastPt[0],
              lng: lastPt[1],
              label: `${trackData.user?.name} (Jonli)`,
              subLabel: hm(lastPt[2]),
              badge: '📍',
              color: '#4F46E5',
              isLive: true,
              title: `Jonli joy: ${trackData.user?.name} (${hm(lastPt[2])})`,
            },
          ]
        : [];

      return [...vm, ...dm, ...liveMarker];
    }

    return (liveStaff || [])
      .filter((s) => s.last)
      .map((s) => ({
        id: s.id,
        lat: s.last.lat,
        lng: s.last.lng,
        label: s.name,
        subLabel: s.last.battery != null ? `🔋 ${s.last.battery}%` : ago(s.last.at, t),
        badge: s.role === 'agent' ? 'A' : 'K',
        color: liveColor(s),
        isLive: s.on_shift && (minsAgo(s.last.at) ?? 999) <= 10,
        title: `${s.name} • ${ago(s.last.at, t)}`,
        htmlPopup: `
          <div style="font-family:Inter,system-ui,sans-serif;min-width:190px;padding:4px;">
            <div style="font-weight:700;font-size:13px;color:#0F172A;">${esc(s.name)}</div>
            <div style="font-size:11px;color:#64748B;margin-top:2px;">${esc(t(`role.${s.role}`))} • ${s.on_shift ? '🟢 Smenada' : '⚪ Smenadan tashqari'}</div>
            <div style="font-size:11px;color:#475569;margin-top:4px;">⏱ Oxirgi signal: <b>${ago(s.last.at, t)}</b></div>
            ${s.last.battery != null ? `<div style="font-size:11px;color:#475569;">🔋 Batareya: <b>${s.last.battery}%</b></div>` : ''}
            <div style="font-size:11px;color:#059669;margin-top:2px;">📍 Bugungi tashriflar: <b>${s.today_visits ?? s.today_delivered ?? 0}</b></div>
          </div>
        `,
      }));
  }, [selectedAgent, trackData, liveStaff, t]);

  const path = useMemo(
    () => (selectedAgent && trackData?.points ? trackData.points.map((p) => [p[0], p[1]]) : []),
    [selectedAgent, trackData]
  );

  const stats = useMemo(() => {
    if (!trackData) return null;
    const visits = trackData.visits || [];
    const totalOrderSum = visits.reduce((a, v) => a + (v.order_sum || 0), 0);
    const orderCount = visits.filter(
      (v) => (v.order_sum && v.order_sum > 0) || v.result === 'sale' || v.result === 'order'
    ).length;
    const warnCount = visits.filter((v) => v.within_radius === false).length;
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
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
      {/* Chap/Asosiy tomon: Xarita va Ranglar legendasi */}
      <div className="xl:col-span-2 space-y-3">
        <div className="relative rounded-2xl overflow-hidden border border-slate-200/80 shadow-sm bg-white">
          <MultiMap
            markers={markers}
            path={path}
            height={620}
            activeMarkerId={activeMarkerId}
            onMarkerClick={(id) => setActiveMarkerId(id)}
            fitKey={selectedAgent ? `${selectedAgent}-${day}-${trackData?.points?.length}` : `live-${liveStaff?.length}`}
          />
        </div>

        {/* Legend */}
        {selectedAgent && trackData ? (
          <div className="flex items-center justify-between flex-wrap gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 shadow-sm">
            <span className="font-semibold text-slate-900">Belgilar:</span>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-emerald-500 shrink-0" /><span className="font-medium text-emerald-800">Buyurtma olingan</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-sky-500 shrink-0" /><span className="text-sky-800">Tashrif</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-purple-500 shrink-0" /><span className="text-purple-800">To'lov</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-amber-500 shrink-0" /><span className="text-amber-800">Yopiq</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-500 shrink-0" /><span className="text-red-700 font-semibold">Radius buzilgan</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-indigo-600 shrink-0" /><span>Hozirgi joy</span></div>
          </div>
        ) : (
          <div className="flex items-center gap-4 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 shadow-sm">
            <span className="font-semibold text-slate-900">Xodim holati:</span>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-emerald-500" /><span>Onlayn (faol)</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-amber-500" /><span>Signal eski (10+ daq)</span></div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-slate-400" /><span>Smenadan tashqari</span></div>
          </div>
        )}
      </div>

      {/* O'ng tomon: Boshqaruv & Agentlar / Vizitlar paneli */}
      <div className="space-y-4">
        {/* Agent tanlash va Sana boshqaruvi */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <Compass className="size-4 text-blue-600" />
              {selectedAgent ? 'Agent marshruti' : 'Dala xodimlari'}
            </h3>
            {selectedAgent && (
              <button
                onClick={() => setSelectedAgent(null)}
                className="text-xs text-blue-600 hover:text-blue-800 font-semibold"
              >
                ← Barchasi
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <input
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
              className="flex-1 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          {/* Tanlangan agent uchun KPI metrikalar */}
          {selectedAgent && stats && (
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-100">
              <div className="p-2.5 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-500 font-medium">Bosib o'tildi</div>
                <div className="text-base font-bold text-slate-900 tabular-nums">🚗 {stats.distanceKm} km</div>
              </div>
              <div className="p-2.5 bg-emerald-50/60 rounded-xl border border-emerald-100">
                <div className="text-[11px] text-emerald-700 font-medium">Buyurtmalar</div>
                <div className="text-base font-bold text-emerald-800 tabular-nums">{stats.orderCount} / {stats.totalVisits} ta</div>
              </div>
              <div className="p-2.5 bg-emerald-500 text-white rounded-xl col-span-2 shadow-sm">
                <div className="text-[11px] text-emerald-100 font-medium">Buyurtma summasi</div>
                <div className="text-lg font-extrabold tabular-nums">💰 {fmt(stats.totalOrderSum)} so'm</div>
              </div>
              {stats.warnCount > 0 && (
                <div className="p-2 bg-red-50 border border-red-200 text-red-700 rounded-xl col-span-2 text-xs flex items-center gap-1.5 font-medium">
                  <AlertTriangle className="size-4 text-red-500 shrink-0" />
                  <span>{stats.warnCount} ta tashrifda do'kondan chetda bo'lgan!</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Ro'yxat: Yoki agentlar kartalari, yoki agentning tashriflar lentasi */}
        <div className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm max-h-[500px] overflow-y-auto space-y-2">
          {!selectedAgent ? (
            /* Barcha xodimlar kartochkalari */
            (liveStaff || []).map((s) => (
              <div
                key={s.id}
                onClick={() => setSelectedAgent(s.id)}
                className="p-3 rounded-xl border border-slate-100 hover:border-blue-300 hover:bg-blue-50/30 transition-all cursor-pointer flex items-center justify-between group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="relative">
                    <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center font-bold text-slate-700">
                      {s.name?.slice(0, 2).toUpperCase()}
                    </div>
                    <span
                      className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white"
                      style={{ backgroundColor: liveColor(s) }}
                    />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-900 text-sm truncate group-hover:text-blue-600 transition-colors">
                      {s.name}
                    </div>
                    <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                      <span className="capitalize">{s.role === 'agent' ? 'Savdo agenti' : 'Kurier'}</span>
                      {s.last?.battery != null && (
                        <span className="flex items-center gap-0.5 text-slate-600 font-medium">
                          <Battery className="size-3 text-emerald-600" /> {s.last.battery}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <div className="text-xs font-bold text-slate-900 tabular-nums">
                    {s.today_visits ?? s.today_delivered ?? 0} ta
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{ago(s.last?.at, t)}</div>
                </div>
              </div>
            ))
          ) : (
            /* Tanlangan agent tashriflari lentasi */
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 pb-2 border-b border-slate-100 text-xs">
                {[['all', 'Barchasi'], ['order', 'Buyurtmalar'], ['visited', 'Tashrif'], ['warning', 'Shubhali']].map(
                  ([key, label]) => (
                    <button
                      key={key}
                      onClick={() => setFilter(key)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                        filter === key ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {label}
                    </button>
                  )
                )}
              </div>

              {filteredVisits.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">Tashriflar topilmadi</div>
              ) : (
                filteredVisits.map((v, idx) => {
                  const meta = getVisitMeta(v, idx);
                  const isMarkerActive = activeMarkerId === `v${v.id}`;
                  return (
                    <div
                      key={v.id}
                      onClick={() => setActiveMarkerId(`v${v.id}`)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer ${meta.cardBorder} ${
                        isMarkerActive ? 'ring-2 ring-blue-500 shadow-md' : 'shadow-none'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${meta.pillCls}`}>
                          #{idx + 1} {meta.tag}
                        </span>
                        <span className="text-slate-500 font-medium">{hm(v.at)}</span>
                      </div>
                      <div className="font-bold text-slate-900 text-sm">{v.customer}</div>
                      {v.address && <div className="text-xs text-slate-500 truncate mt-0.5">{v.address}</div>}

                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100/80 text-xs">
                        {v.order_sum ? (
                          <span className="font-bold text-emerald-700 tabular-nums">{fmt(v.order_sum)} so'm</span>
                        ) : (
                          <span className="text-slate-400">Buyurtmasiz</span>
                        )}

                        {v.has_photo && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setPhoto(`/field-staff/visits/${v.id}/photo`);
                            }}
                            className="text-xs text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
                          >
                            <Eye className="size-3.5" /> Rasm
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
    </div>
  );
}

/* =========================================================================
   TAB 2: TASHRIFLAR VA VIZITLAR JURNALI (VISITS TABLE)
   ========================================================================= */
function VisitsTab({ day }) {
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [photo, setPhoto] = useState(null);

  const loadVisits = useCallback(async () => {
    setLoading(true);
    try {
      // Backend track yoki live dan yuklash
      const { data } = await api.get('/field-staff/live');
      // Barcha agentlar bo'yicha tashriflarni jamlash
      const all = [];
      for (const st of data || []) {
        if (st.role === 'agent') {
          try {
            const tr = await api.get('/field-staff/track', { params: { user_id: st.id, day } });
            (tr.data?.visits || []).forEach((v) => {
              all.push({ ...v, agent_name: st.name, agent_id: st.id });
            });
          } catch {}
        }
      }
      setVisits(all);
    } catch {
      setVisits([]);
    } finally {
      setLoading(false);
    }
  }, [day]);

  useEffect(() => {
    loadVisits();
  }, [loadVisits]);

  const filtered = useMemo(() => {
    return visits.filter(
      (v) =>
        v.customer?.toLowerCase().includes(q.toLowerCase()) ||
        v.agent_name?.toLowerCase().includes(q.toLowerCase())
    );
  }, [visits, q]);

  const columns = [
    {
      key: 'agent_name',
      label: 'Agent',
      render: (r) => (
        <div>
          <div className="font-bold text-slate-900">{r.agent_name}</div>
          <div className="text-xs text-slate-400">ID: #{r.agent_id}</div>
        </div>
      ),
    },
    {
      key: 'customer',
      label: 'Savdo nuqtasi',
      render: (r) => (
        <div>
          <div className="font-semibold text-slate-900">{r.customer}</div>
          <div className="text-xs text-slate-500">{r.address || r.territory || "Manzil ko'rsatilmagan"}</div>
        </div>
      ),
    },
    {
      key: 'at',
      label: 'Vaqt & Davomiylik',
      render: (r) => (
        <div className="text-xs">
          <div className="font-semibold text-slate-800">{hm(r.at)}</div>
          <div className="text-slate-500">{r.duration_min ? `${r.duration_min} daqiqa` : '—'}</div>
        </div>
      ),
    },
    {
      key: 'result',
      label: 'Natija',
      render: (r, idx) => {
        const meta = getVisitMeta(r, idx);
        return <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${meta.pillCls}`}>{meta.statusText}</span>;
      },
    },
    {
      key: 'order_sum',
      label: 'Buyurtma summasi',
      numeric: true,
      render: (r) =>
        r.order_sum ? (
          <span className="font-bold text-emerald-700">{fmt(r.order_sum)} so'm</span>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      key: 'distance_m',
      label: 'Geo-Radius',
      render: (r) =>
        r.within_radius === false ? (
          <span className="px-2 py-0.5 rounded-md bg-red-100 text-red-700 text-xs font-bold flex items-center gap-1 w-fit">
            <AlertTriangle className="size-3" /> {r.distance_m ?? 0}m
          </span>
        ) : (
          <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-xs font-medium flex items-center gap-1 w-fit">
            <Check className="size-3" /> Ichida
          </span>
        ),
    },
    {
      key: 'actions',
      label: 'Foto / Izoh',
      render: (r) => (
        <div className="flex items-center gap-2">
          {r.has_photo && (
            <button
              onClick={() => setPhoto(`/field-staff/visits/${r.id}/photo`)}
              className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-semibold flex items-center gap-1"
            >
              <Eye className="size-3.5" /> Rasm
            </button>
          )}
          {r.note && (
            <span title={r.note} className="text-slate-400 hover:text-slate-600 cursor-pointer text-xs">
              💬
            </span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 size-4 text-slate-400" />
          <input
            type="text"
            placeholder="Agent yoki do'kon nomi..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div className="text-xs text-slate-500 font-medium">Jami tashriflar: {filtered.length} ta</div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
        <DataTable columns={columns} rows={filtered} emptyText={loading ? 'Yuklanmoqda...' : 'Tashriflar topilmadi'} />
      </div>

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
    </div>
  );
}

/* =========================================================================
   TAB 3: SAVDO NUQTALARI VA MIJOZLAR (OUTLETS & CRM)
   ========================================================================= */
function OutletsTab() {
  const [customers, setCustomers] = useState([]);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [assignAgent, setAssignAgent] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [cRes, uRes] = await Promise.all([
        api.get('/customers', { params: { limit: 100 } }),
        api.get('/field-staff/users'),
      ]);
      setCustomers(cRes.data?.items || cRes.data || []);
      setAgents(uRes.data?.agents || []);
    } catch {
      toast.error("Ma'lumotlarni yuklab bo'lmadi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filtered = useMemo(() => {
    return customers.filter(
      (c) =>
        c.name?.toLowerCase().includes(q.toLowerCase()) ||
        c.phone?.includes(q) ||
        c.address?.toLowerCase().includes(q.toLowerCase())
    );
  }, [customers, q]);

  const columns = [
    {
      key: 'name',
      label: 'Savdo nuqtasi / Mijoz',
      render: (r) => (
        <div>
          <div className="font-bold text-slate-900">{r.name}</div>
          <div className="text-xs text-slate-500">{r.address || 'Manzil belgilanmagan'}</div>
        </div>
      ),
    },
    {
      key: 'phone',
      label: 'Telefon',
      render: (r) => <span className="text-xs font-semibold text-slate-700">{r.phone || '—'}</span>,
    },
    {
      key: 'balance',
      label: 'Qarzdorlik / Balans',
      numeric: true,
      render: (r) => {
        const bal = r.balance ?? 0;
        return (
          <span className={`text-xs font-bold ${bal > 0 ? 'text-red-600' : 'text-slate-700'}`}>
            {bal > 0 ? `${fmt(bal)} so'm qarz` : "0 so'm"}
          </span>
        );
      },
    },
    {
      key: 'coordinates',
      label: 'GPS Lokatsiya',
      render: (r) =>
        r.lat != null && r.lng != null ? (
          <span className="text-xs text-emerald-700 font-semibold flex items-center gap-1">
            <MapPin className="size-3.5" /> Aniq
          </span>
        ) : (
          <span className="text-xs text-slate-400">Koordinata yo'q</span>
        ),
    },
    {
      key: 'actions',
      label: 'Amal',
      render: (r) => (
        <Link
          to={`/admin/customers/${r.id}`}
          className="text-xs text-blue-600 hover:text-blue-800 font-bold flex items-center gap-1"
        >
          Tafsilot <ChevronRight className="size-3.5" />
        </Link>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 size-4 text-slate-400" />
          <input
            type="text"
            placeholder="Do'kon yoki telefon raqam..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
        </div>

        <div className="flex items-center gap-2">
          {agents.length > 0 && (
            <button
              onClick={() => setAssignAgent(agents[0])}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
            >
              <Users className="size-4" /> Agentga biriktirish
            </button>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
        <DataTable columns={columns} rows={filtered} emptyText={loading ? 'Yuklanmoqda...' : 'Mijozlar topilmadi'} />
      </div>

      {assignAgent && (
        <AssignCustomersModal
          agent={assignAgent}
          onClose={() => setAssignAgent(null)}
          onSuccess={() => {
            setAssignAgent(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}

/* =========================================================================
   TAB 4: DALA XODIMLARI VA QURILMALAR (STAFF & DEVICES)
   ========================================================================= */
function StaffTab() {
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assignAgent, setAssignAgent] = useState(null);

  const loadStaff = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/field-staff/users');
      setStaff(data?.staff || []);
    } catch {
      toast.error("Xodimlarni yuklab bo'lmadi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStaff();
  }, [loadStaff]);

  const revokeDevice = async (device_id) => {
    if (!window.confirm('Haqiqatan ham ushbu qurilmani ajratmoqchimisiz?')) return;
    try {
      await api.post(`/field-staff/devices/${device_id}/revoke`);
      toast.success('Qurilma ajratildi');
      loadStaff();
    } catch {
      toast.error('Xatolik yuz berdi');
    }
  };

  const columns = [
    {
      key: 'name',
      label: 'Xodim',
      render: (r) => (
        <div>
          <div className="font-bold text-slate-900">{r.name}</div>
          <div className="text-xs text-slate-500">{r.phone || '—'}</div>
        </div>
      ),
    },
    {
      key: 'role',
      label: 'Lavozim',
      render: (r) => (
        <span
          className={`px-2.5 py-1 rounded-full text-xs font-bold ${
            r.role === 'agent' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
          }`}
        >
          {r.role === 'agent' ? 'Savdo Agenti' : 'Kurier'}
        </span>
      ),
    },
    {
      key: 'device_model',
      label: 'Qurilma modeli',
      render: (r) => (
        <div className="text-xs text-slate-800 font-medium">
          {r.device_model ? (
            <span className="flex items-center gap-1.5">
              <Smartphone className="size-3.5 text-slate-500" /> {r.device_model}
            </span>
          ) : (
            <span className="text-slate-400">Bog'lanmagan</span>
          )}
        </div>
      ),
    },
    {
      key: 'device_id',
      label: 'Qurilma ID / Status',
      render: (r) => (
        <div className="text-xs">
          {r.device_id ? (
            <span className="font-mono text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
              {r.device_id.slice(0, 12)}...
            </span>
          ) : (
            <span className="text-amber-600 font-medium">Kutilmoqda</span>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      label: 'Amallar',
      render: (r) => (
        <div className="flex items-center gap-2">
          {r.role === 'agent' && (
            <button
              onClick={() => setAssignAgent(r)}
              className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1"
            >
              <Store className="size-3.5" /> Do'konlar
            </button>
          )}
          {r.device_id && (
            <button
              onClick={() => revokeDevice(r.device_id)}
              className="px-2.5 py-1 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold flex items-center gap-1"
            >
              <ShieldOff className="size-3.5" /> Qurilmani uzish
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-slate-900 text-base">Ulangan agentlar va ularning mobil qurilmalari</h3>
        <Link
          to="/admin/employees/create"
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
        >
          <UserPlus className="size-4" /> Yangi xodim qo'shish
        </Link>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
        <DataTable columns={columns} rows={staff} emptyText={loading ? 'Yuklanmoqda...' : 'Xodimlar topilmadi'} />
      </div>

      {assignAgent && (
        <AssignCustomersModal
          agent={assignAgent}
          onClose={() => setAssignAgent(null)}
          onSuccess={() => {
            setAssignAgent(null);
            loadStaff();
          }}
        />
      )}
    </div>
  );
}

/* =========================================================================
   TAB 5: KPI, REJA VA BALANS (PERFORMANCE & MARKETPLACE PAYOUTS)
   ========================================================================= */
function KPITab() {
  const [report, setReport] = useState(null);
  const [mpAgents, setMpAgents] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [rRes, mpRes] = await Promise.all([
        api.get('/field-staff/report'),
        api.get('/marketplace-agents').catch(() => ({ data: { items: [] } })),
      ]);
      setReport(rRes.data);
      setMpAgents(mpRes.data?.items || []);
    } catch {
      toast.error("Hisobotlarni yuklab bo'lmadi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      {/* Agentlar KPI reytingi */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
            <Award className="size-5 text-amber-500" /> Savdo agentlari samaradorligi
          </h3>
          <span className="text-xs text-slate-500 font-medium">Oxirgi 7 kunlik natijalar</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(report?.agents || []).map((ag, i) => (
            <div key={ag.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 text-sm">
                  #{i + 1} {ag.name}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
                  {ag.visits_count || 0} tashrif
                </span>
              </div>
              <div className="space-y-1.5 text-xs text-slate-600">
                <div className="flex justify-between">
                  <span>Bosib o'tilgan masofa:</span>
                  <span className="font-bold text-slate-900">{ag.total_distance_km || 0} km</span>
                </div>
                <div className="flex justify-between">
                  <span>Olingan buyurtmalar:</span>
                  <span className="font-bold text-emerald-700">{fmt(ag.orders_sum || 0)} so'm</span>
                </div>
              </div>
            </div>
          ))}
          {(!report?.agents || report.agents.length === 0) && (
            <div className="col-span-3 py-8 text-center text-xs text-slate-400">Agentlar hisoboti mavjud emas</div>
          )}
        </div>
      </div>

      {/* Marketplace Agentlari balansi va komissiyasi */}
      {mpAgents.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
              <DollarSign className="size-5 text-emerald-600" /> Marketplace agentlari balansi va komissiya
            </h3>
            <Link to="/admin/marketplace-agents" className="text-xs text-blue-600 font-bold hover:underline">
              Barcha agentlar →
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {mpAgents.slice(0, 6).map((m) => (
              <div key={m.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 space-y-2">
                <div className="font-bold text-slate-900 text-sm">{m.name}</div>
                <div className="text-xs text-slate-500">{m.phone}</div>
                <div className="pt-2 border-t border-slate-200/60 flex justify-between items-center">
                  <span className="text-xs text-slate-600">Balans:</span>
                  <span className="font-bold text-emerald-700 text-sm">{fmt(m.balance || 0)} so'm</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* =========================================================================
   ASOSIY SFA MODUL KOMPONENTI (MASTER SFA PAGE)
   ========================================================================= */
export default function SFA() {
  const { t } = useLang();
  const [tab, setTab] = useState('live'); // live, visits, outlets, staff, kpi
  const [day, setDay] = useState(today());
  const [liveStaff, setLiveStaff] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadLive = useCallback(async () => {
    setRefreshing(true);
    try {
      const { data } = await api.get('/field-staff/live');
      setLiveStaff(data || []);
    } catch {
      setLiveStaff([]);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadLive();
    const timer = setInterval(loadLive, 30000);
    return () => clearInterval(timer);
  }, [loadLive]);

  // Yuqori metrikalar hisobi
  const topMetrics = useMemo(() => {
    const onShift = liveStaff.filter((s) => s.on_shift).length;
    const totalStaff = liveStaff.length;
    const todayVisits = liveStaff.reduce((sum, s) => sum + (s.today_visits || 0), 0);
    const todayDelivered = liveStaff.reduce((sum, s) => sum + (s.today_delivered || 0), 0);

    return {
      onShift,
      totalStaff,
      todayVisits,
      todayDelivered,
    };
  }, [liveStaff]);

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      {/* 1. Sarlavha va Amal Tugmalari */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl md:text-2xl font-black text-slate-900 tracking-tight">SFA & Dala Savdosi Markazi</h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs font-bold">Avtomatlashtirish</span>
          </div>
          <p className="text-xs md:text-sm text-slate-500 mt-1">
            Agentlar jonli GPS monitoringi, marshrutlar, do'konlarga tashriflar va savdo rejalari
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={loadLive}
            disabled={refreshing}
            className="px-3.5 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-all"
          >
            <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
            {refreshing ? 'Yangilanmoqda...' : 'Yangilash'}
          </button>

          <Link
            to="/admin/distributors"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-all"
          >
            <Store className="size-4" /> Distribyutorlar
          </Link>
        </div>
      </div>

      {/* 2. Yuqori 4 ta KPI Kartasi (Design System standarti) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {/* Karta 1: Faol agentlar */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Faol agentlar</span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <div className="text-2xl font-black text-slate-900 tabular-nums">
            {topMetrics.onShift} <span className="text-xs font-normal text-slate-400">/ {topMetrics.totalStaff} smenada</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
            <Users className="size-3 text-blue-600" /> Barcha dala xodimlari
          </div>
        </div>

        {/* Karta 2: Bugungi tashriflar */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Bugungi tashriflar</span>
            <CheckSquare className="size-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-black text-emerald-700 tabular-nums">{topMetrics.todayVisits} ta</div>
          <div className="text-[11px] text-slate-500 mt-1">Savdo nuqtalariga vizitlar</div>
        </div>

        {/* Karta 3: Yetkazib berishlar */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Yetkazilgan buyurtmalar</span>
            <Truck className="size-4 text-blue-600" />
          </div>
          <div className="text-2xl font-black text-blue-700 tabular-nums">{topMetrics.todayDelivered} ta</div>
          <div className="text-[11px] text-slate-500 mt-1">Kurierlar tomonidan</div>
        </div>

        {/* Karta 4: GPS nazorat holati */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">GPS Geo-nazorat</span>
            <Navigation className="size-4 text-indigo-600" />
          </div>
          <div className="text-2xl font-black text-indigo-700">Faol</div>
          <div className="text-[11px] text-slate-500 mt-1">Radius va treklar yozilmoqda</div>
        </div>
      </div>

      {/* 3. 5-Tabli Navigatsiya Paneli */}
      <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-2xl w-fit flex-wrap border border-slate-200/60">
        {[
          ['live', 'Jonli Xarita & Trek', Navigation],
          ['visits', 'Tashriflar Jurnali', CheckSquare],
          ['outlets', 'Savdo Nuqtalari', Store],
          ['staff', 'Xodimlar & Qurilmalar', Smartphone],
          ['kpi', 'KPI & Reja', BarChart3],
        ].map(([key, label, Icon]) => {
          const isActive = tab === key;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all ${
                isActive
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              <Icon className={`size-4 ${isActive ? 'text-blue-600' : 'text-slate-500'}`} />
              {label}
            </button>
          );
        })}
      </div>

      {/* 4. Tab Kontentlari */}
      <div className="mt-4">
        {tab === 'live' && (
          <LiveTab
            liveStaff={liveStaff}
            selectedAgent={selectedAgent}
            setSelectedAgent={setSelectedAgent}
            day={day}
            setDay={setDay}
          />
        )}
        {tab === 'visits' && <VisitsTab day={day} />}
        {tab === 'outlets' && <OutletsTab />}
        {tab === 'staff' && <StaffTab />}
        {tab === 'kpi' && <KPITab />}
      </div>
    </div>
  );
}
