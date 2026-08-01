import React from 'react';

/**
 * E-code Logo Component with continuous rhythmic wave animation on the 3 U-bars.
 */

const BLUE_LIGHT = '#60a5fa'; // blue-400 (for dark backgrounds)
const BLUE_DARK = '#2563eb';  // blue-600 (for light backgrounds)
const DARK_TEXT = '#1e293b';  // slate-800 (for light backgrounds)

const LogoWaveStyle = () => (
  <style>{`
    @keyframes logoWave {
      0%, 100% {
        transform: translateY(0px);
      }
      50% {
        transform: translateY(-4px);
      }
    }
    .animate-logo-bar1 {
      animation: logoWave 1.6s ease-in-out infinite;
      animation-delay: 0ms;
    }
    .animate-logo-bar2 {
      animation: logoWave 1.6s ease-in-out infinite;
      animation-delay: 250ms;
    }
    .animate-logo-bar3 {
      animation: logoWave 1.6s ease-in-out infinite;
      animation-delay: 500ms;
    }
  `}</style>
);

export default function ECodeLogo({
  size = 48,
  showText = true,
  className = '',
}) {
  if (showText) {
    return (
      <div className={`flex items-center gap-2 ${className}`} style={{ width: 'fit-content' }}>
        <LogoWaveStyle />
        <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
          {/* Shape 1: Dark U (Left) */}
          <path d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10" stroke={DARK_TEXT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar1" />
          {/* Shape 2: Blue U (Middle) */}
          <path d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar2" />
          {/* Shape 3: Blue U (Right) */}
          <path d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar3" />
        </svg>
        <span className="text-slate-800 font-bold text-2xl leading-none tracking-wide font-sans mt-1">E-code</span>
      </div>
    );
  }

  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <LogoWaveStyle />
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10" stroke={DARK_TEXT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar1" />
        <path d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar2" />
        <path d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar3" />
      </svg>
    </div>
  );
}

export function ECodeIcon({ size = 32, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <LogoWaveStyle />
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10" stroke={DARK_TEXT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar1" />
        <path d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar2" />
        <path d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10" stroke={BLUE_DARK} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar3" />
      </svg>
    </div>
  );
}

export function ECodeLogoPrimary({ size = 48, className = '' }) {
  return (
    <div className={`flex items-center gap-2 ${className}`} style={{ width: 'fit-content' }}>
      <LogoWaveStyle />
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
        <path d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10" stroke="white" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar1" />
        <path d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18" stroke={BLUE_LIGHT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar2" />
        <path d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10" stroke={BLUE_LIGHT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar3" />
      </svg>
      <span className="text-white font-bold text-2xl leading-none tracking-wide font-sans mt-1">E-code</span>
    </div>
  );
}

export function ECodeIconLight({ size = 48, className = '' }) {
  return (
    <div className={className} style={{ display: 'inline-flex' }}>
      <LogoWaveStyle />
      <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10" stroke="white" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar1" />
        <path d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18" stroke={BLUE_LIGHT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar2" />
        <path d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10" stroke={BLUE_LIGHT} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" className="animate-logo-bar3" />
      </svg>
    </div>
  );
}
