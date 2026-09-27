export const inputCls = 'w-full min-h-12 px-4 rounded-xl border border-line bg-surface text-[15px] text-ink-900 focus:outline-none focus:ring-2 focus:ring-brand/40';

export const fmtMoney = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
