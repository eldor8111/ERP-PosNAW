import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CalendarCheck, CheckCircle2, MapPin, CircleDot, XCircle, Clock } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import { distanceM, fmtDistance, getPosition } from '../lib/geo';
import { ShiftCard } from '../screens/Profile';
import { Card, Empty, Page } from '../ui';
import { fmtMoney } from '../format';
import { getActiveVisit, loadPlan } from './data';
import CustomerSheet from './CustomerSheet';

const STATUS_STYLE = {
  visited:   { icon: CheckCircle2, color: 'text-success',  bg: 'opacity-70' },
  cancelled: { icon: XCircle,      color: 'text-danger',   bg: 'opacity-50 line-through' },
  planned:   { icon: Clock,        color: 'text-brand',    bg: '' },
};

export default function AgentPlan() {
  const { t } = useLang();
  const { user } = useMobileAuth();
  const [plan, setPlan] = useState(null);
  const [offline, setOffline] = useState(false);
  const [pos, setPos] = useState(null);
  const [active, setActive] = useState(null);
  const [open, setOpen] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchAll = () => Promise.all([loadPlan(), getPosition({ timeout: 8000 }), getActiveVisit()]);
  const apply = ([r, p, v]) => { setPlan(r.data); setOffline(r.offline); setPos(p); setActive(v); };
  const load = useCallback(async () => {
    setLoading(true);
    apply(await fetchAll());
    setLoading(false);
  }, []);
  useEffect(() => { fetchAll().then(apply); }, []);

  const items = (plan?.planned || [])
    .map(c => ({ ...c, dist: distanceM(pos, c) }))
    .sort((a, b) => {
      // cancelled eng pastda, visited o'rtada, planned yuqorida
      const order = { planned: 0, visited: 1, cancelled: 2 };
      const ao = order[a.visit_status] ?? 0;
      const bo = order[b.visit_status] ?? 0;
      return ao - bo || ((a.dist ?? 1e9) - (b.dist ?? 1e9));
    });
  const done = items.filter(c => c.visit_status === 'visited').length;
  const total = items.filter(c => c.visit_status !== 'cancelled').length;
  const unplanned = plan?.unplanned_visits || [];

  return (
    <Page title={t('m.tabPlan')}
      right={<button onClick={load} className="p-2 -m-2 text-brand"><RefreshCw className={`size-5 ${loading ? 'animate-spin' : ''}`} /></button>}>
      <div className="space-y-3">
        {!user.shift && <ShiftCard />}

        {active && (
          <Card className="border-success/40 bg-success/5" onClick={() => setOpen({ id: active.customer_id, name: active.customer_name, ...(items.find(i => i.id === active.customer_id) || {}) })}>
            <div className="flex items-center gap-2 text-success font-semibold"><CircleDot className="size-4 animate-pulse" />{t('m.activeVisit')}</div>
            <div className="text-ink-900 font-semibold mt-0.5">{active.customer_name}</div>
          </Card>
        )}

        {plan && (
          <Card className="flex items-center justify-between">
            <div>
              <div className="text-xs text-ink-500">{plan.date ? `📅 ${plan.date}` : t('m.todayPlan')}</div>
              <div className="text-xl font-bold text-ink-900">{done} / {total}</div>
            </div>
            <div className="w-24 h-2 rounded-full bg-surface-sunken overflow-hidden">
              <div className="h-full bg-success" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
            </div>
          </Card>
        )}
        {offline && <div className="text-xs text-ink-500 text-center">{t('m.showingCached')}</div>}
        {plan && items.length === 0 && <Empty icon={CalendarCheck} title={t('m.noPlan')} text={t('m.noPlanHint')} />}

        {items.map(c => {
          const st = STATUS_STYLE[c.visit_status] || STATUS_STYLE.planned;
          const Icon = c.visit_status === 'visited' ? st.icon : (c.visit_status === 'cancelled' ? st.icon : null);
          return (
            <Card key={c.id} onClick={() => c.visit_status !== 'cancelled' && setOpen(c)} className={`active:bg-surface-sunken ${st.bg}`}>
              <div className="flex items-start gap-3">
                {Icon
                  ? <Icon className={`size-6 shrink-0 ${st.color}`} />
                  : <div className="w-6 h-6 rounded-full border-2 border-line shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between gap-2">
                    <span className={`font-semibold truncate ${c.visit_status === 'cancelled' ? 'text-ink-400' : 'text-ink-900'}`}>{c.name}</span>
                    {c.dist != null && <span className="text-xs font-semibold text-ink-500 shrink-0">{fmtDistance(c.dist)}</span>}
                  </div>
                  <div className="text-sm text-ink-500 truncate flex items-center gap-1"><MapPin className="size-3.5 shrink-0" />{c.address || t('logistics.noAddress')}</div>
                  <div className="flex justify-between mt-1 text-xs">
                    <span className={c.debt > 0 ? 'text-danger font-semibold' : 'text-ink-300'}>{t('m.debt')}: {fmtMoney(c.debt)}</span>
                    {c.visit?.result && <span className="text-success font-semibold">{t(`m.result.${c.visit.result}`)}</span>}
                    {c.visit_status === 'cancelled' && <span className="text-danger text-xs">{t('m.cancelled') || 'Bekor qilingan'}</span>}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}

        {/* Rejalanmagan tashriflar */}
        {unplanned.length > 0 && (
          <>
            <div className="text-xs font-semibold text-ink-400 uppercase tracking-wider mt-4 px-1">{t('m.unplannedVisits') || 'Rejalanmagan tashriflar'}</div>
            {unplanned.map(v => (
              <Card key={v.id} className="opacity-80 border-dashed">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="size-5 text-ink-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <span className="font-semibold text-ink-700 truncate">{v.customer_name}</span>
                    {v.result && <span className="ml-2 text-xs text-success">{t(`m.result.${v.result}`)}</span>}
                  </div>
                </div>
              </Card>
            ))}
          </>
        )}
      </div>
      {open && <CustomerSheet customer={open} onClose={() => { setOpen(null); getActiveVisit().then(setActive); }} onChanged={load} />}
    </Page>
  );
}
