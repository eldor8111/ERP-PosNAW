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

const PENDING_SALES_KEY = 'pos_pending_sales';
const PENDING_RETURNS_KEY = 'pos_pending_returns';
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
  localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
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

    // 1. Sotuvlar
    const pendingSales = getPending(PENDING_SALES_KEY);
    const failedSales = [];
    for (const sale of pendingSales) {
      try {
        await api.post('/sales/', sale.payload);
      } catch {
        failedSales.push(sale);
      }
    }
    setPending(PENDING_SALES_KEY, failedSales);

    // 2. Vazvratlar
    const pendingReturns = getPending(PENDING_RETURNS_KEY);
    const failedReturns = [];
    for (const ret of pendingReturns) {
      try {
        await api.post('/sales/return', ret.payload);
      } catch {
        failedReturns.push(ret);
      }
    }
    setPending(PENDING_RETURNS_KEY, failedReturns);

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
    if (!navigator.onLine) {
      // Offline: locally ga saqlash
      const key = isReturn ? PENDING_RETURNS_KEY : PENDING_SALES_KEY;
      const pending = getPending(key);
      pending.push({ payload, savedAt: Date.now() });
      setPending(key, pending);
      refreshPendingCount();
      return { offline: true };
    }

    // Online: to'g'ridan serverga yuborish
    const endpoint = isReturn ? '/sales/return' : '/sales/';
    const res = await api.post(endpoint, payload);
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
      }).catch(() => {});
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
    (params = {}) => fetchWithCache('/products/', CACHE_PRODUCTS_KEY, { limit: 12000, status: 'active', ...params }),
    [fetchWithCache]
  );

  const fetchCustomers = useCallback(
    (params = {}) => fetchWithCache('/customers/', CACHE_CUSTOMERS_KEY, { limit: 500, ...params }),
    [fetchWithCache]
  );

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
