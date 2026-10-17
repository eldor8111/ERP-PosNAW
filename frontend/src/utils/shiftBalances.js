// Smena balanslari yordamchilari (T1.11).
// /shifts/current javobidagi `balances` ichma-ich: { ptype: { currency: "summa" } }.
// Oldin komponent `Number(obyekt)` qilar edi va "NaN so'm" ko'rsatardi.

// Haqiqiy pul tushmaydigan to'lov turlari — terminal jamiga kirmaydi
const NON_MONEY_TYPES = ['cash', 'debt', 'cashback', 'mixed'];

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

/** { UZS: '1500', USD: '5' } -> 1500 (faqat so'm qismi; bo'sh/noto'g'ri qiymat -> 0). */
export function uzs(map) {
  if (map === null || map === undefined) return 0;
  if (typeof map === 'object') return num(map.UZS);
  return num(map);
}

/** Barcha elektron to'lovlar (naqd, qarz, keshbek, aralashdan tashqari) so'mdagi jami. */
export function terminalUzs(balances) {
  return Object.entries(balances || {}).reduce(
    (acc, [ptype, map]) => (NON_MONEY_TYPES.includes(ptype) ? acc : acc + uzs(map)),
    0,
  );
}

/** UZS dan boshqa valyutalar: [['USD', 5], ...] (nolga teng qiymatlar tashlab ketiladi). */
export function foreignEntries(map) {
  if (!map || typeof map !== 'object') return [];
  return Object.entries(map)
    .filter(([cur]) => cur !== 'UZS')
    .map(([cur, v]) => [cur, num(v)])
    .filter(([, v]) => v !== 0);
}

/** i18n kaliti hali tarjima fayllarida bo'lmasa (t kalitni qaytaradi) — berilgan matn ishlatiladi. */
export function tOr(t, key, fallback) {
  const v = t(key);
  return v && v !== key ? v : fallback;
}
