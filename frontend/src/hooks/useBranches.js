import { useState, useEffect, useCallback } from 'react';
import api from '../api/axios';

/**
 * Filiallar ro'yxati (T3.8) — GET /branches 11 sahifada alohida yuklanardi.
 * Endi modul darajasidagi promise keshi: bir daqiqa ichida sahifalar o'rtasida o'tishda
 * so'rov bitta marta ketadi; parallel chaqiruvlar bitta so'rovga birlashadi.
 *
 * `useBranches({ includeInactive })` -> `{ branches, loading, reload }`
 *  - `reload()` keshni chetlab qayta yuklaydi;
 *  - `invalidateBranches()` — filial yaratilganda/o'zgartirilganda/o'chirilganda (yoki korxona
 *    almashtirilganda) chaqiriladi: kesh tozalanadi va ochiq hook'lar darhol yangilanadi.
 * Kesh kaliti: korxona + foydalanuvchi (`localStorage.user`) + includeInactive — boshqa korxona/
 * foydalanuvchiga o'tilganda eski ro'yxat ko'rinmaydi.
 */
const TTL_MS = 60_000;

const _cache = new Map();       // key -> { promise, ts }
const _listeners = new Set();   // invalidateBranches() ochiq hook'larni yangilaydi

function _scopeKey(includeInactive) {
  let companyId = '';
  let userId = '';
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    companyId = u?.company_id ?? '';
    userId = u?.id ?? '';
  } catch { /* localStorage mavjud emas yoki buzilgan */ }
  return `${companyId}:${userId}:${includeInactive ? 1 : 0}`;
}

function _load(includeInactive, force = false) {
  const key = _scopeKey(includeInactive);
  const hit = _cache.get(key);
  if (!force && hit && Date.now() - hit.ts < TTL_MS) return hit.promise;

  const promise = api
    .get('/branches', { _suppressToast: true, ...(includeInactive ? { params: { include_inactive: true } } : {}) })
    .then(r => (Array.isArray(r.data) ? r.data : []))
    .catch(() => {
      // Xato keshlanmaydi — keyingi chaqiruvda qayta so'raladi
      if (_cache.get(key)?.promise === promise) _cache.delete(key);
      const failed = []; failed.failed = true;   // C4.3: chaqiruvchi xatoni ajrata olsin (list.failed)
      return failed;
    });
  _cache.set(key, { promise, ts: Date.now() });
  return promise;
}

export function invalidateBranches() {
  _cache.clear();
  _listeners.forEach(fn => fn());
}

export function useBranches({ includeInactive = false } = {}) {
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async (force = true) => {   // reload(false) — keshdan (invalidateBranches() dan keyin ulashilgan so'rov)
    setLoading(true);
    const list = await _load(includeInactive, force !== false);
    setBranches(list);
    setLoading(false);
    return list;
  }, [includeInactive]);

  useEffect(() => {
    let alive = true;
    _load(includeInactive).then(list => {
      if (!alive) return;
      setBranches(list);
      setLoading(false);
    });
    // Filial qo'shilgan/o'zgargan: kesh tozalangan — darhol yangilaymiz
    const onInvalidate = () => {
      _load(includeInactive).then(list => { if (alive) setBranches(list); });
    };
    _listeners.add(onInvalidate);
    return () => { alive = false; _listeners.delete(onInvalidate); };
  }, [includeInactive]);

  return { branches, loading, reload };
}
