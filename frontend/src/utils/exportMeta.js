// T2.5: Excel / PDF / 1C eksportlari uchun filial va davr ma'lumoti.
// Fayl nomi: <prefix>[_<filial>]_<boshlanish>_<tugash>.<ext> — turli filial/davr fayllari ajralib tursin.

const safePart = (s) => String(s ?? '')
  .trim()
  .replace(/[\/:*?"<>|'`]+/g, '')   // fayl nomida mumkin bo'lmagan va maxsus belgilar
  .replace(/\s+/g, '_')
  .replace(/_+/g, '_')
  .replace(/^_+|_+$/g, '');

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/**
 * exportFileName('sotuvlar', { branchName: 'Chilonzor', dateFrom: '2026-10-01', dateTo: '2026-10-14', ext: 'xlsx' })
 *   -> 'sotuvlar_Chilonzor_2026-10-01_2026-10-14.xlsx'
 * Filial berilmasa nomga qo'shilmaydi; davr berilmasa bugungi sana qo'yiladi.
 */
export function exportFileName(prefix, { branchName, dateFrom, dateTo, ext = 'xlsx' } = {}) {
  const parts = [safePart(prefix) || 'hisobot'];
  const branch = safePart(branchName);
  if (branch) parts.push(branch);
  if (dateFrom || dateTo) {
    parts.push(safePart(dateFrom || dateTo));
    if (dateTo && dateTo !== dateFrom) parts.push(safePart(dateTo));
  } else {
    parts.push(localToday());
  }
  return `${parts.join('_')}.${String(ext).replace(/^\./, '')}`;
}

/** "2026-10-01 — 2026-10-14" (bir kun bo'lsa — bitta sana); davr yo'q bo'lsa ''. */
export function periodText(dateFrom, dateTo) {
  if (!dateFrom && !dateTo) return '';
  if (!dateFrom || !dateTo || dateFrom === dateTo) return dateFrom || dateTo;
  return `${dateFrom} — ${dateTo}`;
}

/**
 * Excel varag'i boshidagi qatorlar (aoa): sarlavha, "Filial: ...", "Davr: ..." (davr bo'lsa).
 * Yorliqlar chaqiruvchi tomonidan beriladi (i18n).
 */
export function sheetHeaderRows({ title, branchName, dateFrom, dateTo, period, branchLabel = 'Filial', periodLabel = 'Davr' } = {}) {
  const rows = [];
  if (title) rows.push([title]);
  if (branchName) rows.push([`${branchLabel}: ${branchName}`]);
  const p = period || periodText(dateFrom, dateTo);
  if (p) rows.push([`${periodLabel}: ${p}`]);
  return rows;
}
