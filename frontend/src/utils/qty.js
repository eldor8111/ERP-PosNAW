// Miqdor / qoldiq ko'rinishi. Server Decimal ni satr qilib beradi ("53.000", "2.500"); o'zgartirmay chiqarilsa
// "53.000" ko'rinadi. "53.000" -> "53", "2.500" -> "2,5", 1200 -> "1 200"; bo'sh -> "0"
export function fmtQty(v) {
  if (v === null || v === undefined || v === '') return '0';
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('uz-UZ', { maximumFractionDigits: 3 }) : String(v);
}
