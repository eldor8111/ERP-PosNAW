import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CloudOff, ShoppingCart } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import api from '../lib/api';
import useSyncState from '../lib/useOnline';
import { kvGet, kvSet } from '../offline/db';
import { Card, Empty, Page } from '../ui';
import { fmtMoney } from '../format';

const STATUS_CLS = {
  pending: 'bg-warning/10 text-warning', completed: 'bg-success/10 text-success',
  cancelled: 'bg-danger/10 text-danger', refunded: 'bg-danger/10 text-danger', partial_refund: 'bg-warning/10 text-warning',
};

export default function AgentOrders() {
  const { t } = useLang();
  const { items } = useSyncState();
  const [orders, setOrders] = useState(null);
  const [kpi, setKpi] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, k] = await Promise.all([api.get('/mobile/agent/orders'), api.get('/mobile/agent/kpi')]);
      setOrders(o.data); setKpi(k.data);
      await kvSet('agent_orders', { orders: o.data, kpi: k.data });
    } catch {
      const c = await kvGet('agent_orders');
      setOrders(c?.value?.orders || []); setKpi(c?.value?.kpi || null);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const queued = items.filter(i => i.url === '/mobile/agent/orders');

  return (
    <Page title={t('m.tabOrders')}
      right={<button onClick={load} className="p-2 -m-2 text-brand"><RefreshCw className={`size-5 ${loading ? 'animate-spin' : ''}`} /></button>}>
      <div className="space-y-3">
        {kpi && (
          <div className="grid grid-cols-2 gap-2">
            <Card className="!p-3">
              <div className="text-xs text-ink-500">{t('m.kpiToday')}</div>
              <div className="text-lg font-bold tabular-nums text-ink-900">{fmtMoney(kpi.today.orders.sum)}</div>
              <div className="text-xs text-ink-500">{kpi.today.orders.count} {t('m.ordersShort')} · {t('m.visitsShort')} {kpi.today.visits_done}/{kpi.today.visits_planned}</div>
            </Card>
            <Card className="!p-3">
              <div className="text-xs text-ink-500">{t('m.kpiMonth')}</div>
              <div className="text-lg font-bold tabular-nums text-ink-900">{fmtMoney(kpi.month.orders.sum)}</div>
              <div className="text-xs text-ink-500">{t('m.collected')}: {fmtMoney(kpi.month.collected)}</div>
            </Card>
          </div>
        )}

        {queued.map(q => (
          <Card key={q.id} className={`!py-3 ${q.state === 'failed' ? 'border-danger/40' : 'border-dashed'}`}>
            <div className="flex items-center gap-2 text-sm">
              <CloudOff className={`size-4 ${q.state === 'failed' ? 'text-danger' : 'text-warning'}`} />
              <span className="flex-1 truncate text-ink-900">{q.label}</span>
            </div>
            <div className={`text-xs mt-0.5 ${q.state === 'failed' ? 'text-danger' : 'text-ink-500'}`}>{q.error || t('m.waitingSync')}</div>
          </Card>
        ))}

        {orders && orders.length === 0 && queued.length === 0 && <Empty icon={ShoppingCart} title={t('m.noOrders')} text={t('m.noOrdersHint')} />}
        {(orders || []).map(o => (
          <Card key={o.id} className="!py-3">
            <div className="flex justify-between gap-2">
              <span className="font-semibold text-ink-900 truncate">{o.customer_name}</span>
              <span className="font-bold tabular-nums shrink-0">{fmtMoney(o.total)}</span>
            </div>
            <div className="flex justify-between items-center mt-1 text-xs">
              <span className="text-ink-500">#{o.number} · {o.created_at ? new Date(o.created_at).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}</span>
              <span className={`px-2 py-0.5 rounded-full font-bold ${STATUS_CLS[o.status] || ''}`}>
                {t(`m.orderStatus.${o.status}`)}{o.delivery_status ? ` · 🚚 ${t(`logistics.orderStatus.${o.delivery_status}`)}` : ''}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </Page>
  );
}
