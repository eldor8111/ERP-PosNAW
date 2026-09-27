import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { X, Phone, Navigation, ShoppingCart, HandCoins, LogIn, LogOut, MapPin } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import api from '../lib/api';
import { distanceM, fmtDistance, getPosition, navigateUrl } from '../lib/geo';
import { enqueue } from '../offline/outbox';
import { Btn } from '../ui';
import { fmtMoney, inputCls } from '../format';
import { clearActiveVisit, getActiveVisit, setActiveVisit } from './data';
import OrderEditor from './OrderEditor';

const RESULTS = ['no_order', 'closed'];

export default function CustomerSheet({ customer, onClose, onChanged }) {
  const { t } = useLang();
  const { refreshProfile } = useMobileAuth();
  const [visit, setVisit] = useState(undefined); // undefined — yuklanmoqda
  const [detail, setDetail] = useState(null);
  const [mode, setMode] = useState(null); // null | order | pay | finish
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const c = detail || customer;

  useEffect(() => {
    getActiveVisit().then(v => setVisit(v || null));
    api.get(`/mobile/agent/customers/${customer.id}`).then(r => setDetail(r.data)).catch(() => {});
  }, [customer.id]);

  const here = visit?.customer_id === customer.id;
  const otherActive = visit && !here;

  const start = async () => {
    setBusy(true);
    const pos = await getPosition({ timeout: 10000 });
    const v = { customer_id: customer.id, customer_name: customer.name, started_at: new Date().toISOString(), lat: pos?.lat ?? null, lng: pos?.lng ?? null, did: [] };
    await setActiveVisit(v);
    setVisit(v);
    setBusy(false);
    const d = distanceM(pos, c);
    if (d != null && d > (c.visit_radius_m || 150)) toast(t('m.farFromStore', { distance: fmtDistance(d) }), { icon: '⚠️' });
  };

  const markDid = async (what) => {
    if (!here) return;
    const v = { ...visit, did: [...new Set([...(visit.did || []), what])] };
    await setActiveVisit(v); setVisit(v);
  };

  const finish = async (result) => {
    setBusy(true);
    await enqueue({
      url: '/mobile/agent/visits',
      body: { customer_id: visit.customer_id, lat: visit.lat, lng: visit.lng, check_in_at: visit.started_at, check_out_at: new Date().toISOString(), result },
      label: `${t('m.visit')}: ${visit.customer_name}`,
    });
    await clearActiveVisit();
    setVisit(null); setMode(null); setBusy(false);
    toast.success(t('m.visitSaved'));
    onChanged?.();
  };

  const pay = async () => {
    const a = Number(amount);
    if (!a) return;
    if (a > c.debt + 0.01) { toast.error(t('m.payMoreThanDebt')); return; }
    setBusy(true);
    await enqueue({ url: '/mobile/agent/payments', body: { customer_id: customer.id, amount: a }, label: `${t('m.payment')}: ${customer.name} — ${fmtMoney(a)}` });
    await markDid('payment');
    setAmount(''); setMode(null); setBusy(false);
    toast.success(t('m.paymentQueued'));
    setTimeout(() => refreshProfile().catch(() => {}), 2000);
    onChanged?.();
  };

  if (mode === 'order') {
    return <OrderEditor customer={c} onClose={() => setMode(null)} onDone={async () => { await markDid('order'); setMode(null); onChanged?.(); }} />;
  }

  const lastResult = visit?.did?.includes('order') ? 'order' : visit?.did?.includes('payment') ? 'payment' : null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/40" onClick={onClose}>
      <div className="bg-bg-base rounded-t-3xl max-h-[90%] flex flex-col" onClick={e => e.stopPropagation()} style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
          <div className="min-w-0">
            <div className="text-lg font-bold text-ink-900">{c.name}</div>
            <div className="text-sm text-ink-500 flex items-start gap-1"><MapPin className="size-3.5 mt-0.5 shrink-0" />{c.address || t('logistics.noAddress')}</div>
          </div>
          <button onClick={onClose} className="p-2 -m-2 text-ink-300"><X className="size-6" /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <a href={c.phone ? `tel:${c.phone}` : undefined} className={`min-h-12 rounded-xl border border-line bg-surface flex items-center justify-center gap-2 font-semibold ${c.phone ? 'text-brand' : 'text-ink-300'}`}><Phone className="size-4" />{t('m.call')}</a>
            <a href={c.lat != null ? navigateUrl(c.lat, c.lng) : undefined} target="_blank" rel="noreferrer" className={`min-h-12 rounded-xl border border-line bg-surface flex items-center justify-center gap-2 font-semibold ${c.lat != null ? 'text-brand' : 'text-ink-300'}`}><Navigation className="size-4" />{t('m.navigate')}</a>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="bg-surface border border-line rounded-2xl px-4 py-3">
              <div className="text-xs text-ink-500">{t('m.debt')}</div>
              <div className={`text-lg font-bold tabular-nums ${c.debt > 0 ? 'text-danger' : 'text-ink-900'}`}>{fmtMoney(c.debt)}</div>
            </div>
            <div className="bg-surface border border-line rounded-2xl px-4 py-3">
              <div className="text-xs text-ink-500">{t('customer.creditLimit')}</div>
              <div className="text-lg font-bold tabular-nums text-ink-900">{c.debt_limit > 0 ? fmtMoney(c.debt_limit) : '—'}</div>
            </div>
          </div>

          {detail?.recent_sales?.length > 0 && (
            <div className="bg-surface border border-line rounded-2xl divide-y divide-line">
              {detail.recent_sales.slice(0, 5).map(s => (
                <div key={s.id} className="flex justify-between px-4 py-2.5 text-sm">
                  <span className="text-ink-500">{s.created_at ? new Date(s.created_at).toLocaleDateString('uz-UZ') : ''} · #{s.number}</span>
                  <span className="tabular-nums font-semibold">{fmtMoney(s.total)}</span>
                </div>
              ))}
            </div>
          )}

          {mode === 'pay' && (
            <div className="bg-surface border border-line rounded-2xl p-4 space-y-2">
              <div className="font-semibold text-ink-900">{t('m.acceptPayment')}</div>
              <div className="flex gap-2">
                <input type="number" inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} placeholder={t('m.amount')} className={inputCls} autoFocus />
                <button onClick={() => setAmount(String(c.debt))} className="px-3 rounded-xl border border-line text-sm font-semibold text-brand shrink-0">{t('m.all')}</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Btn variant="ghost" onClick={() => setMode(null)}>{t('common.cancel')}</Btn>
                <Btn variant="success" loading={busy} onClick={pay}>{t('m.cashReceived')}</Btn>
              </div>
            </div>
          )}

          {mode === 'finish' && (
            <div className="bg-surface border border-line rounded-2xl p-4 space-y-2">
              <div className="font-semibold text-ink-900">{t('m.visitResult')}</div>
              {lastResult ? (
                <Btn className="w-full" loading={busy} onClick={() => finish(lastResult)}>{t('m.finishVisit')}</Btn>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {RESULTS.map(r => <Btn key={r} variant="ghost" loading={busy} onClick={() => finish(r)}>{t(`m.result.${r}`)}</Btn>)}
                </div>
              )}
            </div>
          )}

          {otherActive && <div className="text-sm text-warning bg-warning/10 rounded-xl px-4 py-3">{t('m.otherVisitActive', { name: visit.customer_name })}</div>}
          {here && <div className="text-sm text-success bg-success/10 rounded-xl px-4 py-3">{t('m.visitInProgress', { time: new Date(visit.started_at).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) })}</div>}
        </div>

        {visit !== undefined && mode === null && (
          <div className="px-5 pt-3 pb-4 space-y-2">
            {!here && !otherActive && <Btn variant="success" loading={busy} onClick={start} className="w-full"><LogIn className="size-5" />{t('m.startVisit')}</Btn>}
            <div className="grid grid-cols-2 gap-2">
              <Btn onClick={() => setMode('order')}><ShoppingCart className="size-5" />{t('m.order')}</Btn>
              <Btn variant="ghost" disabled={!(c.debt > 0)} onClick={() => setMode('pay')}><HandCoins className="size-5" />{t('m.payment')}</Btn>
            </div>
            {here && <Btn variant="ghost" onClick={() => setMode('finish')} className="w-full"><LogOut className="size-5" />{t('m.endVisit')}</Btn>}
          </div>
        )}
      </div>
    </div>
  );
}
