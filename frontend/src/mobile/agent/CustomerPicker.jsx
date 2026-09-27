import { useEffect, useMemo, useState } from 'react';
import { X, Search, UserX } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { Empty } from '../ui';
import { fmtMoney } from '../format';
import { loadCustomers } from './data';

/** Buyurtma uchun mijoz tanlash (faqat agentga biriktirilganlar, oflayn keshdan ham) */
export default function CustomerPicker({ onPick, onClose }) {
  const { t } = useLang();
  const [customers, setCustomers] = useState(null);
  const [q, setQ] = useState('');

  useEffect(() => { loadCustomers().then(r => setCustomers(r.data || [])); }, []);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const all = customers || [];
    return s ? all.filter(c => c.name.toLowerCase().includes(s) || c.phone?.includes(s) || c.address?.toLowerCase().includes(s)) : all;
  }, [customers, q]);

  return (
    <div className="fixed inset-0 z-50 bg-bg-base flex flex-col" style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
      <div className="shrink-0 flex items-center gap-3 px-4 h-14 bg-surface border-b border-line">
        <button onClick={onClose} className="p-2 -m-2 text-ink-500"><X className="size-6" /></button>
        <div className="font-bold text-ink-900">{t('m.pickCustomer')}</div>
      </div>
      <div className="shrink-0 p-3">
        <div className="flex items-center gap-2 px-3 min-h-12 rounded-xl border border-line bg-surface">
          <Search className="size-5 text-ink-300" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('m.searchCustomer')} autoFocus className="flex-1 bg-transparent outline-none text-[15px]" />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-2">
        {customers === null && <div className="py-10 text-center text-ink-300">…</div>}
        {customers && customers.length === 0 && <Empty icon={UserX} title={t('m.noAssignedCustomers')} text={t('m.noAssignedCustomersHint')} />}
        {list.map(c => (
          <button key={c.id} onClick={() => onPick(c)} className="w-full text-left bg-surface border border-line rounded-xl px-4 py-3 active:bg-surface-sunken">
            <div className="flex justify-between gap-2">
              <span className="font-semibold text-ink-900 truncate">{c.name}</span>
              {c.debt > 0 && <span className="text-sm font-bold text-danger tabular-nums shrink-0">{fmtMoney(c.debt)}</span>}
            </div>
            <div className="text-sm text-ink-500 truncate">{c.address || c.phone || '—'}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
