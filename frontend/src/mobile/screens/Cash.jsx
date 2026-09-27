import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowDownLeft, ArrowUpRight, Wallet, Clock, RefreshCw } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import api, { errText } from '../lib/api';
import { enqueue } from '../offline/outbox';
import { Btn, Card, Page } from '../ui';
import { fmtMoney, inputCls } from '../format';

export default function Cash() {
  const { t } = useLang();
  const { refreshProfile } = useMobileAuth();
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ wallet_id: '', amount: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get('/mobile/cash').then(({ data: d }) => {
    setData(d);
    setForm(f => ({ ...f, wallet_id: f.wallet_id || String(d.wallets[0]?.id || '') }));
  }).catch(e => toast.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);

  const handover = async () => {
    const amount = Number(form.amount);
    if (!form.wallet_id || !amount) return;
    if (amount > data.balance) { toast.error(t('m.handoverTooMuch')); return; }
    if (!window.confirm(t('m.confirmHandover', { amount: fmtMoney(amount) }))) return;
    setBusy(true);
    await enqueue({ url: '/mobile/cash/handover', body: { wallet_id: Number(form.wallet_id), amount }, label: `${t('m.handover')}: ${fmtMoney(amount)}` });
    setForm(f => ({ ...f, amount: '' }));
    toast.success(t('m.handoverSent'));
    setTimeout(() => { load(); refreshProfile().catch(() => {}); setBusy(false); }, 1500);
  };

  return (
    <Page title={t('m.tabCash')} right={<button onClick={load} className="p-2 -m-2 text-brand"><RefreshCw className="size-5" /></button>}>
      {!data ? <div className="py-16 text-center text-ink-300">…</div> : (
        <div className="space-y-3">
          <Card className="!bg-warning text-white border-warning">
            <div className="flex items-center gap-2 text-sm opacity-90"><Wallet className="size-4" />{t('m.cashOnHand')}</div>
            <div className="text-3xl font-bold tabular-nums mt-1">{fmtMoney(data.balance)} <span className="text-base font-medium">so'm</span></div>
          </Card>

          {data.pending_handovers.length > 0 && (
            <Card className="space-y-1">
              {data.pending_handovers.map(h => (
                <div key={h.id} className="flex items-center gap-2 text-sm text-ink-500">
                  <Clock className="size-4 text-warning" />
                  {t('m.awaitingAccept', { amount: fmtMoney(h.amount), wallet: h.receiver })}
                </div>
              ))}
            </Card>
          )}

          {data.balance > 0 && (
            <Card className="space-y-2">
              <div className="font-semibold text-ink-900">{t('m.handover')}</div>
              <select value={form.wallet_id} onChange={e => setForm(f => ({ ...f, wallet_id: e.target.value }))} className={inputCls}>
                {data.wallets.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
              <div className="flex gap-2">
                <input type="number" inputMode="numeric" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  placeholder={t('m.amount')} className={inputCls} />
                <button onClick={() => setForm(f => ({ ...f, amount: String(data.balance) }))} className="px-3 rounded-xl border border-line text-sm font-semibold text-brand shrink-0">{t('m.all')}</button>
              </div>
              <Btn loading={busy} onClick={handover} disabled={!form.amount} className="w-full">{t('m.handoverBtn')}</Btn>
              <p className="text-xs text-ink-500">{t('m.handoverHint')}</p>
            </Card>
          )}

          <div className="pt-1 text-xs font-bold uppercase tracking-wider text-ink-300">{t('m.recentMoves')}</div>
          {data.movements.length === 0 && <div className="text-sm text-ink-300 text-center py-6">{t('m.noMoves')}</div>}
          {data.movements.map(m => (
            <div key={m.id} className="flex items-center gap-3 bg-surface border border-line rounded-xl px-3 py-2.5">
              {m.direction === 'in'
                ? <ArrowDownLeft className="size-5 text-success shrink-0" />
                : <ArrowUpRight className="size-5 text-danger shrink-0" />}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-ink-900 truncate">{m.description}</div>
                <div className="text-xs text-ink-300">{m.created_at ? new Date(m.created_at).toLocaleString('uz-UZ', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : ''}</div>
              </div>
              <div className={`text-sm font-bold tabular-nums ${m.direction === 'in' ? 'text-success' : 'text-danger'}`}>
                {m.direction === 'in' ? '+' : '−'}{fmtMoney(m.amount)}
              </div>
            </div>
          ))}
        </div>
      )}
    </Page>
  );
}
