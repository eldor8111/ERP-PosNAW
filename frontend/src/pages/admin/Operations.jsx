import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import api from '../../api/axios';
import InventoryCountsPage from './InventoryCounts';
import toast from 'react-hot-toast';
import { matchesSearch } from '../../utils/translit';
import { EllipsisVertical, Pen, Undo2 } from 'lucide-react';
import BranchSelect from '../../components/BranchSelect';
import CustomerPicker from '../../components/CustomerPicker';
import useCompanyFeatures from '../../hooks/useCompanyFeatures';

/* ─── Helpers ─── */
// T1.3: ombor varianti "Ombor — Filial" ko'rinishida (bir xil nomli omborlar chalkashmasin)
const whLabel = (w) => (w.branch_name ? `${w.name} — ${w.branch_name}` : w.name);
// Kalit i18n fayllarida hali bo'lmasa — o'zbekcha zaxira matn
const tOr = (t, key, fallback) => { const v = t(key); return v === key ? fallback : v; };
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const fmtDt = (d) => d ? new Date(d).toLocaleString('uz-UZ') : '—';
const fmtDay = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);

const OptionsTable = ({ row, onEdit, onReturn, onDelete }) => {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const ref = useRef(null);
  const btnRef = useRef(null);

  useEffect(() => {
    const handleClose = (e) => {
      if (open && ref.current && !ref.current.contains(e.target) && !btnRef.current?.contains(e.target)) {
        setOpen(false);
      }
    };
    const handleScroll = () => setOpen(false);

    if (open) {
      document.addEventListener('mousedown', handleClose);
      window.addEventListener('scroll', handleScroll, true);
    }
    return () => {
      document.removeEventListener('mousedown', handleClose);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [open]);

  const toggle = (e) => {
    e.stopPropagation();
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setPos({
        top: rect.bottom + 5,
        right: window.innerWidth - rect.right
      });
    }
    setOpen(!open);
  };

  return (
    <div className="relative inline-block text-left" onClick={e => e.stopPropagation()}>
      <button
        ref={btnRef}
        onClick={toggle}
        className="flex items-center justify-center text-slate-600 p-2 bg-slate-50 hover:bg-slate-100 active:bg-slate-200 rounded-lg transition-colors cursor-pointer border border-slate-200/60"
      >
        <EllipsisVertical className="w-5 h-5" />
      </button>

      {open && (
        <div
          ref={ref}
          style={{
            position: 'fixed',
            top: pos.top,
            right: pos.right,
            zIndex: 9999
          }}
          className="w-40 bg-white border border-slate-200 rounded-xl shadow-xl p-1.5 animate-in fade-in slide-in-from-top-1 duration-100"
        >
          {/* Bekor qilingan transferni tahrirlab/qaytarib bo'lmaydi (backend 400 beradi) */}
          {row?.status !== 'cancelled' && row?.status !== 'in_transit' && (
            <button onClick={e => { e.stopPropagation(); setOpen(false); onEdit?.(row); }} className="flex cursor-pointer w-full items-center px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-md transition-colors font-medium">
              {t('common.edit')}
            </button>
          )}
          {row?.status === 'received' && (
            <button onClick={e => { e.stopPropagation(); setOpen(false); onReturn?.(row); }} className="flex cursor-pointer w-full items-center px-3 py-2 text-sm text-amber-600 hover:bg-amber-50 rounded-md transition-colors font-medium">
              {t('pos.return')}
            </button>
          )}
          {row?.status !== 'in_transit' && (
            <button onClick={e => { e.stopPropagation(); setOpen(false); onDelete?.(row); }} className="flex cursor-pointer w-full items-center px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-md transition-colors font-medium">
              {t('common.delete')}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

const trMeta = {
  // Backend statuslari: pending / in_transit / received / cancelled
  pending: { l: 'purchase.pending', c: 'bg-amber-100 text-amber-700' },
  in_transit: { l: 'ombor.statusInTransit', c: 'bg-blue-100 text-blue-700' },
  received: { l: 'ombor.statusReceived', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { l: 'common.cancel', c: 'bg-red-100 text-red-500' },
};

/* ─── UI atoms ─── */
function Badge({ meta, val }) {
  const { t } = useLang();
  const m = meta[val] || { l: val, c: 'bg-slate-100 text-slate-600' };
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${m.c}`}>{t(m.l) || m.l}</span>;
}
const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white transition-colors hover:border-slate-300';
function Btn({ v = 'primary', sm, children, ...p }) {
  const { t } = useLang();
  const cl = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm shadow-blue-200',
    green: 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm shadow-emerald-200',
    red: 'bg-red-500 hover:bg-red-600 text-white shadow-sm shadow-red-200',
    ghost: 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200',
    amber: 'bg-amber-500 hover:bg-amber-600 text-white shadow-sm shadow-amber-200',
  }[v];
  return <button className={`${sm ? 'px-3 py-1.5 text-xs' : 'px-4 py-2.5 text-sm'} rounded-xl font-semibold transition-all ${cl} disabled:opacity-50 disabled:cursor-not-allowed`} {...p}>{children}</button>;
}
function Lbl({ t, children }) {
  return <div className="flex flex-col gap-1.5"><label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{t}</label>{children}</div>;
}

/* ─── Create page header (back + title + right) ─── */
function CreateHeader({ title, onBack, right }) {
  const { t } = useLang();
  return (
    <div className="flex items-center gap-3 px-6 py-3.5 border-b border-slate-100 bg-white shrink-0 shadow-sm">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 px-3 py-2 rounded-xl hover:bg-blue-50 transition-all text-sm font-semibold">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
        </svg>
        {t('common.back')}
      </button>
      <div className="w-px h-6 bg-slate-200 shrink-0" />
      <h2 className="text-base font-bold text-slate-800 flex-1">{title}</h2>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

/* ─── Paginator ─── */
function Pager({ skip, limit, count, onChange }) {
  const { t } = useLang();
  return (
    <div className="flex items-center justify-between px-5 py-3.5 border-t border-slate-100 bg-slate-50/60 text-sm">
      <span className="text-slate-400 text-xs font-medium">
        {count === 0 ? t('ops.noResults') : `${skip + 1}–${skip + count} ${t('ops.shownCount')}`}
      </span>
      <div className="flex gap-1.5">
        <button disabled={skip === 0} onClick={() => onChange(Math.max(0, skip - limit))}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-white disabled:opacity-40 hover:border-blue-300 hover:text-blue-600 transition-all text-xs font-semibold shadow-sm">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
          {t('common.prev')}
        </button>
        <button disabled={count < limit} onClick={() => onChange(skip + limit)}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-white disabled:opacity-40 hover:border-blue-300 hover:text-blue-600 transition-all text-xs font-semibold shadow-sm">
          {t('common.next')}
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  );
}

/* ─── Data table ─── */
function Tbl({ cols, rows, onRow, loading, skip = 0, limit, onChange }) {
  const { t } = useLang();
  if (loading) return (
    <div className="py-20 text-center">
      <div className="inline-flex items-center gap-2 text-slate-400 text-sm">
        <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {t('common.loading')}
      </div>
    </div>
  );
  if (!rows.length) return (
    <div className="py-20 text-center text-slate-400">
      <svg className="w-10 h-10 mx-auto mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p className="text-sm">{t('common.noData')}</p>
    </div>
  );
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-100">
              <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-400 w-12">#</th>
              {cols.map(c => (
                <th key={c.k} className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{c.l}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {rows.map((row, i) => (
              <tr key={i} onClick={onRow ? () => onRow(row) : undefined}
                className={`transition-colors ${onRow ? 'cursor-pointer hover:bg-blue-50/70 active:bg-blue-100/50' : 'hover:bg-slate-50/80'}`}>
                <td className="px-5 py-4 text-slate-300 text-xs font-medium">{skip + i + 1}</td>
                {cols.map(c => (
                  <td key={c.k} className="px-5 py-4 text-slate-700 text-sm">
                    {c.r ? c.r(row[c.k], row) : (row[c.k] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onChange && <Pager skip={skip} limit={limit} count={rows.length} onChange={onChange} />}
    </div>
  );
}

/* ─── Product search dropdown ─── */
/* T3.3: serverdan qidiruv (debounce 300ms). warehouseId berilsa `stock_quantity` — shu ombor qoldig'i.
   Katta ro'yxatni oldindan yuklamaydi: GET /products/?search=&warehouse_id=&limit=30 */
function useServerProducts(q, warehouseId, enabled = true) {
  const { t } = useLang();
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const params = { limit: 30 };
        if (q.trim()) params.search = q.trim();
        if (warehouseId) params.warehouse_id = warehouseId;
        const r = await api.get('/products/', { params, _noCache: true });
        if (alive) setResults(Array.isArray(r.data) ? r.data : (r.data?.items || []));
      } catch (e) {
        if (alive) { setResults([]); toast.error(e.response?.data?.detail || t('ops.errorOccurred')); }
      } finally { if (alive) setLoading(false); }
    }, q.trim() ? 300 : 0);
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, warehouseId, enabled]);
  return { results, loading };
}

/* T3.3: ProdSearch ning serverdan qidiruvli varianti (transfer oynasi uchun) */
function SrvProdSearch({ warehouseId, onSelect, placeholder }) {
  const { t } = useLang();
  const ph = placeholder || t('ops.searchProductDots');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const { results, loading } = useServerProducts(q, warehouseId, open);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
        </svg>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={ph}
          className={`w-full pl-9 ${ic}`} />
        {q && (
          <button onMouseDown={() => { setQ(''); setOpen(true); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>
        )}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {loading && results.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">{t('pos.productsLoading')}</div>
          ) : results.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">{q.trim() ? `«${q.trim()}» ${t('ops.notFoundBy')}` : t('common.noData')}</div>
          ) : results.map(p => (
            <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
              className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3">
              <div className="min-w-0">
                <div className="font-medium text-slate-800 text-sm truncate">{p.name}</div>
                <div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
              </div>
              <div className="text-right shrink-0 text-xs">
                <div className={`font-semibold ${Number(p.stock_quantity) > 0 ? 'text-emerald-600' : 'text-red-500'}`}>{t('ops.available')}: {fmt(p.stock_quantity)}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ProdSearch({ products, onSelect, placeholder }) {
  const { t } = useLang();
  const ph = placeholder || t('ops.searchProductDots');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const filtered = q.trim()
    ? products.filter(p =>
      matchesSearch(p.name, q) ||
      matchesSearch(p.sku, q) ||
      p.barcode?.includes(q)
    ).slice(0, 20)
    : products.slice(0, 20);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
        </svg>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={ph}
          className={`w-full pl-9 ${ic}`} />
        {q && (
          <button onMouseDown={() => { setQ(''); setOpen(true); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>
        )}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {products.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">{t('pos.productsLoading')}</div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">«{q}» {t('ops.notFoundBy')}</div>
          ) : (
            <>
              {filtered.map(p => (
                <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
                  className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-slate-800 text-sm truncate">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
                  </div>
                  <div className="text-right shrink-0 text-xs">
                    <div className="font-semibold text-blue-600">{fmt(p.sale_price)} {t('common.sum')}</div>
                    {p.wholesale_price > 0 && <div className="text-amber-600">{t('ops.wholesaleShort')}: {fmt(p.wholesale_price)}</div>}
                    <div className="text-slate-400">{t('pos.stockLabel')} {fmt(p.stock_quantity)}</div>
                  </div>
                </button>
              ))}
              {products.length > 20 && !q.trim() && (
                <div className="px-4 py-2 text-xs text-slate-400 text-center bg-slate-50 border-t border-slate-100">
                  {t('common.total')} {products.length} {t('common.piece')} — {t('ops.findViaSearch')}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}


/* ══════════════════════════════════════════════════════════
   QAYTARISHLAR — split panel create view
══════════════════════════════════════════════════════════ */
function QaytarishCreateView({ products, type, onBack, suppliers, warehouses, editData, onEditSaved }) {
  const { t } = useLang();
  const isCustomer = type === 'customer';
  const [items, setItems] = useState([]);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [showPay, setShowPay] = useState(false);

  const [form, setForm] = useState({ supplier_id: '', customer_id: '', warehouse_id: '', received_amount: '', wallet_id: '', payment_type: 'debt', paid_cash: '', paid_card: '' });
  const [wallets, setWallets] = useState([]);

  useEffect(() => {
    api.get('/finance/wallets').then(r => setWallets(r.data)).catch(console.error);
  }, []);

  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('1');
  const [cost, setCost] = useState('');

  // CD.2: dorixona rejimida ta'minotchiga qaytarishda partiya (seriya) tanlash. Oddiy korxonada umuman ishlamaydi.
  const features = useCompanyFeatures();
  const pharmacyOn = !!features?.pharmacy;
  const showBatchPick = pharmacyOn && !isCustomer;
  const [batches, setBatches] = useState([]);
  const [batchId, setBatchId] = useState('');
  const batchWh = form.warehouse_id || (warehouses?.length === 1 ? String(warehouses[0].id) : '');
  useEffect(() => {
    setBatchId(''); setBatches([]);
    if (!showBatchPick || !sel) return;
    let cancelled = false;
    const params = { product_id: sel.id };
    if (batchWh) params.warehouse_id = batchWh;
    api.get('/pharmacy/batches', { params, _silent: true })
      .then(r => { if (!cancelled) setBatches(Array.isArray(r.data) ? r.data : []); })
      .catch(() => { if (!cancelled) setBatches([]); });
    return () => { cancelled = true; };
  }, [showBatchPick, sel, batchWh]);
  const batchStatusLabel = (st) => {
    const k = { active: ['pharmacyBatches.statusActive', 'Faol'], quarantine: ['pharmacyBatches.statusQuarantine', 'Karantin'],
      defect: ['pharmacyBatches.statusDefect', 'Brak'], recalled: ['pharmacyBatches.statusRecalled', 'Qaytarib olingan'] }[st || 'active'];
    return k ? tOr(t, k[0], k[1]) : st;
  };
  const batchText = (b) => `${b.lot_number || '—'} · ${b.expiry_date ? fmtDay(b.expiry_date) : '—'} · ${batchStatusLabel(b.status)} · ${fmt(b.quantity)}`;

  // Update cost when product is selected
  useEffect(() => {
    if (sel) {
      if (isCustomer) {
        setCost(sel.sale_price || '');
      } else {
        setCost(sel.unit_cost || '');
      }
    }
  }, [sel, isCustomer]);

  const addItem = () => {
    if (!sel || !qty) return;
    if (!cost) { setErr(t('ops.enterReturnPrice')); return; }
    // CD.2: tanlangan partiya (faqat dorixona + ta'minotchiga qaytarish)
    const pickedBatch = showBatchPick && batchId ? batches.find(b => String(b.batch_id) === String(batchId)) : null;
    const bId = pickedBatch ? pickedBatch.batch_id : null;
    if (pickedBatch && Number(qty) > Number(pickedBatch.quantity || 0)) {
      setErr(tOr(t, 'pharmaSale.batchQtyExceeded', "Miqdor partiya qoldig'idan oshib ketdi")); return;
    }

    setItems(prev => {
      const same = (i) => i.product_id === sel.id && i.cost === Number(cost) && (i.batch_id || null) === bId;
      const ex = prev.find(same);
      if (ex) return prev.map(i => same(i) ? { ...i, qty: Number(i.qty) + Number(qty) } : i);
      return [...prev, {
        product_id: sel.id, product_name: sel.name, unit: sel.unit || t('common.piece'), qty: Number(qty), cost: Number(cost), current: Number(sel.stock_quantity || 0),
        ...(bId ? { batch_id: bId, batch_label: `${pickedBatch.lot_number || '—'} · ${pickedBatch.expiry_date ? fmtDay(pickedBatch.expiry_date) : '—'}` } : {}),
      }];
    });
    setSel(null); setQty('1'); setCost(''); setErr(''); setBatchId('');
  };

  const save = async (overridePayType) => {
    const pType = typeof overridePayType === 'string' ? overridePayType : form.payment_type;
    if (!items.length) { setErr(t('ops.addProduct')); return; }
    if (isCustomer) {
      if (!form.customer_id) { setErr(t('ops.selectCustomer')); return; }
      if (!form.warehouse_id) { setErr(t('ops.selectWarehouse')); return; }
      if (pType !== 'debt' && !form.wallet_id) { setErr(t('ops.selectCashbox')); return; }
    } else {
      if (!form.supplier_id) { setErr(t('ops.selectSupplier')); return; }
      // T1.16: bir nechta ombor bo'lsa qaytarish ombori majburiy (aks holda qoldiq istalgan ombordan yechilardi)
      if (!form.warehouse_id && (warehouses?.length || 0) > 1) { setErr(t('ops.selectWarehouse')); return; }
      if (Number(form.received_amount) > 0 && !form.wallet_id) { setErr(t('ops.selectCashbox')); return; }
    }

    setSaving(true); setErr(''); setMsg('');
    try {
      if (isCustomer) {
        const totalAmount = items.reduce((s, i) => s + (i.qty * i.cost), 0);
        let paidAmount = 0;
        let paidCash = 0;
        let paidCard = 0;

        if (pType === 'cash') {
          paidAmount = totalAmount;
          paidCash = totalAmount;
        } else if (pType === 'card') {
          paidAmount = totalAmount;
          paidCard = totalAmount;
        } else if (pType === 'mixed') {
          paidCash = Number(form.paid_cash) || 0;
          paidCard = Number(form.paid_card) || 0;
          paidAmount = paidCash + paidCard;
          if (paidAmount > totalAmount) {
            setErr(t('ops.returnedAmountExceedsTotal'));
            setSaving(false);
            return;
          }
          // Qolgan summa mijoz qarzidan ayiriladi — mijozsiz yuborib bo'lmaydi
          if (paidAmount < totalAmount && !form.customer_id) {
            setErr(t('ops.selectCustomerForRemainder'));
            setSaving(false);
            return;
          }
        }

        const payload = {
          customer_id: Number(form.customer_id),
          warehouse_id: Number(form.warehouse_id),
          items: items.map(i => ({
            product_id: i.product_id,
            quantity: i.qty,
            unit_price: i.cost,
          })),
          payment_type: pType,
          paid_cash: paidCash,
          paid_card: paidCard,
          wallet_id: form.wallet_id ? Number(form.wallet_id) : null,
          note: note
        };

        const res = await api.post('/inventory/return-from-customer', payload);
        setMsg(res.data?.message || t('ops.returnedSuccessfully'));
      } else {
        const payload = {
          supplier_id: Number(form.supplier_id),
          warehouse_id: form.warehouse_id ? Number(form.warehouse_id) : (warehouses?.length === 1 ? Number(warehouses[0].id) : null),
          items: items.map(i => ({ product_id: i.product_id, quantity: i.qty, unit_cost: i.cost, ...(showBatchPick && i.batch_id ? { batch_id: i.batch_id } : {}) })),
          received_amount: form.received_amount ? Number(form.received_amount) : 0,
          wallet_id: form.wallet_id ? Number(form.wallet_id) : null,
          note: note
        };
        const res = await api.post('/inventory/return-to-supplier', payload);
        setMsg(res.data?.message || t('ops.returnedSuccessfully'));
      }

      setItems([]); setNote(''); setForm({ supplier_id: '', customer_id: '', warehouse_id: '', received_amount: '', wallet_id: '', payment_type: 'debt', paid_cash: '', paid_card: '' });
      setShowPay(false);
    } catch (e) {
      // Backend detail: satr (404/403/400 matnlari) yoki 422 ro'yxati
      const d = e.response?.data?.detail;
      setErr(typeof d === 'string' ? d : (Array.isArray(d) ? d.map(x => x?.msg).join('; ') : t('ops.errorOccurred')));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <CreateHeader title={isCustomer ? (t('ops.returnFromCustomer') || 'Mijozdan qaytarish') : (t('ops.returnToSupplier') || "Ta'minotchiga qaytarish")} onBack={onBack} />
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-slate-100 bg-white shadow-sm shrink-0">
        <input placeholder={isCustomer ? (t('ops.customerNameOpt') || "Mijoz ismi / Izoh (ixtiyoriy)") : (t('ops.noteOpt') || "Izoh (ixtiyoriy)")} value={note} onChange={e => setNote(e.target.value)} className={`${ic} w-72`} />
        <span className="text-xs text-slate-400 font-medium ml-auto">{new Date().toLocaleString('uz-UZ')}</span>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="w-[450px] border-r border-slate-100 p-5 flex flex-col gap-4 overflow-y-auto shrink-0 bg-white shadow-sm">
          {isCustomer ? (
            <>
              <Lbl t={`${t('admin.dict.customer')} *`}>
                <CustomerPicker
                  value={form.customer_id}
                  onChange={val => setForm(f => ({ ...f, customer_id: val }))}
                  placeholder={t('ops.selectCustomerDots')}
                />
              </Lbl>
              <Lbl t={`${t('admin.dict.warehouse')} *`}>
                <select value={form.warehouse_id} onChange={e => setForm({ ...form, warehouse_id: e.target.value })} className={ic}>
                  <option value="">{t('admin.dict.select')}...</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
              </Lbl>
            </>
          ) : (
            <>
              <Lbl t={`${t('purchase.supplier')} *`}>
                <select value={form.supplier_id} onChange={e => setForm({ ...form, supplier_id: e.target.value })} className={ic}>
                  <option value="">{t('admin.dict.select')}...</option>
                  {suppliers?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Lbl>
              <Lbl t={`${t('admin.dict.warehouse')} (${t('common.optional')})`}>
                <select value={form.warehouse_id} onChange={e => setForm({ ...form, warehouse_id: e.target.value })} className={ic}>
                  <option value="">{t('ops.allGlobalStock')}</option>
                  {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
              </Lbl>
            </>
          )}

          <Lbl t={t('pos.searchProduct') || "Mahsulot qidirish"}>
            <ProdSearch products={products} onSelect={p => { setSel(p); setQty('1'); }} />
          </Lbl>
          {sel ? (
            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {sel.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm">{sel.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{t('pos.stockLabel') || 'Joriy qoldiq:'} <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit || t('common.piece')}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Lbl t={t('ops.returnQty') || "Qaytarish miqdori"}>
                  <div className="flex gap-2 items-center">
                    <input type="number" min="0.001" step="any" value={qty} onChange={e => setQty(e.target.value)} className={`flex-1 ${ic} text-center font-bold`} />
                  </div>
                </Lbl>
                <Lbl t={t('ops.returnPrice')}>
                  <input type="number" min="0" step="any" value={cost} onChange={e => setCost(e.target.value)} className={`w-full ${ic}`} placeholder={`${t('admin.dict.price')}...`} />
                </Lbl>
              </div>
              {showBatchPick && (
                <Lbl t={tOr(t, 'pharmaSale.batchPick', 'Partiya (seriya / muddat / holat / qoldiq)')}>
                  <select value={batchId} onChange={e => setBatchId(e.target.value)} className={`w-full ${ic}`}>
                    <option value="">{tOr(t, 'pharmaSale.batchAuto', 'Avtomatik (muddati yaqini birinchi)')}</option>
                    {batches.map(b => <option key={b.batch_id} value={b.batch_id}>{batchText(b)}</option>)}
                  </select>
                </Lbl>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-8">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              <p className="text-sm text-center">{t('ops.searchAndSelect') || "Mahsulot qidiring va tanlang"}</p>
            </div>
          )}
          <button onClick={addItem} disabled={!sel || !qty}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-blue-200 active:scale-95">
            <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            {t('ops.addToList') || "Ro'yxatga qo'shish"}
          </button>




        </div>
        <div className="flex-1 overflow-y-auto">
          {items.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
              <p>{t('ops.addProduct') || "Mahsulot qo'shing"}</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">№</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('common.name') || 'Nomi'}</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('common.quantity') || 'Soni'}</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.price')}</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('common.total')}</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((it, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-400 text-xs">{i + 1}</td>
                    <td className="px-4 py-3 font-medium">
                      {it.product_name}
                      {it.batch_id && <div className="text-[11px] font-normal text-slate-500">{tOr(t, 'pharmaSale.batch', 'Seriya')}: {it.batch_label}</div>}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <span className="font-bold">{it.qty}</span>
                        <span className="text-slate-500 text-xs">{it.unit}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-slate-600">{fmt(it.cost)}</td>
                    <td className="px-4 py-3 text-right font-bold text-blue-700">{fmt(it.qty * it.cost)}</td>
                    <td className="pr-3">
                      <button onClick={() => setItems(p => p.filter((_, idx) => idx !== i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white shrink-0 shadow-[0_-1px_8px_rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-3">
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
          {msg && <span className="text-emerald-600 text-sm font-bold">{msg}</span>}
          {err && <span className="text-red-500 text-sm font-medium">{err}</span>}
        </div>
        <div className="flex items-center gap-3">
          {items.length > 0 && (
            <div className="text-sm text-slate-500 mr-2">
              {t('common.total')}: <span className="font-bold text-slate-800 text-base">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))} {t('common.sum')}</span>
            </div>
          )}
          <Btn v="amber" disabled={saving || !items.length} onClick={() => save('debt')}>
            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            {t('ops.closeOnDebt')}
          </Btn>
          <button disabled={saving || !items.length} onClick={() => { setErr(''); setShowPay(true); }}
            className="inline-flex items-center gap-2.5 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-blue-200 active:scale-95">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
            {t('ops.goToPayment')}
          </button>
        </div>
      {showPay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowPay(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-800">{t('ops.payFromCashbox')}</h3>
              <button onClick={() => setShowPay(false)} className="p-1.5 hover:bg-slate-100 rounded-xl text-slate-400 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 text-center">
                <div className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-1">{t('ops.returningAmount')}</div>
                <div className="text-3xl font-black text-blue-700">{fmt(items.reduce((s, i) => s + (i.qty * i.cost), 0))} <span className="text-lg font-normal text-blue-400">{t('common.sum')}</span></div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">{t('sale.paymentType')}</label>
                <select value={form.payment_type} onChange={e => setForm({ ...form, payment_type: e.target.value })} className="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 focus:outline-none transition-colors">
                  <option value="cash">{t('finance.cash')}</option>
                  <option value="card">{t('ops.plasticCard')}</option>
                  <option value="mixed">{t('pay.mixed')}</option>
                </select>
              </div>

              {form.payment_type === 'mixed' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 block">{t('finance.cash')}</label>
                    <input type="number" min="0" step="any" value={form.paid_cash} onChange={e => setForm({ ...form, paid_cash: e.target.value })} className="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 block">{t('sale.payByCard')}</label>
                    <input type="number" min="0" step="any" value={form.paid_card} onChange={e => setForm({ ...form, paid_card: e.target.value })} className="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-3 py-2 text-lg font-bold text-slate-800 focus:outline-none" />
                  </div>
                  {(() => {
                    const totalAmt = items.reduce((s, i) => s + (i.qty * i.cost), 0);
                    const paidAmt = (Number(form.paid_cash) || 0) + (Number(form.paid_card) || 0);
                    if (paidAmt >= totalAmt) return null;
                    return form.customer_id
                      ? <div className="col-span-2 text-xs text-amber-600 font-medium">{t('ops.remainderFromDebt')}: {fmt(totalAmt - paidAmt)} {t('common.sum')}</div>
                      : <div className="col-span-2 text-xs text-red-500 font-medium">{t('ops.selectCustomerForRemainder')}</div>;
                  })()}
                </div>
              )}

              {form.payment_type !== 'debt' && (
                <div>
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">{t('ops.cashboxAccount')}</label>
                  <select value={form.wallet_id} onChange={e => setForm({ ...form, wallet_id: e.target.value })} className="w-full border-2 border-slate-200 focus:border-blue-500 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 focus:outline-none transition-colors">
                    <option value="">{t('admin.dict.select')}...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name}{w.balance !== undefined ? ` (${fmt(w.balance)})` : ''}</option>)}
                  </select>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <Btn v="ghost" onClick={() => setShowPay(false)}>{t('admin.dict.cancel')}</Btn>
                <button onClick={() => save(form.payment_type)} disabled={saving} className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-blue-200 active:scale-95">
                  {saving ? t('ops.confirming') : t('common.confirm')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      </div>
    </div>
  );
}

function QaytarishlarTab({ products, suppliers, warehouses }) {
  const { t } = useLang();
  const [mode, setMode] = useState('list');
  const [sub, setSub] = useState('customer');
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(false);

  const [editReturnId, setEditReturnId] = useState(null);
  const [editReturnData, setEditReturnData] = useState(null);

  const handleEditReturn = async (returnId) => {
    try {
      const res = await api.get(`/inventory/movements/${returnId}`);
      setEditReturnData(res.data);
      setEditReturnId(returnId);
      setMode("create");
    } catch (err) {
      console.error("Failed to fetch return details:", err);
      toast.error(t('ops.errorFetchingReturnData'));
    }
  };

  const handleDeleteReturn = async (returnId) => {
    if (!window.confirm(t('ops.confirmCancelReturn'))) return;
    try {
      const delRes = await api.delete(`/inventory/movements/${returnId}`);
      // Ta'minotchi qaytaruvida butun hujjat bekor qilinadi — server nechta pozitsiya ekanini aytadi
      toast.success(delRes.data?.message || t('ops.returnCancelledStockRestored'));
      // Ro'yxatni yangilash
      setLoading(true);
      const params = { reference_type: sub === "supplier" ? "return_to_supplier" : "return_from_customer" };
      const res = await api.get("/inventory/movements", { params });
      setReturns(res.data);
    } catch (err) {
      console.error("Failed to reverse return:", err);
      toast.error(err.response?.data?.detail || t('ops.errorCancellingReturn'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (mode === 'list') {
      setLoading(true);
      api.get('/inventory/movements', { params: { reference_type: sub === 'supplier' ? 'return_to_supplier' : 'return_from_customer' } })
        .then(r => setReturns(r.data))
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [mode, sub]);

  if (mode === 'create') return (
    <QaytarishCreateView products={products} type={sub} onBack={() => setMode('list')} suppliers={suppliers} warehouses={warehouses} />
  );

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 bg-slate-100 p-1 rounded-xl">
            {[['customer', t('ops.returnFromCustomer') || 'Mijozdan qaytarish'], ['supplier', t('ops.returnToSupplier') || "Ta'minotchiga qaytarish"]].map(([v, l]) => (
              <button key={v} onClick={() => setSub(v)}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${sub === v ? 'bg-white shadow text-blue-700' : 'text-slate-500 hover:text-slate-700'}`}>{l}</button>
            ))}
          </div>
          <div className="ml-auto">
            <Btn onClick={() => setMode('create')}>
              <svg className="w-4 h-4 inline mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              {t('ops.newReturn') || 'Yangi qaytaruv'}
            </Btn>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" /></div>
        ) : returns.length === 0 ? (
          <div className="py-16 text-center">
            <svg className="w-12 h-12 mx-auto mb-3 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
            </svg>
            <p className="text-slate-400 text-sm">{t('ops.noReturnedProductsFound')}</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.date')}</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.product')}</th>
                <th className="text-center px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('purchase.colQty')}</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('movements.warehouse')}</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.note')}</th>
                <th className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {returns.map((r, i) => (
                <tr key={r.id || i} className="hover:bg-slate-50">
                  <td className="px-5 py-3.5 text-slate-500">{new Date(r.created_at).toLocaleString('uz-UZ')}</td>
                  <td className="px-5 py-3.5 font-semibold">{r.product_name}</td>
                  <td className="px-5 py-3.5 text-center text-red-500 font-bold">{fmt(r.quantity)}</td>
                  <td className="px-5 py-3.5 text-slate-500 text-xs whitespace-nowrap">{r.warehouse_name || '—'}</td>
                  <td className="px-5 py-3.5 text-slate-500 text-xs">{r.reason}</td>
                  <td className="px-5 py-4 text-slate-700 text-sm">
                    <div className="flex gap-2">
                      <button onClick={() => handleEditReturn(r.id)} className="flex items-center gap-1 px-3 py-1 text-xs rounded-sm font-semibold border transition-all cursor-pointer border-blue-300 text-blue-600">
                        <Pen size={16} />
                        {t('common.edit')}
                      </button>
                      <button onClick={() => handleDeleteReturn(r.id)} className="flex items-center gap-1 px-3 py-1 text-xs rounded-sm font-semibold border transition-all cursor-pointer border-red-300 text-red-600">
                        <Undo2 size={16} />
                        {t('common.delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}


/* ══════════════════════════════════════════════════════════
   TRANSFERLAR
══════════════════════════════════════════════════════════ */
function TransferCreateView({ warehouses, allWarehouses = null, onBack, onSaved, editData = null }) {
  const { t } = useLang();
  const [step, setStep] = useState(1);

  const [form, setForm] = useState(editData ? {
    from_warehouse_id: String(editData.from_warehouse_id),
    to_warehouse_id: String(editData.to_warehouse_id),
    note: editData.note || ''
  } : { from_warehouse_id: '', to_warehouse_id: '', note: '' });

  const [items, setItems] = useState(editData ? editData.items.map(i => ({
    product_id: i.product_id,
    variant_id: i.variant_id || null,
    product_name: i.product_name,
    unit: i.unit || t('common.piece'),
    quantity: Number(i.quantity),
    stock: Number(i.stock_quantity || 0),
    target_product_id: i.target_product_id || null,
    target_product_name: i.target_product_name || null,
  })) : []);

  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('1');
  const [selTargetProd, setSelTargetProd] = useState(null); // maqsad omborda boshqa mahsulot
  const [targetQ, setTargetQ] = useState('');
  const [targetOpen, setTargetOpen] = useState(false);
  const targetRef = useRef(null);
  const qtyRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // T3.3: mahsulotlar oldindan yuklanmaydi — manba ombor bo'yicha serverdan qidiriladi (SrvProdSearch);
  // maqsad mahsulot (mapping) qidiruvi ombor filtrisiz.
  const { results: targetResults } = useServerProducts(targetQ, '', targetOpen);

  // T1.3: manba — joriy filial konteksti; maqsad — korxonaning barcha filiallari omborlari (scope=all)
  const targetWarehouses = allWarehouses || warehouses;
  const fromWh = [...warehouses, ...targetWarehouses].find(w => String(w.id) === String(form.from_warehouse_id));
  const toWh = targetWarehouses.find(w => String(w.id) === String(form.to_warehouse_id));
  // T4.1: omborlar farqli filiallarda bo'lsa transfer ikki bosqichli (yuborildi -> yo'lda -> qabul)
  const crossBranch = !!(fromWh?.branch_id && toWh?.branch_id && fromWh.branch_id !== toWh.branch_id);



  const addItem = () => {
    if (!sel || !qty) return;
    setItems(prev => {
      const ex = prev.find(i => i.product_id === sel.id);
      if (ex) return prev.map(i => i.product_id === sel.id
        ? { ...i, quantity: Number(i.quantity) + Number(qty) }
        : i
      );
      return [...prev, {
        product_id: sel.id,
        product_name: sel.name,
        unit: sel.unit || t('common.piece'),
        quantity: Number(qty),
        stock: Number(sel.stock_quantity || 0),
        // Maqsad mahsulot mapping (ixtiyoriy)
        target_product_id: selTargetProd ? selTargetProd.id : null,
        target_product_name: selTargetProd ? selTargetProd.name : null,
      }];
    });
    setSel(null); setQty('1'); setSelTargetProd(null); setTargetQ('');
  };

  const save = async (send = true) => {
    setSaving(true); setErr('');
    try {
      const payload = {
        from_warehouse_id: Number(form.from_warehouse_id),
        to_warehouse_id: Number(form.to_warehouse_id),
        note: form.note || null,
        items: items.map(i => ({
          product_id: i.product_id,
          variant_id: i.variant_id || null,
          quantity: i.quantity,
          target_product_id: i.target_product_id || null,
        })),
      };
      if (!editData && crossBranch) payload.send = send;

      if (editData) {
        await api.put(`/transfers/${editData.id}`, payload);
        toast.success(t('ops.transferEditedSuccessfully'));
      } else {
        await api.post('/transfers', payload);
        toast.success(t('ops.transferCreatedSuccessfully'));
      }

      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); } finally { setSaving(false); }
  };

  /* ── Step indicator ── */
  const STEPS = [t('ops.warehousesPlural'), t('ops.productsUpper'), t('common.confirm')];

  return (
    <div className="fixed inset-0 z-40 bg-slate-100 flex flex-col">

      {/* ── Header ── */}
      <div className="flex items-center gap-4 px-6 py-3.5 bg-white border-b border-slate-100 shadow-sm shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 px-3 py-2 rounded-xl hover:bg-blue-50 transition-all text-sm font-semibold">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>
          {t('common.back')}
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0" />
        <h2 className="text-base font-bold text-slate-800">{editData ? `${t('ops.editTransfer')} · ${editData.number}` : t('ops.newTransfer')}</h2>

        {/* Step indicator */}
        <div className="flex items-center gap-0 ml-6">
          {STEPS.map((label, idx) => {
            const n = idx + 1;
            const done = step > n;
            const active = step === n;
            return (
              <div key={n} className="flex items-center">
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold transition-all ${active ? 'bg-blue-600 text-white shadow-md shadow-blue-200' :
                  done ? 'bg-emerald-100 text-emerald-700' :
                    'bg-slate-100 text-slate-400'
                  }`}>
                  {done
                    ? <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
                    : <span>{n}</span>
                  }
                  <span className="hidden sm:inline">{label}</span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div className={`w-8 h-0.5 mx-1 ${done ? 'bg-emerald-400' : 'bg-slate-200'}`} />
                )}
              </div>
            );
          })}
        </div>

        <div className="ml-auto text-xs text-slate-400 font-medium">{new Date().toLocaleString('uz-UZ')}</div>
      </div>

      {/* ══════════════════ STEP 1 — OMBOR TANLASH ══════════════════ */}
      {step === 1 && (
        <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-center">
          <div className="w-full max-w-2xl">
            <div className="text-center mb-8">
              <div className="w-14 h-14 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
                <svg className="w-7 h-7 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-slate-800">{t('ops.selectWarehouses')}</h3>
              <p className="text-sm text-slate-500 mt-1">{t('ops.transferDirectionQuestion')}</p>
            </div>

            <div className="flex items-center gap-4">
              {/* FROM */}
              <div className="flex-1">
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">{t('ops.sourceWarehouse')}</label>
                <div className="space-y-2">
                  {warehouses.map(w => (
                    <button key={w.id} onClick={() => setForm(f => ({ ...f, from_warehouse_id: String(w.id) }))}
                      disabled={String(form.to_warehouse_id) === String(w.id)}
                      className={`w-full text-left px-4 py-3.5 rounded-2xl border-2 transition-all flex items-center gap-3 ${String(form.from_warehouse_id) === String(w.id)
                        ? 'border-blue-500 bg-blue-50 shadow-md shadow-blue-100'
                        : 'border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/30 disabled:opacity-30 disabled:cursor-not-allowed'
                        }`}>
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 font-bold text-sm ${String(form.from_warehouse_id) === String(w.id) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500'
                        }`}>
                        {w.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">{w.name}</div>
                        {w.branch_name && <div className="text-xs text-slate-400 truncate">{w.branch_name}</div>}
                      </div>
                      {String(form.from_warehouse_id) === String(w.id) && (
                        <svg className="w-5 h-5 text-blue-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Arrow */}
              <div className="flex flex-col items-center gap-2 shrink-0">
                <div className="w-12 h-12 bg-white border-2 border-slate-200 rounded-full flex items-center justify-center shadow-sm">
                  <svg className="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                  </svg>
                </div>
                {fromWh && toWh && (
                  <div className="text-[10px] text-emerald-600 font-bold text-center bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">OK</div>
                )}
              </div>

              {/* TO */}
              <div className="flex-1">
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">{t('ops.targetWarehouse')}</label>
                <div className="space-y-2">
                  {targetWarehouses.filter(w => String(w.id) !== String(form.from_warehouse_id)).length === 0 && (
                    <div className="px-4 py-3.5 rounded-2xl border-2 border-dashed border-amber-200 bg-amber-50 text-sm text-amber-700">
                      {tOr(t, 'ops.noTargetWarehouse', "Maqsad ombor yo'q — avval boshqa ombor yarating")}
                    </div>
                  )}
                  {targetWarehouses.map(w => (
                    <button key={w.id} onClick={() => setForm(f => ({ ...f, to_warehouse_id: String(w.id) }))}
                      disabled={String(form.from_warehouse_id) === String(w.id)}
                      className={`w-full text-left px-4 py-3.5 rounded-2xl border-2 transition-all flex items-center gap-3 ${String(form.to_warehouse_id) === String(w.id)
                        ? 'border-emerald-500 bg-emerald-50 shadow-md shadow-emerald-100'
                        : 'border-slate-200 bg-white hover:border-emerald-300 hover:bg-emerald-50/30 disabled:opacity-30 disabled:cursor-not-allowed'
                        }`}>
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 font-bold text-sm ${String(form.to_warehouse_id) === String(w.id) ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-500'
                        }`}>
                        {w.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">{w.name}</div>
                        {w.branch_name && <div className="text-xs text-slate-400 truncate">{w.branch_name}</div>}
                      </div>
                      {String(form.to_warehouse_id) === String(w.id) && (
                        <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Note */}
            <div className="mt-6">
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">{t('ops.noteOpt')}</label>
              <input placeholder={t('ops.transferReasonPlaceholder')} value={form.note}
                onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            {/* Next btn */}
            <div className="mt-6 flex justify-end">
              <button
                disabled={!form.from_warehouse_id || !form.to_warehouse_id || form.from_warehouse_id === form.to_warehouse_id}
                onClick={() => setStep(2)}
                className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-blue-200">
                {t('ops.continue')}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════ STEP 2 — MAHSULOTLAR ══════════════════ */}
      {step === 2 && (
        <div className="flex flex-1 overflow-hidden">
          {/* LEFT — Product search panel */}
          <div className="w-[500px] border-r border-slate-200 bg-white flex flex-col gap-4 p-5 overflow-y-auto shrink-0 shadow-sm">
            {/* Route badge */}
            <div className="bg-blue-50 border border-blue-100 rounded-2xl px-4 py-3 flex items-center gap-2.5">
              <div className="text-xs font-bold text-blue-600 bg-blue-100 px-2 py-0.5 rounded-lg truncate max-w-[90px]">{fromWh?.name}</div>
              <svg className="w-4 h-4 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" /></svg>
              <div className="text-xs font-bold text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-lg truncate max-w-[90px]">{toWh?.name}</div>
            </div>

            <Lbl t={t('purchase.searchProduct')}>
              <SrvProdSearch key={form.from_warehouse_id} warehouseId={form.from_warehouse_id}
                onSelect={p => { setSel(p); setQty('1'); setTimeout(() => qtyRef.current?.focus(), 50); }} />
            </Lbl>

            {sel ? (
              <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                    {sel.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-800 text-sm truncate">{sel.name}</div>
                    <div className="text-xs mt-0.5">
                      <span className="text-slate-500">{t('ops.available')}:</span>
                      <span className={`font-bold ml-1 ${Number(sel.stock_quantity) < 5 ? 'text-red-500' : 'text-emerald-600'}`}>
                        {fmt(sel.stock_quantity)} {sel.unit || t('common.piece')}
                      </span>
                    </div>
                  </div>
                </div>

                {Number(sel.stock_quantity) <= 0 && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2 flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                    {t('ops.noStockInWarehouse')}
                  </div>
                )}

                <Lbl t={t('ops.transferQty')}>
                  <div className="flex gap-2 items-center">
                    <button onClick={() => setQty(q => String(Math.max(1, Number(q) - 1)))}
                      className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">−</button>
                    <input ref={qtyRef} type="number" min="0.001" step="any" value={qty}
                      onChange={e => setQty(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addItem()}
                      className={`flex-1 ${ic} text-center font-bold`} />
                    <button onClick={() => setQty(q => String(Number(q) + 1))}
                      className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">+</button>
                    <span className="text-sm text-slate-500 shrink-0">{sel.unit || t('common.piece')}</span>
                  </div>
                </Lbl>

                {Number(qty) > Number(sel.stock_quantity) && Number(sel.stock_quantity) > 0 && (
                  <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                    ⚠️ {t('ops.qtyExceedsStock')} ({fmt(sel.stock_quantity)})
                  </div>
                )}

                {/* ── Maqsad mahsulot (ixtiyoriy mapping) ── */}
                <div className="border-t border-blue-200 pt-3">
                  <div className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                    {t('ops.mapToOtherProduct')}
                  </div>
                  <div className="relative" ref={targetRef}>
                    <div className={`flex items-center border rounded-xl bg-white overflow-hidden focus-within:ring-2 focus-within:ring-blue-400 transition-colors ${selTargetProd ? 'border-blue-300' : 'border-slate-200'}`}>
                      <svg className="w-3.5 h-3.5 ml-3 shrink-0 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
                      </svg>
                      <input
                        value={targetOpen ? targetQ : (selTargetProd ? selTargetProd.name : '')}
                        onChange={e => { setTargetQ(e.target.value); setTargetOpen(true); if (!e.target.value) setSelTargetProd(null); }}
                        onFocus={() => setTargetOpen(true)}
                        onBlur={() => setTimeout(() => setTargetOpen(false), 150)}
                        placeholder={t('ops.emptyMeansSameProduct')}
                        className="flex-1 px-2 py-2 text-xs outline-none bg-transparent min-w-0"
                      />
                      {selTargetProd && (
                        <button onMouseDown={() => { setSelTargetProd(null); setTargetQ(''); }}
                          className="px-2 text-slate-400 hover:text-red-400 leading-none text-base">×</button>
                      )}
                    </div>
                    {targetOpen && (
                      <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-48 overflow-y-auto">
                        {targetResults
                          .filter(p => p.id !== sel.id)
                          .slice(0, 15)
                          .map(p => (
                            <button key={p.id} onMouseDown={() => { setSelTargetProd(p); setTargetQ(''); setTargetOpen(false); }}
                              className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-2">
                              <span className="text-xs font-medium text-slate-800 truncate">{p.name}</span>
                              <span className="text-[10px] text-slate-400 shrink-0">{p.sku}</span>
                            </button>
                          ))}
                        {!targetQ.trim() && (
                          <div className="px-3 py-2 text-[10px] text-slate-400 bg-slate-50 border-t border-slate-100 text-center">
                            {t('ops.typeSearchOrLeaveEmpty')}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  {selTargetProd && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-blue-700 font-semibold bg-blue-50 px-3 py-1.5 rounded-lg border border-blue-200">
                      <span className="text-slate-500">{sel.name}</span>
                      <svg className="w-3.5 h-3.5 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                      </svg>
                      <span className="text-blue-700">{selTargetProd.name}</span>
                    </div>
                  )}
                </div>
              </div>

            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-10">
                <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                <p className="text-sm text-center">{t('purchase.searchAndSelect')}</p>
              </div>
            )}

            <button onClick={addItem} disabled={!sel || !qty || Number(sel?.stock_quantity) <= 0}
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-blue-200 active:scale-95">
              <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              {t('purchase.addToList')}
            </button>

            {items.length > 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-center">
                <div className="text-xs text-slate-400 font-medium">{items.length} {t('ops.kindsProduct')}</div>
                <div className="text-lg font-bold text-blue-600 mt-1">{items.reduce((s, i) => s + Number(i.quantity), 0)} {t('common.piece')}</div>
              </div>
            )}
          </div>

          {/* RIGHT — Items list */}
          <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
            <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-100 shrink-0">
              <span className="text-sm font-bold text-slate-700">{t('ops.transferList')}</span>
              {items.length > 0 && (
                <button onClick={() => setItems([])} className="text-xs text-red-400 hover:text-red-600 flex items-center gap-1 px-2 py-1 hover:bg-red-50 rounded-lg transition-colors">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  {t('admin.dict.clear')}
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3">
                  <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
                  <p className="text-sm">{t('ops.addProductFromLeftPanel')}</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white border-b border-slate-200 z-10">
                    <tr>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product') || 'Mahsulot'}</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('ops.currentStock')}</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('ops.transferQty')}</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('ops.unit')}</th>
                      <th className="w-10" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {items.map((it, i) => (
                      <tr key={i} className="hover:bg-white/80 transition-colors">
                        <td className="px-5 py-3.5 text-slate-400 text-xs">{i + 1}</td>
                        <td className="px-5 py-3.5">
                          {it.target_product_name ? (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-semibold text-slate-700 text-sm">{it.product_name}</span>
                              <svg className="w-3.5 h-3.5 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                              </svg>
                              <span className="font-bold text-blue-700 text-sm">{it.target_product_name}</span>
                              <span className="text-[10px] bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded font-semibold">{t('ops.mapping')}</span>
                            </div>
                          ) : (
                            <div className="font-semibold text-slate-800">{it.product_name}</div>
                          )}
                        </td>

                        <td className="px-4 py-3.5 text-center">
                          <span className={`text-sm font-semibold ${it.quantity > it.stock ? 'text-amber-600' : 'text-slate-600'}`}>{fmt(it.stock)}</span>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <button onClick={() => setItems(p => p.map((x, idx) => idx === i ? { ...x, quantity: Math.max(0.001, x.quantity - 1) } : x))}
                              className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center leading-none">−</button>
                            <input type="number" min="0.001" step="any" value={it.quantity}
                              onChange={e => setItems(p => p.map((x, idx) => idx === i ? { ...x, quantity: Number(e.target.value) || 1 } : x))}
                              className="w-16 text-center border border-slate-200 rounded px-1 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 font-bold" />
                            <button onClick={() => setItems(p => p.map((x, idx) => idx === i ? { ...x, quantity: x.quantity + 1 } : x))}
                              className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center leading-none">+</button>
                          </div>
                          {it.quantity > it.stock && (
                            <div className="text-[10px] text-amber-500 mt-1">⚠️ {t('ops.moreThanStock')}</div>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-center text-xs text-slate-400">{it.unit}</td>
                        <td className="pr-4">
                          <button onClick={() => setItems(p => p.filter((_, idx) => idx !== i))}
                            className="p-1.5 text-slate-300 hover:text-red-500 rounded transition-colors">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Footer nav */}
            <div className="flex items-center justify-between px-6 py-3.5 bg-white border-t border-slate-200 shrink-0">
              <button onClick={() => setStep(1)} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 px-4 py-2 rounded-xl hover:bg-blue-50 text-sm font-semibold transition-all">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
                {t('common.back')}
              </button>
              <button disabled={items.length === 0} onClick={() => setStep(3)}
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-blue-200">
                {t('ops.goToConfirm')}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════ STEP 3 — TASDIQLASH ══════════════════ */}
      {step === 3 && (
        <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-start">
          <div className="w-full max-w-2xl space-y-5">

            {/* Transfer route summary card */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
                <span className="text-sm font-bold text-slate-700">{t('ops.transferRoute')}</span>
              </div>
              <div className="p-5 flex items-center gap-4">
                <div className="flex-1 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 text-center">
                  <div className="text-xs text-blue-500 font-bold uppercase tracking-wide mb-1">{t('ops.fromWhom')}</div>
                  <div className="font-bold text-blue-800 text-base">{fromWh?.name}</div>
                </div>
                <div className="flex flex-col items-center gap-1 shrink-0">
                  <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" /></svg>
                  <span className="text-[10px] text-slate-400 font-bold">{t('ops.transit')}</span>
                </div>
                <div className="flex-1 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-center">
                  <div className="text-xs text-emerald-600 font-bold uppercase tracking-wide mb-1">{t('ops.toWhom')}</div>
                  <div className="font-bold text-emerald-800 text-base">{toWh?.name}</div>
                </div>
              </div>
              {form.note && (
                <div className="px-5 pb-4">
                  <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-sm text-slate-600 italic">
                    💬 {form.note}
                  </div>
                </div>
              )}
            </div>

            {/* Transit status info */}
            <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-start gap-3">
              <div className="w-8 h-8 bg-amber-100 rounded-xl flex items-center justify-center shrink-0">
                <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <div>
                <div className="text-sm font-bold text-amber-800 mb-0.5">{t('ops.transitStatusAbout')}</div>
                <p className="text-xs text-amber-700 leading-relaxed">
                  {t('ops.transitStatusExplanation')}
                </p>
              </div>
            </div>

            {/* Items summary */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                <span className="text-sm font-bold text-slate-700">{t('ops.productsToTransfer')}</span>
                <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">{items.length} {t('ops.kindsShort')} · {items.reduce((s, i) => s + i.quantity, 0)} {t('common.piece')}</span>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-100">
                  <tr>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product') || 'Mahsulot'}</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.qty') || 'Miqdor'}</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">{t('ops.unit')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {items.map((it, i) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-5 py-3 text-slate-400 text-xs">{i + 1}</td>
                      <td className="px-5 py-3">
                        {it.target_product_name ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-medium text-slate-600 text-sm">{it.product_name}</span>
                            <svg className="w-3.5 h-3.5 text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                            </svg>
                            <span className="font-bold text-blue-700 text-sm">{it.target_product_name}</span>
                          </div>
                        ) : (
                          <span className="font-medium text-slate-800">{it.product_name}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center font-bold text-blue-600">{it.quantity}</td>
                      <td className="px-4 py-3 text-center text-slate-400 text-xs">{it.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Error */}
            {err && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                {err}
              </div>
            )}

            {crossBranch && !editData && (
              <div className="bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-xl px-4 py-3">
                {tOr(t, 'transfers.twoStepHint', "Boshqa filialga ko'chirish ikki bosqichli: yuborilgach tovar \"yo'lda\" bo'ladi, qoldiq esa qabul qiluvchi filial tasdiqlagandan keyin o'tadi.")}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between">
              <button onClick={() => setStep(2)} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 px-4 py-2.5 rounded-xl hover:bg-blue-50 text-sm font-semibold transition-all">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
                {t('common.back')}
              </button>
              {crossBranch && !editData && (
                <button onClick={() => save(false)} disabled={saving}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 border border-slate-200 rounded-xl font-bold text-sm transition-all active:scale-95">
                  {t('common.save')}
                </button>
              )}
              <button onClick={() => save(true)} disabled={saving}
                className="inline-flex items-center gap-2.5 px-8 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-emerald-200 active:scale-95">
                {saving ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                    {t('common.saving')}
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    {crossBranch && !editData ? tOr(t, 'transfers.saveAndSend', 'Saqlab yuborish') : t('ops.createTransfer')}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}





function TransferlarTab({ warehouses, allWarehouses = null, users = [] }) {
  const { t } = useLang();
  const [mode, setMode] = useState('list');
  const [transfers, setTr] = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip] = useState(0);
  const [f, setF] = useState({ dateFrom: today(), dateTo: today(), status: '', direction: '', fromWh_id: '', toWh_id: '', user_id: '', statusQ: '', fromWhQ: '', toWhQ: '', userQ: '' });
  const [detail, setDetail] = useState(null);
  const [recv, setRecv] = useState(null); // T4.1: qabul modali {id, number, rows, note, saving}
  const [editData, setEditData] = useState(null);
  const LIMIT = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (f.status) params.status = f.status;
      if (f.direction) params.direction = f.direction;
      if (f.dateFrom) params.date_from = f.dateFrom;
      if (f.dateTo) params.date_to = f.dateTo;
      if (f.fromWh_id) params.from_warehouse_id = f.fromWh_id;
      if (f.toWh_id) params.to_warehouse_id = f.toWh_id;
      if (f.user_id) params.user_id = f.user_id;
      const r = await api.get('/transfers', { params });
      setTr(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, f]);

  useEffect(() => { if (mode === 'list') load(); }, [load, mode]);

  const openDetail = async (row) => {
    const r = await api.get(`/transfers/${row.id}`);
    setDetail(r.data);
  };
  // T4.1: pending -> in_transit (manba ombor kamayadi)
  const send = async (id) => {
    try {
      await api.post(`/transfers/${id}/send`);
      toast.success(tOr(t, 'transfers.sentOk', 'Transfer yuborildi'));
      setDetail(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('ops.errorOccurred')); }
  };
  // T4.1: qabul modalini ochish — har qator uchun haqiqiy miqdor (boshida to'liq) va kamomad sababi
  const openReceive = async (id) => {
    try {
      const r = await api.get(`/transfers/${id}`);
      setRecv({
        id: r.data.id, number: r.data.number, note: '', saving: false,
        rows: (r.data.items || []).map(i => ({
          item_id: i.id, name: i.product_name,
          sent: Number(i.qty_sent ?? i.quantity), qty: String(Number(i.qty_sent ?? i.quantity)), reason: '',
        })),
      });
    } catch (e) { toast.error(e.response?.data?.detail || t('ops.errorLoadingData')); }
  };
  const submitReceive = async () => {
    for (const r of recv.rows) {
      const q = Number(r.qty);
      if (!(q >= 0) || q > r.sent) { toast.error(`${r.name}: ${tOr(t, 'transfers.qtyInvalid', "Miqdor 0 dan yuborilgan miqdorgacha bo'lishi kerak")}`); return; }
      if (q < r.sent && !r.reason.trim()) { toast.error(`${r.name}: ${tOr(t, 'transfers.reasonRequired', 'Kamomad sababini kiriting')}`); return; }
    }
    setRecv(p => ({ ...p, saving: true }));
    try {
      await api.post(`/transfers/${recv.id}/receive`, {
        items: recv.rows.map(r => ({ item_id: r.item_id, qty_received: Number(r.qty), reason: r.reason.trim() || null })),
        note: recv.note.trim() || null,
      });
      toast.success(tOr(t, 'transfers.receivedOk', 'Transfer qabul qilindi'));
      setRecv(null); setDetail(null);
      load();
    } catch (e) {
      setRecv(p => ({ ...p, saving: false }));
      toast.error(e.response?.data?.detail || t('ops.errorOccurred'));
    }
  };
  const cancel = async (id) => {
    // Sabab ixtiyoriy; Esc/Bekor — amal to'xtatiladi
    const reason = window.prompt(tOr(t, 'transfers.cancelReasonPrompt', 'Bekor qilish sababi (ixtiyoriy)'), '');
    if (reason === null) return;
    try {
      await api.post(`/transfers/${id}/cancel`, { reason: reason.trim() || null });
      toast.success(t('ops.transferCancelled'));
      setDetail(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('ops.errorOccurred')); }
  };
  // T4.1: yuk xati — oddiy HTML, brauzer chop etish oynasi orqali
  const printWaybill = (d) => {
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const rows = (d.items || []).map((i, n) => `<tr><td>${n + 1}</td><td>${esc(i.product_name)}${i.variant_name ? ' / ' + esc(i.variant_name) : ''}</td><td class="r">${esc(fmt(i.qty_sent ?? i.quantity))}</td><td class="r">${i.qty_received == null ? '' : esc(fmt(i.qty_received))}</td><td>${esc(i.discrepancy_reason || '')}</td></tr>`).join('');
    const w = window.open('', '_blank', 'width=800,height=900');
    if (!w) { toast.error(t('ops.errorOccurred')); return; }
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(d.number)}</title>
<style>body{font-family:Arial,sans-serif;font-size:13px;margin:24px}h2{margin:0 0 12px}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{border:1px solid #444;padding:6px 8px;text-align:left}.r{text-align:right}.sign{display:flex;justify-content:space-between;margin-top:48px}.sign div{width:45%;border-top:1px solid #444;padding-top:4px}</style></head><body>
<h2>${esc(tOr(t, 'transfers.waybill', 'Yuk xati'))} № ${esc(d.number)}</h2>
<div>${esc(t('ops.fromWhom'))}: <b>${esc(d.from_warehouse_name)}${d.from_branch_name ? ' — ' + esc(d.from_branch_name) : ''}</b></div>
<div>${esc(t('ops.toWhom'))}: <b>${esc(d.to_warehouse_name)}${d.to_branch_name ? ' — ' + esc(d.to_branch_name) : ''}</b></div>
<div>${esc(t('common.date'))}: ${esc(fmtDt(d.sent_at || d.created_at))}</div>
${d.note ? `<div>${esc(d.note)}</div>` : ''}
<table><thead><tr><th>#</th><th>${esc(t('admin.dict.product') || 'Mahsulot')}</th><th class="r">${esc(tOr(t, 'transfers.qtySent', 'Yuborilgan'))}</th><th class="r">${esc(tOr(t, 'transfers.qtyReceived', 'Haqiqiy miqdor'))}</th><th>${esc(tOr(t, 'transfers.shortageReason', 'Kamomad sababi'))}</th></tr></thead><tbody>${rows}</tbody></table>
<div class="sign"><div>${esc(tOr(t, 'transfers.sender', 'Yuboruvchi'))}: ${esc(d.sender_name || '')}</div><div>${esc(tOr(t, 'transfers.receiver', 'Qabul qiluvchi'))}: ${esc(d.confirmer_name || '')}</div></div>
<script>window.onload=function(){window.print();}</script></body></html>`);
    w.document.close();
  };

  const handleEdit = async (row) => {
    try {
      const r = await api.get(`/transfers/${row.id}`);
      setEditData(r.data);
      setMode('edit');
    } catch (e) {
      toast.error(t('ops.errorLoadingData'));
    }
  };

  const handleReturn = async (row) => {
    if (!window.confirm(t('ops.confirmReturnTransfer'))) return;
    try {
      await api.post(`/transfers/${row.id}/cancel`);
      toast.success(t('ops.productReturnedSuccessfully'));
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('ops.errorOccurred'));
    }
  };

  const handleDelete = async (row) => {
    if (!window.confirm(t('ops.confirmDeleteTransfer'))) return;
    try {
      await api.delete(`/transfers/${row.id}`);
      toast.success(t('ops.transferDeleted'));
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('ops.errorOccurred'));
    }
  };

  if (mode === 'create') return <TransferCreateView warehouses={warehouses} allWarehouses={allWarehouses} onBack={() => setMode('list')} onSaved={load} />;
  if (mode === 'edit' && editData) return <TransferCreateView warehouses={warehouses} allWarehouses={allWarehouses} editData={editData} onBack={() => { setMode('list'); setEditData(null); }} onSaved={load} />;



  const cols = [
    { k: 'number', l: t('common.number') },
    { k: 'from_warehouse_name', l: t('ops.fromWhom'), r: (v, row) => whLabel({ name: v, branch_name: row.from_branch_name }) },
    { k: 'to_warehouse_name', l: t('ops.toWhom'), r: (v, row) => whLabel({ name: v, branch_name: row.to_branch_name }) },
    { k: 'total_qty', l: t('admin.dict.qty') || 'Miqdor', r: v => fmt(v) },
    { k: 'status', l: t('common.status'), r: v => <Badge meta={trMeta} val={v} /> },
    { k: 'created_at', l: t('common.date'), r: v => fmtDay(v) },
    { k: '', l: '', r: (v, row) => <OptionsTable row={row} onEdit={handleEdit} onReturn={handleReturn} onDelete={handleDelete} /> },
    {
      // T4.1: tugmalar holat va filial ruxsatiga qarab (server can_send / can_receive / can_cancel bergan)
      k: 'id', l: '', r: (v, row) => (
        <div className="flex gap-1.5" onClick={e => e.stopPropagation()}>
          {row.status === 'pending' && row.can_send && (
            <Btn v="primary" sm onClick={() => send(v)}>{tOr(t, 'transfers.send', 'Yuborish')}</Btn>
          )}
          {row.status === 'in_transit' && row.can_receive && (
            <Btn v="green" sm onClick={() => openReceive(v)}>{tOr(t, 'transfers.receive', 'Qabul qilish')}</Btn>
          )}
          {(row.status === 'pending' || row.status === 'in_transit') && row.can_cancel && (
            <Btn v="red" sm onClick={() => cancel(v)}>{t('common.cancel')}</Btn>
          )}
        </div>
      )
    },
  ];

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          <Btn onClick={() => setMode('create')} sm>
            <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            {t('ops.newTransfer')}
          </Btn>
        </div>
      </div>

      {/* Filters — Custom 2-row grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* T3.3: holat — tayyor ro'yxatdan (backend TransferStatus qiymatlari), matn bo'yicha taxmin qilinmaydi */}
          <select value={f.status} onChange={e => setF({ ...f, status: e.target.value })}
            className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white">
            <option value="">{t('common.all')}</option>
            {Object.entries(trMeta).map(([k, m]) => <option key={k} value={k}>{t(m.l)}</option>)}
          </select>
          {/* T4.1: yo'nalish — mening filialimdan chiquvchi / filialimga kiruvchi */}
          <select value={f.direction} onChange={e => { setSkip(0); setF({ ...f, direction: e.target.value }); }}
            className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white">
            <option value="">{tOr(t, 'transfers.direction', "Yo'nalish")}: {t('common.all')}</option>
            <option value="outgoing">{tOr(t, 'transfers.dirOutgoing', 'Chiquvchi')}</option>
            <option value="incoming">{tOr(t, 'transfers.dirIncoming', 'Kiruvchi')}</option>
          </select>
          <input type="date" value={f.dateFrom} onChange={e => setF({ ...f, dateFrom: e.target.value })} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white" />
          <input type="date" value={f.dateTo} onChange={e => setF({ ...f, dateTo: e.target.value })} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          {/* Kimdan (From warehouse) */}
          <div className="relative">
            <input type="text" value={f.fromWhQ || ''} placeholder={`${t('ops.fromWhom')} (${t('admin.dict.warehouse')})`}
              onChange={e => setF({ ...f, fromWhQ: e.target.value, fromWh_id: '' })}
              onFocus={() => setF(p => ({ ...p, _fromOpen: true }))}
              onBlur={() => setTimeout(() => setF(p => ({ ...p, _fromOpen: false })), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._fromOpen && f.fromWhQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {(allWarehouses || warehouses).filter(w => matchesSearch(whLabel(w), f.fromWhQ || '')).slice(0, 10).map(w => (
                  <button key={w.id} onMouseDown={() => setF({ ...f, fromWh_id: String(w.id), fromWhQ: w.name, _fromOpen: false })}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{whLabel(w)}</button>
                ))}
              </div>
            )}
          </div>
          <span className="text-slate-300 text-lg">→</span>
          {/* Kimga (To warehouse) */}
          <div className="relative">
            <input type="text" value={f.toWhQ || ''} placeholder={`${t('ops.toWhom')} (${t('admin.dict.warehouse')})`}
              onChange={e => setF({ ...f, toWhQ: e.target.value, toWh_id: '' })}
              onFocus={() => setF(p => ({ ...p, _toOpen: true }))}
              onBlur={() => setTimeout(() => setF(p => ({ ...p, _toOpen: false })), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._toOpen && f.toWhQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {(allWarehouses || warehouses).filter(w => matchesSearch(whLabel(w), f.toWhQ || '')).slice(0, 10).map(w => (
                  <button key={w.id} onMouseDown={() => setF({ ...f, toWh_id: String(w.id), toWhQ: w.name, _toOpen: false })}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{whLabel(w)}</button>
                ))}
              </div>
            )}
          </div>
          {/* Foydalanuvchi */}
          <div className="relative">
            <input type="text" value={f.userQ || ''} placeholder={t('admin.dict.user') || 'Foydalanuvchi'}
              onChange={e => setF({ ...f, userQ: e.target.value, user_id: '' })}
              onFocus={() => setF(p => ({ ...p, _usOpen: true }))}
              onBlur={() => setTimeout(() => setF(p => ({ ...p, _usOpen: false })), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users?.filter(u => matchesSearch(u.name, f.userQ || '')).slice(0, 10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({ ...f, user_id: String(u.id), userQ: u.name, _usOpen: false })}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{u.name}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <Tbl cols={cols} rows={transfers} loading={loading} skip={skip} limit={LIMIT} onChange={setSkip} onRow={openDetail} />
      </div>
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="text-lg font-bold">{t('ops.transfer')} · {detail.number}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  [t('ops.fromWhom'), whLabel({ name: detail.from_warehouse_name, branch_name: detail.from_branch_name })],
                  [t('ops.toWhom'), whLabel({ name: detail.to_warehouse_name, branch_name: detail.to_branch_name })],
                  [t('common.status'), <Badge meta={trMeta} val={detail.status} />],
                  [t('common.date'), fmtDt(detail.created_at)],
                  detail.sent_at && [tOr(t, 'transfers.sender', 'Yuboruvchi'), `${detail.sender_name || '—'} · ${fmtDt(detail.sent_at)}`],
                  detail.status === 'received' && detail.confirmed_at && [tOr(t, 'transfers.receiver', 'Qabul qiluvchi'), `${detail.confirmer_name || '—'} · ${fmtDt(detail.confirmed_at)}`],
                ].filter(Boolean).map(([k, v]) => (
                  <div key={k} className="bg-slate-50 rounded-xl p-3 text-sm"><div className="text-xs text-slate-500 mb-1">{k}</div><div className="font-semibold">{v}</div></div>
                ))}
              </div>
              {detail.cancel_reason && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{detail.cancel_reason}</div>
              )}
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.product') || 'Mahsulot'}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.qtySent', 'Yuborilgan')}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.qtyReceived', 'Haqiqiy miqdor')}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.shortage', 'Kamomad')}</th>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.shortageReason', 'Kamomad sababi')}</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.items?.map(item => {
                    const sent = Number(item.qty_sent ?? item.quantity);
                    const diff = item.qty_received == null ? null : sent - Number(item.qty_received);
                    return (
                      <tr key={item.id}>
                        <td className="px-4 py-3 font-medium">{item.product_name}</td>
                        <td className="px-4 py-3 text-center font-semibold">{fmt(sent)}</td>
                        <td className="px-4 py-3 text-center font-semibold">{item.qty_received == null ? '—' : fmt(item.qty_received)}</td>
                        <td className={`px-4 py-3 text-center font-semibold ${diff > 0 ? 'text-red-600' : 'text-slate-400'}`}>{diff > 0 ? fmt(diff) : '—'}</td>
                        <td className="px-4 py-3 text-slate-600">{item.discrepancy_reason || ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap justify-end gap-2 px-6 py-4 border-t">
              <Btn v="ghost" onClick={() => printWaybill(detail)}>{tOr(t, 'transfers.printWaybill', 'Yuk xatini chop etish')}</Btn>
              {detail.status === 'pending' && detail.can_send && (
                <Btn v="primary" onClick={() => send(detail.id)}>{tOr(t, 'transfers.send', 'Yuborish')}</Btn>
              )}
              {detail.status === 'in_transit' && detail.can_receive && (
                <Btn v="green" onClick={() => openReceive(detail.id)}>{tOr(t, 'transfers.receive', 'Qabul qilish')}</Btn>
              )}
              {(detail.status === 'pending' || detail.status === 'in_transit') && detail.can_cancel && (
                <Btn v="red" onClick={() => cancel(detail.id)}>{t('common.cancel')}</Btn>
              )}
            </div>
          </div>
        </div>
      )}

      {recv && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="text-lg font-bold">{tOr(t, 'transfers.receiveTitle', 'Transferni qabul qilish')} · {recv.number}</h3>
              <button onClick={() => setRecv(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-3 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.product') || 'Mahsulot'}</th>
                  <th className="text-center px-3 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.qtySent', 'Yuborilgan')}</th>
                  <th className="text-center px-3 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.qtyReceived', 'Haqiqiy miqdor')}</th>
                  <th className="text-center px-3 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.shortage', 'Kamomad')}</th>
                  <th className="text-left px-3 py-2.5 text-xs text-slate-500 font-semibold">{tOr(t, 'transfers.shortageReason', 'Kamomad sababi')}</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {recv.rows.map((r, idx) => {
                    const diff = Math.max(0, r.sent - (Number(r.qty) || 0));
                    return (
                      <tr key={r.item_id}>
                        <td className="px-3 py-2 font-medium">{r.name}</td>
                        <td className="px-3 py-2 text-center">{fmt(r.sent)}</td>
                        <td className="px-3 py-2 text-center">
                          <input type="number" min="0" max={r.sent} step="any" value={r.qty}
                            onChange={e => setRecv(p => ({ ...p, rows: p.rows.map((x, i) => i === idx ? { ...x, qty: e.target.value } : x) }))}
                            className={`${ic} w-24 text-center`} />
                        </td>
                        <td className={`px-3 py-2 text-center font-semibold ${diff > 0 ? 'text-red-600' : 'text-slate-400'}`}>{diff > 0 ? fmt(diff) : '—'}</td>
                        <td className="px-3 py-2">
                          {diff > 0 && (
                            <input type="text" maxLength={200} value={r.reason}
                              onChange={e => setRecv(p => ({ ...p, rows: p.rows.map((x, i) => i === idx ? { ...x, reason: e.target.value } : x) }))}
                              placeholder={tOr(t, 'transfers.shortageReason', 'Kamomad sababi')} className={`${ic} w-full`} />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <input type="text" value={recv.note} onChange={e => setRecv(p => ({ ...p, note: e.target.value }))}
                placeholder={tOr(t, 'common.note', 'Izoh')} className={`${ic} w-full`} />
            </div>
            <div className="flex justify-end gap-2 px-6 py-4 border-t">
              <Btn v="ghost" onClick={() => setRecv(null)}>{t('common.cancel')}</Btn>
              <Btn v="green" disabled={recv.saving} onClick={submitReceive}>{tOr(t, 'transfers.receive', 'Qabul qilish')}</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   REVIZIYALAR
══════════════════════════════════════════════════════════ */
function ReviziyalarTab() {
  const { t } = useLang();
  return <InventoryCountsPage />;
}

/* ══════════════════════════════════════════════════════════
   CHIQIMLAR
══════════════════════════════════════════════════════════ */
const CHIQIM_TYPES = [
  { v: 'brak', l: 'ops.chiqimType.brak' },
  { v: 'yoqotish', l: 'ops.chiqimType.yoqotish' },
  { v: 'namunaviy', l: 'ops.chiqimType.namunaviy' },
  { v: 'qaytarma', l: 'ops.chiqimType.qaytarma' },
  { v: 'boshqa', l: 'ops.chiqimType.boshqa' },
];


function ChiqimCreateView({ products, warehouses = [], onBack, onSaved, editItems = [], editId = null }) {
  const { t } = useLang();
  // T1.8: ombor majburiy — tahrirda asl ombor, aks holda foydalanuvchi filialidagi birinchi ombor
  const [warehouseId, setWarehouseId] = useState(() => {
    const own = editItems.find(i => i.warehouse_id)?.warehouse_id;
    if (own) return String(own);
    return warehouses[0]?.id ? String(warehouses[0].id) : '';
  });
  useEffect(() => {
    if (!warehouseId && warehouses.length > 0) setWarehouseId(String(warehouses[0].id));
  }, [warehouses]); // eslint-disable-line react-hooks/exhaustive-deps
  const [items, setItems] = useState(() => {
    return editItems.map(i => ({
      variant_id: i.variant_id || null,
      product: { id: i.product_id, name: i.product_name, stock_quantity: 0, unit: i.product_unit },
      qty: i.quantity,
      type: CHIQIM_TYPES.find(t => t.l === i.type || t.v === i.type)?.v || CHIQIM_TYPES[0].v,
      doc_num: i.doc_num || '',
      reason: i.reason || ''
    }));
  });
  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('1');
  const qtyRef = useRef(null);
  const [form, setForm] = useState({ type: 'brak', doc_num: '', reason: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const addItem = () => {
    if (!sel || !qty || Number(qty) <= 0) return;
    setItems(p => [...p, { product: sel, qty: Number(qty), type: form.type, doc_num: form.doc_num, reason: form.reason }]);
    setSel(null); setQty('1'); setForm({ type: 'brak', doc_num: '', reason: '' });
  };

  const save = async (overridePayType) => {
    const pType = typeof overridePayType === 'string' ? overridePayType : form.payment_type;
    if (!items.length) return;
    if (!warehouseId) { setErr(t('ops.chiqim.warehouseRequired')); return; }
    setSaving(true); setErr('');
    try {
      const payload = items.map(item => ({
        product_id: Number(item.product.id),
        variant_id: item.variant_id || undefined,
        quantity: Number(item.qty),
        type: item.type,
        doc_num: item.doc_num || undefined,
        reason: item.reason || undefined,
      }));
      const body = { items: payload, warehouse_id: Number(warehouseId) };
      if (editId) {
        // Tahrir — bitta tranzaksiya (eski chiqimni bekor qilish + yangisini yozish)
        await api.put(`/inventory/chiqims/${editId}`, body);
      } else {
        await api.post('/inventory/chiqims', body);
      }
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-100 flex flex-col">
      <div className="flex items-center gap-4 px-6 py-3.5 bg-white border-b border-slate-100 shadow-sm shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-blue-600 px-3 py-2 rounded-xl hover:bg-blue-50 transition-all text-sm font-semibold">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>
          {t('common.back')}
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0" />
        <h2 className="text-base font-bold text-slate-800">{editId ? `${t('ops.editChiqim')} (#${editId})` : t('ops.newChiqim')}</h2>
        <div className="ml-auto text-xs text-slate-400 font-medium">{new Date().toLocaleString('uz-UZ')}</div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT */}
        <div className="w-[500px] border-r border-slate-200 bg-white flex flex-col gap-4 p-5 overflow-y-auto shrink-0 shadow-sm">
          <Lbl t={`${t('ops.whichWarehouse')} *`}>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className={ic}>
              {!warehouseId && <option value="" disabled>{t('ops.chiqim.warehouseRequired')}</option>}
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </Lbl>

          <Lbl t={t('purchase.searchProduct')}>
            <ProdSearch products={products} onSelect={p => { setSel(p); setQty('1'); setTimeout(() => qtyRef.current?.focus(), 50); }} />
          </Lbl>

          {sel ? (
            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {sel.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm truncate">{sel.name}</div>
                  <div className="text-xs mt-0.5">
                    <span className="text-slate-500">{t('ops.stockInWarehouse')}:</span>
                    <span className="font-bold ml-1 text-emerald-600">{fmt(sel.stock_quantity)} {sel.unit || t('common.piece')}</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Lbl t={`${t('ops.chiqimTypeLabel')} *`}>
                  <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))} className={ic}>
                    {CHIQIM_TYPES.map(ct => <option key={ct.v} value={ct.v}>{t(ct.l)}</option>)}
                  </select>
                </Lbl>
                <Lbl t={`${t('common.quantity')} *`}>
                  <div className="flex gap-2 items-center">
                    <button onClick={() => setQty(q => String(Math.max(1, Number(q) - 1)))} className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">−</button>
                    <input ref={qtyRef} type="number" min="0.001" step="any" value={qty} onChange={e => setQty(e.target.value)} onKeyDown={e => e.key === 'Enter' && addItem()} className={`flex-1 ${ic} text-center font-bold`} />
                    <button onClick={() => setQty(q => String(Number(q) + 1))} className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">+</button>
                  </div>
                </Lbl>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Lbl t={t('ops.docNumber')}>
                  <input value={form.doc_num} onChange={e => setForm(f => ({ ...f, doc_num: e.target.value }))} onKeyDown={e => e.key === 'Enter' && addItem()} className={ic} placeholder="ACT-001" />
                </Lbl>
                <Lbl t={t('common.note')}>
                  <input value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))} onKeyDown={e => e.key === 'Enter' && addItem()} className={ic} placeholder={`${t('ops.reason')}...`} />
                </Lbl>
              </div>

              {form.type === 'brak' && (
                <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-700">
                  ⚠️ {t('ops.brakCannotBeReturned')}
                </div>
              )}

              <button onClick={addItem} disabled={!qty || Number(qty) <= 0} className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-2xl font-bold text-sm transition-all shadow-sm active:scale-95">
                {t('purchase.addToList')}
              </button>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-10">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
              <p className="text-sm text-center">{t('purchase.searchAndSelect')}</p>
            </div>
          )}
        </div>

        {/* RIGHT */}
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
          <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-100 shrink-0">
            <span className="text-sm font-bold text-slate-700">{t('ops.productsToChiqim')}</span>
            {items.length > 0 && <button onClick={() => setItems([])} className="text-xs text-red-500 font-semibold hover:underline">{t('admin.dict.clear') || 'Tozalash'}</button>}
          </div>
          <div className="flex-1 overflow-y-auto">
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3">
                <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
                <p className="text-sm">{t('ops.addProductFromLeftPanel')}</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white border-b border-slate-200 z-10">
                  <tr>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">{t('admin.dict.product') || 'Mahsulot'}</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">{t('ops.typeOrReason')}</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500">{t('admin.dict.qty') || 'Miqdor'}</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((it, i) => (
                    <tr key={i} className="hover:bg-white transition-colors">
                      <td className="px-5 py-3.5 text-slate-400 text-xs">{i + 1}</td>
                      <td className="px-5 py-3.5 font-semibold text-slate-800">{it.product.name}</td>
                      <td className="px-5 py-3.5">
                        <div className="text-xs font-semibold text-blue-600">{CHIQIM_TYPES.find(t => t.v === it.type)?.l?.split('—')[0]?.trim() || it.type}</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">{[it.doc_num, it.reason].filter(Boolean).join(' | ')}</div>
                      </td>
                      <td className="px-4 py-3.5 text-center font-bold text-red-500">−{it.qty} {it.product.unit}</td>
                      <td className="pr-4">
                        <button onClick={() => setItems(p => p.filter((_, idx) => idx !== i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded">✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="flex items-center justify-between px-6 py-4 bg-white border-t border-slate-200 shrink-0">
            <div>{err && <span className="text-red-500 text-sm font-semibold">{err}</span>}</div>
            <div className="flex items-center gap-3">
              <button onClick={onBack} className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-semibold hover:bg-slate-50">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving || !items.length || !warehouseId} className="px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition-all disabled:opacity-50 shadow-sm flex items-center gap-2">
                {saving ? t('ops.confirming') : t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChiqimlarTab({ products, users = [], warehouses = [] }) {
  const { t } = useLang();
  const [mode, setMode] = useState('list');
  const [movements, setMov] = useState([]);
  const [movLoad, setML] = useState(false);
  const [f, setF] = useState({ dateFrom: today(), dateTo: today(), user_id: '', userQ: '' });

  const loadMov = useCallback(() => {
    setML(true);
    const params = { skip: 0, limit: 100 };
    if (f.dateFrom) params.date_from = f.dateFrom;
    if (f.dateTo) params.date_to = f.dateTo;
    if (f.user_id) params.user_id = f.user_id;

    api.get('/inventory/chiqims', { params })
      .then(r => setMov(r.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred')) })
      .finally(() => setML(false));
  }, [f]);
  useEffect(() => { if (mode === 'list') loadMov(); }, [mode, loadMov]);

  const [detailId, setDetailId] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailItems, setDetailItems] = useState([]);

  const openDetail = async (id) => {
    setDetailId(id);
    setLoadingDetail(true);
    try {
      const r = await api.get(`/inventory/chiqims/${id}`);
      setDetailItems(r.data);
    } catch {
      // ignore
    } finally {
      setLoadingDetail(false);
    }
  };

  const deleteChiqim = async (id) => {
    if (!window.confirm(t('ops.confirmCancelChiqim'))) return;
    try {
      await api.delete(`/inventory/chiqims/${id}`);
      loadMov();
      if (detailId === id) setDetailId(null);
    } catch (e) {
      alert(`${t('common.error')}: ` + (e.response?.data?.detail || e.message));
    }
  };

  const [editingData, setEditingData] = useState(null);

  if (mode === 'create') return <ChiqimCreateView products={products} warehouses={warehouses} onBack={() => { setMode('list'); setEditingData(null); }} onSaved={loadMov} editId={editingData?.id} editItems={editingData?.items} />;

  const startEdit = () => {
    setEditingData({ id: detailId, items: detailItems });
    setDetailId(null);
    setMode('create');
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          <Btn onClick={() => setMode('create')} sm>
            <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            {t('ops.newChiqim')}
          </Btn>
        </div>
      </div>

      {/* Filters — Custom 2-row grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input type="text" placeholder={t('admin.dict.status2') || 'Status'} disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 focus:outline-none bg-slate-50 cursor-not-allowed" />
          <input type="date" value={f.dateFrom} onChange={e => setF({ ...f, dateFrom: e.target.value })} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white" />
          <input type="date" value={f.dateTo} onChange={e => setF({ ...f, dateTo: e.target.value })} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          <input type="text" placeholder={t('admin.dict.contragent')} disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 bg-slate-50 cursor-not-allowed" />
          <span className="text-slate-300 text-lg">+</span>
          <input type="text" placeholder={t('admin.dict.employee') || 'Xodim'} disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 bg-slate-50 cursor-not-allowed" />
          <div className="relative">
            <input type="text" value={f.userQ || ''} placeholder={t('admin.dict.user') || 'Foydalanuvchi'}
              onChange={e => setF({ ...f, userQ: e.target.value, user_id: '' })}
              onFocus={() => setF(p => ({ ...p, _usOpen: true }))}
              onBlur={() => setTimeout(() => setF(p => ({ ...p, _usOpen: false })), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users?.filter(u => matchesSearch(u.name, f.userQ || '')).slice(0, 10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({ ...f, user_id: String(u.id), userQ: u.name, _usOpen: false })}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{u.name}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {movLoad ? (
          <div className="py-16 text-center"><div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto" /></div>
        ) : movements.length === 0 ? (
          <div className="text-center py-20 text-slate-400 text-sm">{t('ops.noChiqims')}</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-100">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">{t('ops.docNumber')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.date') || 'Sana'}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">{t('movements.warehouse')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">{t('ops.reason')}</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-slate-500 uppercase">{t('ops.composition')}</th>
                <th className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {movements.map(m => {
                const types = m.type_hints.filter(Boolean);
                const firstType = CHIQIM_TYPES.find(ct => types.includes(ct.v) || types.includes(ct.l));
                const firstTypeLabel = firstType ? t(firstType.l) : (types[0] || t('pay.mixed'));

                return (
                  <tr key={m.reference_id} className="hover:bg-slate-50 relative group">
                    <td className="px-6 py-4 font-semibold text-slate-800">{t('ops.chiqim').toUpperCase()} #{m.reference_id}</td>
                    <td className="px-6 py-4 text-slate-500">{fmtDt(m.created_at)}</td>
                    <td className="px-6 py-4 text-slate-500 text-xs whitespace-nowrap">{m.warehouse_name || '—'}</td>
                    <td className="px-6 py-4">
                      {firstTypeLabel && <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 mb-1">{firstTypeLabel.split('—')[0].trim()}</span>}
                      {m.doc_nums.length > 0 && <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-600 mb-1 ml-1">{t('ops.docNumber')}: {m.doc_nums[0]}</span>}
                      <div className="text-xs text-slate-500 line-clamp-1">{m.reasons.join(', ') || '—'}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col items-center justify-center">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-bold text-xs border border-blue-100/50">
                          <svg className="w-3.5 h-3.5 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
                          {m.item_count} {t('ops.kindsShort')}
                        </span>
                        <div className="text-[11px] text-slate-400 font-medium mt-1">{t('common.total')}: <span className="text-slate-600 font-bold">{fmt(m.total_qty)} {t('common.piece')}</span></div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openDetail(m.reference_id)} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg transition-colors border border-blue-100/50">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                          {t('common.view')}
                        </button>
                        <button onClick={async () => {
                          try {
                            const r = await api.get(`/inventory/chiqims/${m.reference_id}`);
                            setEditingData({ id: m.reference_id, items: r.data });
                            setMode('create');
                          } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
                        }} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-amber-50 text-amber-600 hover:bg-amber-100 rounded-lg transition-colors border border-amber-100/50">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                          {t('common.edit')}
                        </button>
                        <button onClick={() => deleteChiqim(m.reference_id)} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors border border-red-100/50">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          {t('common.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {detailId && (
        <div className="fixed inset-0 z-[60] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl flex flex-col max-h-screen overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-bold text-lg text-slate-800">{t('ops.chiqimDetails')} #{detailId}</h3>
              <button onClick={() => setDetailId(null)} className="text-slate-400 hover:text-slate-600"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg></button>
            </div>
            <div className="p-6 overflow-y-auto">
              {loadingDetail ? (
                <div className="py-10 text-center"><div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto" /></div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('admin.dict.product') || 'Mahsulot'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('ops.reason')}</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500">{t('admin.dict.qty') || 'Miqdor'}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {detailItems.map(item => {
                      const ct = CHIQIM_TYPES.find(x => item.type === x.v || item.type === x.l);
                      const ctLabel = ct ? t(ct.l) : item.type;
                      return (
                        <tr key={item.id}>
                          <td className="px-4 py-3 font-semibold text-slate-800">{item.product_name}</td>
                          <td className="px-4 py-3 text-slate-500 text-xs">
                            <div className="font-medium text-slate-700">{ctLabel.split('—')[0]}</div>
                            {item.doc_num && <div>{t('ops.docNumber')}: {item.doc_num}</div>}
                            {item.reason && <div>{item.reason}</div>}
                          </td>
                          <td className="px-4 py-3 text-right font-bold text-red-500">−{fmt(item.quantity)} {item.product_unit}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
              <button onClick={startEdit} className="px-4 py-2 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg">{t('common.edit')}</button>
              <button onClick={() => setDetailId(null)} className="px-4 py-2 text-sm font-bold text-white bg-slate-800 hover:bg-slate-700 rounded-lg">{t('admin.dict.close') || 'Yopish'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MAIN
══════════════════════════════════════════════════════════ */
/* ─── T4.4: To'ldirish — ombor bo'yicha min/max va markazdan to'ldirish tavsiyasi ─── */
function ToldirishTab({ warehouses = [], allWarehouses = null }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const srcOptions = allWarehouses || warehouses;
  const [whId, setWhId] = useState('');
  const [srcId, setSrcId] = useState('');
  const [search, setSearch] = useState('');
  const [skip, setSkip] = useState(0);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [edits, setEdits] = useState({}); // product_id -> { min_qty, max_qty, reorder_qty, source_warehouse_id }
  const [saving, setSaving] = useState(false);
  const [recs, setRecs] = useState([]);
  const [recLoading, setRecLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const LIMIT = 50;

  useEffect(() => {
    if (!whId && warehouses.length) setWhId(String(warehouses[0].id));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouses]);

  const loadRows = useCallback(async () => {
    if (!whId) return;
    setLoading(true);
    try {
      const params = { warehouse_id: whId, skip, limit: LIMIT };
      if (search.trim()) params.search = search.trim();
      const r = await api.get('/inventory/stock-settings', { params });
      setRows(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [whId, search, skip]);

  useEffect(() => {
    const h = setTimeout(loadRows, 300);
    return () => clearTimeout(h);
  }, [loadRows]);

  const loadRecs = useCallback(async () => {
    setRecLoading(true);
    try {
      const params = {};
      if (whId) params.warehouse_id = whId;
      if (srcId) params.source_warehouse_id = srcId;
      const r = await api.get('/inventory/replenishment', { params });
      setRecs(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
    } finally { setRecLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [whId, srcId]);

  useEffect(() => { loadRecs(); }, [loadRecs]);
  useEffect(() => { setEdits({}); setSkip(0); }, [whId]);

  const val = (row, f) => {
    const e = edits[row.product_id];
    if (e && f in e) return e[f];
    const v = row[f];
    return v === null || v === undefined ? '' : v;
  };
  const setEdit = (pid, f, v) => setEdits(p => ({ ...p, [pid]: { ...(p[pid] || {}), [f]: v } }));
  const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));

  const save = async () => {
    const items = Object.entries(edits).map(([pid, e]) => {
      const it = { product_id: Number(pid) };
      ['min_qty', 'max_qty', 'reorder_qty'].forEach(f => { if (f in e) it[f] = num(e[f]); });
      if ('source_warehouse_id' in e) it.source_warehouse_id = e.source_warehouse_id ? Number(e.source_warehouse_id) : null;
      return it;
    });
    if (!items.length) { toast(tf('replen.nothingToSave', "O'zgarish yo'q")); return; }
    setSaving(true);
    try {
      const r = await api.put('/inventory/stock-settings/bulk', { warehouse_id: Number(whId), items });
      const { saved, errors } = r.data;
      if (errors?.length) toast.error(`${tf('replen.savedErrors', 'Xatolar')}: ${errors.length} — ${errors[0].error}`);
      if (saved) toast.success(`${tf('replen.saved', 'Saqlandi')}: ${saved}`);
      setEdits({});
      await loadRows();
      await loadRecs();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
    } finally { setSaving(false); }
  };

  const createDrafts = async () => {
    const groups = {};
    recs.filter(r => r.transfer_qty > 0 && r.source_warehouse_id).forEach(r => {
      const k = `${r.source_warehouse_id}-${r.warehouse_id}`;
      (groups[k] = groups[k] || { source: r.source_warehouse_id, dest: r.warehouse_id, items: [] })
        .items.push({ product_id: r.product_id, qty: r.transfer_qty });
    });
    const list = Object.values(groups);
    if (!list.length) { toast(tf('replen.draftsNone', "Transfer uchun qator yo'q (manba ombor tanlang)")); return; }
    setCreating(true);
    let ok = 0;
    for (const g of list) {
      try {
        await api.post('/inventory/replenishment/transfers', {
          source_warehouse_id: g.source, destination_warehouse_id: g.dest, items: g.items,
        });
        ok += 1;
      } catch (err) {
        toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
      }
    }
    setCreating(false);
    if (ok) toast.success(`${tf('replen.draftsCreated', 'Transfer qoralamalari yaratildi')}: ${ok}`);
  };

  const inp = 'w-24 border border-slate-200 rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500';
  const whName = (id) => (srcOptions.find(w => w.id === id) || {}).name || '—';

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4">
        <div>
          <h3 className="text-base font-bold text-slate-800">{tf('replen.title', "Ombor bo'yicha min/max qoldiq")}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{tf('replen.hint', "Bo'sh qoldirilsa mahsulotning umumiy min/max qiymati ishlatiladi")}</p>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <Lbl t={tf('replen.warehouse', 'Ombor')}>
            <select className={ic} value={whId} onChange={e => setWhId(e.target.value)}>
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </Lbl>
          <Lbl t={tf('replen.search', 'Qidirish')}>
            <input className={ic} value={search} onChange={e => { setSearch(e.target.value); setSkip(0); }} placeholder={tf('replen.searchPh', 'Nomi, SKU, shtrix-kod')} />
          </Lbl>
          <Btn onClick={save} disabled={saving || !Object.keys(edits).length}>{saving ? t('common.loading') : tf('replen.save', 'Saqlash')}</Btn>
        </div>
        <Tbl loading={loading} rows={rows} skip={skip} limit={LIMIT} onChange={setSkip} cols={[
          { k: 'product_name', l: tf('replen.product', 'Mahsulot') },
          { k: 'current_qty', l: tf('replen.current', 'Qoldiq'), r: v => Number(v ?? 0).toLocaleString('uz-UZ') },
          { k: 'company_min_stock', l: tf('replen.companyMin', 'Umumiy min / max'), r: (v, r) => `${v ?? 0}${r.company_max_stock != null ? ` / ${r.company_max_stock}` : ''}` },
          { k: 'min_qty', l: t('ombor.min'), r: (v, r) => <input type="number" min="0" className={inp} value={val(r, 'min_qty')} onChange={e => setEdit(r.product_id, 'min_qty', e.target.value)} /> },
          { k: 'max_qty', l: tf('ombor.max', 'Max'), r: (v, r) => <input type="number" min="0" className={inp} value={val(r, 'max_qty')} onChange={e => setEdit(r.product_id, 'max_qty', e.target.value)} /> },
          { k: 'reorder_qty', l: tf('replen.reorder', "To'ldirish miqdori"), r: (v, r) => <input type="number" min="0" className={inp} value={val(r, 'reorder_qty')} onChange={e => setEdit(r.product_id, 'reorder_qty', e.target.value)} /> },
          { k: 'source_warehouse_id', l: tf('replen.source', 'Manba ombor'), r: (v, r) => (
            <select className={`${ic} !py-1 !px-2`} value={val(r, 'source_warehouse_id')} onChange={e => setEdit(r.product_id, 'source_warehouse_id', e.target.value)}>
              <option value="">—</option>
              {srcOptions.filter(w => String(w.id) !== String(whId)).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          ) },
        ]} />
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-slate-800">{tf('replen.recommendations', "To'ldirish tavsiyalari")}</h3>
            <p className="text-xs text-slate-400 mt-0.5">{tf('replen.recHint', "Manba ombor o'z minimumidan pastga tushirilmaydi; yetmagan qismi xarid uchun")}</p>
          </div>
          <div className="flex flex-wrap gap-3 items-end">
            <Lbl t={tf('replen.defaultSource', 'Standart manba (markaz)')}>
              <select className={ic} value={srcId} onChange={e => setSrcId(e.target.value)}>
                <option value="">—</option>
                {srcOptions.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </Lbl>
            <Btn v="green" onClick={createDrafts} disabled={creating || !recs.some(r => r.transfer_qty > 0)}>
              {creating ? t('common.loading') : tf('replen.createDrafts', 'Transfer qoralamalarini yaratish')}
            </Btn>
          </div>
        </div>
        <Tbl loading={recLoading} rows={recs} cols={[
          { k: 'warehouse_name', l: tf('replen.warehouse', 'Ombor') },
          { k: 'product_name', l: tf('replen.product', 'Mahsulot') },
          { k: 'current_qty', l: tf('replen.current', 'Qoldiq') },
          { k: 'min', l: t('ombor.min') },
          { k: 'max', l: tf('ombor.max', 'Max') },
          { k: 'need_qty', l: tf('replen.need', 'Kerak') },
          { k: 'source_warehouse_id', l: tf('replen.source', 'Manba ombor'), r: (v) => (v ? whName(v) : '—') },
          { k: 'transfer_qty', l: tf('replen.transfer', 'Transfer'), r: v => <b className="text-emerald-700">{v}</b> },
          { k: 'purchase_needed', l: tf('replen.purchase', 'Xarid kerak'), r: v => <b className={v > 0 ? 'text-red-600' : 'text-slate-400'}>{v}</b> },
        ]} />
      </div>
    </div>
  );
}

function getOpsTabs(t) {
  return [
    {
      id: 'qaytarishlar', label: t('ops.tab.returns'),
      icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>,
    },
    {
      id: 'transferlar', label: t('ops.tab.transfers'),
      icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>,
    },
    {
      id: 'toldirish', label: (() => { const v = t('replen.tab'); return v === 'replen.tab' ? "To'ldirish" : v; })(),
      icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M4 7c0-2 1-3 3-3h10c2 0 3 1 3 3M4 7h16M10 12h4" /></svg>,
    },
    {
      id: 'reviziyalar', label: t('ops.tab.revisions'),
      icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
    },
    {
      id: 'chiqimlar', label: t('ops.tab.expenses'),
      icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>,
    },
  ];
}

export default function Operations() {
  const { t } = useLang();
  const [tab, setTab] = useState('qaytarishlar');
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  // T1.3: transfer maqsadi va filtrlari uchun — korxonaning barcha filiallari omborlari (scope=all)
  const [allWarehouses, setAllWarehouses] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [users, setUsers] = useState([]);
  const productsLoaded = useRef(false);
  const suppliersLoaded = useRef(false);

  useEffect(() => {
    api.get('/inventory/warehouses', { params: { scope: 'all' } }).then(r => setAllWarehouses(r.data)).catch(() => {});
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred')) });
    api.get('/users/').then(r => setUsers(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred')) });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // T3.8: mahsulotlar faqat ularni ishlatadigan tab (qaytarishlar, chiqimlar) ochilganda yuklanadi;
  // yengil /products/pos-list (3-5 marta kichik javob), 5000 talik sahifalar bilan
  useEffect(() => {
    if (!['qaytarishlar', 'chiqimlar'].includes(tab) || productsLoaded.current) return;
    productsLoaded.current = true;
    (async () => {
      try {
        const all = [];
        const PAGE = 5000;
        for (let skip = 0; skip < 15000; skip += PAGE) {
          const r = await api.get('/products/pos-list', { params: { limit: PAGE, skip } });
          const rows = Array.isArray(r.data) ? r.data : (r.data.items || []);
          all.push(...rows);
          if (rows.length < PAGE) break;
        }
        setProducts(all);
      } catch (err) {
        productsLoaded.current = false;
        toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Ta'minotchilar faqat "Qaytarishlar" tabiga kerak (mijozlar CustomerPicker orqali serverda qidiriladi)
  useEffect(() => {
    if (tab !== 'qaytarishlar' || suppliersLoaded.current) return;
    suppliersLoaded.current = true;
    api.get('/suppliers', { params: { limit: 5000 } }).then(r => setSuppliers(r.data)).catch((err) => {
      suppliersLoaded.current = false;
      toast.error(err.response?.data?.detail || err.message || t('ops.errorOccurred'));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const TABS = getOpsTabs(t);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('ops.title')}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{t('ops.subtitle')}</p>
        </div>
      </div>

      <div className="flex gap-1 bg-white border border-slate-200 rounded-2xl p-1.5 overflow-x-auto shadow-sm">
        {TABS.map(tab_item => (
          <button key={tab_item.id} onClick={() => setTab(tab_item.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold whitespace-nowrap transition-all ${tab === tab_item.id
              ? 'bg-blue-600 text-white shadow-md shadow-blue-200'
              : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}>
            {tab_item.icon}<span>{tab_item.label}</span>
          </button>
        ))}
      </div>

      {['qaytarishlar', 'transferlar', 'reviziyalar', 'chiqimlar'].includes(tab) && (
        <div className="text-xs font-medium text-amber-700 bg-amber-50 px-3 py-1.5 rounded-lg inline-block">
          {(() => { const v = t('reports.companyWide'); return v === 'reports.companyWide' ? "Butun korxona bo'yicha (filial filtri qo'llanmaydi)" : v; })()}
        </div>
      )}

      {tab === 'qaytarishlar' && <QaytarishlarTab products={products} suppliers={suppliers} warehouses={warehouses} />}
      {tab === 'transferlar' && <TransferlarTab warehouses={warehouses} allWarehouses={allWarehouses} users={users} />}
      {tab === 'toldirish' && <ToldirishTab warehouses={warehouses} allWarehouses={allWarehouses} />}
      {tab === 'reviziyalar' && <ReviziyalarTab warehouses={warehouses} />}
      {tab === 'chiqimlar' && <ChiqimlarTab products={products} users={users} warehouses={warehouses} />}
    </div>
  );
}

