import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { Search, UserPlus, X, LocateFixed, MapPin } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { getPosition } from '../lib/geo';
import { enqueue } from '../offline/outbox';
import { Btn, Card, Empty, Page } from '../ui';
import { fmtMoney, inputCls } from '../format';
import { loadCustomers } from './data';
import CustomerSheet from './CustomerSheet';

function NewCustomer({ onClose, onSaved }) {
  const { t } = useLang();
  const [f, setF] = useState({ name: '', phone: '', address: '', work_days: [] });
  const [pos, setPos] = useState(null);
  const [locating, setLocating] = useState(true);
  const [busy, setBusy] = useState(false);

  const locate = async () => { setLocating(true); setPos(await getPosition({ timeout: 12000 })); setLocating(false); };
  useEffect(() => {
    getPosition({ timeout: 12000 }).then(p => { setPos(p); setLocating(false); });
  }, []);

  const save = async () => {
    if (f.name.trim().length < 2) return;
    setBusy(true);
    const digits = f.phone.replace(/\D/g, '');
    await enqueue({
      url: '/mobile/agent/customers',
      body: {
        name: f.name.trim(), phone: digits ? (digits.length === 9 ? `998${digits}` : digits) : null,
        address: f.address || null, work_days: f.work_days, ...(pos ? { lat: pos.lat, lng: pos.lng } : {}),
      },
      label: `${t('m.newCustomer')}: ${f.name.trim()}`,
    });
    setBusy(false);
    toast.success(t('m.customerQueued'));
    onSaved();
  };

  return (
    <div className="fixed inset-0 z-50 bg-bg-base flex flex-col" style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
      <div className="shrink-0 flex items-center gap-3 px-4 h-14 bg-surface border-b border-line">
        <button onClick={onClose} className="p-2 -m-2 text-ink-500"><X className="size-6" /></button>
        <div className="font-bold text-ink-900">{t('m.newCustomer')}</div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder={t('m.storeName')} className={inputCls} />
        <div className="flex items-center rounded-xl border border-line bg-surface">
          <span className="pl-4 pr-2 text-ink-500">+998</span>
          <input value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} inputMode="tel" placeholder="90 123 45 67" className="flex-1 min-h-12 pr-4 bg-transparent outline-none text-[15px]" />
        </div>
        <input value={f.address} onChange={e => setF({ ...f, address: e.target.value })} placeholder={t('customerProfile.addressPlaceholder')} className={inputCls} />
        <Card className="flex items-center justify-between gap-3">
          <div className="text-sm">
            <div className="font-semibold text-ink-900 flex items-center gap-1"><MapPin className="size-4" />{t('m.storeLocation')}</div>
            <div className="text-ink-500">{pos ? `${pos.lat.toFixed(5)}, ${pos.lng.toFixed(5)} (±${Math.round(pos.accuracy)} m)` : t('m.noGps')}</div>
          </div>
          <button onClick={locate} className="p-2 text-brand shrink-0"><LocateFixed className={`size-6 ${locating ? 'animate-pulse' : ''}`} /></button>
        </Card>
        <p className="text-xs text-ink-500 -mt-1 px-1">{t('m.storeLocationHint')}</p>
        <div>
          <div className="text-sm font-semibold text-ink-900 mb-2">{t('customerProfile.workDays')}</div>
          <div className="grid grid-cols-7 gap-1.5">
            {[1, 2, 3, 4, 5, 6, 7].map(d => {
              const on = f.work_days.includes(d);
              return (
                <button key={d} onClick={() => setF({ ...f, work_days: on ? f.work_days.filter(x => x !== d) : [...f.work_days, d] })}
                  className={`h-11 rounded-xl text-xs font-bold border ${on ? 'bg-brand text-white border-brand' : 'bg-surface border-line text-ink-500'}`}>
                  {t(`weekday.short${d}`)}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="shrink-0 p-3 bg-surface border-t border-line">
        <Btn loading={busy} disabled={f.name.trim().length < 2} onClick={save} className="w-full">{t('common.save')}</Btn>
      </div>
    </div>
  );
}

export default function AgentCustomers() {
  const { t } = useLang();
  const [customers, setCustomers] = useState(null);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => loadCustomers().then(r => setCustomers(r.data || [])), []);
  useEffect(() => { loadCustomers().then(r => setCustomers(r.data || [])); }, []);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const all = customers || [];
    return s ? all.filter(c => c.name.toLowerCase().includes(s) || c.phone?.includes(s) || c.address?.toLowerCase().includes(s)) : all;
  }, [customers, q]);

  return (
    <Page title={t('m.tabCustomers')}
      right={<button onClick={() => setAdding(true)} className="p-2 -m-2 text-brand"><UserPlus className="size-6" /></button>}>
      <div className="space-y-2">
        <div className="flex items-center gap-2 px-3 min-h-12 rounded-xl border border-line bg-surface sticky top-0 z-10">
          <Search className="size-5 text-ink-300" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('m.searchCustomer')} className="flex-1 bg-transparent outline-none text-[15px]" />
        </div>
        {customers && list.length === 0 && <Empty title={t('m.noCustomers')} text={t('m.noCustomersHint')} />}
        {list.map(c => (
          <Card key={c.id} onClick={() => setOpen(c)} className="!py-3 active:bg-surface-sunken">
            <div className="flex justify-between gap-2">
              <span className="font-semibold text-ink-900 truncate">{c.name}</span>
              {c.debt > 0 && <span className="text-sm font-bold text-danger tabular-nums shrink-0">{fmtMoney(c.debt)}</span>}
            </div>
            <div className="text-sm text-ink-500 truncate">{c.address || c.phone || '—'}</div>
          </Card>
        ))}
      </div>
      {open && <CustomerSheet customer={open} onClose={() => setOpen(null)} onChanged={load} />}
      {adding && <NewCustomer onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTimeout(load, 1500); }} />}
    </Page>
  );
}
