import React from 'react';
import paymeOfficialImg from '../assets/images/payme_official.png';

/**
 * Official Payme Brand Logo Component.
 */
export default function PaymeLogo({ className = "", height = 24, width, style = {} }) {
  return (
    <img
      src={paymeOfficialImg}
      alt="Payme"
      style={{ height: typeof height === 'number' ? `${height}px` : height, ...style }}
      className={`w-auto object-contain rounded-xs select-none shrink-0 ${className}`}
    />
  );
}

export function PaymeIcon({ size = 24, className = "", style = {} }) {
  return (
    <img
      src={paymeOfficialImg}
      alt="Payme"
      style={{ height: typeof size === 'number' ? `${size}px` : size, ...style }}
      className={`w-auto object-contain rounded-xs select-none shrink-0 ${className}`}
    />
  );
}
