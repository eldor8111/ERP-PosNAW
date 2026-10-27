import React from 'react';

/**
 * Official Uzum Bank Logo & Icon Components.
 * Brand color: #7000FF (Vibrant Violet / Grape)
 */
export default function UzumLogo({ width = 140, height = 40, className = "" }) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 160 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="160" height="48" rx="12" fill="#7000FF" />
      {/* Uzum 7-dots grape cluster */}
      <g transform="translate(14, 10) scale(0.65)">
        <circle cx="12" cy="7" r="5" fill="#FFFFFF" />
        <circle cx="28" cy="7" r="5" fill="#FFFFFF" />
        <circle cx="4" cy="23" r="5" fill="#FFFFFF" />
        <circle cx="20" cy="23" r="5" fill="#FFFFFF" />
        <circle cx="36" cy="23" r="5" fill="#FFFFFF" />
        <circle cx="12" cy="39" r="5" fill="#FFFFFF" />
        <circle cx="28" cy="39" r="5" fill="#FFFFFF" />
      </g>
      <text
        x="50"
        y="33"
        fill="#FFFFFF"
        fontSize="24"
        fontWeight="900"
        fontFamily="system-ui, -apple-system, sans-serif"
        letterSpacing="-0.5px"
      >
        uzum
      </text>
      <text
        x="112"
        y="33"
        fill="#FFFFFF"
        fontSize="17"
        fontWeight="600"
        fontFamily="system-ui, -apple-system, sans-serif"
        opacity="0.9"
      >
        bank
      </text>
    </svg>
  );
}

export function UzumIcon({ size = 24, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="48" height="48" rx="12" fill="#7000FF" />
      <g transform="translate(4, 4) scale(0.95)">
        <circle cx="14" cy="10" r="4.5" fill="#FFFFFF" />
        <circle cx="28" cy="10" r="4.5" fill="#FFFFFF" />
        <circle cx="7" cy="22" r="4.5" fill="#FFFFFF" />
        <circle cx="21" cy="22" r="4.5" fill="#FFFFFF" />
        <circle cx="35" cy="22" r="4.5" fill="#FFFFFF" />
        <circle cx="14" cy="34" r="4.5" fill="#FFFFFF" />
        <circle cx="28" cy="34" r="4.5" fill="#FFFFFF" />
      </g>
    </svg>
  );
}
