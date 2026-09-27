import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { X, Search, Minus, Plus, ShoppingCart } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { enqueue } from '../offline/outbox';
import { Btn } from '../ui';
import { fmtMoney } from '../format';
import { loadCatalog, priceFor } from './data';

/** Mijoz uchun buyurtma: katalog (oflayn keshdan ham), miqdor, izoh */
export default function OrderEditor({ customer, onClose, onDone }) {
  const { t } = useLang();
  const [catalog, setCatalog] = useState(null);
  const [q, setQ] = useState('');
  const [cart, setCart] = useState({}); // product_id -> qty
  const [note, setNote] = useState('');
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { loadCatalog().then(r => setCatalog(r.data || [])); }, []);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const items = catalog || [];
    return s ? items.filter(p => p.name.toLowerCase().includes(s) || p.sku?.toLowerCase().includes(s) || p.barcode?.includes(s)) : items;
  }, [catalog, q]);

  const byId = useMemo(() => Object.fromEntries((catalog || []).map(p => [p.id, p])), [catalog]);
  const lines = Object.entries(cart).filter(([, qty]) => qty > 0).map(([id, qty]) => {
    const p = byId[id];
    return { p, qty, price: priceFor(p, customer), sum: priceFor(p, customer) * qty };
  }).filter(l => l.p);
  const total = lines.reduce((a, l) => a + l.sum, 0);

  const setQty = (id, qty) => setCart(c => ({ ...c, [id]: Math.max(0, Math.round(qty * 1000) / 1000) }));

  const submit = async () => {
    setBusy(true);
    await enqueue({
      url: '/mobile/agent/orders',
      body: { customer_id: customer.id, items: lines.map(l => ({ product_id: l.p.id, quantity: l.qty })), note: note || null },
      label: `${t('m.order')}: ${customer.name} — ${fmtMoney(total)}`,
    });
    setBusy(false);
    toast.success(t('m.orderQueued'));
    onDone?.({ total, lines: lines.length });
  };

  return (
    <div className="fixed inset-0 z-50 bg-bg-base flex flex-col" style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
      <div className="shrink-0 flex items-center gap-3 px-4 h-14 bg-surface border-b border-line">
        <button onClick={review ? () => setReview(false) : onClose} className="p-2 -m-2 text-ink-500"><X className="size-6" /></button>
        <div className="min-w-0">
          <div className="font-bold text-ink-900 truncate">{review ? t('m.reviewOrder') : t('m.newOrder')}</div>
          <div className="text-xs text-ink-500 truncate">{customer.name} · {t(`customer.priceType${customer.price_type === 'wholesale' ? 'Wholesale' : customer.price_type === 'cost' ? 'Cost' : 'Retail'}`)}</div>
        </div>
      </div>

      {!review ? (
        <>
          <div className="shrink-0 p-3">
            <div className="flex items-center gap-2 px-3 min-h-12 rounded-xl border border-line bg-surface">
              <Search className="size-5 text-ink-300" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('m.searchProduct')} className="flex-1 bg-transparent outline-none text-[15px]" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-2">
            {catalog === null && <div className="py-10 text-center text-ink-300">…</div>}
            {list.map(p => {
              const qty = cart[p.id] || 0;
              const price = priceFor(p, customer);
              return (
                <div key={p.id} className={`flex items-center gap-3 bg-surface border rounded-xl p-3 ${qty ? 'border-brand' : 'border-line'}`}>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-ink-900 text-sm">{p.name}</div>
                    <div className="text-xs text-ink-500 tabular-nums">{fmtMoney(price)} so'm · {t('m.stock')}: {p.stock} {p.unit}</div>
                  </div>
                  {qty === 0 ? (
                    <button onClick={() => setQty(p.id, 1)} className="w-11 h-11 rounded-xl bg-brand text-white flex items-center justify-center"><Plus className="size-5" /></button>
                  ) : (
                    <div className="flex items-center gap-1">
                      <button onClick={() => setQty(p.id, qty - 1)} className="w-10 h-10 rounded-xl border border-line flex items-center justify-center"><Minus className="size-4" /></button>
                      <input type="number" inputMode="decimal" value={qty} onChange={e => setQty(p.id, Number(e.target.value) || 0)}
                        className="w-16 h-10 text-center rounded-xl border border-line tabular-nums font-semibold" />
                      <button onClick={() => setQty(p.id, qty + 1)} className="w-10 h-10 rounded-xl border border-line flex items-center justify-center"><Plus className="size-4" /></button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="shrink-0 p-3 bg-surface border-t border-line">
            <Btn disabled={lines.length === 0} onClick={() => setReview(true)} className="w-full">
              <ShoppingCart className="size-5" />{lines.length} · {fmtMoney(total)} so'm
            </Btn>
          </div>
        </>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <div className="bg-surface border border-line rounded-2xl divide-y divide-line">
              {lines.map(l => (
                <div key={l.p.id} className="flex justify-between gap-3 px-4 py-3 text-sm">
                  <span className="text-ink-900">{l.p.name} <span className="text-ink-500">× {l.qty}</span></span>
                  <span className="tabular-nums font-semibold shrink-0">{fmtMoney(l.sum)}</span>
                </div>
              ))}
              <div className="flex justify-between px-4 py-3 font-bold"><span>{t('m.total')}</span><span className="tabular-nums">{fmtMoney(total)} so'm</span></div>
            </div>
            {customer.customer_type === 'distributor' && customer.debt_limit > 0 && customer.debt + total > customer.debt_limit && (
              <div className="text-sm text-warning bg-warning/10 rounded-xl px-4 py-3">{t('m.limitWarning', { limit: fmtMoney(customer.debt_limit) })}</div>
            )}
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder={t('m.orderNote')}
              className="w-full px-4 py-3 rounded-xl border border-line bg-surface text-[15px] outline-none" />
            <p className="text-xs text-ink-500 px-1">{t('m.orderHint')}</p>
          </div>
          <div className="shrink-0 p-3 bg-surface border-t border-line">
            <Btn loading={busy} onClick={submit} className="w-full">{t('m.sendOrder')}</Btn>
          </div>
        </>
      )}
    </div>
  );
}
