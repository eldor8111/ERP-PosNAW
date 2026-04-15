import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import { Link } from 'react-router-dom';
import api from '../../api/axios';
import { getReceiptSettings, buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import toast from 'react-hot-toast';
const fmt   = (v) => Number(v || 0).toLocaleString('uz-UZ');
const today = () => new Date().toISOString().slice(0, 10);

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
const inputCls = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';
const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';

function Badge({ meta, val }) {
  const { t } = useLang();
  const m = meta[val] || { l: val, c: 'bg-slate-100 text-slate-600' };
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${m.c}`}>{m.l}</span>;
}
function Btn({ v = 'primary', sm, children, ...p }) {
  const { t } = useLang();
  const cl = { primary: 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm', ghost: 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200' }[v];
  return <button className={`${sm?'px-3 py-1.5 text-xs':'px-4 py-2.5 text-sm'} rounded-xl font-semibold transition-all ${cl} disabled:opacity-50`} {...p}>{children}</button>;
}
function Avatar({ name }) {
  const { t } = useLang();
  const colors = ['bg-indigo-100 text-indigo-600','bg-emerald-100 text-emerald-600','bg-violet-100 text-violet-600','bg-rose-100 text-rose-600','bg-amber-100 text-amber-600'];
  const c = colors[(name?.charCodeAt(0)||0) % colors.length];
  return <div className={`w-8 h-8 ${c} rounded-full flex items-center justify-center font-bold shrink-0 text-sm`}>{name?.charAt(0).toUpperCase()}</div>;
}

/* ── Customer combobox ── */
function CustSearch({ customers, value, onChange, onAfterSelect }) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => c.id === value);
  const filtered = q.trim() ? customers.filter(c => c.name.toLowerCase().includes(q.toLowerCase()) || (c.phone&&c.phone.includes(q))).slice(0,12) : customers.slice(0,12);
  useEffect(() => { const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); }; document.addEventListener('mousedown',h); return () => document.removeEventListener('mousedown',h); }, []);
  const select = (c) => { onChange(c?c.id:''); setQ(''); setOpen(false); if (c) onAfterSelect?.(); };
  return (
    <div className="relative" ref={ref}>
      <div className="flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400">
        <input value={open?q:(selected?selected.name:'')} onChange={e=>{setQ(e.target.value);setOpen(true);if(!e.target.value)onChange('');}} onFocus={()=>setOpen(true)} placeholder="Mijoz: ism yoki telefon..." className="flex-1 px-3 py-1.5 text-sm outline-none bg-transparent min-w-0"/>
        {selected && <button onClick={()=>select(null)} className="px-2 text-slate-400 hover:text-red-400 text-lg leading-none">×</button>}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length===0 ? <div className="px-4 py-3 text-sm text-slate-400">Topilmadi</div> : filtered.map(c => (
            <button key={c.id} onMouseDown={()=>select(c)} className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-50 last:border-0 flex items-center justify-between">
              <div><div className="text-sm font-medium text-slate-800">{c.name}</div>{c.phone&&<div className="text-xs text-slate-400">{c.phone}</div>}</div>
              {c.debt_balance>0 && <span className="text-xs text-red-500 font-medium ml-2">Qarz: {fmt(c.debt_balance)}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Product search ── */
function ProdSearch({ products, onSelect, inputRef: externalRef }) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [activeIdx, setActiveIdx] = useState(-1);
  const internalRef = useRef(null);
  const ref = externalRef || internalRef;
  const listRef = useRef(null);

  const list = q.trim()
    ? products.filter(p =>
        p.name.toLowerCase().includes(q.toLowerCase()) ||
        p.sku?.toLowerCase().includes(q.toLowerCase()) ||
        p.barcode?.includes(q)
      ).slice(0, 12)
    : [];

  useEffect(() => {
    if (activeIdx >= 0 && listRef.current) {
      listRef.current.querySelectorAll('button')[activeIdx]?.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIdx]);

  const pick = (p) => { onSelect(p); setQ(''); setActiveIdx(-1); };

  const handleKeyDown = (e) => {
    if (!list.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, list.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); pick(list[activeIdx]); }
    else if (e.key === 'Escape') { setQ(''); setActiveIdx(-1); }
  };

  return (
    <div className="relative">
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"/>
        </svg>
        <input ref={ref} value={q} onChange={e => { setQ(e.target.value); setActiveIdx(-1); }} onKeyDown={handleKeyDown}
          placeholder="Mahsulot qidiring (↑↓ Enter)..." className={`w-full pl-9 ${ic}`}/>
        {q && <button onMouseDown={() => setQ('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>}
      </div>
      {list.length > 0 && (
        <div ref={listRef} className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-lg shadow-xl z-30 overflow-hidden max-h-64 overflow-y-auto">
          {list.map((p, idx) => (
            <button key={p.id} onMouseDown={() => pick(p)}
              className={`w-full text-left px-4 py-2.5 border-b border-slate-100 last:border-0 flex justify-between items-center transition-colors ${idx === activeIdx ? 'bg-indigo-50 ring-1 ring-inset ring-indigo-200' : 'hover:bg-indigo-50'}`}>
              <div><div className="font-medium text-slate-800 text-sm">{p.name}</div><div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div></div>
              <div className="text-right ml-3 shrink-0 text-xs"><div className="font-semibold text-indigo-600">{fmt(p.sale_price)}</div><div className="text-slate-400">Qoldiq: {fmt(p.stock_quantity)}</div></div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   YANGI SOTUV VIEW — POS Interface
══════════════════════════════════════════════════ */
function Lbl({ className = '', t, children }) {
  return (
    <div className={className}>
      {t && <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{t}</div>}
      {children}
    </div>
  );
}

/* ── Sale Create View ── */
function SaleCreateView({ customers, onBack, onSaved }) {
  const { t } = useLang();
  const [products, setProds] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_cache_products'))?.data || []; } catch { return []; }
  });

  useEffect(() => {
    // Fon fonda yangilash — xato bo'lsa toast chiqarmaydi (_silent)
    api.get('/products/pos-list', { _silent: true })
       .then(r => {
         const data = Array.isArray(r.data) ? r.data : (r.data.items || []);
         setProds(data);
         localStorage.setItem('pos_cache_products', JSON.stringify({ ts: Date.now(), data }));
       }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const [cart, setCart] = useState([]);
  // Pre-select default customer from settings
  const [custId, setCust] = useState(() => {
    try {
      const s = JSON.parse(localStorage.getItem('pos_settings') || '{}');
      return s.default_customer_id ? String(s.default_customer_id) : '';
    } catch { return ''; }
  });
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [showPay, setShowPay] = useState(false);
  const [payForm, setPayForm] = useState({ discType: 'amt', discVal: '', cash: '', info: '', payType: 'cash' });
  const [payErr, setPayErr] = useState('');
  const [showPayTypes, setShowPayTypes] = useState(false);
  const [showMuddat, setShowMuddat] = useState(false);
  const [muddatDate, setMuddatDate] = useState('');
  const [pendingPayInfo, setPendingPayInfo] = useState(null);

  const totalNet = cart.reduce((s, c) => s + c.qty_ordered * c.net_cost, 0);

  const calcFinalTotal = () => {
    const d = Number(payForm.discVal) || 0;
    return payForm.discType === 'pct' ? totalNet * (1 - d / 100) : totalNet - d;
  };
  const finalTotal = calcFinalTotal();
  const paid = (Number(payForm.cash) || 0);
  const debt = Math.max(0, finalTotal - paid);
  const change = Math.max(0, paid - finalTotal);

  const doSave = async (paymentInfo = null, shouldPrint = false) => {
    if (!cart.length) { setErr("Kamida bitta mahsulot qo'shing"); return; }
    setSaving(true); setErr(''); setPayErr('');

    // ── Modalni DARHOL yopamiz — foydalanuvchi qotib qolgan ko'rinishni ko'rmaydi
    // Xato bo'lsa quyida qaytadan ochamiz
    setShowPay(false);
    setShowMuddat(false);

    try {
      const discAmt = payForm.discType === 'pct'
        ? totalNet * (Number(payForm.discVal) || 0) / 100
        : (Number(payForm.discVal) || 0);

      const rawPaid = paymentInfo ? paymentInfo.paid : finalTotal;
      const paidAmt = Math.max(0, rawPaid);
      const payType = paidAmt === 0 ? 'debt' : (paymentInfo ? paymentInfo.type : 'cash');

      // Chekni API dan OLDIN print qilish — tez ishlash uchun
      if (shouldPrint) {
        const rSettings = getReceiptSettings();
        const tpl = posSettings.paper === '58mm' ? '58' : posSettings.paper === 'A4' ? 'nak' : '80';
        const cfg = tpl === 'nak' ? (rSettings.nak || {}) : (rSettings['r' + tpl] || rSettings[tpl] || {});
        printReceiptHtml(buildReceiptHtml({
          id: Date.now(), number: Date.now(),
          cashier_name: 'Kassir',
          created_at: new Date().toISOString(),
          total_amount: finalTotal,
          paid_amount: paidAmt,
          discount_amount: discAmt,
          payment_types_array: [{ type: payType, amount: paidAmt }],
          items: cart.map(c => ({
            product_name: c.product_name,
            quantity: c.qty_ordered,
            unit_price: c.unit_price,
            subtotal: c.unit_price * c.qty_ordered,
          })),
        }, tpl, cfg));
      }

      const payload = {
        items: cart.map(c => ({
          product_id: c.product_id,
          quantity:   c.qty_ordered,
          unit_price: c.unit_price,
          discount:   c.discount_type === 'pct'
            ? c.unit_price * c.qty_ordered * (c.discount_val / 100)
            : c.discount_val * c.qty_ordered,
        })),
        payment_type:    payType,
        paid_amount:     paidAmt,
        discount_amount: discAmt,
        note:            note || '',
        customer_id:     custId ? Number(custId) : null,
        debt_due_date:   paymentInfo?.debtDueDate || null,
      };

      if (paymentInfo?.info) {
        payload.note = (payload.note ? payload.note + '\n' : '') + paymentInfo.info;
      }

      // ── OPTIMISTIK UI: Darhol orqaga ketamiz (server javobini KUTMAYMIZ) ──
      setSaving(false);
      setShowPay(false);
      setShowMuddat(false);
      onBack(); // ← 0ms! Foydalanuvchi darhol ro'yxatga qaytadi

      // API ga fon rejimida yuboramiz
      api.post('/sales/', payload)
        .then(() => { onSaved(); })
        .catch((e) => {
          const msg = e.response?.data?.detail || 'Sotuv saqlanmadi!';
          window.alert('\u26A0\uFE0F Sotuv xatosi:\n' + msg);
          onSaved();
        });
    } catch (e) {
      const msg = e.response?.data?.detail || 'Xatolik';
      setPayErr(msg);
      setErr(msg);
      setSaving(false);
      setShowPay(true);
    } finally { setSaving(false); }
  };

  // Called when user clicks "Sotuvni yakunlash" or "Saqlash va chop etish"
  const handlePaySubmit = (shouldPrint = false) => {
    const paidAmt = Math.max(0, Math.round(Number(payForm.cash) || 0));
    const ft = Math.round(finalTotal);
    const debtAmt = Math.max(0, ft - paidAmt);
    const info = { paid: paidAmt, type: payForm.payType, info: payForm.info, shouldPrint };
    if (debtAmt > 0) {
      // Show muddat modal before saving
      setPendingPayInfo(info);
      setMuddatDate('');
      setShowMuddat(true);
    } else {
      doSave(info, shouldPrint);
    }
  };


  const searchRef = useRef(null);
  const qtyRef = useRef(null);
  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('');
  const [price, setPrice] = useState('');
  const [discType, setDiscType] = useState('pct');
  const [discVal, setDiscVal] = useState('0');

  const selectProduct = (p) => {
    setSel(p);
    setPrice(String(Math.round(p.sale_price) || '0'));
    setQty(''); setDiscVal('0'); setDiscType('pct');
    setTimeout(() => { if (qtyRef.current) qtyRef.current.focus(); }, 10);
  };

  const calcNet = (rawPrice, dType, dVal) => {
    const p = Number(rawPrice) || 0;
    const d = Number(dVal) || 0;
    return dType === 'pct' ? p * (1 - d / 100) : p - d;
  };
  const selNet = calcNet(price, discType, discVal);

  const addItem = () => {
    if (!sel || !qty) return;
    if (posSettings.require_customer && !custId) {
      setErr('Avval mijoz tanlang! Nastroykada "Mijoz majburiy" yoqilgan.');
      setTimeout(() => setErr(''), 3500);
      return;
    }
    const base = {
      product_id: sel.id, product_name: sel.name, unit: sel.unit || 'dona',
      unit_price: Number(price) || 0, discount_type: discType, discount_val: Number(discVal) || 0,
      net_cost: selNet,
    };
    setCart(prev => {
      const ex = prev.find(x => x.product_id === sel.id);
      if (ex) return prev.map(x => x.product_id === sel.id ? { ...x, qty_ordered: x.qty_ordered + Number(qty) } : x);
      return [...prev, { ...base, qty_ordered: Number(qty) }];
    });
    setSel(null); setQty(''); setPrice(''); setDiscVal('0');
    setTimeout(() => { if (searchRef.current) searchRef.current.focus(); }, 10);
  };

  const updCart = (i, field, val) => setCart(prev => prev.map((x, idx) => idx === i ? { ...x, [field]: val, net_cost: calcNet(field==='unit_price'?val:x.unit_price, field==='discount_type'?val:x.discount_type, field==='discount_val'?val:x.discount_val) } : x));

  // POS Settings (stored in localStorage)
  const [showSettings, setShowSettings] = useState(false);
  const [posSettings, setPosSettings] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_settings') || '{}'); } catch { return {}; }
  });
  const savePosSettings = (updates) => {
    const next = { ...posSettings, ...updates };
    setPosSettings(next);
    localStorage.setItem('pos_settings', JSON.stringify(next));
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <div className="flex items-center gap-4 px-6 py-4 bg-white border-b border-slate-100 shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-2 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 font-semibold">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200" />
        <h1 className="text-xl font-bold text-slate-800">Yangi sotuv</h1>
        <div className="flex-1 flex gap-3 ml-4 items-center">
          <div className="w-64">
            <CustSearch customers={customers} value={custId} onChange={setCust}
              onAfterSelect={() => setTimeout(() => searchRef.current?.focus(), 50)}
              placeholder={posSettings.require_customer ? 'Mijoz KERAK  ★...' : 'Mijoz tanlang...'} />
          </div>
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Izoh (ixtiyoriy)..." className="flex-1 max-w-sm border border-slate-200 rounded-xl px-4 text-sm focus:ring-2 focus:ring-indigo-400 outline-none" />
        </div>
        {/* Settings Gear */}
        <button onClick={() => setShowSettings(s => !s)} title="Nastroykalar"
          className={`ml-auto w-10 h-10 rounded-xl flex items-center justify-center border transition-all shrink-0 ${showSettings ? 'bg-indigo-600 text-white border-indigo-600 shadow-md' : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-indigo-50 hover:text-indigo-600'}`}>
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
      </div>

      {/* ─── Settings Modal (Premium) ─── */}
      {showSettings && (
        <div className="fixed inset-0 z-70 flex items-center justify-center p-4" style={{background:'rgba(2,6,23,0.72)', backdropFilter:'blur(8px)'}} onClick={() => setShowSettings(false)}>
          <div className="w-full max-w-xl overflow-hidden rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200"
            style={{background:'linear-gradient(135deg,#1e293b 0%,#0f172a 100%)', border:'1px solid rgba(99,102,241,0.25)'}}
            onClick={e => e.stopPropagation()}>

            {/* Header */}
            <div className="flex items-center justify-between px-6 pt-6 pb-4" style={{borderBottom:'1px solid rgba(255,255,255,0.07)'}}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{background:'linear-gradient(135deg,#6366f1,#4f46e5)', boxShadow:'0 4px 16px rgba(99,102,241,0.4)'}}>
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-tight">POS Nastroykalar</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Sozlamalar avtomatik saqlanadi</p>
                </div>
              </div>
              <button onClick={() => setShowSettings(false)}
                className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-400 hover:text-white transition-colors"
                style={{background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.1)'}}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-3">

              {/* Default Customer */}
              <div className="rounded-xl px-4 py-3.5" style={{background:'rgba(99,102,241,0.12)', border:'1px solid rgba(99,102,241,0.2)'}}>
                <div className="flex items-center gap-2 mb-2">
                  <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                  <span className="text-xs font-bold text-indigo-300 uppercase tracking-widest">Standart mijoz</span>
                </div>
                <select
                  value={posSettings.default_customer_id ?? ''}
                  onChange={e => {
                    const val = e.target.value;
                    savePosSettings({ default_customer_id: val ? Number(val) : null });
                    setCust(val);
                  }}
                  className="w-full rounded-xl px-3 py-2.5 text-sm font-medium text-white outline-none focus:ring-2 focus:ring-indigo-500"
                  style={{background:'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.12)'}}>
                  <option value="" style={{background:'#1e293b'}}>— Tanlanmagan —</option>
                  {customers.map(c => <option key={c.id} value={c.id} style={{background:'#1e293b'}}>{c.name} {c.phone ? `(${c.phone})` : ''}</option>)}
                </select>
                <p className="text-xs text-slate-500 mt-1.5">Tanlasangiz yangi sotuv ochilganda avtomat tanlanib turadi</p>
              </div>

              {/* Toggles */}
              <div className="space-y-1">
                {[
                  { key: 'require_customer', label: 'Mijoz majburiy',     sub: "Mijoz tanlanmasa mahsulot qo'shilmaydi",      color: '#f59e0b' },
                  { key: 'allow_negative',   label: 'Minusga sotish',     sub: "Qoldiq 0 bo'lsa ham sotishga ruxsat beradi",  color: '#ef4444' },
                  { key: 'always_wholesale', label: 'Ulgurji narx rejimi', sub: 'Har doim ulgurji narx bo\u2019yicha sotuv', color: '#10b981' },
                  { key: 'autoPrint',        label: 'Avtomatik chop etish', sub: 'Sotuv tasdiqlanganda chek avtomatik chiqadi', color: '#6366f1' },
                ].map(opt => (
                  <div key={opt.key}
                    className="flex items-center justify-between px-4 py-3 rounded-xl cursor-pointer transition-all"
                    style={{background: posSettings[opt.key] ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.07)'}}
                    onClick={() => savePosSettings({ [opt.key]: !posSettings[opt.key] })}>
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{background: posSettings[opt.key] ? opt.color : '#475569'}} />
                        <span className="text-sm font-semibold text-white">{opt.label}</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5 ml-4">{opt.sub}</p>
                    </div>
                    <div className={`w-11 h-6 rounded-full flex items-center px-0.5 transition-all duration-200 shrink-0 ml-4`}
                      style={{background: posSettings[opt.key] ? opt.color : 'rgba(255,255,255,0.1)'}}>
                      <div className={`w-5 h-5 rounded-full bg-white shadow transition-transform duration-200 ${posSettings[opt.key] ? 'translate-x-5' : 'translate-x-0'}`} />
                    </div>
                  </div>
                ))}
              </div>

              {/* Paper size — only visible when autoPrint is on */}
              {posSettings.autoPrint && (
                <div className="rounded-xl px-4 py-3.5" style={{background:'rgba(99,102,241,0.08)', border:'1px solid rgba(99,102,241,0.2)'}}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-white">Chek o'lchami</div>
                      <div className="text-xs text-slate-500 mt-0.5">Chop etiladigan qog'oz kengligi</div>
                    </div>
                    <div className="flex gap-1.5">
                      {['58mm','80mm','A4'].map(sz => (
                        <button key={sz}
                          onClick={() => savePosSettings({ paper: sz })}
                          className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
                          style={{
                            background: (posSettings.paper || '80mm') === sz ? '#6366f1' : 'rgba(255,255,255,0.08)',
                            color: (posSettings.paper || '80mm') === sz ? '#fff' : '#94a3b8',
                            border: '1px solid ' + ((posSettings.paper || '80mm') === sz ? '#6366f1' : 'rgba(255,255,255,0.1)'),
                          }}>
                          {sz}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Max Discount */}
              <div className="rounded-xl px-4 py-3.5" style={{background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.07)'}}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold text-white">Maksimal chegirma</div>
                    <div className="text-xs text-slate-500 mt-0.5">Bo'sh qoldirsangiz chegirma cheksiz bo'ladi</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="number" min="0" max="100"
                      value={posSettings.max_discount ?? ''}
                      placeholder="—"
                      onClick={e => e.stopPropagation()}
                      onChange={e => savePosSettings({ max_discount: e.target.value === '' ? null : Number(e.target.value) })}
                      className="w-20 text-center rounded-xl px-3 py-2 text-sm font-bold text-white outline-none focus:ring-2 focus:ring-indigo-500"
                      style={{background:'rgba(255,255,255,0.1)', border:'1px solid rgba(255,255,255,0.15)'}} />
                    <span className="text-slate-400 font-bold text-sm">%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 pb-6 pt-2 flex justify-end">
              <button onClick={() => setShowSettings(false)}
                className="px-6 py-2.5 text-sm font-bold text-white rounded-xl transition-all hover:opacity-90 active:scale-95"
                style={{background:'linear-gradient(135deg,#6366f1,#4f46e5)', boxShadow:'0 4px 16px rgba(99,102,241,0.35)'}}>
                Yopish
              </button>
            </div>
          </div>
        </div>
      )}


      <div className="flex flex-1 overflow-hidden">
        <div className="w-[500px] border-r border-slate-100 p-6 flex flex-col gap-6 overflow-y-auto bg-white shrink-0">
          <Lbl t="Mahsulot qidirish">
            <ProdSearch products={products} onSelect={selectProduct} inputRef={searchRef} />
          </Lbl>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
                  {sel.name.slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-base truncate">{sel.name}</div>
                  <div className="text-sm text-slate-600 mt-1">Qoldiq: <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit||'dona'}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2 border-t border-indigo-100/50">
                <Lbl t="Soni*">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm">
                    <input type="number" min="1" step="any" value={qty} onChange={e=>setQty(e.target.value)} ref={qtyRef} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 w-full py-2.5 px-3 text-lg font-bold text-center outline-none" placeholder="0" />
                    <div className="px-3 py-2.5 bg-slate-50 border-l border-slate-200 text-slate-500 font-semibold text-sm">{sel.unit||'dona'}</div>
                  </div>
                </Lbl>
                <Lbl t="Sotish narxi*">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm">
                    <input type="number" min="0" value={price} onChange={e=>setPrice(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 w-full py-2.5 px-3 text-lg font-bold text-center outline-none" />
                  </div>
                </Lbl>
                <Lbl t="Chegirma" className="col-span-2">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm h-11">
                    <input type="number" min="0" value={discVal} onChange={e=>setDiscVal(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 py-2 px-3 text-base font-bold text-center outline-none" />
                    <button onClick={()=>setDiscType(t=>t==='pct'?'amt':'pct')} className={`w-14 h-full flex items-center justify-center font-bold border-l border-slate-200 transition-colors ${discType==='pct'?'bg-amber-100 text-amber-700':'bg-violet-100 text-violet-700'}`}>{discType==='pct'?'%':"so'm"}</button>
                  </div>
                </Lbl>
              </div>

              <div className="flex items-end justify-between pt-4 pb-2">
                <div className="text-sm text-slate-500 font-medium">Sof narx:</div>
                <div className="text-xl font-black text-emerald-600">{fmt(Math.round(selNet))} UZS</div>
              </div>
              <button onClick={addItem} disabled={!qty || Number(qty)<=0} className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl transition-all shadow-md active:scale-95">
                Ro'yxatga qo'shish
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-300 gap-3">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              <p>Mahsulot tanlang</p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {cart.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2"><svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg><p>Mahsulot qo'shing</p></div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 w-8">№</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product') || 'Mahsulot'}</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-24">Soni</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-32">Narxi</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-28">Chegirma</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-32">Sof narx</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase w-32">{t('admin.dict.total') || 'Jami'}</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cart.map((it, i) => (
                  <tr key={i} className="hover:bg-slate-50 group">
                    <td className="px-4 py-3 text-slate-400 text-xs">{i+1}</td>
                    <td className="px-3 py-3">
                      <div className="font-semibold text-slate-800">{it.product_name}</div>
                      <div className="text-xs text-slate-400">{it.unit}</div>
                    </td>
                    <td className="px-3 py-3 text-center">
                      <input type="number" min="0.1" step="any" value={it.qty_ordered} onChange={e=>updCart(i,'qty_ordered',Number(e.target.value))} className="w-16 text-center border border-slate-200 rounded-lg py-1.5 focus:ring-2 focus:ring-indigo-500 font-bold" />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <input type="number" min="0" value={it.unit_price} onChange={e=>updCart(i,'unit_price',e.target.value)} className="w-24 text-right border border-slate-200 rounded-lg py-1.5 px-2 focus:ring-2 focus:ring-indigo-500" />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <input type="number" min="0" value={it.discount_val} onChange={e=>updCart(i,'discount_val',e.target.value)} className="w-16 text-center border border-slate-200 rounded-lg py-1.5 focus:ring-2 focus:ring-indigo-500" />
                        <button onClick={()=>updCart(i,'discount_type',it.discount_type==='pct'?'amt':'pct')} className={`text-[10px] font-bold px-1.5 py-1.5 rounded-md transition-colors ${it.discount_type==='pct'?'bg-amber-100 text-amber-700':'bg-violet-100 text-violet-700'}`}>{it.discount_type==='pct'?'%':"so'm"}</button>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right font-bold text-emerald-600">{fmt(Math.round(it.net_cost))}</td>
                    <td className="px-4 py-3 text-right font-black text-slate-800">{fmt(Math.round(it.net_cost * it.qty_ordered))}</td>
                    <td className="pr-3">
                      <button onClick={()=>setCart(p=>p.filter((_,idx)=>idx!==i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white shrink-0">
        <div className="flex gap-3">
          <Btn v="ghost" onClick={onBack} disabled={saving}>{t('common.cancel')}</Btn>
          {err && <span className="text-red-500 font-bold bg-red-50 px-3 py-1.5 rounded-xl border border-red-100">{err}</span>}
        </div>
        <div className="flex gap-3 items-center">
          {cart.length > 0 && <span className="mr-3 font-bold text-slate-500">Jami summasi: <span className="text-slate-800 text-lg ml-1">{fmt(totalNet)} UZS</span></span>}
          {saving ? (
            <div className="px-8 py-3 bg-blue-600 text-white rounded-xl font-bold shadow-sm flex items-center gap-2.5 min-w-[130px] justify-center">
              <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
              </svg>
              Saqlanmoqda...
            </div>
          ) : (
            <button onClick={()=>{ if(!cart.length){setErr("Savat bo'sh"); return;} setErr(''); setShowPay(true); }} className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold shadow-sm flex items-center gap-2">
              To'lov
            </button>
          )}
        </div>
      </div>

      {showPay && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-full animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h2 className="text-lg font-bold text-slate-800 tracking-tight">
                Kassadan to'lov
                <span className="text-blue-500 font-medium text-base ml-2">{new Date().toLocaleString('uz-UZ').replace(',', '')}</span>
              </h2>
              <button onClick={()=>{setShowPay(false);setPayErr('');setShowPayTypes(false);}} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition-colors bg-slate-50 border border-slate-200">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="p-6 space-y-5 overflow-y-auto bg-slate-50/50">
              {/* Chegirma + Kassa row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex items-center gap-3 text-xs font-bold text-slate-500 uppercase tracking-widest">
                    Chegirma (Savatga)
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 normal-case font-medium hover:text-slate-700">
                      <input type="radio" checked={payForm.discType==='amt'} onChange={()=>setPayForm(p=>({...p,discType:'amt'}))} className="w-3.5 h-3.5 text-blue-600" /> Foizsiz
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 normal-case font-medium hover:text-slate-700">
                      <input type="radio" checked={payForm.discType==='pct'} onChange={()=>setPayForm(p=>({...p,discType:'pct'}))} className="w-3.5 h-3.5 text-blue-600" /> %
                    </label>
                  </div>
                  <div className="flex h-12 bg-white rounded-xl border-2 border-slate-200 focus-within:border-blue-500 overflow-hidden shadow-sm">
                    <input type="number" value={payForm.discVal} onChange={e=>setPayForm(p=>({...p,discVal:e.target.value}))} className="flex-1 border-none bg-transparent px-4 text-lg font-bold outline-none" placeholder="0" />
                    <div className="bg-slate-50 px-4 flex items-center border-l border-slate-100 text-slate-500 text-sm font-bold">
                      {payForm.discType === 'pct' ? '%' : 'UZS'}
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-widest">{t('admin.dict.pos') || 'Kassa'}</label>
                  <select className="w-full h-12 bg-white border-2 border-slate-200 rounded-xl px-4 font-bold shadow-sm outline-none text-sm">
                    <option value="1">KASSA</option>
                  </select>
                </div>
              </div>

              {/* Payment row — clickable type + amount */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-500 uppercase tracking-widest">To'lov qiymati (so'm)</label>
                <div className="flex gap-2 h-14 items-center">
                  {/* Clickable payment-type button */}
                  <button type="button" onClick={() => setShowPayTypes(s => !s)}
                    className={`flex items-center gap-2 h-full px-4 rounded-xl border-2 font-bold text-sm transition-all whitespace-nowrap shadow-sm
                      ${showPayTypes ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200 hover:border-blue-400 hover:bg-blue-50'}`}>
                    {[
                      {v:'cash',l:'Naqd'},{v:'uzcard',l:'Uzcard'},{v:'humo',l:'Humo'},
                      {v:'bank',l:"Bank o'tkazmasi"},{v:'click',l:'Click'},{v:'payme',l:'Payme'},
                      {v:'visa',l:'Visa'},{v:'uzum',l:'Uzum'},{v:'mixed',l:'Aralash'},{v:'debt',l:'Qarzga'},
                    ].find(t => t.v === payForm.payType)?.l || 'Naqd'}
                    <svg className={`w-3 h-3 transition-transform ${showPayTypes ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7"/></svg>
                  </button>
                  {/* Amount input */}
                  <div className="flex flex-1 items-center h-full rounded-xl focus-within:ring-4 focus-within:ring-blue-500/20 focus-within:border-blue-500 border-2 border-slate-200 bg-white shadow-sm overflow-hidden transition-all">
                    <input type="number" min="0" autoFocus value={payForm.cash}
                      onChange={e => { setPayErr(''); setPayForm(p=>({...p, cash: e.target.value})); }}
                      className="flex-1 w-full h-full border-none px-4 text-2xl font-black text-slate-800 outline-none bg-transparent" placeholder="0" />
                    <div className="px-4 flex items-center text-blue-600 text-sm font-bold h-full border-l border-slate-100 bg-slate-50">UZS</div>
                    <button type="button" onClick={()=>setPayForm(p=>({...p, cash: String(Math.round(finalTotal))}))}
                      className="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-5 h-full border-l border-slate-200 text-sm whitespace-nowrap transition-colors">
                      Umumiy Summa
                    </button>
                  </div>
                </div>

                {/* Payment type panel — shown when button clicked */}
                {showPayTypes && (
                  <div className="bg-white border-2 border-blue-100 rounded-xl p-3 grid grid-cols-5 gap-1.5 shadow-lg">
                    {[
                      {v:'cash',l:'Naqd'},{v:'uzcard',l:'Uzcard'},{v:'humo',l:'Humo'},
                      {v:'bank',l:"Bank o'tkazmasi"},{v:'click',l:'Click'},
                      {v:'payme',l:'Payme'},{v:'visa',l:'Visa'},{v:'uzum',l:'Uzum'},
                      {v:'mixed',l:'Aralash'},{v:'debt',l:'Qarzga'},
                    ].map(t => (
                      <button key={t.v} type="button" onClick={() => {
                        setPayForm(p => ({...p, payType: t.v, cash: t.v === 'debt' ? '0' : String(Math.round(finalTotal))}));
                        setShowPayTypes(false);
                      }}
                        className={`px-2 py-2.5 rounded-lg border font-bold text-xs transition-all ${
                          payForm.payType === t.v ? 'bg-blue-600 text-white border-blue-600' : 'bg-slate-50 text-slate-600 border-slate-200 hover:border-blue-300 hover:bg-blue-50'
                        }`}>{t.l}</button>
                    ))}
                  </div>
                )}
              </div>

              {/* Info textarea */}
              <textarea rows="2" value={payForm.info} onChange={e=>setPayForm(p=>({...p,info:e.target.value}))}
                className="w-full border-2 border-slate-200 rounded-xl p-4 text-sm resize-none focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 bg-white" placeholder="Ma'lumot..."/>

              {/* Summary */}
              <div className="flex flex-col items-end gap-2.5 pt-4 border-t border-slate-200">
                <div className="flex items-center justify-between w-72">
                  <span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">Umumiy summa:</span>
                  <span className="font-black text-emerald-600 bg-emerald-50 px-3 py-1 rounded-xl text-lg">{fmt(Math.round(finalTotal))}</span>
                </div>
                <div className="flex items-center justify-between w-72">
                  <span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">To'lov:</span>
                  <span className="font-bold text-blue-700 bg-blue-100/50 border border-blue-200 px-3 py-1.5 rounded-xl">{fmt(Math.max(0, Math.round(paid)))} UZS</span>
                </div>
                {debt > 0 && (
                  <div className="flex items-center justify-between w-72 animate-in slide-in-from-right-2">
                    <span className="text-red-500 font-semibold text-sm uppercase tracking-wide">Qarzga:</span>
                    <span className="font-bold text-red-600 bg-red-50 border border-red-200 px-3 py-1.5 rounded-xl">{fmt(Math.round(debt))}</span>
                  </div>
                )}
                {change > 0 && (
                  <div className="flex items-center justify-between w-72 animate-in slide-in-from-right-2">
                    <span className="text-amber-600 font-semibold text-sm uppercase tracking-wide">Do'kon qarzi:</span>
                    <span className="font-bold text-amber-700 bg-amber-50 border border-amber-200 px-3 py-1.5 rounded-xl">{fmt(Math.round(change))} UZS</span>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 bg-white rounded-b-2xl">
              {payErr && <div className="flex-1 px-4 py-2.5 bg-red-50 border border-red-200 text-red-600 text-sm font-semibold rounded-xl">{payErr}</div>}
              <button type="button" onClick={()=>{setShowPay(false);setPayErr('');setShowPayTypes(false);}} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-bold hover:bg-slate-50 transition-all text-sm">{t('common.cancel')}</button>
              {posSettings.autoPrint ? (
                <button type="button" disabled={saving}
                  onClick={() => handlePaySubmit(true)}
                  className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-black text-sm shadow-md flex items-center gap-2 transition-all active:scale-95">
                  {saving ? '...' : <><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>Sotuvni yakunlash</>}
                </button>
              ) : (
                <>
                  <button type="button" disabled={saving}
                    onClick={() => handlePaySubmit(true)}
                    className="px-5 py-3 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed text-indigo-700 border border-indigo-200 rounded-xl font-bold text-sm flex items-center gap-2 transition-all active:scale-95">
                    {saving ? '...' : <><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6v-8z"/></svg>Saqlash va chop etish</>}
                  </button>
                  <button type="button" disabled={saving}
                    onClick={() => handlePaySubmit(false)}
                    className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-black text-sm shadow-md flex items-center gap-2 transition-all active:scale-95">
                    {saving ? '...' : <><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>Sotuvni saqlash</>}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Muddat modal ── */}
      {showMuddat && (
        <div className="fixed inset-0 z-70 flex items-center justify-center bg-slate-900/70 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-slate-100 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-800">Qarz muddatini belgilang</h3>
                <p className="text-sm text-slate-500 mt-0.5">
                  Qarz miqdori: <strong className="text-red-600">{fmt(Math.round(Math.max(0, finalTotal - (pendingPayInfo?.paid || 0))))} UZS</strong>
                </p>
              </div>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2 block">To'lov muddati (ixtiyoriy)</label>
                <input type="date" value={muddatDate} min={today()}
                  onChange={e => setMuddatDate(e.target.value)}
                  className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 text-sm font-semibold text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" />
              </div>
              {payErr && <div className="px-4 py-2.5 bg-red-50 border border-red-200 text-red-600 text-sm font-semibold rounded-xl">{payErr}</div>}
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => { setShowMuddat(false); setPendingPayInfo(null); }}
                  className="flex-1 py-3 rounded-xl border border-slate-200 text-slate-600 font-bold hover:bg-slate-50 transition-all text-sm">
                  Bekor
                </button>
                <button type="button" disabled={saving}
                  onClick={() => { setShowMuddat(false); doSave({ ...pendingPayInfo, debtDueDate: muddatDate || null }, pendingPayInfo?.shouldPrint); }}
                  className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl font-black text-sm shadow-md transition-all active:scale-95">
                  {saving ? '...' : 'Qarzga saqlash'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function SaleDetailModal({ saleId, onClose, onEdit, onDelete, onPrint }) {
  const { t } = useLang();
  const [sale, setSale] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/sales/${saleId}`)
      .then(r => setSale(r.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
      .finally(() => setLoading(false));
  }, [saleId]);

  if (loading) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl p-10 shadow-2xl">
        <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto"/>
      </div>
    </div>
  );
  if (!sale) return null;

  const debt = Number(sale.total_amount) - Number(sale.paid_amount);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h3 className="text-lg font-bold text-slate-800 font-mono">{sale.number}</h3>
            <p className="text-xs text-slate-400 mt-0.5">{sale.cashier_name} · {new Date(sale.created_at).toLocaleString('uz-UZ')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onPrint} title="Chek chop" className="p-2 text-indigo-500 hover:bg-indigo-50 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
            </button>
            {/* Excel single sale */}
            <button onClick={() => exportSaleExcel(sale)} title="Excel yuklash" className="p-2 text-emerald-600 hover:bg-emerald-50 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/><path d="M14 2v6h6"/><path d="M8 13h2m0 0h2m-2 0v4m4-4h-2m0 0v4" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round"/></svg>
            </button>
            {/* PDF single sale */}
            <button onClick={() => exportSalePDF(sale)} title="PDF yuklash" className="p-2 text-red-500 hover:bg-red-50 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/><path d="M14 2v6h6"/></svg>
            </button>
            <button onClick={onEdit} title="Tahrirlash" className="p-2 text-slate-500 hover:bg-slate-100 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
            </button>
            <button onClick={onDelete} title="O'chirish" className="p-2 text-red-400 hover:bg-red-50 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
            </button>
            <button onClick={onClose} className="p-2 text-slate-400 hover:bg-slate-100 rounded-xl transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
        </div>

        {/* Badges */}
        <div className="flex items-center gap-2 px-6 py-3 border-b border-slate-50">
          <Badge meta={saleMeta} val={sale.status}/>
          <Badge meta={payMeta} val={sale.payment_type}/>
          {sale.note && <span className="text-xs text-slate-500 bg-slate-50 px-2 py-1 rounded-lg">📝 {sale.note}</span>}
        </div>

        {/* Items table */}
        <div className="flex-1 overflow-y-auto">
          <table className="min-w-full">
            <thead className="bg-slate-50 sticky top-0">
              <tr>
                {['#','Mahsulot','Soni','Narx','Chegirma','Jami'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {sale.items.map((item, i) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-xs text-slate-400">{i+1}</td>
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-slate-800">{item.product_name}</div>
                    <div className="text-xs text-slate-400 font-mono">ID:{item.product_id}</div>
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-slate-700">{Number(item.quantity)}</td>
                  <td className="px-4 py-3 text-sm text-slate-600 font-mono">{fmt(item.unit_price)}</td>
                  <td className="px-4 py-3 text-sm text-amber-600 font-mono">{Number(item.discount) > 0 ? `-${fmt(item.discount)}` : '—'}</td>
                  <td className="px-4 py-3 text-sm font-bold text-indigo-700 font-mono">{fmt(item.subtotal)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer totals */}
        <div className="border-t border-slate-100 px-6 py-4 space-y-1.5 bg-slate-50 rounded-b-2xl">
          <div className="flex justify-between text-sm text-slate-500"><span>Mahsulotlar ({sale.items.length} ta)</span><span className="font-mono">{fmt(Number(sale.total_amount) + Number(sale.discount_amount))} so'm</span></div>
          {Number(sale.discount_amount) > 0 && <div className="flex justify-between text-sm text-amber-600 font-semibold"><span>Chegirma</span><span className="font-mono">−{fmt(sale.discount_amount)} so'm</span></div>}
          <div className="flex justify-between text-base font-bold text-slate-800 border-t border-slate-200 pt-1.5"><span>{t('admin.dict.th_total') || 'JAMI'}</span><span className="font-mono text-indigo-700">{fmt(sale.total_amount)} so'm</span></div>
          <div className="flex justify-between text-sm text-emerald-600 font-semibold"><span>To'langan</span><span className="font-mono">{fmt(sale.paid_amount)} so'm</span></div>
          {debt > 0 && <div className="flex justify-between text-sm text-red-500 font-bold"><span>{t('admin.dict.debt') || 'Qarz'}</span><span className="font-mono">{fmt(debt)} so'm</span></div>}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   SALE EDIT MODAL
══════════════════════════════════════════════════ */
function SaleEditModal({ sale, onClose, onSaved }) {
  const { t } = useLang();
  const [form, setForm] = useState({
    status: sale.status,
    note: sale.note || '',
    paid_amount: String(sale.paid_amount),
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const handleSave = async () => {
    setSaving(true); setErr('');
    try {
      await api.put(`/sales/${sale.id}`, {
        status: form.status,
        note: form.note || null,
        paid_amount: Number(form.paid_amount),
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">Sotuvni tahrirlash</h3>
          <button onClick={onClose} className="p-2 text-slate-400 hover:bg-slate-100 rounded-xl"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg></button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{t('admin.dict.status') || 'Holat'}</div>
            <div className="flex gap-2">
              {Object.entries(saleMeta).map(([v, m]) => (
                <button key={v} onClick={() => setForm(f => ({...f, status: v}))}
                  className={`flex-1 py-2 rounded-xl border text-xs font-semibold transition-all ${form.status === v ? `${m.c} border-transparent` : 'border-slate-200 text-slate-500 hover:border-slate-300'}`}>
                  {m.l}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">To'lov miqdori (so'm)</div>
            <input type="number" className={inputCls} value={form.paid_amount} onChange={e => setForm(f => ({...f, paid_amount: e.target.value}))}/>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{t('admin.dict.comment') || 'Izoh'}</div>
            <textarea rows={2} className={inputCls} value={form.note} onChange={e => setForm(f => ({...f, note: e.target.value}))} placeholder="Izoh..."/>
          </div>
          {err && <div className="px-3 py-2 bg-red-50 text-red-600 text-sm rounded-xl border border-red-100">{err}</div>}
          <div className="flex gap-3 pt-1">
            <button onClick={onClose} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-semibold rounded-xl hover:bg-slate-50">{t('common.cancel')}</button>
            <button onClick={handleSave} disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl">{saving ? '...' : 'Saqlash'}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   RECEIPT HTML BUILDER (MOVED TO utils/receiptBuilder.js)
══════════════════════════════════════════════════ */

/* ══════════════════════════════════════════════════
   PRINT INTO SAME-WINDOW IFRAME
══════════════════════════════════════════════════ */
function printWithIframe(html) {
  const old = document.getElementById('__receipt_iframe__');
  if (old) old.remove();
  const iframe = document.createElement('iframe');
  iframe.id = '__receipt_iframe__';
  iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;border:none;';
  document.body.appendChild(iframe);
  const doc = iframe.contentWindow.document;
  doc.open(); doc.write(html); doc.close();
  setTimeout(() => {
    try {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    } catch (e) {
      console.error("Iframe print error:", e);
    }
  }, 50);
}

/* ══════════════════════════════════════════════════
   PRINT PICKER MODAL
══════════════════════════════════════════════════ */
function PrintPickerModal({ sale, onClose }) {
  const { t } = useLang();
  const settings = getReceiptSettings();
  const templates = [
    { id: '58', icon: '🧾', label: 'Chek 58mm', desc: 'Kichik termal printer', cfg: settings.r58 || {} },
    { id: '80', icon: '🧾', label: 'Chek 80mm', desc: 'Standart termal printer', cfg: settings.r80 || {} },
    { id: 'nak', icon: '📄', label: 'Nakladnoy A4', desc: "Katta format hujjat", cfg: settings.nak || {} },
  ];

  const handlePrint = (tpl) => {
    const tmpl = templates.find(t => t.id === tpl);
    const html = buildReceiptHtml(sale, tpl, tmpl.cfg);
    printWithIframe(html);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-70 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h3 className="text-base font-bold text-slate-800">Chop etish shabloni</h3>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{sale.number}</p>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:bg-slate-100 rounded-xl">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        {/* Template cards */}
        <div className="p-5 space-y-3">
          <p className="text-xs text-slate-500 mb-1">Sozlamalar → Chek shablonlari bo'limida tahrirlashingiz mumkin</p>
          {templates.map(t => {
            const company = t.cfg.company || t.cfg.director || '';
            const configured = !!company;
            return (
              <button key={t.id} onClick={() => handlePrint(t.id)}
                className="w-full flex items-center gap-4 px-4 py-3.5 bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-300 rounded-xl transition-all group text-left">
                <div className="w-10 h-10 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-xl shrink-0 shadow-sm group-hover:border-indigo-300">
                  {t.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800 text-sm">{t.label}</div>
                  <div className="text-xs text-slate-400">{t.desc}</div>
                  {configured && <div className="text-xs text-indigo-600 font-medium mt-0.5">✓ {company}</div>}
                  {!configured && <div className="text-xs text-amber-500 mt-0.5">⚠ Sozlanmagan (standart)</div>}
                </div>
                <svg className="w-4 h-4 text-slate-300 group-hover:text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
                </svg>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════
   EXCEL EXPORT (SheetJS CDN) — settings-aware
══════════════════════════════════════════════════ */
function exportExcel(sales) {
  const loadXLSX = () => new Promise((res, rej) => {
    if (window.XLSX) { res(window.XLSX); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
    s.onload = () => res(window.XLSX);
    s.onerror = rej;
    document.head.appendChild(s);
  });

  // Get company from settings (r58 or r80 whichever is set)
  const cfg = getReceiptSettings();
  const company = cfg.r58?.company || cfg.r80?.company || '';
  const date = new Date().toISOString().slice(0, 10);

  loadXLSX().then(XLSX => {
    const wb = XLSX.utils.book_new();

    // Title rows
    const titleRows = [];
    if (company) titleRows.push([company]);
    titleRows.push([`Sotuvlar hisoboti — ${new Date().toLocaleDateString('uz-UZ')}`]);
    titleRows.push([]);  // blank row

    const dataRows = sales.map(s => ({
      'Raqam': s.number,
      'Kassir': s.cashier_name,
      'Miqdor (ta)': s.items_count,
      "Jami (so'm)": Number(s.total_amount),
      "To'langan (so'm)": Number(s.paid_amount),
      "Qarz (so'm)": Number(s.total_amount) - Number(s.paid_amount),
      "To'lov turi": payMeta[s.payment_type]?.l || s.payment_type,
      'Holat': saleMeta[s.status]?.l || s.status,
      'Sana': new Date(s.created_at).toLocaleString('uz-UZ'),
    }));

    // Build sheet with title then data
    const ws = XLSX.utils.aoa_to_sheet(titleRows);
    XLSX.utils.sheet_add_json(ws, dataRows, { origin: titleRows.length });

    // Bold title
    if (!ws['!merges']) ws['!merges'] = [];
    ws['!merges'].push({ s: { r: 0, c: 0 }, e: { r: 0, c: 8 } });

    // Column widths
    ws['!cols'] = [16,14,10,14,14,12,10,10,18].map(w => ({ wch: w }));

    XLSX.utils.book_append_sheet(wb, ws, 'Sotuvlar');

    // Summary sheet
    const total = sales.reduce((s, r) => s + Number(r.total_amount), 0);
    const paid  = sales.reduce((s, r) => s + Number(r.paid_amount), 0);
    const summaryData = [
      ['Ko\'rsatkich', 'Qiymat'],
      ['Jami sotuvlar', sales.length],
      ["Jami summa (so'm)", total],
      ["To'langan (so'm)", paid],
      ["Qarz (so'm)", total - paid],
    ];
    const ws2 = XLSX.utils.aoa_to_sheet(summaryData);
    ws2['!cols'] = [{ wch: 22 }, { wch: 16 }];
    XLSX.utils.book_append_sheet(wb, ws2, 'Xulosa');

    XLSX.writeFile(wb, `sotuvlar_${date}.xlsx`);
  }).catch(() => alert('Excel kutubxona yuklanmadi'));
}

/* ══════════════════════════════════════════════════
   PDF EXPORT (jsPDF CDN) — settings-aware
══════════════════════════════════════════════════ */
function exportPDF(sales) {
  const loadJsPDF = () => new Promise((res, rej) => {
    if (window.jspdf) { res(window.jspdf.jsPDF); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
    s.onload = () => {
      const s2 = document.createElement('script');
      s2.src = 'https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.2/dist/jspdf.plugin.autotable.min.js';
      s2.onload = () => res(window.jspdf.jsPDF);
      s2.onerror = rej;
      document.head.appendChild(s2);
    };
    s.onerror = rej;
    document.head.appendChild(s);
  });

  const cfg = getReceiptSettings();
  const company = cfg.r58?.company || cfg.r80?.company || '';

  loadJsPDF().then(JsPDF => {
    const doc = new JsPDF({ orientation: 'landscape' });
    let y = 14;
    if (company) {
      doc.setFontSize(16); doc.setFont(undefined, 'bold');
      doc.text(company, 14, y); y += 8;
    }
    doc.setFontSize(11); doc.setFont(undefined, 'normal');
    doc.text(`Sotuvlar hisoboti — ${new Date().toLocaleDateString('uz-UZ')}`, 14, y); y += 4;

    doc.autoTable({
      startY: y + 4,
      head: [['Raqam','Kassir','Miqdor','Jami',"To'langan",'Qarz',"To'lov",'Holat','Sana']],
      body: sales.map(s => [
        s.number, s.cashier_name, s.items_count + ' ta',
        Number(s.total_amount).toLocaleString('uz-UZ'),
        Number(s.paid_amount).toLocaleString('uz-UZ'),
        (Number(s.total_amount) - Number(s.paid_amount)).toLocaleString('uz-UZ'),
        payMeta[s.payment_type]?.l || s.payment_type,
        saleMeta[s.status]?.l || s.status,
        new Date(s.created_at).toLocaleDateString('uz-UZ'),
      ]),
      styles: { fontSize: 8, cellPadding: 2.5 },
      headStyles: { fillColor: [79, 70, 229], textColor: 255, fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      foot: [[
        `Jami: ${sales.length} ta`, '', '',
        sales.reduce((s,r) => s+Number(r.total_amount),0).toLocaleString('uz-UZ'),
        sales.reduce((s,r) => s+Number(r.paid_amount),0).toLocaleString('uz-UZ'),
        '', '', '', ''
      ]],
      footStyles: { fillColor: [241, 245, 249], fontStyle: 'bold', fontSize: 8 },
    });
    doc.save(`sotuvlar_${new Date().toISOString().slice(0,10)}.pdf`);
  }).catch(() => alert('PDF kutubxona yuklanmadi'));
}

/* ══════════════════════════════════════════════════
   PER-SALE EXCEL EXPORT
══════════════════════════════════════════════════ */
function exportSaleExcel(sale) {
  const loadXLSX = () => new Promise((res, rej) => {
    if (window.XLSX) { res(window.XLSX); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
    s.onload = () => res(window.XLSX); s.onerror = rej;
    document.head.appendChild(s);
  });
  const cfg = getReceiptSettings();
  const company = cfg.r58?.company || cfg.r80?.company || '';
  loadXLSX().then(XLSX => {
    const wb = XLSX.utils.book_new();
    const header = [];
    if (company) header.push([company]);
    header.push([`Sotuv: ${sale.number}`]);
    header.push([`Kassir: ${sale.cashier_name} | ${new Date(sale.created_at).toLocaleString('uz-UZ')}`]);
    header.push([]);
    const ws = XLSX.utils.aoa_to_sheet(header);
    const items = sale.items.map(i => ({
      'Mahsulot': i.product_name,
      'Soni': Number(i.quantity),
      "Narxi (so'm)": Number(i.unit_price),
      "Chegirma (so'm)": Number(i.discount || 0),
      "Jami (so'm)": Number(i.subtotal),
    }));
    XLSX.utils.sheet_add_json(ws, items, { origin: header.length });
    ws['!cols'] = [{ wch: 28 }, { wch: 8 }, { wch: 14 }, { wch: 14 }, { wch: 14 }];
    const summaryData = [
      [], // blank
      ['Jami mahsulotlar:', sale.items.length + ' ta'],
      ["Chegirma (so'm):", Number(sale.discount_amount)],
      ["JAMI (so'm):", Number(sale.total_amount)],
      ["To'langan (so'm):", Number(sale.paid_amount)],
      ["Qarz (so'm):", Number(sale.total_amount) - Number(sale.paid_amount)],
      ["To'lov turi:", payMeta[sale.payment_type]?.l || sale.payment_type],
      ['Holat:', saleMeta[sale.status]?.l || sale.status],
    ];
    XLSX.utils.sheet_add_aoa(ws, summaryData, { origin: { r: header.length + items.length + 1, c: 0 } });
    XLSX.utils.book_append_sheet(wb, ws, 'Sotuv');
    XLSX.writeFile(wb, `sotuv_${sale.number}_${new Date().toISOString().slice(0,10)}.xlsx`);
  }).catch(() => alert('Excel kutubxona yuklanmadi'));
}

/* ══════════════════════════════════════════════════
   PER-SALE PDF EXPORT
══════════════════════════════════════════════════ */
function exportSalePDF(sale) {
  const loadJsPDF = () => new Promise((res, rej) => {
    if (window.jspdf) { res(window.jspdf.jsPDF); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
    s.onload = () => {
      const s2 = document.createElement('script');
      s2.src = 'https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.2/dist/jspdf.plugin.autotable.min.js';
      s2.onload = () => res(window.jspdf.jsPDF); s2.onerror = rej;
      document.head.appendChild(s2);
    };
    s.onerror = rej;
    document.head.appendChild(s);
  });
  const cfg = getReceiptSettings();
  const company = cfg.r58?.company || cfg.r80?.company || '';
  const debt = Number(sale.total_amount) - Number(sale.paid_amount);

  loadJsPDF().then(JsPDF => {
    const doc = new JsPDF();
    let y = 14;
    if (company) {
      doc.setFontSize(14); doc.setFont(undefined, 'bold');
      doc.text(company, 14, y); y += 7;
    }
    doc.setFontSize(11); doc.setFont(undefined, 'bold');
    doc.text(`Sotuv: ${sale.number}`, 14, y); y += 6;
    doc.setFontSize(9); doc.setFont(undefined, 'normal');
    doc.setTextColor(100);
    doc.text(`Kassir: ${sale.cashier_name}  |  ${new Date(sale.created_at).toLocaleString('uz-UZ')}`, 14, y); y += 4;
    doc.text(`To'lov: ${payMeta[sale.payment_type]?.l || sale.payment_type}  |  Holat: ${saleMeta[sale.status]?.l || sale.status}`, 14, y); y += 4;
    doc.setTextColor(0);

    doc.autoTable({
      startY: y + 3,
      head: [['#','Mahsulot nomi','Soni',"Narxi (so'm)","Chegirma","Jami (so'm)"]],
      body: sale.items.map((i, idx) => [
        idx+1, i.product_name, Number(i.quantity),
        Number(i.unit_price).toLocaleString('uz-UZ'),
        Number(i.discount||0) > 0 ? `-${Number(i.discount).toLocaleString('uz-UZ')}` : '—',
        Number(i.subtotal).toLocaleString('uz-UZ'),
      ]),
      styles: { fontSize: 9, cellPadding: 3 },
      headStyles: { fillColor: [79, 70, 229], textColor: 255, fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      columnStyles: { 0:{cellWidth:8}, 2:{cellWidth:12}, 3:{cellWidth:30}, 4:{cellWidth:22}, 5:{cellWidth:32} },
    });

    const tableBottom = doc.lastAutoTable.finalY + 6;
    doc.setFontSize(9);
    const summaryLines = [
      Number(sale.discount_amount) > 0 ? [`Chegirma:`, `-${Number(sale.discount_amount).toLocaleString('uz-UZ')} so'm`] : null,
      [`JAMI:`, `${Number(sale.total_amount).toLocaleString('uz-UZ')} so'm`],
      [`To'langan:`, `${Number(sale.paid_amount).toLocaleString('uz-UZ')} so'm`],
      debt > 0 ? [`Qarz:`, `${Number(debt).toLocaleString('uz-UZ')} so'm`] : null,
    ].filter(Boolean);
    let sy = tableBottom;
    summaryLines.forEach(([label, val]) => {
      doc.setFont(undefined, label === 'JAMI:' ? 'bold' : 'normal');
      doc.text(label, 120, sy); doc.text(val, 190, sy, { align: 'right' }); sy += 5;
    });
    doc.save(`sotuv_${sale.number}.pdf`);
  }).catch(() => alert('PDF kutubxona yuklanmadi'));
}

/* ══════════════════════════════════════════════════
   TAB 1 — SOTUVLAR
══════════════════════════════════════════════════ */
function SotuvlarTab({ customers }) {
  const { t } = useLang();
  const [mode, setMode] = useState('list');
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(false);
  const [skip, setSkip] = useState(0);
  const LIMIT = 20;
  const [f, setF] = useState({ dateFrom: today(), dateTo: today(), status: '', customer_id: '', branch_id: '', cashier_id: '', customerQ: '', branchQ: '', userQ: '' });
  const [branches, setBranches] = useState([]);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    api.get('/branches/').then(r => setBranches(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/users/').then(r => setUsers(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  // Modals
  const [detailId, setDetailId]     = useState(null);
  const [editSale, setEditSale]     = useState(null);
  const [printSale, setPrintSale]   = useState(null); // sale for print picker

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip, limit: LIMIT };
      if (f.dateFrom) params.date_from = f.dateFrom;
      if (f.dateTo)   params.date_to   = f.dateTo;
      if (f.status)   params.status    = f.status;
      if (f.customer_id) params.customer_id = f.customer_id;
      if (f.branch_id) params.branch_id = f.branch_id;
      if (f.cashier_id) params.cashier_id = f.cashier_id;
      const r = await api.get('/sales/', { params });
      setSales(r.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [skip, f]);

  useEffect(() => { if (mode === 'list') load(); }, [load, mode]);

  if (mode === 'create') return <SaleCreateView customers={customers} onBack={() => setMode('list')} onSaved={() => {}} />;

  const totals = {
    sum:  sales.reduce((s,r) => s + Number(r.total_amount), 0),
    paid: sales.reduce((s,r) => s + Number(r.paid_amount || 0), 0),
  };

  const handleDelete = async (sale) => {
    if (!confirm(`"${sale.number}" sotuvini o'chirilsinmi?\nMahsulot qoldiqlari avtomatik qaytariladi.`)) return;
    try {
      await api.delete(`/sales/${sale.id}`);
      setDetailId(null);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik yuz berdi');
    }
  };

  // Opens print picker: fetches full sale if needed (list rows only have summary)
  const openPrintPicker = async (saleOrId) => {
    try {
      const id = typeof saleOrId === 'object' ? saleOrId.id : saleOrId;
      // If we already have a full sale with .items use it directly
      if (typeof saleOrId === 'object' && saleOrId.items) {
        setPrintSale(saleOrId);
      } else {
        const r = await api.get(`/sales/${id}`);
        setPrintSale(r.data);
      }
    } catch { alert('Chekni yuklashda xatolik'); }
  };

  return (
    <div className="space-y-3">
      {/* Header: actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-500">{t('admin.dict.total_colon') || 'Jami:'}</span>
          <span className="font-bold text-slate-800">{fmt(totals.sum)}</span>
          <span className="text-slate-300">|</span>
          <span className="text-emerald-600 font-semibold">{fmt(totals.paid)}</span>
          <span className="text-slate-300">|</span>
          <span className="text-red-500 font-semibold">{fmt(totals.sum - totals.paid)}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => exportExcel(sales)} className="flex items-center gap-1.5 px-3.5 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-lg border border-emerald-200 transition-colors">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/></svg>
            Excel
          </button>
          <button onClick={() => exportPDF(sales)} className="flex items-center gap-1.5 px-3.5 py-2 bg-red-50 hover:bg-red-100 text-red-700 text-sm font-semibold rounded-lg border border-red-200 transition-colors">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/></svg>
            PDF
          </button>
          <button onClick={() => setMode('create')} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg flex items-center gap-1.5 shadow-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
            {t('sale.newSale')}
          </button>
        </div>
      </div>

      {/* Filters — rasmdagi kabi 2 qator, keng inputlar */}
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-3">
          <input
            type="text"
            value={f.statusQ || ''}
            onChange={e => {
              const q = e.target.value;
              const match = Object.entries(saleMeta).find(([,m]) => m.l.toLowerCase().startsWith(q.toLowerCase()));
              setF({...f, statusQ: q, status: match ? match[0] : ''});
            }}
            placeholder={t('admin.dict.status2') || 'Status'}
            className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
          />
          <input type="date" value={f.dateFrom} onChange={e => setF({...f, dateFrom: e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
          <input type="date" value={f.dateTo} onChange={e => setF({...f, dateTo: e.target.value})} className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:border-slate-400 bg-white"/>
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 items-center">
          <div className="relative">
            <input
              type="text"
              value={f.customerQ || ''}
              onChange={e => setF({...f, customerQ: e.target.value, customer_id: ''})}
              onFocus={() => setF(p => ({...p, _custOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _custOpen: false})), 200)}
              placeholder={t('sale.customer')}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
            />
            {f._custOpen && f.customerQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {customers.filter(c => c.name.toLowerCase().includes((f.customerQ||'').toLowerCase()) || (c.phone && c.phone.includes(f.customerQ||''))).slice(0,10).map(c => (
                  <button key={c.id} onMouseDown={() => setF({...f, customer_id: String(c.id), customerQ: c.name, _custOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">
                    {c.name} {c.phone && <span className="text-slate-400 ml-1">{c.phone}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button className="w-8 h-8 flex items-center justify-center text-slate-300 hover:text-slate-500">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
          </button>
          <div className="relative">
            <input
              type="text"
              value={f.branchQ || ''}
              onChange={e => setF({...f, branchQ: e.target.value, branch_id: ''})}
              onFocus={() => setF(p => ({...p, _brOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _brOpen: false})), 200)}
              placeholder={t('admin.dict.employee') || 'Xodim'}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
            />
            {f._brOpen && f.branchQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {branches.filter(b => b.name.toLowerCase().includes((f.branchQ||'').toLowerCase())).slice(0,10).map(b => (
                  <button key={b.id} onMouseDown={() => setF({...f, branch_id: String(b.id), branchQ: b.name, _brOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{b.name}</button>
                ))}
              </div>
            )}
          </div>
          <div className="relative">
            <input
              type="text"
              value={f.userQ || ''}
              onChange={e => setF({...f, userQ: e.target.value, cashier_id: ''})}
              onFocus={() => setF(p => ({...p, _usOpen: true}))}
              onBlur={() => setTimeout(() => setF(p => ({...p, _usOpen: false})), 200)}
              placeholder={t('admin.dict.user') || 'Foydalanuvchi'}
              className="w-full border border-slate-200 rounded px-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 bg-white"
            />
            {f._usOpen && f.userQ && (
              <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-48 overflow-y-auto">
                {users.filter(u => u.name.toLowerCase().includes((f.userQ||'').toLowerCase())).slice(0,10).map(u => (
                  <button key={u.id} onMouseDown={() => setF({...f, cashier_id: String(u.id), userQ: u.name, _usOpen: false})}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b border-slate-100 last:border-0">{u.name}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16"><div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"/></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="px-3 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider w-10">#</th>
                  <th className="px-3 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.number') || 'Raqam'}</th>
                  <th className="px-3 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.contragent') || 'Kontragent'}</th>
                  <th className="px-3 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.total') || 'Jami'}</th>
                  <th className="px-3 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">{t('sale.paid')}</th>
                  <th className="px-3 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">{t('sale.debt')}</th>
                  <th className="px-3 py-3 text-center text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.payment') || 'To\'lov'}</th>
                  <th className="px-3 py-3 text-center text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.status') || 'Holat'}</th>
                  <th className="px-3 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.cashier') || 'Kassir'}</th>
                  <th className="px-3 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
                  <th className="px-3 py-3 w-24"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {/* Summary row */}
                {sales.length > 0 && (
                  <tr className="bg-indigo-50/40 text-sm font-semibold">
                    <td className="px-3 py-2.5" colSpan={3}><span className="text-slate-600">{t('common.total')}: {sales.length} {t('dashboard.salesCount')}</span></td>
                    <td className="px-3 py-2.5 text-right font-mono text-slate-800">{fmt(totals.sum)}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-emerald-600">{fmt(totals.paid)}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-red-500">{fmt(totals.sum - totals.paid)}</td>
                    <td colSpan={5}></td>
                  </tr>
                )}
                {sales.map((s, idx) => {
                  const debt = Number(s.total_amount) - Number(s.paid_amount);
                  return (
                    <tr key={s.id} className="hover:bg-indigo-50/30 transition-colors group">
                      <td className="px-3 py-2.5 text-slate-400 text-sm">{skip + idx + 1}</td>
                      <td className="px-3 py-2.5">
                        <button onClick={() => setDetailId(s.id)} className="font-mono font-semibold text-indigo-600 hover:text-indigo-800 hover:underline text-sm">{s.number}</button>
                      </td>
                      <td className="px-3 py-2.5 font-medium text-slate-800 text-sm">
                        {s.customer_name ? (
                          <Link to={`/admin/customers/${s.customer_id}`} className="text-indigo-600 hover:underline">{s.customer_name}</Link>
                        ) : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-800 text-sm">{fmt(s.total_amount)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-emerald-600 text-sm">{fmt(s.paid_amount)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-sm">
                        {debt > 0 ? <span className="font-semibold text-red-500">{fmt(debt)}</span> : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-3 py-2.5 text-center"><Badge meta={payMeta} val={s.payment_type}/></td>
                      <td className="px-3 py-2.5 text-center"><Badge meta={saleMeta} val={s.status}/></td>
                      <td className="px-3 py-2.5 text-sm text-slate-600 whitespace-nowrap">{s.cashier_name}</td>
                      <td className="px-3 py-2.5 text-sm text-slate-500 whitespace-nowrap">{new Date(s.created_at).toLocaleDateString('uz-UZ')} <span className="text-slate-400">{new Date(s.created_at).toLocaleTimeString('uz-UZ', {hour:'2-digit',minute:'2-digit'})}</span></td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => setDetailId(s.id)} title="Ko'rish" className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                          </button>
                          <button onClick={() => openPrintPicker(s.id)} title="Chek" className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-purple-600 hover:bg-purple-50 rounded-md">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
                          </button>
                          <button onClick={() => handleDelete(s)} title="O'chirish" className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-md">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {sales.length === 0 && !loading && (
                  <tr><td colSpan={11} className="px-5 py-10 text-center text-slate-400 text-sm">{t('sale.notFound')}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination - footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50/50">
          <span className="text-sm text-slate-500">{sales.length > 0 ? `${skip + 1}–${skip + sales.length} ${t('common.shown')}` : t('common.noData')}</span>
          <div className="flex items-center gap-2">
            <button disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - LIMIT))} className="px-3.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors">{t('admin.dict.prev') || 'Oldingi'}</button>
            <button disabled={sales.length < LIMIT} onClick={() => setSkip(skip + LIMIT)} className="px-3.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors">{t('admin.dict.next') || 'Keyingi'}</button>
          </div>
          <span className="text-sm text-slate-400">Limit: {LIMIT}</span>
        </div>
      </div>

      {/* Detail modal */}
      {detailId && (
        <SaleDetailModal
          saleId={detailId}
          onClose={() => setDetailId(null)}
          onEdit={() => {
            const s = sales.find(x => x.id === detailId);
            if (s) setEditSale(s);
          }}
          onDelete={() => {
            const s = sales.find(x => x.id === detailId);
            if (s) { setDetailId(null); handleDelete(s); }
          }}
          onPrint={() => openPrintPicker(detailId)}
        />
      )}

      {/* Edit modal */}
      {editSale && (
        <SaleEditModal
          sale={editSale}
          onClose={() => setEditSale(null)}
          onSaved={load}
        />
      )}

      {/* Print template picker */}
      {printSale && (
        <PrintPickerModal
          sale={printSale}
          onClose={() => setPrintSale(null)}
        />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   TAB 2 — MIJOZLAR
══════════════════════════════════════════════════ */
const TIERS = { Gold:{label:'Gold',cls:'bg-amber-100 text-amber-700'}, Silver:{label:'Silver',cls:'bg-slate-200 text-slate-700'}, Bronze:{label:'Bronze',cls:'bg-orange-100 text-orange-700'}, Standard:{label:'Standard',cls:'bg-slate-100 text-slate-500'} };
const tierOf = (pts) => pts>=10000?'Gold':pts>=5000?'Silver':pts>=1000?'Bronze':'Standard';
const generateCard = () => {
  let s = '8888';
  for (let i = 0; i < 12; i++) s += Math.floor(Math.random() * 10);
  return s.match(/.{1,4}/g).join(' ');
};

const emptyCustomer = { name: '', phone: '', debt_limit: '', loyalty_points: 0, card_number: '', cashback_percent: '' };

function MijozlarTab() {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(emptyCustomer);
  const [payAmt, setPayAmt] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = (q=search) => api.get(`/customers${q?'?search='+encodeURIComponent(q):''}`).then(r => setList(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => load(search), 400); return () => clearTimeout(t); }, [search]);

  const close = () => { setModal(null); setSel(null); setErr(''); };

  const handleSave = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try {
      const p = { 
        name: form.name, 
        phone: form.phone || null, 
        debt_limit: Number(form.debt_limit) || 0, 
        loyalty_points: Number(form.loyalty_points) || 0,
        card_number: form.card_number || null,
        cashback_percent: form.cashback_percent ? Number(form.cashback_percent) : 0
      };
      if (sel) await api.put(`/customers/${sel.id}`, p); else await api.post('/customers', p);
      close(); load();
    } catch (e) { setErr(e.response?.data?.detail||'Xatolik'); } finally { setSaving(false); }
  };

  const handlePay = async (e) => {
    e.preventDefault(); setSaving(true); setErr('');
    try { await api.post(`/customers/${sel.id}/pay-debt`, { amount:Number(payAmt), reason:"To'lov" }); close(); load(); }
    catch (e) { setErr(e.response?.data?.detail||'Xatolik'); } finally { setSaving(false); }
  };

  const del = async (id) => { if (!confirm("O'chirilsinmi?")) return; await api.delete(`/customers/${id}`); load(); };
  const totalDebt = list.reduce((s,c) => s+Number(c.debt_balance||0), 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5"><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{t('customer.totalCustomers')}</div><div className="text-2xl font-bold text-indigo-600 mt-0.5">{list.length}</div></div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5"><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{t('customer.totalDebt')}</div><div className="text-2xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} {t('common.sum')}</div></div>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5"><div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{t('customer.totalDebtors')}</div><div className="text-2xl font-bold text-amber-600 mt-0.5">{list.filter(c=>Number(c.debt_balance)>0).length}</div></div>
      </div>
      <div className="flex gap-3">
        <div className="relative flex-1"><svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg><input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder={t('customer.searchPlaceholder')} value={search} onChange={e => setSearch(e.target.value)}/></div>
        <button onClick={() => { setForm(emptyCustomer); setSel(null); setErr(''); setModal('form'); }} className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/></svg>{t('customer.newCustomer')}
        </button>
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead><tr className="bg-slate-50 border-b border-slate-100">{[t('common.name'),t('common.phone'),t('common.debt'),t('customer.creditLimit'),t('customer.loyaltyPoints'),''].map(h => <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(c => (
              <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-4"><div className="flex items-center gap-2.5"><Avatar name={c.name}/><Link to={`/admin/customers/${c.id}`} className="text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:underline">{c.name}</Link></div></td>
                <td className="px-5 py-4 text-sm text-slate-500">{c.phone||'—'}</td>
                <td className="px-5 py-4 text-sm font-semibold"><span className={Number(c.debt_balance)>0?'text-red-500':'text-emerald-600'}>{fmt(c.debt_balance)} so'm</span></td>
                <td className="px-5 py-4 text-sm text-slate-500">{fmt(c.debt_limit)} so'm</td>
                <td className="px-5 py-4"><div className="flex flex-col gap-0.5"><span className="text-xs font-semibold text-amber-600">⭐ {c.loyalty_points}</span><span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${TIERS[tierOf(c.loyalty_points||0)].cls}`}>{TIERS[tierOf(c.loyalty_points||0)].label}</span></div></td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-1">
                    {Number(c.debt_balance)>0&&<button onClick={() => { setSel(c); setPayAmt(''); setModal('pay'); }} className="p-1.5 text-emerald-500 hover:bg-emerald-50 rounded-lg" title="Qarz to'lash"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg></button>}
                    <button onClick={() => { setForm({name:c.name,phone:c.phone||'',debt_limit:c.debt_limit||0,loyalty_points:c.loyalty_points||0,card_number:c.card_number||'',cashback_percent:c.cashback_percent||0}); setSel(c); setModal('form'); }} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
                    <button onClick={() => del(c.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>
                  </div>
                </td>
              </tr>
            ))}
            {list.length===0&&<tr><td colSpan={6} className="px-5 py-12 text-center text-slate-400 text-sm">{t('customer.noCustomers')}</td></tr>}
          </tbody>
        </table>
      </div>

      {modal==='form' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100"><h3 className="text-lg font-bold text-slate-800">{sel ? t('customer.editCustomer') : t('customer.addCustomer')}</h3><button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.fullName')} *</label><input required className={inputCls} value={form.name} onChange={e => setForm({...form,name:e.target.value})} placeholder="Javohir Toshmatov"/></div>
              <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.phone') || 'Telefon'}</label><input className={inputCls} value={form.phone} onChange={e => setForm({...form,phone:e.target.value})} placeholder="+998 90 123 45 67"/></div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold text-slate-600">{t('customer.cardNumber')}</label>
                  <button type="button" onClick={() => setForm({ ...form, card_number: generateCard() })} className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">{t('customer.generateCard')}</button>
                </div>
                <input className={`${inputCls} font-mono`} value={form.card_number} onChange={e => setForm({...form,card_number:e.target.value})} placeholder="Masalan: 8888 1234 5678 9012"/>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.cashback')} (%)</label><input type="number" min="0" max="100" step="0.1" className={inputCls} value={form.cashback_percent} onChange={e => setForm({...form,cashback_percent:e.target.value})} placeholder="Masalan: 3.5"/></div>
                <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.creditLimit')}</label><input type="number" min="0" className={inputCls} value={form.debt_limit} onChange={e => setForm({...form,debt_limit:e.target.value})} placeholder="0"/></div>
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3 pt-1"><button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">{t('common.cancel')}</button><button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? '...' : t('common.save')}</button></div>
            </form>
          </div>
        </div>
      )}
      {modal==='pay'&&sel&&(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100"><h3 className="text-lg font-bold text-slate-800">{t('customer.payDebt')}</h3><button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400"><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
            <form onSubmit={handlePay} className="p-6 space-y-4">
              <div className="p-3 bg-slate-50 rounded-xl"><div className="font-semibold text-slate-800">{sel.name}</div><div className="text-red-500 font-bold mt-0.5">{t('common.debt')}: {fmt(sel.debt_balance)} {t('common.sum')}</div></div>
              <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('customer.paymentAmount')} *</label><input type="number" min="1" max={sel.debt_balance} required autoFocus className={inputCls} value={payAmt} onChange={e => setPayAmt(e.target.value)} placeholder="Miqdor..."/></div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3"><button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm rounded-xl hover:bg-slate-50">{t('common.cancel')}</button><button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">{saving ? '...' : t('common.confirm')}</button></div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   MAIN PAGE
══════════════════════════════════════════════════ */
export default function SotuvMijozlar() {
  const { t } = useLang();
  const [tab, setTab] = useState('sotuvlar');
  const TABS = [
    { id: 'sotuvlar', label: t('sale.title'),       icon: '🛒' },
    { id: 'mijozlar', label: t('customer.customers'), icon: '👥' },
  ];
  const [customers, setCustomers] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_cache_customers'))?.data || []; } catch { return []; }
  });

  useEffect(() => {
    api.get('/customers', { params: { limit: 300 }, _silent: true })
      .then(r => {
        const data = r.data;
        setCustomers(data);
        localStorage.setItem('pos_cache_customers', JSON.stringify({ ts: Date.now(), data }));
      }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  return (
    <div className="space-y-3">
      {/* Sarlavha + tablar bir qatorda */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold text-slate-800">{t('sale.salesAndCustomers')}</h1>
          <div className="flex gap-0.5 bg-slate-100 p-0.5 rounded-lg">
            {TABS.map(tabItem => (
              <button key={tabItem.id} onClick={() => setTab(tabItem.id)}
                className={`px-4 py-1.5 text-sm font-semibold rounded-md transition-all flex items-center gap-1.5 ${tab===tabItem.id?'bg-white text-slate-800 shadow-sm':'text-slate-500 hover:text-slate-700'}`}>
                <span className="text-xs">{tabItem.icon}</span>{tabItem.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tab==='sotuvlar' && <SotuvlarTab customers={customers}/>}
      {tab==='mijozlar' && <MijozlarTab/>}
    </div>
  );
}

