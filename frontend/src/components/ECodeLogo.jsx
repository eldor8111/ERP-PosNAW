/**
 * E-code Logo Component
 * ASLIY SHAKL: daire + yuqori nuqta + E harfi
 * Ranglar: yashil (#16a34a) — har xil fon uchun moslashtirilgan
 */

const GREEN = '#059669';           // emerald-600 — oq fonda professional to'q yashil
const GREEN_DARK = '#047857';
const GREEN_GLOW = 'rgba(5,150,105,0.5)';
const GREEN_LIGHT = '#34d399';     // emerald-400 — qorang'u fonda yorqin yashil

const BLUE = '#60a5fa'; // blue-400
const DARK_BG = '#111827'; // gray-900

export default function ECodeLogo({
  size = 48,
  showText = true,
  className = '',
}) {
  // If showText is true, render the full pill logo
  if (showText) {
    return (
      <div className={`flex items-center bg-[#111827] rounded-[1.5rem] px-5 py-2 gap-3 shadow-lg ${className}`} style={{ width: 'fit-content' }}>
        <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
          {/* White U */}
          <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="white" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          {/* Blue U */}
          <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </svg>
        <div className="flex flex-col justify-center">
          <span className="text-white font-bold text-xl leading-none tracking-wide font-sans">E-code</span>
          <span className="text-blue-400 font-bold text-[10px] leading-tight tracking-[0.2em] mt-1 font-sans">PAPERLESS ERP</span>
        </div>
      </div>
    );
  }

  // If showText is false, render just the icon without the dark pill
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="#111827" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="#111827" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

export function ECodeLogoPrimary({ size = 48, className = '' }) {
  return (
    <div className={`flex items-center bg-[#111827] rounded-[1.5rem] px-5 py-2 gap-3 shadow-2xl shadow-blue-500/20 ${className}`} style={{ width: 'fit-content' }}>
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
        <path d="M 16 12 L 16 36 A 8 8 0 0 0 32 36 L 32 18" stroke="white" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
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
        <path d="M 32 18 L 32 46 A 8 8 0 0 0 48 46 L 48 24" stroke={BLUE} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}
