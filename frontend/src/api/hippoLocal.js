/**
 * hippoLocal.js
 * ─────────────
 * Hippo Communicator bilan TO'G'RIDAN muloqot qiluvchi modul.
 * Hippo kassir kompyuterida localhost:8081 da ishlaydi.
 * Backend orqali EMAS — brauzerdan bevosita chaqiriladi.
 */

const HIPPO_BASE = 'http://127.0.0.1:8081';
const HIPPO_TIMEOUT = 5000; // 5 soniya

// ── VAT mapping ─────────────────────────────────────────────────────────────
const VAT_MAP = {
  standard: 12,
  zero:      0,
  exempt:    0,
  nds_12:   12,
  nds_0:     0,
  no_nds:    0,
};

function getVatPercent(vatRateType) {
  return VAT_MAP[vatRateType] ?? 12;
}

// ── HTTP yordamchi ──────────────────────────────────────────────────────────
async function hippoRequest(method, path, body = null) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HIPPO_TIMEOUT);

  try {
    const res = await fetch(`${HIPPO_BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    clearTimeout(timer);

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw Object.assign(new Error(data?.Message || `HTTP ${res.status}`), {
        status: res.status,
        payload: data,
      });
    }

    return data;
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new Error('Hippo javob bermadi (timeout 5s). Servis ishlab turganligini tekshiring.');
    }
    throw err;
  }
}

// ── Health check ─────────────────────────────────────────────────────────────
export async function hippoHealth() {
  return hippoRequest('GET', '/fiscalization/v1/fiscal-modules');
}

// ── Fiskal modullar ro'yxati ─────────────────────────────────────────────────
export async function getFiscalModules() {
  return hippoRequest('GET', '/fiscalization/v1/fiscal-modules');
}

// ── Chek ro'yxatdan o'tkazish ─────────────────────────────────────────────────
/**
 * cart: PosKassa.jsx dagi cart array
 * payments: [{ type: 'cash'|'card'|..., amount: 15000 }]
 * factoryId: localStorage.getItem('fiskalId')
 * discountAmount: umumiy chegirma
 */
export async function registerReceipt({ factoryId, cart, payments, discountAmount = 0 }) {
  // To'lovlarni ajratish
  const CASH_TYPES = new Set(['cash']);
  const CARD_TYPES = new Set(['card', 'uzcard', 'humo', 'payme', 'click', 'uzum']);

  let receivedCash = 0;
  let receivedCard = 0;

  for (const p of payments) {
    const amt = parseInt(p.amount || 0, 10);
    if (CASH_TYPES.has(p.type)) receivedCash += amt;
    else if (CARD_TYPES.has(p.type)) receivedCard += amt;
  }

  // Chek qatorlari
  const items = cart.map(item => ({
    name:         item.product_name || item.name || 'Mahsulot',
    barcode:      item.barcode || '',
    spic:         item.mxik_code || '',
    package_code: item.package_code ? String(item.package_code) : '',
    labels:       item.labels || [],
    quantity:     Number(item.qty_ordered || item.quantity || 1),
    price:        Math.round(Number(item.unit_price || 0)),
    discount:     Math.round(Number(item.discount || 0)),
    vat_percent:  getVatPercent(item.vat_rate_type),
  }));

  const payload = {
    factory_id: factoryId,
    receipt: {
      receivedCash,
      received_card: receivedCard,
      discount:      Math.round(Number(discountAmount || 0)),
      type:          0,      // 0 = oddiy sotuv
      operation:     0,      // 0 = sotuv
      items,
    },
  };

  return hippoRequest('POST', '/fiscalization/v1/receipt/register', payload);
}

// ── Qaytarish cheki ───────────────────────────────────────────────────────────
export async function registerReturn({ factoryId, cart, payments, discountAmount = 0 }) {
  const receipt = await registerReceipt({ factoryId, cart, payments, discountAmount });
  // operation=1 bilan qaytadan yuboring (qaytarish)
  // Amalda registerReceipt ni operation:1 bilan chaqiramiz
  return hippoRequest('POST', '/fiscalization/v1/receipt/register', {
    factory_id: factoryId,
    receipt: {
      receivedCash:  0,
      received_card: 0,
      discount:      0,
      type:          0,
      operation:     1,   // 1 = qaytarish
      items: cart.map(item => ({
        name:         item.product_name || item.name || 'Mahsulot',
        barcode:      item.barcode || '',
        spic:         item.mxik_code || '',
        package_code: item.package_code ? String(item.package_code) : '',
        labels:       item.labels || [],
        quantity:     Number(item.qty_ordered || item.quantity || 1),
        price:        Math.round(Number(item.unit_price || 0)),
        discount:     0,
        vat_percent:  getVatPercent(item.vat_rate_type),
      })),
    },
  });
}

// ── Z-report ochish ───────────────────────────────────────────────────────────
export async function openZReport(factoryId) {
  return hippoRequest('POST', '/report/v1/z-report/open', { factory_id: factoryId });
}

// ── Z-report yopish ───────────────────────────────────────────────────────────
export async function closeZReport(factoryId) {
  return hippoRequest('POST', '/report/v1/z-report/close', { factory_id: factoryId });
}
