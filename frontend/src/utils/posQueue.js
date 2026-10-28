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
            // D2.6: rad etish sababi (retsept / muddat / markirovka / boshqa) — kassirga aniq ko'rsatish uchun
            rejected.push({ ...item, kind, detail, reason: describeRejection(detail), rejectedAt: Date.now() });
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

// ─── D2.6: dorixona POS yordamchilari (faqat dorixona rejimida ishlatiladi) ───────────────────────────

/** Bugungi sana (kassir qurilmasi vaqt mintaqasida) YYYY-MM-DD — retsept sanasi kelajakda bo'lmasligi uchun */
export function todayLocalIso() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** ISO sana (2026-03-05 yoki 2026-03-05T00:00:00) -> 05.03.2026 */
export function fmtExpiry(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

/** Server rad etgan sotuv sababi: { category: 'rx'|'expiry'|'marking'|'stock'|'other', text, products }.
 *  detail — satr yoki { code, message, products: [{name}] } (D1.2 muddat, D2.5 retsept, D3.2 markirovka xatolari). */
export function describeRejection(detail) {
  const isObj = detail && typeof detail === 'object' && !Array.isArray(detail);
  const msg = isObj ? String(detail.message || '') : String(detail || '');
  const code = isObj ? String(detail.code || '') : '';
  const products = isObj && Array.isArray(detail.products) ? detail.products.map(p => p?.name).filter(Boolean) : [];
  let category = 'other';
  if (code === 'rx_required' || code === 'rx_blank_invalid' || /retsept/i.test(msg)) category = 'rx';
  else if (/markirovka|data\s*matrix/i.test(msg) || /kod.*(sotilgan|topilmadi|yaroqsiz)/i.test(msg)) category = 'marking';
  else if (/muddat|yaroqlilik|expir/i.test(msg)) category = 'expiry';
  else if (/butun quti|qoldiq|yetarli/i.test(msg)) category = 'stock';
  const text = products.length ? `${msg} (${products.join(', ')})` : msg;
  return { category, text: text || (isObj ? JSON.stringify(detail) : ''), products };
}

/** Savatdagi retseptli (is_rx) yoki nazoratdagi dorilar (nomi: product_name yoki name). */
export function rxProductsOf(items) {
  return (items || []).filter(it => it && (it.is_rx || (it.control_class && it.control_class !== 'none')));
}

export const isControlled = (it) => !!(it && it.control_class && it.control_class !== 'none');

/** So'rovga qo'shiladigan maydonlar: { prescriptions, rx_override_reason } (bo'sh bo'lsa — bo'sh obyekt).
 *  P.13: retsept ixtiyoriy — faqat kassir kiritgan (hech bo'lmasa bitta maydoni to'ldirilgan) retseptlar yuboriladi. */
export function buildRxPayload(items, rxData, reason, rxMode = 'warn') {
  const prescriptions = [];
  let needReason = false;
  for (const it of rxProductsOf(items)) {
    const d = (rxData || {})[it.product_id] || {};
    const mode = isControlled(it) || rxMode === 'block' ? 'rx' : (d.mode || 'rx');
    if (mode === 'norx') { needReason = true; continue; }
    if (![d.number, d.doctor, d.clinic, d.issued_at].some(v => String(v || '').trim())) continue;
    prescriptions.push({
      product_id: it.product_id,
      number: String(d.number || '').trim(),
      issued_at: d.issued_at,
      doctor: String(d.doctor || '').trim(),
      clinic: String(d.clinic || '').trim(),
      patient: String(d.patient || '').trim() || undefined,
      blank_type: isControlled(it) ? (d.blank_type || 'form_107') : (d.blank_type || 'simple'),
    });
  }
  const out = {};
  if (prescriptions.length) out.prescriptions = prescriptions;
  if (needReason && String(reason || '').trim()) out.rx_override_reason = String(reason).trim();
  return out;
}

/** Qatordagi birlik ro'yxat narxi (mijozga maxsus/narx turi bo'lmasa serverdagi `unit.price`, aks holda asosiy narx * nisbat). */
export function unitLinePrice(basePrice, productSalePrice, unit) {
  if (!unit) return Number(basePrice) || 0;
  const ratio = Number(unit.ratio) || 1;
  if (unit.price != null && Number(basePrice) === (Number(productSalePrice) || 0)) return Number(unit.price);
  return (Number(basePrice) || 0) * ratio;
}

/** P.13: omborda butun quti yo'q, faqat ochilgan quti bor — skanerda/tanlashda quti o'rniga kichik birlik taklif
 *  qilinadi (cheklov emas: quti ham tanlanadi). Qoldiq umuman yo'q bo'lsa — quti (eng katta birlik). */
export const openedBoxOnly = (p) => !!p && p.pack_ratio != null && p.full_boxes != null
  && Number(p.full_boxes) < 1 && Number(p.loose_units) > 0;

/** Server "butun quti X ta, ochilgan qutida Y dona bor" (D2.4) xatosini ajratadi; boshqa xato uchun null. */
export function parseWholeBoxError(detail) {
  const msg = typeof detail === 'string' ? detail : String(detail?.message || '');
  const m = /^(.*?):\s*butun quti\s+([\d.,]+)\s*ta,\s*ochilgan qutida\s+([\d.,]+)\s*dona/i.exec(msg);
  return m ? { name: m[1].trim(), boxes: m[2], loose: m[3], message: msg } : null;
}
