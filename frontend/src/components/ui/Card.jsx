const COLOR_MAP = {
  brand: 'bg-brand/10 text-brand',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  danger: 'bg-danger/10 text-danger',
};

export function Card({ children, className = '', padding = true }) {
  return (
    <div className={`bg-surface rounded-2xl border border-line shadow-sm ${padding ? 'p-5' : ''} ${className}`}>
      {children}
    </div>
  );
}

// KPI / statistika kartochkasi — Mijozlar/Ombor sahifalaridagi hozirgi
// naqshga mos (icon-chip + label + katta raqam), token'lardan foydalanadi
export function StatCard({ icon, label, value, color = 'brand', trend, className = '' }) {
  const colorCls = COLOR_MAP[color] || COLOR_MAP.brand;

  return (
    <Card className={`flex items-center gap-4 ${className}`}>
      {icon && (
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${colorCls}`}>
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-ink-300 font-semibold">{label}</div>
        <div className="text-xl font-bold tabular-nums text-ink-900">{value}</div>
        {trend != null && (
          <div className={`text-xs font-medium mt-0.5 ${trend >= 0 ? 'text-success' : 'text-danger'}`}>
            {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}%
          </div>
        )}
      </div>
    </Card>
  );
}
