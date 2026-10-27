import React from 'react';
import uzumOfficialImg from '../assets/images/uzum_official.png';

/**
 * Official Uzum Logo & Icon Components (Using official brand assets).
 * Brand color: #7000FF (Vibrant Violet / Grape)
 */
export default function UzumLogo({ className = "", height = 24, width, style = {} }) {
  return (
    <img
      src={uzumOfficialImg}
      alt="Uzum"
      style={{ height: typeof height === 'number' ? `${height}px` : height, ...style }}
      className={`w-auto object-contain select-none shrink-0 ${className}`}
    />
  );
}

export function UzumIcon({ size = 24, className = "", style = {} }) {
  return (
    <img
      src={uzumOfficialImg}
      alt="Uzum"
      style={{ height: typeof size === 'number' ? `${size}px` : size, ...style }}
      className={`w-auto object-contain select-none shrink-0 ${className}`}
    />
  );
}
