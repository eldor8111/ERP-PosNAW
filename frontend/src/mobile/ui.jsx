// Mobil ilova uchun kichik UI to'plami — katta bosiladigan maydonlar
// (qo'lqop bilan ham), yuqori kontrast, dizayn tokenlari.
import { Loader2 } from 'lucide-react';

export function Page({ title, right, children, footer }) {
  return (
    <div className="flex flex-col h-full">
      {title && (
        <header className="shrink-0 flex items-center justify-between gap-3 px-4 pt-3 pb-2">
          <h1 className="text-xl font-bold text-ink-900 truncate">{title}</h1>
          {right}
        </header>
      )}
      <div className="flex-1 overflow-y-auto px-4 pb-4">{children}</div>
      {footer && <div className="shrink-0 px-4 py-3 border-t border-line bg-surface">{footer}</div>}
    </div>
  );
}

export function Btn({ children, variant = 'primary', loading, className = '', ...rest }) {
  const v = {
    primary: 'bg-brand text-white active:bg-brand-deep',
    success: 'bg-success text-white',
    danger: 'bg-danger text-white',
    ghost: 'bg-surface border border-line text-ink-900 active:bg-surface-sunken',
  }[variant];
  return (
    <button {...rest} disabled={loading || rest.disabled}
      className={`min-h-12 px-4 rounded-xl font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-50 transition-colors ${v} ${className}`}>
      {loading && <Loader2 className="size-4 animate-spin" />}{children}
    </button>
  );
}

export function Card({ children, className = '', ...rest }) {
  return <div {...rest} className={`bg-surface border border-line rounded-2xl p-4 ${className}`}>{children}</div>;
}

export function Empty({ icon: Icon, title, text }) {
  return (
    <div className="flex flex-col items-center text-center py-16 px-6 text-ink-300">
      {Icon && <Icon className="size-12 mb-3" />}
      <div className="font-semibold text-ink-500">{title}</div>
      {text && <div className="text-sm mt-1">{text}</div>}
    </div>
  );
}

