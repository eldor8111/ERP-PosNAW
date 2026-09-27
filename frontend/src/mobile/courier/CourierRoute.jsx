import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Phone, Navigation, MapPin, PackageCheck, Truck, RefreshCw, ChevronRight } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import api, { errText } from '../lib/api';
import { navigateUrl } from '../lib/geo';
import { kvGet, kvSet } from '../offline/db';
import { enqueue } from '../offline/outbox';
import { ShiftCard } from '../screens/Profile';
import { Btn, Card, Empty, Page } from '../ui';
import { fmtMoney } from '../format';
import StopSheet from './StopSheet';

const STATUS_CLS = {
  assigned: 'bg-brand/10 text-brand', on_way: 'bg-warning/10 text-warning',
  delivered: 'bg-success/10 text-success', cancelled: 'bg-danger/10 text-danger',
};
const CACHE = 'courier_today';

export function StopCard({ stop, index, onOpen }) {
  const { t } = useLang();
  const done = ['delivered', 'cancelled'].includes(stop.status);
  return (
    <Card className={`!p-0 overflow-hidden ${done ? 'opacity-60' : ''}`}>
      <button onClick={() => onOpen(stop)} className="w-full text-left p-4 flex gap-3">
        {index != null && (
          <div className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-sm font-bold ${done ? 'bg-success/10 text-success' : 'bg-brand text-white'}`}>
            {done ? '✓' : index + 1}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink-900 truncate">{stop.customer_name}</span>
            <span className={`shrink-0 text-[11px] font-bold px-2 py-0.5 rounded-full ${STATUS_CLS[stop.status] || 'bg-surface-sunken text-ink-500'}`}>
              {t(`logistics.orderStatus.${stop.status}`)}
            </span>
          </div>
          <div className="text-sm text-ink-500 mt-0.5 flex items-start gap-1">
            <MapPin className="size-3.5 mt-0.5 shrink-0" /><span className="line-clamp-2">{stop.address || t('logistics.noAddress')}</span>
          </div>
          <div className="mt-1.5 flex items-center justify-between">
            <span className="text-xs text-ink-300">{stop.source === 'sale' ? `🧾 #${stop.sale_number}` : '🛍 Telegram'}</span>
            <span className={`text-sm font-bold tabular-nums ${stop.collect_amount > 0 ? 'text-ink-900' : 'text-ink-300'}`}>
              {stop.collect_amount > 0 ? `${fmtMoney(stop.collect_amount)} so'm` : t('m.noCash')}
            </span>
          </div>
        </div>
        <ChevronRight className="size-5 text-ink-300 self-center shrink-0" />
      </button>
      {!done && (
        <div className="grid grid-cols-2 border-t border-line">
          <a href={stop.phone ? `tel:${stop.phone}` : undefined}
            className={`flex items-center justify-center gap-1.5 h-11 text-sm font-semibold ${stop.phone ? 'text-brand' : 'text-ink-300 pointer-events-none'}`}>
            <Phone className="size-4" />{t('m.call')}
          </a>
          <a href={stop.lat != null ? navigateUrl(stop.lat, stop.lng) : undefined} target="_blank" rel="noreferrer"
            className={`flex items-center justify-center gap-1.5 h-11 text-sm font-semibold border-l border-line ${stop.lat != null ? 'text-brand' : 'text-ink-300 pointer-events-none'}`}>
            <Navigation className="size-4" />{t('m.navigate')}
          </a>
        </div>
      )}
    </Card>
  );
}

export default function CourierRoute() {
  const { t } = useLang();
  const { user, refreshProfile } = useMobileAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(null);
  const [starting, setStarting] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get('/mobile/courier/today');
      setData(d); await kvSet(CACHE, d);
    } catch (e) {
      const cached = await kvGet(CACHE);
      if (cached) { setData(cached.value); toast(t('m.showingCached')); }
      else toast.error(errText(e));
    } finally { setLoading(false); }
  }, [t]);
  useEffect(() => { load(); }, [load]);

  // Oflayn ham ishlashi uchun: holat darhol ekranda o'zgaradi, so'rov navbatga tushadi
  const applyLocal = async (key, status) => {
    const patch = (s) => s.group_key === key ? { ...s, status } : s;
    const next = {
      ...data,
      routes: data.routes.map(r => {
        const stops = r.stops.map(patch);
        return { ...r, stops, stops_delivered: stops.filter(s => s.status === 'delivered').length };
      }),
      loose: data.loose.map(patch),
    };
    setData(next); await kvSet(CACHE, next);
  };

  const act = async (stop, action, extra = {}) => {
    const target = { on_way: 'on_way', delivered: 'delivered', failed: 'cancelled' }[action];
    await enqueue({
      url: `/mobile/courier/stops/${encodeURIComponent(stop.group_key)}/status`,
      body: { action, ...extra },
      label: `${t(`m.action.${action}`)}: ${stop.customer_name}`,
    });
    await applyLocal(stop.group_key, target);
    setOpen(null);
    if (action === 'delivered') { toast.success(t('m.markedDelivered')); setTimeout(() => refreshProfile().catch(() => {}), 2500); }
  };

  const startRoute = async (route) => {
    setStarting(route.id);
    try {
      await api.post(`/mobile/courier/routes/${route.id}/start`);
      await load();
    } catch (e) { toast.error(errText(e)); }
    finally { setStarting(null); }
  };

  const routes = data?.routes || [];
  const loose = data?.loose || [];
  const empty = data && routes.length === 0 && loose.length === 0;

  return (
    <Page title={t('m.tabRoute')}
      right={<button onClick={load} className="p-2 -m-2 text-brand"><RefreshCw className={`size-5 ${loading ? 'animate-spin' : ''}`} /></button>}>
      <div className="space-y-3">
        {!user.shift && <ShiftCard />}
        {!data && <div className="py-16 text-center text-ink-300">…</div>}
        {empty && <Empty icon={PackageCheck} title={t('m.noDeliveries')} text={t('m.noDeliveriesHint')} />}

        {routes.map(route => {
          const left = route.stops.filter(s => !['delivered', 'cancelled'].includes(s.status));
          const toCollect = left.reduce((a, s) => a + (s.collect_amount || 0), 0);
          return (
            <div key={route.id} className="space-y-2">
              <Card className="!bg-brand text-white border-brand">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs opacity-80">{route.number} · {route.route_date}</div>
                    <div className="text-lg font-bold">{route.stops_delivered}/{route.stops_total} {t('logistics.delivered')}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs opacity-80">{t('logistics.toCollect')}</div>
                    <div className="text-lg font-bold tabular-nums">{fmtMoney(toCollect)}</div>
                  </div>
                </div>
                {route.vehicle_plate && <div className="text-xs opacity-80 mt-1">🚚 {route.vehicle_plate}</div>}
                {route.status === 'planned' && (
                  <Btn variant="ghost" loading={starting === route.id} onClick={() => startRoute(route)} className="w-full mt-3 !text-brand">
                    <Truck className="size-5" />{t('m.startRoute')}
                  </Btn>
                )}
              </Card>
              {route.stops.map((s, i) => <StopCard key={s.group_key} stop={s} index={i} onOpen={setOpen} />)}
            </div>
          );
        })}

        {loose.length > 0 && (
          <>
            <div className="pt-2 text-xs font-bold uppercase tracking-wider text-ink-300">{t('m.otherDeliveries')}</div>
            {loose.map(s => <StopCard key={s.group_key} stop={s} onOpen={setOpen} />)}
          </>
        )}
      </div>

      {open && <StopSheet stop={open} onClose={() => setOpen(null)} onAction={act} />}
    </Page>
  );
}
