/**
 * E-code Logo Component
 * ASLIY SHAKL: daire + yuqori nuqta + E harfi
 * Ranglar: yashil (#16a34a) — har xil fon uchun moslashtirilgan
 */

const GREEN = '#059669';           // emerald-600 — oq fonda professional to'q yashil
const GREEN_DARK = '#047857';
const GREEN_GLOW = 'rgba(5,150,105,0.5)';
const GREEN_LIGHT = '#34d399';     // emerald-400 — qorang'u fonda yorqin yashil

/* ─── Yorug' (oq) fon uchun — sidebar, mobile ────────────────────────── */
export default function ECodeLogo({
  size = 32,
  showText = true,
  textClassName = 'text-[14px]',
  className = '',
}) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
      >
        {/* Tashqi daire — yashil */}
        <circle cx="24" cy="24" r="21" stroke={GREEN} strokeWidth="2.5" />
        {/* Yuqori kichik nuqta */}
        <circle cx="24" cy="5" r="2.8" fill={GREEN} />
        {/* E harfi */}
        <text
          x="24" y="30"
          fontFamily="Arial, sans-serif"
          fontSize="19"
          fontWeight="700"
          textAnchor="middle"
          fill={GREEN}
        >E</text>
      </svg>

      {showText && (
        <span className={`font-black leading-none tracking-tight ${textClassName} text-slate-800`}>
          <span style={{ color: GREEN }}>E</span>-code
        </span>
      )}
    </div>
  );
}

/* ─── Faqat ikonka — sidebar yig'ilgan holat ─────────────────────────── */
export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
      >
        <circle cx="24" cy="24" r="21" stroke={GREEN} strokeWidth="2.5" />
        <circle cx="24" cy="5" r="2.8" fill={GREEN} />
        <text
          x="24" y="30"
          fontFamily="Arial, sans-serif"
          fontSize="19"
          fontWeight="700"
          textAnchor="middle"
          fill={GREEN}
        >E</text>
      </svg>
    </div>
  );
}

/* ─── Qorang'u / gradient fon uchun (Login, Register chap panel) ──────
   Yashil daire + yashil E — qorang'u fonda glow bilan ajralib turadi
   ──────────────────────────────────────────────────────────────────── */
export function ECodeLogoPrimary({ size = 44, className = '' }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          flexShrink: 0,
          filter: `drop-shadow(0 0 10px ${GREEN_GLOW}) drop-shadow(0 2px 6px ${GREEN_GLOW})`,
        }}
      >
        {/* Yashil daire — qorang'u fonda glow bilan yaqqol ko'rinadi */}
        <circle cx="24" cy="24" r="21" stroke={GREEN_LIGHT} strokeWidth="2.8" />
        {/* Yashil nuqta */}
        <circle cx="24" cy="5" r="2.8" fill={GREEN_LIGHT} />
        {/* Yashil E harfi */}
        <text
          x="24" y="30"
          fontFamily="Arial, sans-serif"
          fontSize="19"
          fontWeight="700"
          textAnchor="middle"
          fill={GREEN_LIGHT}
        >E</text>
      </svg>

      <span className="font-bold text-[20px] text-white leading-none tracking-wide">
        E-code
      </span>
    </div>
  );
}

/* ─── POS login (qorang'u fon) uchun ikonka ─────────────────────────── */
export function ECodeIconLight({ size = 64, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          flexShrink: 0,
          filter: `drop-shadow(0 0 14px ${GREEN_GLOW}) drop-shadow(0 3px 8px ${GREEN_GLOW})`,
        }}
      >
        <circle cx="24" cy="24" r="21" stroke={GREEN_LIGHT} strokeWidth="2.8" />
        <circle cx="24" cy="5" r="2.8" fill={GREEN_LIGHT} />
        <text
          x="24" y="30"
          fontFamily="Arial, sans-serif"
          fontSize="19"
          fontWeight="700"
          textAnchor="middle"
          fill={GREEN_LIGHT}
        >E</text>
      </svg>
    </div>
  );
}
