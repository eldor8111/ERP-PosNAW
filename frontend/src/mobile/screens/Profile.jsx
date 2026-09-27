import { useState } from 'react';
import toast from 'react-hot-toast';
import { LogOut, Wallet, RefreshCw, Trash2, RotateCcw, CloudOff, Play, Square } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import api, { errText } from '../lib/api';
import { getPosition } from '../lib/geo';
import { APP_VERSION } from '../lib/device';
import { flush, removeItem, retryItem } from '../offline/outbox';
import useSyncState from '../lib/useOnline';
import { Btn, Card, Page } from '../ui';
import { fmtMoney } from '../format';

export function ShiftCard() {
  const { t } = useLang();
  const { user, refreshProfile } = useMobileAuth();
  const [busy, setBusy] = useState(false);
  const shift = user?.shift;

  const toggle = async () => {
    setBusy(true);
    try {
      const pos = await getPosition({ timeout: 8000 });
      await api.post(shift ? '/mobile/shift/end' : '/mobile/shift/start', pos ? { lat: pos.lat, lng: pos.lng } : {});
      await refreshProfile();
      toast.success(shift ? t('m.shiftEnded') : t('m.shiftStarted'));
    } catch (e) { toast.error(errText(e)); }
    finally { setBusy(false); }
  };

  return (
    <Card className={shift ? 'border-success/40 bg-success/5' : ''}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-ink-900">{shift ? t('m.shiftOpen') : t('m.shiftClosed')}</div>
          <div className="text-xs text-ink-500 mt-0.5">
            {shift ? `${t('m.since')} ${new Date(shift.started_at).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })} · ${t('m.gpsOn')}` : t('m.shiftHint')}
          </div>
        </div>
        <Btn variant={shift ? 'ghost' : 'success'} loading={busy} onClick={toggle} className="shrink-0">
          {shift ? <Square className="size-4" /> : <Play className="size-4" />}
          {shift ? t('m.endShift') : t('m.startShift')}
        </Btn>
      </div>
    </Card>
  );
}

export default function Profile() {
  const { t, lang, setLang, LANGUAGES } = useLang();
  const { user, logout, refreshProfile } = useMobileAuth();
  const { items, pending } = useSyncState();
  const [syncing, setSyncing] = useState(false);

  const sync = async () => {
    setSyncing(true);
    try { await flush(); await refreshProfile(); } catch { /* oflayn */ }
    setSyncing(false);
  };

  const doLogout = async () => {
    if (pending > 0 && !window.confirm(t('m.logoutUnsynced', { count: pending }))) return;
    if (!pending && !window.confirm(t('m.confirmLogout'))) return;
    await logout();
  };

  return (
    <Page title={t('m.profile')}>
      <div className="space-y-3">
        <Card>
          <div className="text-lg font-bold text-ink-900">{user.name}</div>
          <div className="text-sm text-ink-500">{t(`role.${user.role}`)} · {user.company_name}</div>
          <div className="text-sm text-ink-300 mt-0.5">{user.phone}</div>
        </Card>

        <ShiftCard />

        <Card className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-warning/10 text-warning flex items-center justify-center"><Wallet className="size-5" /></div>
          <div className="flex-1">
            <div className="text-xs text-ink-500">{t('m.cashOnHand')}</div>
            <div className="text-xl font-bold tabular-nums text-ink-900">{fmtMoney(user.wallet?.balance)} <span className="text-sm font-medium text-ink-500">so'm</span></div>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <div className="font-semibold text-ink-900">{t('m.sync')}</div>
            <button onClick={sync} className="p-2 -m-2 text-brand"><RefreshCw className={`size-5 ${syncing ? 'animate-spin' : ''}`} /></button>
          </div>
          {items.length === 0 ? (
            <div className="text-sm text-ink-500 mt-1">{t('m.allSynced')}</div>
          ) : (
            <div className="mt-2 space-y-2">
              {items.map(it => (
                <div key={it.id} className={`flex items-center gap-2 text-sm rounded-xl px-3 py-2 ${it.state === 'failed' ? 'bg-danger/10' : 'bg-surface-sunken'}`}>
                  <CloudOff className={`size-4 shrink-0 ${it.state === 'failed' ? 'text-danger' : 'text-ink-300'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-ink-900">{it.label || it.url}</div>
                    {it.error && <div className="text-xs text-danger">{it.error}</div>}
                  </div>
                  {it.state === 'failed' && <button onClick={() => retryItem(it.id)} className="p-1 text-brand"><RotateCcw className="size-4" /></button>}
                  {it.state === 'failed' && <button onClick={() => window.confirm(t('m.confirmDiscard')) && removeItem(it.id)} className="p-1 text-danger"><Trash2 className="size-4" /></button>}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="font-semibold text-ink-900 mb-2">{t('m.language')}</div>
          <div className="grid grid-cols-3 gap-2">
            {LANGUAGES.map(l => (
              <button key={l.code} onClick={() => setLang(l.code)}
                className={`min-h-11 rounded-xl text-sm font-semibold border ${lang === l.code ? 'bg-brand text-white border-brand' : 'border-line text-ink-500'}`}>
                {l.label}
              </button>
            ))}
          </div>
        </Card>

        <Btn variant="ghost" onClick={doLogout} className="w-full text-danger"><LogOut className="size-4" />{t('m.logout')}</Btn>
        <div className="text-center text-xs text-ink-300">E-code Mobile v{APP_VERSION}</div>
      </div>
    </Page>
  );
}
