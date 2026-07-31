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
const BLUE_DARK = '#3b82f6';  // blue-500 (for light backgrounds)
const DARK_TEXT = '#1e293b';  // slate-800

export default function ECodeLogo({
  size = 48,
  showText = true,
  className = '',
}) {
  // If showText is true, render the full logo
  if (showText) {
    return (
      <div className={`flex items-center gap-3 ${className}`} style={{ width: 'fit-content' }}>
        <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
          {/* Dark U (instead of White) */}
          <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke={DARK_TEXT} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          {/* Blue U */}
          <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE_DARK} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
        <div className="flex flex-col justify-center">
          <span className="text-slate-800 font-bold text-xl leading-none tracking-wide font-sans">E-code</span>
          <span className="text-blue-500 font-bold text-[10px] leading-tight tracking-[0.2em] mt-1 font-sans">PAPERLESS ERP</span>
        </div>
      </div>
    );
  }

  // If showText is false, render just the icon
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke={DARK_TEXT} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE_DARK} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke={DARK_TEXT} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE_DARK} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeLogoPrimary({ size = 48, className = '' }) {
  return (
    <div className={`flex items-center gap-3 ${className}`} style={{ width: 'fit-content' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="white" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE_LIGHT} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
      <div className="flex flex-col justify-center">
        <span className="text-white font-bold text-xl leading-none tracking-wide font-sans">E-code</span>
        <span className="text-blue-400 font-bold text-[10px] leading-tight tracking-[0.2em] mt-1 font-sans">PAPERLESS ERP</span>
      </div>
    </div>
  );
}

export function ECodeIconLight({ size = 48, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="white" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE_LIGHT} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}
