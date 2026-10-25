import { useState, useEffect, useRef, useMemo } from 'react';
import { matchesSearch } from '../../utils/translit';
import { useLang } from '../../context/LangContext';
import { useNavigate } from 'react-router-dom';
import usePosSync from '../../hooks/usePosSync';
import useCompanyFeatures from '../../hooks/useCompanyFeatures';
import {
  describeRejection, fmtExpiry, todayLocalIso, rxProductsOf, isControlled, validateRx, buildRxPayload, unitLinePrice, wholeBoxMax,
  parseWholeBoxError, getPending, setPending, REJECTED_SALES_KEY, getCurrentCompanyId,
} from '../../utils/posQueue';
import { toast } from '../../utils/toast';
import api from '../../api/axios';
import { getReceiptSettings, saveReceiptSettings, buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import { useActiveShift } from '../../hooks/useActiveShift';
import CustomerPicker from '../../components/CustomerPicker';
import ShiftOpenModal from '../../components/ShiftOpenModal';
import ShiftCloseModal from '../../components/ShiftCloseModal';
import { registerReceipt, fiscalizeAndPrint } from '../../api/hippoLocal';
import { parseScaleBarcode, findScaleProduct } from '../../utils/scale';
import { GS, parseGs1Scan, gtinVariants, productMatchesGtin, createGsDetector } from '../../utils/gs1';
import { useApprovalFlow, ApprovalModal } from './Approvals'; // T4.6: menejer tasdig'i


const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const cleanNum = (str) => Number(String(str).replace(/\D/g, ''));
const parseAmt = (str) => parseInt(String(str || '').replace(/\D/g, ''), 10) || 0;
// Sodiqlik kartasi: faqat raqamlar (server app/utils/loyalty_card.py normalize_card bilan bir xil)
const normCard = (s) => String(s || '').replace(/\D/g, '');

/* Mijoz tanlash: T3.8 — serverdagi qidiruv (components/CustomerPicker.jsx); `customers` — oflayn zaxira */

export default function PosKassa() {
  const { t } = useLang();
  // Kalit lug'atda bo'lmasa o'zbekcha zaxira matn (T2.12 kalitlari umumiy lug'atga keyin qo'shiladi)
  const tf = (key, fallback, vars) => {
    const s = t(key, vars);
    if (s !== key) return s;
    return Object.entries(vars || {}).reduce((a, [k, v]) => a.split(`{${k}}`).join(String(v)), fallback);
  };
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

  // T1.17: qoldiq tanlangan ombor (filial) bo'yicha; kesh kaliti korxona/filial/ombor bilan ajratiladi
  const branchKey = (() => { try { return localStorage.getItem('current_branch_id') || ''; } catch { return ''; } })();
  const whMemKey = `pos_warehouse:${currentCompanyId ?? ''}:${branchKey}`;
  const [warehouseId, setWarehouseId] = useState(() => { try { return localStorage.getItem(whMemKey) || ''; } catch { return ''; } });
  const [posWarehouses, setPosWarehouses] = useState([]);
  const [posBranchId, setPosBranchId] = useState(null);   // T3.18: terminal tanlash uchun joriy filial
  // T4.2: filial rekvizitlari va filial chek shabloni — server javobini (yoki oflayn navbatni) kutmasdan chop etish uchun
  const [branchInfo, setBranchInfo] = useState(() => {
    try { return branchKey ? JSON.parse(localStorage.getItem(`pos_branch_info:${currentCompanyId ?? ''}:${branchKey}`) || 'null') : null; } catch { return null; }
  });
  const [products, setProducts] = useState(() => readCache(`pos_cache_products:${currentCompanyId ?? ''}:${branchKey}:${warehouseId}`));
  const [customers, setCustomers] = useState([]);
  const [categories, setCategories] = useState(() => readCache('pos_cache_categories'));
  const [refreshing, setRefreshing] = useState(false);
  
  // Savat va UI holatlari
  const [cart, setCart] = useState([]);

  // D2.6: dorixona rejimi — faqat korxonada modul yoqilgan bo'lsa dorixona elementlari ko'rinadi
  const features = useCompanyFeatures();
  const pharmacy = !!features?.pharmacy;
  const rxMode = features?.pharmacy_settings?.rx_mode === 'block' ? 'block' : 'warn';
  const [rxModal, setRxModal] = useState(null);        // { message?, onDone? } — retsept oynasi
  const [rxData, setRxData] = useState({});            // { [product_id]: { mode, number, issued_at, doctor, clinic, patient, blank_type } }
  const [rxReason, setRxReason] = useState('');        // retseptsiz sotish sababi (rx_mode=warn)
  const [analogModal, setAnalogModal] = useState(null); // { product_id, name, loading, items, auto }
  const [unitPick, setUnitPick] = useState(null);     // P.7: { p, qty, sel } — quti / blister / dona tanlash
  const [saleError, setSaleError] = useState(null);    // { message, boxFix? } — server 400 xatosi (muddat, quti, markirovka...)
  const [rejectedModal, setRejectedModal] = useState(false);
  const [rejectedTick, setRejectedTick] = useState(0);
  const [custId, setCustId] = useState('');
  // T3.19: tanlangan mijozning individual narxlari { [product_id]: price }
  const [custPrices, setCustPrices] = useState({});
  // Tanlangan mijozning YANGI (backenddan) qarz malumoti - ro'yxatdagi
  // nusxa sahifa ochilgandagi holat bolib, eskirgan bolishi mumkin.
  const [freshCust, setFreshCust] = useState(null);
  // Keshbek / ball bilan to'lash (T2.12): so'm va ball miqdori (matn)
  const [redeemCash, setRedeemCash] = useState('');
  const [redeemPts, setRedeemPts] = useState('');
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState(null);
  const [variantParent, setVariantParent] = useState(null);
  
  const [showSettings, setShowSettings] = useState(false);
  const [showCheckout, setShowCheckout] = useState(false);
  const [isPaying, setIsPaying] = useState(false);

  // Buyurtma raqami generatori

  // Yangi mahsulot qo'shish modali
  const [showNewProduct, setShowNewProduct] = useState(false);
  const [newProd, setNewProd] = useState({ name:'', barcode:'', sale_price:'', cost_price:'', unit:'dona', category_id:'', stock_quantity:'0' });
  const [savingProd, setSavingProd] = useState(false);
  const { shift: activeShift, hasShift, reload: reloadShift } = useActiveShift();
  const [showShiftModal, setShowShiftModal] = useState(false);
  const [showShiftClose, setShowShiftClose] = useState(false);   // T3.1: POS ichidan smenani yopish

  // Sync hooks
  const { isOnline, syncing, pendingCount, submitSaleOrQueue, fetchProducts, fetchPosContext, fetchCustomers, fetchCategories } = usePosSync({
    onSyncSuccess: (count) => {
      toast.success(`✅ ${t('pos.offlineSalesSynced', { count })}`);
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

  // T4.3: narx filiali — ombor tanlangan bo'lsa server uning filialidan oladi, aks holda kassir filiali (branch_id)
  const posPriceParams = (wid, bid) => (wid ? { warehouse_id: wid } : (bid ? { branch_id: bid } : {}));

  // Ombor almashtirish: qoldiq yangi ombor bo'yicha qayta yuklanadi, savatdagi max_stock yangilanadi
  const changeWarehouse = (wid) => {
    setWarehouseId(wid);
    try { if (wid) localStorage.setItem(whMemKey, wid); else localStorage.removeItem(whMemKey); } catch { /* ignore */ }
    setRefreshing(true);
    fetchProducts(posPriceParams(wid, posBranchId)).then(prods => {
      setProducts(prods);
      setCart(prev => prev.map(i => {
        const p = prods.find(x => x.id === i.product_id);
        return p ? { ...i, max_stock: p.stock_quantity } : i;
      }));
    }).finally(() => setRefreshing(false));
  };

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
    // Ombor kontekstini olib, qoldiqni tanlangan (default) ombor bo'yicha yuklash
    const loadProductsForWarehouse = async () => {
      const posCtx = await fetchPosContext();
      const whs = posCtx?.warehouses || [];
      setPosWarehouses(whs);
      setPosBranchId(posCtx?.branch_id ?? null);
      let wid = warehouseId;
      if (posCtx) {
        wid = whs.some(w => String(w.id) === String(warehouseId)) ? String(warehouseId) : '';
        if (!wid) wid = posCtx.default_warehouse_id ? String(posCtx.default_warehouse_id) : (whs.length === 1 ? String(whs[0].id) : '');
      }
      setWarehouseId(wid);
      try { if (wid) localStorage.setItem(whMemKey, wid); else localStorage.removeItem(whMemKey); } catch { /* ignore */ }
      return fetchProducts(posPriceParams(wid, posCtx?.branch_id ?? null));
    };
    Promise.all([
      fetchCategories(),
      loadProductsForWarehouse(),
      fetchCustomers(),
    ]).then(([cats, prods, custs]) => {
      setCategories(cats);
      setProducts(prods);
      setCustomers(custs);
      const s = JSON.parse(localStorage.getItem('pos_desktop_settings') || '{}');
      if (s.defaultCustomer) setCustId(s.defaultCustomer);
    }).finally(() => setRefreshing(false));

    // Chek shabloni sozlamalarini kompaniya (backend) dan sinxronlash - aks
    // holda bu terminal hech qachon Sozlamalar sahifasini ochmagan bo'lsa,
    // eski/bo'sh shablon bilan chop etaveradi.
    api.get('/companies/me/receipt_templates').then(r => {
      const d = r.data?.receipt_templates || {};
      if (d.r58 || d.r80 || d.nak) {
        const existing = getReceiptSettings();
        saveReceiptSettings({
          ...existing,
          ...(d.r58 ? { r58: d.r58 } : {}),
          ...(d.r80 ? { r80: d.r80 } : {}),
          ...(d.nak ? { nak: d.nak } : {}),
        });
      }
    }).catch(() => { /* ignore - lokal keshdan foydalanaveradi */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // T4.2: joriy filial rekvizitlari + filial chek shabloni (bo'sh shablon = korxona shabloni). Xato bo'lsa lokal kesh qoladi.
  useEffect(() => {
    if (!posBranchId) return;
    api.get(`/branches/${posBranchId}/receipt_templates`, { _suppressToast: true }).then(r => {
      const info = { ...(r.data?.branch || {}), receipt_templates: r.data?.receipt_templates || {} };
      setBranchInfo(info);
      try { localStorage.setItem(`pos_branch_info:${currentCompanyId ?? ''}:${posBranchId}`, JSON.stringify(info)); } catch { /* ignore */ }
    }).catch(() => { /* oflayn: kesh ishlatiladi */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posBranchId]);

  // Mijozni tanlash: serverdan topilgan (500 talik ro'yxatda yo'q) mijoz ro'yxatga qo'shiladi
  const addCustomerToList = (c) => setCustomers(prev => (prev.some(x => x.id === c.id) ? prev : [c, ...prev]));
  const pickCustomer = (id, c) => {
    if (c) addCustomerToList(c);
    setCustId(id);
  };

  // T3.19: narx hal qilish — backend resolve_item_pricing bilan bir xil: maxsus narx > narx turi > sotuv narxi
  const selectedCust = customers.find(c => String(c.id) === String(custId)) || null;
  const priceCtxRef = useRef({ prices: {}, cust: null });
  priceCtxRef.current = { prices: custPrices, cust: selectedCust };
  const priceFor = (p, ctx = priceCtxRef.current) => {
    const special = ctx.prices?.[p.id];
    if (special != null && Number(special) > 0) return Number(special);
    const pt = ctx.cust?.price_type;
    if (pt === 'wholesale') return Number(p.wholesale_price || p.sale_price) || 0;
    if (pt === 'cost') return Number(p.cost_price || p.sale_price) || 0;
    return Number(p.sale_price) || 0;
  };
  // Mijozning doimiy chegirma foizi (qatorda chegirma bo'lmasa oldindan qo'yiladi)
  const custDiscountPct = (ctx = priceCtxRef.current) => {
    const v = Number(ctx.cust?.discount_percent) || 0;
    return v > 0 ? v : 0;
  };

  useEffect(() => {
    setCustPrices({});
    if (!custId || !isOnline) return undefined;
    let cancelled = false;
    api.get(`/customers/${custId}/prices`, { _silent: true, _suppressToast: true })
      .then(r => {
        if (cancelled) return;
        const map = {};
        (Array.isArray(r.data) ? r.data : []).forEach(row => { map[row.product_id] = Number(row.price); });
        setCustPrices(map);
      })
      .catch(() => { });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [custId]);

  // Mijoz / uning narxlari o'zgarganda savat qatorlari narxi va chegirmasi qayta hisoblanadi
  useEffect(() => {
    const ctx = { prices: custPrices, cust: selectedCust };
    const pct = custDiscountPct(ctx);
    setCart(prev => {
      let changed = false;
      const next = prev.map(it => {
        if (it.price_manual) return it;
        const prod = products.find(x => x.id === it.product_id);
        let out = it;
        if (prod) {
          const unitObj = it.unit_id ? (it.units || []).find(u => u.id === it.unit_id) : null;
          const np = unitObj ? unitLinePrice(priceFor(prod, ctx), prod.sale_price, unitObj) : priceFor(prod, ctx);
          if (np !== it.unit_price) out = { ...out, unit_price: np };
        }
        // Avto-chegirma (mijoz foizi): faqat o'zi qo'ygan bo'lsa yangilanadi/olib tashlanadi
        if (out.auto_discount && pct <= 0) out = { ...out, discount_type: 'sum', discount_val: 0, auto_discount: false };
        else if (out.auto_discount && pct > 0) out = { ...out, discount_type: 'pct', discount_val: pct };
        else if (!out.discount_val && pct > 0) out = { ...out, discount_type: 'pct', discount_val: pct, auto_discount: true };
        if (out !== it) changed = true;
        return out;
      });
      return changed ? next : prev;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [custId, custPrices, selectedCust?.price_type, selectedCust?.discount_percent]);

  // Mijoz tanlanganda yangi qarz/bonus malumotini fonda olamiz - chekda
  // eskirgan qarz chop etilmasligi uchun. T2.12: sodiqlik qoidalari (filial) ham shu javobda keladi.
  const loadFreshCust = (id) => api.get(`/customers/${id}/cashback`, { params: warehouseId ? { warehouse_id: warehouseId } : {} });
  useEffect(() => {
    setRedeemCash('');
    setRedeemPts('');
    if (!custId) { setFreshCust(null); return undefined; }
    let cancelled = false;
    loadFreshCust(custId)
      .then(r => { if (!cancelled) setFreshCust(r.data); })
      .catch(() => { if (!cancelled) setFreshCust(null); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [custId, warehouseId]);

  // T2.12: sodiqlik kartasi bo'yicha mijozni topish (lokal ro'yxat, so'ng server: GET /customers?card=)
  const findCustomerByCard = async (code) => {
    const digits = normCard(code);
    if (digits.length < 6) return null;
    const local = customers.find(c => c.card_number && normCard(c.card_number) === digits);
    if (local) return local;
    if (!isOnline) return null;
    try {
      const r = await api.get('/customers', { params: { card: digits, limit: 1 } });
      const list = Array.isArray(r.data) ? r.data : (r.data.items || []);
      return list[0] || null;
    } catch { return null; }
  };

  // D2.6: dorixona — QR (Data Matrix) kodi: dori GTIN bo'yicha topiladi (lokal ro'yxat, pos-list, shtrix-kod).
  // Seriyali kod (markirovka): bitta kod = bitta quti (omborda butun quti bo'lsa), kod shu qatorga yoziladi
  const addByGs1 = async (gs1) => {
    let p = products.find(x => productMatchesGtin(x, gs1.gtin)) || null;
    if (!p && isOnline) {
      for (const c of gtinVariants(gs1.gtin)) {
        try {
          const r = await api.get('/products/pos-list', {
            params: { search: c, limit: 5, ...posPriceParams(warehouseId, posBranchId) },
            _silent: true, _suppressToast: true,
          });
          const rows = Array.isArray(r.data) ? r.data : (r.data?.items || []);
          p = rows.find(x => productMatchesGtin(x, gs1.gtin)) || null;
        } catch { /* shtrix-kod bo'yicha urinamiz */ }
        if (!p) {
          try {
            const r = await api.get('/products/barcode/' + encodeURIComponent(c), { _silent: true, _suppressToast: true });
            if (r.data && r.data.id != null) p = r.data;
          } catch { /* keyingi variant */ }
        }
        if (p) break;
      }
    }
    if (!p) {
      // Tovar topilmadi: kodi to'liq bo'lmagan markirovkali qator bo'lsa kod unga yoziladi (avvalgidek)
      const pendingIdx = gs1.serial ? findPendingMarkingIdx() : -1;
      if (pendingIdx >= 0) { addMarkingCode(pendingIdx, gs1.code); return; }
      toast.error(t('pos.markingScannedNoProduct'));
      return;
    }
    if (!gs1.serial) { pickOrAdd(p); return; }
    if (cart.some(x => (x.marking_codes || []).includes(gs1.code))) { toast.error(t('pos.markingCodeAlreadyScanned')); return; }
    const box = (Array.isArray(p.units) ? p.units : [])
      .filter(u => (Number(u.ratio) || 1) > 1).sort((a, b) => Number(b.ratio) - Number(a.ratio))[0] || null;
    const unit = box && !(p.pack_ratio != null && p.full_boxes != null && Number(p.full_boxes) < 1) ? box : null;
    const same = (x) => x.product_id === p.id && (x.unit_id || null) === (unit ? unit.id : null);
    const open = (x) => same(x) && (x.marking_codes || []).length < x.qty_ordered;
    if (!cart.some(open)) addToCart(p, 1, unit);
    setCart(prev => {
      const idx = prev.findIndex(open);
      return idx < 0 ? prev : prev.map((x, i) => (i === idx ? { ...x, marking_codes: [...(x.marking_codes || []), gs1.code] } : x));
    });
  };

  // Skanerlangan kodni qayta ishlash (global skaner tinglovchisi va P.7 birlik tanlash oynasi chaqiradi)
  const handleScannedCode = (code) => {
    const gs1 = pharmacy ? parseGs1Scan(code) : null;
    if (gs1) { addByGs1(gs1); return; }

    // Tarozi barkodi (T3.12): PLU bo'yicha — eksport fayllari bilan bir xil plu_code
    const scale = parseScaleBarcode(code);
    if (scale) {
      const scaleProduct = findScaleProduct(products, scale.plu);
      if (scaleProduct) {
        addToCart(scaleProduct, scale.weightKg);
        return;
      }
    }

    const p = products.find(x =>
      x.barcode === code ||
      x.sku === code ||
      (Array.isArray(x.extra_barcodes) && x.extra_barcodes.includes(code))
    );
    if (p) {
      pickOrAdd(p);   // P.7: dorixonada quti / blister / dona tanlanadi
      return;
    }

    // D2.6: birlik (quti/blister) shtrix-kodi — mahsulot ham, birlik ham o'zi tanlanadi
    if (pharmacy) {
      const up = products.find(x => Array.isArray(x.units) && x.units.some(u => u.barcode && u.barcode === code));
      if (up) {
        addToCart(up, undefined, up.units.find(u => u.barcode === code));
        return;
      }
    }

    // Lokal ro'yxatda topilmadi
    const handleNotFound = () => {
      // Oddiy mahsulot barkodiga to'g'ri kelmadi — uzun kod bo'lsa (Data Matrix
      // markirovka kodlari odatda 20+ belgi), savatdagi kodi to'liq bo'lmagan
      // markirovkali qatorga biriktiramiz, aks holda yangi mahsulot modalini ochamiz.
      if (code.length >= 20) {
        const pendingIdx = findPendingMarkingIdx();
        if (pendingIdx >= 0) {
          addMarkingCode(pendingIdx, code);
          return;
        }
        toast.error(t('pos.markingScannedNoProduct'));
        return;
      }

      // Topilmadi — yangi mahsulot qo'shish modalini och
      const openNewProduct = () => {
        setNewProd({ name:'', barcode: code, sale_price:'', cost_price:'', unit:'dona', category_id:'', stock_quantity:'0' });
        setShowNewProduct(true);
      };
      // T2.12: tartib — tarozi mahsulot -> oddiy mahsulot -> mijoz kartasi -> yangi mahsulot
      const afterLocalMiss = () => {
        if (/^\d{6,19}$/.test(code)) {
          findCustomerByCard(code).then(cust => {
            if (cust) {
              pickCustomer(cust.id, cust);
              toast.success(tf('pos.cardCustomerFound', 'Mijoz topildi: {name}', { name: cust.name }));
            } else {
              openNewProduct();
            }
          });
          return;
        }
        openNewProduct();
      };
      // T3.11: lokal ro'yxatda yo'q (ro'yxatga sig'magan tovar) — onlayn bo'lsa serverdan shtrix-kod bo'yicha;
      // faqat 404 bo'lsa "yangi mahsulot" modali (dublikat mahsulot yaratilmasin)
      if (isOnline) {
        api.get('/products/barcode/' + encodeURIComponent(code))
          .then(r => {
            if (r.data && r.data.id != null) pickOrAdd(r.data);
            else afterLocalMiss();
          })
          .catch(err => {
            if (err.response?.status === 404) afterLocalMiss();
            else toast.error(err.response?.data?.detail || err.message || t('common.error'));
          });
        return;
      }
      afterLocalMiss();
    };
    // D2.6: dorixona — ro'yxatga sig'magan birlik shtrix-kodi serverdan (pos-list scanned_unit_id)
    if (pharmacy && isOnline && !scale) {
      api.get('/products/pos-list', {
        params: { search: code, limit: 5, ...posPriceParams(warehouseId, posBranchId) },
        _silent: true, _suppressToast: true,
      }).then(r => {
        const rows = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        const hit = rows.find(x => x.scanned_unit_id != null);
        if (hit) addToCart(hit, undefined, (hit.units || []).find(u => u.id === hit.scanned_unit_id));
        else handleNotFound();
      }).catch(() => handleNotFound());
      return;
    }
    // Tarozi PLU si lokal ro'yxatda yo'q (masalan, ro'yxatga sig'magan tovar): serverdan PLU bo'yicha
    if (scale && isOnline) {
      api.get('/products/barcode/' + String(scale.plu).padStart(5, '0'))
        .then(r => {
          if (r.data && r.data.id != null) addToCart(r.data, scale.weightKg);
          else handleNotFound();
        })
        .catch(() => handleNotFound());
      return;
    }
    handleNotFound();
  };
  const scanRef = useRef(null);
  scanRef.current = handleScannedCode;

  // Global Skaner Listener
  const gsKeyRef = useRef(createGsDetector());
  useEffect(() => {
    let buf = '';
    let lastTime = Date.now();
    const handleKeyDown = (e) => {
      if (showCheckout || showNewProduct || rxModal || analogModal || saleError || rejectedModal || unitPick) return;
      // Dorixona: Data Matrix ajratgichi (GS) buferda saqlanadi, Alt+raqamlar kodga yozilmaydi
      const gsAct = pharmacy ? gsKeyRef.current(e) : null;
      if (gsAct === 'gs') { buf += GS; lastTime = Date.now(); return; }
      if (gsAct === 'skip' || e.type === 'keyup') return;
      const isInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
      const now = Date.now();
      if (now - lastTime > 200) buf = '';
      lastTime = now;

      if (e.key === 'Enter') {
         if (buf.length >= 3) {
           e.preventDefault();
           const code = buf;
           buf = '';
           e.stopPropagation();
           if (isInput) { e.target.blur(); e.target.value = ''; e.target.dispatchEvent(new Event('input', { bubbles: true })); }

           scanRef.current(code);
         }
         return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) buf += e.key;
    };
    window.addEventListener('keydown', handleKeyDown, true);
    window.addEventListener('keyup', handleKeyDown, true);
    return () => { window.removeEventListener('keydown', handleKeyDown, true); window.removeEventListener('keyup', handleKeyDown, true); };
  }, [products, cart, showCheckout, showNewProduct, customers, isOnline, pharmacy, warehouseId, posBranchId, rxModal, analogModal, saleError, rejectedModal, unitPick]);

  // Yangi mahsulotni bazaga saqlash va savatga qo'shish
  const saveNewProduct = async () => {
    if (!newProd.name.trim()) return toast.error(t('pos.enterProductName'));
    if (!newProd.sale_price || Number(newProd.sale_price) <= 0) return toast.error(t('pos.enterSalePrice'));
    setSavingProd(true);
    try {
      const payload = {
        name: newProd.name.trim(),
        barcode: newProd.barcode || null,
        sale_price: Number(newProd.sale_price),
        cost_price: Number(newProd.cost_price) || 0,
        unit: newProd.unit || 'dona',
        category_id: newProd.category_id ? Number(newProd.category_id) : null,
        // T1.5: backend `initial_stock` / `initial_warehouse_id` kutadi (`stock_quantity` tashlab yuborilardi);
        // qoldiq kassirning tanlangan (default) omboriga yoziladi
        initial_stock: Number(newProd.stock_quantity) || 0,
        initial_warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        status: 'active',
      };
      const res = await api.post('/products/', payload);
      const created = res.data;
      // Mahsulotlar ro'yxatiga qo'sh
      setProducts(prev => [...prev, created]);
      // Savatga qo'sh
      addToCart({ ...created, sale_price: created.sale_price, stock_quantity: created.stock_quantity });
      toast.success(t('pos.productAddedToCart', { name: created.name }));
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
    const m1 = !search || matchesSearch(p.name, search) || p.sku?.includes(search) || p.barcode?.includes(search) ||
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
  // D2.6: dorixona qatorining qo'shimcha maydonlari (muddat, retsept, birliklar); oddiy korxonada bo'sh
  const pharmaCartFields = (p, unit) => {
    if (!pharmacy) return {};
    const packRatio = p.pack_ratio != null ? Number(p.pack_ratio) : null;
    const ratio = unit ? Number(unit.ratio) || 1 : 1;
    return {
      nearest_expiry: p.nearest_expiry || null,
      expiry_warn: !!p.expiry_warn,
      expired_qty: Number(p.expired_qty) || 0,   // P.7
      is_rx: !!p.is_rx,
      control_class: p.control_class || 'none',
      units: Array.isArray(p.units) ? p.units : [],
      pack_ratio: packRatio,
      full_boxes: p.full_boxes != null ? Number(p.full_boxes) : null,
      loose_units: p.loose_units != null ? Number(p.loose_units) : null,
      stock_display: p.stock_display || null,
      unit_id: unit ? unit.id : null,
      unit_name: unit ? unit.name : null,
      unit_ratio: ratio,
      base_unit_name: p.unit || 'dona',
    };
  };

  // Birlik tanlanganda narx: server ro'yxat narxi (unit.price) yoki asosiy narx * nisbat
  const unitPriceFor = (p, unit, ctx = priceCtxRef.current) =>
    unitLinePrice(priceFor(p, ctx), p.sale_price, unit);

  const addToCart = (p, overrideQty, unitArg, opts = {}) => {
    // nisbati 1 bo'lgan birlik = asosiy birlik (unit_id yuborilmaydi)
    let unit = pharmacy && unitArg && (Number(unitArg.ratio) || 1) !== 1 ? unitArg : null;
    // Qoldiq yo'q — analoglar avtomatik taklif qilinadi (savatga qo'shish avvalgidek davom etadi)
    if (pharmacy && isOnline && !opts.noAnalogs && Number(p.stock_quantity) <= 0 && (p.product_type || 'stock') === 'stock') {
      openAnalogs(p, true);
    }
    // Butun quti shtrix-kodi, lekin omborda butun quti yo'q (faqat ochilgan quti) — dona qilib sotish taklif qilinadi
    if (unit && p.pack_ratio != null && Number(unit.ratio) >= Number(p.pack_ratio) && p.full_boxes != null && Number(p.full_boxes) < 1) {
      toast.warn(tf('pos.wholeBoxNone', "Omborda butun quti yo'q (ochilgan qutida {loose} dona). Dona qilib soting.", { loose: p.loose_units ?? 0 }));
      unit = null;
    }
    setCart(prev => {
      const idx = prev.findIndex(x => x.product_id === p.id && (x.unit_id || null) === (unit ? unit.id : null));
      if (idx >= 0) {
        const next = [...prev];
        next[idx].qty_ordered += overrideQty !== undefined ? overrideQty : 1;
        _clampWholeBox(next[idx]);
        return next;
      }
      return [{
        product_id: p.id,
        product_name: p.name,
        sku: p.sku || '',
        unit: p.unit || 'dona',
        unit_price: unit ? unitPriceFor(p, unit) : priceFor(p),
        discount_type: custDiscountPct() > 0 ? 'pct' : 'sum',
        discount_val: custDiscountPct(),
        auto_discount: custDiscountPct() > 0,
        mxik_code: p.mxik_code || '',
        package_code: p.parent_code || p.package_code || '',
        barcode: p.barcode || '',
        labels: p.labels || [],
        requires_marking: !!p.requires_marking,
        marking_codes: [],
        vat_rate_type: p.vat_rate_type || 'nds_12',
        qty_ordered: overrideQty !== undefined ? overrideQty : 1,
        max_stock: p.stock_quantity,
        ...pharmaCartFields(p, unit),
      }, ...prev];
    });
  };

  // P.7: dorixona — shtrix-kod skanerlanganda (yoki kartochka bosilganda) quti / blister / dona tanlanadi
  const unitOptions = (p) => {
    const base = priceFor(p);
    const us = (Array.isArray(p.units) ? p.units : [])
      .filter(u => (Number(u.ratio) || 1) !== 1)
      .map(u => (u.price == null && u.sale_price != null ? { ...u, price: u.sale_price } : u))
      .sort((a, b) => Number(b.ratio) - Number(a.ratio));
    const noWholeBox = p.pack_ratio != null && p.full_boxes != null && Number(p.full_boxes) < 1;
    return [
      ...us.map(u => ({
        unit: u, name: u.name, ratio: Number(u.ratio), price: unitLinePrice(base, p.sale_price, u),
        disabled: noWholeBox && Number(u.ratio) >= Number(p.pack_ratio),
      })),
      { unit: null, name: p.unit || 'dona', ratio: 1, price: base, disabled: false },
    ];
  };
  // Oyna faqat quti VA blister (2 ta qadoq birligi) bo'lgan dorida; donalab yoki blistersiz dori — avvalgidek savatga
  const pickOrAdd = (p, qty) => {
    const opts = pharmacy ? unitOptions(p) : [];
    if (opts.length < 3) { addToCart(p, qty); return; }
    setUnitPick({ p, qty, sel: Math.max(0, opts.findIndex(o => !o.disabled)) });
  };
  const confirmUnitPick = (i) => {
    if (!unitPick) return;
    const o = unitOptions(unitPick.p)[i != null ? i : unitPick.sel];
    if (!o || o.disabled) return;
    addToCart(unitPick.p, unitPick.qty, o.unit);
    setUnitPick(null);
  };
  const moveUnitPick = (d) => setUnitPick(u => {
    if (!u) return u;
    const opts = unitOptions(u.p);
    let s = u.sel;
    for (let k = 0; k < opts.length; k++) { s = (s + d + opts.length) % opts.length; if (!opts[s].disabled) break; }
    return { ...u, sel: s };
  });
  // Oyna ochiq: ↑/↓ tanlash, Enter — savatga, Esc — bekor. Skaner kodi (tez belgilar + Enter) tanlov bo'lib ketmaydi:
  // joriy tanlov qo'shiladi va yangi kod odatdagidek qayta ishlanadi
  useEffect(() => {
    if (!unitPick) return undefined;
    let buf = '';
    let last = 0;
    const onKey = (e) => {
      const now = Date.now();
      const fast = now - last < 60;
      last = now;
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setUnitPick(null); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); e.stopPropagation();
        moveUnitPick(e.key === 'ArrowDown' ? 1 : -1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault(); e.stopPropagation();
        const code = buf;
        buf = '';
        confirmUnitPick();
        if (code.length >= 3) setTimeout(() => scanRef.current && scanRef.current(code), 0);
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
        e.preventDefault(); e.stopPropagation();
        buf = fast ? buf + e.key : e.key;
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitPick]);

  // P.7: yaroqlilik muddati rangi — yashil (ko'p vaqt bor), sariq (yaqinlashmoqda), qizil (kam qoldi);
  // omborda muddati o'tgan qoldiq bo'lsa — qizil miltillaydi. Chegara: sozlamadagi expiry_warn_days (qizil), x3 (sariq)
  const expiryDays = (iso) => {
    if (!iso) return null;
    const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
    const t0 = new Date();
    t0.setHours(0, 0, 0, 0);
    return Math.round((new Date(y, m - 1, d) - t0) / 86400000);
  };
  const expiryLevel = (days) => {
    if (days == null) return null;
    const red = Math.max(1, Number(features?.pharmacy_settings?.expiry_warn_days) || 30);
    if (days < 0) return 'expired';
    if (days <= red) return 'red';
    if (days <= red * 3) return 'yellow';
    return 'green';
  };
  const EXPIRY_CLS = {
    green: 'bg-emerald-100 text-emerald-700 border border-emerald-300',
    yellow: 'bg-amber-100 text-amber-800 border border-amber-300',
    red: 'bg-red-100 text-red-700 border border-red-400',
    expired: 'bg-red-600 text-white border border-red-700 animate-pulse',
  };
  const expiryBadges = (it, size = 'sm') => {
    const cls = size === 'lg' ? 'px-2 py-0.5 rounded text-xs font-bold'
      : size === 'md' ? 'px-1.5 rounded text-[10px] font-bold' : 'px-1 rounded text-[9px] font-bold';
    const days = expiryDays(it.nearest_expiry);
    const lvl = expiryLevel(days);
    const expiredQty = Number(it.expired_qty) || 0;
    return (
      <>
        {lvl && (
          <span className={`${cls} ${EXPIRY_CLS[lvl]}`} data-expiry-level={lvl}
            title={tf('pos.expiryDaysLeft', '{n} kun qoldi', { n: days })}>
            {lvl === 'red' || lvl === 'expired' ? '⚠ ' : ''}{fmtExpiry(it.nearest_expiry)}
          </span>
        )}
        {expiredQty > 0 && (
          <span className={`${cls} ${EXPIRY_CLS.expired}`} data-expiry-level="expired"
            title={tf('pos.expiredTitle', "Omborda muddati o'tgan partiya bor — sotilmaydi")}>
            {tf('pos.expiredShort', "Muddati o'tgan")}: {fmt(expiredQty)}
          </span>
        )}
      </>
    );
  };

  // Markirovka (Data Matrix) kod skanerlash — savat qatoriga kod qo'shish/o'chirish
  const [markingModal, setMarkingModal] = useState(null); // { idx }

  const addMarkingCode = (idx, code) => {
    const trimmed = (code || '').trim();
    if (!trimmed) return;
    setCart(prev => {
      const next = [...prev];
      const item = { ...next[idx] };
      const codes = [...(item.marking_codes || [])];
      if (codes.includes(trimmed)) {
        toast.error(t('pos.markingCodeAlreadyScanned'));
        return prev;
      }
      if (codes.length >= item.qty_ordered) {
        toast.error(t('pos.markingCodeEnoughForQty', { qty: item.qty_ordered }));
        return prev;
      }
      codes.push(trimmed);
      item.marking_codes = codes;
      next[idx] = item;
      return next;
    });
  };

  const removeMarkingCode = (idx, codeIdx) => {
    setCart(prev => {
      const next = [...prev];
      const item = { ...next[idx] };
      item.marking_codes = (item.marking_codes || []).filter((_, i) => i !== codeIdx);
      next[idx] = item;
      return next;
    });
  };

  // Savatda markirovka talab qiluvchi, hali kodlari to'liq bo'lmagan oxirgi qator
  // (global skaner orqali kelgan uzun DataMatrix kodini shu qatorga biriktirish uchun)
  const findPendingMarkingIdx = () => {
    for (let i = 0; i < cart.length; i++) {
      const item = cart[i];
      if (item.requires_marking && (item.marking_codes || []).length < item.qty_ordered) return i;
    }
    return -1;
  };

  // Miqdor kamaytirilganda ortiqcha skanerlangan markirovka kodlarini kesib tashlaymiz
  const _trimMarkingCodes = (item) => {
    if (item.requires_marking && (item.marking_codes || []).length > item.qty_ordered) {
      item.marking_codes = item.marking_codes.slice(0, Math.floor(item.qty_ordered));
    }
    return item;
  };

  // D2.6: butun quti sotuvida miqdor ombordagi butun qutilar sonidan oshmasin (server ham 400 qaytaradi)
  const _clampWholeBox = (item) => {
    const max = wholeBoxMax(item);
    if (max != null && item.qty_ordered > max) {
      item.qty_ordered = Math.max(max, 1);
      toast.warn(tf('pos.wholeBoxMax', "Omborda butun quti {boxes} ta (ochilgan qutida {loose} dona). Ko'proq kerak bo'lsa dona qilib soting.", {
        boxes: item.full_boxes, loose: item.loose_units ?? 0,
      }));
    }
    return item;
  };

  const updateCartQty = (idx, delta) => {
    setCart(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx] };
      next[idx].qty_ordered = Math.max(0.1, next[idx].qty_ordered + delta);
      _clampWholeBox(next[idx]);
      _trimMarkingCodes(next[idx]);
      return next;
    });
  };

  const updateExtQty = (idx, qtyVal) => {
    setCart(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx] };
      next[idx].qty_ordered = Math.max(0.1, Number(qtyVal)||1);
      _clampWholeBox(next[idx]);
      _trimMarkingCodes(next[idx]);
      return next;
    });
  };

  // D2.6: savat qatorida birlikni almashtirish (quti <-> blister <-> dona) — narx qayta hisoblanadi, miqdor imkon bo'lsa saqlanadi
  const switchUnit = (idx, unitIdRaw) => {
    setCart(prev => {
      const it = prev[idx];
      if (!it) return prev;
      const unit = unitIdRaw ? (it.units || []).find(u => String(u.id) === String(unitIdRaw)) || null : null;
      if ((it.unit_id || null) === (unit ? unit.id : null)) return prev;
      const oldRatio = it.unit_ratio || 1;
      const newRatio = unit ? Number(unit.ratio) || 1 : 1;
      const prod = products.find(x => x.id === it.product_id);
      const base = prod ? priceFor(prod) : it.unit_price / oldRatio;
      const price = unitLinePrice(base, prod ? prod.sale_price : base, unit);
      const q = (it.qty_ordered * oldRatio) / newRatio;
      const nextItem = {
        ...it,
        unit_id: unit ? unit.id : null,
        unit_name: unit ? unit.name : null,
        unit_ratio: newRatio,
        unit_price: price,
        qty_ordered: Number.isInteger(q) && q >= 1 ? q : 1,
      };
      if (wholeBoxMax(nextItem) === 0) {
        toast.warn(tf('pos.wholeBoxNone', "Omborda butun quti yo'q (ochilgan qutida {loose} dona). Dona qilib soting.", { loose: it.loose_units ?? 0 }));
        return prev;
      }
      if (nextItem.discount_type === 'sum') nextItem.discount_val = Math.min(nextItem.discount_val || 0, price * nextItem.qty_ordered);
      _clampWholeBox(nextItem);
      _trimMarkingCodes(nextItem);
      const next = [...prev];
      next[idx] = nextItem;
      return next;
    });
  };

  // D2.6: analoglar (GET /products/{id}/analogs) — qoldiq 0 bo'lganda `auto` rejimida o'zi ochiladi (analog topilmasa jim yopiladi)
  const openAnalogs = (p, auto = false) => {
    const pid = p.id ?? p.product_id;
    const name = p.name ?? p.product_name;
    if (!isOnline) { toast.warn(tf('pos.analogsOffline', "Analoglar uchun internet kerak")); return; }
    setAnalogModal({ product_id: pid, name, loading: true, items: [], auto });
    api.get(`/products/${pid}/analogs`, { _silent: true, _suppressToast: true })
      .then(r => {
        const items = Array.isArray(r.data) ? r.data : [];
        setAnalogModal(m => (m && m.product_id === pid ? (auto && !items.length ? null : { ...m, loading: false, items }) : m));
      })
      .catch(() => setAnalogModal(m => (m && m.product_id === pid ? (auto ? null : { ...m, loading: false, items: [], error: true }) : m)));
  };

  const addAnalogToCart = (a) => {
    const prod = products.find(x => x.id === a.id) || {
      id: a.id, name: a.name, barcode: a.barcode, unit: a.unit, sale_price: a.sale_price,
      stock_quantity: a.stock_quantity, nearest_expiry: a.nearest_expiry, expiry_warn: a.expiry_warn,
      is_rx: a.is_rx, control_class: a.control_class,
    };
    addToCart(prod, undefined, undefined, { noAnalogs: true });
    setAnalogModal(null);
  };

  const updateDiscount = (idx, val) => {
    setCart(prev => {
      const next = [...prev];
      const item = next[idx];
      // T3.19: avto-chegirma (mijoz foizi) qo'lda tahrirlansa — oddiy summa chegirmasiga o'tadi
      if (item.auto_discount) { item.auto_discount = false; item.discount_type = 'sum'; }
      // Chegirma [0, narx x miqdor] oralig'ida bo'lishi shart - aks holda
      // manfiy summali sotuv yuzaga keladi (backend baribir rad etadi,
      // oflaynda esa savdo sinxronlanmay qolardi).
      const maxDisc = item.discount_type === 'pct'
        ? 100
        : item.unit_price * item.qty_ordered;
      next[idx].discount_val = Math.min(maxDisc, Math.max(0, Number(val) || 0));
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
  const [debtDueDate, setDebtDueDate]     = useState('');
  const [debtNote, setDebtNote]           = useState('');

  // Fiskal tasdiqlash modal
  // null | { factoryId, cartSnap, paymentsSnap, discount }
  const [fiskalPending, setFiskalPending] = useState(null);
  const [isFiskalizing, setIsFiskalizing] = useState(false);

  // T3.18: filial to'lov terminallari va fiskal qurilmalari (serverdan; xato bo'lsa bo'sh = eski xatti-harakat)
  const [terminals, setTerminals] = useState([]);
  const [fiscalDevices, setFiscalDevices] = useState([]);
  useEffect(() => {
    if (!isOnline) return;
    api.get('/payment-terminals/mine', { _silent: true, _suppressToast: true })
      .then(r => setTerminals(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    api.get('/fiscal-devices/mine', { _silent: true, _suppressToast: true })
      .then(r => setFiscalDevices(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline]);
  const REF_PROVIDERS = ['click', 'payme', 'uzum'];
  // Joriy filial terminallari (filial aniqlangan bo'lsa); butun korxona terminallari (branch_id yo'q) hammada
  const providerTerminals = (type) => terminals.filter(x =>
    x.provider === type && x.is_active !== false && (!posBranchId || !x.branch_id || x.branch_id === posBranchId));
  const referenceRequired = (p) => {
    if (!REF_PROVIDERS.includes(p.type)) return false;
    const sel = p.terminal_id ? terminals.find(x => String(x.id) === String(p.terminal_id)) : null;
    if (sel) return !!sel.require_reference;
    return providerTerminals(p.type).some(x => x.require_reference);
  };
  // Serverda ro'yxatdan o'tgan qurilma bo'lsa: boshqa filial qurilmasi (localStorage'da qolib ketgan) ishlatilmaydi
  const resolveFactoryId = (stored) => {
    if (!fiscalDevices.length) return stored;
    if (stored && fiscalDevices.some(d => d.factory_id === stored)) return stored;
    return fiscalDevices.length === 1 ? fiscalDevices[0].factory_id : null;
  };


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

  // Keshbek / ball bilan to'lash (T2.12): faqat mijoz tanlangan, online va balans bor bo'lsa
  const loyal = freshCust && String(freshCust.customer_id) === String(custId) ? freshCust : null;
  const pointValue = Number(loyal?.point_value || 1) || 1;
  const bonusAvail = Math.floor(Number(loyal?.bonus_balance || 0));
  const pointsAvail = Number(loyal?.loyalty_points || 0);
  const canRedeem = !!(custId && isOnline && loyal && loyal.loyalty_enabled !== false && (bonusAvail > 0 || pointsAvail > 0));
  const maxRedeemUzs = Math.floor(totalNet * (Number(loyal?.max_redeem_percent ?? 100)) / 100);
  const redeemCashAmt = canRedeem ? Math.min(parseAmt(redeemCash), bonusAvail, maxRedeemUzs) : 0;
  const redeemPtsCnt = canRedeem
    ? Math.min(parseAmt(redeemPts), pointsAvail, Math.floor(Math.max(0, maxRedeemUzs - redeemCashAmt) / pointValue))
    : 0;
  const redeemUzs = redeemCashAmt + redeemPtsCnt * pointValue;
  // Keshbek/ball chekdan ayiriladi; qolgan qism pul (yoki qarz) bilan to'lanadi
  const payableNet = Math.max(0, totalNet - redeemUzs);

  // Qaytish hisoblash
  const finalPaid = payments.reduce((s, p) => s + parseAmt(p.amount), 0);
  const isEnough = finalPaid >= payableNet;
  const changeAmt = isEnough ? (finalPaid - payableNet) : 0;
  const remaining = isEnough ? 0 : (payableNet - finalPaid);

  // D2.6: to'lovdan oldin dorixona tekshiruvlari — markirovka kodlari to'liq skanerlanmaguncha va retsept
  // ma'lumoti kiritilmaguncha to'lov oynasi ochilmaydi (server baribir tekshiradi: D2.5, D3.2)
  const requestCheckout = () => {
    if (pharmacy) {
      const incomplete = cart.find(c => c.requires_marking && (c.marking_codes || []).length < c.qty_ordered);
      if (incomplete) {
        toast.error(t('pos.markingScanIncomplete', {
          name: incomplete.product_name, scanned: (incomplete.marking_codes || []).length, qty: incomplete.qty_ordered,
        }));
        setMarkingModal({ idx: cart.indexOf(incomplete) });
        return;
      }
      if (rxProductsOf(cart).length && validateRx(cart, rxData, rxReason, rxMode)) {
        setRxModal({ proceed: true });
        return;
      }
    }
    setShowCheckout(true);
  };

  const setRxField = (pid, field, val) => setRxData(prev => ({ ...prev, [pid]: { ...(prev[pid] || {}), [field]: val } }));
  const [rxError, setRxError] = useState('');
  const confirmRx = () => {
    const err = validateRx(cart, rxData, rxReason, rxMode);
    if (err) { setRxError(err); return; }
    setRxError('');
    const proceed = !!rxModal?.proceed;
    setRxModal(null);
    if (proceed) setShowCheckout(true);
  };

  // Server 400 xatosi (dorixona): retsept — oyna, boshqalari (muddat, quti, markirovka...) — aniq xabar oynasi
  const handlePharmacyReject = (raw) => {
    const info = describeRejection(raw);
    setShowCheckout(false);
    if (info.category === 'rx' && raw && typeof raw === 'object') {
      setRxError(info.text);
      setRxModal({ proceed: true, message: info.text });
      return;
    }
    setSaleError({ category: info.category, message: info.text, boxFix: parseWholeBoxError(raw) });
  };
  const applyBoxFix = () => {
    const name = saleError?.boxFix?.name;
    const idx = cart.findIndex(c => c.product_name === name && wholeBoxMax(c) != null);
    if (idx >= 0) switchUnit(idx, '');
    setSaleError(null);
  };

  // Oflayn navbatdan server rad etgan sotuvlar (joriy korxona) — sababi bilan
  const rejectedSales = useMemo(() => {
    if (!pharmacy) return [];
    const cid = getCurrentCompanyId();
    return getPending(REJECTED_SALES_KEY).filter(r => r.kind !== 'return' && (r.company_id == null || cid == null || String(r.company_id) === String(cid)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pharmacy, syncing, pendingCount, rejectedTick]);
  const clearRejectedSales = () => {
    const cid = getCurrentCompanyId();
    setPending(REJECTED_SALES_KEY, getPending(REJECTED_SALES_KEY).filter(r => !(r.company_id == null || cid == null || String(r.company_id) === String(cid))));
    setRejectedTick(x => x + 1);
    setRejectedModal(false);
  };

  const checkout = async (isDebtConfirm = false, approvalId = null) => {
    if (!cart.length) return toast.warn(t('pos.emptyCart'));
    if (!hasShift) { setShowShiftModal(true); return; }

    // Markirovka talab qilinadigan mahsulotlar uchun skanerlangan kodlar
    // miqdorga to'liq mos kelishi shart — aks holda fiskal chekda aks etmaydi.
    const incompleteMarking = cart.find(c => c.requires_marking && (c.marking_codes || []).length < c.qty_ordered);
    if (incompleteMarking) {
      toast.error(t('pos.markingScanIncomplete', {
        name: incompleteMarking.product_name,
        scanned: (incompleteMarking.marking_codes || []).length,
        qty: incompleteMarking.qty_ordered,
      }));
      setMarkingModal({ idx: cart.indexOf(incompleteMarking) });
      return;
    }

    // T3.18: click/payme to'lovida terminal talab qilsa tranzaksiya raqami majburiy
    const missingRef = payments.find(p => parseAmt(p.amount) > 0 && referenceRequired(p) && !String(p.reference || '').trim());
    if (missingRef) {
      toast.error(tf('pos.referenceRequired', 'Tranzaksiya raqamini kiriting'));
      return;
    }

    // Pul yetarli emas va mijoz tanlanmagan → xato
    if (!isEnough && !custId) {
      toast.error(t('pos.customerRequiredForDebt'));
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
         if (payments.length === 1 && redeemUzs === 0) mainType = payments[0].type;
         else mainType = 'mixed';
      } else if (redeemUzs > 0 && payableNet <= 0) {
         mainType = 'cashback';
      }

      // Har to'lov turi alohida yuboriladi (uzcard, humo, payme, click, bank terminal bo'yicha ajraladi).
      // Qaytim (berilgan − sotuv summasi) oxirgi naqd qatorlardan ayiriladi: Transaction,
      // KassaMovement va kassa balansi haqiqatan olingan pulga teng bo'ladi.
      const payRows = payments
        .map(p => ({ type: p.type, amount: parseAmt(p.amount), reference: String(p.reference || '').trim(), terminal_id: p.terminal_id ? Number(p.terminal_id) : null }))
        .filter(p => p.amount > 0);
      let changeLeft = Math.max(0, finalPaid - payableNet);
      for (let i = payRows.length - 1; i >= 0 && changeLeft > 0; i--) {
         if (payRows[i].type !== 'cash') continue;
         const cut = Math.min(payRows[i].amount, changeLeft);
         payRows[i].amount -= cut;
         changeLeft -= cut;
      }
      const paymentsPayload = payRows
        .filter(p => p.amount > 0)
        .map(p => ({
          type: p.type, amount: p.amount, currency: 'UZS',
          // T3.18: provayder tranzaksiya raqami va terminal (faqat click/payme/uzum)
          ...(REF_PROVIDERS.includes(p.type) && p.reference ? { reference: p.reference } : {}),
          ...(REF_PROVIDERS.includes(p.type) && p.terminal_id ? { terminal_id: p.terminal_id } : {}),
        }));

      // Eski serverlar uchun paid_cash/paid_card (ular payments'ni bilmaydi)
      let pCash = 0, pCard = 0;
      paymentsPayload.forEach(p => {
         if (p.type === 'cash') pCash += p.amount;
         else pCard += p.amount;
      });

      const payload = {
        items: cart.map(c => ({
          product_id: c.product_id,
          quantity: c.qty_ordered,
          unit_price: c.unit_price,
          // T3.19: faqat kassir narxni qo'lda o'zgartirgan qator true; aks holda server ro'yxat narxini hal qiladi
          price_manual: c.price_manual === true,
          discount: c.discount_type === 'pct'
             ? c.unit_price * c.qty_ordered * (c.discount_val / 100)
             : c.discount_val,
          marking_codes: c.marking_codes && c.marking_codes.length ? c.marking_codes : undefined,
          // D2.6: qadoq birligi (quti/blister) — miqdor shu birlikda; asosiy birlik (dona) uchun yuborilmaydi
          unit_id: pharmacy && c.unit_id ? c.unit_id : undefined,
        })),
        payment_type: mainType,
        // paid_amount keshbek/ballni o'z ichiga olmaydi (server: paid_amount + paid_cashback + ball*qiymat < jami => qarz)
        paid_amount: finalPaid > payableNet ? payableNet : finalPaid,
        paid_cash: pCash,
        paid_card: pCard,
        payments: paymentsPayload.length ? paymentsPayload : undefined,
        paid_cashback: redeemCashAmt > 0 ? redeemCashAmt : undefined,
        loyalty_points_used: redeemPtsCnt > 0 ? redeemPtsCnt : undefined,
        discount_amount: totalDiscount,
        note: isDebtConfirm && debtNote ? debtNote : (t('pos.retailSaleNoteShort') === 'pos.retailSaleNoteShort' ? 'Chakana sotuv' : t('pos.retailSaleNoteShort')),
        customer_id: Number(custId) || null,
        debt_due_date: isDebtConfirm && debtDueDate ? debtDueDate : null,
        // Ekranda ko'ringan qoldiq ombori = sotuv yechadigan ombor (T1.17)
        warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        // T4.6: menejer tasdiqlagan so'rov (limitdan oshgan chegirma/narx)
        approval_id: approvalId || undefined,
        // D2.6: retsept(lar) yoki retseptsiz sotish sababi (D2.5) — faqat dorixona rejimida
        ...(pharmacy ? buildRxPayload(cart, rxData, rxReason, rxMode) : {}),
      };

      const result = await submitSaleOrQueue(payload, false, { suppressToast: pharmacy });

      // T3.7: chek faqat sotuv serverga yoki oflayn navbatga yozilgandan KEYIN chop etiladi:
      // raqam bazadagi sale.number (oflaynda OFL-XXXXXXXX), kassir va filial rekvizitlari server javobidan.
      try {
        if (posSettings.autoPrint) {
          const settings = getReceiptSettings();
          const templateType = posSettings.template || (posSettings.paper === '58mm' ? '58' : '80');
          const companyTmpl = settings['r' + templateType] || settings[templateType] || {};
          // T4.2: filial shabloni bo'lsa korxona shabloni ustidan yoziladi (sotuv boshqa filialniki bo'lsa — qo'llanmaydi)
          const sameBranch = !result?.data?.branch_id || !branchInfo?.id || result.data.branch_id === branchInfo.id;
          const branchTmpl = (sameBranch && (branchInfo?.receipt_templates?.['r' + templateType] || branchInfo?.receipt_templates?.[templateType])) || {};
          const tmplCfg = { ...companyTmpl, ...branchTmpl };
          const selectedCust = customers.find(c => String(c.id) === String(custId));
          // Yangi (backenddan olingan) qarz malumotini afzal koramiz - royxatdagi
          // nusxa sahifa ochilgandan beri eskirgan bolishi mumkin.
          const fresh = freshCust && String(freshCust.customer_id) === String(custId) ? freshCust : null;
          const debtSource = fresh || selectedCust;
          const debtBalances = debtSource
            ? ((debtSource.debt_balances && Object.keys(debtSource.debt_balances).length > 0)
                ? debtSource.debt_balances
                : { UZS: Number(debtSource.debt_balance || 0) })
            : null;
          const saved = result?.offline ? null : (result?.data || null);
          const localMeta = {
            id: saved?.id ?? result?.localNumber,
            number: saved?.number || result?.localNumber,
            cashier_name: saved?.cashier_name || currentUser?.name || '',
            // T4.2: server javobi (oflayn rejimda yo'q) bo'lmasa — sahifa yuklanganda olingan filial rekvizitlari
            branch_name: saved?.branch_name || branchInfo?.name,
            branch_address: saved?.branch_address || branchInfo?.address,
            branch_phone: saved?.branch_phone || branchInfo?.phone,
            branch_legal_name: saved?.branch_legal_name || branchInfo?.legal_name,
            branch_stir: saved?.branch_stir || branchInfo?.stir,
            company_name: saved?.company_name,
            created_at: new Date().toISOString(),
            total_amount: payableNet,
            paid_amount: finalPaid > payableNet ? payableNet : finalPaid,
            discount_amount: totalDiscount,
            payment_types_array: payments.map(p => ({ type: p.type, amount: parseAmt(p.amount) })),
            items: cart,
            contractor_name: selectedCust ? selectedCust.name : undefined,
            customer_name: selectedCust ? selectedCust.name : undefined,
            before_debt_balances: debtBalances,
            before_debt: debtBalances ? (debtBalances['UZS'] || 0) : 0,
          };
          printReceiptHtml(buildReceiptHtml(localMeta, templateType, tmplCfg));
        }
      } catch (printErr) {
        // Sotuv allaqachon saqlangan — chop etish xatosi savat tozalanishiga xalaqit bermasin
        console.error('Chek chop etishda xato:', printErr);
      }

      // Savat va to'lovni tozalamiz
      const cartSnap     = [...cart];
      const paymentsSnap = [...payments];
      const discSnap     = totalDiscount;

      setCart([]);
      setRxData({});
      setRxReason('');
      setPayments([{ type: 'cash', amount: '' }]);
      setRedeemCash('');
      setRedeemPts('');
      if (custId && !result?.offline) loadFreshCust(custId).then(r => setFreshCust(r.data)).catch(() => {});
      setActiveInputIdx(0);
      setShowDebtModal(false);
      setDebtDueDate('');
      setDebtNote('');
      setShowCheckout(false);

      if (result?.offline) {
        toast.warning(t('pos.offlineSaleSaved'));
      } else {
        toast.success(t('pos.saleSuccessful'));
      }

      // Fiskalizatsiya yoqilgan bo'lsa — tasdiqlash modalini ko'rsatamiz
      const fiskalEnabled = JSON.parse(localStorage.getItem('fiskalSend') || 'false');
      const factoryId     = resolveFactoryId(JSON.parse(localStorage.getItem('fiskalId') || 'null'));
      if (fiskalEnabled && factoryId && !result?.offline) {
        // T3.18: saleId — fiskallangach natijani PATCH /sales/{id}/fiscal bilan serverga yozish uchun
        setFiskalPending({ factoryId, cartSnap, paymentsSnap, discount: discSnap, saleId: result?.data?.id ?? null });
      }

    } catch (e) {
      const raw = e.response?.data?.detail;
      // D2.6: dorixona 400 xatolari (muddat D1.2, butun quti D2.4, retsept D2.5, markirovka D3.2) — aniq oynada
      if (pharmacy && e.response?.status === 400 && !(raw && typeof raw === 'object' && String(raw.code || '').startsWith('approval'))) {
        handlePharmacyReject(raw);
        return;
      }
      // T4.6: detail obyekt bo'lishi mumkin ({code, message, ...})
      if (raw && typeof raw === 'object') {
        if (e.response?.status === 403 && raw.code === 'approval_required') {
          setShowDebtModal(false);
          approvalFlow.begin(raw, { isDebtConfirm });
          return;
        }
        if (raw.code === 'approval_invalid') approvalFlow.close();
        toast.error(raw.message || t('auth.errGeneral'));
        return;
      }
      toast.error(raw || t('auth.errGeneral'));
    } finally {
      setIsPaying(false);
    }
  };

  // T4.6: tasdiq so'rovi/kutish/qayta yuborish (Approvals.jsx); tasdiqlansa sotuv approval_id bilan qayta yuboriladi
  const approvalFlow = useApprovalFlow((requestId, ctx) => checkout(ctx?.isDebtConfirm, requestId));

  return (
    <div className={`font-sans select-none bg-slate-200 flex overflow-hidden w-full h-[calc(100vh-65px)]`}>
      {showShiftModal && (
        <ShiftOpenModal
          onOpened={() => { reloadShift(); setShowShiftModal(false); }}
          onCancel={() => setShowShiftModal(false)}
        />
      )}
      {showShiftClose && activeShift && (
        <ShiftCloseModal
          shift={activeShift}
          onClosed={() => { setShowShiftClose(false); reloadShift(); }}
          onCancel={() => setShowShiftClose(false)}
        />
      )}

      {/* ── FISKAL TASDIQLASH MODAL ─────────────────────────────────────── */}
      {fiskalPending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-[360px] overflow-hidden">
            {/* Header */}
            <div className="bg-slate-900 px-5 py-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <div>
                <div className="text-white font-bold text-sm">{t('pos.saleSavedCheckmark')}</div>
                <div className="text-slate-400 text-xs">{t('pos.decideFiscalReceipt')}</div>
              </div>
            </div>

            {/* Body */}
            <div className="px-5 py-5 text-center">
              <div className="text-2xl mb-1">🧾</div>
              <div className="font-bold text-slate-800 text-base mb-1">
                {t('pos.issueFiscalReceiptQuestion')}
              </div>
              <div className="text-slate-500 text-xs">
                {t('pos.fiscalReceiptHippoInfo')}
              </div>
            </div>

            {/* Buttons */}
            <div className="px-5 pb-5 flex gap-3">
              {/* Yo'q */}
              <button
                disabled={isFiskalizing}
                onClick={() => setFiskalPending(null)}
                className="flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50 transition-colors disabled:opacity-40"
              >
                {t('pos.skipFiscalReceipt')}
              </button>

              {/* Ha */}
              <button
                disabled={isFiskalizing}
                onClick={async () => {
                  setIsFiskalizing(true);
                  try {
                    const { factoryId, cartSnap, paymentsSnap, discount, saleId } = fiskalPending;
                    const { fiscal } = await fiscalizeAndPrint({
                      factoryId,
                      cart:          cartSnap,
                      payments:      paymentsSnap,
                      discountAmount: discount,
                    });
                    toast.success('✅ ' + t('pos.fiscalReceiptSent'));
                    // T3.18: natijani serverga yozish (xato bo'lsa sotuv bekor qilinmaydi, faqat ogohlantirish)
                    const sign = fiscal?.fiscal_sign ?? fiscal?.FiscalSign;
                    if (saleId && sign) {
                      const seq = Number(fiscal?.receipt_seq ?? fiscal?.receipt_number ?? fiscal?.ReceiptSeq);
                      const txId = fiscal?.transaction_id ?? fiscal?.TransactionID;
                      const body = {
                        fiscal_sign: String(sign),
                        fiscal_qr_url: fiscal?.qr_code_url ?? fiscal?.QRCodeURL ?? undefined,
                        fiscal_receipt_seq: Number.isFinite(seq) && seq >= 0 ? seq : undefined,
                        fiscal_transaction_id: txId != null ? String(txId) : undefined,
                        fiscal_at: new Date().toISOString().slice(0, 19),
                        fiscal_factory_id: factoryId,
                      };
                      try {
                        await api.patch(`/sales/${saleId}/fiscal`, body, { _suppressToast: true });
                      } catch (patchErr) {
                        toast.warning('⚠️ ' + tf('pos.fiscalSaveFailed', "Fiskal chek berildi, lekin natija serverga yozilmadi: {message}", {
                          message: patchErr?.response?.data?.detail || patchErr?.message || t('pos.unknown'),
                        }));
                      }
                    }
                  } catch (err) {
                    toast.error('⚠️ ' + t('pos.fiscalError', { message: err?.message || t('pos.unknown') }));
                  } finally {
                    setIsFiskalizing(false);
                    setFiskalPending(null);
                  }
                }}
                className="flex-1 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isFiskalizing
                  ? <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg> {t('pos.sending')}</>
                  : <>✓ {t('pos.yesMakeFiscal')}</>
                }
              </button>
            </div>
          </div>
        </div>
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
            {!isOnline && <span className="bg-red-500 font-bold px-2.5 py-1 rounded text-xs animate-pulse">{t('pos.offlineBadge')}</span>}
            {pendingCount > 0 && (
              <span className="bg-amber-500 font-bold px-2.5 py-1 rounded text-xs" title={tf('pos.pendingBadge', 'Yuborilmagan sotuvlar: {count}', { count: pendingCount })}>
                {syncing ? '⏳ ' : ''}{tf('pos.pendingBadge', 'Yuborilmagan sotuvlar: {count}', { count: pendingCount })}
              </span>
            )}
            {pharmacy && rejectedSales.length > 0 && (
              <button onClick={() => setRejectedModal(true)} className="bg-red-600 hover:bg-red-700 font-bold px-2.5 py-1 rounded text-xs"
                title={tf('pos.rejectedTitle', 'Server rad etgan oflayn sotuvlar')}>
                {tf('pos.rejectedBadge', 'Rad etilgan: {count}', { count: rejectedSales.length })}
              </button>
            )}
            {activeShift && (
              <button onClick={() => setShowShiftClose(true)}
                className="px-2.5 h-8 bg-red-500/80 hover:bg-red-500 rounded-lg text-xs font-bold transition-colors">
                {tf('shift.closeAction', 'Smenani yopish')}
              </button>
            )}
            <button onClick={() => setShowSettings(true)} className="w-8 h-8 bg-white/10 hover:bg-white/20 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            </button>
          </div>
        </div>

        {/* CUSTOMER SELECTOR */}
        <div className="p-1 px-2 border-b border-slate-200 bg-slate-50 shrink-0">
           <CustomerPicker variant="pos" customers={customers} value={custId} onChange={pickCustomer} onResolve={addCustomerToList} isOnline={isOnline} placeholder={t('pos.customerSearch')} />
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
                  {pharmacy && (
                    <div className="flex flex-wrap items-center gap-1 mt-0.5" data-testid="pharmacy-cart-extras">
                      {expiryBadges(item, 'sm')}
                      {isControlled(item) ? (
                        <button type="button" onClick={() => setRxModal({})} title={tf('pos.rxOpen', "Retsept ma'lumotlari")}
                          className="px-1 rounded text-[9px] font-bold bg-red-100 text-red-700 hover:bg-red-200">{tf('pos.rxControlled', 'Nazoratda')}</button>
                      ) : item.is_rx ? (
                        <button type="button" onClick={() => setRxModal({})} title={tf('pos.rxOpen', "Retsept ma'lumotlari")}
                          className="px-1 rounded text-[9px] font-bold bg-violet-100 text-violet-700 hover:bg-violet-200">Rx</button>
                      ) : null}
                      {Array.isArray(item.units) && item.units.some(u => (Number(u.ratio) || 1) !== 1) && (
                        <select
                          value={item.unit_id || ''}
                          onChange={e => switchUnit(i, e.target.value)}
                          className="border border-slate-200 rounded px-0.5 h-5 text-[10px] font-bold text-slate-700 bg-white outline-none"
                          title={tf('pos.unitSelect', 'Birlik')}
                        >
                          <option value="">{item.base_unit_name || 'dona'}</option>
                          {item.units.filter(u => (Number(u.ratio) || 1) !== 1).map(u => (
                            <option key={u.id} value={u.id}>{u.name}</option>
                          ))}
                        </select>
                      )}
                      {wholeBoxMax(item) != null && (
                        <>
                          <span className="text-[9px] font-bold text-slate-400">{tf('pos.wholeBoxMaxShort', 'max {n} quti', { n: wholeBoxMax(item) })}</span>
                          <button type="button" onClick={() => switchUnit(i, '')}
                            className="px-1 h-4 rounded text-[9px] font-bold bg-blue-50 text-blue-700 hover:bg-blue-100">
                            {tf('pos.sellByPiece', 'Dona qilib sotish')}
                          </button>
                        </>
                      )}
                      <button type="button" onClick={() => openAnalogs(item)}
                        className="px-1 h-4 rounded text-[9px] font-bold bg-emerald-50 text-emerald-700 hover:bg-emerald-100">
                        {tf('pos.analogs', 'Analoglar')}
                      </button>
                    </div>
                  )}
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
                  <div className="mt-0 flex items-center gap-1">

                    <input
                      type="text"
                      value={item.discount_val || ''}
                      onChange={e => updateDiscount(i, cleanNum(e.target.value))}
                      placeholder="0"
                      className="w-12 border border-slate-200 rounded px-1 py-0 text-[10px] h-5 font-bold text-red-500 outline-none focus:border-red-400 focus:ring-1 focus:ring-red-400 placeholder:text-slate-300"
                    />
                    {item.requires_marking && (
                      <button
                        type="button"
                        onClick={() => setMarkingModal({ idx: i })}
                        className={`flex items-center gap-0.5 px-1.5 h-5 rounded text-[9px] font-bold ${
                          (item.marking_codes || []).length >= item.qty_ordered
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-red-100 text-red-600 animate-pulse'
                        }`}
                        title={t('pos.scanMarkingCode')}
                      >
                        📷 {(item.marking_codes || []).length}/{item.qty_ordered}
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end justify-between shrink-0">
                   <button onClick={()=>removeCartItem(i)} className="w-4 h-4 bg-red-50 hover:bg-red-500 text-red-500 hover:text-white rounded flex items-center justify-center transition-colors">
                     <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                   </button>
                   <div className="text-right mt-0.5">
                     {item.discount_val > 0 && <div className="text-[10px] text-slate-400 line-through">{fmt(item.unit_price * item.qty_ordered)}</div>}
                     <div className="font-black text-[13px] text-slate-800 leading-none mt-1">{fmt((item.unit_price * item.qty_ordered) - (item.discount_type === 'pct' ? item.unit_price * item.qty_ordered * (item.discount_val / 100) : item.discount_val))}</div>
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
              requestCheckout();
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
           {posWarehouses.length > 1 && (
             <select
               value={warehouseId}
               onChange={e => changeWarehouse(e.target.value)}
               title={t('pos.stockLabel')}
               className="border-[2px] border-slate-300 rounded-2xl bg-slate-50 px-3 py-3 font-bold text-slate-700 outline-none focus:border-blue-500 max-w-[220px]"
             >
               {posWarehouses.map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
             </select>
           )}
           
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
                <button key={p.id}
                  onClick={() => {
                    if (p.product_type === 'parent') {
                      setVariantParent(p);
                    } else {
                      pickOrAdd(p);   // P.7: dorixonada quti / blister / dona tanlanadi
                    }
                  }}
                  className="bg-white rounded-2xl border-2 border-transparent hover:border-blue-500 p-4 shadow-sm hover:shadow-xl transition-all text-left flex flex-col active:scale-95 relative overflow-hidden group h-[160px]">
                  <div className="absolute -top-10 -right-10 w-24 h-24 bg-blue-50 rounded-full group-hover:scale-[2] transition-transform duration-500 ease-out z-0"></div>
                  {p.product_type === 'parent' && (
                    <span className="absolute top-2 right-2 bg-blue-100 text-blue-700 text-[9px] font-black px-1.5 py-0.5 rounded-md z-10 uppercase tracking-wide">
                      {t('pos.sizeBadge')}
                    </span>
                  )}
                  <h3 className="font-extrabold text-slate-800 text-base leading-tight mb-auto z-10 line-clamp-3">{p.name}</h3>
                  {pharmacy && (
                    <div className="z-10 flex flex-wrap items-center gap-1 mt-1" data-testid="pharmacy-card-extras">
                      {expiryBadges(p, 'md')}
                      {(p.control_class && p.control_class !== 'none') ? (
                        <span className="px-1.5 rounded text-[10px] font-bold bg-red-100 text-red-700">{tf('pos.rxControlled', 'Nazoratda')}</span>
                      ) : p.is_rx ? (
                        <span className="px-1.5 rounded text-[10px] font-bold bg-violet-100 text-violet-700">Rx</span>
                      ) : null}
                      <span
                        role="button" tabIndex={0}
                        onClick={e => { e.stopPropagation(); openAnalogs(p); }}
                        onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); openAnalogs(p); } }}
                        className="px-1.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 cursor-pointer"
                      >
                        {tf('pos.analogs', 'Analoglar')}
                      </span>
                    </div>
                  )}
                  <div className="z-10 mt-2">
                    <div className="text-xl font-black text-blue-700 tracking-tight">{fmt(p.sale_price)}{p.price_source === 'branch' && <span title={t('pos.branchPrice') === 'pos.branchPrice' ? 'Filial narxi' : t('pos.branchPrice')} className="ml-1.5 align-middle text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{t('pos.branchPrice') === 'pos.branchPrice' ? 'Filial' : t('pos.branchPrice')}</span>}</div>
                    <div className="text-xs font-bold text-slate-400 mt-1">{t('pos.stockLabel')} <span title={posWarehouses.find(w => String(w.id) === String(warehouseId))?.name || ''} className={p.stock_quantity<=p.min_stock?'text-red-500':'text-emerald-500'}>{p.stock_quantity>0 ? ((pharmacy && p.stock_display) ? p.stock_display : `${fmt(p.stock_quantity)} ${p.unit||'dona'}`) : t('pos.zeroStock')}</span></div>
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

      {/* ── D2.6: RETSEPT OYNASI (faqat dorixona rejimi) ── */}
      {/* P.7: quti / blister / dona tanlash (faqat dorixonada) */}
      {pharmacy && unitPick && (() => {
        const opts = unitOptions(unitPick.p);
        return (
          <div className="fixed inset-0 z-[120] bg-black/50 flex items-center justify-center p-4" onClick={() => setUnitPick(null)}
            data-testid="pharmacy-unit-pick">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-5 space-y-3" onClick={e => e.stopPropagation()}>
              <div>
                <div className="text-xs font-bold text-slate-400 uppercase">{tf('pos.unitPickTitle', 'Qanday sotiladi?')}</div>
                <div className="text-lg font-black text-slate-800 leading-tight">{unitPick.p.name}</div>
                <div className="flex flex-wrap items-center gap-1.5 mt-1">
                  {expiryBadges(unitPick.p, 'lg')}
                  {unitPick.p.stock_display && (
                    <span className="text-xs font-bold text-slate-500">{t('pos.stockLabel')} {unitPick.p.stock_display}</span>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                {opts.map((o, i) => (
                  <button key={o.unit ? o.unit.id : 'base'} type="button" disabled={o.disabled}
                    onClick={() => confirmUnitPick(i)}
                    onMouseEnter={() => { if (!o.disabled) setUnitPick(u => (u ? { ...u, sel: i } : u)); }}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 text-left transition-colors ${i === unitPick.sel ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'} ${o.disabled ? 'opacity-40 cursor-not-allowed' : 'hover:border-blue-400'}`}>
                    <span>
                      <span className="block text-base font-black text-slate-800">1 {o.name}</span>
                      {o.ratio > 1 && <span className="block text-xs font-semibold text-slate-500">{fmt(o.ratio)} {unitPick.p.unit || 'dona'}</span>}
                      {o.disabled && <span className="block text-xs font-semibold text-red-600">{tf('pos.noWholeBox', "Butun quti yo'q")}</span>}
                    </span>
                    <span className="text-xl font-black text-blue-700">{fmt(o.price)}</span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400 text-center">{tf('pos.unitPickHint', '↑ ↓ — tanlash · Enter — savatga · Esc — bekor')}</p>
            </div>
          </div>
        );
      })()}

      {pharmacy && rxModal && (() => {
        const rxItems = rxProductsOf(cart).filter((it, i, arr) => arr.findIndex(x => x.product_id === it.product_id) === i);
        const anyNoRx = rxItems.some(it => !isControlled(it) && rxMode !== 'block' && (rxData[it.product_id]?.mode === 'norx'));
        const inputCls = 'border border-slate-300 rounded-lg px-2 py-1.5 text-sm font-semibold text-slate-700 outline-none focus:border-blue-500 w-full';
        return (
          <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="rx-modal">
            <div className="bg-white rounded-2xl shadow-2xl w-[640px] max-w-[96vw] max-h-[92vh] flex flex-col overflow-hidden">
              <div className="bg-violet-700 px-5 py-3 text-white">
                <div className="font-black text-base">{tf('pos.rxTitle', "Retsept ma'lumotlari")}</div>
                <div className="text-violet-100 text-xs">
                  {rxMode === 'block'
                    ? tf('pos.rxModeBlock', 'Retseptli dori retseptsiz sotilmaydi')
                    : tf('pos.rxModeWarn', 'Retsept kiriting yoki retseptsiz sotish sababini yozing')}
                </div>
              </div>
              <div className="p-4 overflow-y-auto space-y-3">
                {rxModal.message && (
                  <div className="bg-red-50 border border-red-200 text-red-700 text-sm font-semibold rounded-lg px-3 py-2">{rxModal.message}</div>
                )}
                {rxItems.map(it => {
                  const d = rxData[it.product_id] || {};
                  const controlled = isControlled(it);
                  const canSkip = !controlled && rxMode !== 'block';
                  const mode = canSkip ? (d.mode || 'rx') : 'rx';
                  return (
                    <div key={it.product_id} className="border border-slate-200 rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-black text-slate-800 text-sm flex-1">{it.product_name}</span>
                        {controlled
                          ? <span className="px-1.5 rounded text-[10px] font-bold bg-red-100 text-red-700">{tf('pos.rxControlled', 'Nazoratda')}</span>
                          : <span className="px-1.5 rounded text-[10px] font-bold bg-violet-100 text-violet-700">Rx</span>}
                      </div>
                      {canSkip && (
                        <div className="flex gap-4 mb-2 text-sm font-bold text-slate-600">
                          <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" checked={mode === 'rx'} onChange={() => setRxField(it.product_id, 'mode', 'rx')} />
                            {tf('pos.rxHas', 'Retsept bor')}
                          </label>
                          <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" checked={mode === 'norx'} onChange={() => setRxField(it.product_id, 'mode', 'norx')} />
                            {tf('pos.rxNone', 'Retseptsiz sotish')}
                          </label>
                        </div>
                      )}
                      {mode === 'rx' && (
                        <div className="grid grid-cols-2 gap-2">
                          <input className={inputCls} placeholder={tf('pos.rxNumber', 'Retsept raqami')} value={d.number || ''} onChange={e => setRxField(it.product_id, 'number', e.target.value)} />
                          <input className={inputCls} type="date" max={todayLocalIso()} value={d.issued_at || ''} onChange={e => setRxField(it.product_id, 'issued_at', e.target.value)} />
                          <input className={inputCls} placeholder={tf('pos.rxDoctor', 'Shifokor')} value={d.doctor || ''} onChange={e => setRxField(it.product_id, 'doctor', e.target.value)} />
                          <input className={inputCls} placeholder={tf('pos.rxClinic', 'Muassasa')} value={d.clinic || ''} onChange={e => setRxField(it.product_id, 'clinic', e.target.value)} />
                          <input className={inputCls} placeholder={tf('pos.rxPatient', 'Bemor (ixtiyoriy)')} value={d.patient || ''} onChange={e => setRxField(it.product_id, 'patient', e.target.value)} />
                          <select
                            className={inputCls}
                            value={d.blank_type || (controlled ? '' : 'simple')}
                            onChange={e => setRxField(it.product_id, 'blank_type', e.target.value)}
                          >
                            {controlled && <option value="">{tf('pos.rxBlankPick', 'Blank turini tanlang (majburiy)')}</option>}
                            {!controlled && <option value="simple">{tf('pos.rxBlankSimple', 'Oddiy blank')}</option>}
                            <option value="form_107">{tf('pos.rxBlank107', '107-1/u blank')}</option>
                            <option value="form_148">{tf('pos.rxBlank148', '148-1/u blank')}</option>
                            <option value="special">{tf('pos.rxBlankSpecial', 'Maxsus blank')}</option>
                          </select>
                        </div>
                      )}
                    </div>
                  );
                })}
                {anyNoRx && (
                  <textarea
                    className={`${inputCls} h-16`}
                    placeholder={tf('pos.rxReason', 'Retseptsiz sotish sababi (majburiy)')}
                    value={rxReason}
                    onChange={e => setRxReason(e.target.value)}
                  />
                )}
                {rxError && <div className="text-red-600 text-sm font-bold">{rxError}</div>}
              </div>
              <div className="px-4 py-3 border-t border-slate-100 flex gap-3">
                <button onClick={() => { setRxModal(null); setRxError(''); }} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50">
                  {tf('common.cancel', 'Bekor qilish')}
                </button>
                <button onClick={confirmRx} className="flex-1 py-2.5 rounded-xl bg-violet-700 hover:bg-violet-800 text-white font-black text-sm">
                  {tf('pos.rxConfirm', 'Tasdiqlash')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── D2.6: ANALOGLAR OYNASI ── */}
      {pharmacy && analogModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="analog-modal">
          <div className="bg-white rounded-2xl shadow-2xl w-[620px] max-w-[96vw] max-h-[88vh] flex flex-col overflow-hidden">
            <div className="bg-emerald-700 px-5 py-3 text-white flex items-center">
              <div className="flex-1">
                <div className="font-black text-base">{tf('pos.analogs', 'Analoglar')}</div>
                <div className="text-emerald-100 text-xs">
                  {analogModal.auto ? tf('pos.analogsAuto', "Qoldiq yo'q — {name} o'rniga:", { name: analogModal.name }) : analogModal.name}
                </div>
              </div>
              <button onClick={() => setAnalogModal(null)} className="w-8 h-8 rounded-full bg-white/20 hover:bg-white/30 font-bold">&times;</button>
            </div>
            <div className="p-3 overflow-y-auto space-y-2">
              {analogModal.loading && <div className="text-center text-slate-400 font-bold py-6">{t('pos.refreshing')}</div>}
              {!analogModal.loading && analogModal.error && <div className="text-center text-red-500 font-bold py-6">{t('common.error')}</div>}
              {!analogModal.loading && !analogModal.error && analogModal.items.length === 0 && (
                <div className="text-center text-slate-400 font-bold py-6">{tf('pos.analogsNone', 'Analog topilmadi')}</div>
              )}
              {analogModal.items.map(a => (
                <div key={a.id} className="border border-slate-200 rounded-xl p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-black text-slate-800 text-sm truncate">{a.name}</div>
                    <div className="flex flex-wrap gap-1.5 mt-1 text-[11px] font-bold">
                      <span className="text-blue-700">{fmt(a.sale_price)}</span>
                      <span className={a.in_stock ? 'text-emerald-600' : 'text-red-500'}>
                        {a.in_stock ? `${tf('pos.stockLabel', 'Qoldiq')}: ${fmt(a.valid_quantity)}` : t('pos.zeroStock')}
                      </span>
                      {expiryBadges(a, 'sm')}
                      {a.is_rx && <span className="px-1 rounded bg-violet-100 text-violet-700">Rx</span>}
                      {[a.dosage_form, a.strength, a.manufacturer].filter(Boolean).length > 0 && (
                        <span className="text-slate-400">{[a.dosage_form, a.strength, a.manufacturer].filter(Boolean).join(' · ')}</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => addAnalogToCart(a)}
                    disabled={!a.in_stock}
                    className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-black text-xs disabled:opacity-40"
                  >
                    {tf('pos.analogAdd', 'Savatga')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── D2.6: SOTUV XATOSI (server 400: muddat, butun quti, markirovka...) ── */}
      {pharmacy && saleError && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="sale-error-modal">
          <div className="bg-white rounded-2xl shadow-2xl w-[480px] max-w-[96vw] overflow-hidden">
            <div className="bg-red-600 px-5 py-3 text-white font-black text-base">
              {saleError.category === 'expiry' ? tf('pos.errExpiry', "Muddati o'tgan yoki yaroqsiz dori")
                : saleError.category === 'marking' ? tf('pos.errMarking', 'Markirovka xatosi')
                : saleError.category === 'stock' ? tf('pos.errStock', 'Qoldiq yetarli emas')
                : tf('pos.errRejected', 'Sotuv rad etildi')}
            </div>
            <div className="px-5 py-4 text-slate-700 font-semibold text-sm">{saleError.message}</div>
            {saleError.boxFix && (
              <div className="px-5 pb-2 text-xs text-slate-500 font-semibold">
                {tf('pos.wholeBoxHint', 'Butun quti yetmaydi — dona qilib sotishingiz mumkin.')}
              </div>
            )}
            <div className="px-5 pb-4 pt-2 flex gap-3">
              <button onClick={() => setSaleError(null)} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50">
                {tf('common.close', 'Yopish')}
              </button>
              {saleError.boxFix && (
                <button onClick={applyBoxFix} className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-black text-sm">
                  {tf('pos.sellByPiece', 'Dona qilib sotish')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── D2.6: OFLAYN NAVBATDAN RAD ETILGAN SOTUVLAR (sabab bilan) ── */}
      {pharmacy && rejectedModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="rejected-modal">
          <div className="bg-white rounded-2xl shadow-2xl w-[600px] max-w-[96vw] max-h-[88vh] flex flex-col overflow-hidden">
            <div className="bg-red-600 px-5 py-3 text-white flex items-center">
              <div className="flex-1 font-black text-base">{tf('pos.rejectedTitle', 'Server rad etgan oflayn sotuvlar')}</div>
              <button onClick={() => setRejectedModal(false)} className="w-8 h-8 rounded-full bg-white/20 hover:bg-white/30 font-bold">&times;</button>
            </div>
            <div className="p-3 overflow-y-auto space-y-2">
              {rejectedSales.length === 0 && <div className="text-center text-slate-400 font-bold py-6">{tf('pos.rejectedNone', "Rad etilgan sotuv yo'q")}</div>}
              {rejectedSales.map((r, i) => {
                const reason = r.reason || describeRejection(r.detail);
                return (
                  <div key={i} className="border border-red-200 bg-red-50 rounded-xl p-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                      <span>{r.localNumber || ''}</span>
                      <span>{r.rejectedAt ? new Date(r.rejectedAt).toLocaleString('uz-UZ') : ''}</span>
                      <span className="ml-auto px-1.5 rounded bg-red-100 text-red-700 uppercase">
                        {reason.category === 'rx' ? tf('pos.rejRx', 'Retsept')
                          : reason.category === 'expiry' ? tf('pos.rejExpiry', 'Muddat')
                          : reason.category === 'marking' ? tf('pos.rejMarking', 'Markirovka')
                          : reason.category === 'stock' ? tf('pos.rejStock', 'Qoldiq')
                          : tf('pos.rejOther', 'Boshqa')}
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-slate-700 mt-1">{reason.text}</div>
                  </div>
                );
              })}
            </div>
            <div className="px-4 py-3 border-t border-slate-100 flex gap-3">
              <button onClick={() => setRejectedModal(false)} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50">
                {tf('common.close', 'Yopish')}
              </button>
              {rejectedSales.length > 0 && (
                <button onClick={clearRejectedSales} className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-900 text-white font-black text-sm">
                  {tf('pos.rejectedClear', "Ro'yxatni tozalash")}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

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
                       <span className="font-black text-2xl text-slate-700">{fmt(payableNet)}</span>
                    </div>

                    {payments.map((p, idx) => (
                      <div key={idx}>
                      <div className={`mt-2 flex gap-3 items-center bg-white border-[3px] ${activeInputIdx===idx?'border-blue-500 ring-4 ring-blue-500/20':'border-slate-200'} rounded-2xl px-4 py-3 cursor-pointer transition-all`} onClick={()=>setActiveInputIdx(idx)}>
                         <select value={p.type} onChange={e => {
                            const next = [...payments]; next[idx].type = e.target.value; next[idx].reference = ''; next[idx].terminal_id = ''; setPayments(next);
                         }} className="bg-transparent font-black text-slate-600 outline-none uppercase cursor-pointer">
                            <option value="cash">{t('pos.paymentCash')}</option>
                            <option value="card">{t('pos.paymentCard')}</option>
                            <option value="uzcard">UZCARD</option>
                            <option value="humo">HUMO</option>
                            <option value="payme">PAYME</option>
                            <option value="click">CLICK</option>
                            <option value="bank">{t('pos.transferLabel')}</option>
                         </select>
                         <div className={`flex-1 text-right text-3xl font-black tracking-tight ${p.amount?'text-emerald-500':'text-slate-300'}`}>{p.amount ? fmt(parseAmt(p.amount)) : "0"}</div>
                         {payments.length > 1 && (
                            <button onClick={(e)=>{ e.stopPropagation(); setPayments(prev => prev.filter((_, i) => i !== idx)); setActiveInputIdx(0); }} className="text-blue-400 hover:text-white hover:bg-blue-500 w-8 h-8 rounded-xl flex items-center justify-center transition-colors">
                               <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                         )}
                      </div>
                      {/* T3.18: provayder to'lovi — terminal (bir nechta bo'lsa) va tranzaksiya raqami */}
                      {REF_PROVIDERS.includes(p.type) && (providerTerminals(p.type).length > 0 || p.type !== 'uzum') && (
                        <div className="mt-1 flex gap-2 items-center px-1">
                          {providerTerminals(p.type).length > 1 && (
                            <select value={p.terminal_id || ''} onChange={e => {
                              const next = [...payments]; next[idx].terminal_id = e.target.value; setPayments(next);
                            }} className="bg-white border border-slate-200 rounded-xl px-2 py-2 text-xs font-bold text-slate-600 outline-none">
                              <option value="">{tf('pos.terminalSelect', 'Terminal')}</option>
                              {providerTerminals(p.type).map(x => (
                                <option key={x.id} value={x.id}>{x.label || x.merchant_id || `#${x.id}`}</option>
                              ))}
                            </select>
                          )}
                          <input
                            type="text"
                            maxLength={64}
                            value={p.reference || ''}
                            onChange={e => { const next = [...payments]; next[idx].reference = e.target.value; setPayments(next); }}
                            placeholder={tf('pos.referencePlaceholder', 'Tranzaksiya raqami') + (referenceRequired(p) ? ' *' : '')}
                            className={`flex-1 bg-white border rounded-xl px-3 py-2 text-sm font-semibold outline-none focus:border-blue-500 ${referenceRequired(p) && !String(p.reference || '').trim() ? 'border-amber-400' : 'border-slate-200'}`}
                          />
                        </div>
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
                             nxt[activeInputIdx].amount = String(Math.max(0, payableNet - otherSum));
                             return nxt; 
                          });
                       }} className="flex-1 bg-blue-50 hover:bg-blue-100 border-[3px] border-blue-200 text-blue-600 rounded-2xl flex items-center justify-center active:scale-95 transition-all font-black text-sm uppercase px-2 text-center leading-tight">{t('pos.exactAmount')}</button>
                    </div>
                 </div>
               </div>

               {/* Right Summary Section */}
               <div className="flex-1 flex flex-col p-8 bg-slate-50">
                  <div className="bg-white rounded-3xl p-6 shadow-xl shadow-slate-200/50 border border-slate-100 flex-1 flex flex-col">
                     
                     <div className="space-y-4 mb-6">
                        {/* Keshbek / ball bilan to'lash (T2.12) — faqat mijoz tanlangan va online bo'lsa */}
                        {canRedeem && (
                          <div className="rounded-2xl border-2 border-amber-200 bg-amber-50 p-4 space-y-3">
                            <div className="flex justify-between items-center text-amber-700 font-bold text-sm">
                              <span>{tf('pos.cashbackAvailable', 'Mavjud keshbek / ball')}</span>
                              <span>{fmt(bonusAvail)} UZS · {fmt(pointsAvail)}</span>
                            </div>
                            {bonusAvail > 0 && (
                              <div className="flex items-center gap-2">
                                <span className="flex-1 text-sm font-black text-slate-600">{tf('pos.payWithCashback', "Keshbek bilan to'lash")}</span>
                                <input
                                  inputMode="numeric"
                                  value={redeemCash ? fmt(redeemCashAmt) : ''}
                                  onChange={e => setRedeemCash(e.target.value.replace(/\D/g, ''))}
                                  placeholder="0"
                                  className="w-36 text-right text-lg font-black border-2 border-amber-300 rounded-xl px-3 py-2 outline-none focus:border-amber-500 bg-white"
                                />
                                <button type="button" onClick={() => setRedeemCash(String(Math.min(bonusAvail, maxRedeemUzs)))}
                                  className="px-3 py-2 text-xs font-black rounded-xl bg-amber-200 text-amber-800 hover:bg-amber-300">MAX</button>
                              </div>
                            )}
                            {pointsAvail > 0 && (
                              <div className="flex items-center gap-2">
                                <span className="flex-1 text-sm font-black text-slate-600">
                                  {tf('pos.payWithPoints', "Ball bilan to'lash")} <span className="text-xs text-slate-400">(1 = {fmt(pointValue)} UZS)</span>
                                </span>
                                <input
                                  inputMode="numeric"
                                  value={redeemPts ? fmt(redeemPtsCnt) : ''}
                                  onChange={e => setRedeemPts(e.target.value.replace(/\D/g, ''))}
                                  placeholder="0"
                                  className="w-36 text-right text-lg font-black border-2 border-amber-300 rounded-xl px-3 py-2 outline-none focus:border-amber-500 bg-white"
                                />
                                <button type="button" onClick={() => setRedeemPts(String(Math.min(pointsAvail, Math.floor(Math.max(0, maxRedeemUzs - redeemCashAmt) / pointValue))))}
                                  className="px-3 py-2 text-xs font-black rounded-xl bg-amber-200 text-amber-800 hover:bg-amber-300">MAX</button>
                              </div>
                            )}
                          </div>
                        )}
                        <div className="flex justify-between items-center text-slate-500 font-bold">
                          <span className="uppercase text-sm tracking-widest">{t('pos.totalBill')}</span>
                          <span className="text-xl">{fmt(totalNet)} UZS</span>
                        </div>
                        {redeemUzs > 0 && (
                          <div className="flex justify-between items-center text-amber-600 font-bold">
                            <span className="uppercase text-sm tracking-widest">{tf('pos.cashbackAndPoints', 'Keshbek / ball')}</span>
                            <span className="text-xl">− {fmt(redeemUzs)} UZS</span>
                          </div>
                        )}
                        <div className="flex justify-between items-center text-emerald-600 font-black border-t-2 border-dashed border-slate-200 pt-4">
                          <span className="uppercase text-lg tracking-widest">{t('pos.entered')}</span>
                          <span className="text-2xl">{fmt(finalPaid)} UZS</span>
                        </div>
                        
                        {/* Qaytim or Qarz indikatori */}
                        <div className={`flex justify-between items-center mt-4 p-4 rounded-2xl border-[3px] ${isEnough ? 'bg-emerald-50 border-emerald-500 text-emerald-700' : 'bg-blue-50 border-blue-500 text-blue-700'}`}>
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
      {markingModal && cart[markingModal.idx] && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/70 p-4" onClick={() => setMarkingModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 px-5 py-3.5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-black text-white">{t('pos.scanMarkingCode')}</h2>
                <p className="text-red-100 text-xs font-medium">{cart[markingModal.idx].product_name}</p>
              </div>
              <button onClick={() => setMarkingModal(null)} className="w-8 h-8 bg-white/20 hover:bg-white/30 rounded-lg flex items-center justify-center text-white">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
            <div className="p-5 flex flex-col gap-3">
              <p className="text-sm text-slate-500">
                {t('pos.markingScanInstruction')}
                {' '}{t('pos.markingRequiredCount')} <span className="font-bold text-slate-700">{cart[markingModal.idx].qty_ordered}</span> {t('pos.pieceUnit')}.
              </p>
              <input
                autoFocus
                type="text"
                placeholder={t('pos.scanCodePlaceholder')}
                className="w-full border border-slate-300 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-200"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addMarkingCode(markingModal.idx, e.target.value);
                    e.target.value = '';
                  }
                }}
              />
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
                {(cart[markingModal.idx].marking_codes || []).length === 0 && (
                  <div className="text-xs text-slate-400 text-center py-3">{t('pos.noCodeScannedYet')}</div>
                )}
                {(cart[markingModal.idx].marking_codes || []).map((code, ci) => (
                  <div key={ci} className="flex items-center justify-between gap-2 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5">
                    <span className="text-xs font-mono text-slate-700 truncate">{code}</span>
                    <button onClick={() => removeMarkingCode(markingModal.idx, ci)} className="text-red-400 hover:text-red-600 shrink-0">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={() => setMarkingModal(null)}
                disabled={(cart[markingModal.idx].marking_codes || []).length < cart[markingModal.idx].qty_ordered}
                className="w-full py-2.5 rounded-xl font-bold text-white bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-300 disabled:cursor-not-allowed"
              >
                {(cart[markingModal.idx].marking_codes || []).length}/{cart[markingModal.idx].qty_ordered} {t('pos.scannedDashClose')}
              </button>
            </div>
          </div>
        </div>
      )}

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
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">{t('pos.barcodeSkuLabel')}</label>
                <input
                  value={newProd.barcode}
                  onChange={e => setNewProd(p => ({...p, barcode: e.target.value}))}
                  className="w-full border-2 border-amber-300 bg-amber-50 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/20"
                  placeholder={t('pos.barcodePlaceholder')}
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
                  placeholder={t('pos.enterProductNamePlaceholder')}
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
             <h2 className="text-2xl font-black text-slate-800 mb-6">{t('pos.kassaSettingsTitle')}</h2>
             <div className="space-y-4">
               <div>
                  <label className="block text-sm font-bold text-slate-500 mb-2">{t('pos.paperSize')}</label>
                  <select value={posSettings.paper} onChange={e=>savePosSettings({paper:e.target.value})} className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500">
                    <option value="80mm">{t('pos.paper80mm')}</option>
                    <option value="58mm">{t('pos.paper58mm')}</option>
                  </select>
               </div>
               <div>
                  <label className="block text-sm font-bold text-slate-500 mb-2">{t('pos.receiptTemplateLabel')}</label>
                  <select value={posSettings.template || '80'} onChange={e=>savePosSettings({template:e.target.value})} className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500">
                    <option value="80">{t('pos.template80mm')}</option>
                    <option value="58">{t('pos.template58mm')}</option>
                    <option value="nak">{t('pos.templateA4Nakladnaya')}</option>
                  </select>
               </div>
               <div className="border border-blue-200 rounded-xl p-3 bg-blue-50/50 flex items-start gap-2">
                  <svg className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <p className="text-xs font-semibold text-blue-600">{t('pos.storeNameLogoHint')} → <b>{t('pos.settingsReceiptTemplatePath')}</b></p>
               </div>
               <div className="flex items-center gap-3 pt-4">
                  <input type="checkbox" id="ap" checked={posSettings.autoPrint} onChange={e=>savePosSettings({autoPrint:e.target.checked})} className="w-6 h-6 rounded" />
                  <label htmlFor="ap" className="font-bold text-slate-700 cursor-pointer">{t('pos.enableAutoPrint')}</label>
               </div>
               <div className="pt-4 border-t border-slate-100 mt-2">
                  <label className="block text-sm font-bold text-slate-600 mb-2">{t('pos.defaultCustomerLabel')}</label>
                  <select
                    value={posSettings.defaultCustomer || ''}
                    onChange={e => { savePosSettings({ defaultCustomer: e.target.value }); setCustId(e.target.value); }}
                    className="w-full bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500"
                  >
                    <option value="">{t('pos.notSelected')}</option>
                    {customers.map(c => <option key={c.id} value={c.id}>{c.name}{c.phone ? ` (${c.phone})` : ''}</option>)}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">{t('pos.defaultCustomerHint')}</p>
               </div>
             </div>
             <div className="mt-8 flex justify-end gap-3">
               <button onClick={()=>setShowSettings(false)} className="px-6 py-3 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-xl active:scale-95 transition-all">{t('admin.dict.close') || 'Yopish'}</button>
             </div>
           </div>
        </div>
      )}

      {/* T4.6: limitdan oshgan chegirma/narx — menejer tasdig'i */}
      <ApprovalModal flow={approvalFlow} />

      {showDebtModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm flex flex-col overflow-hidden">
             <div className="bg-blue-500 px-6 py-4 flex items-center justify-between">
               <h2 className="text-xl font-black text-white">{t('pos.setDebtDueDateTitle')}</h2>
               <button onClick={()=>setShowDebtModal(false)} className="text-white opacity-70 hover:opacity-100 transition-colors">
                 <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" /></svg>
               </button>
             </div>
             <div className="p-6 space-y-4">
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex justify-between items-center">
                   <span className="font-bold text-slate-500 uppercase text-xs">{t('pos.debtAmount')}</span>
                   <span className="font-black text-xl text-blue-600">{fmt(remaining)} UZS</span>
                </div>
                <div>
                   <label className="block text-xs font-bold text-slate-500 mb-2 uppercase">{t('pos.dueDate')}</label>
                   <input type="date" value={debtDueDate} onChange={e=>setDebtDueDate(e.target.value)} className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500" />
                </div>
                <div>
                   <label className="block text-xs font-bold text-slate-500 mb-2 uppercase">{t('pos.noteOptional')}</label>
                   <input type="text" value={debtNote} onChange={e=>setDebtNote(e.target.value)} placeholder={t('pos.debtReasonPlaceholder')} className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 font-bold text-slate-700 outline-none focus:border-blue-500" />
                </div>
             </div>
             <div className="p-6 pt-0 flex gap-3">
                <button onClick={()=>setShowDebtModal(false)} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl active:scale-95 transition-all">{t('common.back')}</button>
                <button onClick={()=>checkout(true)} disabled={isPaying || !debtDueDate} className="flex-1 py-3 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white font-black rounded-xl active:scale-95 transition-all text-sm uppercase tracking-widest">
                  {isPaying ? t('pos.paying') : t('common.confirm')}
                </button>
             </div>
          </div>
        </div>
      )}

    
      {variantParent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h2 className="text-xl font-black text-slate-800">{variantParent.name} - {t('pos.variants')}</h2>
              <button onClick={() => setVariantParent(null)} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-4">
              {products.filter(p => p.parent_code === variantParent.id).map(v => {
                const size = v.attributes?.find(a => a.key === 'Size' || a.key === "O'lcham")?.value || '';
                const color = v.attributes?.find(a => a.key === 'Color' || a.key === 'Rang')?.value || '';
                const label = [size, color].filter(Boolean).join(' | ') || v.name;
                return (
                  <button key={v.id} onClick={() => { addToCart(v); setVariantParent(null); }} className="p-4 border border-slate-200 rounded-2xl hover:border-blue-400 hover:bg-blue-50 hover:shadow-lg transition-all text-left flex flex-col gap-2 group">
                    <span className="font-bold text-slate-700 group-hover:text-blue-700">{label}</span>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-bold text-blue-600">{Number(v.sale_price).toLocaleString()} UZS</span>
                      <span className="text-slate-500">{v.stock_quantity || 0} {v.unit}</span>
                    </div>
                  </button>
                );
              })}
              {products.filter(p => p.parent_code === variantParent.id).length === 0 && (
                <div className="col-span-full py-8 text-center text-slate-400">{t('pos.noVariantsFound')}</div>
              )}
            </div>
          </div>
        </div>
      )}

</div>
  );
}



