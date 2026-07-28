/**
 * hippoLocal.js
 * ─────────────
 * Hippo Communicator bilan muloqot qiluvchi frontend moduli.
 *
 * Electron app (e-code-pos) da ishlasa:
 *   → window.hippo.* (IPC orqali, Node.js, CORS muammosi yo'q) ✅
 *
 * Oddiy brauzerda ishlasa (fallback):
 *   → http://127.0.0.1:8082 (hippo_bridge.py orqali)
 */

// ── Electron aniqlash ────────────────────────────────────────────────────────
const isElectron = () => typeof window !== 'undefined' && !!window.hippo;

// ── VAT mapping (fallback uchun) ─────────────────────────────────────────────
const VAT_MAP = { standard: 12, zero: 0, exempt: 0, nds_12: 12, nds_0: 0, no_nds: 0 };
const getVatPercent = (t) => VAT_MAP[t] ?? 12;

// ── Cart → Hippo items ───────────────────────────────────────────────────────
function cartToItems(cart) {
  return cart.map(item => ({
    name:         item.product_name || item.name || 'Mahsulot',
    barcode:      item.barcode       || '',
    spic:         item.mxik_code     || '',
    package_code: item.package_code  ? String(item.package_code) : '',
    labels:       item.labels        || [],
    quantity:     Number(item.qty_ordered || item.quantity || 1),
    price:        Math.round(Number(item.unit_price || 0)),
    discount:     Math.round(Number(item.discount   || 0)),
    vat_percent:  getVatPercent(item.vat_rate_type),
  }));
}

// ── To'lovlarni ajratish ─────────────────────────────────────────────────────
function splitPayments(payments) {
  const CASH  = new Set(['cash']);
  let cash = 0, card = 0;
  for (const p of (payments || [])) {
    const amt = parseInt(p.amount || 0, 10);
    if (CASH.has(p.type)) cash += amt; else card += amt;
  }
  return { receivedCash: cash, received_card: card };
}

// ── Direct fetch (fallback) ───────────────────────────────────────────────────
const BRIDGE = 'http://127.0.0.1:8082';
async function bridgeFetch(method, path, body = null) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await fetch(`${BRIDGE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    return await res.json().catch(() => ({}));
  } finally { clearTimeout(t); }
}

// ────────────────────────────────────────────────────────────────────────────
// PUBLIC API
// ────────────────────────────────────────────────────────────────────────────

/** Hippo Communicator health check */
export async function hippoHealth() {
  if (isElectron()) return window.hippo.health();
  return bridgeFetch('GET', '/api/fiscal-module/v1/fiscal-module');
}

/** Ulangan fiskal qurilmalar ro'yxati */
export async function getFiscalModules() {
  if (isElectron()) return window.hippo.listDevices();
  return bridgeFetch('GET', '/api/fiscal-module/v1/fiscal-module');
}

/**
 * Sotuv chekini fiskallash
 * @param {{ factoryId, cart, payments, discountAmount }} opts
 */
export async function registerReceipt({ factoryId, cart, payments, discountAmount = 0 }) {
  const items = cartToItems(cart);
  const { receivedCash, received_card } = splitPayments(payments);
  const receipt = {
    receivedCash,
    received_card,
    discount:  Math.round(Number(discountAmount || 0)),
    type:      0,   // 0 = oddiy sotuv
    operation: 0,   // 0 = sotuv
  };

  if (isElectron()) {
    return window.hippo.fiscalize(factoryId, receipt, items);
  }
  return bridgeFetch('POST', '/api/fiscalization/v1/receipt/register', {
    factory_id: factoryId,
    receipt: { ...receipt, items },
  });
}

/**
 * Qaytarish chekini fiskallash
 */
export async function registerReturn({ factoryId, cart, discountAmount = 0 }) {
  const items = cartToItems(cart);
  const receipt = {
    receivedCash:  0,
    received_card: 0,
    discount:      0,
    type:          0,
    operation:     1,   // 1 = qaytarish
  };

  if (isElectron()) {
    return window.hippo.fiscalize(factoryId, receipt, items);
  }
  return bridgeFetch('POST', '/api/fiscalization/v1/receipt/register', {
    factory_id: factoryId,
    receipt: { ...receipt, items },
  });
}

/** Z-report ochish */
export async function openZReport(factoryId) {
  if (isElectron()) return window.hippo.openShift(factoryId);
  return bridgeFetch('POST', '/api/report/v1/z-report/open', { factory_id: factoryId });
}

/** Z-report yopish */
export async function closeZReport(factoryId) {
  if (isElectron()) return window.hippo.closeShift(factoryId);
  return bridgeFetch('POST', '/api/report/v1/z-report/close', { factory_id: factoryId });
}

/**
 * Fiskal chekni printer ga yuborish
 * @param {string} factoryId
 * @param {string|number} transactionId  — registerReceipt javobidagi transaction_id
 */
export async function printFiscalReceipt(factoryId, transactionId) {
  if (isElectron()) {
    return window.hippo.printReceipt(factoryId, transactionId);
  }
  return bridgeFetch('POST', '/api/fiscalization/v1/receipt/print', {
    factory_id:     factoryId,
    transaction_id: transactionId,
  });
}

/**
 * Fiskallash + chop etish birgalikda (checkout modal tomonidan ishlatiladi)
 * @returns {{ fiscal: object, printed: boolean }}
 */
export async function fiscalizeAndPrint({ factoryId, cart, payments, discountAmount = 0 }) {
  const fiscal = await registerReceipt({ factoryId, cart, payments, discountAmount });
  let printed = false;
  const txId = fiscal?.transaction_id ?? fiscal?.TransactionID;

  // PDF to'g'ridan qaytsa — Electron printer ga yubor
  if (fiscal?.receipt_pdf_base64_content) {
    try {
      if (isElectron() && window.electron?.print?.fiscalPdf) {
        await window.electron.print.fiscalPdf(fiscal.receipt_pdf_base64_content, '');
        printed = true;
      }
    } catch { /* chop xatosi fiskalizatsiyani bekor qilmaydi */ }
  } else if (txId) {
    try {
      await printFiscalReceipt(factoryId, txId);
      printed = true;
    } catch { /* chop xatosi fiskalizatsiyani bekor qilmaydi */ }
  }

  return { fiscal, printed };
}

