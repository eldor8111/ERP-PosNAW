import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLang } from '../../context/LangContext';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import api from '../../api/axios';
import { matchesSearch, searchVariants } from '../../utils/translit';
import toast from 'react-hot-toast';
import { CircleArrowDown, PackageCheck, Plus, Minus } from 'lucide-react';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/react';
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtDay = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
// Server xatosi matni (axios interceptor toast ko'rsatadi, bu — formadagi yozuv uchun)
const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map(x => x?.msg || JSON.stringify(x)).join('; ');
  return fallback || e?.message || 'Error';
};

// Xarid to'lovi turlari (kassa yopilishidagi to'lov turlari bilan bir xil kalitlar)
const PO_PAY_TYPES = [
  { key: 'cash', lKey: 'pay.cash' },
  { key: 'card', lKey: 'pay.card' },
  { key: 'uzcard', label: 'Uzcard' },
  { key: 'humo', label: 'Humo' },
  { key: 'transfer', lKey: 'purchase.bankTransfer' },
  { key: 'click', label: 'Click' },
  { key: 'payme', label: 'Payme' },
];

const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white transition-colors hover:border-slate-300';

const poMeta = {
  draft: { lKey: 'purchase.statusDraft', c: 'bg-slate-100 text-slate-600' },
  sent: { lKey: 'purchase.statusOrdered', c: 'bg-blue-100 text-blue-700' },
  partial: { lKey: 'purchase.statusPartial', c: 'bg-amber-100 text-amber-700' },
  received: { lKey: 'purchase.statusReceived', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { lKey: 'common.cancel', c: 'bg-red-100 text-red-500' },
};

function Badge({ meta, val }) {
  const { t } = useLang();
  const m = meta[val] || { c: 'bg-slate-100 text-slate-600' };
  const label = m.lKey ? t(m.lKey) || m.l || val : m.l || val;
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${m.c}`}>{label}</span>;
}
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

/* ─── Page header (list mode) ─── */
function ListHeader({ btn, btnLabel, children }) {
  const { t } = useLang();
  return (
    <div className="flex flex-wrap items-end gap-3 mb-4">
      {children}
      <div className="ml-auto">
        <Btn onClick={btn}>+ {btnLabel}</Btn>
      </div>
    </div>
  );
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
        {t('purchase.back')}
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
        {count === 0 ? t('purchase.noResults') : `${skip + 1}–${skip + count} ${t('purchase.shownCount')}`}
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
function ProdSearch({ products, onSelect, inputRef, placeholder }) {
  const { t } = useLang();
  placeholder = placeholder || t('purchase.searchProductPlaceholder');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [navIdx, setNavIdx] = useState(-1);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }

    // 1. Tezkor lokal qidiruv
    const localMatches = products.filter(p =>
      matchesSearch(p.name, q) ||
      matchesSearch(p.sku, q) ||
      (p.barcode && p.barcode.includes(q))
    ).slice(0, 15);
    setResults(localMatches);

    // 2. Orqa fonda serverdan qidirish (chunki limit 1000 sababli baza to'liq kelmagan bo'lishi mumkin)
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const variants = searchVariants(q);
        const reqs = variants.map(v => api.get('/products/', { params: { search: v, limit: 15, status: 'active' } }).catch(() => ({ data: [] })));
        const resps = await Promise.all(reqs);
        const seen = new Set(localMatches.map(p => p.id));
        const merged = [...localMatches];
        for (const r of resps) {
          const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
          for (const item of items) {
            if (!seen.has(item.id)) { seen.add(item.id); merged.push(item); }
          }
        }
        setResults(merged.slice(0, 15));
      } catch (err) {
        // ignore
      } finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [q, products]);

  const displayList = q.trim() ? results : products.slice(0, 15);

  const handleKeyDown = (e) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setNavIdx(prev => (prev < displayList.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setNavIdx(prev => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (navIdx >= 0 && navIdx < displayList.length) {
        onSelect(displayList[navIdx]);
        setQ(''); setOpen(false); setNavIdx(-1);
      } else if (displayList.length > 0) {
        onSelect(displayList[0]);
        setQ(''); setOpen(false); setNavIdx(-1);
      }
    }
  };

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setNavIdx(-1), [q, open]);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className={`flex items-center gap-2 border border-slate-200 rounded-xl px-3.5 py-2 bg-white transition-all ${open ? 'border-blue-400 ring-2 ring-blue-50' : 'hover:border-slate-300'}`}>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          ref={inputRef}
          placeholder={placeholder}
          className="w-full text-sm outline-none bg-transparent" />
        {loading && <div className="w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />}
      </div>
      {open && displayList.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {displayList.map((p, i) => (
            <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
              className={`w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3 ${navIdx === i ? 'bg-blue-50' : ''}`}>
              <div className="min-w-0">
                <div className="font-medium text-slate-800 text-sm truncate">{p.name}</div>
                <div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
              </div>
              <div className="text-right shrink-0 text-xs">
                <div className="font-semibold text-blue-600">{fmt(p.sale_price)} {t('purchase.somUnit')}</div>
                {p.wholesale_price > 0 && <div className="text-amber-600">{t('purchase.wholesaleShort')}: {fmt(p.wholesale_price)}</div>}
                <div className="text-slate-400">{t('purchase.stockLabel')} {fmt(p.stock_quantity)}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Supplier search combobox ─── */
function SupSearch({ suppliers, value, onChange, placeholder }) {
  const { t } = useLang();
  placeholder = placeholder || t('purchase.selectSupplierPlaceholder');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = suppliers.find(s => String(s.id) === String(value));

  const filtered = q.trim()
    ? suppliers.filter(s =>
      matchesSearch(s.name, q) ||
      (s.phone && s.phone.includes(q))
    ).slice(0, 12)
    : suppliers.slice(0, 12);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const pick = (s) => { onChange(s ? s.id : ''); setQ(''); setOpen(false); };

  return (
    <div className="relative" ref={ref}>
      <div className={`flex items-center border rounded-xl bg-white overflow-hidden focus-within:ring-2 focus-within:ring-blue-500 transition-colors ${selected ? 'border-blue-300' : 'border-slate-200'}`}>
        <svg className="w-4 h-4 ml-3 shrink-0 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
        <input
          value={open ? q : (selected ? selected.name : '')}
          onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="flex-1 px-3 py-2 text-sm outline-none bg-transparent min-w-0"
        />
        {selected && (
          <button onMouseDown={() => pick(null)} className="px-2 text-slate-400 hover:text-red-400 text-xl leading-none">×</button>
        )}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400">{t('purchase.notFound')}</div>
          ) : filtered.map(s => (
            <button key={s.id} onMouseDown={() => pick(s)}
              className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-slate-50 last:border-0">
              <div className="text-sm font-medium text-slate-800">{s.name}</div>
              {s.phone && <div className="text-xs text-slate-400">{s.phone}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   KIRIM CREATE VIEW — split panel
══════════════════════════════════════════════════════════ */
function KirimCreateView({ onBack, onSaved, editPo = null }) {
  const { t } = useLang();
  const [products, setProds] = useState([]);
  const [warehouses, setWhs] = useState([]);
  const [suppliers, setSups] = useState([]);
  const [wallets, setWallets] = useState([]);
  const [currencies, setCurrencies] = useState([{ code: 'UZS', rate: 1 }]);
  const [currenciesLoaded, setCurrenciesLoaded] = useState(false);
  const [productsLoaded, setProductsLoaded] = useState(false);

  useEffect(() => {
    api.get('/products/', { params: { limit: 1000, status: 'active' } })
      .then(r => setProds(Array.isArray(r.data) ? r.data : (r.data.items || []))).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('auth.errGeneral')) })
      .finally(() => setProductsLoaded(true));
    api.get('/inventory/warehouses').then(r => setWhs(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('auth.errGeneral')) });
    api.get('/suppliers', { params: { limit: 5000 } }).then(r => setSups(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('auth.errGeneral')) });
    api.get('/finance/wallets').then(r => { setWallets(r.data); if (r.data.length > 0) setPayForm(p => ({ ...p, wallet_id: r.data[0].id })); }).catch(console.error);
    api.get('/currencies/active').then(r => {
      const list = Array.isArray(r.data) ? r.data : [];
      if (!list.find(c => c.code === 'UZS')) list.unshift({ code: 'UZS', rate: 1 });
      setCurrencies(list);
      setCurrenciesLoaded(true);
    }).catch(() => { setCurrenciesLoaded(true); });
  }, []);

  // Valyuta kursi. Tahrirda xarid valyutasi uchun xarid yaratilgandagi kurs ishlatiladi —
  // backend ham qarzni shu kurs bilan hisoblaydi.
  const getRateFor = (code) => {
    if (!code || code === 'UZS') return 1;
    if (editPo && code === editPo.currency && Number(editPo.exchange_rate) > 0) return Number(editPo.exchange_rate);
    const c = currencies.find(c => c.code === code);
    return c ? Number(c.rate || 1) : 1;
  };


  // Pre-populate from editPo when data is loaded
  useEffect(() => {
    if (!editPo || !warehouses.length || !suppliers.length || !productsLoaded) return;
    setPoForm({
      supplier_id: String(editPo.supplier_id || ''),
      warehouse_id: String(editPo.warehouse_id || ''),
      note: editPo.note || '',
      expected_date: editPo.expected_date ? String(editPo.expected_date).slice(0, 10) : '',
    });
    if (editPo.items && editPo.items.length > 0) {
      // Bazada unit_cost — UZS (sof). Valyutali qator narxi xarid kursida valyutaga qaytariladi
      // (avval hammasi UZS deb ochilib, qayta saqlashda xarid valyutasi yo'qolardi).
      setPoItems(editPo.items.map(item => {
        const cur = item.cost_currency || 'UZS';
        const netUzs = Number(item.unit_cost);
        const prod = products.find(pr => pr.id === item.product_id);
        return {
          product_id: item.product_id,
          product_name: item.product_name,
          unit: prod?.unit || t('common.piece'),
          category_is_perishable: prod?.category_is_perishable || false,
          expiry_date: item.expiry_date ? String(item.expiry_date).slice(0, 10) : '',
          unit_cost: cur === 'UZS' ? netUzs : Math.round((netUzs / getRateFor(cur)) * 10000) / 10000,
          discount_type: 'pct',
          discount_val: 0,
          currency: cur,
          net_cost: netUzs,
          new_sale_price: item.new_sale_price != null ? Number(item.new_sale_price) : null,
          new_wholesale_price: item.new_wholesale_price != null ? Number(item.new_wholesale_price) : null,
          orig_sale_price: prod ? Number(prod.sale_price || 0) : null,
          orig_wholesale_price: prod ? Number(prod.wholesale_price || 0) : null,
          qty_ordered: Number(item.qty_ordered),
        };
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editPo, warehouses, suppliers, productsLoaded]);

  // PO form
  const [poForm, setPoForm] = useState({ supplier_id: '', warehouse_id: '', note: '', expected_date: '' });
  const [poItems, setPoItems] = useState([]);
  const [variantPickerProduct, setVariantPickerProduct] = useState(null);

  // Auto-update price flags
  const [autoRetail, setAutoRet] = useState(false);
  const [autoWholesale, setAutoWho] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // Left panel: selected product + input fields
  const searchRef = useRef(null);
  const qtyRef = useRef(null);
  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('');
  const [cost, setCost] = useState('');
  const [newSalePrice, setNewSalePrice] = useState('');
  const [newWholesalePrice, setNewWholesalePrice] = useState('');
  const [discType, setDiscType] = useState('pct');  // 'pct' | 'amt'
  const [discVal, setDiscVal] = useState('0');
  const [currency, setCurrency] = useState('UZS');
  const [expiryDate, setExpiryDate] = useState('');

  const selectProduct = (p) => {
    if (p.product_type === 'parent') {
      setVariantPickerProduct(p);
      return;
    }
    setSel(p);
    const prodCur = p.cost_currency || 'UZS';
    const prodPrice = Number(p.cost_price) > 0 ? p.cost_price : (Number(p.sale_price) > 0 ? p.sale_price : '');
    setCurrency(prodCur);
    setCost(prodPrice ? String(Number(prodPrice)) : '');
    setNewSalePrice(p.sale_price ? String(Math.round(p.sale_price)) : '');
    setNewWholesalePrice(p.wholesale_price ? String(Math.round(p.wholesale_price)) : '');
    setQty(''); setDiscVal('0'); setDiscType('pct'); setExpiryDate('');
    setTimeout(() => { if (qtyRef.current) qtyRef.current.focus(); }, 10);
  };

  // Net cost per unit in UZS using real currency rate
  const calcNet = (rawCost, dType, dVal, cur) => {
    const c = Number(rawCost) || 0;
    const d = Number(dVal) || 0;
    const net = dType === 'pct' ? c * (1 - d / 100) : c - d;
    const rate = getRateFor(cur);
    return cur === 'UZS' ? net : net * rate;
  };
  const selNet = calcNet(cost, discType, discVal, currency);


  const addItem = () => {
    if (!sel || !qty) return;
    const base = {
      product_id: sel.id, product_name: sel.name, unit: sel.unit || t('common.piece'),
      category_is_perishable: sel.category_is_perishable || false,
      expiry_date: expiryDate || '',
      unit_cost: Number(cost) || 0, discount_type: discType, discount_val: Number(discVal) || 0,
      currency, net_cost: selNet,
      new_sale_price: newSalePrice ? Number(newSalePrice) : null,
      new_wholesale_price: newWholesalePrice ? Number(newWholesalePrice) : null,
      orig_sale_price: Number(sel.sale_price || 0),
      orig_wholesale_price: Number(sel.wholesale_price || 0),
    };


    setPoItems(prev => {
      const ex = prev.find(x => x.product_id === sel.id);
      if (ex) return prev.map(x => x.product_id === sel.id ? { ...x, qty_ordered: x.qty_ordered + Number(qty) } : x);
      return [...prev, { ...base, qty_ordered: Number(qty) }];
    });
    setSel(null); setQty(''); setCost(''); setDiscVal('0'); setExpiryDate('');
    setTimeout(() => { if (searchRef.current) searchRef.current.focus(); }, 10);
  };

  const updPoItem = (i, field, val) => setPoItems(prev => prev.map((x, idx) => {
    if (idx !== i) return x;
    const updated = { ...x, [field]: val };
    if (field === 'currency' && x.currency !== val) {
      const oldRate = getRateFor(x.currency);
      const newRate = getRateFor(val);
      if (x.unit_cost && Number(x.unit_cost) > 0) {
        const inUzs = Number(x.unit_cost) * oldRate;
        updated.unit_cost = Math.round((inUzs / newRate) * 100) / 100;
      }
    }
    updated.net_cost = calcNet(
      field === 'unit_cost' ? val : updated.unit_cost,
      field === 'discount_type' ? val : updated.discount_type,
      field === 'discount_val' ? val : updated.discount_val,
      field === 'currency' ? val : updated.currency
    );
    return updated;
  }));


  const activeItems = poItems;
  const totalNet = activeItems.reduce((s, i) => s + i.qty_ordered * (i.net_cost || 0), 0);
  // ✅ O'RTA-3 TUZATILDI: faqat USD emas, barcha chet el valyutalar
  const hasCurrency = activeItems.some(i => i.currency && i.currency !== 'UZS');

  const [showPay, setShowPay] = useState(false);
  const [payForm, setPayForm] = useState({ discType: 'amt', discVal: '', cash: '', info: '', wallet_id: '', currency: 'UZS', payment_type: 'cash' });

  const handleOpenPay = () => {
    if (!poForm.supplier_id || !poForm.warehouse_id || !poItems.length) {
      setErr(t('purchase.fillRequiredFieldsDetailed'));
      return;
    }
    setErr('');
    const activeCur = (poItems.length > 0 && poItems[poItems.length - 1].currency) ? poItems[poItems.length - 1].currency : (currency || 'UZS');
    const rate = getRateFor(activeCur);
    const totalInCur = activeCur === 'UZS' ? Math.round(totalNet) : Math.round((totalNet / rate) * 100) / 100;

    setPayForm(p => ({
      ...p,
      currency: activeCur,
      discType: 'amt',
      discVal: '',
      cash: String(totalInCur),
      info: p.info || '',
    }));
    setShowPay(true);
  };

  const payCur = payForm.currency || 'UZS';
  const payCurRate = getRateFor(payCur);

  const calcPayModalTotals = () => {
    const dVal = Number(payForm.discVal) || 0;
    const discInUzs = payForm.discType === 'pct' ? totalNet * (dVal / 100) : dVal * payCurRate;
    const finalTotalUzs = Math.max(0, totalNet - discInUzs);
    const finalTotalInPayCur = payCur === 'UZS' ? finalTotalUzs : finalTotalUzs / payCurRate;

    const paidInPayCur = Number(payForm.cash) || 0;
    const paidInUzs = paidInPayCur * payCurRate;

    const debtUzs = Math.max(0, finalTotalUzs - paidInUzs);
    const changeUzs = Math.max(0, paidInUzs - finalTotalUzs);

    return {
      discInUzs,
      finalTotalUzs,
      finalTotalInPayCur: Math.round(finalTotalInPayCur * 100) / 100,
      paidInUzs,
      paidInPayCur,
      debtUzs: Math.round(debtUzs),
      changeUzs: Math.round(changeUzs),
      debtInPayCur: payCur === 'UZS' ? Math.round(debtUzs) : Math.round((debtUzs / payCurRate) * 100) / 100,
      changeInPayCur: payCur === 'UZS' ? Math.round(changeUzs) : Math.round((changeUzs / payCurRate) * 100) / 100,
    };
  };

  const payTotals = calcPayModalTotals();

  const handlePayCurrencyChange = (newCur) => {
    const oldCur = payForm.currency || 'UZS';
    if (oldCur === newCur) return;
    const oldRate = getRateFor(oldCur);
    const newRate = getRateFor(newCur);
    let newCash = payForm.cash;
    if (newCash && Number(newCash) > 0) {
      const inUzs = Number(newCash) * oldRate;
      newCash = String(Math.round((inUzs / newRate) * 100) / 100);
    }
    setPayForm(p => ({ ...p, currency: newCur, cash: newCash }));
  };

  // Sotuv narxi faqat foydalanuvchi o'zgartirgan yoki "Narxlarni yangilash" yoqilgan bo'lsa yuboriladi
  // (avval har doim yuborilib, qabulda mahsulot narxi keraksiz qayta yozilardi).
  const priceIfChanged = (val, orig, force) => {
    if (val == null || val === '' || !(Number(val) > 0)) return null;
    return (force || orig == null || Number(val) !== Number(orig)) ? Number(val) : null;
  };

  const savePo = async (status = 'draft', paymentInfo = null) => {
    if (!poForm.supplier_id || !poForm.warehouse_id || !poItems.length) { setErr(t('purchase.fillRequiredFields')); return; }
    // Perishable mahsulotlarda muddatni tekshirish
    const missingExpiry = poItems.filter(i => i.category_is_perishable && !i.expiry_date);
    if (missingExpiry.length > 0) {
      setErr(`"${missingExpiry.map(i => i.product_name).join(', ')}" ${t('purchase.enterExpiryFor')}`);
      return;
    }
    if (poItems.some(i => !(Number(i.qty_ordered) > 0))) { setErr(t('purchase.qtyMustBePositive')); return; }
    if (saving) return;
    setSaving(true); setErr('');

    // PO ning asosiy valyutasi: qatorlardagi birinchi non-UZS valyuta
    const activeCurrency = poItems.find(i => i.currency && i.currency !== 'UZS')?.currency
      || (poItems.length > 0 ? (poItems[0].currency || 'UZS') : 'UZS');
    const payload = {
      supplier_id: Number(poForm.supplier_id), warehouse_id: Number(poForm.warehouse_id),
      ...(editPo ? {} : { status }),
      note: poForm.note || null, expected_date: poForm.expected_date || null,
      currency: activeCurrency,
      items: poItems.map(i => ({
        product_id: i.product_id,
        qty_ordered: i.qty_ordered,
        unit_cost: i.net_cost,
        cost_currency: i.currency || 'UZS',
        original_unit_cost: i.currency && i.currency !== 'UZS' ? (Number(i.unit_cost) || 0) : (i.net_cost || 0),
        new_sale_price: priceIfChanged(i.new_sale_price, i.orig_sale_price, autoRetail),
        new_wholesale_price: priceIfChanged(i.new_wholesale_price, i.orig_wholesale_price, autoWholesale),
        expiry_date: i.expiry_date || null
      })),
    };

    if (paymentInfo) {
      // paid_amount — UZS (qarz hisobi), payment_amount/payment_currency — kassadan chiqqan haqiqiy pul
      payload.paid_amount = Math.max(0, Math.round(paymentInfo.paid * 100) / 100);
      payload.discount_amount = Math.max(0, totalNet - payTotals.finalTotalUzs);
      payload.payment_type = paymentInfo.payment_type || 'cash';
      payload.payment_currency = paymentInfo.currency || 'UZS';
      payload.payment_amount = Math.max(0, paymentInfo.amount || 0);
      if (paymentInfo.wallet_id) payload.wallet_id = Number(paymentInfo.wallet_id);
      if (paymentInfo.info) payload.note = (payload.note ? payload.note + '\n' : '') + paymentInfo.info;
    }

    // Javob kutiladi: xato bo'lsa forma yopilmaydi va kiritilgan ma'lumot yo'qolmaydi
    // (avval darrov chiqib ketilar, xato faqat konsolga yozilardi).
    try {
      if (editPo) await api.patch(`/purchase-orders/${editPo.id}`, payload);
      else await api.post('/purchase-orders', payload);
      toast.success(t('purchase.poSaved'));
      setShowPay(false);
      onSaved();
      onBack();
    } catch (e) {
      setErr(errText(e, t('common.error')));
      setShowPay(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <CreateHeader title={editPo ? `${t('purchase.editKirimTitle')} · ${editPo.number}` : t('purchase.newKirimTitle')} onBack={onBack} />

      {/* ── Header fields ── */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-100 bg-white shrink-0 flex-wrap shadow-sm">
        {/* Supplier combobox */}
        <div className="w-64">
          <SupSearch
            suppliers={suppliers}
            value={poForm.supplier_id}
            onChange={v => setPoForm(f => ({ ...f, supplier_id: v }))}
            placeholder={t('purchase.selectSupplier')}
          />
        </div>
        {/* Warehouse */}
        <select
          value={poForm.warehouse_id}
          onChange={e => setPoForm(f => ({ ...f, warehouse_id: e.target.value }))}
          className={`${ic} min-w-40`}>
          <option value="">{t('purchase.selectWarehouse')}</option>
          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <input type="date" value={poForm.expected_date} onChange={e => setPoForm(f => ({ ...f, expected_date: e.target.value }))} className={ic} />

        {/* Currency rates info — shown when non-UZS currencies are in use */}
        {(hasCurrency || (currency && currency !== 'UZS')) && (
          <div className="flex items-center gap-2 flex-wrap">
            {currencies.filter(c => c.code !== 'UZS').map(c => (
              <span key={c.code} className="text-xs text-slate-500 font-semibold bg-slate-100 px-2 py-1 rounded-lg">
                1 {c.code} = {fmt(c.rate)} {t('purchase.somUnit')}
              </span>
            ))}
          </div>
        )}

        <input placeholder={t('admin.dict.comment')} value={poForm.note}
          onChange={e => setPoForm(f => ({ ...f, note: e.target.value }))}
          className={`${ic} flex-1 min-w-32`} />
      </div>

      {/* ── Split body ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div className="w-[500px] border-r border-slate-100 p-6 flex flex-col gap-6 overflow-y-auto shrink-0 bg-white shadow-sm">
          <Lbl t={t('purchase.searchProduct')}>
            <ProdSearch products={products.filter(p => p.product_type !== 'sell')} onSelect={selectProduct} inputRef={searchRef} />
          </Lbl>

          {sel ? (
            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-5 space-y-4">
              {/* Product info */}
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center text-sm font-bold shrink-0 shadow-sm">
                  {sel.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-base truncate">{sel.name}</div>
                  <div className="text-sm text-slate-600 mt-1">
                    {t('purchase.stockLabel')} <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit || t('common.piece')}
                    <span className="mx-2 text-slate-300">|</span>
                    {t('purchase.retailLabel')} <strong className="text-blue-600">{fmt(sel.sale_price)}</strong>
                  </div>
                </div>
              </div>

              {/* Cost price + currency */}
              <div>
                <label className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-2 block">{t('purchase.costPrice')}</label>
                <div className="flex rounded-xl border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-blue-500 shadow-sm">
                  <input type="number" min="0" value={cost} onChange={e => setCost(e.target.value)}
                    className="flex-1 min-w-0 px-4 py-3 text-base font-semibold focus:outline-none bg-transparent rounded-l-xl" />
                  {/* Currency Listbox — outside overflow-hidden so dropdown is not clipped */}
                  <Listbox value={currency} disabled={!currenciesLoaded} onChange={val => {
                    if (cost && Number(cost) > 0) {
                      const oldRate = getRateFor(currency);
                      const newRate = getRateFor(val);
                      if (oldRate > 0 && newRate > 0) {
                        const inUzs = Number(cost) * oldRate;
                        setCost(String(Math.round((inUzs / newRate) * 100) / 100));
                      }
                    }
                    setCurrency(val);
                  }}>
                    <div className="relative border-l border-slate-200">
                      <ListboxButton className="h-full min-w-[90px] rounded-r-xl cursor-pointer flex items-center gap-1.5 pl-3 pr-7 bg-slate-50 hover:bg-slate-100 text-blue-600 font-bold text-sm outline-none transition-colors">
                        <span>{currency}</span>
                        <span className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-slate-400">
                          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor" className="size-3.5"><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" /></svg>
                        </span>
                      </ListboxButton>
                      <ListboxOptions className="absolute z-[100] right-0 top-[calc(100%+4px)] w-44 overflow-auto rounded-xl bg-white border border-slate-200 shadow-2xl outline-none p-1">
                        {currencies.map(c => (
                          <ListboxOption key={c.code} value={c.code}
                            className="group flex items-center justify-between gap-2 py-2 px-3 select-none cursor-pointer rounded-lg text-slate-800 data-focus:bg-slate-100 outline-none transition-colors">
                            <span className="font-semibold text-sm group-data-selected:text-blue-600">{c.code}</span>
                            {c.code !== 'UZS' && (
                              <span className="text-[10px] font-medium text-slate-500">{fmt(c.rate)} {t('purchase.somUnit')}</span>
                            )}
                            <span className="ml-auto text-blue-600 opacity-0 group-data-selected:opacity-100 transition-opacity">
                              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="size-4"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                            </span>
                          </ListboxOption>
                        ))}
                      </ListboxOptions>
                    </div>
                  </Listbox>
                </div>
                {currency !== 'UZS' && (
                  <div className="mt-1.5 text-xs text-slate-400 flex items-center gap-1">
                    <span>1 {currency} = <span className="font-semibold text-slate-500">{fmt(getRateFor(currency))} UZS</span></span>
                    {cost && Number(cost) > 0 && <span className="mx-1 text-slate-300">→</span>}
                    {cost && Number(cost) > 0 && <span className="text-blue-600 font-semibold">{fmt(Math.round(selNet))} UZS</span>}
                  </div>
                )}
              </div>


              {/* Dynamic Price Update Prompt */}
              {sel && cost && Number(cost) !== Number(sel.cost_price || 0) && (
                <div className="mt-3 bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-3 shadow-sm">
                  <p className="text-xs font-bold text-amber-700 uppercase tracking-wide">
                    {t('purchase.priceChanged')}
                  </p>
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div>
                      <label className="text-xs font-bold text-amber-700/70 mb-1.5 block">{t('purchase.newRetailPrice')}</label>
                      <input type="number" value={newSalePrice} onChange={e => setNewSalePrice(e.target.value)} className={`${ic} w-full text-sm py-2 font-semibold`} placeholder={Math.round(sel.sale_price || 0)} />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-amber-700/70 mb-1.5 block">{t('purchase.newWholesalePrice')}</label>
                      <input type="number" value={newWholesalePrice} onChange={e => setNewWholesalePrice(e.target.value)} className={`${ic} w-full text-sm py-2 font-semibold`} placeholder={Math.round(sel.wholesale_price || 0)} />
                    </div>
                  </div>
                </div>
              )}

              {/* Discount */}
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">{t('purchase.discount')}</label>
                <div className="flex rounded-xl border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-blue-500 overflow-hidden">
                  <input type="number" min="0" value={discVal} onChange={e => setDiscVal(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-2 text-sm focus:outline-none bg-transparent" />
                  <div className="flex border-l border-slate-200">
                    {[['pct', '%'], ['amt', t('purchase.somUnit')]].map(([v, l]) => (
                      <button key={v} type="button" onClick={() => setDiscType(v)}
                        className={`px-2.5 py-2 text-xs font-bold transition-colors ${discType === v ? 'bg-amber-500 text-white' : 'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Net cost preview */}
              {(Number(discVal) > 0 || currency === 'USD') && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2 flex justify-between items-center">
                  <span className="text-xs text-emerald-700 font-semibold">{t('purchase.netCost')}</span>
                  <span className="text-sm font-black text-emerald-700">{fmt(Math.round(selNet))} {t('purchase.somUnit')}</span>
                </div>
              )}

              {/* Quantity */}
              <Lbl t={t('admin.dict.qty')}>
                <div className="flex gap-2 items-center">
                  <input type="number" min="1" step="any" value={qty} onChange={e => setQty(e.target.value)}
                    ref={qtyRef}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && qty && Number(qty) > 0) {
                        e.preventDefault();
                        addItem();
                      }
                    }}
                    className={`flex-1 ${ic} text-center font-bold`} />
                  <span className="text-sm text-slate-500 font-medium shrink-0">{sel.unit || t('common.piece')}</span>
                </div>
              </Lbl>

              {/* Expiry Date — faqat perishable mahsulotlar uchun */}
              {sel.category_is_perishable && (
                <Lbl t={`⏰ ${t('purchase.expiryDateRequired')}`}>
                  <div className="relative">
                    <input
                      type="date"
                      value={expiryDate}
                      onChange={e => setExpiryDate(e.target.value)}
                      className={`w-full ${ic} font-semibold text-sm ${
                        !expiryDate
                          ? 'border-red-300 bg-red-50 text-red-700 ring-1 ring-red-200 focus:ring-red-400'
                          : 'border-blue-300 bg-blue-50 text-blue-700 focus:ring-blue-500'
                      }`}
                    />
                    {!expiryDate && (
                      <div className="absolute -bottom-5 left-0 text-[10px] text-red-500 font-bold flex items-center gap-1">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        </svg>
                        {t('purchase.expiryDateMandatory')}
                      </div>
                    )}
                  </div>
                </Lbl>
              )}

              {/* Total preview */}
              <div className="text-xs text-slate-500 text-right">
                {t('admin.dict.total_colon')} <strong className="text-blue-700">{fmt(Math.round(selNet * Number(qty)))} {t('purchase.somUnit')}</strong>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-8">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
              </svg>
              <p className="text-sm text-center">{t('purchase.searchAndSelect')}</p>
            </div>
          )}

          <button onClick={addItem} disabled={!sel || !qty}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-blue-200 active:scale-95">
            <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            {t('purchase.addToList')}
          </button>

          {activeItems.length > 0 && (
            <div className="bg-blue-600 rounded-2xl p-4 text-white">
              <div className="text-xs font-semibold opacity-70 uppercase tracking-wide">{t('purchase.totalSum')}</div>
              <div className="text-2xl font-black mt-1">{fmt(Math.round(totalNet))} <span className="text-sm font-normal opacity-70">{t('purchase.somUnit')}</span></div>
              <div className="text-xs opacity-60 mt-1">{activeItems.length} {t('purchase.productCount')}</div>
            </div>
          )}
        </div>

        {/* ── Right: items table ── */}
        <div className="flex-1 overflow-y-auto">
          {activeItems.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
              <p>{t('purchase.addProductHint')}</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-400 w-8">№</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product')}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-20">{t('purchase.colQty')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('purchase.colPrice')}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-28">{t('purchase.discount')}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('purchase.expiryDateShort')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('purchase.colNetPrice')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.total')}</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activeItems.map((it, i) => {
                  const qty_n = it.qty_ordered;
                  const discPct = it.discount_type === 'pct' ? it.discount_val : (it.unit_cost > 0 ? (it.discount_val / it.unit_cost * 100).toFixed(1) : 0);
                  const updFn = updPoItem;
                  return (
                    <tr key={i} className="hover:bg-slate-50 group">
                      <td className="px-3 py-2.5 text-slate-400 text-xs">{i + 1}</td>
                      <td className="px-3 py-2.5">
                        <div className="font-medium text-sm">{it.product_name}</div>
                        <div className="text-xs text-slate-400">{it.unit}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <input type="number" min="1" value={qty_n}
                          onChange={e => updFn(i, 'qty_ordered', Number(e.target.value))}
                          className="w-16 text-center border border-slate-200 rounded-lg px-1.5 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <input type="number" min="0" value={it.unit_cost}
                            onChange={e => updFn(i, 'unit_cost', e.target.value)}
                            className="w-24 text-right border border-slate-200 rounded-lg px-1.5 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                          {/* ✅ O'RTA-4 TUZATILDI: Barcha currencies orqali aylanadi */}
                          <button onClick={() => {
                            const curList = currencies.length > 0 ? currencies.map(c => c.code) : ['UZS', 'USD'];
                            const idx = curList.indexOf(it.currency || 'UZS');
                            const nextCur = curList[(idx + 1) % curList.length];
                            updFn(i, 'currency', nextCur);
                          }}
                            className={`text-[10px] font-bold px-1.5 py-1 rounded-md transition-colors ${
                              it.currency && it.currency !== 'UZS'
                                ? 'bg-emerald-100 text-emerald-700'
                                : 'bg-slate-100 text-slate-500'
                            }`}>
                            {it.currency || 'UZS'}
                          </button>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <input type="number" min="0" value={it.discount_val}
                            onChange={e => updFn(i, 'discount_val', e.target.value)}
                            className="w-14 text-center border border-slate-200 rounded-lg px-1 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500" />
                          <button onClick={() => updFn(i, 'discount_type', it.discount_type === 'pct' ? 'amt' : 'pct')}
                            className={`text-[10px] font-bold px-1.5 py-1 rounded-md min-w-[28px] transition-colors ${it.discount_type === 'pct' ? 'bg-amber-100 text-amber-700' : 'bg-violet-100 text-violet-700'}`}>
                            {it.discount_type === 'pct' ? '%' : t('purchase.somUnit')}
                          </button>
                        </div>
                        {Number(it.discount_val) > 0 && <div className="text-[10px] text-amber-600 mt-0.5">–{discPct}%</div>}
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        {it.category_is_perishable ? (
                          <div className="flex flex-col items-center gap-1">
                            <input type="date" value={it.expiry_date || ''}
                              onChange={e => updFn(i, 'expiry_date', e.target.value)}
                              className={`w-34 text-center border rounded-lg px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                                !it.expiry_date
                                  ? 'border-red-300 bg-red-50 text-red-600 ring-1 ring-red-200'
                                  : 'border-slate-200 hover:border-blue-300'
                              }`} />
                            {!it.expiry_date && (
                              <span className="text-[9px] text-red-500 font-bold">{t('purchase.enterExpiry')}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-300 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold text-emerald-700 text-sm">
                        {it.currency && it.currency !== 'UZS' ? (
                          <div>
                            <div>{fmt(it.unit_cost)} <span className="text-xs">{it.currency}</span></div>
                            <div className="text-[10px] text-slate-400 font-normal">≈ {fmt(Math.round(it.net_cost))} {t('purchase.somUnit')}</div>
                          </div>
                        ) : (
                          fmt(Math.round(it.net_cost))
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-bold text-slate-800">
                        {it.currency && it.currency !== 'UZS' ? (
                          <div>
                            <div className="text-blue-600">{fmt(Math.round(it.unit_cost * qty_n * 100) / 100)} <span className="text-xs">{it.currency}</span></div>
                            <div className="text-[10px] text-slate-400 font-normal">≈ {fmt(Math.round(it.net_cost * qty_n))} {t('purchase.somUnit')}</div>
                          </div>
                        ) : (
                          fmt(Math.round(it.net_cost * qty_n))
                        )}
                      </td>
                      <td className="pr-2">
                        <button onClick={() => setPoItems(p => p.filter((_, idx) => idx !== i))}
                          className="p-1.5 text-slate-300 hover:text-red-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="flex items-center gap-4 px-6 py-3.5 border-t border-slate-200 bg-white shrink-0">
        {/* Auto-update toggles */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wide">{t('purchase.updatePricesLabel')}</span>
          <button onClick={() => setAutoRet(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoRetail ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            {t('purchase.retail')}
          </button>
          <button onClick={() => setAutoWho(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoWholesale ? 'bg-amber-500 text-white border-amber-500' : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            {t('purchase.wholesale')}
          </button>
        </div>
        <div className="flex gap-2 ml-auto items-center">
          {err && <span className="text-red-500 text-sm whitespace-nowrap bg-red-50 px-3 py-1.5 rounded-lg border border-red-100 font-semibold">{err}</span>}
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
          <Btn v="secondary" onClick={() => savePo('draft')} disabled={saving}>{t('purchase.saveDraft')}</Btn>
          <Btn v="secondary" onClick={() => savePo('sent')} disabled={saving}>{t('purchase.saveNoPayment')}</Btn>
          <Btn v="amber" onClick={() => savePo('received')} disabled={saving}>{t('purchase.receiveOnDebt')}</Btn>
          <Btn onClick={handleOpenPay} disabled={saving}>{t('admin.dict.payment')}</Btn>
        </div>
      </div>

      {showPay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl flex flex-col max-h-full">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h2 className="text-xl font-bold text-slate-800 tracking-tight">{t('purchase.payTitle')} <span className="text-blue-500 font-medium text-lg ml-2">{new Date().toLocaleString('uz-UZ').replace(',', '')}</span></h2>
              <button onClick={() => setShowPay(false)} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6">
              <div className="grid grid-cols-2 gap-6">
                {/* Chegirma */}
                <div className="space-y-2">
                  <div className="flex items-center gap-4 text-sm font-semibold text-slate-700">
                    {t('purchase.discount')}
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 font-medium hover:text-slate-700 transition-colors">
                      <input type="radio" checked={payForm.discType === 'amt'} onChange={() => setPayForm(p => ({ ...p, discType: 'amt' }))} className="w-4 h-4 text-blue-600" /> {t('purchase.noDiscountLabel')}
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 font-medium hover:text-slate-700 transition-colors">
                      <input type="radio" checked={payForm.discType === 'pct'} onChange={() => setPayForm(p => ({ ...p, discType: 'pct' }))} className="w-4 h-4 text-blue-600" /> %
                    </label>
                  </div>
                  <div className="flex h-11">
                    <input type="number" value={payForm.discVal} onChange={e => setPayForm(p => ({ ...p, discVal: e.target.value }))} className={`${ic} flex-1 rounded-r-none border-r-0 text-base font-medium`} placeholder="0" />
                    <div className="bg-slate-50 px-4 flex items-center border border-slate-200 text-slate-500 text-sm font-semibold rounded-r-xl">
                      {payCur} | {fmt(payCurRate)}
                    </div>
                  </div>
                </div>

                {/* Kassa */}
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-600">{t('finance.wallet')}</label>
                  <select value={payForm.wallet_id} onChange={e => setPayForm(p => ({ ...p, wallet_id: e.target.value }))} className={`${ic} w-full h-11 bg-white text-base`}>
                    <option value="">{t('admin.dict.select')}</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)})</option>)}
                  </select>
                </div>
              </div>

              {/* To'lov */}
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-600">{t('admin.dict.payment')}</label>
                <div className="flex gap-2 h-11 items-center">
                  {/* Naqd label separated */}
                  <select value={payForm.payment_type || 'cash'} onChange={e => setPayForm(p => ({ ...p, payment_type: e.target.value }))}
                    className="bg-slate-50 px-3 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 h-full shadow-sm outline-none cursor-pointer">
                    {PO_PAY_TYPES.map(pt => <option key={pt.key} value={pt.key}>{pt.lKey ? t(pt.lKey) : pt.label}</option>)}
                  </select>
                  {/* Input group */}
                  <div className="flex flex-1 items-center h-full rounded-xl focus-within:ring-2 focus-within:ring-blue-500 overflow-hidden shadow-sm">
                    <input type="number" min="0" value={payForm.cash} onChange={e => setPayForm(p => ({ ...p, cash: e.target.value }))} className="flex-1 w-full h-full border border-slate-200 border-r-0 rounded-l-xl px-4 text-base font-bold text-blue-700 outline-none" placeholder="0" />
                    <select value={payCur} onChange={e => handlePayCurrencyChange(e.target.value)} className="bg-slate-50 hover:bg-slate-100 px-3 flex items-center border border-slate-200 border-x-0 text-blue-600 text-sm font-bold h-full outline-none cursor-pointer">
                      {currencies.map(c => <option key={c.code} value={c.code}>{c.code}</option>)}
                    </select>
                    <button onClick={() => setPayForm(p => ({ ...p, cash: String(payTotals.finalTotalInPayCur) }))} className="bg-blue-50 hover:bg-blue-100 text-blue-700 border border-slate-200 border-l-0 font-semibold px-6 h-full rounded-r-xl transition-colors whitespace-nowrap">
                      {t('purchase.totalBtn')}
                    </button>
                  </div>
                </div>
              </div>

              {/* Malumot */}
              <div className="space-y-2">
                <textarea rows="3" value={payForm.info} onChange={e => setPayForm(p => ({ ...p, info: e.target.value }))} className={`${ic} resize-none w-full text-sm leading-relaxed`} placeholder={t('purchase.infoPlaceholder')}></textarea>
              </div>

              {/* Summary blocks aligned to right */}
              <div className="flex flex-col items-end gap-3 pt-2">
                <div className="flex items-center justify-between w-72 text-base sm:text-lg">
                  <span className="text-slate-500">{t('purchase.summaryTotal')}</span>
                  <span className="font-bold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-lg">
                    {fmt(payTotals.finalTotalInPayCur)} <span className="text-xs uppercase">{payCur}</span>
                    {payCur !== 'UZS' && <span className="text-xs text-slate-400 font-normal ml-1">({fmt(payTotals.finalTotalUzs)} {t('purchase.somUnit')})</span>}
                  </span>
                </div>
                <div className="flex items-center justify-between w-72 text-base sm:text-lg">
                  <span className="text-slate-500">{t('purchase.summaryPaid')}</span>
                  <span className="font-bold text-blue-600 bg-blue-50 px-3 py-1 rounded-lg">
                    {fmt(payTotals.paidInPayCur)} <span className="text-xs uppercase">{payCur}</span>
                    {payCur !== 'UZS' && <span className="text-xs text-slate-400 font-normal ml-1">({fmt(payTotals.paidInUzs)} {t('purchase.somUnit')})</span>}
                  </span>
                </div>
                <div className="flex items-center justify-between w-72 text-base sm:text-lg">
                  <span className="text-slate-500">{t('purchase.summaryDebt')}</span>
                  <span className="font-bold text-red-500 bg-red-50 px-3 py-1 rounded-lg">
                    {fmt(payTotals.debtInPayCur)} <span className="text-xs uppercase">{payCur}</span>
                    {payCur !== 'UZS' && <span className="text-xs text-slate-400 font-normal ml-1">({fmt(payTotals.debtUzs)} {t('purchase.somUnit')})</span>}
                  </span>
                </div>
                {payTotals.changeInPayCur > 0 && (
                  <div className="flex items-center justify-between w-72 text-base sm:text-lg">
                    <span className="text-slate-500">{t('purchase.summaryChange')}</span>
                    <span className="font-bold text-slate-600 bg-slate-100 px-3 py-1 rounded-lg">
                      {fmt(payTotals.changeInPayCur)} <span className="text-xs uppercase">{payCur}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer Buttons */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 bg-slate-50 mt-auto rounded-b-2xl flex-wrap">
              <div className="text-sm font-semibold text-slate-500 flex-1">{t('purchase.supplierDebt')} <span className="text-slate-800 ml-1">{fmt(payTotals.debtInPayCur)} {payCur}</span></div>
              <button onClick={() => setShowPay(false)} className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-semibold bg-white hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
              <button disabled={saving} onClick={() => savePo('received', { paid: payTotals.paidInUzs - payTotals.changeUzs, amount: Math.round((payTotals.paidInPayCur - payTotals.changeInPayCur) * 100) / 100, currency: payCur, payment_type: payForm.payment_type || 'cash', info: payForm.info, wallet_id: payForm.wallet_id })} className="px-6 py-2.5 rounded-xl bg-orange-400 hover:bg-orange-500 text-white font-bold flex items-center gap-2 transition-colors disabled:opacity-50 shadow-sm">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" /></svg>
                {t('purchase.saveAndPrint')}
              </button>
              <button disabled={saving} onClick={() => savePo('received', { paid: payTotals.paidInUzs - payTotals.changeUzs, amount: Math.round((payTotals.paidInPayCur - payTotals.changeInPayCur) * 100) / 100, currency: payCur, payment_type: payForm.payment_type || 'cash', info: payForm.info, wallet_id: payForm.wallet_id })} className="px-8 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold transition-colors shadow-sm shadow-blue-200 disabled:opacity-50 flex items-center gap-2">
                {saving ? '...' : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    {t('purchase.receiveAndSave')}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── VARIANT PICKER MODAL ── */}
      {variantPickerProduct && (
        <VariantPickerModal
          parent={variantPickerProduct}
          onClose={() => setVariantPickerProduct(null)}
          onSelect={(variant) => {
            setVariantPickerProduct(null);
            selectProduct(variant);
          }}
        />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   KIRIMLAR TAB
══════════════════════════════════════════════════════════ */
function KirimlarTab() {
  const { t } = useLang();
  const [mode, setMode] = useState('list');
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip] = useState(0);
  const [stFilter, setStFil] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [branches, setBranches] = useState([]);
  const [detail, setDetail] = useState(null);
  const [recModal, setRec] = useState(null);
  const [recSaving, setRS] = useState(false);
  const [editPo, setEditPo] = useState(null);
  const LIMIT = 20;

  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('auth.errGeneral')) });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (stFilter) params.status = stFilter;
      if (branchFilter) params.branch_id = branchFilter;
      const r = await api.get('/purchase-orders', { params, _noCache: true });
      setPos(r.data);
    } catch { /* xabarni axios interceptor ko'rsatadi */ } finally { setLoading(false); }
  }, [skip, stFilter, branchFilter]);

  useEffect(() => { if (mode === 'list') load(); }, [load, mode]);

  const openDetail = async (row) => {
    try {
      const r = await api.get(`/purchase-orders/${row.id}`, { _noCache: true });
      setDetail(r.data);
    } catch { /* xabarni axios interceptor ko'rsatadi */ }
  };

  // Qabul: har bir qator uchun miqdor (qisman qabul), partiya raqami va yaroqlilik muddati
  const openReceive = (po) => {
    setRec({
      ...po,
      items: (po.items || []).map(i => {
        const rem = Math.max(0, Number(i.qty_ordered) - Number(i.qty_received));
        return { ...i, _qty: String(rem), _lot: '', _exp: i.expiry_date ? String(i.expiry_date).slice(0, 10) : '' };
      }),
    });
    setDetail(null);
  };
  const updRec = (id, field, val) => setRec(r => ({ ...r, items: r.items.map(i => i.id === id ? { ...i, [field]: val } : i) }));

  const receivePo = async () => {
    const rows = recModal.items
      .filter(i => Number(i.qty_ordered) > Number(i.qty_received) && Number(i._qty) > 0)
      .map(i => ({ po_item_id: i.id, qty_received: Number(i._qty), lot_number: i._lot || null, expiry_date: i._exp || null }));
    if (!rows.length) { toast.error(t('purchase.nothingToReceive')); return; }
    setRS(true);
    try {
      await api.post(`/purchase-orders/${recModal.id}/receive`, { items: rows });
      toast.success(t('purchase.receivedOk'));
      setRec(null); setDetail(null); load();
    } catch { /* xabarni axios interceptor ko'rsatadi, oyna ochiq qoladi */ } finally { setRS(false); }
  };

  const cancelPo = async (po) => {
    if (!confirm(`"${po.number}" ${t('purchase.confirmCancelPo')}`)) return;
    try {
      await api.post(`/purchase-orders/${po.id}/cancel`);
      toast.success(t('purchase.poCancelled'));
      setDetail(null); load();
    } catch { /* xabarni axios interceptor ko'rsatadi */ }
  };

  // Qator narxi xarid valyutasida (bazada unit_cost — UZS)
  const itemPrice = (item, po) => {
    const cur = item.cost_currency || 'UZS';
    if (cur === 'UZS') return { cur, unit: Number(item.unit_cost) };
    if (cur === po.currency && Number(po.exchange_rate) > 0) return { cur, unit: Number(item.unit_cost) / Number(po.exchange_rate) };
    return { cur, unit: Number(item.original_unit_cost ?? item.unit_cost) };
  };

  const handleEdit = async (row) => {
    try {
      const r = await api.get(`/purchase-orders/${row.id}`);
      setEditPo(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  const handleDeletePo = async (row) => {
    if (!confirm(`"${row.number}" ${t('purchase.confirmDeletePo')}`)) return;
    try {
      await api.delete(`/purchase-orders/${row.id}`);
      toast.success(t('purchase.poDeleted'));
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  if (editPo) return <KirimCreateView editPo={editPo} onBack={() => setEditPo(null)} onSaved={() => { setEditPo(null); load(); }} />;
  if (mode === 'create') return <KirimCreateView onBack={() => setMode('list')} onSaved={load} />;

  const cols = [
    { k: 'number', l: t('purchase.colNumber') },
    { k: 'supplier_name', l: t('purchase.supplier') },
    { k: 'warehouse_name', l: t('purchase.colWarehouse') },
    { k: 'status', l: t('purchase.filterStatus'), r: v => <Badge meta={poMeta} val={v} /> },
    { k: 'total_amount', l: t('purchase.colTotal'), r: (v, row) => {
      const netUzs = Number(v) - Number(row.discount_amount || 0);  // chegirmadan keyin
      if (row.currency && row.currency !== 'UZS' && row.original_total_amount != null) {
        return (
          <div>
            <div className="font-bold text-blue-600">{fmt(Number(row.original_total_amount))} <span className="text-xs uppercase font-semibold">{row.currency}</span></div>
            <div className="text-[10px] text-slate-400">≈ {fmt(netUzs)} {t('purchase.somUnit')}</div>
          </div>
        );
      }
      return <span>{fmt(netUzs)} <span className="text-xs text-slate-400">{t('purchase.somUnit')}</span></span>;
    } },
    { k: 'paid_amount', l: t('common.paid'), r: (v, row) => {
      // USD yoki boshqa valyutada bo'lsa, original qiymatni ko'rsatish
      if (row.currency && row.currency !== 'UZS' && row.original_paid_amount != null) {
        return (
          <div>
            <div className="font-semibold text-emerald-600">{fmt(Number(row.original_paid_amount))} <span className="text-xs uppercase font-semibold">{row.currency}</span></div>
            <div className="text-[10px] text-slate-400">≈ {fmt(Number(v))} {t('purchase.somUnit')}</div>
          </div>
        );
      }
      // Agar currency USD lekin original_paid_amount yo'q bo'lsa — UZS ekvivalentini ko'rsatish
      if (row.currency && row.currency !== 'UZS') {
        const origPaid = Number(v);
        return <span className="text-emerald-600 font-semibold">{fmt(origPaid)} <span className="text-xs text-slate-400">{t('purchase.somUnit')}</span></span>;
      }
      return <span className="text-emerald-600 font-semibold">{fmt(v)} <span className="text-xs text-slate-400">{t('purchase.somUnit')}</span></span>;
    } },
    { k: 'debt', l: t('common.debt'), r: (_, row) => {
      // Server hisobi: faqat qabul qilingan tovar qarz bo'ladi; manfiy — ortiqcha to'lov (avans)
      const d = row.debt_amount != null ? Number(row.debt_amount) : Number(row.total_amount) - Number(row.paid_amount || 0) - Number(row.discount_amount || 0);
      const cur = row.currency && row.currency !== 'UZS' ? row.currency : t('purchase.somUnit');
      if (d > 0.004) return <span className="text-red-500 font-semibold">{fmt(d)} <span className="text-xs">{cur}</span></span>;
      if (d < -0.004) return <span className="text-emerald-600 font-semibold">{t('purchase.avans')}: {fmt(-d)} <span className="text-xs">{cur}</span></span>;
      return '—';
    } },
    { k: 'created_at', l: t('purchase.colDate'), r: v => fmtDay(v) },
    {
      k: 'id', l: '', r: (v, row) => (
        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
          {['draft', 'sent'].includes(row.status) && (
            <button onClick={() => handleEdit(row)}
              className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 font-medium whitespace-nowrap">
              ✏️ {t('common.edit')}
            </button>
          )}
          {['draft', 'sent', 'partial'].includes(row.status) && (
            <button onClick={() => openDetail(row)}
              className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 font-medium whitespace-nowrap">
              {t('purchase.receive')}
            </button>
          )}
          <button onClick={() => handleDeletePo(row)}
            className="text-xs px-2 py-1 bg-red-50 text-red-500 rounded-lg hover:bg-red-100 font-medium whitespace-nowrap">
            🗑️
          </button>
        </div>
      )
    },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Lbl t={t('purchase.filterStatus')}>
            <select value={stFilter} onChange={e => setStFil(e.target.value)} className={ic}>
              <option value="">{t('admin.dict.all2')}</option>
              {Object.entries(poMeta).map(([v, m]) => <option key={v} value={v}>{m.lKey ? t(m.lKey) : m.l}</option>)}
            </select>
          </Lbl>
          {branches.length > 0 && (
            <Lbl t={t('purchase.filterBranch')}>
              <select value={branchFilter} onChange={e => setBranchFilter(e.target.value)} className={ic}>
                <option value="">{t('purchase.allBranches')}</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </Lbl>
          )}
          <div className="ml-auto">
            <Btn onClick={() => setMode('create')}>
              <svg className="w-4 h-4 inline mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              {t('purchase.newKirim')}
            </Btn>
          </div>
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <Tbl cols={cols} rows={pos} loading={loading} skip={skip} limit={LIMIT} onChange={setSkip} onRow={openDetail} />
      </div>

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="text-lg font-bold">{t('purchase.order')} · {detail.number}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-4 gap-3 text-sm">
                {[[t('purchase.supplier'), detail.supplier_name], [t('purchase.colWarehouse'), detail.warehouse_name], [t('purchase.filterStatus'), <Badge meta={poMeta} val={detail.status} />], [t('purchase.colDate'), fmtDay(detail.created_at)]].map(([k, v]) => (
                  <div key={k} className="bg-slate-50 rounded-xl p-3"><div className="text-xs text-slate-500 mb-1">{k}</div><div className="font-semibold">{v}</div></div>
                ))}
              </div>
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.product')}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('purchase.order')}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('purchase.received')}</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.price')}</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.total')}</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.items?.map(item => (
                    <tr key={item.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium">{item.product_name}</td>
                      <td className="px-4 py-3 text-center">{item.qty_ordered}</td>
                      <td className="px-4 py-3 text-center text-emerald-600 font-semibold">{item.qty_received}</td>
                      {(() => {
                        // Avval UZS narx valyuta belgisi bilan chiqardi (masalan "1 270 000 USD")
                        const { cur, unit } = itemPrice(item, detail);
                        const label = cur === 'UZS' ? t('purchase.somUnit') : cur;
                        return (
                          <>
                            <td className="px-4 py-3 text-right">
                              <div>{fmt(Math.round(unit * 100) / 100)} <span className="text-xs font-semibold">{label}</span></div>
                              {cur !== 'UZS' && <div className="text-[10px] text-slate-400">≈ {fmt(item.unit_cost)} {t('purchase.somUnit')}</div>}
                            </td>
                            <td className="px-4 py-3 text-right font-semibold">{fmt(Math.round(Number(item.qty_ordered) * unit * 100) / 100)} <span className="text-xs font-semibold">{label}</span></td>
                          </>
                        );
                      })()}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex flex-wrap justify-end gap-x-6 gap-y-1 text-sm">
                <span className="text-slate-500">{t('purchase.colTotal')}: <b className="text-slate-800">{fmt(detail.total_amount)} {t('purchase.somUnit')}</b></span>
                {Number(detail.discount_amount) > 0 && <span className="text-slate-500">{t('purchase.discount')}: <b className="text-amber-600">{fmt(detail.discount_amount)} {t('purchase.somUnit')}</b></span>}
                <span className="text-slate-500">{t('common.paid')}: <b className="text-emerald-600">{fmt(detail.paid_amount)} {t('purchase.somUnit')}</b></span>
                {detail.currency && detail.currency !== 'UZS' && Number(detail.exchange_rate) > 0 && (
                  <span className="text-slate-400">1 {detail.currency} = {fmt(detail.exchange_rate)} {t('purchase.somUnit')}</span>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t">
              {['draft', 'sent', 'partial'].includes(detail.status) && (
                <Btn v="red" onClick={() => cancelPo(detail)}>{t('purchase.cancelOrder')}</Btn>
              )}
              <Btn v="ghost" onClick={() => setDetail(null)}>{t('admin.dict.close')}</Btn>
              {['draft', 'sent', 'partial'].includes(detail.status) && (
                <Btn v="green" onClick={() => openReceive(detail)}>{t('purchase.receive')}</Btn>
              )}
            </div>
          </div>
        </div>
      )}

      {recModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 max-h-[90vh] flex flex-col">
            <h3 className="text-lg font-bold mb-4">{t('purchase.receive')} · {recModal.number}</h3>
            <div className="overflow-y-auto border border-slate-200 rounded-xl mb-4">
              <table className="w-full text-sm">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-3 py-2 text-xs text-slate-500 font-semibold">{t('admin.dict.product')}</th>
                  <th className="text-center px-3 py-2 text-xs text-slate-500 font-semibold">{t('purchase.remaining')}</th>
                  <th className="text-center px-3 py-2 text-xs text-slate-500 font-semibold">{t('purchase.receiveQty')}</th>
                  <th className="text-center px-3 py-2 text-xs text-slate-500 font-semibold">{t('purchase.lotNumber')}</th>
                  <th className="text-center px-3 py-2 text-xs text-slate-500 font-semibold">{t('purchase.expiryDateShort')}</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {recModal.items?.filter(i => Number(i.qty_ordered) > Number(i.qty_received)).map(item => {
                    const rem = Number(item.qty_ordered) - Number(item.qty_received);
                    const bad = Number(item._qty) < 0 || Number(item._qty) > rem;
                    return (
                      <tr key={item.id}>
                        <td className="px-3 py-2 font-medium">{item.product_name}</td>
                        <td className="px-3 py-2 text-center text-slate-500">{fmt(rem)}</td>
                        <td className="px-3 py-2 text-center">
                          <input type="number" min="0" max={rem} step="any" value={item._qty} onChange={e => updRec(item.id, '_qty', e.target.value)}
                            className={`w-20 text-center border rounded-lg px-1.5 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${bad ? 'border-red-300 bg-red-50' : 'border-slate-200'}`} />
                        </td>
                        <td className="px-3 py-2 text-center">
                          <input value={item._lot} onChange={e => updRec(item.id, '_lot', e.target.value)} placeholder={`PO-${recModal.number}`}
                            className="w-28 border border-slate-200 rounded-lg px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500" />
                        </td>
                        <td className="px-3 py-2 text-center">
                          <input type="date" value={item._exp} onChange={e => updRec(item.id, '_exp', e.target.value)}
                            className="border border-slate-200 rounded-lg px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex gap-3">
              <Btn v="ghost" onClick={() => setRec(null)} className="flex-1">{t('common.cancel')}</Btn>
              <Btn v="green" onClick={receivePo} disabled={recSaving} className="flex-1">{recSaving ? '...' : t('common.confirm')}</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════

/* ===================== TA'MINOTCHILAR TAB ===================== */
const emptySupplier = {
  name: '', inn: '', phone: '', email: '', address: '', payment_terms: '30',
  bank_name: '', bank_account: '', bank_mfo: '', contract_number: '', contract_date: '', rating: '', notes: '',
  // Valyuta bo'yicha qarz: [{ currency: 'UZS', amount: '' }, ...] (manfiy — avans)
  debtEntries: [{ currency: 'UZS', amount: '' }],
  debtReason: '',
};
function StarRating({ value }) {
  const { t } = useLang();
  return <div className="flex gap-0.5">{[1, 2, 3, 4, 5].map(s => <span key={s} className={`text-base ${(value || 0) >= s ? 'text-amber-400' : 'text-slate-200'}`}>{'★'}</span>)}</div>;
}
function AvatarS({ name }) {
  const { t } = useLang();
  const cols = ['bg-blue-100 text-blue-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-blue-100 text-blue-600', 'bg-amber-100 text-amber-600'];
  const c = cols[(name?.charCodeAt(0) || 0) % cols.length];
  return <div className={`w-8 h-8 ${c} rounded-full flex items-center justify-center font-bold shrink-0 text-sm`}>{name?.charAt(0).toUpperCase()}</div>;
}
function SuppliersTab() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [list, setList] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(emptySupplier);
  const [saving, setSaving] = useState(false);
  const [payWallet, setPayWallet] = useState('');
  const [payInfo, setPayInfo] = useState('');
  const [wallets, setWallets] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [err, setErr] = useState('');
  const inp = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white';

  // Multi-row pay state (matches Customers.jsx pattern)
  const [payRows, setPayRows] = useState([{ id: Date.now(), payType: '', payAmount: '', currencyType: 'UZS' }]);

  const addPayRow = () => {
    if (payRows.length < 4) {
      setPayRows(prev => [...prev, { id: Date.now() + Math.random(), payType: '', payAmount: '', currencyType: 'UZS' }]);
    }
  };
  const removePayRow = (idx) => {
    if (payRows.length > 1) {
      setPayRows(prev => prev.filter((_, i) => i !== idx));
    } else {
      setPayRows([{ id: Date.now(), payType: '', payAmount: '', currencyType: 'UZS' }]);
    }
  };
  const updatePayRow = (idx, field, value) => {
    setPayRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r));
  };

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importRows, setImportRows] = useState([]);
  const [colMap, setColMap] = useState({});
  const [importLoading, setImportLoading] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState('');
  const [importPage, setImportPage] = useState(1);
  const [skipRows, setSkipRows] = useState(1);
  const [allowUpdate, setAllowUpdate] = useState(false);

  const IMPORT_FIELDS = [
    { key: '', label: t('product.selectOption') },
    { key: 'Nomi', label: t('purchase.importFieldSupplierName') },
    { key: 'INN', label: t('purchase.importFieldInn') },
    { key: 'Telefon', label: t('common.phone') },
    { key: 'Email', label: t('purchase.importFieldEmail') },
    { key: 'Manzil', label: t('common.address') },
    { key: "To'lov muddati (kun)", label: t('purchase.importFieldPaymentTermDays') },
    { key: 'Qarz', label: t('common.debt') },
    { key: '__SKIP__', label: t('purchase.importFieldSkip') },
  ];

  const resetImport = () => {
    setImportOpen(false); setImportRows([]); setImportFile(null);
    setImportResult(null); setImportError(''); setColMap({}); setImportPage(1);
    setSkipRows(1); setAllowUpdate(false); setImportProgress(0);
  };
  const openImport = () => { resetImport(); setImportOpen(true); };

  const autoMap = (rows) => {
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    const map = {};
    cols.forEach(col => {
      const lc = col.trim().toLowerCase();
      const found = IMPORT_FIELDS.find(f => f.label.toLowerCase().includes(lc) || f.key.toLowerCase() === lc);
      map[col] = found?.key && found.key !== '__SKIP__' ? found.key : '';
    });
    setColMap(map);
  };

  const parseExcel = async (file) => {
    setImportFile(file); setImportResult(null); setImportError(''); setImportPage(1);
    const XLSX = await loadXLSX();
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { defval: '', raw: false });
        setImportRows(rows);
        autoMap(rows);
      } catch {
        setImportError(t('purchase.fileReadError'));
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const buildPayload = () => {
    const actualRows = skipRows > 0 ? importRows.slice(skipRows - 1) : importRows;
    return actualRows.map((row, idx) => {
      const obj = {};
      Object.entries(colMap).forEach(([excelCol, fieldKey]) => {
        if (fieldKey && fieldKey !== '__SKIP__') {
          obj[fieldKey] = row[excelCol];
        }
      });
      obj.__row_index = (skipRows > 0 ? skipRows - 1 : 0) + idx + 2;
      return obj;
    }).filter(r => r['Nomi'] || r['INN']);
  };

  const downloadTemplate = async () => {
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const ws = XLSX.utils.json_to_sheet([{
      'Nomi': "Euro Print MChJ", 'INN': '123456789',
      'Telefon': '+998901234567', 'Email': 'info@europrint.uz',
      'Manzil': 'Toshkent sh.', "To'lov muddati (kun)": 30, 'Qarz': 0
    }]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, t('purchase.tabSuppliers'));
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), 'taminotchilar_shablon.xlsx');
  };

  const handleImport = async () => {
    const payload = buildPayload();
    if (!payload.length) return;
    setImportLoading(true); setImportResult(null); setImportError('');
    try {
      let totC = 0, totU = 0, totS = 0;
      let errs = [];
      const CHUNK_SIZE = 1000;

      for (let i = 0; i < payload.length; i += CHUNK_SIZE) {
        const chunk = payload.slice(i, i + CHUNK_SIZE);
        const { data } = await api.post(`/suppliers/bulk-import?allow_update=${allowUpdate}`, chunk);
        totC += data.created || 0;
        totU += data.updated || 0;
        totS += data.skipped || 0;
        if (data.errors) errs = [...errs, ...data.errors];
        setImportProgress(Math.round(((i + chunk.length) / payload.length) * 100));
      }

      setImportResult({ created: totC, updated: totU, skipped: totS, errors: errs });
      if (totC > 0 || totU > 0) load();
    } catch (err) {
      setImportError(err.response?.data?.detail || t('error.serverError'));
    } finally { setImportLoading(false); }
  };

  const [summary, setSummary] = useState(null);
  // Keshsiz: xarid/to'lov/qaytarishdan keyin qarz darhol yangilangan bo'lishi kerak
  const load = (q = search) => {
    api.get('/suppliers', { params: { limit: 5000, ...(q ? { search: q } : {}) }, _noCache: true }).then(r => setList(r.data)).catch(() => { });
    api.get('/suppliers/summary', { _noCache: true }).then(r => setSummary(r.data)).catch(() => { });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    load();
    api.get('/finance/wallets').then(r => { setWallets(r.data); if (r.data.length > 0) setPayWallet(String(r.data[0].id)); }).catch(() => { });
    api.get('/currencies/active').then(r => setCurrencies(r.data)).catch(() => { });
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => load(search), 400); return () => clearTimeout(t); }, [search]);
  const close = () => { setModal(null); setSel(null); setErr(''); };
  // All currency codes from backend
  const allCurrencyCodes = currencies.length > 0
    ? currencies.map(c => c.code)
    : ['UZS'];
  // Convert supplier debt_balances dict -> debtEntries array
  const buildDebtEntries = (s) => {
    const balances = s.debt_balances && typeof s.debt_balances === 'object' ? s.debt_balances : {};
    const entries = Object.entries(balances)
      .filter(([, amt]) => Number(amt) !== 0)
      .map(([currency, amount]) => ({ currency, amount: String(amount) }));
    // If no entries but has legacy debt_balance, add it
    if (entries.length === 0 && Number(s.debt_balance) !== 0) {
      entries.push({ currency: s.debt_currency || 'UZS', amount: String(s.debt_balance) });
    }
    // Always show at least 1 row
    if (entries.length === 0) {
      entries.push({ currency: allCurrencyCodes[0] || 'UZS', amount: '' });
    }
    return entries;
  };
  const openEdit = (s) => {
    setForm({
      ...emptySupplier,
      name: s.name, inn: s.inn || '', phone: s.phone || '', email: s.email || '', address: s.address || '',
      payment_terms: s.payment_terms != null ? String(s.payment_terms) : '30',
      bank_name: s.bank_name || '', bank_account: s.bank_account || '', bank_mfo: s.bank_mfo || '',
      contract_number: s.contract_number || '', contract_date: s.contract_date ? String(s.contract_date).slice(0, 10) : '',
      rating: s.rating != null ? String(s.rating) : '', notes: s.notes || '',
      debtEntries: buildDebtEntries(s), debtReason: '',
    });
    setSel(s); setErr(''); setModal('form');
  };
  const handleSave = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try {
      const p = {
        name: form.name.trim(), inn: form.inn || null, phone: form.phone || null, email: form.email || null,
        address: form.address || null,
        payment_terms: form.payment_terms !== '' ? Number(form.payment_terms) : 30,
        bank_name: form.bank_name || null, bank_account: form.bank_account || null, bank_mfo: form.bank_mfo || null,
        contract_number: form.contract_number || null, contract_date: form.contract_date || null,
        rating: form.rating !== '' ? Number(form.rating) : null, notes: form.notes || null,
      };
      const entered = {};
      (form.debtEntries || []).forEach(en => {
        if (en.currency && en.amount !== '' && !Number.isNaN(Number(en.amount))) entered[en.currency] = (entered[en.currency] || 0) + Number(en.amount);
      });
      if (sel) {
        // Rekvizitlar alohida saqlanadi. Qarz o'zgargan bo'lsa — faqat farqi, sababi bilan
        // (avval butun balans qayta yozilib, oraliqdagi xarid/to'lovlar yo'qolardi).
        const current = sel.debt_balances && typeof sel.debt_balances === 'object' ? sel.debt_balances : {};
        const changes = [];
        new Set([...Object.keys(current), ...Object.keys(entered)]).forEach(c => {
          const delta = Math.round(((entered[c] || 0) - Number(current[c] || 0)) * 10000) / 10000;
          if (Math.abs(delta) >= 0.01) changes.push({ currency: c, delta });
        });
        if (changes.length && !form.debtReason.trim()) { setErr(t('purchase.debtAdjustReasonRequired')); return; }
        await api.patch(`/suppliers/${sel.id}`, p);
        if (changes.length) await api.post(`/suppliers/${sel.id}/adjust-debt`, { changes, reason: form.debtReason.trim() });
      } else {
        const debtBalances = Object.fromEntries(Object.entries(entered).filter(([, v]) => v !== 0));
        await api.post('/suppliers', { ...p, debt_balances: debtBalances });
      }
      close(); load();
    } catch (ex) { setErr(errText(ex, t('common.error'))); load(); } finally { setSaving(false); }
  };
  const handlePayDebt = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try {
      const valid = payRows.filter(r => r.payAmount && Number(r.payAmount) > 0 && r.payType);
      if (valid.length === 0) { setErr(t('purchase.enterAtLeastOnePayment')); setSaving(false); return; }
      for (const row of valid) {
        await api.post(`/suppliers/${sel.id}/pay-debt`, {
          amount: Number(row.payAmount),
          currency: row.currencyType || 'UZS',
          payment_type: row.payType,
          reason: payInfo || t('purchase.debtPaymentReason'),
          wallet_id: payWallet ? Number(payWallet) : null,
        });
      }
      close(); load();
    }
    catch (ex) { setErr(errText(ex, t('common.error'))); load(); } finally { setSaving(false); };
  };
  const del = async (id) => {
    if (!confirm(t('confirm.delete'))) return;
    try { await api.delete(`/suppliers/${id}`); toast.success(t('purchase.supplierDeleted')); load(); }
    catch { /* xabar (masalan, ochiq qarz) axios interceptor orqali ko'rsatiladi */ }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <div className="relative flex-1"><svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder={t('purchase.searchSupplier')} value={search} onChange={e => setSearch(e.target.value)} /></div>

        <button
          onClick={async () => {
            const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
            const ws = XLSX.utils.json_to_sheet(list.map(s => {
              // ✅ Kichik-14 TUZATILDI: har bir valyuta alohida ustun
              const base = {
                [t('purchase.supplier')]: s.name,
                'INN': s.inn || '—',
                [t('common.phone')]: s.phone || '—',
                'Email': s.email || '—',
              };
              if (s.debt_balances && typeof s.debt_balances === 'object' && Object.keys(s.debt_balances).length > 0) {
                Object.entries(s.debt_balances).forEach(([cur, amt]) => {
                  if (Number(amt) > 0) base[`${t('common.debt')} (${cur})`] = Number(amt);
                });
              } else {
                base[`${t('common.debt')} (UZS)`] = s.debt_balance || 0;
              }
              return base;
            }));
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, t('purchase.tabSuppliers'));
            saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `taminotchilar_${new Date().toISOString().slice(0, 10)}.xlsx`);
          }}
          className="px-4 py-2 text-sm font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-xl flex items-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
          {t('purchase.exportExcel')}
        </button>
        <button
          onClick={openImport}
          className="px-4 py-2 text-sm font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-xl flex items-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
          {t('purchase.importExcel')}
        </button>

        <button onClick={() => { setForm(emptySupplier); setSel(null); setErr(''); setModal('form'); }} className="px-4 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-xl flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>{t('common.new')}
        </button>
      </div>
      <div className="flex items-center justify-between px-4 py-3 bg-white border border-slate-100 rounded-xl shadow-sm flex-wrap gap-2">
        <span className="text-sm font-medium text-slate-500">{t('purchase.totalSupplierDebt')}</span>
        <div className="flex flex-wrap items-center gap-3">
          {(() => {
            const debts = Object.entries(summary?.debt_by_currency || {}).filter(([, v]) => Number(v) > 0);
            const avans = Object.entries(summary?.avans_by_currency || {}).filter(([, v]) => Number(v) > 0);
            if (!debts.length && !avans.length) {
              return <span className="text-lg font-bold text-emerald-500">0 UZS</span>;
            }
            return (
              <>
                {debts.map(([cur, amt]) => (
                  <span key={`d-${cur}`} className="text-lg font-black text-red-500">
                    {fmt(amt)} <span className="text-xs font-bold text-slate-400">{cur}</span>
                  </span>
                ))}
                {avans.map(([cur, amt]) => (
                  <span key={`a-${cur}`} className="text-sm font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg border border-emerald-100">
                    {t('purchase.avans')}: {fmt(amt)} {cur}
                  </span>
                ))}
              </>
            );
          })()}
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">{[t('purchase.supplier'), 'INN', t('common.phone'), t('purchase.colRating'), t('common.debt'), ''].map(h => <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(s => {
              // Build multi-currency debt display
              const allBal = (s.debt_balances && typeof s.debt_balances === 'object')
                ? Object.entries(s.debt_balances)
                : (Number(s.debt_balance) !== 0 ? [[s.debt_currency || 'UZS', s.debt_balance]] : []);
              const debtMap = allBal.filter(([, v]) => Number(v) > 0);
              const avansMap = allBal.filter(([, v]) => Number(v) < 0);  // biz oldindan to'laganmiz
              const hasDebt = debtMap.length > 0;
              return (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4 cursor-pointer hover:bg-slate-100 transition-colors" onClick={() => navigate(`/admin/suppliers/${s.id}`)}><div className="flex items-center gap-2.5"><AvatarS name={s.name} /><div><div className="text-sm font-semibold text-blue-600 hover:underline">{s.name}</div>{s.email && <div className="text-xs text-slate-400">{s.email}</div>}</div></div></td>
                  <td className="px-5 py-4 text-sm font-mono text-slate-600">{s.inn || '\u2014'}</td>
                  <td className="px-5 py-4 text-sm text-slate-500">{s.phone || '\u2014'}</td>
                  <td className="px-5 py-4"><StarRating value={s.rating} /></td>
                  <td className="px-5 py-4">
                    {(hasDebt || avansMap.length > 0) ? (
                      <div className="flex flex-wrap gap-1.5">
                        {debtMap.map(([cur, amt]) => (
                          <span key={cur} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-red-50 text-red-600 border border-red-100">
                            {fmt(amt)} <span className="text-red-400">{cur}</span>
                          </span>
                        ))}
                        {avansMap.map(([cur, amt]) => (
                          <span key={`a-${cur}`} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">
                            {t('purchase.avans')}: {fmt(-Number(amt))} <span className="text-emerald-500">{cur}</span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs font-medium text-emerald-500 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-100">{t('purchase.noDebt')}</span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-1">
                      {hasDebt && (
                        <button onClick={() => {
                          setSel(s);
                          // Pre-fill first row with first real debt currency
                          const dMap = (s.debt_balances && typeof s.debt_balances === 'object')
                            ? Object.entries(s.debt_balances).filter(([, v]) => Number(v) > 0)
                            : (Number(s.debt_balance) > 0 ? [['UZS', s.debt_balance]] : []);
                          const firstCur = dMap[0]?.[0] || 'UZS';
                          const firstAmt = dMap[0]?.[1] !== undefined ? String(dMap[0][1]) : '';
                          setPayRows([{ id: Date.now(), payType: '', payAmount: firstAmt, currencyType: firstCur }]);
                          if (wallets.length > 0) setPayWallet(String(wallets[0].id));
                          setPayInfo('');
                          setErr('');
                          setModal('pay');
                        }} title={t('purchase.payDebt')} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
                          {t('purchase.payDebt')}
                        </button>
                      )}
                      <button onClick={() => openEdit(s)} className="p-1.5 text-blue-500 hover:bg-blue-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg></button>
                      <button onClick={() => del(s.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {list.length === 0 && <tr><td colSpan={6} className="px-5 py-12 text-center text-slate-400 text-sm">{t('purchase.noSuppliers')}</td></tr>}
          </tbody>
        </table>
      </div>
      {modal === 'form' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{sel ? t('common.edit') : t('purchase.newSupplier')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg></button>
            </div>
            <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('common.name')} *</label><input required className={inp} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={t('purchase.companyNamePlaceholder')} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">INN</label><input className={inp} value={form.inn} onChange={e => setForm({ ...form, inn: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.phone')}</label><input className={inp} value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">Email</label><input type="email" className={inp} value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.importFieldPaymentTermDays')}</label><input type="number" min="0" className={inp} value={form.payment_terms} onChange={e => setForm({ ...form, payment_terms: e.target.value })} /></div>
                <div className="col-span-2"><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('common.address')}</label><input className={inp} value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.bankName')}</label><input className={inp} value={form.bank_name} onChange={e => setForm({ ...form, bank_name: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.bankAccount')}</label><input className={inp} value={form.bank_account} onChange={e => setForm({ ...form, bank_account: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.bankMfo')}</label><input className={inp} value={form.bank_mfo} onChange={e => setForm({ ...form, bank_mfo: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.colRating')}</label>
                  <select className={inp} value={form.rating} onChange={e => setForm({ ...form, rating: e.target.value })}>
                    <option value="">—</option>
                    {[1, 2, 3, 4, 5].map(r => <option key={r} value={r}>{'★'.repeat(r)}</option>)}
                  </select>
                </div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.contractNumber')}</label><input className={inp} value={form.contract_number} onChange={e => setForm({ ...form, contract_number: e.target.value })} /></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.contractDate')}</label><input type="date" className={inp} value={form.contract_date} onChange={e => setForm({ ...form, contract_date: e.target.value })} /></div>
                <div className="col-span-2"><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('common.note')}</label><textarea rows={2} className={`${inp} resize-none`} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></div>

                {/* ── Multi-currency debt section ── */}
                <div className="col-span-2">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-semibold text-slate-600">
                      {sel ? t('purchase.debtByCurrency') : t('purchase.initialDebt')}
                    </label>
                    {/* + tugmasi: faqat hali qo'shilmagan valyuta bo'lsa */}
                    {(() => {
                      const usedCurrencies = (form.debtEntries || []).map(e => e.currency);
                      const availCurrencies = allCurrencyCodes.filter(c => !usedCurrencies.includes(c));
                      return availCurrencies.length > 0 ? (
                        <button
                          type="button"
                          onClick={() => {
                            const nextCur = availCurrencies[0];
                            setForm(f => ({ ...f, debtEntries: [...(f.debtEntries || []), { currency: nextCur, amount: '' }] }));
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1 text-xs font-bold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" /></svg>
                          {t('purchase.currencyLabel')}
                        </button>
                      ) : null;
                    })()}
                  </div>

                  {/* Debt entries list */}
                  <div className="space-y-2">
                    {(form.debtEntries || []).map((entry, idx) => {
                      const usedCurrencies = (form.debtEntries || []).map((e, i) => i !== idx ? e.currency : null).filter(Boolean);
                      const availForThisRow = allCurrencyCodes.filter(c => !usedCurrencies.includes(c));
                      return (
                        <div key={idx} className="flex items-center gap-2">
                          {/* Valyuta select */}
                          <select
                            value={entry.currency}
                            onChange={e => setForm(f => ({
                              ...f,
                              debtEntries: f.debtEntries.map((en, i) => i === idx ? { ...en, currency: e.target.value } : en)
                            }))}
                            className="shrink-0 w-24 px-2 py-2 border border-slate-200 rounded-lg text-sm font-bold bg-white focus:outline-none focus:ring-2 focus:ring-blue-400 text-slate-700"
                          >
                            {availForThisRow.map(c => <option key={c} value={c}>{c}</option>)}
                          </select>
                          {/* Miqdor input */}
                          <input
                            type="number"
                            className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
                            value={entry.amount}
                            onChange={e => setForm(f => ({
                              ...f,
                              debtEntries: f.debtEntries.map((en, i) => i === idx ? { ...en, amount: e.target.value } : en)
                            }))}
                            placeholder="0"
                          />
                          {/* Remove: faqat 2+ row bo'lsagina ko'rsatish */}
                          {(form.debtEntries || []).length > 1 && (
                            <button
                              type="button"
                              onClick={() => setForm(f => ({ ...f, debtEntries: f.debtEntries.filter((_, i) => i !== idx) }))}
                              className="w-8 h-8 flex items-center justify-center text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-xs text-slate-400 mt-1.5">
                    {sel
                      ? t('purchase.debtByCurrencyHint')
                      : t('purchase.initialDebtHint')}
                  </p>
                  {sel && (
                    <div className="mt-3">
                      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('purchase.debtAdjustReason')}</label>
                      <input className={inp} value={form.debtReason} onChange={e => setForm({ ...form, debtReason: e.target.value })} placeholder={t('purchase.debtAdjustReasonHint')} />
                    </div>
                  )}
                </div>
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
            </form>
            <div className="p-6 border-t border-slate-100 flex gap-3 shrink-0">
              <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
              <button onClick={handleSave} disabled={saving} className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? t('common.saving') : t('common.save')}</button>
            </div>
          </div>
        </div>
      )}

      {/* Qarz to'lash Modal — Multi-valyuta */}
      {modal === 'pay' && sel && (() => {
        const debt = Number(sel.debt_balance) || 0;
        const PAY_TYPES = [
          { key: 'cash', label: t('pay.cash') },
          { key: 'card', label: t('pay.card') },
          { key: 'uzcard', label: 'Uzcard' },
          { key: 'humo', label: 'Humo' },
          { key: 'transfer', label: t('purchase.bankTransfer') },
          { key: 'click', label: 'Click' },
          { key: 'payme', label: 'Payme' },
        ];

        // Per-currency totals being paid
        const paidPerCurrency = payRows.reduce((acc, row) => {
          const c = row.currencyType || 'UZS';
          acc[c] = (acc[c] || 0) + (Number(row.payAmount) || 0);
          return acc;
        }, {});

        // Total paid in UZS for aggregate remaining
        const totalPaidUzs = payRows.reduce((sum, row) => {
          const cur = currencies.find(c => c.code === row.currencyType) || { rate: 1 };
          return sum + (Number(row.payAmount) || 0) * Number(cur.rate || 1);
        }, 0);
        const remaining = Math.max(0, debt - totalPaidUzs);

        // Helper: get debt for a specific currency
        const getDebtForCur = (cur) => {
          if (sel.debt_balances && typeof sel.debt_balances === 'object' && Object.keys(sel.debt_balances).length > 0) {
            return Number(sel.debt_balances[cur] || 0);
          }
          return cur === 'UZS' ? debt : 0;
        };

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-2 md:p-4 bg-slate-900/70 backdrop-blur-sm" onClick={close}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="flex items-center justify-between px-5 md:px-7 py-4 md:py-5 border-b border-slate-100 shrink-0">
                <div>
                  <h3 className="text-lg md:text-xl font-bold text-slate-800 tracking-tight">{t('purchase.payTitle')}</h3>
                  <p className="text-xs md:text-sm text-blue-500 font-medium mt-0.5">{new Date().toLocaleString('uz-UZ').replace(',', '')}</p>
                </div>
                <button onClick={close} className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition-colors">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>

              {/* Body */}
              <div className="px-5 md:px-7 py-4 overflow-y-auto space-y-5">
                {/* Supplier Info Card */}
                <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <div className="w-11 h-11 rounded-xl bg-violet-100 flex items-center justify-center shrink-0">
                    <svg className="w-6 h-6 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1" /></svg>
                  </div>
                  <div className="min-w-0">
                    <div className="font-bold text-slate-800 text-sm md:text-base truncate">{sel.name}</div>
                    {sel.phone && <div className="text-xs text-slate-500 mt-0.5">{sel.phone}</div>}
                    <div className="text-sm font-bold text-red-500 mt-1">
                      {t('purchase.currentDebt')}
                      {sel.debt_balances && typeof sel.debt_balances === 'object' && Object.keys(sel.debt_balances).filter(k => Number(sel.debt_balances[k]) > 0).length > 0
                        ? Object.entries(sel.debt_balances).filter(([, v]) => Number(v) > 0).map(([cur, amt]) => (
                            <span key={cur} className="ml-2 inline-block">{fmt(amt)} {cur}</span>
                          ))
                        : <span className="ml-2">{fmt(debt)} UZS</span>
                      }
                    </div>
                  </div>
                </div>

                {/* Kassa tanlash */}
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold text-slate-700">{t('purchase.walletAccountLabel')}</label>
                  <select value={payWallet} onChange={e => setPayWallet(e.target.value)}
                    className="w-full h-11 md:h-12 px-4 border border-slate-200 cursor-pointer rounded-xl bg-white text-sm font-medium focus:border-blue-500 outline-none transition-all">
                    <option value="">{t('purchase.mainWallet')}</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} — {fmt(w.balance)} {t('purchase.somUnit')}</option>)}
                  </select>
                </div>

                {/* Multi-row payment inputs */}
                <div className="flex flex-col gap-2">
                  {payRows.map((row, index) => (
                    <div key={row.id} className="flex w-full items-end gap-2">

                      {/* To'lov turi (Listbox) */}
                      <div className="flex-1 min-w-[130px] space-y-1.5">
                        {index === 0 && <label className="text-sm font-semibold text-slate-700">{t('sale.paymentType')} *</label>}
                        <Listbox value={row.payType} onChange={val => updatePayRow(index, 'payType', val)}>
                          <div className="relative">
                            <ListboxButton className="w-full cursor-pointer flex items-center pl-3 pr-8 py-3 justify-between rounded-xl border border-slate-200 text-sm bg-white text-slate-900 outline-none focus:border-blue-500 transition-colors shadow-xs text-left font-medium h-11 md:h-12">
                              <span className="block truncate">{PAY_TYPES.find(pt => pt.key === row.payType)?.label || t('purchase.selectEllipsis')}</span>
                              <span className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-slate-400">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="size-4"><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" /></svg>
                              </span>
                            </ListboxButton>
                            <ListboxOptions className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-xl outline-none bg-white text-sm border border-slate-200 shadow-lg p-1">
                              {PAY_TYPES.map(pt => (
                                <ListboxOption key={pt.key} value={pt.key}
                                  className="group relative py-2 px-3 select-none cursor-pointer rounded-lg text-slate-800 data-[focus]:bg-blue-600 data-[focus]:text-white outline-none transition-colors">
                                  <div className="flex items-center justify-between">
                                    <span className="block truncate font-normal group-data-[selected]:font-semibold">{pt.label}</span>
                                    <span className="text-blue-600 group-data-[focus]:text-white group-not-data-[selected]:hidden">
                                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="size-4"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                                    </span>
                                  </div>
                                </ListboxOption>
                              ))}
                            </ListboxOptions>
                          </div>
                        </Listbox>
                      </div>

                      {/* To'lov miqdori + valyuta */}
                      <div className="flex-1 space-y-1.5">
                        {index === 0 && <label className="text-sm font-semibold text-slate-700">{t('purchase.paymentAmountLabel')} *</label>}
                        <div className="flex h-11 md:h-12">
                          <input
                            type="number"
                            value={row.payAmount}
                            onChange={e => updatePayRow(index, 'payAmount', e.target.value)}
                            className="flex-1 min-w-0 h-full border border-slate-200 rounded-l-xl px-3 text-sm font-medium outline-none focus:border-blue-500 transition-all"
                            placeholder="0"
                            autoFocus={index === 0}
                          />
                          {/* Valyuta Listbox */}
                          <Listbox value={row.currencyType || 'UZS'} onChange={val => {
                            const prevCode = row.currencyType || 'UZS';
                            const prevRate = Number(currencies.find(c => c.code === prevCode)?.rate || 1);
                            const newRate = Number(currencies.find(c => c.code === val)?.rate || 1);
                            const currentAmt = Number(row.payAmount) || 0;
                            const directDebt = getDebtForCur(val);

                            let newAmount;
                            if (directDebt > 0 && val !== prevCode) {
                              // New currency has its own explicit debt — show it
                              newAmount = directDebt;
                            } else if (currentAmt > 0) {
                              // Convert entered amount via rates: prev→UZS→new
                              const inUzs = currentAmt * prevRate;
                              newAmount = Math.round((inUzs / newRate) * 100) / 100;
                            } else {
                              newAmount = '';
                            }
                            updatePayRow(index, 'currencyType', val);
                            if (newAmount !== '') updatePayRow(index, 'payAmount', String(newAmount));
                          }}>
                            <div className="relative">
                              <ListboxButton className="w-full min-w-[80px] cursor-pointer flex items-center pl-3 pr-7 py-3 justify-between border-l-0 border border-slate-200 text-sm bg-white text-blue-600 font-bold outline-none transition-colors shadow-xs text-left h-11 md:h-12">
                                <span className="block truncate">{row.currencyType || 'UZS'}</span>
                                <span className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-slate-400">
                                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="size-4"><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" /></svg>
                                </span>
                              </ListboxButton>
                              <ListboxOptions className="absolute z-30 mt-1 max-h-60 right-0 w-28 overflow-auto rounded-xl outline-none bg-white text-sm border border-slate-200 shadow-lg p-1">
                                {currencies.map(c => (
                                  <ListboxOption key={c.code} value={c.code}
                                    className="group relative py-2 px-3 select-none cursor-pointer rounded-lg text-slate-800 data-[focus]:bg-blue-600 data-[focus]:text-white outline-none transition-colors">
                                    <div className="flex items-center justify-between">
                                      <span className="block truncate font-normal group-data-[selected]:font-semibold">{c.code}</span>
                                      <span className="text-blue-600 group-data-[focus]:text-white group-not-data-[selected]:hidden">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="size-4"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                                      </span>
                                    </div>
                                  </ListboxOption>
                                ))}
                              </ListboxOptions>
                            </div>
                          </Listbox>
                          {/* Barchasi button */}
                          <button type="button"
                            onClick={() => {
                              const d = getDebtForCur(row.currencyType || 'UZS');
                              updatePayRow(index, 'payAmount', String(d > 0 ? d : (Number(debt) || 0)));
                            }}
                            className="bg-blue-50 hover:bg-blue-100 text-blue-700 border border-slate-200 border-l-0 font-bold px-3 h-full rounded-r-xl transition-colors whitespace-nowrap text-xs">
                            {t('purchase.allAmount')}
                          </button>
                        </div>
                      </div>

                      {/* O'chirish tugmasi */}
                      <button type="button" onClick={() => removePayRow(index)}
                        className="cursor-pointer p-3 bg-red-50 hover:bg-red-100 text-red-500 rounded-xl h-11 md:h-12 flex items-center justify-center shrink-0 self-end">
                        <Minus className="size-4" />
                      </button>
                    </div>
                  ))}

                  {/* Qator qo'shish */}
                  <button type="button" onClick={addPayRow}
                    className="cursor-pointer flex ml-auto items-center gap-1 hover:bg-blue-50 w-max px-2 py-0.5 rounded-xl">
                    <Plus className="size-5 text-blue-600" />
                    <span className="text-sm font-semibold text-blue-600">{t('purchase.addPaymentRow')}</span>
                  </button>
                </div>

                {/* Izoh */}
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold text-slate-700">{t('common.note')}</label>
                  <textarea rows={2} value={payInfo} onChange={e => setPayInfo(e.target.value)}
                    className="w-full p-3 border border-slate-200 rounded-xl text-sm leading-relaxed focus:ring-2 focus:ring-blue-500 outline-none resize-none transition-all"
                    placeholder={t('common.optional')} />
                </div>

                {err && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{err}</div>}

                {/* Per-currency summary */}
                <div className="flex justify-end">
                  <div className="w-full md:w-auto min-w-64 space-y-2 bg-blue-50/50 rounded-xl p-4 border border-blue-100/50">
                    <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">{t('purchase.debtStatus')}</div>
                    {Object.entries(paidPerCurrency).map(([cur, payAmt]) => {
                      const currDebt = getDebtForCur(cur);
                      const currRemaining = Math.max(0, currDebt - payAmt);
                      const currChange = Math.max(0, payAmt - currDebt);
                      return (
                        <div key={cur} className="space-y-1 pb-2 border-b border-blue-100/50 last:border-0">
                          <div className="flex justify-between text-xs items-center">
                            <span className="text-slate-500 font-medium">{cur} {t('purchase.debtSuffix')}</span>
                            <span className="font-bold text-slate-700">{fmt(currDebt)} {cur}</span>
                          </div>
                          <div className="flex justify-between text-xs items-center">
                            <span className="text-slate-500 font-medium">{t('admin.dict.payment')}:</span>
                            <span className="font-bold text-blue-600">{fmt(payAmt)} {cur}</span>
                          </div>
                          <div className="flex justify-between text-xs items-center">
                            <span className="text-slate-600 font-semibold">{t('purchase.remaining')}</span>
                            <span className={`font-bold ${currRemaining > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                              {fmt(currRemaining)} {cur}
                            </span>
                          </div>
                          {currChange > 0 && (
                            <div className="flex justify-between text-xs items-center">
                              <span className="text-amber-600 font-bold">{t('purchase.summaryChange')}</span>
                              <span className="font-bold text-amber-600">{fmt(currChange)} {cur}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {Object.keys(paidPerCurrency).length > 0 && (
                      <div className="flex justify-between text-xs items-center pt-1">
                        <span className="text-slate-400 font-medium">{t('purchase.totalRemainingUzs')}</span>
                        <span className={`font-semibold ${remaining > 0 ? 'text-red-400' : 'text-emerald-500'}`}>{fmt(remaining)} UZS</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 md:px-7 py-4 md:py-5 border-t border-slate-100 bg-slate-50 rounded-b-2xl shrink-0">
                <div className="text-xs md:text-sm text-slate-500 text-center sm:text-left">
                  <span className="font-semibold text-slate-600">{t('purchase.remainsAfterPayment')}</span>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                    {sel.debt_balances && Object.entries(sel.debt_balances).map(([cur, amt]) => {
                      const willPay = paidPerCurrency[cur] || 0;
                      const afterPay = Math.max(0, Number(amt) - willPay);
                      return (
                        <span key={cur} className={`font-bold ${afterPay > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                          {fmt(afterPay)} {cur}
                        </span>
                      );
                    })}
                    {(!sel.debt_balances || Object.keys(sel.debt_balances).length === 0) && (
                      <span className={`font-bold ${remaining > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmt(remaining)} UZS</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-2 md:gap-3 w-full sm:w-auto">
                  <button onClick={close} className="flex-1 sm:flex-none px-4 md:px-6 py-2 md:py-2.5 rounded-xl border border-slate-300 text-slate-600 text-sm font-bold bg-white hover:bg-slate-50 transition-all">{t('admin.dict.cancel')}</button>
                  <button disabled={saving || !payRows.some(r => r.payAmount && Number(r.payAmount) > 0 && r.payType)}
                    onClick={handlePayDebt}
                    className="flex-1 cursor-pointer sm:flex-none px-6 md:px-8 py-2 md:py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold transition-all shadow-lg shadow-blue-200 disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-2 text-sm">
                    {saving ? (
                      <span className="flex items-center gap-2"><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>{t('common.saving')}</span>
                    ) : (
                      <><svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>{t('common.save')}</>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
      {/* ── IMPORT MODAL (Full screen) ────────────── */}
      {importOpen && (
        <div className="fixed inset-0 z-50 bg-slate-50 flex flex-col">
          {/* Top Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <button onClick={resetImport} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
              <h2 className="text-xl font-bold text-slate-800">{t('purchase.importSuppliersTitle')}</h2>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={downloadTemplate} className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-lg transition-colors">
                {t('purchase.templateLabel')}
              </button>
              <label className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-lg border border-slate-200 cursor-pointer">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                {t('purchase.chooseFile')}
                <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
              </label>
              <button
                onClick={handleImport}
                disabled={!buildPayload().length || importLoading || !(Object.values(colMap).includes('Nomi') || (allowUpdate && Object.values(colMap).includes('INN')))}
                className="inline-flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors border border-transparent"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
                {importLoading ? `${t('common.saving')} ${importProgress}%` : t('common.save')}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto flex flex-col">
            {!importFile ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                <svg className="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">{t('purchase.uploadExcelToStart')}</p>
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Options Toolbar */}
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shadow-sm bg-white shrink-0">
                  <div className="flex items-center gap-6">
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${allowUpdate ? 'bg-blue-600' : 'bg-slate-200'}`}>
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${allowUpdate ? 'translate-x-6' : 'translate-x-1'}`} />
                      </div>
                      <span className="text-sm font-semibold text-slate-700 group-hover:text-blue-600 transition-colors">{t('purchase.allowUpdatePermission')}</span>
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-3 bg-white border border-slate-200 px-3 py-1.5 rounded-xl">
                      <span className="text-sm font-medium text-slate-600">{t('purchase.skipRowsLabel')}</span>
                      <button onClick={() => setSkipRows(Math.max(0, skipRows - 1))} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">−</button>
                      <span className="text-sm font-bold w-6 text-center">{skipRows}</span>
                      <button onClick={() => setSkipRows(skipRows + 1)} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">+</button>
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="px-6 py-2.5 flex items-center justify-between border-b border-slate-100 shrink-0">
                    <span className="text-sm text-slate-600 font-medium">
                      {t('purchase.loadingCount')} <strong>{buildPayload().length} {t('common.piece')}</strong>
                    </span>
                    {!(Object.values(colMap).includes('Nomi') || (allowUpdate && Object.values(colMap).includes('INN'))) && (
                      <span className="text-sm font-semibold text-red-500">
                        * {allowUpdate ? t('purchase.nameOrInn') : t('purchase.importFieldSupplierName')} {t('purchase.columnRequired')}
                      </span>
                    )}
                  </div>

                  <div className="flex-1 overflow-auto">
                    <table className="min-w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-slate-100">
                          <th className="px-3 py-2.5 text-left font-bold text-slate-500 border-b border-slate-200 text-sm">#</th>
                          {Object.keys(importRows[0] || {}).map(col => (
                            <th key={col} className="px-2 py-2 border-b border-slate-200 min-w-[160px]">
                              <select
                                value={colMap[col] || ''}
                                onChange={e => setColMap(m => ({ ...m, [col]: e.target.value }))}
                                className="w-full bg-white border border-slate-300 px-2 py-1.5 rounded-lg text-sm font-semibold text-slate-700 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                              >
                                {IMPORT_FIELDS.map(f => (
                                  <option key={f.key} value={f.key}>{f.label}</option>
                                ))}
                              </select>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {importRows.slice(0, importPage * 50).map((row, i) => {
                          const skipped = i < skipRows;
                          return (
                            <tr key={i} className={`hover:bg-slate-50/50 ${skipped ? 'opacity-40 bg-slate-50' : ''}`}>
                              <td className="px-3 py-2 text-slate-400 font-medium border-r border-slate-100 bg-slate-50">{i + 1} {skipped && <span className="text-[10px] text-amber-500 block leading-none">{t('purchase.skipLabel')}</span>}</td>
                              {Object.keys(importRows[0] || {}).map((col, j) => (
                                <td key={j} className="px-3 py-2 border-r border-slate-100 text-slate-700 truncate max-w-[200px]" title={row[col]}>
                                  {row[col] || <span className="text-slate-300">—</span>}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {importRows.length > importPage * 50 && (
                      <div className="py-4 text-center">
                        <button onClick={() => setImportPage(p => p + 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">
                          {t('purchase.showMore')}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Result panel */}
            {importResult && (
              <div className="px-6 py-4 bg-white border-t border-slate-100">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="px-5 py-3 bg-emerald-50 rounded-xl text-center min-w-[120px]">
                    <div className="text-3xl font-black text-emerald-600">{importResult.created}</div>
                    <div className="text-sm font-semibold text-emerald-500">{t('product.importAdded')}</div>
                  </div>
                  {importResult.updated > 0 && (
                    <div className="px-5 py-3 bg-blue-50 rounded-xl text-center min-w-[120px]">
                      <div className="text-3xl font-black text-blue-600">{importResult.updated}</div>
                      <div className="text-sm font-semibold text-blue-500">{t('product.importUpdated')}</div>
                    </div>
                  )}
                  <div className={`px-5 py-3 rounded-xl text-center min-w-[120px] ${importResult.skipped > 0 ? 'bg-amber-50' : 'bg-slate-50'}`}>
                    <div className={`text-3xl font-black ${importResult.skipped > 0 ? 'text-amber-600' : 'text-slate-400'}`}>{importResult.skipped}</div>
                    <div className={`text-sm font-semibold ${importResult.skipped > 0 ? 'text-amber-500' : 'text-slate-400'}`}>{t('product.importSkipped')}</div>
                  </div>
                  <div className="flex-1 min-w-0">
                    {importResult.errors?.length > 0 && (
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {importResult.errors.map((e, i) => (
                          <div key={i} className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-lg text-sm">
                            <span className="font-bold text-amber-600 shrink-0">#{e.row}</span>
                            <span className="text-amber-700">{e.name && <span className="font-semibold">{e.name}: </span>}{e.error}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            {importError && (
              <div className="mx-6 mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{importError}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ===================== MAIN ===================== */
const TABS_IDS = [
  { id: 'kirimlar', key: 'purchase.tabKirimlar', icon: <CircleArrowDown size={18} className='text-blue-500' /> },
  { id: 'suppliers', key: 'purchase.tabSuppliers', icon: <PackageCheck size={18} className='text-green-500' /> },
];

/* ═══════════════════════════════════════════ */
/* Variant tanlash modali                      */
/* ═══════════════════════════════════════════ */
function VariantPickerModal({ parent, onClose, onSelect }) {
  const { t } = useLang();
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/products/${parent.id}/variants`)
      .then(r => setVariants(Array.isArray(r.data) ? r.data : []))
      .catch(() => {
        // fallback
        api.get('/products', { params: { parent_id: parent.id, limit: 100 } })
          .then(r => setVariants(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
          .catch(() => setVariants([]));
      })
      .finally(() => setLoading(false));
  }, [parent.id]);

  const colors = [...new Set(variants.map(v => v.color).filter(Boolean))];
  const sizes  = [...new Set(variants.map(v => v.size).filter(Boolean))];

  const getVariant = (color, size) =>
    variants.find(v => v.color === color && v.size === size) ||
    variants.find(v => v.color === color && !size) ||
    variants.find(v => !color && v.size === size);

  const fmt = v => Number(v || 0).toLocaleString('uz-UZ');

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-white font-black text-lg">{parent.name}</h2>
            <p className="text-blue-200 text-xs mt-0.5">{t('purchase.selectSizeAndColor')}</p>
          </div>
          <button onClick={onClose} className="w-9 h-9 bg-white/20 hover:bg-white/30 rounded-xl flex items-center justify-center transition-colors">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"/>
            </div>
          ) : variants.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <svg className="w-16 h-16 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/></svg>
              <p className="font-semibold">{t('purchase.variantsNotFound')}</p>
            </div>
          ) : colors.length > 0 && sizes.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs font-bold text-slate-500 pb-3 pr-3">{t('purchase.colorSizeHeader')}</th>
                    {sizes.map(s => (
                      <th key={s} className="text-center text-xs font-bold text-blue-700 bg-blue-50 rounded-lg px-3 py-2 min-w-[80px]">{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {colors.map(color => (
                    <tr key={color}>
                      <td className="pr-3 py-1.5"><span className="text-sm font-bold text-slate-700">{color}</span></td>
                      {sizes.map(size => {
                        const v = getVariant(color, size);
                        return (
                          <td key={size} className="text-center py-1.5 px-1">
                            {v ? (
                              <button onClick={() => onSelect(v)} className="w-full px-2 py-2 bg-white border-2 border-slate-200 hover:border-blue-500 hover:bg-blue-50 rounded-xl transition-all group">
                                <div className="text-xs font-black text-blue-700">{fmt(v.sale_price)}</div>
                                <div className={`text-[10px] font-semibold mt-0.5 ${Number(v.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                                  {Number(v.stock_quantity) > 0 ? `${fmt(v.stock_quantity)} ${t('common.piece')}` : t('purchase.outOfStock')}
                                </div>
                              </button>
                            ) : (
                              <div className="px-2 py-2 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-300 text-xs">—</div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {variants.map(v => (
                <button key={v.id} onClick={() => onSelect(v)} className="p-4 bg-white border-2 border-slate-200 hover:border-blue-500 hover:bg-blue-50 rounded-2xl transition-all text-left">
                  <div className="font-bold text-slate-800 text-sm">{v.size || v.color || v.name}</div>
                  <div className="text-blue-700 font-black mt-1">{fmt(v.sale_price)} UZS</div>
                  <div className={`text-xs font-semibold mt-1 ${Number(v.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                    {Number(v.stock_quantity) > 0 ? `${fmt(v.stock_quantity)} ${t('common.piece')}` : t('purchase.outOfStock')}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-between items-center bg-slate-50">
          <span className="text-xs text-slate-500 font-medium">{variants.length} {t('purchase.variantsAvailable')}</span>
          <button onClick={onClose} className="px-5 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-xl text-sm transition-colors">{t('admin.dict.cancel')}</button>
        </div>
      </div>
    </div>
  );
}

export default function Purchases() {
  const { t } = useLang();
  const [tab, setTab] = useState('kirimlar');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('purchase.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('purchase.pageSubtitle')}</p>
      </div>
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {TABS_IDS.map(tab_ => (
          <button key={tab_.id} onClick={() => setTab(tab_.id)}
            className={`px-5 py-2 text-sm cursor-pointer font-semibold rounded-lg transition-all flex items-center gap-2 ${tab === tab_.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            <span>{tab_.icon}</span>{t(tab_.key)}
          </button>
        ))}
      </div>
      {tab === 'kirimlar' && <KirimlarTab />}
      {tab === 'suppliers' && <SuppliersTab />}
    </div>
  );
}