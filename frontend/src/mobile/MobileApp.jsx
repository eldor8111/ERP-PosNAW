import { lazy, Suspense, useEffect, useState } from 'react';
import { Route as RouteIcon, User, Wifi, WifiOff, CloudUpload, CalendarCheck, ShoppingCart, Users, Download, Wallet } from 'lucide-react';
import { useLang } from '../context/LangContext';
import { useMobileAuth } from './lib/authContext';
import { startAutoFlush } from './offline/outbox';
import { startTracking, stopTracking } from './lib/tracker';
import { initPush } from './lib/push';
import useSyncState from './lib/useOnline';
import Login from './screens/Login';
import Profile from './screens/Profile';
import Cash from './screens/Cash';
import { Empty } from './ui';

const CourierRoute = lazy(() => import('./courier/CourierRoute'));
const AgentPlan = lazy(() => import('./agent/AgentPlan'));
const AgentOrders = lazy(() => import('./agent/AgentOrders'));
const AgentCustomers = lazy(() => import('./agent/AgentCustomers'));

// Rol bo'yicha pastki navigatsiya
const TABS = {
  courier: [
    { id: 'route', icon: RouteIcon, label: 'm.tabRoute', el: CourierRoute },
    { id: 'cash', icon: Wallet, label: 'm.tabCash', el: Cash },
    { id: 'profile', icon: User, label: 'm.profile', el: Profile },
  ],
  agent: [
    { id: 'plan', icon: CalendarCheck, label: 'm.tabPlan', el: AgentPlan },
    { id: 'orders', icon: ShoppingCart, label: 'm.tabOrders', el: AgentOrders },
    { id: 'customers', icon: Users, label: 'm.tabCustomers', el: AgentCustomers },
    { id: 'cash', icon: Wallet, label: 'm.tabCash', el: Cash },
    { id: 'profile', icon: User, label: 'm.profile', el: Profile },
  ],
};

function StatusBar() {
  const { t } = useLang();
  const { user } = useMobileAuth();
  const { online, pending, failed } = useSyncState();
  return (
    <div className="shrink-0 flex items-center justify-between gap-2 px-4 h-11 bg-surface border-b border-line"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      <div className="text-sm font-semibold text-ink-900 truncate">{user.company_name}</div>
      <div className="flex items-center gap-2 text-xs font-semibold">
        {(pending > 0 || failed > 0) && (
          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full ${failed ? 'bg-danger/10 text-danger' : 'bg-warning/10 text-warning'}`}>
            <CloudUpload className="size-3.5" />{pending + failed}
          </span>
        )}
        {online
          ? <span className="flex items-center gap-1 text-success"><Wifi className="size-3.5" />{t('m.online')}</span>
          : <span className="flex items-center gap-1 text-ink-300"><WifiOff className="size-3.5" />{t('m.offline')}</span>}
      </div>
    </div>
  );
}

function Workspace() {
  const { t } = useLang();
  const { user } = useMobileAuth();
  const tabs = TABS[user.role] || [];
  const [active, setActive] = useState(tabs[0]?.id);
  useEffect(() => { startAutoFlush(); initPush(); }, []);

  // GPS faqat ochiq smenada — smena yopilsa yoki chiqilsa kuzatuv to'xtaydi
  const onShift = !!user.shift;
  useEffect(() => {
    if (onShift) startTracking({ title: t('m.trackingTitle'), message: t('m.trackingMessage') }).catch(() => {});
    else stopTracking();
    return () => { stopTracking(); };
  }, [onShift]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user.features?.distribution) {
    return <Empty title={t('m.moduleOff')} text={t('m.moduleOffHint')} />;
  }
  const Current = tabs.find(x => x.id === active)?.el || Profile;

  return (
    <div className="flex flex-col h-full">
      <StatusBar />
      <main className="flex-1 min-h-0">
        <Suspense fallback={<div className="p-10 text-center text-ink-300">…</div>}>
          <Current onNavigate={setActive} />
        </Suspense>
      </main>
      <nav className="shrink-0 grid bg-surface border-t border-line" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)`, paddingBottom: 'env(safe-area-inset-bottom)' }}>
        {tabs.map(tab => {
          const on = tab.id === active;
          return (
            <button key={tab.id} onClick={() => setActive(tab.id)}
              className={`flex flex-col items-center justify-center gap-0.5 h-16 text-[11px] font-semibold ${on ? 'text-brand' : 'text-ink-300'}`}>
              <tab.icon className="size-6" />{t(tab.label)}
            </button>
          );
        })}
      </nav>
    </div>
  );
}

export default function MobileApp() {
  const { t } = useLang();
  const { status } = useMobileAuth();
  if (status === 'loading') {
    return <div className="h-full flex items-center justify-center"><div className="w-9 h-9 border-4 border-brand border-t-transparent rounded-full animate-spin" /></div>;
  }
  if (status === 'update_required') {
    return <Empty icon={Download} title={t('m.updateRequired')} text={t('m.updateHint')} />;
  }
  if (status === 'guest') return <Login />;
  return <Workspace />;
}
