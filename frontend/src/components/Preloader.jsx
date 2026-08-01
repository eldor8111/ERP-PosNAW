import React, { useEffect, useState } from 'react';

/**
 * Clean & Minimal E-code Logo Wave Preloader.
 * - Only the E-code Logo Icon performing equalizing wave animation.
 * - No text, no progress scrollbar, no % counter.
 */
export default function Preloader({ onComplete }) {
  const [hasSeen] = useState(() => {
    try {
      return !!sessionStorage.getItem('hasSeenPreloader');
    } catch (e) {
      return false;
    }
  });

  const [fadeExit, setFadeExit] = useState(false);
  const [hidden, setHidden] = useState(hasSeen);

  useEffect(() => {
    if (hasSeen) return;

    // Fade exit at 2200ms (2.2s)
    const tExit = setTimeout(() => setFadeExit(true), 2200);

    // Unmount at 2700ms (2.7s)
    const tUnmount = setTimeout(() => {
      try {
        sessionStorage.setItem('hasSeenPreloader', 'true');
      } catch (e) {}
      setHidden(true);
      if (onComplete) onComplete();
    }, 2700);

    return () => {
      clearTimeout(tExit);
      clearTimeout(tUnmount);
    };
  }, [hasSeen, onComplete]);

  if (hidden || hasSeen) return null;

  return (
    <div
      className={`fixed inset-0 z-[999999] flex flex-col items-center justify-center bg-[#090E1A] text-white select-none transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${
        fadeExit ? 'opacity-0 scale-[1.04] pointer-events-none' : 'opacity-100 scale-100'
      }`}
    >
      {/* Wave Animation Keyframes */}
      <style>{`
        @keyframes uBarWave {
          0%, 100% {
            transform: translateY(0px);
          }
          50% {
            transform: translateY(-14px);
          }
        }
      `}</style>

      {/* Tech Grid Background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.035)_1px,transparent_1px)] bg-[size:36px_36px] pointer-events-none opacity-50" />

      {/* Main Logo Icon Container */}
      <div className="relative z-10 flex items-center justify-center">
        <svg
          width="120"
          height="120"
          viewBox="0 0 60 60"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="relative z-10"
        >
          {/* Shape 1: White Left U (Wave Animation Delay: 0ms) */}
          <path
            d="M 13 10 L 13 38 A 4 4 0 0 0 21 38 L 21 10"
            stroke="#FFFFFF"
            strokeWidth="5.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            style={{
              animation: 'uBarWave 1.4s ease-in-out infinite',
              animationDelay: '0ms',
            }}
          />
          {/* Shape 2: Bright Blue U (Middle) (Wave Animation Delay: 250ms) */}
          <path
            d="M 26 18 L 26 46 A 4 4 0 0 0 34 46 L 34 18"
            stroke="#3B82F6"
            strokeWidth="5.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            style={{
              animation: 'uBarWave 1.4s ease-in-out infinite',
              animationDelay: '250ms',
            }}
          />
          {/* Shape 3: Bright Blue U (Right) (Wave Animation Delay: 500ms) */}
          <path
            d="M 39 10 L 39 38 A 4 4 0 0 0 47 38 L 47 10"
            stroke="#3B82F6"
            strokeWidth="5.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            style={{
              animation: 'uBarWave 1.4s ease-in-out infinite',
              animationDelay: '500ms',
            }}
          />
        </svg>
      </div>
    </div>
  );
}
