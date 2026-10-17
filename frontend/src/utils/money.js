// Pul ko'rinishi yordamchilari.

// 1200000 -> "1 200 000"; kasr qismi (USD kabi) 2 xonagacha, ortiqcha nollarsiz
function groupNumber(n) {
  const num = Number(n);
  if (!Number.isFinite(num)) return '0';
  const neg = num < 0;
  const [int, frac] = Math.abs(num).toFixed(2).split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const tail = frac.replace(/0+$/, '');
  return `${neg ? '-' : ''}${grouped}${tail ? '.' + tail : ''}`;
}

// i18n kaliti topilmasa t() kalitning o'zini qaytaradi — zaxira matn ishlatiladi
function sumLabel(t) {
  if (typeof t !== 'function') return "so'm";
  const s = t('common.sum');
  return !s || s === 'common.sum' ? "so'm" : s;
}

// /kassa javobidagi balances.total: massiv [{currency, value}] (kassa.py), eski son yoki undefined.
// Natija: "1 200 000 so'm · 50 USD"; bo'sh bo'lsa "0 so'm". UZS -> t('common.sum').
export function formatBalances(total, t) {
  const sum = sumLabel(t);
  if (Array.isArray(total)) {
    const parts = total
      .filter(b => b && Number(b.value) !== 0 && Number.isFinite(Number(b.value)))
      .map(b => {
        const cur = !b.currency || b.currency === 'UZS' ? sum : b.currency;
        return `${groupNumber(b.value)} ${cur}`;
      });
    return parts.length ? parts.join(' · ') : `0 ${sum}`;
  }
  const n = Number(total);
  return `${groupNumber(Number.isFinite(n) ? n : 0)} ${sum}`;
}
