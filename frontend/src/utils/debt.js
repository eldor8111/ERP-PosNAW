export const getUzsDebt = (c) => {
  if (!c) return 0;
  // Agar debt_balances null yoki bo'sh ob'ekt bo'lsa (eski formatdagi mijozlar)
  if (!c.debt_balances || typeof c.debt_balances !== 'object' || Object.keys(c.debt_balances).length === 0) {
    return Number(c.debt_balance || 0);
  }
  // Yangi formatda bo'lsa, aniq UZS valyutadagi qarzni qaytaramiz
  return Number(c.debt_balances.UZS || 0);
};

export const getOtherDebts = (c) => {
  if (!c || !c.debt_balances || typeof c.debt_balances !== 'object') return [];
  return Object.entries(c.debt_balances)
    .filter(([curr, amt]) => curr !== 'UZS' && Number(amt) !== 0)
    .map(([currency, amount]) => ({ currency, amount }));
};

export const hasAnyDebt = (c) => {
  if (!c) return false;
  if (Math.abs(getUzsDebt(c)) > 0.001) return true;
  return getOtherDebts(c).length > 0;
};
