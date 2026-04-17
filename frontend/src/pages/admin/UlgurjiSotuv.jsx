/**
 * UlgurjiSotuv — Ulgurji (wholesale) sotuv sahifasi
 * Barcha mavjud API endpointlari va feature-lar ishlatiladi.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';
import { buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import { toast } from '../../utils/toast';

/* ─── Yordamchi funksiyalar ─────────────────────────────── */
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const today = () => new Date().toISOString().slice(0, 10);
const parseN = (s) => parseFloat(String(s || '').replace(/\s/g, '')) || 0;

const PAY_TYPES = [
  { id: 'cash',   label: 'Naqd',             icon: '💵', color: 'bg-emerald-50 border-emerald-300 text-emerald-700' },
  { id: 'card',   label: 'Karta',             icon: '💳', color: 'bg-blue-50 border-blue-300 text-blue-700' },
  { id: 'uzcard', label: 'Uzcard',            icon: '🏦', color: 'bg-blue-50 border-blue-300 text-blue-700' },
  { id: 'humo',   label: 'Humo',              icon: '🏧', color: 'bg-violet-50 border-violet-300 text-violet-700' },
  { id: 'bank',   label: "Bank o'tkazmasi",   icon: '🏛️', color: 'bg-cyan-50 border-cyan-300 text-cyan-700' },
  { id: 'click',  label: 'Click',             icon: '📱', color: 'bg-indigo-50 border-indigo-300 text-indigo-700' },
  { id: 'payme',  label: 'Payme',             icon: '📲', color: 'bg-sky-50 border-sky-300 text-sky-700' },
  { id: 'uzum',   label: 'Uzum',              icon: '🍇', color: 'bg-orange-50 border-orange-300 text-orange-700' },
  { id: 'debt',   label: 'Qarzga',            icon: '📋', color: 'bg-amber-50 border-amber-300 text-amber-700' },
  { id: 'mixed',  label: 'Aralash',           icon: '🔀', color: 'bg-purple-50 border-purple-300 text-purple-700' },
];

const STATUS_META = {
  completed: { l: 'Yakunlandi', c: 'bg-emerald-100 text-emerald-700' },
  cancelled:  { l: 'Bekor',     c: 'bg-red-100 text-red-600' },
  pending:    { l: 'Kutilmoqda',c: 'bg-amber-100 text-amber-700' },
};
const PAY_META = {
  cash:'Naqd', card:'Karta', uzcard:'Uzcard', humo:'Humo', bank:"Bank o'tkazmasi",
  click:'Click', payme:'Payme', visa:'Visa', uzum:'Uzum', debt:'Qarz', mixed:'Aralash',
};

/* ─── Ikonkalar ─────────────────────────────────────────── */
function Ic({ d, cls = 'w-4 h-4' }) {
  return (
    <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
    </svg>
  );
}

/* ─── Mijoz qidiruv ─────────────────────────────────────── */
function CustomerSearch({ customers, value, onChange }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => String(c.id) === String(value));

  const filtered = (q.trim()
    ? customers.filter(c =>
        c.name?.toLowerCase().includes(q.toLowerCase()) ||
        c.phone?.includes(q))
    : customers
  ).slice(0, 10);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div ref={ref} className="relative">
      <div className={`flex items-center gap-2 border-2 rounded-xl px-3 py-2.5 bg-white transition-all ${open ? 'border-indigo-500 ring-4 ring-indigo-100' : 'border-slate-200 hover:border-slate-300'}`}>
        <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" cls="w-4 h-4 text-slate-400 shrink-0" />
        <input
          value={open ? q : (selected ? `${selected.name}${selected.phone ? ' · '+selected.phone : ''}` : '')}
          onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }}
          onFocus={() => setOpen(true)}
          placeholder="Mijoz tanlang yoki qidiring..."
          className="flex-1 text-sm font-semibold text-slate-800 outline-none bg-transparent placeholder:font-normal placeholder:text-slate-400"
        />
        {selected && (
          <button onClick={() => { onChange(''); setQ(''); }} className="text-slate-300 hover:text-red-400 transition-colors">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {selected && !open && (
        <div className="mt-1.5 px-3 py-2 bg-indigo-50 border border-indigo-100 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-200 text-indigo-700 flex items-center justify-center text-xs font-black">
              {selected.name?.[0]?.toUpperCase()}
            </div>
            <div>
              <div className="text-xs font-bold text-indigo-800">{selected.name}</div>
              {selected.phone && <div className="text-xs text-indigo-500">{selected.phone}</div>}
            </div>
          </div>
          <div className="text-right">
            {Number(selected.debt_balance) > 0 && (
              <div className="text-xs font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                Qarz: {fmt(selected.debt_balance)} s
              </div>
            )}
            {Number(selected.loyalty_points) > 0 && (
              <div className="text-xs text-emerald-600 font-semibold mt-0.5">
                🏆 {fmt(selected.loyalty_points)} ball
              </div>
            )}
          </div>
        </div>
      )}

      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden max-h-72 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-5 text-center text-sm text-slate-400">Mijoz topilmadi</div>
          ) : filtered.map(c => (
            <button key={c.id} onMouseDown={() => { onChange(c.id); setQ(''); setOpen(false); }}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-indigo-50 border-b border-slate-50 last:border-0 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">
                  {c.name?.[0]?.toUpperCase()}
                </div>
                <div className="text-left">
                  <div className="text-sm font-bold text-slate-800">{c.name}</div>
                  <div className="text-xs text-slate-400">{c.phone || '—'}</div>
                </div>
              </div>
              <div className="text-right shrink-0">
                {Number(c.debt_balance) > 0 && (
                  <div className="text-xs font-bold text-red-500">-{fmt(c.debt_balance)} s</div>
                )}
                {Number(c.debt_limit) > 0 && (
                  <div className="text-xs text-slate-400">limit: {fmt(c.debt_limit)} s</div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Mahsulot qidiruv ──────────────────────────────────── */
function ProductSearch({ onSelect }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setLoading(true);
      api.get('/products/pos-list', { params: { search: q, limit: 12 } })
        .then(r => setResults(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
        .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timerRef.current);
  }, [q]);

  const select = (p) => {
    onSelect(p);
    setQ('');
    setResults([]);
    setActiveIdx(0);
    inputRef.current?.focus();
  };

  const handleKey = (e) => {
    if (!results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    if (e.key === 'Enter' && results[activeIdx]) { e.preventDefault(); select(results[activeIdx]); }
    if (e.key === 'Escape') { setResults([]); setQ(''); }
  };

  return (
    <div className="relative">
      <div className={`flex items-center gap-2 border-2 rounded-xl px-3 py-3 bg-white transition-all ${q ? 'border-indigo-500 ring-4 ring-indigo-100' : 'border-slate-200'}`}>
        {loading
          ? <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin shrink-0" />
          : <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-4 h-4 text-slate-400 shrink-0" />
        }
        <input
          ref={inputRef}
          value={q}
          onChange={e => { setQ(e.target.value); setActiveIdx(0); }}
          onKeyDown={handleKey}
          placeholder="Mahsulot nomi, SKU yoki barkod..."
          className="flex-1 text-sm outline-none bg-transparent placeholder:text-slate-400"
          autoFocus
        />
        {q && (
          <button onClick={() => { setQ(''); setResults([]); inputRef.current?.focus(); }} className="text-slate-300 hover:text-red-400">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {results.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden max-h-80 overflow-y-auto">
          {results.map((p, i) => (
            <button key={p.id} onMouseDown={() => select(p)}
              className={`w-full flex items-center gap-3 px-4 py-3 border-b border-slate-50 last:border-0 transition-colors text-left ${i === activeIdx ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}>
              <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 overflow-hidden">
                {p.image_url
                  ? <img src={p.image_url} alt="" className="w-full h-full object-cover" />
                  : <Ic d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" cls="w-4 h-4 text-slate-400" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-slate-800 truncate">{p.name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  {p.sku && <span className="text-xs text-slate-400 font-mono">{p.sku}</span>}
                  {p.barcode && <span className="text-xs text-slate-300">|</span>}
                  {p.barcode && <span className="text-xs text-slate-400 font-mono">{p.barcode}</span>}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-sm font-black text-indigo-700">{fmt(p.wholesale_price || p.sale_price)} s</div>
                {p.wholesale_price && p.sale_price !== p.wholesale_price && (
                  <div className="text-xs text-slate-400 line-through">{fmt(p.sale_price)} s</div>
                )}
                <div className={`text-xs font-semibold mt-0.5 ${Number(p.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                  {fmt(p.stock_quantity)} {p.unit || 'dona'}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Asosiy komponent ──────────────────────────────────── */
export default function UlgurjiSotuv() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);

  // Settings
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoPrint, setAutoPrint] = useState(localStorage.getItem('ulgurji_autoPrint') !== 'false');
  const [receiptWidth, setReceiptWidth] = useState(localStorage.getItem('ulgurji_receiptWidth') || '80');
  const [defaultCustomerId, setDefaultCustomerId] = useState(localStorage.getItem('ulgurji_defaultCustomer') || '');

  const [custId, setCustId] = useState(localStorage.getItem('ulgurji_defaultCustomer') || '');
  const [warehouseId, setWarehouseId] = useState('');
  const [cart, setCart] = useState([]);          // [{id, name, unit, qty, price, discount_type, discount_val, wholesale_price, sale_price, stock_quantity}]
  const [note, setNote] = useState('');
  const [useWholesale, setUseWholesale] = useState(true);
  const [showPayment, setShowPayment] = useState(false);
  const [saving, setSaving] = useState(false);

  const saveSettings = () => {
    localStorage.setItem('ulgurji_autoPrint', autoPrint);
    localStorage.setItem('ulgurji_receiptWidth', receiptWidth);
    localStorage.setItem('ulgurji_defaultCustomer', defaultCustomerId);
    setSettingsOpen(false);
    if (!cart.length && defaultCustomerId) setCustId(defaultCustomerId);
    toast.success('Sozlamalar saqlandi');
  };

  // To'lov formasi
  const [payType, setPayType] = useState('cash');
  const [paidAmt, setPaidAmt] = useState('');
  const [paidCash, setPaidCash] = useState('');
  const [paidCard, setPaidCard] = useState('');
  const [discType, setDiscType] = useState('pct');
  const [discVal, setDiscVal] = useState('');
  const [payNote, setPayNote] = useState('');
  const [debtDate, setDebtDate] = useState('');
  const [showDebtDate, setShowDebtDate] = useState(false);

  // Sotuv ro'yxati
  const [tab, setTab] = useState('new'); // 'new' | 'list'
  const [sales, setSales] = useState([]);
  const [loadingSales, setLoadingSales] = useState(false);
  const [filters, setFilters] = useState({ date_from: today(), date_to: today(), status: '', search: '' });
  const [selectedSale, setSelectedSale] = useState(null);
  const [page, setPage] = useState(0);
  const LIMIT = 25;

  useEffect(() => {
    api.get('/customers/?limit=200').then(r => setCustomers(Array.isArray(r.data) ? r.data : (r.data?.items || []))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/warehouses/').then(r => setWarehouses(Array.isArray(r.data) ? r.data : [])).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const loadSales = useCallback(() => {
    setLoadingSales(true);
    const params = { skip: page * LIMIT, limit: LIMIT, ...filters };
    if (!params.status) delete params.status;
    if (!params.search) delete params.search;
    api.get('/sales/', { params })
      .then(r => setSales(Array.isArray(r.data) ? r.data : []))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
      .finally(() => setLoadingSales(false));
  }, [filters, page]);

  useEffect(() => { if (tab === 'list') loadSales(); }, [tab, loadSales]);

  /* ── Cart operations ── */
  const addToCart = useCallback((p) => {
    const price = useWholesale && p.wholesale_price ? Number(p.wholesale_price) : Number(p.sale_price || 0);
    setCart(prev => {
      const ex = prev.find(i => i.product_id === p.id);
      if (ex) return prev.map(i => i.product_id === p.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, {
        product_id: p.id,
        name: p.name,
        unit: p.unit || 'dona',
        qty: 1,
        price,
        discount_type: 'pct',
        discount_val: 0,
        wholesale_price: Number(p.wholesale_price || 0),
        sale_price: Number(p.sale_price || 0),
        stock_quantity: Number(p.stock_quantity || 0),
        image_url: p.image_url,
      }];
    });
  }, [useWholesale]);

  const updateItem = (idx, field, val) => setCart(prev => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));
  const removeItem = (idx) => setCart(prev => prev.filter((_, i) => i !== idx));

  const itemNet = (it) => {
    const gross = it.price * it.qty;
    const disc = it.discount_type === 'pct' ? gross * (parseN(it.discount_val) / 100) : parseN(it.discount_val);
    return Math.max(0, gross - disc);
  };

  const subtotal = cart.reduce((s, it) => s + itemNet(it), 0);
  const saleDisc = discType === 'pct' ? subtotal * (parseN(discVal) / 100) : parseN(discVal);
  const total = Math.max(0, subtotal - saleDisc);
  const paid = payType === 'mixed' ? (parseN(paidCash) + parseN(paidCard)) : parseN(paidAmt);
  const debt = Math.max(0, total - paid);
  const change = Math.max(0, paid - total);

  const selectedCustomer = customers.find(c => String(c.id) === String(custId));

  /* ── To'lovni qabul qilish ── */
  const handlePay = async () => {
    if (!cart.length) return toast.error('Savat bo\'sh!');
    if (debt > 0 && !custId) return toast.error('Qarzga sotish uchun mijoz tanlang!');
    if (debt > 0 && !debtDate && showDebtDate) return toast.error('Qarz muddat sanasini kiriting!');

    if (debt > 0 && !showDebtDate) { setShowDebtDate(true); return; }

    setSaving(true);
    try {
      const items = cart.map(it => ({
        product_id: it.product_id,
        quantity: it.qty,
        unit_price: it.price,
        discount: it.discount_type === 'pct'
          ? it.price * it.qty * (parseN(it.discount_val) / 100)
          : parseN(it.discount_val),
      }));

      let finalPayType = payType;
      if (paid === 0) finalPayType = 'debt'; // agar to'lanmasa, 'debt'

      const payload = {
        items,
        payment_type: finalPayType,
        paid_amount: paid,
        paid_cash: finalPayType === 'mixed' ? parseN(paidCash) : (finalPayType === 'cash' ? paid : 0),
        paid_card: finalPayType === 'mixed' ? parseN(paidCard) : (finalPayType === 'card' ? paid : 0),
        discount_amount: saleDisc,
        note: note || payNote || undefined,
        customer_id: custId ? Number(custId) : undefined,
        warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        debt_due_date: debt > 0 ? (debtDate || undefined) : undefined,
      };

      const res = await api.post('/sales/', payload);
      toast.success('Sotuv muvaffaqiyatli saqlandi!');

      // Chek chiqarish
      if (autoPrint) {
        try {
          const receiptRes = await api.get(`/sales/${res.data.id}/receipt`);
          const html = buildReceiptHtml(receiptRes.data, receiptWidth);
          printReceiptHtml(html, receiptWidth);
        } catch (err) {
          console.error("Chek chiqarishda xatolik", err);
        }
      }

      // Reset
      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDiscVal(''); setPaidAmt('');
      setPaidCash(''); setPaidCard(''); setPayNote(''); setDebtDate('');
      setShowPayment(false); setShowDebtDate(false); setPayType('cash');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Saqlashda xatolik');
    } finally { setSaving(false); }
  };

  /* ══════════════════════════════════════════════════
     RENDER
  ══════════════════════════════════════════════════ */
  return (
    <div className="h-screen flex flex-col bg-slate-50 overflow-hidden">

      {/* ── TOP NAV ── */}
      <div className="shrink-0 bg-white border-b border-slate-200 px-5 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200">
            <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-base font-black text-slate-800">Ulgurji Sotuv</h1>
            <p className="text-xs text-slate-400">B2B · Yirik savdo</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button onClick={() => setSettingsOpen(true)}
            className={`flex items-center justify-center w-9 h-9 rounded-xl text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors tooltip`} title="Sotuv sozlamalari">
            <Ic d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </button>
          {[
            { id: 'new',  label: '+ Yangi sotuv', icon: 'M12 4v16m8-8H4' },
            { id: 'list', label: 'Sotuvlar tarixi', icon: 'M4 6h16M4 10h16M4 14h16M4 18h16' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${tab === t.id ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              <Ic d={t.icon} cls="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ══ YANGI SOTUV ══════════════════════════════════════════ */}
      {tab === 'new' && (
        <div className="flex-1 flex overflow-hidden">

          {/* ── CHAP PANEL: Mahsulotlar ── */}
          <div className="flex-1 flex flex-col overflow-hidden border-r border-slate-200">

            {/* Search + toolbar */}
            <div className="shrink-0 bg-white px-4 pt-4 pb-3 border-b border-slate-100 space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <ProductSearch onSelect={addToCart} />
                </div>
                {/* Ulgurji narx toggle */}
                <button
                  onClick={() => {
                    setUseWholesale(v => !v);
                    setCart(prev => prev.map(it => ({
                      ...it,
                      price: (!useWholesale && it.wholesale_price) ? it.wholesale_price : it.sale_price,
                    })));
                  }}
                  className={`shrink-0 flex items-center gap-2 px-3 py-2.5 rounded-xl border-2 text-sm font-bold transition-all ${useWholesale ? 'bg-indigo-600 border-indigo-600 text-white shadow-md shadow-indigo-200' : 'bg-white border-slate-200 text-slate-500'}`}>
                  <Ic d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" cls="w-4 h-4" />
                  Ulgurji
                </button>

                {/* Ombor tanlash */}
                {warehouses.length > 0 && (
                  <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
                    className="shrink-0 border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white">
                    <option value="">Barcha omborlar</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                )}
              </div>
            </div>

            {/* Cart table */}
            <div className="flex-1 overflow-y-auto">
              {cart.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-4 text-slate-300">
                  <div className="w-20 h-20 rounded-3xl bg-slate-100 flex items-center justify-center">
                    <Ic d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" cls="w-8 h-8" />
                  </div>
                  <div className="text-center">
                    <p className="font-bold text-slate-400">Savat bo'sh</p>
                    <p className="text-sm text-slate-300 mt-1">Mahsulot qidiring va qo'shing</p>
                  </div>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10">
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="text-left px-4 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide">#</th>
                      <th className="text-left px-3 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide">Mahsulot</th>
                      <th className="text-center px-3 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide w-28">Miqdor</th>
                      <th className="text-right px-3 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide w-32">Narx</th>
                      <th className="text-center px-3 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide w-36">Chegirma</th>
                      <th className="text-right px-3 py-3 text-xs font-bold text-slate-500 uppercase tracking-wide w-32">Jami</th>
                      <th className="w-10 px-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {cart.map((it, idx) => {
                      const net = itemNet(it);
                      const hasDiscount = parseN(it.discount_val) > 0;
                      return (
                        <tr key={idx} className="hover:bg-indigo-50/30 group transition-colors">
                          <td className="px-4 py-3 text-xs text-slate-400 font-mono">{idx + 1}</td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-2.5">
                              <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 overflow-hidden">
                                {it.image_url
                                  ? <img src={it.image_url} alt="" className="w-full h-full object-cover rounded-xl" />
                                  : <span className="text-sm font-black text-slate-400">{it.name?.[0]}</span>
                                }
                              </div>
                              <div>
                                <div className="font-bold text-slate-800 text-sm leading-tight">{it.name}</div>
                                <div className="text-xs text-slate-400 mt-0.5">{it.unit}</div>
                              </div>
                            </div>
                          </td>

                          {/* Miqdor */}
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-1 justify-center">
                              <button onClick={() => updateItem(idx, 'qty', Math.max(0.1, it.qty - 1))}
                                className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 font-bold transition-colors">
                                <Ic d="M20 12H4" cls="w-3 h-3" />
                              </button>
                              <input
                                type="number"
                                value={it.qty}
                                onChange={e => updateItem(idx, 'qty', Math.max(0.01, parseFloat(e.target.value) || 1))}
                                className="w-16 text-center font-black text-slate-800 border border-slate-200 rounded-lg py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                              />
                              <button onClick={() => updateItem(idx, 'qty', it.qty + 1)}
                                className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 font-bold transition-colors">
                                <Ic d="M12 4v16m8-8H4" cls="w-3 h-3" />
                              </button>
                            </div>
                          </td>

                          {/* Narx */}
                          <td className="px-3 py-3">
                            <div className="relative">
                              <input
                                type="number"
                                value={it.price}
                                onChange={e => updateItem(idx, 'price', parseFloat(e.target.value) || 0)}
                                className="w-full text-right font-bold text-slate-800 border border-slate-200 rounded-lg py-1.5 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                              />
                              <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-400">s</span>
                            </div>
                            {it.wholesale_price > 0 && it.price !== it.wholesale_price && (
                              <div className="text-xs text-indigo-500 text-right mt-0.5 font-semibold cursor-pointer hover:text-indigo-700"
                                onClick={() => updateItem(idx, 'price', it.wholesale_price)}>
                                ↑ ulgurji: {fmt(it.wholesale_price)}
                              </div>
                            )}
                          </td>

                          {/* Chegirma */}
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => updateItem(idx, 'discount_type', it.discount_type === 'pct' ? 'amt' : 'pct')}
                                className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-amber-100 text-slate-600 hover:text-amber-700 flex items-center justify-center text-xs font-black transition-colors border border-slate-200">
                                {it.discount_type === 'pct' ? '%' : 's'}
                              </button>
                              <input
                                type="number"
                                value={it.discount_val || ''}
                                onChange={e => updateItem(idx, 'discount_val', parseFloat(e.target.value) || 0)}
                                placeholder="0"
                                className={`w-16 text-center font-semibold border rounded-lg py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300 ${hasDiscount ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-slate-200 text-slate-600'}`}
                              />
                            </div>
                          </td>

                          {/* Jami */}
                          <td className="px-3 py-3 text-right">
                            <div className="font-black text-slate-800">{fmt(net)} s</div>
                            {hasDiscount && (
                              <div className="text-xs text-slate-400 line-through">{fmt(it.price * it.qty)} s</div>
                            )}
                          </td>

                          {/* O'chirish */}
                          <td className="px-2 py-3">
                            <button onClick={() => removeItem(idx)}
                              className="w-7 h-7 rounded-lg text-slate-300 hover:bg-red-50 hover:text-red-500 flex items-center justify-center transition-colors opacity-0 group-hover:opacity-100">
                              <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  {/* Subtotal row */}
                  <tfoot>
                    <tr className="bg-slate-50 border-t-2 border-slate-200">
                      <td colSpan={5} className="px-4 py-3 text-sm font-bold text-slate-600">
                        Jami {cart.length} ta mahsulot · {cart.reduce((s, i) => s + i.qty, 0).toFixed(1)} birlik
                      </td>
                      <td className="px-3 py-3 text-right font-black text-lg text-indigo-700">
                        {fmt(subtotal)} s
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              )}
            </div>
          </div>

          {/* ── O'NG PANEL: Mijoz + To'lov ── */}
          <div className="w-[360px] shrink-0 flex flex-col bg-white border-l border-slate-200">
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">

              {/* Mijoz */}
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Mijoz (Kontragent)</label>
                <CustomerSearch customers={customers} value={custId} onChange={setCustId} />
              </div>

              {/* Izoh */}
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Izoh</label>
                <textarea
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Shartnoma raqami, izoh..."
                  rows={2}
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
                />
              </div>

              {/* Chegirma (butun sotuv) */}
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Sotuv chegirmasi</label>
                <div className="flex gap-2">
                  <div className="flex rounded-xl border-2 border-slate-200 overflow-hidden">
                    {['pct', 'amt'].map(t => (
                      <button key={t} onClick={() => setDiscType(t)}
                        className={`px-3 py-2 text-xs font-bold transition-colors ${discType === t ? 'bg-amber-500 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'}`}>
                        {t === 'pct' ? '%' : "So'm"}
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    value={discVal}
                    onChange={e => setDiscVal(e.target.value)}
                    placeholder={discType === 'pct' ? 'Foiz...' : 'Miqdor...'}
                    className="flex-1 border-2 border-slate-200 rounded-xl px-3 py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>
                {saleDisc > 0 && (
                  <p className="text-xs text-amber-600 font-semibold mt-1.5">
                    − {fmt(saleDisc)} s chegirma qo'llaniladi
                  </p>
                )}
              </div>

              {/* Divider */}
              <div className="border-t border-slate-100" />

              {/* Jami hisob */}
              <div className="bg-slate-50 rounded-2xl p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Mahsulotlar jami</span>
                  <span className="font-bold text-slate-700">{fmt(subtotal)} s</span>
                </div>
                {saleDisc > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-amber-600">Chegirma</span>
                    <span className="font-bold text-amber-600">− {fmt(saleDisc)} s</span>
                  </div>
                )}
                <div className="border-t border-slate-200 pt-2 flex justify-between">
                  <span className="font-bold text-slate-700">Umumiy summa</span>
                  <span className="text-xl font-black text-indigo-700">{fmt(total)} s</span>
                </div>
              </div>
            </div>

            {/* To'lov tugmasi doim pastda ko'rinib turadi */}
            <div className="shrink-0 px-4 pb-4 pt-3 border-t border-slate-100 bg-white shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
              <button
                onClick={() => cart.length > 0 && setShowPayment(true)}
                disabled={cart.length === 0}
                className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-black text-base rounded-2xl shadow-lg shadow-indigo-200 transition-all flex items-center justify-center gap-2">
                <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-5 h-5" />
                To'lovni qabul qilish · {fmt(total)} s
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══ SOTUVLAR TARIXI ══════════════════════════════════════ */}
      {tab === 'list' && (
        <div className="flex-1 overflow-hidden flex flex-col p-4 gap-4">
          {/* Filterlar */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 flex flex-wrap gap-3 items-center">
            <input type="date" value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            <input type="date" value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white">
              <option value="">Barcha holatlar</option>
              <option value="completed">Yakunlandi</option>
              <option value="pending">Kutilmoqda</option>
              <option value="cancelled">Bekor</option>
            </select>
            <input value={filters.search} onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
              placeholder="Sotuv raqami..." className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 w-44" />
            <button onClick={loadSales}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5">
              <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-3.5 h-3.5" />
              Qidirish
            </button>
          </div>

          {/* Jadval */}
          <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-auto">
            {loadingSales ? (
              <div className="flex justify-center items-center h-64">
                <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                  <tr>
                    {['#', 'Sotuv raqami', 'Mijoz', 'Jami', "To'langan", 'Qarz', "To'lov", 'Holat', 'Kassir', 'Sana', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {sales.length === 0 && (
                    <tr><td colSpan={11} className="text-center py-16 text-slate-400">Sotuvlar topilmadi</td></tr>
                  )}
                  {sales.map((s, i) => {
                    const dbt = Number(s.total_amount) - Number(s.paid_amount);
                    return (
                      <tr key={s.id} onClick={() => setSelectedSale(s)}
                        className="hover:bg-indigo-50/40 cursor-pointer transition-colors group">
                        <td className="px-4 py-3 text-xs text-slate-400">{i + 1 + page * LIMIT}</td>
                        <td className="px-4 py-3">
                          <span className="font-mono font-black text-indigo-700 text-xs bg-indigo-50 px-2.5 py-1 rounded-lg border border-indigo-100">
                            {s.number}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {s.customer_name
                            ? <div className="flex items-center gap-2">
                                <div className="w-7 h-7 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">
                                  {s.customer_name[0]}
                                </div>
                                <span className="font-semibold text-slate-700">{s.customer_name}</span>
                              </div>
                            : <span className="text-slate-400 text-xs">—</span>
                          }
                        </td>
                        <td className="px-4 py-3 font-black text-slate-800 text-right whitespace-nowrap">{fmt(s.total_amount)} s</td>
                        <td className="px-4 py-3 font-bold text-emerald-700 text-right whitespace-nowrap">{fmt(s.paid_amount)} s</td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {dbt > 0
                            ? <span className="font-bold text-red-600">{fmt(dbt)} s</span>
                            : <span className="text-slate-300">—</span>
                          }
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                            {PAY_META[s.payment_type] || s.payment_type}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${STATUS_META[s.status]?.c || 'bg-slate-100 text-slate-500'}`}>
                            {STATUS_META[s.status]?.l || s.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-slate-500">{s.cashier_name}</td>
                        <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                          {s.created_at ? new Date(s.created_at).toLocaleDateString('uz-UZ', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' }) : '—'}
                        </td>
                        <td className="px-2 py-3">
                          <Ic d="M9 5l7 7-7 7" cls="w-4 h-4 text-slate-300 group-hover:text-indigo-400 transition-colors" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {/* Summariya */}
                {sales.length > 0 && (
                  <tfoot>
                    <tr className="bg-indigo-50 border-t-2 border-indigo-100">
                      <td colSpan={3} className="px-4 py-3 text-xs font-bold text-indigo-700">{sales.length} ta sotuv</td>
                      <td className="px-4 py-3 text-right font-black text-indigo-800 whitespace-nowrap">
                        {fmt(sales.reduce((s, x) => s + Number(x.total_amount), 0))} s
                      </td>
                      <td className="px-4 py-3 text-right font-black text-emerald-700 whitespace-nowrap">
                        {fmt(sales.reduce((s, x) => s + Number(x.paid_amount), 0))} s
                      </td>
                      <td className="px-4 py-3 text-right font-black text-red-600 whitespace-nowrap">
                        {fmt(sales.reduce((s, x) => s + Math.max(0, Number(x.total_amount) - Number(x.paid_amount)), 0))} s
                      </td>
                      <td colSpan={5} />
                    </tr>
                  </tfoot>
                )}
              </table>
            )}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
              className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">
              ← Oldingi
            </button>
            <span className="text-sm text-slate-500 font-semibold">{page + 1}-sahifa</span>
            <button disabled={sales.length < LIMIT} onClick={() => setPage(p => p + 1)}
              className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">
              Keyingi →
            </button>
          </div>
        </div>
      )}

      {/* ══ TO'LOV MODALI ════════════════════════════════════════ */}
      {showPayment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden">

            {/* Header */}
            <div className="bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-5 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-black">To'lovni qabul qilish</h2>
                  <p className="text-sm text-white/70 mt-0.5">Umumiy summa: {fmt(total)} so'm</p>
                </div>
                <button onClick={() => { setShowPayment(false); setShowDebtDate(false); }}
                  className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center transition-colors">
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="px-6 py-5 space-y-5 max-h-[70vh] overflow-y-auto">

              {/* To'lov turi */}
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3 block">To'lov turi</label>
                <div className="grid grid-cols-5 gap-2">
                  {PAY_TYPES.map(pt => (
                    <button key={pt.id} onClick={() => setPayType(pt.id)}
                      className={`flex flex-col items-center gap-1.5 p-2.5 rounded-xl border-2 text-xs font-bold transition-all ${payType === pt.id ? pt.color + ' shadow-md scale-105' : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'}`}>
                      <span className="text-lg">{pt.icon}</span>
                      <span className="leading-tight text-center">{pt.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Miqdor */}
              {payType === 'mixed' ? (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-bold text-slate-500 mb-1.5 block">Naqd (so'm)</label>
                    <input type="number" value={paidCash} onChange={e => setPaidCash(e.target.value)} placeholder="0"
                      className="w-full border-2 border-emerald-300 rounded-xl px-4 py-3 text-lg font-black text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400" />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-500 mb-1.5 block">Karta (so'm)</label>
                    <input type="number" value={paidCard} onChange={e => setPaidCard(e.target.value)} placeholder="0"
                      className="w-full border-2 border-blue-300 rounded-xl px-4 py-3 text-lg font-black text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400" />
                  </div>
                </div>
              ) : payType !== 'debt' ? (
                <div>
                  <label className="text-xs font-bold text-slate-500 mb-1.5 block">To'lov miqdori (so'm)</label>
                  <div className="relative">
                    <input type="number" value={paidAmt} onChange={e => setPaidAmt(e.target.value)} placeholder="0"
                      className="w-full border-2 border-indigo-300 rounded-xl px-4 py-3 text-xl font-black text-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 pr-28" />
                    <button onClick={() => setPaidAmt(String(total))}
                      className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1.5 bg-indigo-100 hover:bg-indigo-200 text-indigo-700 text-xs font-bold rounded-lg transition-colors">
                      To'liq
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-amber-50 border-2 border-amber-200 rounded-xl p-4 text-center">
                  <p className="text-sm font-bold text-amber-700">Butun summa qarzga yoziladi</p>
                  <p className="text-2xl font-black text-amber-800 mt-1">{fmt(total)} s</p>
                  {!custId && <p className="text-xs text-red-500 font-semibold mt-2">⚠ Mijoz tanlanmagan!</p>}
                </div>
              )}

              {/* Qarz sanasi */}
              {showDebtDate && debt > 0 && (
                <div className="bg-amber-50 border-2 border-amber-200 rounded-xl p-4 space-y-3">
                  <div className="flex items-center gap-2 text-amber-700">
                    <Ic d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" cls="w-5 h-5" />
                    <span className="font-bold">Qarz: {fmt(debt)} s</span>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-amber-700 mb-1.5 block">To'lov muddati (ixtiyoriy)</label>
                    <input type="date" min={today()} value={debtDate} onChange={e => setDebtDate(e.target.value)}
                      className="w-full border-2 border-amber-300 rounded-xl px-3 py-2.5 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-amber-400" />
                  </div>
                </div>
              )}

              {/* Hisob-kitob */}
              <div className="bg-slate-50 rounded-2xl p-4 space-y-2.5">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Jami summa</span>
                  <span className="font-bold">{fmt(total)} s</span>
                </div>
                {saleDisc > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-amber-600">Chegirma</span>
                    <span className="font-bold text-amber-600">− {fmt(saleDisc)} s</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">To'landi</span>
                  <span className="font-bold text-emerald-600">{fmt(payType === 'debt' ? 0 : paid)} s</span>
                </div>
                {debt > 0 && (
                  <div className="flex justify-between text-sm border-t border-slate-200 pt-2.5">
                    <span className="font-bold text-red-600">Qarz</span>
                    <span className="font-black text-red-600">{fmt(payType === 'debt' ? total : debt)} s</span>
                  </div>
                )}
                {change > 0 && (
                  <div className="flex justify-between text-sm border-t border-slate-200 pt-2.5">
                    <span className="font-bold text-blue-600">Qaytim</span>
                    <span className="font-black text-blue-600">{fmt(change)} s</span>
                  </div>
                )}
              </div>

              {/* Izoh */}
              <div>
                <label className="text-xs font-bold text-slate-500 mb-1.5 block">To'lov izohi (ixtiyoriy)</label>
                <input value={payNote} onChange={e => setPayNote(e.target.value)} placeholder="Qo'shimcha ma'lumot..."
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => { setShowPayment(false); setShowDebtDate(false); }}
                className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl text-sm transition-all">
                Bekor
              </button>
              <button onClick={handlePay} disabled={saving}
                className="flex-2 px-8 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-black rounded-2xl text-sm shadow-lg shadow-indigo-200 transition-all flex items-center gap-2">
                {saving
                  ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Saqlanmoqda...</>
                  : <><Ic d="M5 13l4 4L19 7" cls="w-4 h-4" /> Sotuvni tasdiqlash</>
                }
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══ SOTUV TAFSILOTI MODALI ════════════════════════════════ */}
      {selectedSale && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <div>
                <h2 className="font-black text-lg font-mono">{selectedSale.number}</h2>
                <p className="text-sm text-white/60 mt-0.5">
                  {selectedSale.cashier_name} · {new Date(selectedSale.created_at).toLocaleDateString('uz-UZ')}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-3 py-1.5 rounded-full ${STATUS_META[selectedSale.status]?.c || 'bg-white/20 text-white'}`}>
                  {STATUS_META[selectedSale.status]?.l}
                </span>
                <button onClick={() => setSelectedSale(null)}
                  className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center transition-colors">
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              <SaleDetailContent saleId={selectedSale.id} />
            </div>
          </div>
        </div>
      )}

      {/* ══ SOZLAMALAR MODALI ════════════════════════════════ */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm overflow-hidden flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <h2 className="text-lg font-black">Sotuv sozlamalari</h2>
              <button onClick={() => setSettingsOpen(false)}
                className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center transition-colors">
                <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
              </button>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Doimiy mijoz (Standart)</label>
                <CustomerSearch customers={customers} value={defaultCustomerId} onChange={setDefaultCustomerId} />
                <p className="text-[11px] text-slate-400 mt-1">Yangi sotuv sahifasi ochilganda shu mijoz avtomatik tanlanadi.</p>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-800">Avtomatik chek chiqarish</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">To'lov tugashi bilan avtomatik print</p>
                </div>
                <button onClick={() => setAutoPrint(!autoPrint)}
                  className={`w-12 h-6 rounded-full p-1 transition-colors focus:outline-none ${autoPrint ? 'bg-indigo-500' : 'bg-slate-300'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform ${autoPrint ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Chek formati</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: '58', label: '58 mm' },
                    { id: '80', label: '80 mm' },
                    { id: 'A4', label: 'A4' },
                  ].map(w => (
                    <button key={w.id} onClick={() => setReceiptWidth(w.id)}
                      className={`py-2 text-sm font-semibold rounded-xl border-2 transition-colors ${receiptWidth === w.id ? 'border-indigo-500 text-indigo-700 bg-indigo-50' : 'border-slate-100 text-slate-500 hover:border-slate-300'}`}>
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setSettingsOpen(false)}
                className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl text-sm transition-all focus:outline-none">Bekor</button>
              <button onClick={saveSettings}
                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl text-sm transition-all shadow-md shadow-indigo-200 focus:outline-none">Saqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Sotuv tafsiloti kontenti ── */
function SaleDetailContent({ saleId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/sales/${saleId}`)
      .then(r => setData(r.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
      .finally(() => setLoading(false));
  }, [saleId]);

  if (loading) return <div className="flex justify-center py-16"><div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>;
  if (!data) return <div className="text-center py-16 text-slate-400">Ma'lumot topilmadi</div>;

  const fmt = v => Number(v || 0).toLocaleString('uz-UZ');
  const debt = Number(data.total_amount) - Number(data.paid_amount);

  return (
    <div className="space-y-4">
      {data.note && (
        <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-sm text-blue-700 font-medium">
          📝 {data.note}
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="text-left px-4 py-2.5 text-xs font-bold text-slate-500">Mahsulot</th>
            <th className="text-center px-3 py-2.5 text-xs font-bold text-slate-500">Soni</th>
            <th className="text-right px-3 py-2.5 text-xs font-bold text-slate-500">Narxi</th>
            <th className="text-right px-3 py-2.5 text-xs font-bold text-slate-500">Chegirma</th>
            <th className="text-right px-4 py-2.5 text-xs font-bold text-slate-500">Jami</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {(data.items || []).map(it => (
            <tr key={it.id} className="hover:bg-slate-50">
              <td className="px-4 py-3 font-semibold text-slate-800">{it.product_name}</td>
              <td className="px-3 py-3 text-center text-slate-600">{it.quantity}</td>
              <td className="px-3 py-3 text-right text-slate-600">{fmt(it.unit_price)} s</td>
              <td className="px-3 py-3 text-right text-amber-600">{it.discount > 0 ? `−${fmt(it.discount)} s` : '—'}</td>
              <td className="px-4 py-3 text-right font-bold text-slate-800">{fmt(it.subtotal)} s</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-200 bg-slate-50">
            <td colSpan={4} className="px-4 py-3 font-bold text-slate-700 text-right">Chegirma</td>
            <td className="px-4 py-3 font-bold text-amber-600 text-right">−{fmt(data.discount_amount)} s</td>
          </tr>
          <tr className="bg-indigo-50">
            <td colSpan={4} className="px-4 py-3 font-black text-indigo-800 text-right">Jami</td>
            <td className="px-4 py-3 font-black text-indigo-800 text-right text-lg">{fmt(data.total_amount)} s</td>
          </tr>
          <tr>
            <td colSpan={4} className="px-4 py-3 font-bold text-emerald-700 text-right">To'langan</td>
            <td className="px-4 py-3 font-bold text-emerald-700 text-right">{fmt(data.paid_amount)} s</td>
          </tr>
          {debt > 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-3 font-bold text-red-600 text-right">Qarz</td>
              <td className="px-4 py-3 font-bold text-red-600 text-right">{fmt(debt)} s</td>
            </tr>
          )}
        </tfoot>
      </table>
    </div>
  );
}
