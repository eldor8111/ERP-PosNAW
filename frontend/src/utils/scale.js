// T3.12: tarozi (tortiladigan tovar) yordamchilari — eksport fayllari va POS skaneri bir xil PLU dan foydalanadi.

// Tarozi tovarlari birligi (backend SCALE_UNITS bilan bir xil)
export const SCALE_UNITS = ['kg', 'g'];

export const isScaleUnit = (unit) => SCALE_UNITS.includes(String(unit || '').trim().toLowerCase());

// Tovarning tarozi PLU kodi (5 xonali, nol bilan to'ldirilgan qator).
// plu_code bo'lsa shu; aks holda eski qoida: SKU raqamlarining oxirgi 5 tasi, bo'sh bo'lsa mahsulot ID si.
export function pluCode(p) {
  if (p && p.plu_code) return String(p.plu_code).padStart(5, '0');
  const digits = String((p && p.sku) ?? '').replace(/\D/g, '').slice(-5);
  return (digits || String((p && p.id) ?? '')).padStart(5, '0');
}

// PLU ni butun son sifatida (eksport fayllarida bosh nollarsiz yoziladi)
export const pluNumber = (p) => Number(pluCode(p)) || 0;

// Tarozi shtrix-kodi: 13 belgi, 20|21|22 + 5 (PLU) + 5 (vazn, gramm) + 1 (nazorat raqami)
export function parseScaleBarcode(code) {
  const c = String(code ?? '').trim();
  if (!/^\d{13}$/.test(c)) return null;
  const prefix = c.slice(0, 2);
  if (prefix !== '20' && prefix !== '21' && prefix !== '22') return null;
  return { plu: Number(c.slice(2, 7)), weightKg: Number(c.slice(7, 12)) / 1000 };
}

// Mahsulotlar ro'yxatidan PLU bo'yicha tovarni topish. Avval aniq plu_code, so'ng (plu_code hali
// berilmagan eski yozuvlar uchun) eski qoida bo'yicha hisoblangan kod.
export function findScaleProduct(products, plu) {
  const n = Number(plu);
  if (!Array.isArray(products) || !n) return null;
  const exact = products.find(p => p && Number(p.plu_code) === n);
  if (exact) return exact;
  return products.find(p => p && !p.plu_code && Number(pluCode(p)) === n) || null;
}
