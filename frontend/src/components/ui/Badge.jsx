const COLOR_MAP = {
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  danger: 'bg-danger/10 text-danger',
  brand: 'bg-brand/10 text-brand',
  neutral: 'bg-surface-sunken text-ink-500',
};

// Status belgisi — rang bilan bir qatorda matn ham bo'ladi (faqat rangga
// tayanilmaydi), premium-dizayn-texnik-topshiriq.md 2.4-band, 1-prinsip
export function Badge({ children, color = 'neutral', dot = true, className = '' }) {
  const colorCls = COLOR_MAP[color] || COLOR_MAP.neutral;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${colorCls} ${className}`}>
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />}
      {children}
    </span>
  );
}
