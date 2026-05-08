import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import { matchesSearch, searchVariants } from '../../utils/translit';
import toast from 'react-hot-toast';
const fmt    = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtDay = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
const fmtDt  = (d) => d ? new Date(d).toLocaleString('uz-UZ') : '—';
const saleMeta = {
  completed: { l: 'Tugallandi', c: 'bg-emerald-100 text-emerald-700' },
  refunded:  { l: 'Qaytarildi', c: 'bg-red-100 text-red-600' },
  partial_refund: { l: 'Qisman qaytarish', c: 'bg-amber-100 text-amber-700' },
  cancelled: { l: 'Bekor',     c: 'bg-red-100 text-red-500' },
};
const payMeta = {
  cash: { l: 'Naqd', c: 'bg-emerald-100 text-emerald-700' },
  card: { l: 'Karta', c: 'bg-blue-100 text-blue-700' },
  mixed: { l: 'Aralash', c: 'bg-violet-100 text-violet-700' },
  debt: { l: 'Qarz', c: 'bg-amber-100 text-amber-700' },
};

const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white transition-colors hover:border-slate-300';

const poMeta = {
  draft:     { lKey: 'purchase.statusDraft',    c: 'bg-slate-100 text-slate-600' },
  sent:      { lKey: 'purchase.statusOrdered',  c: 'bg-blue-100 text-blue-700' },
  partial:   { lKey: 'purchase.statusPartial',  c: 'bg-amber-100 text-amber-700' },
  received:  { lKey: 'purchase.statusReceived', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { lKey: 'common.cancel',           c: 'bg-red-100 text-red-500' },
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
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold">
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
  const { t } = useLang();
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
function ProdSearch({ products, onSelect, inputRef, placeholder = 'Mahsulot qidiring...' }) {
  const { t } = useLang();
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const [navIdx, setNavIdx] = useState(-1);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref             = useRef(null);
  const timerRef        = useRef(null);

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
      <div className={`flex items-center gap-2 border border-slate-200 rounded-xl px-3.5 py-2 bg-white transition-all ${open ? 'border-indigo-400 ring-2 ring-indigo-50' : 'hover:border-slate-300'}`}>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          ref={inputRef}
          placeholder={placeholder}
          className="w-full text-sm outline-none bg-transparent" />
        {loading && <div className="w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin shrink-0" />}
      </div>
      {open && displayList.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {displayList.map((p, i) => (
            <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
              className={`w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3 ${navIdx === i ? 'bg-indigo-50' : ''}`}>
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
        </div>
      )}
    </div>
  );
}

/* ─── Supplier search combobox ─── */
function SupSearch({ suppliers, value, onChange, placeholder = "Ta'minotchi tanlang..." }) {
  const { t } = useLang();
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);
  const selected        = suppliers.find(s => String(s.id) === String(value));

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
  const { t } = useLang();
  const [q, setQ]       = useState('');
  const [open, setOpen] = useState(false);
  const ref             = useRef(null);
  const selected        = customers.find(c => c.id === value);

  const filtered = q.trim()
    ? customers.filter(c =>
        matchesSearch(c.name, q) ||
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
  const { t } = useLang();
  const [type, setType] = useState('cash');
  const [paid, setPaid] = useState(String(total));
  const change = Number(paid) - total;
  const PAY_OPTS = [
    { v: 'cash',  l: 'Naqd pul',  icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" /></svg> },
    { v: 'card',  l: 'Karta',     icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg> },
    { v: 'debt',  l: 'Qarzga',    icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
    { v: 'mixed', l: 'Aralash',   icon: <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg> },
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        {/* Modal header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{t('admin.dict.payment') || 'To\'lov'}</h3>
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
          <div className="grid grid-cols-2 gap-2">
            {PAY_OPTS.map(({ v, l, icon }) => (
              <button key={v} onClick={() => setType(v)}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold border transition-all ${
                  type === v
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-200'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-indigo-300 hover:bg-indigo-50'
                }`}>
                {icon} {l}
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
            <Btn v="ghost" onClick={onClose}>{t('common.cancel')}</Btn>
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
  const { t } = useLang();
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
    return matchesSearch(p.name, prodQ) ||
           matchesSearch(p.sku, prodQ) ||
           (p.barcode && p.barcode.includes(prodQ.trim()));
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

  const doSave = (payType, paidAmount) => {
    if (!cart.length) { setErr("Kamida bitta mahsulot qo'shing"); return; }
    if (saving) return;
    setSaving(true); setErr('');
    setShowPay(false);

    // Darrov navigatsiya — API background da ishlaydi
    const promise = api.post('/sales', {
      items: cart.map(c => ({ product_id: c.product.id, quantity: c.qty, unit_price: c.price, discount: c.discount })),
      payment_type:    payType,
      paid_amount:     paidAmount,
      discount_amount: 0,
      note:            note || null,
      customer_id:     custId ? Number(custId) : null,
    });

    onBack(); // Darrov ro'yxatga qaytish
    promise
      .then(() => { onSaved(); }) // Ro'yxatni yangilash
      .catch(e => console.error('Sale error:', e.response?.data?.detail || e));
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
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">{t('admin.dict.th_prod') || 'MAHSULOT'}</th>
                    <th className="text-center px-3 py-2.5 text-xs font-semibold text-slate-500 w-28">{t('admin.dict.th_qty') || 'MIQDOR'}</th>
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
                <span className="text-xs text-slate-400 mr-2">{t('admin.dict.total_colon') || 'Jami:'}</span>
                <span className="text-xl font-bold text-indigo-600">{fmt(subtotal)} so'm</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-5 py-3.5 bg-white border-t border-slate-100 shrink-0 shadow-[0_-1px_8px_rgba(0,0,0,0.06)]">
        <div className="flex items-center gap-3">
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
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
                <label className="text-xs font-medium text-slate-500 mb-1 block">{t('admin.dict.qty') || 'Miqdor'}</label>
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
              <span className="text-xs text-slate-400">{t('admin.dict.total_colon') || 'Jami:'}</span>
              <span className="text-lg font-bold text-indigo-600">{fmt(Number(qaItem.qty) * Number(qaItem.price) - Number(qaItem.discount))} so'm</span>
            </div>
            <div className="flex gap-2">
              <Btn v="ghost" onClick={() => setQaItem(null)} sm>{t('common.cancel')}</Btn>
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
  const { t } = useLang();
  const [sale, setSale] = useState(null);
  useEffect(() => {
    api.get(`/sales/${saleId}`).then(r => setSale(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
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
              <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.product') || 'Mahsulot'}</th>
              <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Soni</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Narxi</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">Chegirma</th>
              <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.total') || 'Jami'}</th>
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

/* ══════════════════════════════════════════════════════════
   KIRIM CREATE VIEW — split panel
══════════════════════════════════════════════════════════ */
function KirimCreateView({ onBack, onSaved }) {
  const { t } = useLang();
  // Fetch our own data — don't depend on parent props (avoids race condition)
  const [products,   setProds]  = useState([]);
  const [warehouses, setWhs]    = useState([]);
  const [suppliers,  setSups]   = useState([]);
  const [wallets,    setWallets]= useState([]);

  useEffect(() => {
    api.get('/products/',           { params:{ limit:1000, status:'active' } })
       .then(r => setProds(Array.isArray(r.data) ? r.data : (r.data.items||[]))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/inventory/warehouses').then(r => setWhs(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/suppliers',           { params:{ limit:100 } }).then(r => setSups(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/finance/wallets').then(r => { setWallets(r.data); if(r.data.length > 0) setPayForm(p=>({...p, wallet_id: r.data[0].id})); }).catch(console.error);
  }, []);

  // PO form
  const [poForm, setPoForm]       = useState({ supplier_id:'', warehouse_id:'', note:'', expected_date:'' });
  const [poItems, setPoItems]     = useState([]);
  
  // Auto-update price flags
  const [autoRetail, setAutoRet]     = useState(false);
  const [autoWholesale, setAutoWho]  = useState(false);
  // USD exchange rate
  const [usdRate, setUsdRate]        = useState('12700');
  const [saving, setSaving]          = useState(false);
  const [err, setErr]                = useState('');

  // Left panel: selected product + input fields
  const searchRef               = useRef(null);
  const qtyRef                  = useRef(null);
  const [sel, setSel]           = useState(null);
  const [qty, setQty]           = useState('');
  const [cost, setCost]         = useState('');
  const [newSalePrice, setNewSalePrice] = useState('');
  const [newWholesalePrice, setNewWholesalePrice] = useState('');
  const [discType, setDiscType] = useState('pct');  // 'pct' | 'amt'
  const [discVal, setDiscVal]   = useState('0');
  const [currency, setCurrency] = useState('UZS');  // 'UZS' | 'USD'

  const selectProduct = (p) => {
    setSel(p);
    setCost(String(Number(p.cost_price) || ''));
    setNewSalePrice(p.sale_price ? String(Math.round(p.sale_price)) : '');
    setNewWholesalePrice(p.wholesale_price ? String(Math.round(p.wholesale_price)) : '');
    setQty(''); setDiscVal('0'); setDiscType('pct'); setCurrency('UZS');
    setTimeout(() => { if (qtyRef.current) qtyRef.current.focus(); }, 10);
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
      new_sale_price: newSalePrice ? Number(newSalePrice) : null,
      new_wholesale_price: newWholesalePrice ? Number(newWholesalePrice) : null,
    };
    
    setPoItems(prev => {
      const ex = prev.find(x => x.product_id === sel.id);
      if (ex) return prev.map(x => x.product_id === sel.id ? { ...x, qty_ordered: x.qty_ordered + Number(qty) } : x);
      return [...prev, { ...base, qty_ordered: Number(qty) }];
    });
    setSel(null); setQty(''); setCost(''); setDiscVal('0');
    setTimeout(() => { if (searchRef.current) searchRef.current.focus(); }, 10);
  };

  const updPoItem = (i, field, val) => setPoItems(prev => prev.map((x, idx) => idx === i ? { ...x, [field]: val, net_cost: calcNet(field==='unit_cost'?val:x.unit_cost, field==='discount_type'?val:x.discount_type, field==='discount_val'?val:x.discount_val, field==='currency'?val:x.currency) } : x));

  const activeItems = poItems;
  const totalNet = activeItems.reduce((s, i) => s + i.qty_ordered * (i.net_cost||0), 0);
  const hasCurrency = activeItems.some(i => i.currency === 'USD');

  const [showPay, setShowPay] = useState(false);
  const [payForm, setPayForm] = useState({ discType: 'amt', discVal: '', cash: '', info: '', wallet_id: '' });

  const calcFinalTotal = () => {
    const d = Number(payForm.discVal) || 0;
    return payForm.discType === 'pct' ? totalNet * (1 - d / 100) : totalNet - d;
  };
  const finalTotal = calcFinalTotal();
  const paid = (Number(payForm.cash) || 0);
  const debt = Math.max(0, finalTotal - paid);
  const change = Math.max(0, paid - finalTotal);

  const savePo = (status = 'draft', paymentInfo = null) => {
    if (!poForm.supplier_id || !poForm.warehouse_id || !poItems.length) { setErr("Barcha majburiy maydonlarni to'ldiring"); return; }
    if (saving) return;
    setSaving(true); setErr('');

    const payload = {
      supplier_id: Number(poForm.supplier_id), warehouse_id: Number(poForm.warehouse_id),
      status,
      note: poForm.note || null, expected_date: poForm.expected_date || null,
      update_retail: autoRetail, update_wholesale: autoWholesale,
      items: poItems.map(i => ({
        product_id: i.product_id,
        qty_ordered: i.qty_ordered,
        unit_cost: i.net_cost,
        new_sale_price: i.new_sale_price,
        new_wholesale_price: i.new_wholesale_price
      })),
    };

    if (paymentInfo) {
      payload.paid_amount = paymentInfo.paid;
      payload.discount_amount = totalNet - finalTotal;
      payload.payment_type = 'cash';
      if (paymentInfo.wallet_id) payload.wallet_id = Number(paymentInfo.wallet_id);
      if (paymentInfo.info) payload.note = (payload.note ? payload.note + '\n' : '') + paymentInfo.info;
    }

    // Darrov navigatsiya — API background da ishlaydi
    onBack();
    api.post('/purchase-orders', payload)
      .then(() => { onSaved(); })
      .catch(e => console.error('PO error:', e.response?.data?.detail || e));
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <CreateHeader title={t('purchase.newKirimTitle')} onBack={onBack} />

      {/* ── Header fields ── */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-100 bg-white shrink-0 flex-wrap shadow-sm">
        {/* Supplier combobox */}
        <div className="w-64">
          <SupSearch
            suppliers={suppliers}
            value={poForm.supplier_id}
            onChange={v => setPoForm(f=>({...f,supplier_id:v}))}
            placeholder={t('purchase.selectSupplier')}
          />
        </div>
        {/* Warehouse */}
        <select
          value={poForm.warehouse_id}
          onChange={e => setPoForm(f=>({...f,warehouse_id:e.target.value}))}
          className={`${ic} min-w-40`}>
          <option value="">{t('purchase.selectWarehouse')}</option>
          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <input type="date" value={poForm.expected_date} onChange={e => setPoForm(f=>({...f,expected_date:e.target.value}))} className={ic} />
        
        {/* USD exchange rate — shown when any item uses USD */}
        {(hasCurrency || currency === 'USD') && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 font-semibold">1 USD =</span>
            <input type="number" value={usdRate} onChange={e => setUsdRate(e.target.value)}
              className={`${ic} w-28`} placeholder={t('purchase.exchangeRate')} />
            <span className="text-xs text-slate-500">so'm</span>
          </div>
        )}
        <input placeholder={t('admin.dict.comment') || 'Izoh'} value={poForm.note}
          onChange={e => setPoForm(f=>({...f,note:e.target.value}))}
          className={`${ic} flex-1 min-w-32`} />
      </div>

      {/* ── Split body ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div className="w-[500px] border-r border-slate-100 p-6 flex flex-col gap-6 overflow-y-auto shrink-0 bg-white shadow-sm">
          <Lbl t={t('purchase.searchProduct')}>
            <ProdSearch products={products} onSelect={selectProduct} inputRef={searchRef} />
          </Lbl>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 space-y-4">
              {/* Product info */}
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shrink-0 shadow-sm">
                  {sel.name.slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-base truncate">{sel.name}</div>
                  <div className="text-sm text-slate-600 mt-1">
                    {t('purchase.stockLabel')} <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit||'dona'}
                    <span className="mx-2 text-slate-300">|</span>
                    {t('purchase.retailLabel')} <strong className="text-indigo-600">{fmt(sel.sale_price)}</strong>
                  </div>
                </div>
              </div>

              {/* Cost price + currency */}
              <div>
                <label className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-2 block">{t('purchase.costPrice')}</label>
                <div className="flex rounded-xl border border-slate-200 bg-white focus-within:ring-2 focus-within:ring-indigo-500 overflow-hidden shadow-sm">
                  <input type="number" min="0" value={cost} onChange={e => setCost(e.target.value)}
                    className="flex-1 min-w-0 px-4 py-3 text-base font-semibold focus:outline-none bg-transparent" />
                  <div className="flex border-l border-slate-200">
                    {['UZS','USD'].map(c => (
                      <button key={c} type="button" onClick={() => setCurrency(c)}
                        className={`px-4 py-3 text-sm font-bold transition-colors ${currency===c?'bg-indigo-600 text-white':'bg-slate-50 text-slate-500 hover:bg-slate-100'}`}>
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
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
                      <input type="number" value={newSalePrice} onChange={e=>setNewSalePrice(e.target.value)} className={`${ic} w-full text-sm py-2 font-semibold`} placeholder={Math.round(sel.sale_price||0)} />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-amber-700/70 mb-1.5 block">{t('purchase.newWholesalePrice')}</label>
                      <input type="number" value={newWholesalePrice} onChange={e=>setNewWholesalePrice(e.target.value)} className={`${ic} w-full text-sm py-2 font-semibold`} placeholder={Math.round(sel.wholesale_price||0)} />
                    </div>
                  </div>
                </div>
              )}

              {/* Discount */}
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">{t('purchase.discount')}</label>
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
                  <span className="text-xs text-emerald-700 font-semibold">{t('purchase.netCost')}</span>
                  <span className="text-sm font-black text-emerald-700">{fmt(Math.round(selNet))} so'm</span>
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
                  <span className="text-sm text-slate-500 font-medium shrink-0">{sel.unit||'dona'}</span>
                </div>
              </Lbl>

              {/* Total preview */}
              <div className="text-xs text-slate-500 text-right">
                {t('admin.dict.total_colon')} <strong className="text-indigo-700">{fmt(Math.round(selNet * Number(qty)))} {t('purchase.somUnit')}</strong>
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
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-2xl font-bold text-sm transition-all shadow-sm shadow-indigo-200 active:scale-95">
            <svg className="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            {t('purchase.addToList')}
          </button>

          {activeItems.length > 0 && (
            <div className="bg-indigo-600 rounded-2xl p-4 text-white">
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
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product') || 'Mahsulot'}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-20">{t('purchase.colQty')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('purchase.colPrice')}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-28">{t('purchase.discount')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('purchase.colNetPrice')}</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.total') || 'Jami'}</th>
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
                      <td className="px-3 py-2.5 text-slate-400 text-xs">{i+1}</td>
                      <td className="px-3 py-2.5">
                        <div className="font-medium text-sm">{it.product_name}</div>
                        <div className="text-xs text-slate-400">{it.unit}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <input type="number" min="1" value={qty_n}
                          onChange={e => updFn(i, 'qty_ordered', Number(e.target.value))}
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
                      <td className="pr-2">
                        <button onClick={() => setPoItems(p=>p.filter((_,idx)=>idx!==i))}
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
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoRetail?'bg-indigo-600 text-white border-indigo-600':'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            {t('purchase.retail')}
          </button>
          <button onClick={() => setAutoWho(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${autoWholesale?'bg-amber-500 text-white border-amber-500':'bg-white text-slate-600 border-slate-200 hover:border-amber-300'}`}>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" /></svg>
            {t('purchase.wholesale')}
          </button>
        </div>
        <div className="flex gap-2 ml-auto items-center">
          {err && <span className="text-red-500 text-sm whitespace-nowrap bg-red-50 px-3 py-1.5 rounded-lg border border-red-100 font-semibold">{err}</span>}
          <Btn v="ghost" onClick={onBack}>{t('common.cancel')}</Btn>
          <Btn v="secondary" onClick={() => savePo('draft')} disabled={saving}>{t('purchase.saveDraft')}</Btn>
          <Btn v="secondary" onClick={() => savePo('sent')} disabled={saving}>{t('purchase.saveNoPayment')}</Btn>
          <Btn onClick={() => {
            if (!poForm.supplier_id || !poForm.warehouse_id || !poItems.length) { 
              setErr("Barcha majburiy maydonlarni (Ta'minotchi, Ombor, Mahsulotlar) to'ldiring!"); 
              return; 
            }
            setErr('');
            setShowPay(true);
          }} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white shadow-sm shadow-blue-200">{t('admin.dict.payment') || 'To\'lov'}</Btn>
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
                      <input type="radio" checked={payForm.discType==='amt'} onChange={()=>setPayForm(p=>({...p,discType:'amt'}))} className="w-4 h-4 text-blue-600" /> {t('purchase.noDiscountLabel')}
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 font-medium hover:text-slate-700 transition-colors">
                      <input type="radio" checked={payForm.discType==='pct'} onChange={()=>setPayForm(p=>({...p,discType:'pct'}))} className="w-4 h-4 text-blue-600" /> %
                    </label>
                  </div>
                  <div className="flex h-11">
                    <input type="number" value={payForm.discVal} onChange={e=>setPayForm(p=>({...p,discVal:e.target.value}))} className={`${ic} flex-1 rounded-r-none border-r-0 text-base font-medium`} placeholder="0" />
                    <div className="bg-slate-50 px-4 flex items-center border border-slate-200 text-slate-500 text-sm font-semibold rounded-r-xl">UZS | 1</div>
                  </div>
                </div>

                {/* Kassa */}
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-600">{t('finance.wallet') || 'Kassa/Hisob'}</label>
                  <select value={payForm.wallet_id} onChange={e=>setPayForm(p=>({...p,wallet_id:e.target.value}))} className={`${ic} w-full h-11 bg-white text-base`}>
                    <option value="">Tanlang...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)})</option>)}
                  </select>
                </div>
              </div>

              {/* To'lov */}
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-600">{t('admin.dict.payment') || 'To\'lov'}</label>
                <div className="flex gap-2 h-11 items-center">
                  {/* Naqd label separated */}
                  <div className="bg-slate-50 px-5 flex items-center border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 h-full shadow-sm">{t('purchase.cash')}</div>
                  {/* Input group */}
                  <div className="flex flex-1 items-center h-full rounded-xl focus-within:ring-2 focus-within:ring-indigo-500 overflow-hidden shadow-sm">
                    <input type="number" min="0" value={payForm.cash} onChange={e=>setPayForm(p=>({...p,cash:e.target.value}))} className="flex-1 w-full h-full border border-slate-200 border-r-0 rounded-l-xl px-4 text-base font-medium outline-none" placeholder="0" />
                    <div className="bg-white px-4 flex items-center border border-slate-200 border-x-0 text-indigo-600 text-sm font-bold h-full">UZS | 1</div>
                    <button onClick={() => setPayForm(p=>({...p, cash: String(Math.round(finalTotal))}))} className="bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 border-l-0 font-semibold px-6 h-full rounded-r-xl transition-colors whitespace-nowrap">
                      {t('purchase.totalBtn')}
                    </button>
                  </div>
                </div>
              </div>

              {/* Malumot */}
              <div className="space-y-2">
                <textarea rows="3" value={payForm.info} onChange={e=>setPayForm(p=>({...p,info:e.target.value}))} className={`${ic} resize-none w-full text-sm leading-relaxed`} placeholder={t('purchase.infoPlaceholder')}></textarea>
              </div>

              {/* Summary blocks aligned to right */}
              <div className="flex flex-col items-end gap-3 pt-2">
                <div className="flex items-center justify-between w-64 text-lg">
                  <span className="text-slate-500">{t('purchase.summaryTotal')}</span>
                  <span className="font-bold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-lg">{fmt(Math.round(finalTotal))}</span>
                </div>
                <div className="flex items-center justify-between w-64 text-lg">
                  <span className="text-slate-500">{t('purchase.summaryPaid')}</span>
                  <span className="font-bold text-blue-600 bg-blue-50 px-3 py-1 rounded-lg">{fmt(Math.round(paid))} <span className="text-xs uppercase">uzs</span></span>
                </div>
                <div className="flex items-center justify-between w-64 text-lg">
                  <span className="text-slate-500">{t('purchase.summaryDebt')}</span>
                  <span className="font-bold text-red-500 bg-red-50 px-3 py-1 rounded-lg">{fmt(Math.round(debt))}</span>
                </div>
                <div className="flex items-center justify-between w-64 text-lg">
                  <span className="text-slate-500">{t('purchase.summaryChange')}</span>
                  <span className="font-bold text-slate-600 bg-slate-100 px-3 py-1 rounded-lg">{fmt(Math.round(change))}</span>
                </div>
              </div>
            </div>

            {/* Modal Footer Buttons */}
            {/* Modal Footer Buttons */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 bg-slate-50 mt-auto rounded-b-2xl flex-wrap">
              <div className="text-sm font-semibold text-slate-500 flex-1">{t('purchase.supplierDebt')} <span className="text-slate-800 ml-1">{fmt(debt)} UZS</span></div>
              <button onClick={() => setShowPay(false)} className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-semibold bg-white hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
              <button disabled={saving} onClick={() => savePo('received', { paid: paid - change, info: payForm.info, wallet_id: payForm.wallet_id })} className="px-6 py-2.5 rounded-xl bg-orange-400 hover:bg-orange-500 text-white font-bold flex items-center gap-2 transition-colors disabled:opacity-50 shadow-sm">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" /></svg>
                {t('purchase.saveAndPrint')}
              </button>
              <button disabled={saving} onClick={() => savePo('received', { paid: paid - change, info: payForm.info, wallet_id: payForm.wallet_id })} className="px-8 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold transition-colors shadow-sm shadow-blue-200 disabled:opacity-50 flex items-center gap-2">
                {saving ? '...' : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/></svg>
                    {t('purchase.receiveAndSave')}
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

/* ══════════════════════════════════════════════════════════
   KIRIMLAR TAB
══════════════════════════════════════════════════════════ */
// eslint-disable-next-line no-unused-vars
function KirimlarTab({ products, warehouses, suppliers }) {
  const { t } = useLang();
  const [mode, setMode]       = useState('list');
  const [pos, setPos]         = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip]       = useState(0);
  const [stFilter, setStFil]  = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [branches, setBranches] = useState([]);
  const [detail, setDetail]   = useState(null);
  const [recModal, setRec]    = useState(null);
  const [recSaving, setRS]    = useState(false);
  const LIMIT = 20;

  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (stFilter) params.status = stFilter;
      if (branchFilter) params.branch_id = branchFilter;
      const r = await api.get('/purchase-orders', { params });
      setPos(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, stFilter, branchFilter]);

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

  if (mode === 'create') return <KirimCreateView onBack={() => setMode('list')} onSaved={load} />;

  const cols = [
    { k:'number',         l:t('purchase.colNumber') || 'Raqam' },
    { k:'supplier_name',  l:t('purchase.supplier') || "Ta'minotchi" },
    { k:'warehouse_name', l:t('purchase.colWarehouse') || 'Ombor' },
    { k:'status',         l:t('purchase.filterStatus') || 'Holat', r: v => <Badge meta={poMeta} val={v} /> },
    { k:'total_amount',   l:t('purchase.colTotal') || "Jami (so'm)", r: v => fmt(v) },
    { k:'paid_amount',    l:"To'langan", r: v => <span className="text-emerald-600 font-semibold">{fmt(v)}</span> },
    { k:'debt',           l:"Qarzga", r: (_, row) => { const d = Number(row.total_amount) - Number(row.paid_amount || 0) - Number(row.discount_amount || 0); return d > 0 ? <span className="text-red-500 font-semibold">{fmt(d)}</span> : '—'; } },
    { k:'created_at',     l:t('purchase.colDate') || 'Sana', r: v => fmtDay(v) },
    { k:'id', l:'', r: (v,row) => ['draft','ordered','partial'].includes(row.status) ? (
      <button onClick={e=>{e.stopPropagation(); openDetail(row);}}
        className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 font-medium whitespace-nowrap">
        {t('purchase.receive')}
      </button>
    ) : null },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Lbl t={t('purchase.filterStatus')}>
            <select value={stFilter} onChange={e => setStFil(e.target.value)} className={ic}>
              <option value="">{t('admin.dict.all2') || t('purchase.allBranches')}</option>
              {Object.entries(poMeta).map(([v,m]) => <option key={v} value={v}>{m.lKey ? t(m.lKey) : m.l}</option>)}
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
              <h3 className="text-lg font-bold">Buyurtma · {detail.number}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-4 gap-3 text-sm">
                {[[t('purchase.supplier'),detail.supplier_name],[t('purchase.colWarehouse'),detail.warehouse_name],[t('purchase.filterStatus'),<Badge meta={poMeta} val={detail.status}/>],[t('purchase.colDate'),fmtDay(detail.created_at)]].map(([k,v])=>(
                  <div key={k} className="bg-slate-50 rounded-xl p-3"><div className="text-xs text-slate-500 mb-1">{k}</div><div className="font-semibold">{v}</div></div>
                ))}
              </div>
              <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                <thead className="bg-slate-50"><tr>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.product') || 'Mahsulot'}</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Buyurtma</th>
                  <th className="text-center px-4 py-2.5 text-xs text-slate-500 font-semibold">Qabul</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.price') || 'Narx'}</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-semibold">{t('admin.dict.total') || 'Jami'}</th>
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
              <Btn v="ghost" onClick={() => setDetail(null)}>{t('admin.dict.close') || 'Yopish'}</Btn>
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
              <Btn v="ghost" onClick={() => setRec(null)} className="flex-1">{t('common.cancel')}</Btn>
              <Btn v="green" onClick={receivePo} disabled={recSaving} className="flex-1">{recSaving?'...':'Tasdiqlash'}</Btn>
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
  name: '', inn: '', phone: '', email: ''
};
function StarRating({ value }) {
  const { t } = useLang();
  return <div className="flex gap-0.5">{[1,2,3,4,5].map(s=><span key={s} className={`text-base ${(value||0)>=s?'text-amber-400':'text-slate-200'}`}>{'★'}</span>)}</div>;
}
function AvatarS({ name }) {
  const { t } = useLang();
  const cols=['bg-indigo-100 text-indigo-600','bg-emerald-100 text-emerald-600','bg-violet-100 text-violet-600','bg-rose-100 text-rose-600','bg-amber-100 text-amber-600'];
  const c=cols[(name?.charCodeAt(0)||0)%cols.length];
  return <div className={`w-8 h-8 ${c} rounded-full flex items-center justify-center font-bold shrink-0 text-sm`}>{name?.charAt(0).toUpperCase()}</div>;
}
function SuppliersTab() {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(emptySupplier);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const inp = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';

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
    { key: '',                label: "— Tanlang —" },
    { key: 'Nomi',            label: "Ta'minotchi nomi *" },
    { key: 'INN',             label: "INN" },
    { key: 'Telefon',         label: "Telefon" },
    { key: 'Email',           label: "Email" },
    { key: 'Manzil',          label: "Manzil" },
    { key: "To'lov muddati (kun)", label: "To'lov muddati (kun)" },
    { key: 'Qarz',            label: "Qarz" },
    { key: '__SKIP__',        label: "— O'tkazib yuborish —" },
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

  const parseExcel = (file) => {
    setImportFile(file); setImportResult(null); setImportError(''); setImportPage(1);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { defval: '', raw: false });
        setImportRows(rows);
        autoMap(rows);
      } catch {
        setImportError("Fayl o'qishda xatolik. Iltimos .xlsx formatdagi faylni tanlang.");
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

  const downloadTemplate = () => {
    const ws = XLSX.utils.json_to_sheet([{
      'Nomi': "Euro Print MChJ", 'INN': '123456789',
      'Telefon': '+998901234567', 'Email': 'info@europrint.uz',
      'Manzil': 'Toshkent sh.', "To'lov muddati (kun)": 30, 'Qarz': 0
    }]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Ta'minotchilar");
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
      setImportError(err.response?.data?.detail || 'Server xatosi');
    } finally { setImportLoading(false); }
  };

  const load = (q=search) => api.get(`/suppliers${q?'?search='+encodeURIComponent(q):''}`).then(r=>setList(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(()=>{load();},[]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(()=>{const t=setTimeout(()=>load(search),400);return()=>clearTimeout(t);},[search]);
  const close=()=>{setModal(null);setSel(null);setErr('');};
  const openEdit=(s)=>{setForm({name:s.name,inn:s.inn||'',phone:s.phone||'',email:s.email||''});setSel(s);setErr('');setModal('form');};
  const handleSave=async(e)=>{
    e.preventDefault();setSaving(true);setErr('');
    try{
      const p={...form};
      if(sel)await api.patch(`/suppliers/${sel.id}`,p);else await api.post('/suppliers',p);close();load();
    }catch(ex){setErr(ex.response?.data?.detail||'Xatolik');}finally{setSaving(false);}};
  const del=async(id)=>{if(!confirm("O'chirilsinmi?"))return;await api.delete(`/suppliers/${id}`);load();};

  return(
    <div className="space-y-4">
      <div className="flex gap-3">
        <div className="relative flex-1"><svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          <input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('purchase.searchSupplier')} value={search} onChange={e=>setSearch(e.target.value)}/></div>
        
        <button
          onClick={() => {
            const ws = XLSX.utils.json_to_sheet(list.map(s => ({
              "Ta'minotchi": s.name, 'INN': s.inn || '—', 'Telefon': s.phone || '—', 'Email': s.email || '—', 'Qarz': s.debt_balance || 0
            })));
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, "Ta'minotchilar");
            saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `taminotchilar_${new Date().toISOString().slice(0,10)}.xlsx`);
          }}
          className="px-4 py-2 text-sm font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-xl flex items-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          {t('purchase.exportExcel')}
        </button>
        <button
          onClick={openImport}
          className="px-4 py-2 text-sm font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-xl flex items-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
          {t('purchase.importExcel')}
        </button>

        <button onClick={()=>{setForm(emptySupplier);setSel(null);setErr('');setModal('form');}} className="px-4 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-xl flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>{t('common.new')}
        </button>
      </div>
      <div className="flex items-center justify-between px-4 py-3 bg-white border border-slate-100 rounded-xl shadow-sm">
        <span className="text-sm font-medium text-slate-500">{t('purchase.totalSupplierDebt')}</span>
        <span className="text-lg font-bold text-red-500">{fmt(list.reduce((sum, s) => sum + Number(s.debt_balance || 0), 0))} so'm</span>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">{[t('purchase.supplier'),'INN',t('common.phone'),t('purchase.colRating'),t('common.debt'),''].map(h=><th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(s=>(
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="px-5 py-4"><div className="flex items-center gap-2.5"><AvatarS name={s.name}/><div><div className="text-sm font-semibold text-slate-800">{s.name}</div>{s.email&&<div className="text-xs text-slate-400">{s.email}</div>}</div></div></td>
                <td className="px-5 py-4 text-sm font-mono text-slate-600">{s.inn||'\u2014'}</td>
                <td className="px-5 py-4 text-sm text-slate-500">{s.phone||'\u2014'}</td>
                <td className="px-5 py-4"><StarRating value={s.rating}/></td>
                <td className="px-5 py-4 text-sm font-semibold">{s.debt_balance > 0 ? <span className="text-red-500">{fmt(s.debt_balance)} so'm</span> : <span className="text-emerald-500">0 so'm</span>}</td>
                <td className="px-5 py-4"><div className="flex items-center gap-1">
                  <button onClick={()=>openEdit(s)} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
                  <button onClick={()=>del(s.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>
                </div></td>
              </tr>
            ))}
            {list.length===0&&<tr><td colSpan={5} className="px-5 py-12 text-center text-slate-400 text-sm">{t('purchase.noSuppliers')}</td></tr>}
          </tbody>
        </table>
      </div>
      {modal==='form'&&(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col" onClick={e=>e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{sel?"Tahrirlash":"Yangi ta'minotchi"}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
            </div>
            <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="block text-xs font-semibold text-slate-600 mb-1.5">Nomi *</label><input required className={inp} value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Kompaniya nomi"/></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">INN</label><input className={inp} value={form.inn} onChange={e=>setForm({...form,inn:e.target.value})}/></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.phone') || 'Telefon'}</label><input className={inp} value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})}/></div>
                <div className="col-span-2"><label className="block text-xs font-semibold text-slate-600 mb-1.5">Email</label><input type="email" className={inp} value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></div>
              </div>
              {err&&<div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
            </form>
            <div className="p-6 border-t border-slate-100 flex gap-3 shrink-0">
              <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
              <button onClick={handleSave} disabled={saving} className="flex-1 py-2.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving?'Saqlanmoqda...':'Saqlash'}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── IMPORT MODAL (Full screen) ────────────── */}
      {importOpen && (
        <div className="fixed inset-0 z-50 bg-slate-50 flex flex-col">
          {/* Top Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <button onClick={resetImport} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
              <h2 className="text-xl font-bold text-slate-800">Ta'minotchilarni Exceldan yuklash</h2>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={downloadTemplate} className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-lg transition-colors">
                Shablon
              </button>
              <label className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-lg border border-slate-200 cursor-pointer">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                Fayl tanlash
                <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
              </label>
              <button
                onClick={handleImport}
                disabled={!buildPayload().length || importLoading || !(Object.values(colMap).includes('Nomi') || (allowUpdate && Object.values(colMap).includes('INN')))}
                className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors border border-transparent"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
                {importLoading ? `Saqlanmoqda... ${importProgress}%` : 'Saqlash'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto flex flex-col">
            {!importFile ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                <svg className="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">Boshlash uchun Excel fayl yuklang</p>
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Options Toolbar */}
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shadow-sm bg-white shrink-0">
                  <div className="flex items-center gap-6">
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${allowUpdate ? 'bg-indigo-600' : 'bg-slate-200'}`}>
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${allowUpdate ? 'translate-x-6' : 'translate-x-1'}`} />
                      </div>
                      <span className="text-sm font-semibold text-slate-700 group-hover:text-indigo-600 transition-colors">Tahrirlash ruxsat</span>
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-3 bg-white border border-slate-200 px-3 py-1.5 rounded-xl">
                      <span className="text-sm font-medium text-slate-600">O'tkazib yuborish (qator):</span>
                      <button onClick={() => setSkipRows(Math.max(0, skipRows - 1))} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">−</button>
                      <span className="text-sm font-bold w-6 text-center">{skipRows}</span>
                      <button onClick={() => setSkipRows(skipRows + 1)} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">+</button>
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="px-6 py-2.5 flex items-center justify-between border-b border-slate-100 shrink-0">
                    <span className="text-sm text-slate-600 font-medium">
                      Yuklanayotganlar: <strong>{buildPayload().length} ta</strong>
                    </span>
                    {!(Object.values(colMap).includes('Nomi') || (allowUpdate && Object.values(colMap).includes('INN'))) && (
                      <span className="text-sm font-semibold text-red-500">
                        * {allowUpdate ? 'Nomi yoki INN' : 'Nomi'} ustunini tanlash majburiy
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
                                className="w-full bg-white border border-slate-300 px-2 py-1.5 rounded-lg text-sm font-semibold text-slate-700 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
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
                              <td className="px-3 py-2 text-slate-400 font-medium border-r border-slate-100 bg-slate-50">{i + 1} {skipped && <span className="text-[10px] text-amber-500 block leading-none">Skip</span>}</td>
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
                          Yana ko'rsatish
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
                    <div className="text-sm font-semibold text-emerald-500">Yangi qo'shildi</div>
                  </div>
                  {importResult.updated > 0 && (
                    <div className="px-5 py-3 bg-indigo-50 rounded-xl text-center min-w-[120px]">
                      <div className="text-3xl font-black text-indigo-600">{importResult.updated}</div>
                      <div className="text-sm font-semibold text-indigo-500">Yangilandi</div>
                    </div>
                  )}
                  <div className={`px-5 py-3 rounded-xl text-center min-w-[120px] ${importResult.skipped > 0 ? 'bg-amber-50' : 'bg-slate-50'}`}>
                    <div className={`text-3xl font-black ${importResult.skipped > 0 ? 'text-amber-600' : 'text-slate-400'}`}>{importResult.skipped}</div>
                    <div className={`text-sm font-semibold ${importResult.skipped > 0 ? 'text-amber-500' : 'text-slate-400'}`}>O'tkazib yuborildi</div>
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

/* ===================== BUYURTMALAR TAB ===================== */
function PurchaseOrdersTab() {
  const { t } = useLang();
  const [pos, setPos] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get('/purchase-orders'); setPos(data); }
    catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
      {loading ? (
        <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"/></div>
      ) : (
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">{[t('purchase.colNumber'),t('purchase.supplier'),t('purchase.colWarehouse'),t('purchase.colTotal'),t('purchase.filterStatus')].map(h=><th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-50">
            {pos.map(p=>(
              <tr key={p.id} className="hover:bg-slate-50">
                <td className="px-6 py-4 text-sm font-mono font-semibold text-indigo-600">{p.number}</td>
                <td className="px-6 py-4 text-sm text-slate-700 font-medium">{p.supplier_name}</td>
                <td className="px-6 py-4 text-sm text-slate-500">{p.warehouse_name}</td>
                <td className="px-6 py-4 text-sm font-semibold text-slate-800">{Number(p.total_amount).toLocaleString()} <span className="text-slate-400 font-normal">so'm</span></td>
                <td className="px-6 py-4"><Badge meta={poMeta} val={p.status} /></td>
              </tr>
            ))}
            {pos.length===0&&<tr><td colSpan={5} className="px-6 py-16 text-center text-slate-400 text-sm">{t('purchase.noOrders')}</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ===================== MAIN ===================== */
const TABS_IDS = [
  { id: 'kirimlar',  key: 'purchase.tabKirimlar',  icon: '\u{1F4E6}' },
  { id: 'suppliers', key: 'purchase.tabSuppliers', icon: '\u{1F3ED}' },
  { id: 'orders',    key: 'purchase.tabOrders',    icon: '\u{1F4CB}' },
];

export default function Purchases() {
  const { t } = useLang();
  const [tab, setTab] = useState('kirimlar');
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  useEffect(() => {
    api.get('/products/', { params:{ limit:300 } }).then(r => setProducts(r.data.items||r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/suppliers', { params:{ limit:100 } }).then(r => setSuppliers(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('purchase.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('purchase.pageSubtitle')}</p>
      </div>
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {TABS_IDS.map(tab_=>(
          <button key={tab_.id} onClick={()=>setTab(tab_.id)}
            className={`px-5 py-2 text-sm font-semibold rounded-lg transition-all flex items-center gap-2 ${tab===tab_.id?'bg-white text-slate-800 shadow-sm':'text-slate-500 hover:text-slate-700'}`}>
            <span>{tab_.icon}</span>{t(tab_.key)}
          </button>
        ))}
      </div>
      {tab==='kirimlar'  && <KirimlarTab products={products} warehouses={warehouses} suppliers={suppliers}/>}
      {tab==='suppliers' && <SuppliersTab/>}
      {tab==='orders'    && <PurchaseOrdersTab/>}
    </div>
  );
}

