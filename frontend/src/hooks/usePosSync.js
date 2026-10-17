/**
 * usePosSync — POS uchun offline/online sinxronizatsiya hook.
 *
 * Funksiyalar:
 * 1. Internet holatini kuzatadi (online/offline).
 * 2. Offline bo'lganda sotuv va vazvratlarni localStorage ga saqlaydi.
 * 3. Internet qayta ulanganda — saqlangan (pending) sotuvlarni serverga yuboradi.
 * 4. Mahsulotlar, mijozlar, kategoriyalar ro'yxatlarini keshda saqlaydi.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';
import { getStoredLang, createTranslator } from '../i18n/index.js';

import {
  PENDING_SALES_BASE, PENDING_RETURNS_BASE, queueKey, getPending, setPending,
  getPendingPosCount, flushPosQueue, getCurrentUser,
} from '../utils/posQueue';

const CACHE_PRODUCTS_KEY = 'pos_cache_products';
const CACHE_CONTEXT_KEY = 'pos_cache_context';
const CACHE_CUSTOMERS_KEY = 'pos_cache_customers';
const CACHE_CATEGORIES_KEY = 'pos_cache_categories';

// ─── Yordamchi funksiyalar ──────────────────────────────────────────────────

// Katalog sahifalab yuklanadi (T3.11): /products/pos-list limit<=5000, bitta so'rovda 1000 ta
const PRODUCTS_PAGE_SIZE = 1000;
const PRODUCTS_MAX_PAGES = 20;

async function fetchAllPages(url, params = {}) {
  const all = [];
  for (let page = 0; page < PRODUCTS_MAX_PAGES; page++) {
    const r = await api.get(url, { params: { ...params, limit: PRODUCTS_PAGE_SIZE, skip: page * PRODUCTS_PAGE_SIZE } });
    const rows = Array.isArray(r.data) ? r.data : (r.data.items || []);
    all.push(...rows);
    if (rows.length < PRODUCTS_PAGE_SIZE) break;
  }
  return all;
}

// T1.17: mahsulot keshi korxona/filial/ombor bo'yicha ajratiladi — filial yoki ombor
// almashganda eski filial qoldig'i ko'rsatilmaydi: pos_cache_products:{company}:{branch}:{warehouse}
function scopedCacheKey(base, warehouseId) {
  let companyId = '';
  try { companyId = JSON.parse(localStorage.getItem('user'))?.company_id ?? ''; } catch { /* ignore */ }
  let branchId = '';
  try { branchId = localStorage.getItem('current_branch_id') || ''; } catch { /* ignore */ }
  return `${base}:${companyId}:${branchId}:${warehouseId || ''}`;
}

function saveToCache(key, data) {
  const user = getCurrentUser();
  const write = (d) => localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data: d, company_id: user?.company_id }));
  try {
    write(data);
  } catch {
    // Kvota to'ldi (katta katalog, ~5 MB): rasm havolalarisiz qayta yozamiz, u ham sig'masa — keshsiz davom etamiz
    try {
      if (Array.isArray(data)) write(data.map(({ image_url, ...rest }) => rest)); // eslint-disable-line no-unused-vars
      else throw new Error('quota');
    } catch {
      try { localStorage.removeItem(key); } catch { /* ignore */ }
    }
  }
}

function loadFromCache(key) {
  try {
    const raw = JSON.parse(localStorage.getItem(key));
    // Boshqa korxona keshi ko'rsatilmaydi (T3.11)
    if (!raw || raw.company_id !== getCurrentUser()?.company_id) return null;
    return raw.data || null;
  } catch { return null; }
}

// ─── Asosiy hook ────────────────────────────────────────────────────────────

export default function usePosSync({ onSyncSuccess } = {}) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [syncing, setSyncing] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const syncRef = useRef(false);

  // Pending count ni yangilab turish
  const refreshPendingCount = useCallback(() => {
    setPendingCount(getPendingPosCount());
  }, []);

  // Serverga pending sotuvlarni yuborish
  const syncPending = useCallback(async () => {
    if (syncRef.current || !navigator.onLine) return;
    syncRef.current = true;
    setSyncing(true);

    // Server 4xx (validatsiya) xatosi bergan savdoni cheksiz qayta urinish
    // o'rniga alohida "rad etilgan" ro'yxatga o'tkazamiz va kassirga
    // ko'rsatamiz — aks holda savdo jimgina yo'qolib qolardi (chek bosilgan,
    // lekin bazaga hech qachon yozilmaydi). Tarmoq/5xx xatolari navbatda qoladi.
    // Faqat JORIY korxona navbati yuboriladi (flushPosQueue), boshqa korxonaniki tegilmaydi.
    let result = { sent: 0 };
    try {
      result = await flushPosQueue(api, {
        onReject: (item, kind, detail) => {
          // T4.6: detail obyekt bo'lishi mumkin ({code, message, ...})
          const isObj = detail && typeof detail === 'object' && !Array.isArray(detail);
          const label = kind === 'return' ? 'vazvrat' : 'sotuv';
          if (isObj && detail.code === 'approval_required') {
            // Oflayn navbatdagi amal menejer tasdig'ini talab qiladi — "tasdiq kerak" holati
            toast.error(
              `DIQQAT: oflayn ${label} uchun menejer tasdig'i kerak, shuning uchun yuborilmadi${detail.message ? `: ${detail.message}` : ''}. Amalni qayta kiriting va tasdiq so'rang.`,
              { duration: 15000 }
            );
            return;
          }
          const text = isObj ? (detail.message || JSON.stringify(detail)) : detail;
          toast.error(
            `DIQQAT: oflayn ${label} server tomonidan RAD ETILDI va saqlanmadi: ${text}`,
            { duration: 15000 }
          );
        },
      });
    } finally {
      refreshPendingCount();
      setSyncing(false);
      syncRef.current = false;
    }

    if (result.sent > 0 && typeof onSyncSuccess === 'function') {
      onSyncSuccess(result.sent);
    }
  }, [onSyncSuccess, refreshPendingCount]);

  // Online/offline eventlarini tinglash
  useEffect(() => {
    const goOnline = () => {
      setIsOnline(true);
      syncPending();
    };
    const goOffline = () => setIsOnline(false);

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);

    // Sahifa ochilganda ham pending bo'lsa yuborish
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshPendingCount();
    if (navigator.onLine) syncPending();

    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, [syncPending, refreshPendingCount]);

  // ─── Sotuv saqlash (offline yoki online) ──────────────────────────────
  // options.suppressToast — axios xato toast'ini ko'rsatmaydi (chaqiruvchi o'zi, masalan tasdiq modali, ko'rsatadi)
  const submitSaleOrQueue = useCallback(async (payload, isReturn = false, { suppressToast = false } = {}) => {
    // Har bir sotuv uchun bitta doimiy kalit — timeout/qayta yuborishda
    // server dublikat sotuv yaratmaydi (Idempotency-Key).
    const idemKey = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    if (!navigator.onLine) {
      // T2.12: keshbek/ball balansini oflayn tekshirib bo'lmaydi — bunday sotuv navbatga qo'yilmaydi
      if (!isReturn && (Number(payload?.paid_cashback) > 0 || Number(payload?.loyalty_points_used) > 0)) {
        const k = 'pos.cashbackNeedsInternet';
        const tr = createTranslator(getStoredLang())(k);
        const msg = tr && tr !== k ? tr : "Keshbekdan to'lash uchun internet kerak";
        const err = new Error(msg);
        err.response = { data: { detail: msg } };
        throw err;
      }
      // Offline: locally ga saqlash
      // Sotuv vaqti (UTC ISO, "Z") navbatga tushadi: sinxronda sotuv server vaqtiga emas,
      // haqiqiy vaqtga yoziladi (T3.11). Qaytarish (SaleReturnRequest) da created_at yo'q.
      const user = getCurrentUser();
      const key = queueKey(isReturn ? PENDING_RETURNS_BASE : PENDING_SALES_BASE, user?.company_id);
      const pending = getPending(key);
      const queuedPayload = isReturn
        ? payload
        : { ...payload, created_at: new Date().toISOString(), local_id: idemKey };
      // T3.7: chekda server raqami o'rniga oflayn raqam (OFL-XXXXXXXX) chiqadi
      const localNumber = 'OFL-' + String(idemKey).replace(/[^a-zA-Z0-9]/g, '').slice(0, 8).toUpperCase();
      pending.push({
        payload: queuedPayload, idemKey, savedAt: Date.now(), localNumber,
        user_id: user?.id ?? null, company_id: user?.company_id ?? null,
      });
      setPending(key, pending);
      refreshPendingCount();
      return { offline: true, localNumber };
    }

    // Online: to'g'ridan serverga yuborish
    const endpoint = isReturn ? '/sales/return' : '/sales/';
    const res = await api.post(endpoint, payload, {
      headers: { 'Idempotency-Key': idemKey },
      ...(suppressToast ? { _suppressToast: true } : {}),
    });
    return { offline: false, data: res.data };
  }, [refreshPendingCount]);

  // ─── Kesh yordamida ma'lumot olish ────────────────────────────────────
  // fetcher(url, params) -> massiv; berilmasa bitta GET (fon yangilash va birinchi yuklash bir xil funksiyadan o'tadi)
  const fetchWithCache = useCallback(async (url, cacheKey, params = {}, fetcher = null) => {
    const load = fetcher || (async (u, p) => {
      const r = await api.get(u, { params: p });
      return Array.isArray(r.data) ? r.data : (r.data.items || []);
    });
    if (!navigator.onLine) {
      return loadFromCache(cacheKey) || [];
    }
    const cached = loadFromCache(cacheKey);
    if (cached) {
      // Kesh bor — darhol qaytar, fon fonda serverdan yangilasin
      load(url, params).then(fresh => {
        saveToCache(cacheKey, fresh);
      }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
      return cached;
    }
    // Kesh yo'q — serverdan kutib olish (birinchi marta)
    try {
      const data = await load(url, params);
      saveToCache(cacheKey, data);
      return data;
    } catch {
      return [];
    }
  }, []);

  // ─── Kesh funksiyalari ─────────────────────────────────────────────────
  const fetchProducts = useCallback(
    (params = {}) => fetchWithCache(
      '/products/pos-list', scopedCacheKey(CACHE_PRODUCTS_KEY, params.warehouse_id), params, fetchAllPages,
    ),
    [fetchWithCache]
  );

  // POS ombor tanlagichi uchun: { branch_id, default_warehouse_id, warehouses: [{id,name,type}] }
  const fetchPosContext = useCallback(async () => {
    const key = scopedCacheKey(CACHE_CONTEXT_KEY);
    if (!navigator.onLine) return loadFromCache(key);
    try {
      const r = await api.get('/products/pos-context');
      saveToCache(key, r.data);
      return r.data;
    } catch {
      return loadFromCache(key);
    }
  }, []);

  // params: { limit, search, card, ... } — GET /customers ga to'g'ridan-to'g'ri o'tadi (T2.12: karta/qidiruv server tomonida)
  // T3.8: `limit: 500` — faqat OFLAYN zaxira ro'yxat; onlayn qidiruv CustomerPicker orqali serverda (GET /customers?search=)
  const fetchCustomers = useCallback(async (params = {}) => {
    try {
      const r = await api.get('/customers/', { params: { limit: 500, ...params } });
      return Array.isArray(r.data) ? r.data : (r.data.items || []);
    } catch {
      return [];
    }
  }, []);

  const fetchCategories = useCallback(
    (params = {}) => fetchWithCache('/categories/', CACHE_CATEGORIES_KEY, { limit: 200, ...params }),
    [fetchWithCache]
  );

  return {
    isOnline,
    syncing,
    pendingCount,
    submitSaleOrQueue,
    fetchProducts,
    fetchPosContext,
    fetchCustomers,
    fetchCategories,
    syncPending,
  };
}
