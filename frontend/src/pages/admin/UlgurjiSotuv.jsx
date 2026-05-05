/**
 * UlgurjiSotuv — Ulgurji (wholesale) sotuv sahifasi
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';
import { buildReceiptHtml, printReceiptHtml, getReceiptSettings, saveReceiptSettings } from '../../utils/receiptBuilder';
import { toast } from '../../utils/toast';
import { useActiveShift } from '../../hooks/useActiveShift';
import ShiftOpenModal from '../../components/ShiftOpenModal';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const today = () => new Date().toISOString().slice(0, 10);
const parseN = (s) => parseFloat(String(s || '').replace(/\s/g, '')) || 0;

const PAY_ICONS = {
  cash: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="6" width="20" height="13" rx="2"/><circle cx="12" cy="12.5" r="2.5"/><path d="M6 9.5h.01M18 9.5h.01M6 15.5h.01M18 15.5h.01"/></svg>),
  card: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/></svg>),
  uzcard: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><circle cx="17" cy="15" r="1.5"/><circle cx="14" cy="15" r="1.5"/></svg>),
  humo: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><path d="M6 15h3M15 15h3"/></svg>),
  bank: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18M3 10h18M5 10V21M19 10V21M10 10V21M14 10V21M12 3L2 10h20L12 3z"/></svg>),
  click: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></svg>),
  payme: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M10 7h4M10 11h4M10 15h2"/></svg>),
  uzum: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/><path d="M8 12h8M12 8v8"/></svg>),
  debt: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/></svg>),
  mixed: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M16 3h5v5M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg>),
};

const PAY_TYPES = [
  { id: 'cash',   label: 'Naqd',    accent: 'emerald' },
  { id: 'card',   label: 'Karta',   accent: 'blue'    },
  { id: 'uzcard', label: 'Uzcard',  accent: 'blue'    },
  { id: 'humo',   label: 'Humo',    accent: 'violet'  },
  { id: 'bank',   label: 'Bank',    accent: 'cyan'    },
  { id: 'click',  label: 'Click',   accent: 'indigo'  },
  { id: 'payme',  label: 'Payme',   accent: 'sky'     },
  { id: 'uzum',   label: 'Uzum',    accent: 'orange'  },
  { id: 'debt',   label: 'Qarzga',  accent: 'amber'   },
  { id: 'mixed',  label: 'Aralash', accent: 'purple'  },
];

const ACCENT_CLS = {
  emerald: { active: 'border-emerald-500 bg-emerald-500 text-white shadow-emerald-200', idle: 'border-slate-200 text-emerald-600 hover:border-emerald-300 hover:bg-emerald-50' },
  blue:    { active: 'border-blue-500 bg-blue-500 text-white shadow-blue-200',          idle: 'border-slate-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50' },
  violet:  { active: 'border-violet-500 bg-violet-500 text-white shadow-violet-200',    idle: 'border-slate-200 text-violet-600 hover:border-violet-300 hover:bg-violet-50' },
  cyan:    { active: 'border-cyan-500 bg-cyan-500 text-white shadow-cyan-200',          idle: 'border-slate-200 text-cyan-600 hover:border-cyan-300 hover:bg-cyan-50' },
  indigo:  { active: 'border-indigo-500 bg-indigo-500 text-white shadow-indigo-200',    idle: 'border-slate-200 text-indigo-600 hover:border-indigo-300 hover:bg-indigo-50' },
  sky:     { active: 'border-sky-500 bg-sky-500 text-white shadow-sky-200',             idle: 'border-slate-200 text-sky-600 hover:border-sky-300 hover:bg-sky-50' },
  orange:  { active: 'border-orange-500 bg-orange-500 text-white shadow-orange-200',    idle: 'border-slate-200 text-orange-600 hover:border-orange-300 hover:bg-orange-50' },
  amber:   { active: 'border-amber-500 bg-amber-500 text-white shadow-amber-200',       idle: 'border-slate-200 text-amber-600 hover:border-amber-300 hover:bg-amber-50' },
  purple:  { active: 'border-purple-500 bg-purple-500 text-white shadow-purple-200',    idle: 'border-slate-200 text-purple-600 hover:border-purple-300 hover:bg-purple-50' },
};

const STATUS_META = {
  completed: { l: 'Yakunlandi', c: 'bg-emerald-100 text-emerald-700' },
  cancelled:  { l: 'Bekor',     c: 'bg-red-100 text-red-600' },
  pending:    { l: 'Kutilmoqda',c: 'bg-amber-100 text-amber-700' },
};
const PAY_META = {
  cash:'Naqd', card:'Karta', uzcard:'Uzcard', humo:'Humo', bank:"Bank o'tkazmasi",
  click:'Click', payme:'Payme', visa:'Visa', uzum:'Uzum', debt:'Qarz', mixed:'Aralash',
};

function Ic({ d, cls = 'w-4 h-4' }) {
  return (
    <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
    </svg>
  );
}

function CustomerSearch({ customers, value, onChange }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => String(c.id) === String(value));
  const filtered = (q.trim() ? customers.filter(c => c.name?.toLowerCase().includes(q.toLowerCase()) || c.phone?.includes(q)) : customers).slice(0, 10);

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
        {selected && <button onClick={() => { onChange(''); setQ(''); }} className="text-slate-300 hover:text-red-400"><Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" /></button>}
      </div>

      {selected && !open && (
        <div className="mt-1.5 px-3 py-2 bg-indigo-50 border border-indigo-100 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-200 text-indigo-700 flex items-center justify-center text-xs font-black">{selected.name?.[0]?.toUpperCase()}</div>
            <div>
              <div className="text-xs font-bold text-indigo-800">{selected.name}</div>
              {selected.phone && <div className="text-xs text-indigo-500">{selected.phone}</div>}
            </div>
          </div>
          <div className="text-right">
            {Number(selected.debt_balance) > 0 && <div className="text-xs font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">Qarz: {fmt(selected.debt_balance)} s</div>}
            {Number(selected.loyalty_points) > 0 && <div className="text-xs text-emerald-600 font-semibold mt-0.5">🏆 {fmt(selected.loyalty_points)} ball</div>}
          </div>
        </div>
      )}

      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden max-h-72 overflow-y-auto">
          {filtered.length === 0
            ? <div className="px-4 py-5 text-center text-sm text-slate-400">Mijoz topilmadi</div>
            : filtered.map(c => (
              <button key={c.id} onMouseDown={() => { onChange(c.id); setQ(''); setOpen(false); }}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-indigo-50 border-b border-slate-50 last:border-0 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">{c.name?.[0]?.toUpperCase()}</div>
                  <div className="text-left">
                    <div className="text-sm font-bold text-slate-800">{c.name}</div>
                    <div className="text-xs text-slate-400">{c.phone || '—'}</div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {Number(c.debt_balance) > 0 && <div className="text-xs font-bold text-red-500">-{fmt(c.debt_balance)} s</div>}
                  {Number(c.debt_limit) > 0 && <div className="text-xs text-slate-400">limit: {fmt(c.debt_limit)} s</div>}
                </div>
              </button>
            ))
          }
        </div>
      )}
    </div>
  );
}

function ProductSearch({ onSelect, placeholder }) {
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
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timerRef.current);
  }, [q]);

  const select = (p) => { onSelect(p); setQ(''); setResults([]); setActiveIdx(0); inputRef.current?.focus(); };

  const handleKey = (e) => {
    if (!results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    if (e.key === 'Enter' && results[activeIdx]) { e.preventDefault(); select(results[activeIdx]); }
    if (e.key === 'Escape') { setResults([]); setQ(''); }
  };

  return (
    <div className="relative">
      <div className={`flex items-center gap-2 border-2 rounded-xl px-3 py-2.5 bg-white transition-all ${q ? 'border-indigo-500 ring-4 ring-indigo-100' : 'border-slate-200 hover:border-slate-300'}`}>
        {loading
          ? <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin shrink-0" />
          : <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-4 h-4 text-slate-400 shrink-0" />
        }
        <input ref={inputRef} value={q}
          onChange={e => { setQ(e.target.value); setActiveIdx(0); }}
          onKeyDown={handleKey}
          placeholder={placeholder || "Mahsulot nomi, SKU yoki barkod..."}
          className="flex-1 text-sm outline-none bg-transparent placeholder:text-slate-400"
        />
        {q && <button onClick={() => { setQ(''); setResults([]); inputRef.current?.focus(); }} className="text-slate-300 hover:text-red-400"><Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" /></button>}
      </div>

      {results.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden max-h-72 overflow-y-auto">
          {results.map((p, i) => (
            <button key={p.id} onMouseDown={() => select(p)}
              className={`w-full flex items-center gap-3 px-4 py-3 border-b border-slate-50 last:border-0 transition-colors text-left ${i === activeIdx ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}>
              <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 overflow-hidden">
                {p.image_url ? <img src={p.image_url} alt="" className="w-full h-full object-cover" /> : <Ic d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" cls="w-4 h-4 text-slate-400" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-slate-800 truncate">{p.name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  {p.sku && <span className="text-xs text-slate-400 font-mono">{p.sku}</span>}
                  {p.barcode && <><span className="text-xs text-slate-300">|</span><span className="text-xs text-slate-400 font-mono">{p.barcode}</span></>}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-sm font-black text-indigo-700">{fmt(p.wholesale_price || p.sale_price)} s</div>
                {p.wholesale_price && p.sale_price !== p.wholesale_price && <div className="text-xs text-slate-400 line-through">{fmt(p.sale_price)} s</div>}
                <div className={`text-xs font-semibold mt-0.5 ${Number(p.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>{fmt(p.stock_quantity)} {p.unit || 'dona'}</div>
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

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoPrint, setAutoPrint] = useState(localStorage.getItem('ulgurji_autoPrint') !== 'false');
  const [receiptWidth, setReceiptWidth] = useState(localStorage.getItem('ulgurji_receiptWidth') || '80');
  const [defaultCustomerId, setDefaultCustomerId] = useState(localStorage.getItem('ulgurji_defaultCustomer') || '');

  const [custId, setCustId] = useState(localStorage.getItem('ulgurji_defaultCustomer') || '');
  const [warehouseId, setWarehouseId] = useState('');
  const [cart, setCart] = useState([]);
  const [note, setNote] = useState('');
  const [useWholesale, setUseWholesale] = useState(true);
  const [showPayment, setShowPayment] = useState(false);
  const [saving, setSaving] = useState(false);
  const { hasShift, reload: reloadShift } = useActiveShift();
  const [showShiftModal, setShowShiftModal] = useState(false);

  // Product entry form
  const [formProduct, setFormProduct] = useState(null);
  const [formPrice, setFormPrice] = useState('');
  const [formQty, setFormQty] = useState('1');
  const [formDiscType, setFormDiscType] = useState('pct');
  const [formDiscVal, setFormDiscVal] = useState('');
  const formQtyRef = useRef(null);

  // Mobile tab: 'form' | 'cart'
  const [mobileTab, setMobileTab] = useState('form');

  // Clock
  const [currentTime, setCurrentTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const saveSettings = () => {
    localStorage.setItem('ulgurji_autoPrint', autoPrint);
    localStorage.setItem('ulgurji_receiptWidth', receiptWidth);
    localStorage.setItem('ulgurji_defaultCustomer', defaultCustomerId);
    setSettingsOpen(false);
    if (!cart.length && defaultCustomerId) setCustId(defaultCustomerId);
    toast.success('Sozlamalar saqlandi');
  };

  const [payType, setPayType] = useState('cash');
  const [curPayAmt, setCurPayAmt] = useState('');
  const [payments, setPayments] = useState([]);
  const [discType, setDiscType] = useState('pct');
  const [discVal, setDiscVal] = useState('');
  const [payNote, setPayNote] = useState('');
  const [debtDate, setDebtDate] = useState('');
  const [showDebtDate, setShowDebtDate] = useState(false);
  const [paidAmt, setPaidAmt] = useState('');
  const [paidCash, setPaidCash] = useState('');
  const [paidCard, setPaidCard] = useState('');
  const [editingSale, setEditingSale] = useState(null);

  const [tab, setTab] = useState('new');
  const [sales, setSales] = useState([]);
  const [loadingSales, setLoadingSales] = useState(false);
  const [filters, setFilters] = useState({ date_from: new Date().toISOString().split('T')[0], date_to: new Date().toISOString().split('T')[0], status: '', search: '' });
  const [selectedSale, setSelectedSale] = useState(null);
  const [page, setPage] = useState(0);
  const LIMIT = 25;
  const [openMenuId, setOpenMenuId] = useState(null);

  const scanBufRef   = useRef('');
  const scanTimeRef  = useRef(0);
  const customersRef = useRef([]);
  const setCustIdRef = useRef(setCustId);
  const addToCartRef = useRef(null);

  const [draftsList, setDraftsList] = useState([]);
  useEffect(() => {
    if (tab === 'drafts') {
      try { setDraftsList(JSON.parse(localStorage.getItem('ulgurji_drafts') || '[]')); } catch(e) { setDraftsList([]); }
    }
  }, [tab]);

  const loadDraft = (idx) => {
    const d = draftsList[idx];
    if (!d) return;
    if (cart.length > 0 && !window.confirm("Hozirgi savatdagi ma'lumotlar o'chib ketadi. Davom etasizmi?")) return;
    setCart(d.cart || []); setCustId(d.custId || ''); setNote(d.note || '');
    if (d.discType) setDiscType(d.discType); setDiscVal(d.discVal || '');
    setTab('new');
    const nd = draftsList.filter((_, i) => i !== idx);
    setDraftsList(nd); localStorage.setItem('ulgurji_drafts', JSON.stringify(nd));
    toast.success("Arxiv savatga yuklandi!");
  };

  const removeDraft = (idx) => {
    if (!window.confirm("Rostdan ham arxivni o'chirib yuborasizmi?")) return;
    const nd = draftsList.filter((_, i) => i !== idx);
    setDraftsList(nd); localStorage.setItem('ulgurji_drafts', JSON.stringify(nd));
  };

  useEffect(() => {
    api.get('/customers/?limit=200').then(r => setCustomers(Array.isArray(r.data) ? r.data : (r.data?.items || []))).catch(() => {});
    api.get('/warehouses/').then(r => setWarehouses(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    api.get('/companies/me/receipt_templates').then(r => {
      const d = r.data?.receipt_templates || {};
      if (Object.keys(d).length) {
        const stored = {};
        if (d.r58) stored.r58 = d.r58;
        if (d.r80) stored.r80 = d.r80;
        if (d.nak) stored.nak = d.nak;
        if (Object.keys(stored).length) saveReceiptSettings(stored);
      }
    }).catch(() => {});
  }, []);

  const loadSales = useCallback(() => {
    setLoadingSales(true);
    const params = { skip: page * LIMIT, limit: LIMIT, ...filters };
    if (!params.status) delete params.status;
    if (!params.search) delete params.search;
    api.get('/sales/', { params })
      .then(r => setSales(Array.isArray(r.data) ? r.data : []))
      .catch(() => {})
      .finally(() => setLoadingSales(false));
  }, [filters, page]);

  useEffect(() => { if (tab === 'list') loadSales(); }, [tab, loadSales]);

  const loadEditSale = async (s) => {
    try {
      if (cart.length > 0 && !window.confirm("Hozirgi savat o'chib ketadi. Davom etasizmi?")) return;
      const r = await api.get(`/sales/${s.id}`);
      const sale = r.data;
      setCart((sale.items || []).map(it => ({
        product_id: it.product_id, name: it.product_name, unit: 'dona',
        qty: Number(it.quantity), price: Number(it.unit_price),
        discount_type: 'sum', discount_val: it.discount > 0 ? String(it.discount) : '',
        wholesale_price: Number(it.unit_price), sale_price: Number(it.unit_price), stock_quantity: 9999,
      })));
      setCustId(sale.customer_id ? String(sale.customer_id) : '');
      setNote(sale.note || ''); setDiscType('sum');
      setDiscVal(sale.discount_amount > 0 ? String(sale.discount_amount) : '');
      setEditingSale({ id: sale.id, number: sale.number, warehouse_id: sale.warehouse_id });
      setTab('new'); setOpenMenuId(null);
      toast.success(`"${sale.number}" sotuv tahrirlash uchun yuklandi`);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Sotuvni yuklashda xatolik'); }
  };

  const deleteSale = async (id) => {
    if (!window.confirm("Sotuvni o'chirishni tasdiqlaysizmi?")) return;
    try { await api.delete(`/sales/${id}`); toast.success("Sotuv o'chirildi"); loadSales(); }
    catch (e) { toast.error(e.response?.data?.detail || "O'chirishda xatolik"); }
  };

  const printSale = async (s, size) => {
    try {
      let data = s;
      if (!s.items) { const r = await api.get(`/sales/${s.id}`); data = r.data; }
      const tpl = size === 'nak' ? 'nak' : size === '58' ? '58' : '80';
      let rSettings = getReceiptSettings();
      if (!rSettings.r58 && !rSettings.r80 && !rSettings.nak) {
        try { const res = await api.get('/companies/me/receipt_templates'); const d = res.data?.receipt_templates || {}; if (d.r58 || d.r80 || d.nak) { saveReceiptSettings(d); rSettings = d; } } catch {}
      }
      const tmplCfg = tpl === 'nak' ? (rSettings.nak || {}) : (rSettings['r' + tpl] || {});
      printReceiptHtml(buildReceiptHtml(data, tpl, tmplCfg));
    } catch { toast.error("Chop etishda xatolik"); }
  };

  const addToCart = useCallback((p) => {
    const price = useWholesale && p.wholesale_price ? Number(p.wholesale_price) : Number(p.sale_price || 0);
    setCart(prev => {
      const ex = prev.find(i => i.product_id === p.id);
      if (ex) return prev.map(i => i.product_id === p.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, {
        product_id: p.id, name: p.name, unit: p.unit || 'dona', qty: 1, price,
        discount_type: 'pct', discount_val: 0,
        wholesale_price: Number(p.wholesale_price || 0), sale_price: Number(p.sale_price || 0),
        stock_quantity: Number(p.stock_quantity || 0), image_url: p.image_url,
      }];
    });
  }, [useWholesale]);

  const updateItem = (idx, field, val) => setCart(prev => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));
  const removeItem = (idx) => setCart(prev => prev.filter((_, i) => i !== idx));

  // Select product into form
  const selectFormProduct = useCallback((p) => {
    setFormProduct(p);
    const price = useWholesale && p.wholesale_price ? Number(p.wholesale_price) : Number(p.sale_price || 0);
    setFormPrice(String(price));
    setFormQty('1');
    setFormDiscVal('');
    setTimeout(() => formQtyRef.current?.select(), 40);
  }, [useWholesale]);

  // Update formPrice when useWholesale toggles and product is selected
  useEffect(() => {
    if (formProduct) {
      const price = useWholesale && formProduct.wholesale_price ? Number(formProduct.wholesale_price) : Number(formProduct.sale_price || 0);
      setFormPrice(String(price));
    }
  }, [useWholesale]); // eslint-disable-line react-hooks/exhaustive-deps

  const addFormToCart = () => {
    if (!formProduct) return toast.error('Mahsulot tanlanmagan!');
    const price = parseFloat(formPrice) || 0;
    const qty   = parseFloat(formQty)  || 1;
    if (qty <= 0) return toast.error("Miqdor 0 dan katta bo'lishi kerak!");
    setCart(prev => {
      const ex = prev.find(i => i.product_id === formProduct.id);
      if (ex) return prev.map(i => i.product_id === formProduct.id
        ? { ...i, qty: i.qty + qty, price, discount_type: formDiscType, discount_val: parseFloat(formDiscVal) || 0 }
        : i);
      return [...prev, {
        product_id: formProduct.id, name: formProduct.name, unit: formProduct.unit || 'dona',
        qty, price, discount_type: formDiscType, discount_val: parseFloat(formDiscVal) || 0,
        wholesale_price: Number(formProduct.wholesale_price || 0), sale_price: Number(formProduct.sale_price || 0),
        stock_quantity: Number(formProduct.stock_quantity || 0), image_url: formProduct.image_url,
      }];
    });
    setFormProduct(null); setFormPrice(''); setFormQty('1'); setFormDiscVal('');
    // switch to cart tab on mobile to show the result
    setMobileTab('cart');
    setTimeout(() => setMobileTab('form'), 300); // bounce back after brief show
  };

  // Refs update every render
  customersRef.current = customers;
  setCustIdRef.current = setCustId;
  addToCartRef.current = addToCart;

  // Global barcode scanner
  useEffect(() => {
    const handle = (e) => {
      const el = document.activeElement;
      if (el?.tagName === 'INPUT' || el?.tagName === 'TEXTAREA') return;
      const now = Date.now(); const gap = now - scanTimeRef.current; scanTimeRef.current = now;
      if (e.key === 'Enter') {
        const buf = scanBufRef.current.trim(); scanBufRef.current = '';
        if (buf.length < 4) return;
        const cust = customersRef.current.find(c => c.phone && (c.phone === buf || c.phone.replace(/\D/g,'') === buf.replace(/\D/g,'')));
        if (cust) { setCustIdRef.current(String(cust.id)); toast.success(`Mijoz tanlandi: ${cust.name}`); return; }
        api.get(`/products/barcode/${encodeURIComponent(buf)}`)
          .then(r => { if (r.data?.id) addToCartRef.current(r.data); })
          .catch(() => toast.error(`Topilmadi: ${buf}`));
      } else if (e.key.length === 1) {
        if (gap > 80) scanBufRef.current = e.key; else scanBufRef.current += e.key;
      }
    };
    window.addEventListener('keydown', handle, true);
    return () => window.removeEventListener('keydown', handle, true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const itemNet = (it) => {
    const gross = it.price * it.qty;
    const disc = it.discount_type === 'pct' ? gross * (parseN(it.discount_val) / 100) : parseN(it.discount_val);
    return Math.max(0, gross - disc);
  };

  const subtotal = cart.reduce((s, it) => s + itemNet(it), 0);
  const saleDisc = discType === 'pct' ? subtotal * (parseN(discVal) / 100) : parseN(discVal);
  const total    = Math.max(0, subtotal - saleDisc);
  const paid     = payments.reduce((s, p) => s + (parseN(p.amt) || 0), 0);
  const debt     = Math.max(0, total - paid);
  const change   = Math.max(0, paid - total);

  const submitSale = async (overridePayType, pPaid = 0, pCash = 0, pCard = 0) => {
    if (!cart.length) return toast.error('Savat bo\'sh!');
    if (!custId) return toast.error('Mijoz tanlanmagan! Iltimos mijoz tanlang.');
    setSaving(true);
    try {
      const items = cart.map(it => ({
        product_id: it.product_id, quantity: it.qty, unit_price: it.price,
        discount: it.discount_type === 'pct' ? it.price * it.qty * (parseN(it.discount_val) / 100) : parseN(it.discount_val),
      }));
      const paymentsList = payments.filter(p => parseN(p.amt) > 0).map(p => ({ type: p.type, amount: parseN(p.amt) }));
      const payload = {
        items, payment_type: overridePayType, paid_amount: pPaid, paid_cash: pCash, paid_card: pCard,
        discount_amount: saleDisc, note: note || payNote || undefined,
        customer_id: custId ? Number(custId) : undefined,
        warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        debt_due_date: overridePayType === 'debt' && debtDate ? debtDate : undefined,
        payments: paymentsList.length > 0 ? paymentsList : undefined,
      };

      let res;
      if (editingSale) {
        res = await api.put(`/sales/${editingSale.id}`, { ...payload, warehouse_id: editingSale.warehouse_id || (warehouseId ? Number(warehouseId) : undefined) });
        toast.success(`"${editingSale.number}" sotuv yangilandi!`); setEditingSale(null);
      } else {
        res = await api.post('/sales/', payload);
        toast.success('Sotuv muvaffaqiyatli saqlandi!');
      }

      if (autoPrint) {
        try {
          const rSettings = getReceiptSettings();
          const tpl = receiptWidth === 'A4' ? 'nak' : receiptWidth;
          const cfg = tpl === 'nak' ? (rSettings.nak || {}) : (rSettings['r' + tpl] || {});
          printReceiptHtml(buildReceiptHtml({
            number: res.data.number, id: res.data.id, created_at: res.data.created_at,
            cashier_name: res.data.cashier_name, total_amount: res.data.total_amount,
            paid_amount: res.data.paid_amount, discount_amount: saleDisc,
            items: cart.map(it => ({
              product_name: it.name, quantity: it.qty, unit_price: it.price,
              discount: it.discount_type === 'pct' ? it.price * it.qty * (parseN(it.discount_val) / 100) : parseN(it.discount_val),
              subtotal: itemNet(it),
            })),
          }, tpl, cfg));
        } catch {}
      }

      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDiscVal(''); setPaidAmt('');
      setPaidCash(''); setPaidCard(''); setPayNote(''); setDebtDate('');
      setShowPayment(false); setShowDebtDate(false); setPayType('cash'); setPayments([]); setCurPayAmt('');
      setFormProduct(null); setFormPrice(''); setFormQty('1'); setFormDiscVal('');
    } catch (e) { toast.error(e?.response?.data?.detail || 'Saqlashda xatolik'); }
    finally { setSaving(false); }
  };

  const handlePay = async () => {
    if (!cart.length) return toast.error('Savat bo\'sh!');
    if (!hasShift) { setShowShiftModal(true); return; }
    if (!custId) return toast.error('Mijoz tanlanmagan! Iltimos mijoz tanlang.');
    if (debt > 0 && !debtDate && showDebtDate) return toast.error('Qarz muddat sanasini kiriting!');
    if (debt > 0 && !showDebtDate) { setShowDebtDate(true); return; }
    const totalPaid = payments.reduce((s, p) => s + (parseN(p.amt) || 0), 0);
    const types = [...new Set(payments.map(p => p.type))];
    let finalPayType;
    if (totalPaid === 0) finalPayType = 'debt';
    else if (types.length === 1 && debt === 0) finalPayType = types[0];
    else finalPayType = 'mixed';
    const pCash = payments.filter(p => p.type === 'cash').reduce((s, p) => s + (parseN(p.amt)||0), 0);
    const pCard = payments.filter(p => p.type !== 'cash').reduce((s, p) => s + (parseN(p.amt)||0), 0);
    await submitSale(finalPayType, totalPaid, pCash, pCard);
  };

  const handleDirectAction = async (actionType) => {
    if (!cart.length) return toast.error("Savat bo'sh!");
    if (actionType === 'draft') {
      const existing = JSON.parse(localStorage.getItem('ulgurji_drafts') || '[]');
      localStorage.setItem('ulgurji_drafts', JSON.stringify([{ id: Date.now(), date: new Date().toISOString(), cart, custId, note, discType, discVal, total }, ...existing]));
      toast.success("Sotuv arxivga olindi!");
      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDiscVal('');
      return;
    }
    if (actionType === 'debt') {
      if (!custId) return toast.error("Qarzga sotish uchun mijoz tanlang!");
      await submitSale('debt', 0, 0, 0);
    }
  };

  const openPayModal = () => {
    if (!cart.length) return;
    if (!custId) return toast.error('Mijoz tanlanmagan!');
    if (!hasShift) { setShowShiftModal(true); return; }
    setPayments([{ id: Date.now(), type: 'cash', amt: '' }]);
    setCurPayAmt(''); setShowPayment(true);
  };

  /* ══════════════════════════════════════════════════
     RENDER
  ══════════════════════════════════════════════════ */
  return (
    <div className="absolute inset-0 flex flex-col bg-slate-100 overflow-hidden">
      {showShiftModal && <ShiftOpenModal onOpened={() => { reloadShift(); setShowShiftModal(false); }} onCancel={() => setShowShiftModal(false)} />}

      {/* ── HEADER ── */}
      <div className="shrink-0 bg-white border-b border-slate-200 px-3 md:px-5 py-2.5 flex items-center justify-between shadow-sm gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center shadow-md shadow-indigo-200 shrink-0">
            <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-4 h-4 text-white" />
          </div>
          <span className="font-black text-slate-800 text-base hidden sm:inline">Ulgurji Sotuv</span>
        </div>

        <div className="flex items-center gap-1.5 md:gap-3">
          <div className="hidden lg:flex items-center gap-1.5 text-slate-500 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-100">
            <Ic d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4" />
            <span className="text-sm font-bold font-mono tracking-tight">{currentTime.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>

          {tab === 'new' && (
            <button onClick={() => toast.info("Excel orqali yuklash tez kunda qo'shiladi")}
              className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors text-sm font-bold border border-emerald-100">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              Excel
            </button>
          )}

          <div className="w-px h-5 bg-slate-200 mx-1 hidden md:block" />

          <button onClick={() => setSettingsOpen(true)}
            className="w-9 h-9 rounded-xl text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 flex items-center justify-center transition-colors">
            <Ic d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </button>
          {[
            { id: 'new',    label: 'Yangi',  icon: 'M12 4v16m8-8H4' },
            { id: 'list',   label: 'Tarixi', icon: 'M4 6h16M4 10h16M4 14h16M4 18h16' },
            { id: 'drafts', label: 'Arxiv',  icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 px-2.5 md:px-3.5 py-2 rounded-xl text-sm font-semibold transition-all ${tab === t.id ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              <Ic d={t.icon} cls="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ══ YANGI SOTUV ══ */}
      {tab === 'new' && (
        <>
          {editingSale && (
            <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-700 text-sm font-semibold">
                <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-4 h-4" />
                Tahrirlash rejimi: <span className="font-black font-mono">{editingSale.number}</span>
              </div>
              <button onClick={() => { setEditingSale(null); setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDiscVal(''); }}
                className="text-amber-500 hover:text-amber-700 font-bold text-sm">Bekor qilish</button>
            </div>
          )}

          {/* Main two-panel area */}
          <div className="flex-1 flex flex-col md:flex-row overflow-hidden min-h-0">

            {/* ── LEFT PANEL: Forma ── */}
            <div className={`md:w-[360px] md:shrink-0 md:flex md:flex-col md:bg-white md:border-r md:border-slate-200 md:overflow-y-auto
              ${mobileTab === 'form' ? 'flex flex-col flex-1 overflow-y-auto bg-white' : 'hidden md:flex md:flex-col'}`}>
              <div className="p-4 space-y-4">

                {/* Mijoz */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">Mijoz *</label>
                    {!custId && <span className="text-xs text-red-400 font-semibold">Tanlanmagan</span>}
                  </div>
                  <CustomerSearch customers={customers} value={custId} onChange={setCustId} />
                </div>

                <div className="border-t border-slate-100" />

                {/* Mahsulot qo'shish */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-500 uppercase tracking-wide">Mahsulot</label>
                    <div className="flex items-center gap-2">
                      {/* Ulgurji toggle */}
                      <button
                        onClick={() => {
                          const next = !useWholesale;
                          setUseWholesale(next);
                          setCart(prev => prev.map(it => ({ ...it, price: (next && it.wholesale_price) ? it.wholesale_price : it.sale_price })));
                        }}
                        className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold border transition-all ${useWholesale ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white border-slate-200 text-slate-500'}`}>
                        <Ic d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" cls="w-3 h-3" />
                        Ulgurji
                      </button>
                      {/* Ombor */}
                      {warehouses.length > 0 && (
                        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
                          className="border border-slate-200 rounded-lg px-2 py-1 text-xs font-semibold text-slate-700 focus:outline-none bg-white">
                          <option value="">Barcha</option>
                          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                      )}
                    </div>
                  </div>

                  <ProductSearch onSelect={selectFormProduct} placeholder="Mahsulot nomi, SKU, barkod..." />

                  {/* Selected product card */}
                  {formProduct ? (
                    <div className="mt-3 bg-indigo-50 border border-indigo-100 rounded-2xl p-3">
                      {/* Product info */}
                      <div className="flex items-center gap-2.5 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-white border border-indigo-100 flex items-center justify-center shrink-0 overflow-hidden">
                          {formProduct.image_url
                            ? <img src={formProduct.image_url} alt="" className="w-full h-full object-cover" />
                            : <span className="font-black text-indigo-400 text-sm">{formProduct.name?.[0]}</span>}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-bold text-slate-800 text-sm truncate">{formProduct.name}</div>
                          <div className="text-xs text-slate-500 flex items-center gap-2">
                            <span>{formProduct.unit || 'dona'}</span>
                            <span className={`font-semibold ${Number(formProduct.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                              Ombor: {fmt(formProduct.stock_quantity)}
                            </span>
                          </div>
                        </div>
                        <button onClick={() => setFormProduct(null)} className="text-slate-300 hover:text-red-400 shrink-0">
                          <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                        </button>
                      </div>

                      {/* Narx */}
                      <div className="mb-2">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1 block">Narx (so'm)</label>
                        <div className="flex gap-1.5">
                          <div className="flex-1 relative">
                            <input type="number" value={formPrice}
                              onChange={e => setFormPrice(e.target.value)}
                              className="w-full border-2 border-white rounded-xl px-3 py-2.5 text-base font-black text-slate-800 focus:outline-none focus:border-indigo-500 pr-7 bg-white" />
                            <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-400">s</span>
                          </div>
                          {formProduct.wholesale_price > 0 && (
                            <button onClick={() => setFormPrice(String(formProduct.wholesale_price))}
                              className="shrink-0 px-2.5 py-2 rounded-xl bg-white border-2 border-indigo-200 text-indigo-600 text-xs font-bold hover:bg-indigo-50 transition-colors">
                              U:{fmt(formProduct.wholesale_price)}
                            </button>
                          )}
                          {formProduct.sale_price > 0 && (
                            <button onClick={() => setFormPrice(String(formProduct.sale_price))}
                              className="shrink-0 px-2.5 py-2 rounded-xl bg-white border-2 border-slate-200 text-slate-600 text-xs font-bold hover:bg-slate-50 transition-colors">
                              C:{fmt(formProduct.sale_price)}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Miqdor */}
                      <div className="mb-2">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1 block">Miqdor ({formProduct.unit || 'dona'})</label>
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => setFormQty(q => String(Math.max(0.1, (parseFloat(q) || 1) - 1)))}
                            className="w-11 h-11 rounded-xl bg-white flex items-center justify-center font-black text-slate-600 text-xl active:bg-slate-100 border-2 border-slate-200">−</button>
                          <input ref={formQtyRef} type="number" value={formQty}
                            onChange={e => setFormQty(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addFormToCart(); } }}
                            className="flex-1 border-2 border-white rounded-xl py-2.5 text-center text-base font-black text-slate-800 focus:outline-none focus:border-indigo-500 bg-white" />
                          <button onClick={() => setFormQty(q => String((parseFloat(q) || 1) + 1))}
                            className="w-11 h-11 rounded-xl bg-indigo-600 flex items-center justify-center font-black text-white text-xl active:bg-indigo-700">+</button>
                        </div>
                      </div>

                      {/* Chegirma */}
                      <div className="mb-3">
                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1 block">Chegirma</label>
                        <div className="flex gap-1.5">
                          <button onClick={() => setFormDiscType(t => t === 'pct' ? 'amt' : 'pct')}
                            className="w-12 h-10 rounded-xl bg-white border-2 border-amber-200 text-amber-600 font-black text-xs active:bg-amber-50">
                            {formDiscType === 'pct' ? '%' : "So'm"}
                          </button>
                          <input type="number" value={formDiscVal}
                            onChange={e => setFormDiscVal(e.target.value)}
                            placeholder="0"
                            className="flex-1 border-2 border-white rounded-xl px-3 py-2 text-sm font-bold focus:outline-none focus:border-amber-400 bg-white" />
                        </div>
                      </div>

                      {/* Add button */}
                      <button onClick={addFormToCart}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white font-black text-base rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-indigo-200 transition-colors">
                        <Ic d="M12 4v16m8-8H4" cls="w-5 h-5" />
                        Savatga qo'shish
                      </button>
                    </div>
                  ) : (
                    <div className="mt-3 flex flex-col items-center justify-center py-8 text-slate-300 gap-2">
                      <Ic d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" cls="w-10 h-10" />
                      <p className="text-sm text-slate-400 text-center">Mahsulot qidiring yoki<br/>barkod skanerlang</p>
                    </div>
                  )}
                </div>

                <div className="border-t border-slate-100" />

                {/* Izoh */}
                <div>
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5 block">Izoh</label>
                  <textarea value={note} onChange={e => setNote(e.target.value)}
                    placeholder="Shartnoma raqami, izoh..." rows={2}
                    className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none bg-white" />
                </div>

                {/* Sotuv chegirmasi */}
                <div>
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5 block">Sotuv chegirmasi</label>
                  <div className="flex gap-2">
                    <div className="flex rounded-xl border-2 border-slate-200 overflow-hidden">
                      {['pct','amt'].map(t => (
                        <button key={t} onClick={() => setDiscType(t)}
                          className={`px-3 py-2 text-xs font-bold transition-colors ${discType === t ? 'bg-amber-500 text-white' : 'bg-white text-slate-500'}`}>
                          {t === 'pct' ? '%' : "So'm"}
                        </button>
                      ))}
                    </div>
                    <input type="number" value={discVal} onChange={e => setDiscVal(e.target.value)}
                      placeholder="0"
                      className="flex-1 border-2 border-slate-200 rounded-xl px-3 py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white" />
                  </div>
                  {saleDisc > 0 && <p className="text-xs text-amber-600 font-semibold mt-1">− {fmt(saleDisc)} s chegirma</p>}
                </div>

                {/* Spacer for mobile scroll */}
                <div className="h-2" />
              </div>
            </div>

            {/* ── RIGHT PANEL: Savat ── */}
            <div className={`flex-1 flex flex-col overflow-hidden bg-white
              ${mobileTab === 'cart' ? 'flex' : 'hidden md:flex md:flex-col'}`}>

              {/* Cart header */}
              <div className="shrink-0 px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
                <span className="text-sm font-bold text-slate-600">
                  {cart.length > 0 ? `${cart.length} xil · ${cart.reduce((s,i)=>s+i.qty,0).toFixed(1)} birlik` : 'Savat bo\'sh'}
                </span>
                {cart.length > 0 && (
                  <button onClick={() => { if (window.confirm("Savatni tozalash?")) setCart([]); }}
                    className="text-xs text-red-400 hover:text-red-600 font-semibold px-2 py-1 rounded-lg hover:bg-red-50 transition-colors">
                    Hammasini o'chirish
                  </button>
                )}
              </div>

              {/* Cart body */}
              <div className="flex-1 overflow-y-auto">
                {cart.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3 p-8">
                    <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center">
                      <Ic d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" cls="w-7 h-7" />
                    </div>
                    <div className="text-center">
                      <p className="font-bold text-slate-400">Savat bo'sh</p>
                      <p className="text-xs text-slate-300 mt-1">Chap paneldan mahsulot qo'shing<br/>yoki barkod skanerlang</p>
                    </div>
                  </div>
                ) : (
                  <table className="w-full text-sm border-collapse">
                    <thead className="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="text-left px-3 py-2 text-xs font-bold text-slate-500 w-7">#</th>
                        <th className="text-left px-2 py-2 text-xs font-bold text-slate-500">Nomi</th>
                        <th className="text-center px-2 py-2 text-xs font-bold text-slate-500 w-[120px]">Soni</th>
                        <th className="text-right px-2 py-2 text-xs font-bold text-slate-500 w-[110px]">Narx</th>
                        <th className="text-center px-2 py-2 text-xs font-bold text-slate-500 w-[110px]">Chegirma</th>
                        <th className="text-right px-3 py-2 text-xs font-bold text-slate-500 w-[100px]">Jami</th>
                        <th className="w-8" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {cart.map((it, idx) => {
                        const net = itemNet(it);
                        const hasDisc = parseN(it.discount_val) > 0;
                        return (
                          <tr key={idx} className="hover:bg-slate-50/80 group transition-colors">
                            <td className="px-3 py-2.5 text-xs text-slate-400 font-mono">{idx + 1}</td>
                            <td className="px-2 py-2.5">
                              <div className="font-semibold text-slate-800 text-sm leading-tight">{it.name}</div>
                              <div className="text-xs text-slate-400">{it.unit}</div>
                            </td>
                            <td className="px-2 py-2.5">
                              <div className="flex items-center gap-1 justify-center">
                                <button onClick={() => updateItem(idx, 'qty', Math.max(0.1, it.qty - 1))}
                                  className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center font-bold text-slate-600 text-sm">−</button>
                                <input type="number" value={it.qty}
                                  onChange={e => updateItem(idx, 'qty', Math.max(0.01, parseFloat(e.target.value) || 1))}
                                  className="w-14 text-center font-black text-slate-800 border border-slate-200 rounded-lg py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                                <button onClick={() => updateItem(idx, 'qty', it.qty + 1)}
                                  className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center font-bold text-slate-600 text-sm">+</button>
                              </div>
                            </td>
                            <td className="px-2 py-2.5">
                              <div className="relative">
                                <input type="number" value={it.price}
                                  onChange={e => updateItem(idx, 'price', parseFloat(e.target.value) || 0)}
                                  className="w-full text-right font-bold text-slate-800 border border-slate-200 rounded-lg py-1 pr-6 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400">s</span>
                              </div>
                            </td>
                            <td className="px-2 py-2.5">
                              <div className="flex items-center gap-1">
                                <button onClick={() => updateItem(idx, 'discount_type', it.discount_type === 'pct' ? 'amt' : 'pct')}
                                  className="w-7 h-7 rounded bg-amber-50 text-amber-600 text-[10px] font-black border border-amber-200 shrink-0">
                                  {it.discount_type === 'pct' ? '%' : 's'}
                                </button>
                                <input type="number" value={it.discount_val || ''}
                                  onChange={e => updateItem(idx, 'discount_val', parseFloat(e.target.value) || 0)}
                                  placeholder="0"
                                  className="w-14 text-center text-sm border border-slate-200 rounded-lg py-1 focus:outline-none focus:ring-1 focus:ring-amber-300" />
                              </div>
                            </td>
                            <td className="px-3 py-2.5 text-right">
                              <div className="font-black text-slate-800 text-sm">{fmt(net)} s</div>
                              {hasDisc && <div className="text-xs text-slate-400 line-through">{fmt(it.price * it.qty)} s</div>}
                            </td>
                            <td className="pr-2 py-2.5">
                              <button onClick={() => removeItem(idx)}
                                className="w-7 h-7 rounded-lg text-slate-300 hover:bg-red-50 hover:text-red-500 flex items-center justify-center transition-colors">
                                <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Cart totals */}
              {cart.length > 0 && (
                <div className="shrink-0 bg-slate-50 border-t border-slate-200 px-4 py-3 space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Mahsulotlar jami:</span>
                    <span className="font-bold text-slate-700">{fmt(subtotal)} s</span>
                  </div>
                  {saleDisc > 0 && (
                    <div className="flex justify-between text-sm">
                      <span className="text-amber-600">Chegirma:</span>
                      <span className="font-bold text-amber-600">− {fmt(saleDisc)} s</span>
                    </div>
                  )}
                  <div className="flex justify-between border-t border-slate-200 pt-2">
                    <span className="font-bold text-slate-700 text-base">Umumiy summa:</span>
                    <span className="text-xl font-black text-indigo-700">{fmt(total)} s</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── MOBILE TABS ── */}
          <div className="md:hidden shrink-0 flex border-t border-slate-200 bg-white">
            <button onClick={() => setMobileTab('form')}
              className={`flex-1 py-2.5 text-sm font-bold flex items-center justify-center gap-1.5 transition-colors
                ${mobileTab === 'form' ? 'text-indigo-600 border-t-2 border-indigo-600 -mt-px' : 'text-slate-500 border-t-2 border-transparent -mt-px'}`}>
              <Ic d="M12 4v16m8-8H4" cls="w-4 h-4" />
              Qo'shish
            </button>
            <button onClick={() => setMobileTab('cart')}
              className={`flex-1 py-2.5 text-sm font-bold flex items-center justify-center gap-1.5 transition-colors
                ${mobileTab === 'cart' ? 'text-indigo-600 border-t-2 border-indigo-600 -mt-px' : 'text-slate-500 border-t-2 border-transparent -mt-px'}`}>
              <Ic d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" cls="w-4 h-4" />
              Savat
              {cart.length > 0 && (
                <span className="bg-indigo-600 text-white text-[10px] font-black rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">{cart.length}</span>
              )}
            </button>
          </div>

          {/* ── BOTTOM ACTION BAR ── */}
          <div className="shrink-0 bg-white border-t border-slate-200 px-3 py-2.5 flex items-center gap-2 shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
            <button onClick={() => { if (!cart.length) return; if (window.confirm("Savatni tozalash?")) { setCart([]); setFormProduct(null); } }}
              disabled={cart.length === 0}
              title="Sotuvni o'chirish"
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-red-50 text-red-600 hover:bg-red-100 active:bg-red-200 disabled:opacity-30 text-sm font-bold transition-colors border border-red-100">
              <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-4 h-4" />
              <span className="hidden sm:inline">O'chirish</span>
            </button>

            <button onClick={() => handleDirectAction('draft')}
              disabled={cart.length === 0}
              title="Arxivga saqlash"
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-amber-50 text-amber-600 hover:bg-amber-100 active:bg-amber-200 disabled:opacity-30 text-sm font-bold transition-colors border border-amber-100">
              <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4" />
              <span className="hidden sm:inline">Arxiv</span>
            </button>

            <button onClick={() => handleDirectAction('debt')}
              disabled={cart.length === 0 || saving}
              title="Qarzga sotish"
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-rose-50 text-rose-600 hover:bg-rose-100 active:bg-rose-200 disabled:opacity-30 text-sm font-bold transition-colors border border-rose-100">
              <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-4 h-4" />
              <span className="hidden sm:inline">Qarzga</span>
            </button>

            <button
              disabled={cart.length === 0}
              onClick={() => { if (!cart.length) return; openPayModal(); }}
              title="Chek chiqarish"
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-slate-50 text-slate-600 hover:bg-slate-100 active:bg-slate-200 disabled:opacity-30 text-sm font-bold transition-colors border border-slate-200">
              <Ic d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" cls="w-4 h-4" />
            </button>

            <div className="flex-1" />

            <button onClick={openPayModal}
              disabled={cart.length === 0 || saving}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-black text-sm shadow-md transition-all disabled:opacity-40
                ${!custId && cart.length > 0 ? 'bg-amber-500 hover:bg-amber-600 text-white shadow-amber-200' : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-200'}`}>
              <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-4 h-4" />
              <span>{!custId && cart.length > 0 ? 'Mijoz tanlang' : editingSale ? 'Yangilash' : "To'lov"}</span>
              {cart.length > 0 && <span className="font-black">{fmt(total)} s</span>}
            </button>
          </div>
        </>
      )}

      {/* ══ SOTUVLAR TARIXI ══ */}
      {tab === 'list' && (
        <div className="flex-1 overflow-hidden flex flex-col p-3 md:p-4 gap-3">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-3 md:p-4 flex flex-wrap gap-2 items-center">
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
              placeholder="Sotuv raqami..." className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 w-40" />
            <button onClick={loadSales} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5">
              <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-3.5 h-3.5" />Qidirish
            </button>
          </div>

          <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-auto">
            {loadingSales ? (
              <div className="flex justify-center items-center h-64"><div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                  <tr>
                    {['#','Sotuv raqami','Mijoz','Jami',"To'langan",'Qarz',"To'lov",'Holat','Kassir','Sana',''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {sales.length === 0 && <tr><td colSpan={11} className="text-center py-16 text-slate-400">Sotuvlar topilmadi</td></tr>}
                  {sales.map((s, i) => {
                    const dbt = Number(s.total_amount) - Number(s.paid_amount);
                    return (
                      <tr key={s.id} onClick={() => { setSelectedSale(s); setOpenMenuId(null); }}
                        className="hover:bg-indigo-50/40 cursor-pointer transition-colors">
                        <td className="px-4 py-3 text-xs text-slate-400">{i + 1 + page * LIMIT}</td>
                        <td className="px-4 py-3"><span className="font-mono font-black text-indigo-700 text-xs bg-indigo-50 px-2.5 py-1 rounded-lg border border-indigo-100">{s.number}</span></td>
                        <td className="px-4 py-3">
                          {s.customer_name
                            ? <div className="flex items-center gap-2"><div className="w-7 h-7 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">{s.customer_name[0]}</div><span className="font-semibold text-slate-700">{s.customer_name}</span></div>
                            : <span className="text-slate-400 text-xs">—</span>}
                        </td>
                        <td className="px-4 py-3 font-black text-slate-800 text-right whitespace-nowrap">{fmt(s.total_amount)} s</td>
                        <td className="px-4 py-3 font-bold text-emerald-700 text-right whitespace-nowrap">{fmt(s.paid_amount)} s</td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">{dbt > 0 ? <span className="font-bold text-red-600">{fmt(dbt)} s</span> : <span className="text-slate-300">—</span>}</td>
                        <td className="px-4 py-3"><span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{PAY_META[s.payment_type] || s.payment_type}</span></td>
                        <td className="px-4 py-3"><span className={`text-xs font-bold px-2 py-0.5 rounded-full ${STATUS_META[s.status]?.c || 'bg-slate-100 text-slate-500'}`}>{STATUS_META[s.status]?.l || s.status}</span></td>
                        <td className="px-4 py-3 text-sm text-slate-500">{s.cashier_name}</td>
                        <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{s.created_at ? new Date(s.created_at).toLocaleDateString('uz-UZ', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—'}</td>
                        <td className="px-2 py-3 relative" onClick={e => e.stopPropagation()}>
                          <button onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === s.id ? null : s.id); }}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-all">
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
                          </button>
                          {openMenuId === s.id && (
                            <div className="absolute right-0 top-8 z-50 bg-white border border-slate-200 rounded-xl shadow-2xl py-1 min-w-[170px]" onMouseLeave={() => setOpenMenuId(null)}>
                              <button onClick={() => loadEditSale(s)} className="w-full text-left px-4 py-2.5 text-sm text-slate-700 hover:bg-indigo-50 flex items-center gap-2.5">
                                <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                                Tahrirlash
                              </button>
                              <div className="border-t border-slate-100 my-1"/>
                              <div className="px-4 py-1 text-xs font-semibold text-slate-400 uppercase tracking-wide">Chop etish</div>
                              {[{size:'58',label:'58mm'},{size:'80',label:'80mm'},{size:'nak',label:'A4 Nakladnoy'}].map(opt => (
                                <button key={opt.size} onClick={() => { printSale(s, opt.size); setOpenMenuId(null); }}
                                  className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-indigo-50 flex items-center gap-2.5">
                                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
                                  {opt.label}
                                </button>
                              ))}
                              <div className="border-t border-slate-100 my-1"/>
                              <button onClick={() => { deleteSale(s.id); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2.5">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                                O'chirish
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {sales.length > 0 && (
                  <tfoot>
                    <tr className="bg-indigo-50 border-t-2 border-indigo-100">
                      <td colSpan={3} className="px-4 py-3 text-xs font-bold text-indigo-700">{sales.length} ta sotuv</td>
                      <td className="px-4 py-3 text-right font-black text-indigo-800 whitespace-nowrap">{fmt(sales.reduce((s,x)=>s+Number(x.total_amount),0))} s</td>
                      <td className="px-4 py-3 text-right font-black text-emerald-700 whitespace-nowrap">{fmt(sales.reduce((s,x)=>s+Number(x.paid_amount),0))} s</td>
                      <td className="px-4 py-3 text-right font-black text-red-600 whitespace-nowrap">{fmt(sales.reduce((s,x)=>s+Math.max(0,Number(x.total_amount)-Number(x.paid_amount)),0))} s</td>
                      <td colSpan={5} />
                    </tr>
                  </tfoot>
                )}
              </table>
            )}
          </div>

          <div className="flex items-center justify-between">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">← Oldingi</button>
            <span className="text-sm text-slate-500 font-semibold">{page + 1}-sahifa</span>
            <button disabled={sales.length < LIMIT} onClick={() => setPage(p => p + 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">Keyingi →</button>
          </div>
        </div>
      )}

      {/* ══ ARXIVLAR ══ */}
      {tab === 'drafts' && (
        <div className="flex-1 overflow-auto p-4 md:p-6 bg-slate-50">
          <div className="max-w-4xl mx-auto space-y-4">
            {draftsList.length === 0 && (
              <div className="text-center py-20 bg-white rounded-3xl border border-slate-200">
                <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4 text-slate-300">
                  <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-slate-700">Arxivlangan sotuvlar yo'q</h3>
                <p className="text-sm text-slate-400 mt-1">Sotuv oynasida "Arxivga olish" bosilganlari shu yerga tushadi.</p>
              </div>
            )}
            {draftsList.map((d, i) => (
              <div key={d.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="bg-amber-100 text-amber-700 text-[10px] font-black uppercase px-2 py-0.5 rounded-full tracking-wide">
                      {new Date(d.date).toLocaleString('uz-UZ', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}
                    </span>
                    <span className="text-sm font-bold text-slate-800">{d.cart.length} xil mahsulot</span>
                  </div>
                  <h4 className="text-2xl font-black text-indigo-700">{fmt(d.total)} so'm</h4>
                  {d.note && <p className="text-xs text-slate-500 mt-1">📝 {d.note}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => removeDraft(i)} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm">O'chirish</button>
                  <button onClick={() => loadDraft(i)} className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl text-sm shadow-md shadow-indigo-200">Savatga yuklash</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ══ TO'LOV MODALI ══ */}
      {showPayment && (() => {
        const closeModal = () => { setShowPayment(false); setShowDebtDate(false); setPayments([]); setCurPayAmt(''); };
        const remaining = Math.max(0, total - paid);
        const updateLine = (id, field, val) => setPayments(prev => prev.map(p => p.id === id ? { ...p, [field]: val } : p));
        const removeLine = (id) => { if (payments.length > 1) setPayments(prev => prev.filter(p => p.id !== id)); };
        const addLine = () => setPayments(prev => [...prev, { id: Date.now(), type: 'cash', amt: '' }]);
        const fillLine = (id) => { const la = parseN(payments.find(p => p.id === id)?.amt) || 0; const rem = Math.max(0, remaining + la); updateLine(id, 'amt', rem > 0 ? String(rem) : String(total)); };
        const now = new Date();
        return (
          <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/50 backdrop-blur-sm p-0 md:p-4">
            <div className="bg-white w-full md:max-w-lg rounded-t-3xl md:rounded-2xl shadow-2xl overflow-hidden flex flex-col" style={{maxHeight:'95vh'}}>
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center">
                    <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <h2 className="text-base font-black text-slate-800">Kassaga to'lov</h2>
                    <p className="text-xs text-indigo-500 font-mono">{now.toLocaleString('ru-RU').replace(',','')}</p>
                  </div>
                </div>
                <button onClick={closeModal} className="w-8 h-8 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500">
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">To'lov</span>
                    <button onClick={addLine} className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center shadow-sm">
                      <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-2">
                    {payments.map((line, idx) => {
                      const pt = PAY_TYPES.find(p => p.id === line.type);
                      const acls = ACCENT_CLS[pt?.accent] || ACCENT_CLS.indigo;
                      const isDebt = line.type === 'debt';
                      return (
                        <div key={line.id} className="flex items-center gap-2">
                          <div className="relative w-36 shrink-0">
                            <div className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none ${acls.idle.split(' ').find(c=>c.startsWith('text'))||'text-slate-400'}`}>{PAY_ICONS[line.type]}</div>
                            <select value={line.type} onChange={e => updateLine(line.id, 'type', e.target.value)}
                              className="w-full h-10 pl-8 pr-2 border border-slate-200 rounded-lg text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white appearance-none cursor-pointer">
                              {PAY_TYPES.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                            </select>
                          </div>
                          {isDebt
                            ? <div className="flex-1 h-10 px-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center"><span className="text-sm font-black text-amber-700">{fmt(remaining > 0 ? remaining : total)} s — qarzga</span></div>
                            : <input type="number" value={line.amt} onChange={e => updateLine(line.id, 'amt', e.target.value)}
                                placeholder="0" autoFocus={idx === payments.length - 1}
                                className="flex-1 h-10 px-3 border border-slate-200 rounded-lg text-base font-black text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 min-w-0" />
                          }
                          {!isDebt && <button onClick={() => fillLine(line.id)} className="shrink-0 h-10 px-3 border border-slate-200 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-50 whitespace-nowrap">Qoldi</button>}
                          <button onClick={() => removeLine(line.id)} className={`shrink-0 w-8 h-10 rounded-lg flex items-center justify-center ${payments.length > 1 ? 'text-slate-300 hover:text-red-500 hover:bg-red-50' : 'text-slate-200 cursor-not-allowed'}`}>
                            <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-3.5 h-3.5" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1.5 block">Izoh (ixtiyoriy)</label>
                  <textarea value={payNote} onChange={e => setPayNote(e.target.value)} placeholder="Shartnoma raqami, eslatma..." rows={2}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none" />
                </div>

                {showDebtDate && remaining > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-3">
                    <Ic d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" cls="w-4 h-4 text-amber-600 shrink-0" />
                    <div className="flex-1">
                      <p className="text-xs font-bold text-amber-700 mb-1">Qarz muddati (ixtiyoriy)</p>
                      <input type="date" min={today()} value={debtDate} onChange={e => setDebtDate(e.target.value)}
                        className="w-full border border-amber-300 bg-white rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400" />
                    </div>
                  </div>
                )}

                <div className="bg-slate-50 rounded-xl border border-slate-100 divide-y divide-slate-100">
                  {[
                    { label: 'Umumiy summa', val: fmt(total)+' s', cls: 'text-slate-800 font-bold' },
                    saleDisc > 0 && { label: 'Chegirma', val: '−'+fmt(saleDisc)+' s', cls: 'text-amber-600 font-semibold' },
                    { label: "To'lov", val: fmt(paid)+' s', cls: 'text-emerald-600 font-black' },
                    remaining > 0 && { label: 'Qarzga', val: fmt(remaining)+' s', cls: 'text-red-600 font-black' },
                    change > 0 && { label: 'Qaytim', val: fmt(change)+' s', cls: 'text-blue-600 font-black' },
                  ].filter(Boolean).map((r, i) => (
                    <div key={i} className="flex justify-between items-center px-4 py-2.5 text-sm">
                      <span className="text-slate-500">{r.label}</span>
                      <span className={r.cls}>{r.val}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="shrink-0 px-5 py-3.5 border-t border-slate-100 flex gap-2.5">
                <button onClick={closeModal} className="px-5 py-2.5 border border-slate-200 hover:bg-slate-50 text-slate-600 font-semibold rounded-xl text-sm">Bekor qilish</button>
                <button onClick={handlePay} disabled={saving}
                  className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-black rounded-xl text-sm shadow-md shadow-emerald-200 transition-all flex items-center justify-center gap-2">
                  {saving ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />Saqlanmoqda...</> : <><Ic d="M5 13l4 4L19 7" cls="w-4 h-4" />Saqlash</>}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══ SOTUV TAFSILOTI MODALI ══ */}
      {selectedSale && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <div>
                <h2 className="font-black text-lg font-mono">{selectedSale.number}</h2>
                <p className="text-sm text-white/60 mt-0.5">{selectedSale.cashier_name} · {new Date(selectedSale.created_at).toLocaleDateString('uz-UZ')}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-3 py-1.5 rounded-full ${STATUS_META[selectedSale.status]?.c || 'bg-white/20 text-white'}`}>{STATUS_META[selectedSale.status]?.l}</span>
                <button onClick={() => setSelectedSale(null)} className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center"><Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" /></button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <SaleDetailContent saleId={selectedSale.id} />
            </div>
          </div>
        </div>
      )}

      {/* ══ SOZLAMALAR MODALI ══ */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm overflow-hidden flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <h2 className="text-lg font-black">Sotuv sozlamalari</h2>
              <button onClick={() => setSettingsOpen(false)} className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center"><Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" /></button>
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
                <button onClick={() => setAutoPrint(!autoPrint)} className={`w-12 h-6 rounded-full p-1 transition-colors ${autoPrint ? 'bg-indigo-500' : 'bg-slate-300'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform ${autoPrint ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">Chek formati</label>
                <div className="grid grid-cols-3 gap-2">
                  {[{id:'58',label:'58 mm'},{id:'80',label:'80 mm'},{id:'A4',label:'A4'}].map(w => (
                    <button key={w.id} onClick={() => setReceiptWidth(w.id)}
                      className={`py-2 text-sm font-semibold rounded-xl border-2 transition-colors ${receiptWidth === w.id ? 'border-indigo-500 text-indigo-700 bg-indigo-50' : 'border-slate-100 text-slate-500 hover:border-slate-300'}`}>
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setSettingsOpen(false)} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl text-sm">Bekor</button>
              <button onClick={saveSettings} className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl text-sm shadow-md shadow-indigo-200">Saqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SaleDetailContent({ saleId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/sales/${saleId}`).then(r => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [saleId]);

  if (loading) return <div className="flex justify-center py-16"><div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>;
  if (!data) return <div className="text-center py-16 text-slate-400">Ma'lumot topilmadi</div>;

  const fmtL = v => Number(v || 0).toLocaleString('uz-UZ');
  const debt = Number(data.total_amount) - Number(data.paid_amount);

  return (
    <div className="space-y-4">
      {data.note && <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-sm text-blue-700 font-medium">📝 {data.note}</div>}
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
              <td className="px-3 py-3 text-right text-slate-600">{fmtL(it.unit_price)} s</td>
              <td className="px-3 py-3 text-right text-amber-600">{it.discount > 0 ? `−${fmtL(it.discount)} s` : '—'}</td>
              <td className="px-4 py-3 text-right font-bold text-slate-800">{fmtL(it.subtotal)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="bg-slate-50 rounded-xl p-4 space-y-2">
        {[
          { l: 'Umumiy summa', v: fmtL(data.total_amount)+' s', c: 'font-bold text-slate-800' },
          Number(data.discount_amount) > 0 && { l: 'Chegirma', v: '−'+fmtL(data.discount_amount)+' s', c: 'text-amber-600 font-semibold' },
          { l: "To'langan", v: fmtL(data.paid_amount)+' s', c: 'font-bold text-emerald-700' },
          debt > 0 && { l: 'Qarz', v: fmtL(debt)+' s', c: 'font-bold text-red-600' },
        ].filter(Boolean).map((r, i) => (
          <div key={i} className="flex justify-between text-sm">
            <span className="text-slate-500">{r.l}</span><span className={r.c}>{r.v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
