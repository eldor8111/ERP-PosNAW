import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../api/axios';
import InventoryCountsPage from './InventoryCounts';

/* ─── Helpers ─── */
const fmt    = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtDt  = (d) => d ? new Date(d).toLocaleString('uz-UZ') : '—';
const fmtDay = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
const today  = () => new Date().toISOString().slice(0, 10);

/* ─── Status meta ─── */
const poMeta = {
  draft:     { l: 'Qoralama',     c: 'bg-slate-100 text-slate-600' },
  ordered:   { l: 'Yuborilgan',   c: 'bg-blue-100 text-blue-700' },
  partial:   { l: 'Qisman',       c: 'bg-amber-100 text-amber-700' },
  received:  { l: 'Qabul',        c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { l: 'Bekor',        c: 'bg-red-100 text-red-500' },
};
const trMeta = {
  pending:   { l: 'Kutilmoqda',   c: 'bg-amber-100 text-amber-700' },
  confirmed: { l: 'Tasdiqlandi',  c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { l: 'Bekor',        c: 'bg-red-100 text-red-500' },
};

const payMeta = {
  cash:   { l: 'Naqd',            c: 'bg-emerald-100 text-emerald-700' },
  card:   { l: 'Karta',           c: 'bg-blue-100 text-blue-700' },
  uzcard: { l: 'Uzcard',          c: 'bg-blue-100 text-blue-700' },
  humo:   { l: 'Humo',            c: 'bg-violet-100 text-violet-700' },
  bank:   { l: "Bank o'tkazmasi", c: 'bg-cyan-100 text-cyan-700' },
  click:  { l: 'Click',           c: 'bg-indigo-100 text-indigo-700' },
  payme:  { l: 'Payme',           c: 'bg-sky-100 text-sky-700' },
  visa:   { l: 'Visa',            c: 'bg-blue-100 text-blue-700' },
  uzum:   { l: 'Uzum',            c: 'bg-orange-100 text-orange-700' },
  debt:   { l: 'Qarz',            c: 'bg-amber-100 text-amber-700' },
  mixed:  { l: 'Aralash',         c: 'bg-purple-100 text-purple-700' },
};
const saleMeta = {
  completed: { l: 'Yakunlandi', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { l: 'Bekor',      c: 'bg-red-100 text-red-500' },
  pending:   { l: 'Kutilmoqda', c: 'bg-amber-100 text-amber-700' },
};

/* ─── UI atoms ─── */
function Badge({ meta, val }) {
  const m = meta[val] || { l: val, c: 'bg-slate-100 text-slate-600' };
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${m.c}`}>{m.l}</span>;
}
const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white transition-colors hover:border-slate-300';
function Btn({ v = 'primary', sm, children, ...p }) {
  const cl = {
    primary: 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm shadow-indigo-200',
    green:   'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm shadow-emerald-200',
    red:     'bg-red-500 hover:bg-red-600 text-white shadow-sm shadow-red-200',
    ghost:   'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200',
    amber:   'bg-amber-500 hover:bg-amber-600 text-white shadow-sm shadow-amber-200',
  }[v];
  return <button className={`${sm ? 'px-3 py-1.5 text-xs' : 'px-4 py-2.5 text-sm'} rounded-xl font-semibold transition-all ${cl} disabled:opacity-50 disabled:cursor-not-allowed`} {...p}>{children}</button>;
}
function Lbl({ t, children }) {
  return <div className="flex flex-col gap-1.5"><label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{t}</label>{children}</div>;
}

/* ─── Create page header (back + title + right) ─── */
function CreateHeader({ title, onBack, right }) {
  return (
    <div className="flex items-center gap-3 px-6 py-3.5 border-b border-slate-100 bg-white shrink-0 shadow-sm">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
        </svg>
        Orqaga
      </button>
      <div className="w-px h-6 bg-slate-200 shrink-0" />
      <h2 className="text-base font-bold text-slate-800 flex-1">{title}</h2>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

/* ─── Paginator ─── */
function Pager({ skip, limit, count, onChange }) {
  return (
    <div className="flex items-center justify-between px-5 py-3.5 border-t border-slate-100 bg-slate-50/60 text-sm">
      <span className="text-slate-400 text-xs font-medium">
        {count === 0 ? "Natija yo'q" : `${skip + 1}–${skip + count} ta ko'rsatildi`}
      </span>
      <div className="flex gap-1.5">
        <button disabled={skip === 0} onClick={() => onChange(Math.max(0, skip - limit))}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-white disabled:opacity-40 hover:border-indigo-300 hover:text-indigo-600 transition-all text-xs font-semibold shadow-sm">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
          Oldingi
        </button>
        <button disabled={count < limit} onClick={() => onChange(skip + limit)}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-white disabled:opacity-40 hover:border-indigo-300 hover:text-indigo-600 transition-all text-xs font-semibold shadow-sm">
          Keyingi
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  );
}

/* ─── Data table ─── */
function Tbl({ cols, rows, onRow, loading, skip = 0, limit, onChange }) {
  if (loading) return (
    <div className="py-20 text-center">
      <div className="inline-flex items-center gap-2 text-slate-400 text-sm">
        <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Yuklanmoqda...
      </div>
    </div>
  );
  if (!rows.length) return (
    <div className="py-20 text-center text-slate-400">
      <svg className="w-10 h-10 mx-auto mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p className="text-sm">Ma'lumot topilmadi</p>
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
                className={`transition-colors ${onRow ? 'cursor-pointer hover:bg-indigo-50/70 active:bg-indigo-100/50' : 'hover:bg-slate-50/80'}`}>
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
function ProdSearch({ products, onSelect, placeholder = 'Mahsulot qidiring...' }) {
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);

  const filtered = q.trim()
    ? products.filter(p =>
        p.name.toLowerCase().includes(q.toLowerCase()) ||
        p.sku?.toLowerCase().includes(q.toLowerCase()) ||
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
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"/>
        </svg>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className={`w-full pl-9 ${ic}`} />
        {q && (
          <button onMouseDown={() => { setQ(''); setOpen(true); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>
        )}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {products.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">Mahsulotlar yuklanmoqda...</div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">«{q}» bo'yicha topilmadi</div>
          ) : (
            <>
              {filtered.map(p => (
                <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
                  className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-slate-800 text-sm truncate">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
                  </div>
                  <div className="text-right shrink-0 text-xs">
                    <div className="font-semibold text-indigo-600">{fmt(p.sale_price)} so'm</div>
                    {p.wholesale_price > 0 && <div className="text-amber-600">Ulg: {fmt(p.wholesale_price)}</div>}
                    <div className="text-slate-400">Qoldiq: {fmt(p.stock_quantity)}</div>
                  </div>
                </button>
              ))}
              {products.length > 20 && !q.trim() && (
                <div className="px-4 py-2 text-xs text-slate-400 text-center bg-slate-50 border-t border-slate-100">
                  Jami {products.length} ta — qidiruv orqali toping
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}


/* ─── Supplier search combobox ─── */
function SupSearch({ suppliers, value, onChange, placeholder = "Ta'minotchi tanlang..." }) {
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);
  const selected        = suppliers.find(s => String(s.id) === String(value));

  const filtered = q.trim()
    ? suppliers.filter(s => s.name.toLowerCase().includes(q.toLowerCase())).slice(0, 12)
    : suppliers.slice(0, 12);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const pick = (s) => { onChange(s ? s.id : ''); setQ(''); setOpen(false); };

  return (
    <div className="relative" ref={ref}>
      <div className={`flex items-center border rounded-xl bg-white overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 transition-colors ${selected ? 'border-indigo-300' : 'border-slate-200'}`}>
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
            <div className="px-4 py-3 text-sm text-slate-400">Topilmadi</div>
          ) : filtered.map(s => (
            <button key={s.id} onMouseDown={() => pick(s)}
              className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-50 last:border-0">
              <div className="text-sm font-medium text-slate-800">{s.name}</div>
              {s.phone && <div className="text-xs text-slate-400">{s.phone}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Customer search combobox ─── */
function CustSearch({ customers, value, onChange, placeholder = 'Ism yoki telefon...' }) {
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);
  const selected        = customers.find(c => c.id === value);

  const filtered = q.trim()
    ? customers.filter(c =>
        c.name.toLowerCase().includes(q.toLowerCase()) ||
        (c.phone && c.phone.includes(q))
      ).slice(0, 12)
    : customers.slice(0, 12);

  useEffect(() => {
    const handler = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const select = (c) => { onChange(c ? c.id : ''); setQ(''); setOpen(false); };

  return (
    <div className="relative" ref={ref}>
      <div className="flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400">
        <input
          value={open ? q : (selected ? selected.name : '')}
          onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="flex-1 px-3 py-1.5 text-sm outline-none bg-transparent min-w-0"
        />
        {selected && (
          <button onClick={() => select(null)} className="px-2 text-slate-400 hover:text-red-400 text-lg leading-none">×</button>
        )}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-slate-400">Topilmadi</div>
          ) : filtered.map(c => (
            <button key={c.id} onMouseDown={() => select(c)}
              className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-50 last:border-0 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-slate-800">{c.name}</div>
                {c.phone && <div className="text-xs text-slate-400">{c.phone}</div>}
              </div>
              {c.debt_balance > 0 && (
                <span className="text-xs text-red-500 font-medium ml-2">Qarz: {fmt(c.debt_balance)}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Payment modal ─── */
function PayModal({ total, onPay, onClose }) {
  const [type, setType] = useState('cash');
  const [paid, setPaid] = useState(String(total));
  const change = Number(paid) - total;
  const PAY_OPTS = [
    { v: 'cash',   l: 'Naqd' },
    { v: 'uzcard', l: 'Uzcard' },
    { v: 'humo',   l: 'Humo' },
    { v: 'bank',   l: "Bank o'tkazmasi" },
    { v: 'click',  l: 'Click' },
    { v: 'payme',  l: 'Payme' },
    { v: 'visa',   l: 'Visa' },
    { v: 'uzum',   l: 'Uzum' },
    { v: 'mixed',  l: 'Aralash' },
    { v: 'debt',   l: 'Qarzga' },
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Modal header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">To'lov</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-xl text-slate-400 transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-6 space-y-4">
          {/* Total display */}
          <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 text-center">
            <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">To'lov summasi</div>
            <div className="text-3xl font-black text-indigo-700">{fmt(total)} <span className="text-lg font-normal text-indigo-400">so'm</span></div>
          </div>
          {/* Payment type */}
          <div className="grid grid-cols-5 gap-1.5">
            {PAY_OPTS.map(({ v, l }) => (
              <button key={v} onClick={() => setType(v)}
                className={`px-2 py-2.5 rounded-xl text-xs font-semibold border transition-all ${
                  type === v
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-200'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-indigo-300 hover:bg-indigo-50'
                }`}>
                {l}
              </button>
            ))}
          </div>
          {/* Amount input */}
          {type !== 'debt' && (
            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Qabul qilindi (so'm)</label>
              <input type="number" value={paid} onChange={e => setPaid(e.target.value)} autoFocus
                className="w-full border-2 border-slate-200 focus:border-indigo-500 rounded-xl px-4 py-3 text-2xl font-bold text-center text-slate-800 focus:outline-none transition-colors" />
              {change > 0 && Number(paid) > 0 && (
                <div className="mt-2 flex items-center justify-center gap-2 bg-emerald-50 border border-emerald-200 rounded-xl py-2.5">
                  <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                  <span className="text-sm text-emerald-700 font-bold">Qaytim: {fmt(change)} so'm</span>
                </div>
              )}
            </div>
          )}
          {/* Action buttons */}
          <div className="flex gap-3">
            <Btn v="ghost" onClick={onClose}>Bekor</Btn>
            <button onClick={() => onPay(type, type === 'debt' ? 0 : Number(paid))}
              className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200 active:scale-95">
              Tasdiqlash
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   SALE CREATE VIEW — split panel, wholesale-ready
══════════════════════════════════════════════════════════ */
function SaleCreateView({ products, customers, onBack, onSaved }) {
  const [cart, setCart]       = useState([]);
  const [custId, setCust]     = useState('');
  const [wholesale, setWhole] = useState(false);
  const [note, setNote]       = useState('');
  const [saving, setSaving]   = useState(false);
  const [err, setErr]         = useState('');
  const [showPay, setShowPay] = useState(false);
  const [prodQ, setProdQ]     = useState('');
  // quick-add modal
  const [qaItem, setQaItem]   = useState(null); // { product, qty, price }

  const getPrice = useCallback((p) =>
    wholesale && p.wholesale_price ? Number(p.wholesale_price) : Number(p.sale_price),
  [wholesale]);

  // When wholesale toggles, update all cart prices
  useEffect(() => {
    setCart(prev => prev.map(c => ({
      ...c,
      price: wholesale && c.product.wholesale_price
        ? Number(c.product.wholesale_price)
        : Number(c.product.sale_price),
    })));
  }, [wholesale]);

  const filteredProducts = products.filter(p => {
    if (!prodQ.trim()) return true;
    const lq = prodQ.toLowerCase();
    return p.name.toLowerCase().includes(lq) || p.sku?.toLowerCase().includes(lq) || p.barcode?.includes(lq);
  });

  const addToCart = (product, qty, price, discount = 0) => {
    setCart(prev => {
      const ex = prev.findIndex(c => c.product.id === product.id);
      if (ex >= 0) return prev.map((c, i) => i === ex ? { ...c, qty: c.qty + Number(qty), price: Number(price), discount: Number(discount) } : c);
      return [...prev, { product, qty: Number(qty), price: Number(price), discount: Number(discount) }];
    });
    setQaItem(null);
  };

  const subtotal = cart.reduce((s, c) => s + c.qty * c.price - Number(c.discount || 0), 0);

  const doSave = async (payType, paidAmount) => {
    if (!cart.length) { setErr("Kamida bitta mahsulot qo'shing"); return; }
    setSaving(true); setErr('');
    try {
      await api.post('/sales', {
        items: cart.map(c => ({ product_id: c.product.id, quantity: c.qty, unit_price: c.price, discount: c.discount })),
        payment_type:    payType,
        paid_amount:     paidAmount,
        discount_amount: 0,
        note:            note || null,
        customer_id:     custId ? Number(custId) : null,
      });
      onSaved(); onBack();
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); setShowPay(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 px-5 py-3 bg-white border-b border-slate-100 shrink-0 shadow-sm">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold shrink-0">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
          </svg>
          Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0" />
        <h2 className="text-base font-bold text-slate-800 shrink-0">Yangi sotuv</h2>
        <div className="flex-1 flex items-center gap-2.5">
          {/* Customer */}
          <div className="min-w-[240px]">
            <CustSearch customers={customers} value={custId} onChange={setCust} placeholder="Mijoz: ism yoki telefon..." />
          </div>
          {/* Wholesale */}
          <button onClick={() => setWhole(w => !w)}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-semibold border transition-all shrink-0 ${
              wholesale
                ? 'bg-amber-500 text-white border-amber-500 shadow-sm shadow-amber-200'
                : 'bg-white text-slate-600 border-slate-200 hover:border-amber-400 hover:text-amber-600'
            }`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            Ulgurji
          </button>
          {/* Note */}
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Izoh (ixtiyoriy)..."
            className="flex-1 max-w-sm border border-slate-200 rounded-xl px-3.5 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 placeholder-slate-400" />
        </div>
        <div className="text-xs text-slate-400 shrink-0 font-medium">{new Date().toLocaleString('uz-UZ')}</div>
      </div>

      {/* Body: left = products, right = cart */}
      <div className="flex flex-1 overflow-hidden gap-3 p-3">

        {/* LEFT — Product Browser */}
        <div className="w-[400px] shrink-0 bg-white rounded-2xl border border-slate-100 flex flex-col overflow-hidden shadow-sm">
          {/* Search */}
          <div className="p-3 border-b border-slate-100 bg-slate-50/50">
            <div className="relative">
              <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
              </svg>
              <input value={prodQ} onChange={e => setProdQ(e.target.value)}
                placeholder="Mahsulot nomi, barkod yoki SKU..."
                className="w-full pl-10 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white" />
            </div>
            <div className="flex items-center justify-between mt-2 px-1">
              <span className="text-xs text-slate-400 font-medium">{filteredProducts.length} ta mahsulot</span>
              {wholesale && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-600 font-semibold bg-amber-50 px-2 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block"></span>
                  Ulgurji narxlar
                </span>
              )}
            </div>
          </div>
          {/* Product list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {filteredProducts.length === 0 ? (
              <div className="py-16 text-center text-slate-400">
                <svg className="w-10 h-10 mx-auto mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
                <p className="text-sm">Mahsulot topilmadi</p>
              </div>
            ) : filteredProducts.slice(0, 100).map(p => {
              const inCart = cart.find(c => c.product.id === p.id);
              const displayPrice = getPrice(p);
              const stockLow = Number(p.stock_quantity) < 5;
              return (
                <button key={p.id}
                  onClick={() => setQaItem({ product: p, qty: 1, price: displayPrice, discount: 0 })}
                  className={`w-full text-left px-3 py-2.5 rounded-xl border transition-all flex items-center gap-3 group ${
                    inCart
                      ? 'bg-indigo-50 border-indigo-200'
                      : 'border-transparent hover:bg-slate-50 hover:border-slate-200'
                  }`}>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 ${
                    inCart ? 'bg-indigo-600 text-white' : 'bg-indigo-100 text-indigo-600'
                  }`}>
                    {inCart ? inCart.qty : p.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-800 text-sm truncate">{p.name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-400">{p.sku}</span>
                      {stockLow && (
                        <span className="text-xs text-red-500 font-medium">az: {fmt(p.stock_quantity)}</span>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-bold text-indigo-600">{fmt(displayPrice)}</div>
                    {wholesale && p.wholesale_price && Number(p.wholesale_price) !== Number(p.sale_price) && (
                      <div className="text-xs text-slate-400 line-through">{fmt(p.sale_price)}</div>
                    )}
                    <div className="text-xs text-slate-400 mt-0.5">{fmt(p.stock_quantity)} dona</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* RIGHT — Cart */}
        <div className="flex-1 bg-white rounded-2xl border border-slate-100 flex flex-col overflow-hidden shadow-sm">
          {/* Cart header */}
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 shrink-0 bg-slate-50/50">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <span className="text-sm font-bold text-slate-700">
                Savat {cart.length > 0 && <span className="text-indigo-600 ml-1">({cart.length} tur)</span>}
              </span>
            </div>
            {cart.length > 0 && (
              <button onClick={() => setCart([])} className="inline-flex items-center gap-1 text-xs text-red-400 hover:text-red-600 hover:bg-red-50 px-2 py-1 rounded-lg transition-all">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                Tozalash
              </button>
            )}
          </div>

          {/* Cart table */}
          <div className="flex-1 overflow-y-auto">
            {cart.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-300">
                <svg className="w-16 h-16 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                    d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
                <p className="text-base">Chap tarafdan mahsulot tanlang</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 w-8">№</th>
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">MAHSULOT</th>
                    <th className="text-center px-3 py-2.5 text-xs font-semibold text-slate-500 w-28">MIQDOR</th>
                    <th className="text-center px-3 py-2.5 text-xs font-semibold text-slate-500 w-32">NARXI</th>
                    <th className="text-center px-3 py-2.5 text-xs font-semibold text-slate-500 w-28">CHEGIRMA</th>
                    <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 w-32">SUMMA</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {cart.map((c, i) => (
                    <tr key={i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 text-slate-400 text-xs">{i + 1}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-800">{c.product.name}</div>
                        <div className="text-xs text-slate-400">{c.product.sku} · {c.product.unit || 'dona'}</div>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button onClick={() => setCart(p => p.map((x, idx) => idx === i ? { ...x, qty: Math.max(0.001, x.qty - 1) } : x))}
                            className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center text-sm leading-none">−</button>
                          <input type="number" min="0.001" step="any" value={c.qty}
                            onChange={e => setCart(p => p.map((x, idx) => idx === i ? { ...x, qty: Number(e.target.value) || 1 } : x))}
                            className="w-14 text-center border border-slate-200 rounded px-1 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
                          <button onClick={() => setCart(p => p.map((x, idx) => idx === i ? { ...x, qty: x.qty + 1 } : x))}
                            className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center text-sm leading-none">+</button>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <input type="number" min="0" value={c.price}
                          onChange={e => setCart(p => p.map((x, idx) => idx === i ? { ...x, price: Number(e.target.value) || 0 } : x))}
                          className="w-28 text-center border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
                      </td>
                      <td className="px-3 py-3 text-center">
                        <input type="number" min="0" value={c.discount || 0}
                          onChange={e => setCart(p => p.map((x, idx) => idx === i ? { ...x, discount: Number(e.target.value) || 0 } : x))}
                          className="w-24 text-center border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-red-300 text-red-600" />
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-800">{fmt(c.qty * c.price - Number(c.discount || 0))}</td>
                      <td className="pr-3">
                        <button onClick={() => setCart(p => p.filter((_, idx) => idx !== i))}
                          className="w-6 h-6 text-slate-300 hover:text-red-500 rounded transition-colors flex items-center justify-center">✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Cart totals */}
          {cart.length > 0 && (
            <div className="border-t border-slate-200 px-4 py-3 bg-slate-50 flex items-center justify-between shrink-0">
              <span className="text-sm text-slate-500">{cart.length} xil, {cart.reduce((s,c) => s + c.qty, 0)} ta mahsulot</span>
              <div className="text-right">
                <span className="text-xs text-slate-400 mr-2">Jami:</span>
                <span className="text-xl font-bold text-indigo-600">{fmt(subtotal)} so'm</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-5 py-3.5 bg-white border-t border-slate-100 shrink-0 shadow-[0_-1px_8px_rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-3">
          <Btn v="ghost" onClick={onBack}>Bekor qilish</Btn>
          {err && <span className="text-red-500 text-sm font-medium">{err}</span>}
        </div>
        <div className="flex items-center gap-3">
          {cart.length > 0 && (
            <div className="text-sm text-slate-500 mr-2">
              Jami: <span className="font-bold text-slate-800 text-base">{fmt(subtotal)} so'm</span>
            </div>
          )}
          <Btn v="amber" disabled={saving || !cart.length} onClick={() => doSave('debt', 0)}>
            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            Qarzga saqlash
          </Btn>
          <button disabled={saving || !cart.length} onClick={() => { setErr(''); setShowPay(true); }}
            className="inline-flex items-center gap-2.5 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200 active:scale-95">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
            To'lovga o'tish
            {cart.length > 0 && <span className="bg-white/20 px-2 py-0.5 rounded-lg text-xs font-bold">{fmt(subtotal)}</span>}
          </button>
        </div>
      </div>

      {/* Quick-add modal */}
      {qaItem && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-4" onClick={() => setQaItem(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center text-sm font-bold shrink-0">
                {qaItem.product.name.slice(0,2).toUpperCase()}
              </div>
              <div>
                <div className="font-bold text-slate-800">{qaItem.product.name}</div>
                <div className="text-xs text-slate-400">{qaItem.product.sku}</div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div>
                <label className="text-xs font-medium text-slate-500 mb-1 block">Miqdor</label>
                <input type="number" min="0.001" step="any" value={qaItem.qty}
                  autoFocus
                  onChange={e => setQaItem(v => ({ ...v, qty: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && addToCart(qaItem.product, qaItem.qty, qaItem.price, qaItem.discount)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 text-center font-bold" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 mb-1 block">Narxi (so'm)</label>
                <input type="number" min="0" value={qaItem.price}
                  onChange={e => setQaItem(v => ({ ...v, price: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && addToCart(qaItem.product, qaItem.qty, qaItem.price, qaItem.discount)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 text-center font-bold" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 mb-1 block">Chegirma (so'm)</label>
                <input type="number" min="0" value={qaItem.discount}
                  onChange={e => setQaItem(v => ({ ...v, discount: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && addToCart(qaItem.product, qaItem.qty, qaItem.price, qaItem.discount)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 text-center font-bold" />
              </div>
            </div>
            {qaItem.product.wholesale_price && (
              <div className="flex gap-2 mb-4">
                <button onClick={() => setQaItem(v => ({ ...v, price: Number(v.product.sale_price) }))}
                  className={`flex-1 py-1.5 text-xs rounded-lg border transition-all ${Number(qaItem.price) === Number(qaItem.product.sale_price) ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-200 text-slate-600 hover:border-indigo-300'}`}>
                  Chakana: {fmt(qaItem.product.sale_price)}
                </button>
                <button onClick={() => setQaItem(v => ({ ...v, price: Number(v.product.wholesale_price) }))}
                  className={`flex-1 py-1.5 text-xs rounded-lg border transition-all ${Number(qaItem.price) === Number(qaItem.product.wholesale_price) ? 'bg-amber-500 text-white border-amber-500' : 'border-slate-200 text-slate-600 hover:border-amber-300'}`}>
                  Ulgurji: {fmt(qaItem.product.wholesale_price)}
                </button>
              </div>
            )}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-400">Jami:</span>
              <span className="text-lg font-bold text-indigo-600">{fmt(Number(qaItem.qty) * Number(qaItem.price) - Number(qaItem.discount))} so'm</span>
            </div>
            <div className="flex gap-2">
              <Btn v="ghost" onClick={() => setQaItem(null)} sm>Bekor</Btn>
              <button onClick={() => addToCart(qaItem.product, qaItem.qty, qaItem.price, qaItem.discount)}
                className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm transition-colors">
                + Savatga qo'shish
              </button>
            </div>
          </div>
        </div>
      )}

      {showPay && <PayModal total={subtotal} onClose={() => setShowPay(false)} onPay={doSave} />}
    </div>
  );
}

/* ─── Sale detail view ─── */
function SaleDetailView({ saleId, onBack }) {
  const [sale, setSale] = useState(null);
  useEffect(() => {
    api.get(`/sales/${saleId}`).then(r => setSale(r.data)).catch(() => {});
  }, [saleId]);
  if (!sale) return <div className="py-20 text-center text-slate-400">Yuklanmoqda...</div>;
  const debt = Number(sale.total_amount) - Number(sale.paid_amount);
  return (
    <div className="fixed inset-0 z-40 bg-white flex flex-col">
      <CreateHeader title={`Sotuv · ${sale.number}`} onBack={onBack}
        right={<Badge meta={saleMeta} val={sale.status} />}
      />
      <div className="p-6 overflow-y-auto flex-1">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[['Kassir', sale.cashier_name],['Sana', fmtDt(sale.created_at)],['To\'lov', <Badge meta={payMeta} val={sale.payment_type} />],['Holat', <Badge meta={saleMeta} val={sale.status} />]].map(([k,v]) => (
            <div key={k} className="bg-slate-50 rounded-xl p-3">
              <div className="text-xs text-slate-500 mb-1">{k}</div>
              <div className="font-semibold">{v}</div>
            </div>
          ))}
        </div>
        <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden mb-6">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">№</th>
              <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">Mahsulot</th>
              <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Soni</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Narxi</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Chegirma</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Jami</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sale.items?.map((item, i) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-400 text-xs">{i + 1}</td>
                <td className="px-4 py-3 font-medium">{item.product_name}</td>
                <td className="px-4 py-3 text-center">{item.quantity}</td>
                <td className="px-4 py-3 text-right">{fmt(item.unit_price)}</td>
                <td className="px-4 py-3 text-right text-red-500">{Number(item.discount) > 0 ? `−${fmt(item.discount)}` : '—'}</td>
                <td className="px-4 py-3 text-right font-semibold">{fmt(item.subtotal)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex justify-end">
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 min-w-64 space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Umumiy summa:</span><span className="font-medium">{fmt(sale.total_amount)}</span></div>
            {Number(sale.discount_amount) > 0 && <div className="flex justify-between"><span className="text-slate-500">Chegirma:</span><span className="text-red-500 font-medium">−{fmt(sale.discount_amount)}</span></div>}
            <div className="flex justify-between"><span className="text-slate-500">To'lov miqdori:</span><span className="font-medium">{fmt(sale.paid_amount)}</span></div>
            {debt > 0 && <div className="flex justify-between border-t pt-2"><span className="text-slate-500">Qarzga:</span><span className="text-red-500 font-bold">{fmt(debt)}</span></div>}
            <div className="flex justify-between border-t pt-2"><span className="font-bold text-slate-700">Chegirma bilan summa:</span><span className="font-bold text-xl text-indigo-600">{fmt(sale.total_amount)}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   SALES TAB
══════════════════════════════════════════════════════════ */
function SalesTab({ products, customers }) {
  const [mode, setMode]       = useState('list');
  const [selectedId, setSel]  = useState(null);
  const [sales, setSales]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip]       = useState(0);
  const LIMIT = 20;
  const [f, setF] = useState({ dateFrom: today(), dateTo: today(), payType: '', status: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (f.dateFrom) params.date_from = f.dateFrom;
      if (f.dateTo)   params.date_to   = f.dateTo;
      if (f.status)   params.status    = f.status;
      const r = await api.get('/sales/', { params });
      setSales(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, f]);

  useEffect(() => { if (mode === 'list') load(); }, [load, mode]);

  if (mode === 'create') return <SaleCreateView products={products} customers={customers} onBack={() => setMode('list')} onSaved={load} />;
  if (mode === 'detail') return <SaleDetailView saleId={selectedId} onBack={() => setMode('list')} />;

  const totals = { sum: sales.reduce((s,r) => s+Number(r.total_amount), 0), paid: sales.reduce((s,r) => s+Number(r.paid_amount||0), 0) };

  const cols = [
    { k:'number',       l:'Raqam' },
    { k:'cashier_name', l:'Xodim' },
    { k:'items_count',  l:'Mahsulotlar', r: v => `${v} ta` },
    { k:'total_amount', l:'Umumiy summa', r: v => fmt(v) },
    { k:'discount_amount', l:'Chegirma', r: v => Number(v)>0?`−${fmt(v)}`:'—' },
    { k:'total_amount', l:'Chegirma bilan summa', r: v => <strong className="text-indigo-600">{fmt(v)}</strong> },
    { k:'paid_amount',  l:"To'lov miqdori", r: v => fmt(v) },
    { k:'paid_amount',  l:'Qarzga', r: (v,row) => { const d=Number(row.total_amount)-Number(v); return d>0?<span className="text-red-500 font-semibold">{fmt(d)}</span>:'—'; } },
    { k:'payment_type', l:"To'lov turi", r: v => <Badge meta={payMeta} val={v} /> },
    { k:'status',       l:'Sotuv jarayoni', r: v => <Badge meta={saleMeta} val={v} /> },
    { k:'created_at',   l:'Sana', r: v => fmtDay(v) },
  ];

  return (
    <div className="space-y-3">
      {/* Header: stats + action */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-500">Jami:</span>
          <span className="font-bold text-slate-800">{fmt(totals.sum)}</span>
          <span className="text-slate-300">|</span>
          <span className="text-emerald-600 font-semibold">{fmt(totals.paid)}</span>
          <span className="text-slate-300">|</span>
          <span className="text-red-500 font-semibold">{fmt(totals.sum - totals.paid)}</span>
        </div>
        <div className="flex items-center gap-2">
          <Btn v="ghost" sm onClick={() => { /* excel */ }}>Excel Ga Ko'chirish</Btn>
          <Btn sm onClick={() => setMode('create')}>
            <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            Yangi Sotuv
          </Btn>
        </div>
      </div>

      {/* Filters — rasmdagi kabi 2 qator */}
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3">
          <input type="text" placeholder="Status" value={f.statusQ||''} onChange={e => {
            const q = e.target.value;
            const match = Object.entries(saleMeta).find(([,m]) => m.l.toLowerCase().startsWith(q.toLowerCase()));
            setF({...f, statusQ: q, status: match ? match[0] : ''});
          }} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateFrom} onChange={e => setF({...f, dateFrom:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateTo} onChange={e => setF({...f, dateTo:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          <input type="text" placeholder="Contragent" className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
          <span className="text-slate-300 text-lg">+</span>
          <input type="text" placeholder="Xodim" className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="text" placeholder="Foydalanuvchi" className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <Tbl cols={cols} rows={sales} loading={loading} skip={skip} limit={LIMIT} onChange={setSkip}
          onRow={row => { setSel(row.id); setMode('detail'); }} />
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   KIRIM CREATE VIEW — split panel
══════════════════════════════════════════════════════════ */
function KirimCreateView({ products, warehouses, suppliers, onBack, onSaved }) {
  const [sub, setSub]             = useState('po');
  // PO form
  const [poForm, setPoForm]       = useState({ supplier_id:'', warehouse_id:'', note:'', expected_date:'' });
  const [poItems, setPoItems]     = useState([]);
  // Manual form
  const [manSupId, setManSupId]   = useState('');
  const [manWarehouseId, setManWh]= useState('');
  const [manItems, setManItems]   = useState([]);
  const [manNote, setManNote]     = useState('');
  // Auto-update price flags
  const [autoRetail, setAutoRet]     = useState(false);
  const [autoWholesale, setAutoWho]  = useState(false);
  // USD exchange rate
  const [usdRate, setUsdRate]        = useState('12700');
  const [saving, setSaving]          = useState(false);
  const [err, setErr]                = useState('');

  // Left panel: selected product + input fields
  const [sel, setSel]           = useState(null);
  const [qty, setQty]           = useState('1');
  const [cost, setCost]         = useState('');
  const [discType, setDiscType] = useState('pct');  // 'pct' | 'amt'
  const [discVal, setDiscVal]   = useState('0');
  const [currency, setCurrency] = useState('UZS');  // 'UZS' | 'USD'

  const selectProduct = (p) => {
    setSel(p);
    setCost(String(Number(p.cost_price) || ''));
    setQty('1'); setDiscVal('0'); setDiscType('pct'); setCurrency('UZS');
  };

  // Net cost per unit in UZS
  const calcNet = (rawCost, dType, dVal, cur) => {
    const c = Number(rawCost) || 0;
    const d = Number(dVal) || 0;
    const net = dType === 'pct' ? c * (1 - d / 100) : c - d;
    return cur === 'USD' ? net * (Number(usdRate) || 12700) : net;
  };
  const selNet = calcNet(cost, discType, discVal, currency);

  const addItem = () => {
    if (!sel || !qty) return;
    const base = {
      product_id: sel.id, product_name: sel.name, unit: sel.unit || 'dona',
      unit_cost: Number(cost) || 0, discount_type: discType, discount_val: Number(discVal) || 0,
      currency, net_cost: selNet,
    };
    if (sub === 'po') {
      setPoItems(prev => {
        const ex = prev.find(x => x.product_id === sel.id);
        if (ex) return prev.map(x => x.product_id === sel.id ? { ...x, qty_ordered: x.qty_ordered + Number(qty) } : x);
        return [...prev, { ...base, qty_ordered: Number(qty) }];
      });
    } else {
      setManItems(prev => [...prev, { ...base, quantity: Number(qty), batch_num:'', lot_num:'', mfg_date:'', expiry_date:'', reason:'' }]);
    }
    setSel(null); setQty('1'); setCost(''); setDiscVal('0');
  };

  const updPoItem = (i, field, val) => setPoItems(prev => prev.map((x, idx) => idx === i ? { ...x, [field]: val, net_cost: calcNet(field==='unit_cost'?val:x.unit_cost, field==='discount_type'?val:x.discount_type, field==='discount_val'?val:x.discount_val, field==='currency'?val:x.currency) } : x));
  const updManItem = (i, field, val) => setManItems(prev => prev.map((x, idx) => idx === i ? { ...x, [field]: val, net_cost: calcNet(field==='unit_cost'?val:x.unit_cost, field==='discount_type'?val:x.discount_type, field==='discount_val'?val:x.discount_val, field==='currency'?val:x.currency) } : x));

  const activeItems = sub === 'po' ? poItems : manItems;
  const totalNet = activeItems.reduce((s, i) => s + (sub==='po' ? i.qty_ordered : i.quantity) * (i.net_cost||0), 0);
  const hasCurrency = activeItems.some(i => i.currency === 'USD');

  const savePo = async () => {
    if (!poForm.supplier_id || !poForm.warehouse_id || !poItems.length) { setErr("Barcha majburiy maydonlarni to'ldiring"); return; }
    setSaving(true); setErr('');
    try {
      await api.post('/purchase-orders', {
        supplier_id: Number(poForm.supplier_id), warehouse_id: Number(poForm.warehouse_id),
        note: poForm.note || null, expected_date: poForm.expected_date || null,
        update_retail: autoRetail, update_wholesale: autoWholesale,
        items: poItems.map(i => ({ product_id: i.product_id, qty_ordered: i.qty_ordered, unit_cost: i.net_cost })),
      });
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const saveManual = async () => {
    const items = manItems.filter(i => i.quantity > 0);
    if (!items.length) { setErr("Mahsulot qo'shing"); return; }
    setSaving(true); setErr('');
    try {
      await api.post('/inventory/receive', {
        supplier_id: manSupId ? Number(manSupId) : null,
        warehouse_id: manWarehouseId ? Number(manWarehouseId) : null,
        update_retail: autoRetail, update_wholesale: autoWholesale,
        note: manNote || null,
        items: items.map(i => {
          const parts = [];
          if (i.batch_num)   parts.push(`Partiya: ${i.batch_num}`);
          if (i.lot_num)     parts.push(`Lot: ${i.lot_num}`);
          if (i.mfg_date)    parts.push(`Ishlab: ${i.mfg_date}`);
          if (i.expiry_date) parts.push(`Muddati: ${i.expiry_date}`);
          if (i.reason)      parts.push(i.reason);
          return { product_id: i.product_id, quantity: i.quantity, cost_price: i.net_cost, reason: parts.join(' | ') || null };
        }),
      });
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <CreateHeader title={sub === 'po' ? 'Yangi buyurtma (PO)' : "Qo'lda kirim"} onBack={onBack}
        right={
          <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
            {[['po','Buyurtma (PO)'],['manual',"Qo'lda kirim"]].map(([v,l]) => (
              <button key={v} onClick={() => { setSub(v); setErr(''); setDiscVal('0'); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${sub===v?'bg-white shadow text-indigo-700':'text-slate-600'}`}>{l}</button>
            ))}
          </div>
        }
      />

      {/* ── Header fields ── */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-100 bg-white shrink-0 flex-wrap shadow-sm">
        {/* Supplier combobox — both modes */}
        <div className="w-64">
          <SupSearch
            suppliers={suppliers}
            value={sub === 'po' ? poForm.supplier_id : manSupId}
            onChange={v => sub === 'po' ? setPoForm(f=>({...f,supplier_id:v})) : setManSupId(v)}
            placeholder="Ta'minotchi tanlang... *"
          />
        </div>
        {/* Warehouse */}
        <select
          value={sub === 'po' ? poForm.warehouse_id : manWarehouseId}
          onChange={e => sub === 'po' ? setPoForm(f=>({...f,warehouse_id:e.target.value})) : setManWh(e.target.value)}
          className={`${ic} min-w-40`}>
          <option value="">Ombor *</option>
          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        {sub === 'po' && (
          <input type="date" value={poForm.expected_date} onChange={e => setPoForm(f=>({...f,expected_date:e.target.value}))} className={ic} />
        )}
        {/* USD exchange rate — shown when any item uses USD */}
        {(hasCurrency || currency === 'USD') && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 font-semibold">1 USD =</span>
            <input type="number" value={usdRate} onChange={e => setUsdRate(e.target.value)}
              className={`${ic} w-28`} placeholder="Kurs" />
            <span className="text-xs text-slate-500">so'm</span>
          </div>
        )}
        <input placeholder="Izoh" value={sub==='po' ? poForm.note : manNote}
          onChange={e => sub==='po' ? setPoForm(f=>({...f,note:e.target.value})) : setManNote(e.target.value)}
          className={`${ic} flex-1 min-w-32`} />
      </div>

      {/* ── Split body ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div className="w-80 border-r border-slate-100 p-5 flex flex-col gap-4 overflow-y-auto shrink-0 bg-white shadow-sm">
          <Lbl t="Mahsulot qidirish">
            <ProdSearch products={products} onSelect={selectProduct} />
          </Lbl>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 space-y-3">
              {/* Product info */}
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {sel.name.slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm truncate">{sel.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    Qoldiq: <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit||'dona'}
                    &nbsp;·&nbsp; Chakana: <strong className="text-indigo-600">{fmt(sel.sale_price)}</strong>
                  </div>
                </div>
              </div>

              {/* Cost price + currency */}
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Tan narxi</label>
                <div className="flex rounded-xl border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-indigo-500 overflow-hidden">
                  <input type="number" min="0" value={cost} onChange={e => setCost(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-2 text-sm focus:outline-none bg-transparent" />
                  <div className="flex border-l border-slate-200">
                    {['UZS','USD'].map(c => (
                      <button key={c} type="button" onClick={() => setCurrency(c)}
                        className={`px-2.5 py-2 text-xs font-bold transition-colors ${currency===c?'bg-indigo-600 text-white':'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}>
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Discount */}
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Chegirma</label>
                <div className="flex rounded-xl border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-indigo-500 overflow-hidden">
                  <input type="number" min="0" value={discVal} onChange={e => setDiscVal(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-2 text-sm focus:outline-none bg-transparent" />
                  <div className="flex border-l border-slate-200">
                    {[['pct','%'],['amt','so\'m']].map(([v,l]) => (
                      <button key={v} type="button" onClick={() => setDiscType(v)}
                        className={`px-2.5 py-2 text-xs font-bold transition-colors ${discType===v?'bg-amber-500 text-white':'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Net cost preview */}
              {(Number(discVal) > 0 || currency === 'USD') && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2 flex justify-between items-center">
                  <span className="text-xs text-emerald-700 font-semibold">Sof tan narxi:</span>
                  <span className="text-sm font-black text-emerald-700">{fmt(Math.round(selNet))} so'm</span>
                </div>
              )}

              {/* Quantity */}
              <Lbl t="Miqdor">
                <div className="flex gap-2 items-center">
                  <input type="number" min="1" step="any" value={qty} onChange={e => setQty(e.target.value)}
                    className={`flex-1 ${ic} text-center font-bold`} />
                  <span className="text-sm text-slate-500 font-medium shrink-0">{sel.unit||'dona'}</span>
                </div>
              </Lbl>

              {/* Total preview */}
              <div className="text-xs text-slate-500 text-right">
                Jami: <strong className="text-indigo-700">{fmt(Math.round(selNet * Number(qty)))} so'm</strong>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-8">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
              </svg>
              <p className="text-sm text-center">Mahsulot qidiring va tanlang</p>
            </div>
          )}

          <button onClick={addItem} disabled={!sel || !qty}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-indigo-200 active:scale-95">
            <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Ro'yxatga qo'shish
          </button>

          {activeItems.length > 0 && (
            <div className="bg-indigo-600 rounded-2xl p-4 text-white">
              <div className="text-xs font-semibold opacity-70 uppercase tracking-wide">Jami summa</div>
              <div className="text-2xl font-black mt-1">{fmt(Math.round(totalNet))} <span className="text-sm font-normal opacity-70">so'm</span></div>
              <div className="text-xs opacity-60 mt-1">{activeItems.length} ta mahsulot</div>
            </div>
          )}
        </div>

        {/* ── Right: items table ── */}
        <div className="flex-1 overflow-y-auto">
          {activeItems.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
              <p>Mahsulot qo'shing</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-400 w-8">№</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Mahsulot</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-20">Soni</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Narxi</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-28">Chegirma</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Sof narx</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Jami</th>
                  {sub==='manual' && <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Partiya</th>}
                  {sub==='manual' && <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Lot</th>}
                  {sub==='manual' && <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Muddati</th>}
                  {sub==='manual' && <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Izoh</th>}
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activeItems.map((it, i) => {
                  const qty_n = sub === 'po' ? it.qty_ordered : it.quantity;
                  const discPct = it.discount_type === 'pct' ? it.discount_val : (it.unit_cost > 0 ? (it.discount_val / it.unit_cost * 100).toFixed(1) : 0);
                  const updFn = sub === 'po' ? updPoItem : updManItem;
                  return (
                    <tr key={i} className="hover:bg-slate-50 group">
                      <td className="px-3 py-2.5 text-slate-400 text-xs">{i+1}</td>
                      <td className="px-3 py-2.5">
                        <div className="font-medium text-sm">{it.product_name}</div>
                        <div className="text-xs text-slate-400">{it.unit}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <input type="number" min="1" value={qty_n}
                          onChange={e => updFn(i, sub==='po'?'qty_ordered':'quantity', Number(e.target.value))}
                          className="w-16 text-center border border-slate-200 rounded-lg px-1.5 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <input type="number" min="0" value={it.unit_cost}
                            onChange={e => updFn(i, 'unit_cost', e.target.value)}
                            className="w-24 text-right border border-slate-200 rounded-lg px-1.5 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                          <button onClick={() => updFn(i, 'currency', it.currency==='UZS'?'USD':'UZS')}
                            className={`text-[10px] font-bold px-1.5 py-1 rounded-md transition-colors ${it.currency==='USD'?'bg-emerald-100 text-emerald-700':'bg-slate-100 text-slate-500'}`}>
                            {it.currency}
                          </button>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <input type="number" min="0" value={it.discount_val}
                            onChange={e => updFn(i, 'discount_val', e.target.value)}
                            className="w-14 text-center border border-slate-200 rounded-lg px-1 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                          <button onClick={() => updFn(i, 'discount_type', it.discount_type==='pct'?'amt':'pct')}
                            className={`text-[10px] font-bold px-1.5 py-1 rounded-md min-w-[28px] transition-colors ${it.discount_type==='pct'?'bg-amber-100 text-amber-700':'bg-violet-100 text-violet-700'}`}>
                            {it.discount_type==='pct'?'%':'so\'m'}
                          </button>
                        </div>
                        {Number(it.discount_val) > 0 && <div className="text-[10px] text-amber-600 mt-0.5">–{discPct}%</div>}
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold text-emerald-700 text-sm">
                        {fmt(Math.round(it.net_cost))}
                      </td>
                      <td className="px-3 py-2.5 text-right font-bold text-slate-800">
                        {fmt(Math.round(it.net_cost * qty_n))}
                      </td>
                      {sub==='manual' && (
                        <td className="px-2 py-2">
                          <input placeholder="Partiya №" value={it.batch_num}
                            onChange={e => updManItem(i,'batch_num',e.target.value)}
                            className={`w-22 ${ic} text-xs`} />
                        </td>
                      )}
                      {sub==='manual' && (
                        <td className="px-2 py-2">
                          <input placeholder="Lot №" value={it.lot_num}
                            onChange={e => updManItem(i,'lot_num',e.target.value)}
                            className={`w-18 ${ic} text-xs`} />
                        </td>
                      )}
                      {sub==='manual' && (
                        <td className="px-2 py-2">
                          <input type="date" value={it.expiry_date}
                            onChange={e => updManItem(i,'expiry_date',e.target.value)}
                            className={`${ic} text-xs`} />
                        </td>
                      )}
                      {sub==='manual' && (
                        <td className="px-2 py-2">
                          <input placeholder="Izoh" value={it.reason}
                            onChange={e => updManItem(i,'reason',e.target.value)}
                            className={`min-w-[90px] ${ic} text-xs`} />
                        </td>
                      )}
                      <td className="pr-2">
                        <button onClick={() => sub==='po' ? setPoItems(p=>p.filter((_,idx)=>idx!==i)) : setManItems(p=>p.filter((_,idx)=>idx!==i))}
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
          <span className="text-xs text-slate-400 font-semibold uppercase tracking-wide">Narx yangilash:</span>
          <button onClick={() => setAutoRet(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoRetail?'bg-indigo-600 text-white border-indigo-600':'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            Chakana narx
          </button>
          <button onClick={() => setAutoWho(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoWholesale?'bg-amber-500 text-white border-amber-500':'bg-white text-slate-600 border-slate-200 hover:border-amber-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            Ulgurji narx
          </button>
        </div>
        <div className="flex gap-3 ml-auto items-center">
          {err && <span className="text-red-500 text-sm">{err}</span>}
          <Btn v="ghost" onClick={onBack}>Bekor qilish</Btn>
          <Btn onClick={sub==='po' ? savePo : saveManual} disabled={saving}>
            {saving ? 'Saqlanmoqda...' : (sub==='po' ? 'Buyurtma yaratish' : 'Qabul qilish')}
          </Btn>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   KIRIMLAR TAB
══════════════════════════════════════════════════════════ */
function KirimlarTab({ products, warehouses, suppliers, users }) {
  const [mode, setMode]       = useState('list');
  const [pos, setPos]         = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip]       = useState(0);
  const [f, setF]             = useState({ dateFrom: today(), dateTo: today(), status: '', supplier_id: '', warehouse_id: '', user_id: '', statusQ: '', supplierQ: '', warehouseQ: '', userQ: '' });
  const [detail, setDetail]   = useState(null);
  const [recModal, setRec]    = useState(null);
  const [recSaving, setRS]    = useState(false);
  const LIMIT = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (f.status) params.status = f.status;
      if (f.dateFrom) params.date_from = f.dateFrom;
      if (f.dateTo) params.date_to = f.dateTo;
      if (f.supplier_id) params.supplier_id = f.supplier_id;
      if (f.warehouse_id) params.warehouse_id = f.warehouse_id;
      if (f.user_id) params.user_id = f.user_id;
      const r = await api.get('/purchase-orders', { params });
      setPos(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, f]);

  useEffect(() => { if (mode === 'list') load(); }, [load, mode]);

  const openDetail = async (row) => {
    const r = await api.get(`/purchase-orders/${row.id}`);
    setDetail(r.data);
  };

  const receivePo = async () => {
    const pending = recModal.items.filter(i => Number(i.qty_ordered) > Number(i.qty_received));
    setRS(true);
    try {
      await api.post(`/purchase-orders/${recModal.id}/receive`, {
        items: pending.map(i => ({ po_item_id: i.id, qty_received: Number(i.qty_ordered) - Number(i.qty_received) }))
      });
      setRec(null); setDetail(null); load();
    } catch { /* ignore */ } finally { setRS(false); }
  };

  if (mode === 'create') return <KirimCreateView products={products} warehouses={warehouses} suppliers={suppliers} onBack={() => setMode('list')} onSaved={load} />;

  const cols = [
    { k:'number',         l:'Raqam' },
    { k:'supplier_name',  l:"Ta'minotchi" },
    { k:'warehouse_name', l:'Ombor' },
    { k:'status',         l:'Holat', r: v => <Badge meta={poMeta} val={v} /> },
    { k:'total_amount',   l:"Jami (so'm)", r: v => fmt(v) },
    { k:'created_at',     l:'Sana', r: v => fmtDay(v) },
    { k:'id', l:'', r: (_,row) => ['draft','ordered','partial'].includes(row.status) ? (
      <button onClick={e=>{e.stopPropagation(); openDetail(row);}}
        className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 font-medium whitespace-nowrap">
        Qabul qilish
      </button>
    ) : null },
  ];

  return (
    <div className="space-y-3">
      {/* Header: action */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          <Btn onClick={() => setMode('create')} sm>
            <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            Yangi kirim
          </Btn>
        </div>
      </div>

      {/* Filters — Custom 2-row grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3">
          <input type="text" placeholder="Status" value={f.statusQ||''} onChange={e => {
            const q = e.target.value;
            const match = Object.entries(poMeta).find(([,m]) => m.l.toLowerCase().startsWith(q.toLowerCase()));
            setF({...f, statusQ: q, status: match ? match[0] : ''});
          }} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateFrom} onChange={e => setF({...f, dateFrom:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateTo} onChange={e => setF({...f, dateTo:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          {/* Supplier */}
          <div className="relative">
            <input type="text" value={f.supplierQ||''} placeholder="Contragent"
              onChange={e => setF({...f, supplierQ: e.target.value, supplier_id: ''})}
              onFocus={() => setF(p => ({...p, _supOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _supOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._supOpen && f.supplierQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {suppliers.filter(s => s.name.toLowerCase().includes(f.supplierQ.toLowerCase())).slice(0,10).map(s => (
                  <button key={s.id} onMouseDown={() => setF({...f, supplier_id: String(s.id), supplierQ: s.name, _supOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{s.name}</button>
                ))}
              </div>
            )}
          </div>
          <span className="text-slate-300 text-lg">+</span>
          {/* Warehouse */}
          <div className="relative">
            <input type="text" value={f.warehouseQ||''} placeholder="Xodim (Ombor)"
              onChange={e => setF({...f, warehouseQ: e.target.value, warehouse_id: ''})}
              onFocus={() => setF(p => ({...p, _whOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _whOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._whOpen && f.warehouseQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {warehouses.filter(w => w.name.toLowerCase().includes(f.warehouseQ.toLowerCase())).slice(0,10).map(w => (
                  <button key={w.id} onMouseDown={() => setF({...f, warehouse_id: String(w.id), warehouseQ: w.name, _whOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{w.name}</button>
                ))}
              </div>
            )}
          </div>
          {/* User */}
          <div className="relative">
            <input type="text" value={f.userQ||''} placeholder="Foydalanuvchi"
              onChange={e => setF({...f, userQ: e.target.value, user_id: ''})}
              onFocus={() => setF(p => ({...p, _usOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _usOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users.filter(u => u.name.toLowerCase().includes(f.userQ.toLowerCase())).slice(0,10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({...f, user_id: String(u.id), userQ: u.name, _usOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{u.name}</button>
                ))}
              </div>
            )}
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
              <h3 className="text-lg font-bold">Buyurtma · {detail.number}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-4 gap-3 text-sm">
                {[["Ta'minotchi",detail.supplier_name],["Ombor",detail.warehouse_name],["Holat",<Badge meta={poMeta} val={detail.status}/>],["Sana",fmtDay(detail.created_at)]].map(([k,v])=>(
                  <div key={k} className="bg-slate-50 rounded-xl p-3"><div className="text-xs text-slate-500 mb-1">{k}</div><div className="font-semibold">{v}</div></div>
                ))}
              </div>
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">Mahsulot</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Buyurtma</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Qabul</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Narx</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Jami</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.items?.map(item => (
                    <tr key={item.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium">{item.product_name}</td>
                      <td className="px-4 py-3 text-center">{item.qty_ordered}</td>
                      <td className="px-4 py-3 text-center text-emerald-600 font-semibold">{item.qty_received}</td>
                      <td className="px-4 py-3 text-right">{fmt(item.unit_cost)}</td>
                      <td className="px-4 py-3 text-right font-semibold">{fmt(Number(item.qty_ordered)*Number(item.unit_cost))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t">
              <Btn v="ghost" onClick={() => setDetail(null)}>Yopish</Btn>
              {['draft','ordered','partial'].includes(detail.status) && (
                <Btn v="green" onClick={() => { setRec(detail); setDetail(null); }}>Qabul qilish</Btn>
              )}
            </div>
          </div>
        </div>
      )}

      {recModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold mb-4">Qabul qilish · {recModal.number}</h3>
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden mb-4">
              {recModal.items?.filter(i => Number(i.qty_ordered)>Number(i.qty_received)).map(item => (
                <div key={item.id} className="flex justify-between px-4 py-3">
                  <span className="font-medium text-sm">{item.product_name}</span>
                  <span className="text-indigo-600 font-semibold">+{Number(item.qty_ordered)-Number(item.qty_received)}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-3">
              <Btn v="ghost" onClick={() => setRec(null)} className="flex-1">Bekor</Btn>
              <Btn v="green" onClick={receivePo} disabled={recSaving} className="flex-1">{recSaving?'...':'Tasdiqlash'}</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   QAYTARISHLAR — split panel create view
══════════════════════════════════════════════════════════ */
function QaytarishCreateView({ products, type, onBack }) {
  const isCustomer = type === 'customer';
  const [items, setItems]   = useState([]);
  const [note, setNote]     = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState('');
  const [msg, setMsg]       = useState('');

  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('1');

  const addItem = () => {
    if (!sel || !qty) return;
    setItems(prev => {
      const ex = prev.find(i => i.product_id === sel.id);
      if (ex) return prev.map(i => i.product_id===sel.id ? {...i, qty: Number(i.qty)+Number(qty)} : i);
      return [...prev, { product_id:sel.id, product_name:sel.name, unit:sel.unit||'dona', qty:Number(qty), current:Number(sel.stock_quantity||0) }];
    });
    setSel(null); setQty('1');
  };

  const save = async () => {
    if (!items.length) { setErr("Mahsulot qo'shing"); return; }
    setSaving(true); setErr(''); setMsg('');
    try {
      if (isCustomer) {
        await api.post('/inventory/receive', {
          items: items.map(i => ({ product_id:i.product_id, quantity:i.qty, reason:`Mijozdan qaytarish${note?': '+note:''}` })),
        });
      } else {
        for (const item of items) {
          await api.post('/inventory/adjust', {
            product_id: item.product_id,
            new_quantity: Math.max(0, item.current - item.qty),
            reason: `Ta'minotchiga qaytarish${note ? ': '+note : ''}`,
          });
        }
      }
      setMsg(`${items.length} ta mahsulot qaytarildi`);
      setItems([]); setNote('');
    } catch (e) { setErr(e.response?.data?.detail||'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <CreateHeader title={isCustomer ? 'Mijozdan qaytarish' : "Ta'minotchiga qaytarish"} onBack={onBack} />
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-slate-100 bg-white shadow-sm shrink-0">
        <input placeholder={isCustomer ? "Mijoz ismi (ixtiyoriy)" : "Izoh (ixtiyoriy)"} value={note} onChange={e => setNote(e.target.value)} className={`${ic} w-72`} />
        <span className="text-xs text-slate-400 font-medium ml-auto">{new Date().toLocaleString('uz-UZ')}</span>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="w-80 border-r border-slate-100 p-5 flex flex-col gap-4 overflow-y-auto shrink-0 bg-white shadow-sm">
          <Lbl t="Mahsulot qidirish">
            <ProdSearch products={products} onSelect={p => { setSel(p); setQty('1'); }} />
          </Lbl>
          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {sel.name.slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm">{sel.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">Joriy qoldiq: <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit||'dona'}</div>
                </div>
              </div>
              <Lbl t="Qaytarish miqdori">
                <div className="flex gap-2 items-center">
                  <input type="number" min="0.001" step="any" value={qty} onChange={e => setQty(e.target.value)} className={`flex-1 ${ic} text-center font-bold`} />
                  <span className="text-sm text-slate-500 font-medium shrink-0">{sel.unit||'dona'}</span>
                </div>
              </Lbl>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-8">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              <p className="text-sm text-center">Mahsulot qidiring va tanlang</p>
            </div>
          )}
          <button onClick={addItem} disabled={!sel||!qty}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-indigo-200 active:scale-95">
            <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Ro'yxatga qo'shish
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {items.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
              <p>Mahsulot qo'shing</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">№</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Nomi</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Soni</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">O'lchov</th>
                  {!isCustomer && <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Joriy qoldiq</th>}
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((it, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-400 text-xs">{i+1}</td>
                    <td className="px-4 py-3 font-medium">{it.product_name}</td>
                    <td className="px-4 py-3 text-center">{it.qty}</td>
                    <td className="px-4 py-3 text-center text-slate-500 text-xs">{it.unit}</td>
                    {!isCustomer && <td className="px-4 py-3 text-center text-slate-500">{fmt(it.current)}</td>}
                    <td className="pr-3">
                      <button onClick={() => setItems(p=>p.filter((_,idx)=>idx!==i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white shrink-0">
        <div>
          {msg && <span className="text-emerald-600 text-sm">{msg}</span>}
          {err && <span className="text-red-500 text-sm">{err}</span>}
        </div>
        <div className="flex gap-3">
          <Btn v="ghost" onClick={onBack}>Bekor qilish</Btn>
          <Btn onClick={save} disabled={saving}>{saving?'...':'Saqlash'}</Btn>
        </div>
      </div>
    </div>
  );
}

function QaytarishlarTab({ products }) {
  const [mode, setMode] = useState('list');
  const [sub, setSub]   = useState('customer');

  if (mode === 'create') return (
    <QaytarishCreateView products={products} type={sub} onBack={() => setMode('list')} />
  );

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 bg-slate-100 p-1 rounded-xl">
            {[['customer','Mijozdan qaytarish'],['supplier',"Ta'minotchiga qaytarish"]].map(([v,l]) => (
              <button key={v} onClick={() => setSub(v)}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${sub===v?'bg-white shadow text-indigo-700':'text-slate-500 hover:text-slate-700'}`}>{l}</button>
            ))}
          </div>
          <div className="ml-auto">
            <Btn onClick={() => setMode('create')}>
              <svg className="w-4 h-4 inline mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              Yangi qaytaruv
            </Btn>
          </div>
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-16 text-center">
        <svg className="w-12 h-12 mx-auto mb-3 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
        </svg>
        <p className="text-slate-400 text-sm">Qaytarish tarixini ko'rish uchun yuqoridagi tugmani bosing</p>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   TRANSFERLAR
══════════════════════════════════════════════════════════ */
function TransferCreateView({ products: propProducts, warehouses, onBack, onSaved }) {
  const [localProducts, setLocalProducts] = useState(propProducts || []);
  const [step, setStep]     = useState(1);

  const [form, setForm]     = useState({ from_warehouse_id: '', to_warehouse_id: '', note: '' });
  const [items, setItems]   = useState([]);
  const [sel, setSel]       = useState(null);
  const [qty, setQty]       = useState('1');
  const qtyRef              = useRef(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState('');

  // Fetch products directly when entering step 2 (don't rely on possibly-empty prop)
  useEffect(() => {
    if (step === 2 && localProducts.length === 0) {
      api.get('/products/', { params: { limit: 200 } })
        .then(r => {
          const data = r.data;
          setLocalProducts(Array.isArray(data) ? data : (data.items || []));
        })
        .catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const products = localProducts; // alias for all JSX below

  const fromWh = warehouses.find(w => String(w.id) === String(form.from_warehouse_id));
  const toWh   = warehouses.find(w => String(w.id) === String(form.to_warehouse_id));



  const addItem = () => {
    if (!sel || !qty) return;
    setItems(prev => {
      const ex = prev.find(i => i.product_id === sel.id);
      if (ex) return prev.map(i => i.product_id === sel.id ? { ...i, quantity: Number(i.quantity) + Number(qty) } : i);
      return [...prev, { product_id: sel.id, product_name: sel.name, unit: sel.unit || 'dona', quantity: Number(qty), stock: Number(sel.stock_quantity || 0) }];
    });
    setSel(null); setQty('1');
  };

  const save = async () => {
    setSaving(true); setErr('');
    try {
      await api.post('/transfers', {
        from_warehouse_id: Number(form.from_warehouse_id),
        to_warehouse_id:   Number(form.to_warehouse_id),
        note: form.note || null,
        items: items.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
      });
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  /* ── Step indicator ── */
  const STEPS = ['Omborlar', 'Mahsulotlar', 'Tasdiqlash'];

  return (
    <div className="fixed inset-0 z-40 bg-slate-100 flex flex-col">

      {/* ── Header ── */}
      <div className="flex items-center gap-4 px-6 py-3.5 bg-white border-b border-slate-100 shadow-sm shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7"/></svg>
          Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0"/>
        <h2 className="text-base font-bold text-slate-800">Yangi Transfer</h2>

        {/* Step indicator */}
        <div className="flex items-center gap-0 ml-6">
          {STEPS.map((label, idx) => {
            const n = idx + 1;
            const done    = step > n;
            const active  = step === n;
            return (
              <div key={n} className="flex items-center">
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
                  active  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' :
                  done    ? 'bg-emerald-100 text-emerald-700' :
                            'bg-slate-100 text-slate-400'
                }`}>
                  {done
                    ? <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>
                    : <span>{n}</span>
                  }
                  <span className="hidden sm:inline">{label}</span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div className={`w-8 h-0.5 mx-1 ${done ? 'bg-emerald-400' : 'bg-slate-200'}`}/>
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
              <div className="w-14 h-14 bg-indigo-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
                <svg className="w-7 h-7 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/>
                </svg>
              </div>
              <h3 className="text-xl font-bold text-slate-800">Omborlarni tanlang</h3>
              <p className="text-sm text-slate-500 mt-1">Mahsulot <strong>qayerdan</strong> va <strong>qayerga</strong> ko'chiriladi?</p>
            </div>

            <div className="flex items-center gap-4">
              {/* FROM */}
              <div className="flex-1">
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Manba ombor (Kimdan)</label>
                <div className="space-y-2">
                  {warehouses.map(w => (
                    <button key={w.id} onClick={() => setForm(f => ({ ...f, from_warehouse_id: String(w.id) }))}
                      disabled={String(form.to_warehouse_id) === String(w.id)}
                      className={`w-full text-left px-4 py-3.5 rounded-2xl border-2 transition-all flex items-center gap-3 ${
                        String(form.from_warehouse_id) === String(w.id)
                          ? 'border-indigo-500 bg-indigo-50 shadow-md shadow-indigo-100'
                          : 'border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/30 disabled:opacity-30 disabled:cursor-not-allowed'
                      }`}>
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 font-bold text-sm ${
                        String(form.from_warehouse_id) === String(w.id) ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {w.name.slice(0,2).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">{w.name}</div>
                        {w.location && <div className="text-xs text-slate-400 truncate">{w.location}</div>}
                      </div>
                      {String(form.from_warehouse_id) === String(w.id) && (
                        <svg className="w-5 h-5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Arrow */}
              <div className="flex flex-col items-center gap-2 shrink-0">
                <div className="w-12 h-12 bg-white border-2 border-slate-200 rounded-full flex items-center justify-center shadow-sm">
                  <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3"/>
                  </svg>
                </div>
                {fromWh && toWh && (
                  <div className="text-[10px] text-emerald-600 font-bold text-center bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">OK</div>
                )}
              </div>

              {/* TO */}
              <div className="flex-1">
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Maqsad ombor (Kimga)</label>
                <div className="space-y-2">
                  {warehouses.map(w => (
                    <button key={w.id} onClick={() => setForm(f => ({ ...f, to_warehouse_id: String(w.id) }))}
                      disabled={String(form.from_warehouse_id) === String(w.id)}
                      className={`w-full text-left px-4 py-3.5 rounded-2xl border-2 transition-all flex items-center gap-3 ${
                        String(form.to_warehouse_id) === String(w.id)
                          ? 'border-emerald-500 bg-emerald-50 shadow-md shadow-emerald-100'
                          : 'border-slate-200 bg-white hover:border-emerald-300 hover:bg-emerald-50/30 disabled:opacity-30 disabled:cursor-not-allowed'
                      }`}>
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 font-bold text-sm ${
                        String(form.to_warehouse_id) === String(w.id) ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {w.name.slice(0,2).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">{w.name}</div>
                        {w.location && <div className="text-xs text-slate-400 truncate">{w.location}</div>}
                      </div>
                      {String(form.to_warehouse_id) === String(w.id) && (
                        <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Note */}
            <div className="mt-6">
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Izoh (ixtiyoriy)</label>
              <input placeholder="Transfer sababi yoki qo'shimcha ma'lumot..." value={form.note}
                onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>

            {/* Next btn */}
            <div className="mt-6 flex justify-end">
              <button
                disabled={!form.from_warehouse_id || !form.to_warehouse_id || form.from_warehouse_id === form.to_warehouse_id}
                onClick={() => setStep(2)}
                className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200">
                Davom etish
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/></svg>
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
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-4 py-3 flex items-center gap-2.5">
              <div className="text-xs font-bold text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded-lg truncate max-w-[90px]">{fromWh?.name}</div>
              <svg className="w-4 h-4 text-indigo-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
              <div className="text-xs font-bold text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-lg truncate max-w-[90px]">{toWh?.name}</div>
            </div>

            <Lbl t="Mahsulot qidirish">
              <ProdSearch products={products} onSelect={p => { setSel(p); setQty('1'); setTimeout(() => qtyRef.current?.focus(), 50); }} />
            </Lbl>

            {sel ? (
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                    {sel.name.slice(0,2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-800 text-sm truncate">{sel.name}</div>
                    <div className="text-xs mt-0.5">
                      <span className="text-slate-500">Mavjud:</span>
                      <span className={`font-bold ml-1 ${Number(sel.stock_quantity) < 5 ? 'text-red-500' : 'text-emerald-600'}`}>
                        {fmt(sel.stock_quantity)} {sel.unit||'dona'}
                      </span>
                    </div>
                  </div>
                </div>

                {Number(sel.stock_quantity) <= 0 && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2 flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                    Stokda mahsulot yo'q
                  </div>
                )}

                <Lbl t="Ko'chirish miqdori">
                  <div className="flex gap-2 items-center">
                    <button onClick={() => setQty(q => String(Math.max(1, Number(q)-1)))}
                      className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">−</button>
                    <input ref={qtyRef} type="number" min="0.001" step="any" value={qty}
                      onChange={e => setQty(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && addItem()}
                      className={`flex-1 ${ic} text-center font-bold`} />
                    <button onClick={() => setQty(q => String(Number(q)+1))}
                      className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">+</button>
                    <span className="text-sm text-slate-500 shrink-0">{sel.unit||'dona'}</span>
                  </div>
                </Lbl>

                {Number(qty) > Number(sel.stock_quantity) && Number(sel.stock_quantity) > 0 && (
                  <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                    ⚠️ Miqdor mavjud stokdan ({fmt(sel.stock_quantity)}) ko'p
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-10">
                <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/>
                </svg>
                <p className="text-sm text-center">Mahsulot qidiring va tanlang</p>
              </div>
            )}

            <button onClick={addItem} disabled={!sel || !qty || Number(sel?.stock_quantity) <= 0}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-indigo-200 active:scale-95">
              <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
              Ro'yxatga qo'shish
            </button>

            {items.length > 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-center">
                <div className="text-xs text-slate-400 font-medium">{items.length} xil mahsulot</div>
                <div className="text-lg font-bold text-indigo-600 mt-1">{items.reduce((s,i) => s+Number(i.quantity),0)} dona</div>
              </div>
            )}
          </div>

          {/* RIGHT — Items list */}
          <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
            <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-100 shrink-0">
              <span className="text-sm font-bold text-slate-700">Ko'chirish ro'yxati</span>
              {items.length > 0 && (
                <button onClick={() => setItems([])} className="text-xs text-red-400 hover:text-red-600 flex items-center gap-1 px-2 py-1 hover:bg-red-50 rounded-lg transition-colors">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                  Tozalash
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3">
                  <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>
                  <p className="text-sm">Chap paneldan mahsulot qo'shing</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white border-b border-slate-200 z-10">
                    <tr>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase">Mahsulot</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Joriy qoldiq</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Ko'chirish miqdori</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">O'lchov</th>
                      <th className="w-10"/>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {items.map((it, i) => (
                      <tr key={i} className="hover:bg-white/80 transition-colors">
                        <td className="px-5 py-3.5 text-slate-400 text-xs">{i+1}</td>
                        <td className="px-5 py-3.5">
                          <div className="font-semibold text-slate-800">{it.product_name}</div>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <span className={`text-sm font-semibold ${it.quantity > it.stock ? 'text-amber-600' : 'text-slate-600'}`}>{fmt(it.stock)}</span>
                        </td>
                        <td className="px-4 py-3.5 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <button onClick={() => setItems(p => p.map((x,idx) => idx===i ? {...x, quantity: Math.max(0.001, x.quantity-1)} : x))}
                              className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center leading-none">−</button>
                            <input type="number" min="0.001" step="any" value={it.quantity}
                              onChange={e => setItems(p => p.map((x,idx) => idx===i ? {...x, quantity: Number(e.target.value)||1} : x))}
                              className="w-16 text-center border border-slate-200 rounded px-1 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400 font-bold"/>
                            <button onClick={() => setItems(p => p.map((x,idx) => idx===i ? {...x, quantity: x.quantity+1} : x))}
                              className="w-6 h-6 rounded border border-slate-200 text-slate-500 hover:bg-slate-100 flex items-center justify-center leading-none">+</button>
                          </div>
                          {it.quantity > it.stock && (
                            <div className="text-[10px] text-amber-500 mt-1">⚠️ Stokdan ko'p</div>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-center text-xs text-slate-400">{it.unit}</td>
                        <td className="pr-4">
                          <button onClick={() => setItems(p => p.filter((_,idx) => idx!==i))}
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
              <button onClick={() => setStep(1)} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-4 py-2 rounded-xl hover:bg-indigo-50 text-sm font-semibold transition-all">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/></svg>
                Orqaga
              </button>
              <button disabled={items.length === 0} onClick={() => setStep(3)}
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-indigo-200">
                Tasdiqlashga o'tish
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/></svg>
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
                <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>
                <span className="text-sm font-bold text-slate-700">Ko'chirish marshuruti</span>
              </div>
              <div className="p-5 flex items-center gap-4">
                <div className="flex-1 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 text-center">
                  <div className="text-xs text-indigo-500 font-bold uppercase tracking-wide mb-1">Kimdan</div>
                  <div className="font-bold text-indigo-800 text-base">{fromWh?.name}</div>
                </div>
                <div className="flex flex-col items-center gap-1 shrink-0">
                  <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
                  <span className="text-[10px] text-slate-400 font-bold">TRANZIT</span>
                </div>
                <div className="flex-1 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-center">
                  <div className="text-xs text-emerald-600 font-bold uppercase tracking-wide mb-1">Kimga</div>
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
                <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </div>
              <div>
                <div className="text-sm font-bold text-amber-800 mb-0.5">Tranzit holati haqida</div>
                <p className="text-xs text-amber-700 leading-relaxed">
                  Transfer yaratilgandan so'ng <strong>«Kutilmoqda»</strong> holatida bo'ladi. Maqsad ombor xodimi <strong>«Tasdiqlash»</strong> tugmasini bosganda mahsulot qoldiqlar yangilanadi va transfer <strong>«Tasdiqlandi»</strong> holatiga o'tadi.
                </p>
              </div>
            </div>

            {/* Items summary */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                <span className="text-sm font-bold text-slate-700">Ko'chiriladigan mahsulotlar</span>
                <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full">{items.length} xil · {items.reduce((s,i)=>s+i.quantity,0)} dona</span>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-100">
                  <tr>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase">Mahsulot</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">Miqdor</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase">O'lchov</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {items.map((it, i) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-5 py-3 text-slate-400 text-xs">{i+1}</td>
                      <td className="px-5 py-3 font-medium text-slate-800">{it.product_name}</td>
                      <td className="px-4 py-3 text-center font-bold text-indigo-600">{it.quantity}</td>
                      <td className="px-4 py-3 text-center text-slate-400 text-xs">{it.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Error */}
            {err && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                {err}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between">
              <button onClick={() => setStep(2)} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-4 py-2.5 rounded-xl hover:bg-indigo-50 text-sm font-semibold transition-all">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/></svg>
                Orqaga
              </button>
              <button onClick={save} disabled={saving}
                className="inline-flex items-center gap-2.5 px-8 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl font-bold text-sm transition-all shadow-md shadow-emerald-200 active:scale-95">
                {saving ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Saqlanmoqda...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    Transferni yaratish
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





function TransferlarTab({ products, warehouses, users = [] }) {
  const [mode, setMode]       = useState('list');
  const [transfers, setTr]    = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip]       = useState(0);
  const [f, setF]             = useState({ dateFrom: today(), dateTo: today(), status: '', fromWh_id: '', toWh_id: '', user_id: '', statusQ: '', fromWhQ: '', toWhQ: '', userQ: '' });
  const [detail, setDetail]   = useState(null);
  const LIMIT = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (f.status) params.status = f.status;
      if (f.dateFrom) params.date_from = f.dateFrom;
      if (f.dateTo) params.date_to = f.dateTo;
      if (f.fromWh_id) params.from_warehouse_id = f.fromWh_id;
      if (f.toWh_id) params.to_warehouse_id = f.toWh_id;
      if (f.user_id) params.user_id = f.user_id;
      const r = await api.get('/transfers', { params });
      setTr(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, f]);

  useEffect(() => { if (mode==='list') load(); }, [load, mode]);

  const openDetail = async (row) => {
    const r = await api.get(`/transfers/${row.id}`);
    setDetail(r.data);
  };
  const confirm = async (id) => { try { await api.post(`/transfers/${id}/confirm`); load(); } catch { /* ignore */ } };
  const cancel  = async (id) => { try { await api.post(`/transfers/${id}/cancel`);  load(); } catch { /* ignore */ } };

  if (mode === 'create') return <TransferCreateView products={products} warehouses={warehouses} onBack={() => setMode('list')} onSaved={load} />;

  const cols = [
    { k:'number',              l:'Raqam' },
    { k:'from_warehouse_name', l:'Kimdan' },
    { k:'to_warehouse_name',   l:'Kimga' },
    { k:'status',              l:'Holat', r: v => <Badge meta={trMeta} val={v} /> },
    { k:'created_at',          l:'Sana',  r: v => fmtDay(v) },
    { k:'id', l:'', r: (v,row) => row.status==='pending' ? (
      <div className="flex gap-1.5" onClick={e=>e.stopPropagation()}>
        <Btn v="green" sm onClick={() => confirm(v)}>Tasdiqlash</Btn>
        <Btn v="red"   sm onClick={() => cancel(v)}>Bekor</Btn>
      </div>
    ) : null },
  ];

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          <Btn onClick={() => setMode('create')} sm>
            <svg className="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            Yangi transfer
          </Btn>
        </div>
      </div>

      {/* Filters — Custom 2-row grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3">
          <input type="text" placeholder="Status" value={f.statusQ||''} onChange={e => {
            const q = e.target.value;
            const match = Object.entries(trMeta).find(([,m]) => m.l.toLowerCase().startsWith(q.toLowerCase()));
            setF({...f, statusQ: q, status: match ? match[0] : ''});
          }} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateFrom} onChange={e => setF({...f, dateFrom:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateTo} onChange={e => setF({...f, dateTo:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          {/* Kimdan (From warehouse) */}
          <div className="relative">
            <input type="text" value={f.fromWhQ||''} placeholder="Kimdan (Ombor)"
              onChange={e => setF({...f, fromWhQ: e.target.value, fromWh_id: ''})}
              onFocus={() => setF(p => ({...p, _fromOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _fromOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._fromOpen && f.fromWhQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {warehouses.filter(w => w.name.toLowerCase().includes(f.fromWhQ.toLowerCase())).slice(0,10).map(w => (
                  <button key={w.id} onMouseDown={() => setF({...f, fromWh_id: String(w.id), fromWhQ: w.name, _fromOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{w.name}</button>
                ))}
              </div>
            )}
          </div>
          <span className="text-slate-300 text-lg">→</span>
          {/* Kimga (To warehouse) */}
          <div className="relative">
            <input type="text" value={f.toWhQ||''} placeholder="Kimga (Ombor)"
              onChange={e => setF({...f, toWhQ: e.target.value, toWh_id: ''})}
              onFocus={() => setF(p => ({...p, _toOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _toOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._toOpen && f.toWhQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {warehouses.filter(w => w.name.toLowerCase().includes(f.toWhQ.toLowerCase())).slice(0,10).map(w => (
                  <button key={w.id} onMouseDown={() => setF({...f, toWh_id: String(w.id), toWhQ: w.name, _toOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{w.name}</button>
                ))}
              </div>
            )}
          </div>
          {/* Foydalanuvchi */}
          <div className="relative">
            <input type="text" value={f.userQ||''} placeholder="Foydalanuvchi"
              onChange={e => setF({...f, userQ: e.target.value, user_id: ''})}
              onFocus={() => setF(p => ({...p, _usOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _usOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users?.filter(u => u.name.toLowerCase().includes(f.userQ.toLowerCase())).slice(0,10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({...f, user_id: String(u.id), userQ: u.name, _usOpen: false})}
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
              <h3 className="text-lg font-bold">Transfer · {detail.number}</h3>
              <button onClick={()=>setDetail(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[["Kimdan",detail.from_warehouse_name],["Kimga",detail.to_warehouse_name],["Holat",<Badge meta={trMeta} val={detail.status}/>],["Sana",fmtDt(detail.created_at)]].map(([k,v])=>(
                  <div key={k} className="bg-slate-50 rounded-xl p-3 text-sm"><div className="text-xs text-slate-500 mb-1">{k}</div><div className="font-semibold">{v}</div></div>
                ))}
              </div>
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">Mahsulot</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Miqdor</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.items?.map(item => (
                    <tr key={item.id}><td className="px-4 py-3 font-medium">{item.product_name}</td><td className="px-4 py-3 text-center font-semibold">{item.quantity}</td></tr>
                  ))}
                </tbody>
              </table>
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
  return <InventoryCountsPage />;
}

/* ══════════════════════════════════════════════════════════
   CHIQIMLAR
══════════════════════════════════════════════════════════ */
const CHIQIM_TYPES = [
  { v: 'brak',      l: 'Brak — Nuqsonli mahsulot' },
  { v: 'yoqotish',  l: "Yo'qotish / Kamomad" },
  { v: 'namunaviy', l: "Namuna / Ko'rsatish" },
  { v: 'qaytarma',  l: 'Ichki qaytarma' },
  { v: 'boshqa',    l: 'Boshqa sabab' },
];


function ChiqimCreateView({ products, onBack, onSaved, editItems = [], editId = null }) {
  const [items, setItems]   = useState(() => {
    return editItems.map(i => ({
      product: { id: i.product_id, name: i.product_name, stock_quantity: 0, unit: i.product_unit },
      qty: i.quantity,
      type: CHIQIM_TYPES.find(t => t.l === i.type || t.v === i.type)?.v || CHIQIM_TYPES[0].v,
      doc_num: i.doc_num || '',
      reason: i.reason || ''
    }));
  });
  const [sel, setSel]       = useState(null);
  const [qty, setQty]       = useState('1');
  const qtyRef              = useRef(null);
  const [form, setForm]     = useState({ type: 'brak', doc_num: '', reason: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState('');

  const addItem = () => {
    if (!sel || !qty || Number(qty)<=0) return;
    setItems(p => [...p, { product: sel, qty: Number(qty), type: form.type, doc_num: form.doc_num, reason: form.reason }]);
    setSel(null); setQty('1'); setForm({ type: 'brak', doc_num: '', reason: '' });
  };

  const save = async () => {
    if (!items.length) return;
    setSaving(true); setErr('');
    try {
      const payload = items.map(item => ({
        product_id: Number(item.product.id),
        quantity: Number(item.qty),
        type: item.type,
        doc_num: item.doc_num || undefined,
        reason: item.reason || undefined,
      }));
      if (editId) {
        await api.delete(`/inventory/chiqims/${editId}`);
      }
      await api.post('/inventory/chiqims', { items: payload });
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-100 flex flex-col">
      <div className="flex items-center gap-4 px-6 py-3.5 bg-white border-b border-slate-100 shadow-sm shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7"/></svg>
          Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0"/>
        <h2 className="text-base font-bold text-slate-800">{editId ? `Chiqimni tahrirlash (#${editId})` : 'Yangi chiqim'}</h2>
        <div className="ml-auto text-xs text-slate-400 font-medium">{new Date().toLocaleString('uz-UZ')}</div>
      </div>
      
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT */}
        <div className="w-[500px] border-r border-slate-200 bg-white flex flex-col gap-4 p-5 overflow-y-auto shrink-0 shadow-sm">
          <Lbl t="Mahsulot qidirish">
            <ProdSearch products={products} onSelect={p => { setSel(p); setQty('1'); setTimeout(() => qtyRef.current?.focus(), 50); }} />
          </Lbl>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 space-y-4">
              <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                    {sel.name.slice(0,2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-slate-800 text-sm truncate">{sel.name}</div>
                    <div className="text-xs mt-0.5">
                      <span className="text-slate-500">Ombordagi qoldiq:</span>
                      <span className="font-bold ml-1 text-emerald-600">{fmt(sel.stock_quantity)} {sel.unit||'dona'}</span>
                    </div>
                  </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Lbl t="Chiqim turi *">
                  <select value={form.type} onChange={e => setForm(f=>({...f, type: e.target.value}))} className={ic}>
                    {CHIQIM_TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
                  </select>
                </Lbl>
                <Lbl t="Miqdor *">
                  <div className="flex gap-2 items-center">
                    <button onClick={() => setQty(q => String(Math.max(1, Number(q)-1)))} className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">−</button>
                    <input ref={qtyRef} type="number" min="0.001" step="any" value={qty} onChange={e => setQty(e.target.value)} onKeyDown={e => e.key === 'Enter' && addItem()} className={`flex-1 ${ic} text-center font-bold`} />
                    <button onClick={() => setQty(q => String(Number(q)+1))} className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:bg-slate-100 font-bold shrink-0">+</button>
                  </div>
                </Lbl>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Lbl t="Hujjat raqami">
                  <input value={form.doc_num} onChange={e => setForm(f=>({...f, doc_num: e.target.value}))} onKeyDown={e => e.key === 'Enter' && addItem()} className={ic} placeholder="ACT-001" />
                </Lbl>
                <Lbl t="Izoh">
                  <input value={form.reason} onChange={e => setForm(f=>({...f, reason: e.target.value}))} onKeyDown={e => e.key === 'Enter' && addItem()} className={ic} placeholder="Sabab..." />
                </Lbl>
              </div>

              {form.type === 'brak' && (
                <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-700">
                  ⚠️ Brak mahsulotlar qaytarib bo'lmaydi.
                </div>
              )}

              <button onClick={addItem} disabled={!qty || Number(qty)<=0} className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white rounded-2xl font-bold text-sm transition-all shadow-sm active:scale-95">
                Ro'yxatga qo'shish
              </button>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2 py-10">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>
              <p className="text-sm text-center">Mahsulot qidiring va tanlang</p>
            </div>
          )}
        </div>

        {/* RIGHT */}
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
          <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-100 shrink-0">
            <span className="text-sm font-bold text-slate-700">Chiqim qilinadigan mahsulotlar</span>
            {items.length > 0 && <button onClick={() => setItems([])} className="text-xs text-red-500 font-semibold hover:underline">Tozalash</button>}
          </div>
          <div className="flex-1 overflow-y-auto">
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3">
                  <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>
                  <p className="text-sm">Chap paneldan mahsulot qo'shing</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white border-b border-slate-200 z-10">
                  <tr>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">№</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">Mahsulot</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">Turi / Sabab</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500">Miqdor</th>
                    <th className="w-10"/>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((it, i) => (
                    <tr key={i} className="hover:bg-white transition-colors">
                      <td className="px-5 py-3.5 text-slate-400 text-xs">{i+1}</td>
                      <td className="px-5 py-3.5 font-semibold text-slate-800">{it.product.name}</td>
                      <td className="px-5 py-3.5">
                        <div className="text-xs font-semibold text-indigo-600">{CHIQIM_TYPES.find(t=>t.v===it.type)?.l?.split('—')[0]?.trim() || it.type}</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">{[it.doc_num, it.reason].filter(Boolean).join(' | ')}</div>
                      </td>
                      <td className="px-4 py-3.5 text-center font-bold text-red-500">−{it.qty} {it.product.unit}</td>
                      <td className="pr-4">
                        <button onClick={() => setItems(p=>p.filter((_,idx)=>idx!==i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded">✕</button>
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
              <button onClick={onBack} className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-semibold hover:bg-slate-50">Bekor qilish</button>
              <button onClick={save} disabled={saving || !items.length} className="px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition-all disabled:opacity-50 shadow-sm flex items-center gap-2">
                {saving ? 'Tasdiqlanmoqda...' : 'Tasdiqlash'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChiqimlarTab({ products, users = [] }) {
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
      .catch(() => {})
      .finally(() => setML(false));
  }, [f]);
  useEffect(() => { if (mode==='list') loadMov(); }, [mode, loadMov]);

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
    if (!window.confirm("Chiqimni bekor qilishga ishonchingiz komilmi? (Mahsulotlar omborga qaytadi)")) return;
    try {
      await api.delete(`/inventory/chiqims/${id}`);
      loadMov();
      if (detailId === id) setDetailId(null);
    } catch (e) {
      alert("Xatolik: " + (e.response?.data?.detail || e.message));
    }
  };

  const [editingData, setEditingData] = useState(null);

  if (mode === 'create') return <ChiqimCreateView products={products} onBack={() => { setMode('list'); setEditingData(null); }} onSaved={loadMov} editId={editingData?.id} editItems={editingData?.items} />;

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
            Yangi chiqim
          </Btn>
        </div>
      </div>

      {/* Filters — Custom 2-row grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3">
          <input type="text" placeholder="Status" disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 focus:outline-none bg-slate-50 cursor-not-allowed"/>
          <input type="date" value={f.dateFrom} onChange={e => setF({...f, dateFrom:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateTo} onChange={e => setF({...f, dateTo:e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          <input type="text" placeholder="Contragent" disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 bg-slate-50 cursor-not-allowed" />
          <span className="text-slate-300 text-lg">+</span>
          <input type="text" placeholder="Xodim" disabled className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-400 bg-slate-50 cursor-not-allowed" />
          <div className="relative">
            <input type="text" value={f.userQ||''} placeholder="Foydalanuvchi"
              onChange={e => setF({...f, userQ: e.target.value, user_id: ''})}
              onFocus={() => setF(p => ({...p, _usOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _usOpen: false})), 200)}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white" />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users?.filter(u => u.name.toLowerCase().includes(f.userQ.toLowerCase())).slice(0,10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({...f, user_id: String(u.id), userQ: u.name, _usOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{u.name}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {movLoad ? (
          <div className="py-16 text-center"><div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin mx-auto" /></div>
        ) : movements.length === 0 ? (
          <div className="text-center py-20 text-slate-400 text-sm">Chiqimlar yo'q</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-100">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">Hujjat raqami</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">Sana</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase">Sabab</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-slate-500 uppercase">Tarkibi</th>
                <th className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {movements.map(m => {
                const types = m.type_hints.filter(Boolean);
                const firstType = CHIQIM_TYPES.find(t => types.includes(t.v) || types.includes(t.l)) || {l: types[0] || 'Aralash'};
                
                return (
                  <tr key={m.reference_id} className="hover:bg-slate-50 relative group">
                    <td className="px-6 py-4 font-semibold text-slate-800">CHIQIM #{m.reference_id}</td>
                    <td className="px-6 py-4 text-slate-500">{fmtDt(m.created_at)}</td>
                    <td className="px-6 py-4">
                      {firstType && <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 mb-1">{firstType.l.split('—')[0].trim()}</span>}
                      {m.doc_nums.length > 0 && <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-600 mb-1 ml-1">Hujjat: {m.doc_nums[0]}</span>}
                      <div className="text-xs text-slate-500 line-clamp-1">{m.reasons.join(', ') || '—'}</div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <div className="font-bold text-slate-700">{m.item_count} xil</div>
                      <div className="text-[11px] text-slate-400">Jami: {fmt(m.total_qty)} ta</div>
                    </td>
                    <td className="px-6 py-4 text-right">
                       <button onClick={() => openDetail(m.reference_id)} className="text-indigo-600 font-semibold hover:underline text-xs mr-3">Ko'rish / Tahrirlash</button>
                       <button onClick={() => deleteChiqim(m.reference_id)} className="text-red-500 font-semibold hover:underline text-xs">O'chirish</button>
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
              <h3 className="font-bold text-lg text-slate-800">Chiqim #{detailId} tasfoti</h3>
              <button onClick={() => setDetailId(null)} className="text-slate-400 hover:text-slate-600"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg></button>
            </div>
            <div className="p-6 overflow-y-auto">
              {loadingDetail ? (
                <div className="py-10 text-center"><div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin mx-auto" /></div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">Mahsulot</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">Sabab</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500">Miqdor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {detailItems.map(item => {
                       const t = CHIQIM_TYPES.find(x => item.type===x.v || item.type===x.l) || {l: item.type};
                       return (
                        <tr key={item.id}>
                          <td className="px-4 py-3 font-semibold text-slate-800">{item.product_name}</td>
                          <td className="px-4 py-3 text-slate-500 text-xs">
                             <div className="font-medium text-slate-700">{t.l.split('—')[0]}</div>
                             {item.doc_num && <div>Hujjat: {item.doc_num}</div>}
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
              <button onClick={startEdit} className="px-4 py-2 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg">Tahrirlash</button>
              <button onClick={() => setDetailId(null)} className="px-4 py-2 text-sm font-bold text-white bg-slate-800 hover:bg-slate-700 rounded-lg">Yopish</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   QOLDIQ NAZORATI
══════════════════════════════════════════════════════════ */
function QoldiqTab() {
  const [subtab, setSubtab]   = useState('low');
  const [allStocks, setAll]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch]   = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/inventory/stock', { params: { limit: 500 } });
      setAll(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);

  const filtered = allStocks.filter(s => {
    const nameOk = !search ||
      (s.product_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (s.product_sku  || '').toLowerCase().includes(search.toLowerCase());
    if (!nameOk) return false;
    const qty = Number(s.quantity);
    const min = Number(s.min_stock ?? 0);
    if (subtab === 'low')  return qty > 0 && qty <= min;
    if (subtab === 'zero') return qty <= 0;
    if (subtab === 'dead') return qty > 0 && new Date(s.updated_at) < sixMonthsAgo;
    return true;
  });

  const lowCount  = allStocks.filter(s => Number(s.quantity) > 0 && Number(s.quantity) <= Number(s.min_stock ?? 0)).length;
  const zeroCount = allStocks.filter(s => Number(s.quantity) <= 0).length;
  const deadCount = allStocks.filter(s => Number(s.quantity) > 0 && new Date(s.updated_at) < sixMonthsAgo).length;

  const statCards = [
    { l: 'Jami mahsulot',       v: allStocks.length, cl: 'text-slate-700', bg: 'bg-slate-100',  ic: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
    { l: "Qoldiq yo'q",          v: zeroCount,        cl: 'text-red-600',   bg: 'bg-red-100',    ic: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
    { l: 'Kam qoldiq',           v: lowCount,         cl: 'text-amber-600', bg: 'bg-amber-100',  ic: 'M13 17h8m0 0V9m0 8l-8-8-4 4-6-6' },
    { l: "O'lik qoldiq (6 oy)", v: deadCount,        cl: 'text-slate-500', bg: 'bg-slate-200',  ic: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
  ];

  return (
    <div className="space-y-4">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map(s => (
          <div key={s.l} className="bg-white border border-slate-100 rounded-2xl shadow-sm p-5 flex items-center gap-4">
            <div className={`w-12 h-12 ${s.bg} rounded-xl flex items-center justify-center shrink-0`}>
              <svg className={`w-6 h-6 ${s.cl}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={s.ic} />
              </svg>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{s.l}</div>
              <div className={`text-2xl font-black mt-0.5 ${s.cl}`}>{s.v}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white border border-slate-100 rounded-2xl shadow-sm p-4">
        <div className="flex gap-3 items-center flex-wrap">
          <div className="flex bg-slate-100 rounded-xl p-1 gap-1">
            {[['low','Kam qoldiq'],['zero',"Qoldiq yo'q"],['dead',"O'lik qoldiq"],['all','Barchasi']].map(([v,l]) => (
              <button key={v} onClick={() => setSubtab(v)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${subtab===v?'bg-white shadow text-indigo-700':'text-slate-500 hover:text-slate-700'}`}>
                {l}
                {v==='low' && lowCount>0 && <span className="ml-1.5 bg-amber-500 text-white rounded-full text-[10px] px-1.5 py-0.5">{lowCount}</span>}
                {v==='zero' && zeroCount>0 && <span className="ml-1.5 bg-red-500 text-white rounded-full text-[10px] px-1.5 py-0.5">{zeroCount}</span>}
                {v==='dead' && deadCount>0 && <span className="ml-1.5 bg-slate-500 text-white rounded-full text-[10px] px-1.5 py-0.5">{deadCount}</span>}
              </button>
            ))}
          </div>
          <div className="relative flex-1 min-w-48">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
            </svg>
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Mahsulot nomi yoki SKU..." className={`${ic} w-full pl-9`} />
          </div>
          <Btn v="ghost" onClick={load}>
            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            Yangilash
          </Btn>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center"><div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" /></div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['#','Mahsulot','Joriy qoldiq','Min. qoldiq','O\'lchov','Ombor',"So'nggi yangilanish",'Holat'].map(h => (
                    <th key={h} className="text-left px-5 py-3.5 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.length === 0 ? (
                  <tr><td colSpan={8} className="py-16 text-center text-slate-400 text-sm">
                    {subtab==='low' ? "Kam qoldiqli mahsulotlar yo'q" :
                     subtab==='zero' ? "Qoldiqi yo'q mahsulotlar yo'q" :
                     subtab==='dead' ? "6 oydan ortiq harakatsiz mahsulotlar yo'q" : "Ma'lumot topilmadi"}
                  </td></tr>
                ) : filtered.map((s, i) => {
                  const qty = Number(s.quantity);
                  const min = Number(s.min_stock ?? 0);
                  const daysSince = Math.floor((Date.now() - new Date(s.updated_at)) / 86400000);
                  let statusEl;
                  if (qty <= 0)        statusEl = <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-600">Qoldiq yo'q</span>;
                  else if (qty <= min) statusEl = <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">Kam qoldiq ⚠</span>;
                  else if (daysSince > 180) statusEl = <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-200 text-slate-600">O'lik qoldiq</span>;
                  else statusEl = <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">Yaxshi</span>;
                  return (
                    <tr key={s.id || i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-3.5 text-slate-300 text-xs font-medium">{i+1}</td>
                      <td className="px-5 py-3.5">
                        <div className="font-semibold text-slate-800">{s.product_name}</div>
                        <div className="text-xs text-slate-400 mt-0.5 font-mono">{s.product_sku}</div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`font-bold text-lg ${qty<=0?'text-red-500':qty<=min?'text-amber-600':'text-slate-800'}`}>{fmt(qty)}</span>
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 font-medium">{fmt(min)}</td>
                      <td className="px-5 py-3.5 text-slate-400 text-xs">{s.product_unit || 'dona'}</td>
                      <td className="px-5 py-3.5 text-slate-600">{s.warehouse_name || '—'}</td>
                      <td className="px-5 py-3.5 text-slate-500">
                        {fmtDay(s.updated_at)}
                        {daysSince > 30 && <div className="text-xs text-slate-400">{daysSince} kun oldin</div>}
                      </td>
                      <td className="px-5 py-3.5">{statusEl}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 text-xs text-slate-400 flex justify-between">
              <span>Jami <strong className="text-slate-600">{filtered.length}</strong> ta mahsulot ko'rsatildi</span>
              {subtab==='dead' && <span className="text-slate-500">6 oydan ortiq hech qanday harakatsiz mahsulotlar</span>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MAIN
══════════════════════════════════════════════════════════ */
const TABS = [
  {
    id: 'qaytarishlar', label: 'Qaytarishlar',
    icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>,
  },
  {
    id: 'transferlar', label: 'Transferlar',
    icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>,
  },
  {
    id: 'reviziyalar', label: 'Reviziyalar',
    icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
  },
  {
    id: 'chiqimlar', label: 'Chiqimlar',
    icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>,
  },
];

export default function Operations() {
  const [tab, setTab]               = useState('qaytarishlar');
  const [products, setProducts]     = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [suppliers, setSuppliers]   = useState([]);
  const [customers, setCustomers]   = useState([]);
  const [users, setUsers]           = useState([]);
  const [branches, setBranches]     = useState([]);

  useEffect(() => {
    api.get('/products/', { params:{ limit:200 } }).then(r => {
      const data = r.data;
      setProducts(Array.isArray(data) ? data : (data.items || []));
    }).catch(()=>{});
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch(()=>{});
    api.get('/suppliers',  { params:{ limit:200 } }).then(r => setSuppliers(r.data)).catch(()=>{});
    api.get('/customers',  { params:{ limit:500 } }).then(r => setCustomers(r.data)).catch(()=>{});
    api.get('/users/').then(r => setUsers(r.data)).catch(()=>{});
    api.get('/branches').then(r => setBranches(r.data)).catch(()=>{});
  }, []);


  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Operatsiyalar</h1>
          <p className="text-slate-400 text-sm mt-0.5">Sotuvlar, kirimlar, transferlar va omborxona operatsiyalari</p>
        </div>
      </div>

      <div className="flex gap-1 bg-white border border-slate-200 rounded-2xl p-1.5 overflow-x-auto shadow-sm">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold whitespace-nowrap transition-all ${
              tab === t.id
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}>
            {t.icon}<span>{t.label}</span>
          </button>
        ))}
      </div>

      {tab==='sales'        && <SalesTab products={products} customers={customers} branches={branches} users={users} />}
      {tab==='kirimlar'     && <KirimlarTab products={products} warehouses={warehouses} suppliers={suppliers} users={users} branches={branches} />}
      {tab==='qaytarishlar' && <QaytarishlarTab products={products} />}
      {tab==='transferlar'  && <TransferlarTab products={products} warehouses={warehouses} users={users} />}
      {tab==='reviziyalar'  && <ReviziyalarTab warehouses={warehouses} />}
      {tab==='chiqimlar'    && <ChiqimlarTab products={products} users={users} />}
      {tab==='qoldiq'       && <QoldiqTab />}
    </div>
  );
}
