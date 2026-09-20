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

const PENDING_SALES_KEY = 'pos_pending_sales';
const PENDING_RETURNS_KEY = 'pos_pending_returns';
const REJECTED_SALES_KEY = 'pos_rejected_sales';
const CACHE_PRODUCTS_KEY = 'pos_cache_products';
const CACHE_CUSTOMERS_KEY = 'pos_cache_customers';
const CACHE_CATEGORIES_KEY = 'pos_cache_categories';

// ─── Yordamchi funksiyalar ──────────────────────────────────────────────────

function getPending(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
}

function setPending(key, arr) {
  localStorage.setItem(key, JSON.stringify(arr));
}

function saveToCache(key, data) {
  const user = (() => { try { return JSON.parse(localStorage.getItem('user')); } catch { return null; } })();
  localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data, company_id: user?.company_id }));
}

function loadFromCache(key) {
  try {
    const raw = JSON.parse(localStorage.getItem(key));
    return raw?.data || null;
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
    const s = getPending(PENDING_SALES_KEY).length;
    const r = getPending(PENDING_RETURNS_KEY).length;
    setPendingCount(s + r);
  }, []);

  // Serverga pending sotuvlarni yuborish
  const syncPending = useCallback(async () => {
    if (syncRef.current || !navigator.onLine) return;
    syncRef.current = true;
    setSyncing(true);

    // Server 4xx (validatsiya) xatosi bergan savdoni cheksiz qayta urinish
    // o'rniga alohida "rad etilgan" ro'yxatga o'tkazamiz va kassirga
    // ko'rsatamiz — aks holda savdo jimgina yo'qolib qolardi (chek bosilgan,
    // lekin bazaga hech qachon yozilmaydi). Tarmoq xatolari navbatda qoladi.
    const rejected = getPending(REJECTED_SALES_KEY);
    const rejectSale = (item, kind, detail) => {
      rejected.push({ ...item, kind, detail, rejectedAt: Date.now() });
      toast.error(
        `DIQQAT: oflayn ${kind === 'return' ? 'vazvrat' : 'sotuv'} server tomonidan RAD ETILDI va saqlanmadi: ${detail}`,
        { duration: 15000 }
      );
    };

    // 1. Sotuvlar
    const pendingSales = getPending(PENDING_SALES_KEY);
    const failedSales = [];
    for (const sale of pendingSales) {
      try {
        // Idempotency-Key: qayta yuborishda server dublikat sotuv yaratmaydi
        await api.post('/sales/', sale.payload, sale.idemKey ? { headers: { 'Idempotency-Key': sale.idemKey } } : undefined);
      } catch (e) {
        const status = e.response?.status;
        if (status >= 400 && status < 500) {
          rejectSale(sale, 'sale', e.response?.data?.detail || `HTTP ${status}`);
        } else {
          failedSales.push(sale);
        }
      }
    }
    setPending(PENDING_SALES_KEY, failedSales);

    // 2. Vazvratlar
    const pendingReturns = getPending(PENDING_RETURNS_KEY);
    const failedReturns = [];
    for (const ret of pendingReturns) {
      try {
        await api.post('/sales/return', ret.payload);
      } catch (e) {
        const status = e.response?.status;
        if (status >= 400 && status < 500) {
          rejectSale(ret, 'return', e.response?.data?.detail || `HTTP ${status}`);
        } else {
          failedReturns.push(ret);
        }
      }
    }
    setPending(PENDING_RETURNS_KEY, failedReturns);
    setPending(REJECTED_SALES_KEY, rejected);

    refreshPendingCount();
    setSyncing(false);
    syncRef.current = false;

    const successCount =
      (pendingSales.length - failedSales.length) +
      (pendingReturns.length - failedReturns.length);

    if (successCount > 0 && typeof onSyncSuccess === 'function') {
      onSyncSuccess(successCount);
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
  const submitSaleOrQueue = useCallback(async (payload, isReturn = false) => {
    // Har bir sotuv uchun bitta doimiy kalit — timeout/qayta yuborishda
    // server dublikat sotuv yaratmaydi (Idempotency-Key).
    const idemKey = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    if (!navigator.onLine) {
      // Offline: locally ga saqlash
      const key = isReturn ? PENDING_RETURNS_KEY : PENDING_SALES_KEY;
      const pending = getPending(key);
      pending.push({ payload, idemKey, savedAt: Date.now() });
      setPending(key, pending);
      refreshPendingCount();
      return { offline: true };
    }

    // Online: to'g'ridan serverga yuborish
    const endpoint = isReturn ? '/sales/return' : '/sales/';
    const res = await api.post(endpoint, payload, isReturn ? undefined : { headers: { 'Idempotency-Key': idemKey } });
    return { offline: false, data: res.data };
  }, [refreshPendingCount]);

  // ─── Kesh yordamida ma'lumot olish ────────────────────────────────────
  const fetchWithCache = useCallback(async (url, cacheKey, params = {}) => {
    if (!navigator.onLine) {
      return loadFromCache(cacheKey) || [];
    }
    const cached = loadFromCache(cacheKey);
    if (cached) {
      // Kesh bor — darhol qaytar, fon fonda serverdan yangilasin
      api.get(url, { params }).then(r => {
        const fresh = Array.isArray(r.data) ? r.data : (r.data.items || []);
        saveToCache(cacheKey, fresh);
      }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
      return cached;
    }
    // Kesh yo'q — serverdan kutib olish (birinchi marta)
    try {
      const r = await api.get(url, { params });
      const data = Array.isArray(r.data) ? r.data : (r.data.items || []);
      saveToCache(cacheKey, data);
      return data;
    } catch {
      return [];
    }
  }, []);

  // ─── Kesh funksiyalari ─────────────────────────────────────────────────
  const fetchProducts = useCallback(
    (params = {}) => fetchWithCache('/products/pos-list', CACHE_PRODUCTS_KEY, params),
    [fetchWithCache]
  );

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
    fetchCustomers,
    fetchCategories,
    syncPending,
  };
}
