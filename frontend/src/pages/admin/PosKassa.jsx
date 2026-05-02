import { useState, useEffect, useRef, useMemo } from 'react';
import { useLang } from '../../context/LangContext';
import { useNavigate } from 'react-router-dom';
import usePosSync from '../../hooks/usePosSync';
import { toast } from '../../utils/toast';
import api from '../../api/axios';
import { getReceiptSettings, buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import { useActiveShift } from '../../hooks/useActiveShift';
import ShiftOpenModal from '../../components/ShiftOpenModal';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const cleanNum = (str) => Number(String(str).replace(/\D/g, ''));
const parseAmt = (str) => parseInt(String(str || '').replace(/\D/g, ''), 10) || 0;

/* ── Customer combobox ── */
function CustSearch({ customers, value, onChange, placeholder = "Mijoz izlash..." }) {
  const { t } = useLang();
const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => String(c.id) === String(value));
  const filtered = q.trim() 
    ? customers.filter(c => c.name.toLowerCase().includes(q.toLowerCase()) || (c.phone && c.phone.includes(q))).slice(0, 12) 
    : customers.slice(0, 12);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const select = (c) => { onChange(c ? c.id : ''); setQ(''); setOpen(false); };

  return (
    <div className="relative w-full" ref={ref}>
      <div className="flex items-center border-[2px] border-slate-300 rounded-xl bg-white overflow-hidden focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-500/20 transition-all pr-2">
        <div className="pl-3 text-slate-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
        </div>
        <input 
          value={open ? q : (selected ? selected.name : '')} 
          onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }} 
          onFocus={() => setOpen(true)} 
          placeholder={placeholder} 
          className="w-full px-3 py-3 text-base font-bold text-slate-700 outline-none bg-transparent placeholder:text-slate-400" 
        />
        {selected && <button onClick={() => select(null)} className="text-slate-400 hover:text-red-500 font-bold p-1">×</button>}
      </div>
      {open && (
        <div className="absolute top-full mt-2 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length === 0 ? <div className="px-4 py-3 text-sm text-slate-500 text-center font-medium">{t('pos.customerNotFound')}</div> : filtered.map(c => (
            <button key={c.id} onMouseDown={() => select(c)} className="w-full text-left px-4 py-3 hover:bg-blue-50 border-b border-slate-50 last:border-0 flex items-center justify-between transition-colors">
              <div>
                <div className="text-sm font-bold text-slate-800">{c.name}</div>
                {c.phone && <div className="text-xs text-slate-500 font-medium">{c.phone}</div>}
              </div>
              {Number(c.debt_balance) > 0 && <span className="text-xs text-red-600 font-bold bg-red-50 px-2.5 py-1 rounded-lg">{t('common.debt')}: {fmt(c.debt_balance)}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PosKassa() {
  const { t } = useLang();
const navigate = useNavigate();
  // Keshdan darhol o'qish — faqat joriy foydalanuvchi company_id ga mos kelsa
  const currentUser = (() => { try { return JSON.parse(localStorage.getItem('user')); } catch { return null; } })();
  const currentCompanyId = currentUser?.company_id;

  const readCache = (key) => {
    try {
      const raw = JSON.parse(localStorage.getItem(key));
      if (!raw?.data) return [];
      // Boshqa korxona keshi bo'lsa — ishlatma
      if (currentCompanyId && raw.company_id && raw.company_id !== currentCompanyId) return [];
      return raw.data;
    } catch { return []; }
  };

  const [products, setProducts] = useState(() => readCache('pos_cache_products'));
  const [customers, setCustomers] = useState(() => readCache('pos_cache_customers'));
  const [categories, setCategories] = useState(() => readCache('pos_cache_categories'));
  const [refreshing, setRefreshing] = useState(false);
  
  // Savat va UI holatlari
  const [cart, setCart] = useState([]);
  const [custId, setCustId] = useState('');
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState(null);
  
  const [showSettings, setShowSettings] = useState(false);
  const [showCheckout, setShowCheckout] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [isPaying, setIsPaying] = useState(false);

  // Buyurtma raqami generatori
  const orderIdRef = useRef(Math.floor(Math.random() * 900000) + 100000);
  const [orderId, setOrderId] = useState(() => orderIdRef.current);

  // Yangi mahsulot qo'shish modali
  const [showNewProduct, setShowNewProduct] = useState(false);
  const [newProd, setNewProd] = useState({ name:'', barcode:'', sale_price:'', cost_price:'', unit:'dona', category_id:'', stock_quantity:'0' });
  const [savingProd, setSavingProd] = useState(false);
  const { hasShift, reload: reloadShift } = useActiveShift();
  const [showShiftModal, setShowShiftModal] = useState(false);

  // Sync hooks
  const { isOnline, submitSaleOrQueue, fetchProducts, fetchCustomers, fetchCategories } = usePosSync({
    onSyncSuccess: (count) => {
      toast.success(`✅ ${count} ta offline sotuv serverga yuborildi!`);
    },
  });

  // Settings
  const [posSettings, setPosSettings] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('pos_desktop_settings') || '{"printer":"XP-80C","paper":"80mm","autoPrint":true}');
    } catch {
      return {printer:"XP-80C",paper:"80mm",autoPrint:true};
    }
  });

  const savePosSettings = (updates) => {
    const next = { ...posSettings, ...updates };
    setPosSettings(next);
    localStorage.setItem('pos_desktop_settings', JSON.stringify(next));
  };

  useEffect(() => {
    // Kesh allaqachon ko'rsatildi — fon fonda serverdan yangi ma'lumot olish
    const settings = JSON.parse(localStorage.getItem('pos_desktop_settings') || '{}');
    if (settings.defaultCustomer && !custId) setCustId(settings.defaultCustomer);

    setRefreshing(true);
    Promise.all([
      fetchCategories(),
      fetchProducts(),
      fetchCustomers(),
    ]).then(([cats, prods, custs]) => {
      setCategories(cats);
      setProducts(prods);
      setCustomers(custs);
      const s = JSON.parse(localStorage.getItem('pos_desktop_settings') || '{}');
      if (s.defaultCustomer) setCustId(s.defaultCustomer);
    }).finally(() => setRefreshing(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Global Skaner Listener
  useEffect(() => {
    let buf = '';
    let lastTime = Date.now();
    const handler = (e) => {
      if (showCheckout || showNewProduct) return;
      const isInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
      const now = Date.now();
      if (now - lastTime > 60) buf = '';
      lastTime = now;

      if (e.key === 'Enter') {
         if (buf.length >= 3) {
           e.preventDefault();
           const code = buf;
           buf = '';
           if (isInput) e.target.blur();
           const p = products.find(x =>
             x.barcode === code ||
             x.sku === code ||
             (Array.isArray(x.extra_barcodes) && x.extra_barcodes.includes(code))
           );
           if (p) {
             addToCart(p);
           } else {
             // Topilmadi — yangi mahsulot qo'shish modalini och
             setNewProd({ name:'', barcode: code, sale_price:'', cost_price:'', unit:'dona', category_id:'', stock_quantity:'0' });
             setShowNewProduct(true);
           }
         }
         return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) buf += e.key;
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [products, showCheckout, showNewProduct]);

  // Yangi mahsulotni bazaga saqlash va savatga qo'shish
  const saveNewProduct = async () => {
    if (!newProd.name.trim()) return toast.error("Mahsulot nomini kiriting!");
    if (!newProd.sale_price || Number(newProd.sale_price) <= 0) return toast.error("Sotuv narxini kiriting!");
    setSavingProd(true);
    try {
      const payload = {
        name: newProd.name.trim(),
        barcode: newProd.barcode || null,
        sale_price: Number(newProd.sale_price),
        cost_price: Number(newProd.cost_price) || 0,
        unit: newProd.unit || 'dona',
        category_id: newProd.category_id ? Number(newProd.category_id) : null,
        stock_quantity: Number(newProd.stock_quantity) || 0,
        status: 'active',
      };
      const res = await api.post('/products/', payload);
      const created = res.data;
      // Mahsulotlar ro'yxatiga qo'sh
      setProducts(prev => [...prev, created]);
      // Savatga qo'sh
      addToCart({ ...created, sale_price: created.sale_price, stock_quantity: created.stock_quantity });
      toast.success(`"${created.name}" qo'shildi va savatga tushirildi!`);
      setShowNewProduct(false);
    } catch {
      // axios interceptor toast chiqaradi
    } finally {
      setSavingProd(false);
    }
  };

  const GRID_CAP = 150; // Bir vaqtda DOM-da ko'rsatiladigan max karta soni

  // Barcha filter bo'yicha mahsulotlar (skaner uchun to'liq ro'yxat)
  const filteredProducts = useMemo(() => products.filter(p => {
    const m1 = !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.sku?.includes(search) || p.barcode?.includes(search) ||
      (Array.isArray(p.extra_barcodes) && p.extra_barcodes.some(b => b.includes(search)));
    const m2 = activeCat ? p.category_id === activeCat : true;
    return m1 && m2;
  }), [products, search, activeCat]);

  // Gridda ko'rsatiladigan mahsulotlar (DOM yukini kamaytiradi)
  const displayedProducts = useMemo(() => {
    if (search || activeCat) return filteredProducts;      // Qidirishda barchasini ko'rsat
    return filteredProducts.slice(0, GRID_CAP);            // Filtrsiz — faqat birinchi 150
  }, [filteredProducts, search, activeCat]);

  // Savat boshqaruvi
  const addToCart = (p) => {
    setCart(prev => {
      const idx = prev.findIndex(x => x.product_id === p.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx].qty_ordered += 1;
        return next;
      }
      return [{
        product_id: p.id,
        product_name: p.name,
        unit: p.unit || 'dona',
        unit_price: Number(p.sale_price) || 0,
        discount_type: 'sum',
        discount_val: 0,
        qty_ordered: 1,
        max_stock: p.stock_quantity
      }, ...prev];
    });
  };

  const updateCartQty = (idx, delta) => {
    setCart(prev => {
      const next = [...prev];
      next[idx].qty_ordered = Math.max(0.1, next[idx].qty_ordered + delta);
      return next;
    });
  };

  const updateExtQty = (idx, qtyVal) => {
    setCart(prev => {
      const next = [...prev];
      next[idx].qty_ordered = Math.max(0.1, Number(qtyVal)||1);
      return next;
    });
  };

  const updateDiscount = (idx, val) => {
    setCart(prev => {
      const next = [...prev];
      next[idx].discount_val = Number(val) || 0;
      return next;
    });
  };

  const removeCartItem = (idx) => setCart(prev => prev.filter((_, i) => i !== idx));

  // Hesob-kitoblar
  const totalSubtotal = cart.reduce((s, c) => s + (c.unit_price * c.qty_ordered), 0);
  const totalDiscount = cart.reduce((s, c) => {
    return s + (c.discount_type === 'pct' 
      ? (c.unit_price * c.qty_ordered * (c.discount_val / 100)) 
      : c.discount_val);
  }, 0);
  const totalNet = Math.max(0, totalSubtotal - totalDiscount);

  // To'lov formasi holati
  const [payments, setPayments] = useState([{ type: 'cash', amount: '' }]);
  const [activeInputIdx, setActiveInputIdx] = useState(0);

  const [showDebtModal, setShowDebtModal] = useState(false);
  const [debtDueDate, setDebtDueDate] = useState('');
  const [debtNote, setDebtNote] = useState('');

  const handleNumClick = (val) => {
    setPayments(prev => {
       const next = [...prev];
       const currentItem = { ...next[activeInputIdx] };
       let amountStr = String(currentItem.amount || "");
       if (amountStr === "0" && val !== "000") {
          currentItem.amount = val;
       } else {
          currentItem.amount = amountStr + val;
       }
       next[activeInputIdx] = currentItem;
       return next;
    });
  };

  const handleBackspace = () => {
    setPayments(prev => {
       const next = [...prev];
       const currentItem = { ...next[activeInputIdx] };
       currentItem.amount = String(currentItem.amount || "").slice(0, -1);
       next[activeInputIdx] = currentItem;
       return next;
    });
  };

  // Qaytish hisoblash
  const finalPaid = payments.reduce((s, p) => s + parseAmt(p.amount), 0);
  const isEnough = finalPaid >= totalNet;
  const changeAmt = isEnough ? (finalPaid - totalNet) : 0;
  const remaining = isEnough ? 0 : (totalNet - finalPaid);

  const checkout = async (isDebtConfirm = false) => {
    if (!cart.length) return toast.warn("Savat bo'sh!");
    if (!hasShift) { setShowShiftModal(true); return; }
    
    // Pul yetarli emas va mijoz tanlanmagan → xato
    if (!isEnough && !custId) {
      toast.error("Mijoz tanlanmagan! Qarzga sotish uchun avval mijoz tanlang.");
      return;
    }

    // Pul yetarli emas, lekin mijoz bor → qarz modali
    if (!isEnough && !isDebtConfirm) {
        setShowDebtModal(true);
        return;
    }
    
    setIsPaying(true);
    try {
      let mainType = 'debt';
      if (finalPaid > 0) {
         if (payments.length === 1) mainType = payments[0].type;
         else mainType = 'mixed';
      }

      let pCash = 0, pCard = 0;
      payments.forEach(p => {
         if (p.type === 'cash') pCash += parseAmt(p.amount);
         else if (['card', 'uzcard', 'humo', 'payme', 'click'].includes(p.type)) pCard += parseAmt(p.amount);
      });

      const payload = {
        items: cart.map(c => ({
          product_id: c.product_id,
          quantity: c.qty_ordered,
          unit_price: c.unit_price,
          discount: c.discount_type === 'pct' 
             ? c.unit_price * c.qty_ordered * (c.discount_val / 100) 
             : c.discount_val,
        })),
        payment_type: mainType,
        paid_amount: finalPaid > totalNet ? totalNet : finalPaid,
        paid_cash: pCash > totalNet && mainType === 'cash' ? totalNet : pCash,
        paid_card: pCard,
        discount_amount: totalDiscount,
        note: isDebtConfirm && debtNote ? debtNote : `Chakana sotuv #${orderId}`,
        customer_id: Number(custId) || null,
        debt_due_date: isDebtConfirm && debtDueDate ? debtDueDate : null,
      };

      // Chekni darhol print qilish (API kutilmaydi — tez ishlash uchun)
      if (posSettings.autoPrint) {
        const settings = getReceiptSettings();
        const templateType = posSettings.template || (posSettings.paper === '58mm' ? '58' : '80');
        const tmplCfg = settings['r' + templateType] || settings[templateType] || {};
        const localMeta = {
          id: orderId, number: orderId,
          cashier_name: 'Kassa',
          created_at: new Date().toISOString(),
          total_amount: totalNet,
          paid_amount: finalPaid > totalNet ? totalNet : finalPaid,
          discount_amount: totalDiscount,
          payment_types_array: payments.map(p => ({ type: p.type, amount: parseAmt(p.amount) })),
          items: cart,
        };
        printReceiptHtml(buildReceiptHtml(localMeta, templateType, tmplCfg));
      }

      const result = await submitSaleOrQueue(payload, false);

      setCart([]);
      setPayments([{ type: 'cash', amount: '' }]);
      setActiveInputIdx(0);
      setShowDebtModal(false);
      setDebtDueDate('');
      setDebtNote('');
      setShowCheckout(false);
      setOrderId(Math.floor(Math.random() * 900000) + 100000);
      if (result?.offline) {
         toast.warning("Internet yo'q — sotuv offline saqlandi.");
      } else {
         toast.success("Muvaffaqiyatli sotildi!");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setIsPaying(false);
    }
  };

  return (
    <div className={`font-sans select-none bg-slate-200 flex overflow-hidden ${expanded ? 'fixed inset-0 z-[200]' : 'w-full h-[calc(100vh-65px)]'}`}>
      {showShiftModal && (
        <ShiftOpenModal
          onOpened={() => { reloadShift(); setShowShiftModal(false); }}
          onCancel={() => setShowShiftModal(false)}
        />
      )}
      
      {/* ── LEFT PANE: CHECKOUT & CART ── */}
      <div className="w-[450px] bg-white flex flex-col shadow-2xl z-20 shrink-0">
        
        {/* HEADER */}
        <div className="bg-slate-900 text-white px-2 py-1.5 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/admin/dashboard')} className="w-8 h-8 bg-white/10 hover:bg-white/20 rounded-lg flex items-center justify-center transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/></svg>
            </button>
            <div className="font-black text-lg tracking-wider">{t('pos.retailCashier')}</div>
          </div>
          <div className="flex gap-2">
            {!isOnline && <span className="bg-red-500 font-bold px-2.5 py-1 rounded text-xs animate-pulse">OFFLINE</span>}
            <button onClick={() => setShowSettings(true)} className="w-8 h-8 bg-white/10 hover:bg-white/20 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            </button>
          </div>
        </div>

        {/* CUSTOMER SELECTOR */}
        <div className="p-1 px-2 border-b border-slate-200 bg-slate-50 shrink-0">
           <CustSearch customers={customers} value={custId} onChange={setCustId} placeholder={t('pos.customerSearch')} />
        </div>

        {/* CART LIST */}
        <div className="flex-1 overflow-y-auto bg-slate-100 p-0.5 space-y-0.5">
          {cart.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400">
              <svg className="w-20 h-20 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              <span className="font-bold">{t('pos.scanProduct')}</span>
            </div>
          ) : (
            cart.map((item, i) => (
              <div key={i} className="bg-white p-0.5 rounded shadow-sm border border-slate-200 relative group flex gap-1">
                <div className="w-1.5 bg-blue-500 absolute left-0 top-0 bottom-0 rounded-l-xl"></div>
                <div className="flex-1 pl-2">
                  <div className="font-black text-slate-800 text-[10px] leading-tight line-clamp-2 leading-none">{item.product_name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5 w-full justify-between">
                    {/* Quantity controls */}
                    <div className="flex items-center bg-slate-100 border border-slate-200 rounded-lg overflow-hidden shrink-0">
                      <button onClick={()=>updateCartQty(i, -1)} className="w-8 h-8 flex items-center justify-center text-slate-600 font-bold hover:bg-slate-200">−</button>
                      <input 
                         type="number" 
                         value={item.qty_ordered} 
                         onChange={(e)=>updateExtQty(i, e.target.value)}
                         className="w-8 h-6 text-center font-bold text-[11px] bg-white border-x border-slate-200 outline-none focus:ring-2 focus:ring-blue-500" 
                      />
                      <button onClick={()=>updateCartQty(i, 1)} className="w-6 h-6 flex items-center justify-center text-slate-600 font-bold hover:bg-slate-200 text-xs">+</button>
                    </div>
                    <div className="font-bold text-slate-400 text-[10px]">× {fmt(item.unit_price)}</div>
                  </div>
                  {/* Discount inline input */}
                  <div className="mt-0 flex items-center">
                    
                    <input 
                      type="text" 
                      value={item.discount_val || ''}
                      onChange={e => updateDiscount(i, cleanNum(e.target.value))}
                      placeholder="0"
                      className="w-12 border border-slate-200 rounded px-1 py-0 text-[10px] h-5 font-bold text-red-500 outline-none focus:border-red-400 focus:ring-1 focus:ring-red-400 placeholder:text-slate-300"
                    />
                  </div>
                </div>
                <div className="flex flex-col items-end justify-between shrink-0">
                   <button onClick={()=>removeCartItem(i)} className="w-4 h-4 bg-red-50 hover:bg-red-500 text-red-500 hover:text-white rounded flex items-center justify-center transition-colors">
                     <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                   </button>
                   <div className="text-right mt-0.5">
                     {item.discount_val > 0 && <div className="text-[10px] text-slate-400 line-through">{fmt(item.unit_price * item.qty_ordered)}</div>}
                     <div className="font-black text-[13px] text-slate-800 leading-none mt-1">{fmt((item.unit_price * item.qty_ordered) - item.discount_val)}</div>
                   </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* TOTAL PAY PANEL */}
        <div className="bg-white border-t border-slate-200 flex flex-col px-2 py-1 shrink-0 z-30">
          <div className="flex justify-between items-center mb-0.5 text-slate-500 leading-none">
            <span className="font-bold text-[10px] uppercase">{t('admin.dict.total_colon') || 'Jami:'}</span>
            <span className="font-bold">{fmt(totalSubtotal)}</span>
          </div>
          <div className="flex justify-between items-center mb-0.5 text-red-500 leading-none">
            <span className="font-bold text-[10px] uppercase">{t('pos.discountLabel')}</span>
            <span className="font-bold">-{fmt(totalDiscount)}</span>
          </div>
          <div className="flex justify-between items-end mb-1 leading-none">
            <span className="font-black text-[11px] uppercase text-slate-800">{t('pos.toPayLabel')}</span>
            <span className="font-black text-xl text-blue-700">{fmt(totalNet)} <span className="text-[10px]">UZS</span></span>
          </div>
          <button 
            onClick={() => {
              if(!cart.length) return;
              setShowCheckout(true);
            }}
            className="w-full bg-blue-600 hover:bg-blue-700 active:scale-95 text-white font-black text-[13px] h-8 rounded-md flex items-center justify-center gap-1 shadow-sm uppercase"
          >
             <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
             {t('pos.payNow')}
          </button>
        </div>
      </div>

      {/* ── RIGHT PANE: PRODUCTS GRID ── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-slate-100">
         {/* Top Header Filter */}
         <div className="bg-white px-6 py-4 border-b border-slate-200 flex items-center gap-6 shadow-sm shrink-0">
           <div className="flex-1 max-w-xl position-relative flex items-center border-[2px] border-slate-300 focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-500/20 rounded-2xl bg-slate-50 px-4 py-3 transition-all">
             <svg className="w-6 h-6 text-slate-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
             <input 
               value={search} onChange={e=>setSearch(e.target.value)} 
               placeholder={t('pos.searchBarcode')}
               className="flex-1 bg-transparent border-none outline-none font-bold text-slate-700 placeholder:text-slate-400 text-lg" 
             />
             {search && <button onClick={()=>setSearch('')} className="text-slate-400 hover:text-red-500 font-bold text-2xl px-2">&times;</button>}
           </div>
           
           <button onClick={()=>{if(!document.fullscreenElement) document.documentElement.requestFullscreen(); else document.exitFullscreen();}} className="ml-auto w-12 h-12 bg-white border border-slate-200 rounded-xl flex items-center justify-center text-slate-500 hover:bg-slate-50 hover:text-blue-600 transition-colors shadow-sm">
             <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
           </button>
         </div>

         {/* Categories */}
         <div className="border-b border-slate-200 bg-white">
           <div className="flex px-4 py-3 gap-2 overflow-x-auto scrollbar-hide snap-x">
             <button onClick={()=>setActiveCat(null)} className={`px-5 py-2.5 rounded-xl font-black whitespace-nowrap snap-start border-2 transition-all ${!activeCat ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
                {t('pos.allCategories')}
             </button>
             {categories.map(c => (
               <button key={c.id} onClick={()=>setActiveCat(c.id)} className={`px-5 py-2.5 rounded-xl font-bold whitespace-nowrap snap-start border-2 transition-all ${activeCat===c.id ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
                 {c.name.toUpperCase()}
               </button>
             ))}
           </div>
         </div>

         {/* Grid */}
         <div className="flex-1 overflow-y-auto p-6">
            {/* Yangilanish indikatori */}
            {refreshing && products.length > 0 && (
              <div className="flex items-center gap-2 text-xs text-slate-400 font-bold mb-3 animate-pulse">
                <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg>
                {t('pos.refreshing')}
              </div>
            )}
            <div className="grid grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
              {displayedProducts.map(p => (
                <button key={p.id} onClick={() => addToCart(p)} className="bg-white rounded-2xl border-2 border-transparent hover:border-blue-500 p-4 shadow-sm hover:shadow-xl transition-all text-left flex flex-col active:scale-95 relative overflow-hidden group h-[160px]">
                  <div className="absolute -top-10 -right-10 w-24 h-24 bg-blue-50 rounded-full group-hover:scale-[2] transition-transform duration-500 ease-out z-0"></div>
                  <h3 className="font-extrabold text-slate-800 text-base leading-tight mb-auto z-10 line-clamp-3">{p.name}</h3>
                  <div className="z-10 mt-2">
                    <div className="text-xl font-black text-blue-700 tracking-tight">{fmt(p.sale_price)}</div>
                    <div className="text-xs font-bold text-slate-400 mt-1">{t('pos.stockLabel')} <span className={p.stock_quantity<=p.min_stock?'text-red-500':'text-emerald-500'}>{p.stock_quantity>0 ? `${fmt(p.stock_quantity)} ${p.unit||'dona'}` : t('pos.zeroStock')}</span></div>
                  </div>
                </button>
              ))}
            </div>
            {/* 150 dan ko'p bo'lsa — hint */}
            {!search && !activeCat && filteredProducts.length > GRID_CAP && (
              <div className="mt-6 text-center text-sm text-slate-400 font-semibold py-3 bg-white rounded-2xl border border-slate-100">
                📦 {t('common.total')} <span className="font-black text-slate-600">{filteredProducts.length}</span> {t('pos.productsHint')}
              </div>
            )}
            {filteredProducts.length === 0 && !refreshing && (
               <div className="w-full py-20 flex flex-col items-center justify-center text-slate-400">
                  <svg className="w-20 h-20 mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>
                  <div className="font-bold text-xl uppercase tracking-widest">{t('pos.nothingFound')}</div>
               </div>
            )}
            {products.length === 0 && refreshing && (
               <div className="w-full py-20 flex flex-col items-center justify-center text-slate-400 gap-4">
                  <svg className="w-12 h-12 animate-spin text-blue-400" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg>
                  <div className="font-bold text-lg">{t('pos.productsLoading')}</div>
               </div>
            )}
         </div>
      </div>

      {/* ── CHECKOUT MODAL ── */}
      {showCheckout && (
        <div className="fixed inset-0 z-50 flex bg-slate-900/80 backdrop-blur-sm pt-4 animate-in slide-in-from-bottom-5 duration-300">
          <div className="mt-auto w-full h-[90vh] bg-white rounded-t-[40px] shadow-2xl flex flex-col overflow-hidden">
             
             {/* Header */}
             <div className="flex items-center justify-between px-10 py-6 border-b border-slate-100 bg-slate-50">
               <h2 className="text-3xl font-black text-slate-800 tracking-tight">{t('pos.checkoutTitle')}</h2>
               <button onClick={()=>setShowCheckout(false)} className="w-12 h-12 rounded-full bg-slate-200 text-slate-500 flex items-center justify-center hover:bg-slate-300 transition-colors">
                 <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
               </button>
             </div>

             <div className="flex flex-1 overflow-hidden">
               {/* Payment Numpad Section */}
               <div className="w-[60%] flex flex-col p-8 border-r border-slate-100">
                 
                 {/* Input Display Area */}
                 <div className="bg-slate-50 border border-slate-200 rounded-3xl p-6 mb-6 flex flex-col relative z-0 max-h-[300px] overflow-y-auto">
                    <div className="flex justify-between items-end mb-1 leading-none">
                       <span className="font-bold text-slate-400 uppercase tracking-widest text-sm">{t('pos.amountDue')}</span>
                       <span className="font-black text-2xl text-slate-700">{fmt(totalNet)}</span>
                    </div>

                    {payments.map((p, idx) => (
                      <div key={idx} className={`mt-2 flex gap-3 items-center bg-white border-[3px] ${activeInputIdx===idx?'border-blue-500 ring-4 ring-blue-500/20':'border-slate-200'} rounded-2xl px-4 py-3 cursor-pointer transition-all`} onClick={()=>setActiveInputIdx(idx)}>
                         <select value={p.type} onChange={e => {
                            const next = [...payments]; next[idx].type = e.target.value; setPayments(next);
                         }} className="bg-transparent font-black text-slate-600 outline-none uppercase cursor-pointer">
                            <option value="cash">NAQD</option>
                            <option value="card">KARTA</option>
                            <option value="uzcard">UZCARD</option>
                            <option value="humo">HUMO</option>
                            <option value="payme">PAYME</option>
                            <option value="click">CLICK</option>
                            <option value="bank">{t('pos.transferLabel')}</option>
                         </select>
                         <div className={`flex-1 text-right text-3xl font-black tracking-tight ${p.amount?'text-emerald-500':'text-slate-300'}`}>{p.amount ? fmt(parseAmt(p.amount)) : "0"}</div>
                         {payments.length > 1 && (
                            <button onClick={(e)=>{ e.stopPropagation(); setPayments(prev => prev.filter((_, i) => i !== idx)); setActiveInputIdx(0); }} className="text-rose-400 hover:text-white hover:bg-rose-500 w-8 h-8 rounded-xl flex items-center justify-center transition-colors">
                               <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                         )}
                      </div>
                    ))}

                    <button onClick={()=>{setPayments([...payments, {type:'cash', amount:''}]); setActiveInputIdx(payments.length);}} className="mt-3 w-full py-3 border-2 border-dashed border-blue-300 hover:bg-blue-50 hover:border-blue-500 text-blue-600 font-bold rounded-2xl text-sm transition-all flex items-center justify-center gap-2">
                       <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M12 4v16m8-8H4"/></svg> {t('pos.mixPayment')}
                    </button>
                 </div>

                 {/* Numpad */}
                 <div className="flex-1 flex gap-4">
                    <div className="flex-1 grid grid-cols-3 gap-3">
                      {[1,2,3,4,5,6,7,8,9,'000',0,'00',{l:'C', v:'C', c:'col-span-3 bg-red-50 text-red-500 border-red-200'}].map((n,i) => (
                        <button key={i} onClick={()=>{
                           if(typeof n === 'object') {
                              if(n.v==='C') { 
                                setPayments(prev => { const nxt = [...prev]; nxt[activeInputIdx].amount = ''; return nxt; });
                              }
                              else handleNumClick(n.v);
                           } else handleNumClick(String(n));
                        }} className={`rounded-2xl border-[3px] text-3xl font-black flex items-center justify-center transition-all active:scale-95 ${typeof n==='object' && n.c ? n.c : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300'}`}>
                           {typeof n === 'object' ? n.l : n}
                        </button>
                      ))}
                    </div>
                    {/* Quick mounts & Actions */}
                    <div className="w-[120px] flex flex-col gap-3">
                       <button onClick={()=>handleBackspace()} className="flex-1 bg-slate-100 hover:bg-slate-200 border-[3px] border-slate-200 text-slate-500 rounded-2xl flex items-center justify-center active:scale-95 transition-all"><svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M3 12l6.414 6.414a2 2 0 001.414.586H19a2 2 0 002-2V7a2 2 0 00-2-2h-8.172a2 2 0 00-1.414.586L3 12z"/></svg></button>
                       <button onClick={()=>handleNumClick('50000')} className="flex-1 bg-emerald-50 hover:bg-emerald-100 border-[3px] border-emerald-200 text-emerald-600 rounded-2xl flex items-center justify-center active:scale-95 transition-all font-black text-xl">50k</button>
                       <button onClick={()=>handleNumClick('100000')} className="flex-1 bg-emerald-50 hover:bg-emerald-100 border-[3px] border-emerald-200 text-emerald-600 rounded-2xl flex items-center justify-center active:scale-95 transition-all font-black text-xl">100k</button>
                       <button onClick={()=>{
                          setPayments(prev => { 
                             const nxt = [...prev]; 
                             const otherSum = nxt.reduce((s, p, i) => i === activeInputIdx ? s : s + parseAmt(p.amount), 0);
                             nxt[activeInputIdx].amount = String(Math.max(0, totalNet - otherSum));
                             return nxt; 
                          });
                       }} className="flex-1 bg-indigo-50 hover:bg-indigo-100 border-[3px] border-indigo-200 text-indigo-600 rounded-2xl flex items-center justify-center active:scale-95 transition-all font-black text-sm uppercase px-2 text-center leading-tight">{t('pos.exactAmount')}</button>
                    </div>
                 </div>
               </div>

               {/* Right Summary Section */}
               <div className="flex-1 flex flex-col p-8 bg-slate-50">
                  <div className="bg-white rounded-3xl p-6 shadow-xl shadow-slate-200/50 border border-slate-100 flex-1 flex flex-col">
                     
                     <div className="space-y-4 mb-6">
                        <div className="flex justify-between items-center text-slate-500 font-bold">
                          <span className="uppercase text-sm tracking-widest">{t('pos.totalBill')}</span>
                          <span className="text-xl">{fmt(totalNet)} UZS</span>
                        </div>
                        <div className="flex justify-between items-center text-emerald-600 font-black border-t-2 border-dashed border-slate-200 pt-4">
                          <span className="uppercase text-lg tracking-widest">{t('pos.entered')}</span>
                          <span className="text-2xl">{fmt(finalPaid)} UZS</span>
                        </div>
                        
                        {/* Qaytim or Qarz indikatori */}
                        <div className={`flex justify-between items-center mt-4 p-4 rounded-2xl border-[3px] ${isEnough ? 'bg-emerald-50 border-emerald-500 text-emerald-700' : 'bg-rose-50 border-rose-500 text-rose-700'}`}>
                           <span className="uppercase font-black text-lg tracking-widest">{isEnough ? t('pos.change').toUpperCase()+':' : t('pos.shortage')}</span>
                           <span className="font-black text-3xl">{isEnough ? fmt(changeAmt) : fmt(remaining)}</span>
                        </div>
                     </div>

                     <div className="mt-auto pt-6">
                        <button 
                           onClick={() => checkout()}
                           disabled={isPaying}
                           className="w-full bg-emerald-500 hover:bg-emerald-600 active:scale-95 text-white font-black text-2xl uppercase tracking-widest py-6 rounded-2xl shadow-xl shadow-emerald-500/40 transition-all disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-4"
                        >
                           {isPaying ? t('pos.paying') : <>
                             <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7"/></svg>
                             {t('pos.confirmPay')}
                           </>}
                        </button>
                     </div>
                  </div>
               </div>

             </div>
          </div>
        </div>
      )}

      {/* ── YANGI MAHSULOT QO'SHISH MODALI ── */}
      {showNewProduct && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-900/70 p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg flex flex-col overflow-hidden">
            <div className="bg-amber-500 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-black text-white">{t('pos.newProductTitle')}</h2>
                <p className="text-amber-100 text-sm font-medium mt-0.5">{t('pos.barcodeNotFound')}</p>
              </div>
              <button onClick={() => setShowNewProduct(false)} className="w-10 h-10 bg-white/20 hover:bg-white/30 rounded-xl flex items-center justify-center text-white transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>

            <div className="p-6 flex flex-col gap-4 overflow-y-auto">
              {/* Shtrix kod (o'zgartirib bo'ladi) */}
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Shtrix kod / SKU</label>
                <input
                  value={newProd.barcode}
                  onChange={e => setNewProd(p => ({...p, barcode: e.target.value}))}
                  className="w-full border-2 border-amber-300 bg-amber-50 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/20"
                  placeholder="Shtrix kod..."
                />
              </div>

              {/* Nomi */}
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('pos.productName')} <span className="text-red-500">*</span></label>
                <input
                  autoFocus
                  value={newProd.name}
                  onChange={e => setNewProd(p => ({...p, name: e.target.value}))}
                  onKeyDown={e => e.key === 'Enter' && saveNewProduct()}
                  className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20"
                  placeholder="Mahsulot nomini kiriting..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* Sotuv narxi */}
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('product.salePrice')} <span className="text-red-500">*</span></label>
                  <input
                    type="number"
                    value={newProd.sale_price}
                    onChange={e => setNewProd(p => ({...p, sale_price: e.target.value}))}
                    className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20"
                    placeholder="0"
                    min="0"
                  />
                </div>
                {/* Tan narxi */}
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('product.costPrice')}</label>
                  <input
                    type="number"
                    value={newProd.cost_price}
                    onChange={e => setNewProd(p => ({...p, cost_price: e.target.value}))}
                    className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20"
                    placeholder="0"
                    min="0"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* O'lchov birligi */}
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('product.unit')}</label>
                  <select
                    value={newProd.unit}
                    onChange={e => setNewProd(p => ({...p, unit: e.target.value}))}
                    className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 bg-white"
                  >
                    {['dona','kg','g','litr','ml','metr','sm','paket','quti','juft','set','rol'].map(u => (
                      <option key={u} value={u}>{u}</option>
                    ))}
                  </select>
                </div>
                {/* Boshlang'ich qoldiq */}
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('pos.initialStock')}</label>
                  <input
                    type="number"
                    value={newProd.stock_quantity}
                    onChange={e => setNewProd(p => ({...p, stock_quantity: e.target.value}))}
                    className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20"
                    placeholder="0"
                    min="0"
                  />
                </div>
              </div>

              {/* Kategoriya */}
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('admin.dict.category') || 'Kategoriya'}</label>
                <select
                  value={newProd.category_id}
                  onChange={e => setNewProd(p => ({...p, category_id: e.target.value}))}
                  className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 bg-white"
                >
                  <option value="">{t('pos.noCategory')}</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            </div>

            <div className="px-6 pb-6 flex gap-3">
              <button
                onClick={() => setShowNewProduct(false)}
                className="flex-1 py-4 bg-slate-100 hover:bg-slate-200 text-slate-600 font-black rounded-2xl transition-colors active:scale-95"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={saveNewProduct}
                disabled={savingProd}
                className="flex-2 py-4 bg-emerald-500 hover:bg-emerald-600 text-white font-black rounded-2xl shadow-lg shadow-emerald-500/30 transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2 min-w-[200px]"
              >
                {savingProd
                  ? <><svg className="animate-spin w-5 h-5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg> {t('common.saving')}</>
                  : <><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg> {t('pos.saveAndAdd')}</>
                }
              </button>
            </div>
          </div>
        </div>
      )}

      {showSettings && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 p-4">
           <div className="bg-white rounded-3xl p-8 max-w-xl w-full shadow-2xl">
             <h2 className="text-2xl font-black text-slate-800 mb-6">Kassa Sozlamalari</h2>
             <div className="space-y-4">
               <div>
                  <label className="block text-sm font-bold text-slate-500 mb-2">Qog'oz o'lchami</label>
                  <select value={posSettings.paper} onChange={e=>savePosSettings({paper:e.target.value})} className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500">
                    <option value="80mm">80mm Keng qog'oz</option>
                    <option value="58mm">58mm Tor qog'oz</option>
                  </select>
               </div>
               <div>
                  <label className="block text-sm font-bold text-slate-500 mb-2">Chek Shabloni (Bozor/Layout)</label>
                  <select value={posSettings.template || '80'} onChange={e=>savePosSettings({template:e.target.value})} className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500">
                    <option value="80">Chek 80mm Template</option>
                    <option value="58">Chek 58mm Template</option>
                    <option value="nak">A4 Nakladnoy Template</option>
                  </select>
               </div>
               <div className="border border-blue-200 rounded-xl p-3 bg-blue-50/50 flex items-start gap-2">
                  <svg className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <p className="text-xs font-semibold text-blue-600">Do'kon nomi, logotip va boshqalar → <b>Nastroyka → Chek shabloni</b></p>
               </div>
               <div className="flex items-center gap-3 pt-4">
                  <input type="checkbox" id="ap" checked={posSettings.autoPrint} onChange={e=>savePosSettings({autoPrint:e.target.checked})} className="w-6 h-6 rounded" />
                  <label htmlFor="ap" className="font-bold text-slate-700 cursor-pointer">Avtomatik chek chiqarishni yoqish</label>
               </div>
               <div className="pt-4 border-t border-slate-100 mt-2">
                  <label className="block text-sm font-bold text-slate-600 mb-2">Doimiy mijoz (standart)</label>
                  <select
                    value={posSettings.defaultCustomer || ''}
                    onChange={e => { savePosSettings({ defaultCustomer: e.target.value }); setCustId(e.target.value); }}
                    className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500"
                  >
                    <option value="">-- Tanlanmagan --</option>
                    {customers.map(c => <option key={c.id} value={c.id}>{c.name}{c.phone ? ` (${c.phone})` : ''}</option>)}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">Kassa ochilganda avtomatik tanlanadi</p>
               </div>
             </div>
             <div className="mt-8 flex justify-end gap-3">
               <button onClick={()=>setShowSettings(false)} className="px-6 py-3 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-xl active:scale-95 transition-all">{t('admin.dict.close') || 'Yopish'}</button>
             </div>
           </div>
        </div>
      )}

      {showDebtModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm flex flex-col overflow-hidden">
             <div className="bg-rose-500 px-6 py-4 flex items-center justify-between">
               <h2 className="text-xl font-black text-white">Qarz Muddatini Belgilang</h2>
               <button onClick={()=>setShowDebtModal(false)} className="text-white opacity-70 hover:opacity-100 transition-colors">
                 <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
               </button>
             </div>
             <div className="p-6 space-y-4">
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex justify-between items-center">
                   <span className="font-bold text-slate-500 uppercase text-xs">Qarz Summasi</span>
                   <span className="font-black text-xl text-rose-600">{fmt(remaining)} UZS</span>
                </div>
                <div>
                   <label className="block text-xs font-bold text-slate-500 mb-2 uppercase">Qaytarish Sanasi</label>
                   <input type="date" value={debtDueDate} onChange={e=>setDebtDueDate(e.target.value)} className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500" />
                </div>
                <div>
                   <label className="block text-xs font-bold text-slate-500 mb-2 uppercase">Izoh (Ixtiyoriy)</label>
                   <input type="text" value={debtNote} onChange={e=>setDebtNote(e.target.value)} placeholder="Qarz sababi..." className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500" />
                </div>
             </div>
             <div className="p-6 pt-0 flex gap-3">
                <button onClick={()=>setShowDebtModal(false)} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl active:scale-95 transition-all">{t('common.back')}</button>
                <button onClick={()=>checkout(true)} disabled={isPaying || !debtDueDate} className="flex-1 py-3 bg-rose-500 hover:bg-rose-600 disabled:opacity-50 text-white font-black rounded-xl active:scale-95 transition-all text-sm uppercase tracking-widest">
                  {isPaying ? 'To\'lanmoqda...' : 'Tasdiqlash'}
                </button>
             </div>
          </div>
        </div>
      )}

    </div>
  );
}



