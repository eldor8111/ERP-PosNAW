import { useState, useEffect, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';
import { getReceiptSettings, buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import toast from 'react-hot-toast';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

/* ── Customer combobox ── */
function CustSearch({ customers, value, onChange, placeholder = "Mijoz izlash..." }) {
  const { t } = useLang();
const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => String(c.id) === String(value));
  const filtered = q.trim() ? customers.filter(c => c.name.toLowerCase().includes(q.toLowerCase()) || (c.phone && c.phone.includes(q))).slice(0, 12) : customers.slice(0, 12);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const select = (c) => { onChange(c ? c.id : ''); setQ(''); setOpen(false); };

  return (
    <div className="relative w-full" ref={ref}>
      <div className="flex items-center border-2 border-slate-200 rounded-xl bg-white overflow-hidden focus-within:border-rose-500 focus-within:ring-4 focus-within:ring-rose-500/20 transition-all pr-2">
        <div className="pl-3 text-slate-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
        </div>
        <input 
          value={open ? q : (selected ? selected.name : '')} 
          onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }} 
          onFocus={() => setOpen(true)} 
          placeholder={placeholder} 
          className="w-full px-3 py-3 text-sm font-semibold text-slate-700 outline-none bg-transparent placeholder:text-slate-400" 
        />
        {selected && <button onClick={() => select(null)} className="text-slate-400 hover:text-red-500 font-bold p-1">×</button>}
      </div>
      {open && (
        <div className="absolute top-full mt-2 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length === 0 ? <div className="px-4 py-3 text-sm text-slate-500 text-center font-medium">Topilmadi</div> : filtered.map(c => (
            <button key={c.id} onMouseDown={() => select(c)} className="w-full text-left px-4 py-3 hover:bg-rose-50 border-b border-slate-50 last:border-0 flex items-center justify-between transition-colors">
              <div><div className="text-sm font-bold text-slate-800">{c.name}</div>{c.phone && <div className="text-xs text-slate-500 font-medium">{c.phone}</div>}</div>
              {c.debt_balance > 0 && <span className="text-xs text-red-600 font-bold bg-red-50 px-2.5 py-1 rounded-lg">Qarz: {fmt(c.debt_balance)}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PosReturn() {
  const { t } = useLang();
const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [categories, setCategories] = useState([]);
  const [cart, setCart] = useState([]);
  const [custId, setCustId] = useState('');
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState(null);

  const [mixedAmt1, setMixedAmt1] = useState('');
  const [mixedAmt2, setMixedAmt2] = useState('');
  const [mixedType1, setMixedType1] = useState('cash');
  const [mixedType2, setMixedType2] = useState('card');
  const [focusedMixed, setFocusedMixed] = useState(1);

  // Numpad state
  const [paidInput, setPaidInput] = useState('');
  const [payType, setPayType] = useState('cash'); // cash, card, mixed
  const [isPaying, setIsPaying] = useState(false);
  const [err, setErr] = useState('');

  // Settings state
  const [showSettings, setShowSettings] = useState(false);
  const [posSettings, setPosSettings] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_return_settings') || '{"printer":"XP-80C","paper":"80mm","autoPrint":true,"shift":false,"unknownProduct":false,"fiscal":false}'); } catch { return {printer:"XP-80C",paper:"80mm",autoPrint:true,shift:false,unknownProduct:false,fiscal:false}; }
  });
  const savePosSettings = (updates) => {
    const next = { ...posSettings, ...updates };
    setPosSettings(next);
    localStorage.setItem('pos_return_settings', JSON.stringify(next));
  };

  // Load data
  useEffect(() => {
    api.get('/categories/', { params: { limit: 200 } })
      .then(r => setCategories(Array.isArray(r.data) ? r.data : (r.data.items || []))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/products/', { params: { limit: 12000, status: 'active' } })
      .then(r => setProducts(Array.isArray(r.data) ? r.data : (r.data.items || []))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/customers/', { params: { limit: 200 } })
      .then(r => {
        const custs = Array.isArray(r.data) ? r.data : (r.data.items || []);
        setCustomers(custs);
        try {
          const s = JSON.parse(localStorage.getItem('pos_return_settings') || '{}');
          if (s.defaultCustomer) setCustId(s.defaultCustomer);
        } catch { /* ignore */ }
      }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const filteredProducts = products.filter(p => {
    const ms = p.name.toLowerCase().includes(search.toLowerCase()) || p.sku?.includes(search) || p.barcode?.includes(search);
    const mc = activeCat ? p.category_id === activeCat : true;
    return ms && mc;
  });

  const totalNet = cart.reduce((s, c) => s + c.qty_ordered * c.net_cost, 0);

  const addToCart = (p) => {
    setCart(prev => {
      const ex = prev.find(x => x.product_id === p.id);
      if (ex) {
        // limit stock check
        if (ex.qty_ordered + 1 > p.stock_quantity) {
            // Allow negative config? For simplicity, we just allow it. The backend will validate if strict.
        }
        return prev.map(x => x.product_id === p.id ? { ...x, qty_ordered: x.qty_ordered + 1 } : x);
      }
      return [...prev, {
        product_id: p.id,
        product_name: p.name,
        unit: p.unit || 'dona',
        unit_price: Number(p.sale_price) || 0,
        discount_type: 'pct',
        discount_val: 0,
        net_cost: Number(p.sale_price) || 0,
        qty_ordered: 1,
        max_stock: p.stock_quantity
      }];
    });
  };

  const updateCartQty = (idx, delta) => {
    setCart(prev => {
      const next = prev.map((x, i) => {
        if (i !== idx) return x;
        const nQty = x.qty_ordered + delta;
        return { ...x, qty_ordered: Math.max(0.1, nQty) };
      });
      return next;
    });
  };

  const removeCartItem = (idx) => setCart(prev => prev.filter((_, i) => i !== idx));

  // Global Barcode Listener
  useEffect(() => {
    let barcodeBuffer = '';
    let lastKeyTime = Date.now();

    const handleKeyDown = (e) => {
      const isInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
      const currentTime = Date.now();
      if (currentTime - lastKeyTime > 50) {
         barcodeBuffer = '';
      }
      lastKeyTime = currentTime;

      if (e.key === 'Enter') {
         if (barcodeBuffer.length >= 4) {
           e.preventDefault();
           const scannedCode = barcodeBuffer;
           barcodeBuffer = '';
           if (isInput) e.target.blur();
           
           const found = products.find(p => p.barcode === scannedCode || p.sku === scannedCode);
           if (found) {
              setCart(prev => {
                const ex = prev.find(x => x.product_id === found.id);
                if (ex) return prev.map(x => x.product_id === found.id ? { ...x, qty_ordered: x.qty_ordered + 1 } : x);
                return [...prev, {
                  product_id: found.id, product_name: found.name, unit: found.unit || 'dona',
                  unit_price: Number(found.sale_price) || 0, discount_type: 'pct', discount_val: 0,
                  net_cost: Number(found.sale_price) || 0, qty_ordered: 1, max_stock: found.stock_quantity
                }];
              });
              setSearch('');
           } else {
              setErr(`Shtrix kod topilmadi: ${scannedCode}`);
              setTimeout(() => setErr(''), 3000);
           }
         }
         return;
      }

      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
         barcodeBuffer += e.key;
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [products]);

  // Numpad logic
  const handleNumClick = (val) => {
    if (showCheckout && payType === 'mixed') {
      if (focusedMixed === 1) setMixedAmt1(p => String(Number((p + val))) );
      else setMixedAmt2(p => String(Number((p + val))) );
    } else {
      if (paidInput === '0') setPaidInput(val);
      else setPaidInput(prev => prev + val);
    }
  };
  const handleBackspace = () => {
    if (showCheckout && payType === 'mixed') {
      if (focusedMixed === 1) setMixedAmt1(p => p.slice(0, -1));
      else setMixedAmt2(p => p.slice(0, -1));
    } else {
      setPaidInput(p => p.slice(0, -1));
    }
  };
  const handleClear = () => {
    if (showCheckout && payType === 'mixed') {
      if (focusedMixed === 1) setMixedAmt1('');
      else setMixedAmt2('');
    } else {
      setPaidInput('');
    }
  };

  const quickAmount = (amt) => {
    if (showCheckout && payType === 'mixed') {
      if (focusedMixed === 1) setMixedAmt1(String(amt));
      else setMixedAmt2(String(amt));
    } else {
      setPaidInput(String(amt));
    }
  };

  const [showCheckout, setShowCheckout] = useState(false);

  const submitSale = async () => {
    if (!cart.length) { setErr("Vazvrat savati bo'sh!"); setTimeout(()=>setErr(''),3000); return; }
    
    setIsPaying(true);
    setErr('');
    try {
      let paidAmt = Number(paidInput);
      if (paidInput === '') paidAmt = totalNet; 
      
      let pCash = 0;
      let pCard = 0;
      let noteTxt = '';

      if (payType === 'mixed') {
        const a1 = Number(mixedAmt1) || 0;
        const a2 = Number(mixedAmt2) || 0;
        paidAmt = a1 + a2;
        pCash = (mixedType1 === 'cash' ? a1 : 0) + (mixedType2 === 'cash' ? a2 : 0);
        pCard = (mixedType1 !== 'cash' ? a1 : 0) + (mixedType2 !== 'cash' ? a2 : 0);
        noteTxt = `Aralash to'lov turlari: To'lov 1 - ${mixedType1.toUpperCase()}, To'lov 2 - ${mixedType2.toUpperCase()}`;
      } else {
        pCash = payType === 'cash' ? paidAmt : 0;
        pCard = (payType !== 'cash' && payType !== 'debt') ? paidAmt : 0;
      }

      const finalType = paidAmt === 0 && payType !== 'mixed' ? 'debt' : payType;

      const payload = {
        items: cart.map(c => ({
          product_id: c.product_id,
          quantity: c.qty_ordered,
          unit_price: c.unit_price,
          discount: c.discount_type === 'pct' ? c.unit_price * c.qty_ordered * (c.discount_val / 100) : c.discount_val * c.qty_ordered,
        })),
        payment_type: finalType,
        paid_amount: paidAmt,
        paid_cash: pCash,
        paid_card: pCard,
        discount_amount: 0,
        note: noteTxt,
        customer_id: Number(custId) || null,
      };

      const res = await api.post('/sales/return', payload);

      // Auto Print — iframe (xuddi shu brauzer, tez)
      if (posSettings.autoPrint) {
        const settings = getReceiptSettings();
        const templateType = posSettings.template || (posSettings.paper === '58mm' ? '58' : '80');
        const tmplCfg = settings['r' + templateType] || settings[templateType] || {};
        const meta = res?.data || {
          id: 'Vazvrat-' + Date.now(), number: 'Vazvrat-' + Date.now(),
          cashier_name: 'Kassa', created_at: new Date().toISOString(),
          total_amount: totalNet, paid_amount: paidAmt, discount_amount: 0,
          payment_types_array: [{ type: finalType, amount: paidAmt }],
          items: cart,
        };
        printReceiptHtml(buildReceiptHtml(meta, templateType, tmplCfg));
      }

      setCart([]);
      setPaidInput('');
      setMixedAmt1('');
      setMixedAmt2('');
      if (posSettings.defaultCustomer) setCustId(posSettings.defaultCustomer);
      else setCustId('');
      setShowCheckout(false);
      setErr('MUVAFFAQIYATLI SOTILDI!');
      setTimeout(()=>setErr(''), 3000);
    } catch (e) {
      setErr(e.response?.data?.detail || "Xatolik ro'y berdi");
      setTimeout(()=>setErr(''),4000);
    } finally {
      setIsPaying(false);
    }
  };

  return (
    <div className="w-full h-screen bg-slate-100 flex overflow-hidden font-sans select-none">
      
      {/* ── 1. THIN LEFT SIDEBAR ── */}
      <div className="w-20 bg-slate-900 flex flex-col items-center py-6 gap-6 shadow-2xl z-20 shrink-0">
        {/* User / Logo */}
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-rose-500 to-indigo-600 text-white flex items-center justify-center font-black text-xl shadow-lg shadow-rose-500/30 mb-4">
          POS
        </div>

        {/* Home / Back to Dashboard */}
        <button onClick={() => navigate('/admin/sotuv-mijozlar')} className="w-12 h-12 rounded-xl flex items-center justify-center text-slate-400 hover:bg-slate-800 hover:text-white transition-all group" title="Orqaga">
          <svg className="w-6 h-6 group-hover:-translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>
        </button>

        {/* Current: POS */}
        <button className="w-12 h-12 rounded-xl flex items-center justify-center bg-rose-600 text-white shadow-lg shadow-rose-500/20 transition-all" title="Kassa">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>
        </button>

        <button className="w-12 h-12 rounded-xl flex items-center justify-center text-slate-400 hover:bg-slate-800 hover:text-white transition-all" title="Mijozlar">
           <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
        </button>

        {/* POS Sotuv (Sale) shortcut */}
        <button onClick={() => navigate('/admin/pos-desktop')} className="w-12 h-12 rounded-xl flex items-center justify-center text-blue-400 hover:bg-blue-600 hover:text-white transition-all" title="POS Sotuv">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>
        </button>

        <div className="mt-auto pb-4 space-y-4">
          <button onClick={() => setShowSettings(true)} className="w-12 h-12 rounded-xl flex items-center justify-center text-slate-400 hover:bg-slate-800 hover:text-white transition-all" title="Sozlamalar">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
          </button>
          <button className="w-12 h-12 rounded-xl flex items-center justify-center text-slate-400 hover:bg-slate-800 hover:text-white transition-all" title="Full Ekranga O'tish" onClick={()=>{if(!document.fullscreenElement) document.documentElement.requestFullscreen(); else document.exitFullscreen();}}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
          </button>
        </div>
      </div>

      {/* ── 2. CENTER SECTION (CART & NUMPAD) ── */}
      <div className="w-[420px] bg-white flex flex-col shadow-[10px_0_20px_rgba(0,0,0,0.02)] z-10 shrink-0">
        
        {/* Top: Customer & Order ID */}
        <div className="p-5 border-b border-slate-100 flex flex-col relative z-50">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-black text-slate-800">Buyurtma</h2>
            <div className="text-sm font-bold text-slate-400 bg-slate-100 px-3 py-1 rounded-lg border border-slate-200">#{(Math.floor(Math.random()*90000)+10000).toString()}</div>
          </div>
          <CustSearch customers={customers} value={custId} onChange={setCustId} placeholder="Mijozni tanlang (Majburiy)..." />
        </div>

        {/* Middle: Cart Items */}
        <div className="flex-1 overflow-y-auto bg-slate-50/50 p-2 space-y-2">
          {cart.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3">
              <svg className="w-16 h-16 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              <p className="font-semibold text-sm">Savatga mahsulot qo'shing</p>
            </div>
          ) : (
            cart.map((item, idx) => (
              <div key={idx} className="bg-white p-3 rounded-2xl border border-slate-200 shadow-sm flex items-center relative overflow-hidden group">
                {/* Colored accent line on the left */}
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-rose-500"></div>
                
                <div className="flex-1 pl-3 pr-2">
                  <div className="font-bold text-slate-800 text-sm leading-tight mb-1 truncate pr-6">{item.product_name}</div>
                  <div className="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
                    <span className="text-indigo-600">{fmt(item.unit_price)}</span> 
                    <span>×</span> 
                    <span>{item.qty_ordered} {item.unit}</span>
                  </div>
                </div>
                
                <div className="flex flex-col items-end gap-1.5">
                  <div className="font-black text-base text-slate-800">{fmt(Math.round(item.unit_price * item.qty_ordered))}</div>
                  {/* Qty Controls */}
                  <div className="flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200">
                    <button onClick={()=>updateCartQty(idx, -1)} className="w-6 h-6 flex items-center justify-center text-slate-600 font-bold hover:bg-white rounded hover:shadow-sm transition-all">−</button>
                    <div className="w-8 text-center text-xs font-bold">{item.qty_ordered}</div>
                    <button onClick={()=>updateCartQty(idx, 1)} className="w-6 h-6 flex items-center justify-center text-slate-600 font-bold hover:bg-white rounded hover:shadow-sm transition-all">+</button>
                  </div>
                </div>

                <button onClick={()=>removeCartItem(idx)} className="absolute right-2 top-2 w-6 h-6 bg-red-50 text-red-500 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500 hover:text-white pb-0.5 text-lg leading-none shrink-0" title="O'chirish">×</button>
              </div>
            ))
          )}
        </div>

        {/* Error / Success message area inside the cart view */}
        {err && (
          <div className="mx-4 my-2 px-3 py-2 bg-slate-800 text-white font-bold text-center text-sm rounded-lg shadow-md animate-in slide-in-from-bottom-2">
            {err}
          </div>
        )}

        {/* Bottom: Total & Checkout */}
        <div className="bg-white border-t border-slate-200 px-5 pt-4 pb-6 mt-auto rounded-t-3xl shadow-[0_-10px_20px_rgba(0,0,0,0.03)] flex flex-col gap-4 relative z-20">
          
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-500 font-bold uppercase tracking-widest text-xs">Umumiy summa</span>
            <span className="text-3xl font-black text-slate-800">{fmt(Math.round(totalNet))} <span className="text-lg text-slate-500">UZS</span></span>
          </div>

          <div className="h-16 w-full mt-2">
            <button onClick={() => { if(!cart.length) {setErr("Vazvrat savati bo'sh!"); setTimeout(()=>setErr(''),2000); return;} setShowCheckout(true); if(!paidInput) setPaidInput(String(Math.round(totalNet))); }} className="w-full h-full bg-rose-600 border-2 border-rose-600 text-white rounded-2xl text-xl uppercase tracking-widest font-black hover:bg-rose-700 active:scale-95 transition-all shadow-lg flex items-center justify-center gap-3">
               <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg> VAZVRAT QILISH
            </button>
          </div>
        </div>

      </div>

      {/* ── 3. RIGHT SECTION (PRODUCTS GRID) ── */}
      <div className="flex-1 flex flex-col bg-slate-50 p-6 overflow-hidden">
        
        {/* Top bar */}
        <div className="flex items-center justify-between mb-6 shrink-0 gap-6">
          <div className="flex-1 flex items-center bg-white border border-slate-200 rounded-2xl focus-within:ring-4 focus-within:ring-indigo-500/20 focus-within:border-indigo-500 shadow-sm px-4 py-3.5 transition-all max-w-2xl">
            <svg className="w-6 h-6 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            <input 
              value={search} 
              onChange={e => setSearch(e.target.value)} 
              placeholder="Mahsulot nomi yoki shtrix kodi bo'yicha qidirish..." 
              className="flex-1 bg-transparent border-none outline-none text-slate-700 font-semibold placeholder:text-slate-400 text-lg" 
            />
            {search && <button onClick={()=>setSearch('')} className="text-slate-400 hover:text-red-500 p-1 font-bold text-xl leading-none">×</button>}
          </div>

          <div className="text-right">
             <div className="text-sm font-bold text-slate-500 flex items-center gap-2 justify-end">
               <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Kassa faol
             </div>
             <div className="text-slate-400 text-xs font-semibold mt-1 pr-1">{new Date().toLocaleString('uz-UZ', {weekday:'long', hour:'2-digit', minute:'2-digit'})}</div>
          </div>
        </div>

        {/* Categories Row */}
        <div className="flex gap-2 overflow-x-auto pb-4 mb-2 scrollbar-hide shrink-0 z-10 w-full snap-x">
          <button 
            onClick={() => setActiveCat(null)} 
            className={`px-4 py-2.5 rounded-2xl text-sm font-bold whitespace-nowrap transition-all shadow-sm shrink-0 snap-start border-2 ${!activeCat ? 'bg-indigo-600 border-indigo-600 text-white shadow-indigo-200' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-indigo-300'}`}
          >
            Barchasi
          </button>
          {categories.map(c => (
            <button 
              key={c.id} 
              onClick={() => setActiveCat(c.id)} 
              className={`px-4 py-2.5 rounded-2xl text-sm font-bold whitespace-nowrap transition-all shadow-sm shrink-0 snap-start border-2 ${activeCat === c.id ? 'bg-indigo-600 border-indigo-600 text-white shadow-indigo-200' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-indigo-300'}`}
            >
              {c.name}
            </button>
          ))}
        </div>

        {/* Product Grid */}
        <div className="flex-1 overflow-y-auto pb-10">
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5">
            {filteredProducts.map(p => (
              <button key={p.id} onClick={() => addToCart(p)} className="bg-white rounded-2xl border border-slate-200 p-4 flex flex-col items-start gap-4 hover:border-indigo-400 hover:shadow-xl hover:-translate-y-1 transition-all group active:scale-95 text-left relative overflow-hidden">
                {/* Accent shape top right */}
                <div className="absolute -top-4 -right-4 w-12 h-12 bg-indigo-50 rounded-full group-hover:scale-[3] transition-transform duration-500 ease-out z-0"></div>

                {/* Picture placeholder / Icon */}
                <div className="w-full aspect-video bg-slate-50 rounded-xl flex items-center justify-center mb-1 group-hover:bg-white relative z-10 border border-slate-100">
                  <div className="w-12 h-12 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center font-black text-xl shadow-inner">
                    {p.name.slice(0, 2).toUpperCase()}
                  </div>
                </div>

                <div className="w-full relative z-10">
                  <h3 className="font-bold text-slate-800 text-[15px] leading-snug line-clamp-2 mb-2 group-hover:text-indigo-900 transition-colors h-10">{p.name}</h3>
                  <div className="flex items-end justify-between w-full">
                    <div className="font-black text-indigo-600 text-[17px]">{fmt(p.sale_price)} <span className="text-[11px] font-bold text-slate-400">UZS</span></div>
                    <div className="text-[11px] font-extrabold text-slate-400 bg-slate-100 px-2 py-1 rounded-md border border-slate-200">
                      {p.stock_quantity > 0 ? `${fmt(p.stock_quantity)} ${p.unit||'dona'}` : '0 ta'}
                    </div>
                  </div>
                </div>
              </button>
            ))}
            
            {filteredProducts.length === 0 && (
              <div className="col-span-full py-16 flex flex-col items-center justify-center text-slate-400">
                <svg className="w-16 h-16 mb-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-lg font-bold">Mahsulot topilmadi</p>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* ── 3.5. CHECKOUT MODAL ── */}
      {showCheckout && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4 transition-opacity">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            
            <div className="bg-slate-50 border-b border-slate-100 px-6 py-4 flex items-center justify-between z-10">
              <h2 className="text-xl font-black text-slate-800">Vazvratni tasdiqlash</h2>
              <button onClick={() => setShowCheckout(false)} className="text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="flex flex-col md:flex-row h-full">
              {/* Left Column: Numpad */}
              <div className="w-full md:w-[45%] p-6 bg-slate-100 border-r border-slate-200 flex flex-col gap-4">
                <div className="flex flex-col gap-1 items-center justify-center py-4 bg-white rounded-xl shadow-sm border border-slate-200">
                  <span className="text-slate-400 uppercase tracking-widest text-xs font-bold">Kiritildi</span>
                  <span className="text-3xl font-black text-rose-700">
                     {payType === 'mixed' 
                        ? fmt((Number(mixedAmt1)||0) + (Number(mixedAmt2)||0))
                        : fmt(Number(paidInput)||0)} UZS
                  </span>
                </div>

                <div className="grid grid-cols-4 gap-2 h-[320px] mt-2">
                  <button onClick={()=>handleNumClick('1')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">1</button>
                  <button onClick={()=>handleNumClick('2')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">2</button>
                  <button onClick={()=>handleNumClick('3')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">3</button>
                  <button onClick={handleBackspace} className="bg-rose-50 border-2 border-rose-200 rounded-2xl text-rose-500 hover:bg-rose-100 active:scale-95 transition-all shadow-sm flex items-center justify-center">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M3 12l6.414 6.414a2 2 0 001.414.586H19a2 2 0 002-2V7a2 2 0 00-2-2h-8.172a2 2 0 00-1.414.586L3 12z"/></svg>
                  </button>
                  
                  <button onClick={()=>handleNumClick('4')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">4</button>
                  <button onClick={()=>handleNumClick('5')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">5</button>
                  <button onClick={()=>handleNumClick('6')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">6</button>
                  <button onClick={handleClear} className="bg-slate-100 border-2 border-slate-200 rounded-2xl text-2xl font-bold text-slate-500 hover:bg-slate-200 active:scale-95 transition-all shadow-sm">C</button>
                  
                  <button onClick={()=>handleNumClick('7')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">7</button>
                  <button onClick={()=>handleNumClick('8')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">8</button>
                  <button onClick={()=>handleNumClick('9')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">9</button>
                  <button onClick={()=>quickAmount(50000)} className="bg-emerald-50 border-2 border-emerald-200 text-emerald-700 rounded-2xl font-bold text-base hover:bg-emerald-100 active:scale-95 transition-all shadow-sm leading-tight tracking-wider">50k</button>

                  <button onClick={()=>handleNumClick('0')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm col-span-2">0</button>
                  <button onClick={()=>handleNumClick('00')} className="bg-white border-2 border-slate-200 rounded-2xl text-3xl font-bold text-slate-700 hover:bg-slate-50 active:scale-95 transition-all shadow-sm">00</button>
                  <button onClick={()=>quickAmount(100000)} className="bg-emerald-50 border-2 border-emerald-200 text-emerald-700 rounded-2xl font-bold text-base hover:bg-emerald-100 active:scale-95 transition-all shadow-sm leading-tight tracking-wider">100k</button>
                </div>
              </div>

              {/* Right Column: Settings */}
              <div className="flex-1 p-6 flex flex-col gap-5 overflow-y-auto">
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-bold text-slate-500 uppercase tracking-widest">Mijoz (Ixtiyoriy)</label>
                  <div className="px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-bold overflow-hidden truncate">
                    {customers.find(c=>String(c.id)===String(custId))?.name || <span className="text-slate-400 font-medium">Umumiy mijoz (Mijoz tanlanmagan)</span>}
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <label className="text-sm font-bold text-slate-500 uppercase tracking-widest">To'lov turi</label>
                  <div className="flex flex-wrap gap-2">
                  {[
                    {v:'cash', l:'Naqd', c:'bg-emerald-50 text-emerald-700 border-emerald-300'},
                    {v:'uzcard', l:'Uzc', c:'bg-rose-50 text-rose-700 border-rose-300'},
                    {v:'humo', l:'Humo', c:'bg-indigo-50 text-indigo-700 border-indigo-300'},
                    {v:'click', l:'Click', c:'bg-sky-50 text-sky-700 border-sky-300'},
                    {v:'payme', l:'Payme', c:'bg-cyan-50 text-cyan-700 border-cyan-300'},
                    {v:'mixed', l:'Aralash', c:'bg-orange-50 text-orange-700 border-orange-300'},
                  ].map(t => (
                    <button key={t.v} onClick={()=>setPayType(t.v)} className={`px-4 py-2 rounded-xl text-sm font-bold shadow-sm transition-all border-2 shrink-0 active:scale-95 flex-1 ${payType===t.v ? t.c + ' ring-2 ring-offset-1 ring-'+(t.c.includes('slate')?'slate':t.c.split('-')[1])+'-500' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                      {t.l}
                    </button>
                  ))}
                  </div>
                </div>

                {payType === 'mixed' ? (
                  <div className="flex flex-col gap-3 p-4 bg-orange-50/50 rounded-xl border-2 border-orange-200 relative z-30 shadow-inner mt-2">
                    <div className="flex gap-3 items-center">
                      <select value={mixedType1} onChange={e=>setMixedType1(e.target.value)} className="w-[120px] bg-white border border-slate-200 rounded-lg py-2.5 px-2 font-bold text-sm text-slate-700 outline-none focus:border-orange-500 transition-all">
                         <option value="cash">Naqd</option>
                         <option value="card">Karta (Krt)</option>
                         <option value="uzcard">Uzcard</option>
                         <option value="humo">Humo</option>
                         <option value="click">Click</option>
                         <option value="payme">Payme</option>
                         <option value="uzum">Uzum</option>
                      </select>
                      <input type="text" readOnly onClick={()=>setFocusedMixed(1)} value={mixedAmt1 ? fmt(Number(mixedAmt1)) : ''} placeholder="0" className={`flex-1 px-3 py-2.5 rounded-lg border-2 text-right text-xl font-black outline-none transition-all cursor-pointer ${focusedMixed===1?'border-orange-500 bg-white ring-4 ring-orange-500/20 text-orange-600 shadow-md':'border-transparent bg-slate-100 text-slate-500 hover:bg-white'}`} />
                    </div>
                    <div className="flex gap-3 items-center mt-2">
                      <select value={mixedType2} onChange={e=>setMixedType2(e.target.value)} className="w-[120px] bg-white border border-slate-200 rounded-lg py-2.5 px-2 font-bold text-sm text-slate-700 outline-none focus:border-orange-500 transition-all">
                         <option value="card">Karta (Krt)</option>
                         <option value="cash">Naqd</option>
                         <option value="uzcard">Uzcard</option>
                         <option value="humo">Humo</option>
                         <option value="click">Click</option>
                         <option value="payme">Payme</option>
                         <option value="uzum">Uzum</option>
                      </select>
                      <input type="text" readOnly onClick={()=>setFocusedMixed(2)} value={mixedAmt2 ? fmt(Number(mixedAmt2)) : ''} placeholder="0" className={`flex-1 px-3 py-2.5 rounded-lg border-2 text-right text-xl font-black outline-none transition-all cursor-pointer ${focusedMixed===2?'border-orange-500 bg-white ring-4 ring-orange-500/20 text-orange-600 shadow-md':'border-transparent bg-slate-100 text-slate-500 hover:bg-white'}`} />
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex flex-col gap-1 items-center justify-center">
                    <span className="text-slate-500 font-bold text-xs uppercase tracking-widest">Jami Kiritilishi Kerak</span>
                    <span className="text-3xl font-black text-slate-800">{fmt(Math.round(totalNet))} UZS</span>
                  </div>
                )}

                <div className="flex gap-3 mt-auto pt-4">
                  <button onClick={() => setShowCheckout(false)} className="flex-1 py-3.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-black rounded-xl transition-colors active:scale-95 uppercase tracking-widest text-sm border-2 border-transparent">{t('common.cancel')}</button>
                  <button onClick={submitSale} disabled={isPaying || (payType !== 'mixed' && Number(paidInput) < totalNet && !custId) || (payType === 'mixed' && (Number(mixedAmt1)+Number(mixedAmt2)) < totalNet && !custId)} className="flex-2 py-3.5 bg-rose-600 hover:bg-rose-700 text-white font-black rounded-xl shadow-lg shadow-rose-200 transition-all active:scale-95 flex items-center justify-center gap-2 border-2 border-rose-600 uppercase tracking-widest text-sm disabled:bg-rose-300 disabled:border-rose-300 disabled:shadow-none">
                    {isPaying ? <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>} QAYTARISH VA CHOP ETISH
                  </button>
                </div>

              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 4. SETTINGS MODAL ── */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 transition-opacity">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl flex flex-col p-6 animate-in zoom-in-95 duration-200">
            
            <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-6">
              <h2 className="text-xl font-bold text-slate-800">Общие настройки</h2>
              <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-slate-600">
                 <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="grid grid-cols-2 gap-6 mb-6">
              {/* Left Column */}
              <div className="border border-slate-200 rounded-xl p-6 bg-slate-50/50">
                <h3 className="font-semibold text-slate-600 mb-5">Настройки печати</h3>
                
                <div className="grid grid-cols-2 gap-5 mb-6">
                  <div>
                    <label className="block text-sm font-medium text-slate-500 mb-2">Принтер</label>
                    <select value={posSettings.printer} onChange={e=>savePosSettings({printer:e.target.value})} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-semibold outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 bg-slate-50">
                      <option value="XP-80C">XP-80C</option>
                      <option value="XP-58">XP-58</option>
                      <option value="System Default">Системный по умолчанию</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-500 mb-2">Размер чека</label>
                    <select value={posSettings.paper} onChange={e=>savePosSettings({paper:e.target.value})} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-semibold outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 bg-slate-50">
                      <option value="80mm">80mm</option>
                      <option value="58mm">58mm</option>
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-slate-500 mb-2">Chek Shabloni (Шаблон чека - Bozor)</label>
                    <select value={posSettings.template || '80'} onChange={e=>savePosSettings({template:e.target.value})} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-semibold outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 bg-slate-50">
                      <option value="80">Chek 80mm Template</option>
                      <option value="58">Chek 58mm Template</option>
                      <option value="nak">A4 Nakladnoy Template</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-600">Автоматическая распечатать</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" className="sr-only peer" checked={posSettings.autoPrint} onChange={e=>savePosSettings({autoPrint:e.target.checked})} />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-rose-600"></div>
                  </label>
                </div>
              </div>

              {/* Right Column */}
              <div className="border border-slate-200 rounded-xl p-6 bg-slate-50/50">
                <h3 className="font-semibold text-slate-600 mb-5">Функциональные настройки</h3>
                
                <div className="flex flex-col gap-6">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-600">Смена</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input type="checkbox" className="sr-only peer" checked={posSettings.shift} onChange={e=>savePosSettings({shift:e.target.checked})} />
                      <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-rose-600"></div>
                    </label>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-600">Включить создание неизвестного товара</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input type="checkbox" className="sr-only peer" checked={posSettings.unknownProduct} onChange={e=>savePosSettings({unknownProduct:e.target.checked})} />
                      <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-rose-600"></div>
                    </label>
                  </div>

                  <div className="flex items-center">
                    <label className="relative inline-flex items-center cursor-pointer gap-3">
                      <input type="checkbox" checked={posSettings.fiscal} onChange={e=>savePosSettings({fiscal:e.target.checked})} className="w-5 h-5 text-rose-600 bg-slate-100 border-slate-300 rounded focus:ring-rose-500 focus:ring-2 cursor-pointer" />
                      <span className="text-sm font-medium text-slate-600">Фискализация</span>
                    </label>
                  </div>
                  
                  <div className="mt-4 border-t border-slate-100 pt-5">
                    <label className="block text-sm font-medium text-slate-500 mb-2">Doimiy mijoz (По умолчанию)</label>
                    <select value={posSettings.defaultCustomer || ''} onChange={e=>{savePosSettings({defaultCustomer:e.target.value}); setCustId(e.target.value);}} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-semibold outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 bg-white">
                      <option value="">-- Tanlanmagan --</option>
                      {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Receipt Template */}
            <div className="border border-rose-200 rounded-xl p-5 bg-rose-50/50 mb-4 flex items-start gap-3">
              <svg className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <div>
                <p className="text-sm font-semibold text-rose-700">Chek shabloni Nastroykada sozlanadi</p>
                <p className="text-xs text-rose-500 mt-0.5">Logotip, do'kon nomi, manzil, telefon va boshqalar → <b>Nastroyka → Chek shabloni</b> bo'limidan o'zgartiring.</p>
              </div>
            </div>

            <div className="flex justify-end pt-2">
               <button onClick={() => setShowSettings(false)} className="px-8 py-2.5 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-lg shadow-sm transition-colors text-sm">
                 Сохранить
               </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}



