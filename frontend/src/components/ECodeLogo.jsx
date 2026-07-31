/**
 * E-code Logo Component
 * ASLIY SHAKL: daire + yuqori nuqta + E harfi
 * Ranglar: yashil (#16a34a) — har xil fon uchun moslashtirilgan
 */

const GREEN = '#059669';           // emerald-600 — oq fonda professional to'q yashil
const GREEN_DARK = '#047857';
const GREEN_GLOW = 'rgba(5,150,105,0.5)';
const GREEN_LIGHT = '#34d399';     // emerald-400 — qorang'u fonda yorqin yashil

const BLUE_LIGHT = '#60a5fa'; // blue-400 (for dark backgrounds)
const BLUE_DARK = '#2563eb';  // blue-600 (for light backgrounds)
const DARK_TEXT = '#1e293b';  // slate-800 (for light backgrounds)

export default function ECodeLogo({
  size = 48,
  showText = true,
  className = '',
}) {
  // If showText is true, render the full logo
  if (showText) {
    return (
      <div className={`flex items-center gap-2 ${className}`} style={{ width: 'fit-content' }}>
        <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
          {/* Shape 1: Dark U (Left) */}
          <path d="M 13 12 L 13 34 A 6 6 0 0 0 25 34 L 25 12" stroke={DARK_TEXT} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          {/* Shape 2: Blue U (Right) */}
          <path d="M 35 20 L 35 42 A 6 6 0 0 0 47 42 L 47 20" stroke={BLUE_DARK} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
        <span className="text-slate-800 font-bold text-2xl leading-none tracking-wide font-sans mt-1">E-code</span>
      </div>
    );
  }

  // If showText is false, render just the icon
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 12 L 13 34 A 6 6 0 0 0 25 34 L 25 12" stroke={DARK_TEXT} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 35 20 L 35 42 A 6 6 0 0 0 47 42 L 47 20" stroke={BLUE_DARK} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 12 L 13 34 A 6 6 0 0 0 25 34 L 25 12" stroke={DARK_TEXT} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 35 20 L 35 42 A 6 6 0 0 0 47 42 L 47 20" stroke={BLUE_DARK} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeLogoPrimary({ size = 48, className = '' }) {
  return (
    <div className={`flex items-center gap-2 ${className}`} style={{ width: 'fit-content' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
        <path d="M 13 12 L 13 34 A 6 6 0 0 0 25 34 L 25 12" stroke="white" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 35 20 L 35 42 A 6 6 0 0 0 47 42 L 47 20" stroke={BLUE_LIGHT} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
      <span className="text-white font-bold text-2xl leading-none tracking-wide font-sans mt-1">E-code</span>
    </div>
  );
}

export function ECodeIconLight({ size = 48, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 12 L 13 34 A 6 6 0 0 0 25 34 L 25 12" stroke="white" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 35 20 L 35 42 A 6 6 0 0 0 47 42 L 47 20" stroke={BLUE_LIGHT} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}
