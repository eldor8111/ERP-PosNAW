/**
 * posQueue — Web POS oflayn navbati (sotuv/qaytarish) uchun yordamchilar (T3.11).
 *
 * Navbat korxona bo'yicha ajratiladi: `pos_pending_sales:<companyId>` va
 * `pos_pending_returns:<companyId>`. Shunda boshqa korxona foydalanuvchisi kirganda
 * oldingi korxonaning sotuvlari yangi token bilan yuborilmaydi va o'chib ketmaydi.
 * Eski (korxonasiz) `pos_pending_sales` / `pos_pending_returns` kalitlari birinchi
 * ochilishda joriy korxonaga ko'chiriladi.
 */

export const PENDING_SALES_BASE = 'pos_pending_sales';
export const PENDING_RETURNS_BASE = 'pos_pending_returns';
export const REJECTED_SALES_KEY = 'pos_rejected_sales';

export function getCurrentUser() {
  try { return JSON.parse(localStorage.getItem('user')) || null; } catch { return null; }
}

export function getCurrentCompanyId() {
  return getCurrentUser()?.company_id ?? null;
}

// Korxona ma'lum bo'lmasa (kirmagan) — eski umumiy kalit
export function queueKey(base, companyId = getCurrentCompanyId()) {
  return companyId == null || companyId === '' ? base : `${base}:${companyId}`;
}

export function getPending(key) {
  try {
    const arr = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(arr) ? arr : [];
  } catch { return []; }
}

export function setPending(key, arr) {
  if (!arr || arr.length === 0) {
    localStorage.removeItem(key);
    return;
  }
  localStorage.setItem(key, JSON.stringify(arr));
}

/**
 * Eski `pos_pending_*` kalitlarini korxona kalitiga ko'chiradi (bir marta).
 * Eski yozuvlarga company_id qo'shiladi; mavjud korxona navbati bilan birlashtiriladi.
 */
export function migrateLegacyQueue(companyId = getCurrentCompanyId()) {
  if (companyId == null || companyId === '') return;
  for (const base of [PENDING_SALES_BASE, PENDING_RETURNS_BASE]) {
    try {
      const legacyRaw = localStorage.getItem(base);
      if (legacyRaw == null) continue;
      const legacy = getPending(base).map(it => ({ ...it, company_id: it.company_id ?? companyId }));
      if (legacy.length > 0) {
        const target = queueKey(base, companyId);
        setPending(target, [...getPending(target), ...legacy]);
      }
      localStorage.removeItem(base);
    } catch { /* localStorage to'lgan/yopiq — navbat joyida qoladi */ }
  }
}

/** Joriy korxonaning kutayotgan sotuv + qaytarishlar soni (eski kalit ham hisobga olinadi). */
export function getPendingPosCount(companyId = getCurrentCompanyId()) {
  migrateLegacyQueue(companyId);
  return getPending(queueKey(PENDING_SALES_BASE, companyId)).length
    + getPending(queueKey(PENDING_RETURNS_BASE, companyId)).length;
}

let flushing = null;

/**
 * Joriy korxona navbatini serverga yuboradi. Faqat JORIY korxona navbati yuboriladi.
 * 4xx — rad etilganlar ro'yxatiga o'tadi, 5xx/tarmoq xatosi — navbatda qoladi.
 * Qaytaradi: { sent, rejected, remaining }.
 */
export function flushPosQueue(api, { onReject } = {}) {
  if (flushing) return flushing;
  flushing = (async () => {
    const companyId = getCurrentCompanyId();
    migrateLegacyQueue(companyId);
    const salesKey = queueKey(PENDING_SALES_BASE, companyId);
    const returnsKey = queueKey(PENDING_RETURNS_BASE, companyId);
    const rejected = getPending(REJECTED_SALES_KEY);
    let sent = 0;
    let rejectedCount = 0;

    const run = async (key, endpoint, kind) => {
      const items = getPending(key);
      const failed = [];
      for (const item of items) {
        // Boshqa korxonaga tegishli yozuv hech qachon joriy token bilan yuborilmaydi
        if (item.company_id != null && companyId != null && String(item.company_id) !== String(companyId)) {
          failed.push(item);
          continue;
        }
        try {
          await api.post(endpoint, item.payload, item.idemKey ? { headers: { 'Idempotency-Key': item.idemKey } } : undefined);
          sent += 1;
        } catch (e) {
          const status = e.response?.status;
          if (status >= 400 && status < 500) {
            const detail = e.response?.data?.detail || `HTTP ${status}`;
            rejected.push({ ...item, kind, detail, rejectedAt: Date.now() });
            rejectedCount += 1;
            if (typeof onReject === 'function') onReject(item, kind, detail);
          } else {
            failed.push(item);
          }
        }
      }
      // Yuborish davomida navbatga yangi yozuv qo'shilgan bo'lishi mumkin — ularni yo'qotmaymiz
      const current = getPending(key);
      const added = current.slice(items.length);
      setPending(key, [...failed, ...added]);
    };

    try {
      await run(salesKey, '/sales/', 'sale');
      await run(returnsKey, '/sales/return', 'return');
      setPending(REJECTED_SALES_KEY, rejected);
    } finally {
      flushing = null;
    }
    return { sent, rejected: rejectedCount, remaining: getPendingPosCount(companyId) };
  })();
  return flushing;
}
