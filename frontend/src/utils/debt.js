/**
 * Mijoz qarz ma'lumotlarini olish uchun yordamchi funksiyalar.
 *
 * Ma'lumot mantig'i:
 * - `debt_balances` — yangi format: { UZS: 1000, USD: 5 } kabi ob'ekt
 * - `debt_balance`  — eski format: UZS ekvivalentidagi umumiy qarz
 *
 * Muhim: `debt_balances` mavjud bo'lsa ham, u to'liq bo'lmasligi mumkin
 * (masalan, backend uni kech qo'shgan, eski operatsiyalar u yerda aks etmagan).
 * Shuning uchun:
 *   - Agar `debt_balances` mavjud va bo'sh EMAS → undan foydalanish
 *   - Agar `debt_balances` yo'q yoki bo'sh         → `debt_balance` dan foydalanish (eski format)
 */

/**
 * Mijozning UZS qarzini qaytaradi.
 */
export const getUzsDebt = (c) => {
  if (!c) return 0;
  const hasNewFormat =
    c.debt_balances &&
    typeof c.debt_balances === 'object' &&
    Object.keys(c.debt_balances).length > 0;

  if (hasNewFormat) {
    return Number(c.debt_balances.UZS || 0);
  }
  // Eski format: debt_balance ni to'g'ridan-to'g'ri ishlatish
  return Number(c.debt_balance || 0);
};

/**
 * UZS bo'lmagan boshqa valyutadagi qarzlarni qaytaradi.
 * Faqat yangi formatda (`debt_balances`) mavjud bo'lsa ishlaydi.
 */
export const getOtherDebts = (c) => {
  if (!c || !c.debt_balances || typeof c.debt_balances !== 'object') return [];
  return Object.entries(c.debt_balances)
    .filter(([curr, amt]) => curr !== 'UZS' && Number(amt) !== 0)
    .map(([currency, amount]) => ({ currency, amount }));
};

/**
 * Mijozning umumiy qarz holati bor-yo'qligini aniqlaydi.
 */
export const hasAnyDebt = (c) => {
  if (!c) return false;
  if (Math.abs(getUzsDebt(c)) > 0.001) return true;
  return getOtherDebts(c).length > 0;
};

/**
 * Jadval va qidiruv uchun to'g'ri qarz ro'yxatini qaytaradi.
 * Har bir element: { currency: string, amount: number }
 *
 * Eski mijozlar uchun: [{ currency: 'UZS', amount: debt_balance }]
 * Yangi mijozlar uchun: debt_balances dagi barcha valyutalar
 */
export const getDebtEntries = (c) => {
  if (!c) return [];
  const hasNewFormat =
    c.debt_balances &&
    typeof c.debt_balances === 'object' &&
    Object.keys(c.debt_balances).length > 0;

  if (hasNewFormat) {
    return Object.entries(c.debt_balances)
      .filter(([, amt]) => Number(amt) !== 0)
      .map(([currency, amount]) => ({ currency, amount: Number(amount) }));
  }
  // Eski format
  const amt = Number(c.debt_balance || 0);
  if (amt !== 0) {
    return [{ currency: c.debt_currency || 'UZS', amount: amt }];
  }
  return [];
};

