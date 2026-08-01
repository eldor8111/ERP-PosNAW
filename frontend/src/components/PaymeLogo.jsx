import React from 'react';

/**
 * Official Payme Brand Logo Component.
 * Vector SVG representation of the official Payme brand logo.
 */
export default function PaymeLogo({ width = 160, height = 48, className = "" }) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 160 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Background Rounded Badge */}
      <rect width="160" height="48" rx="12" fill="#00CCCC" />
      
      {/* Authentic "payme" Typography */}
      <g fill="#0B132B">
        {/* p */}
        <path d="M28 16h5v19h-5v-6.2a6.5 6.5 0 11.2-12.8H28V16zm5 10.5a3.8 3.8 0 100-7.6 3.8 3.8 0 000 7.6z" />
        {/* a */}
        <path d="M49 22.8c0-1.8 1.4-2.8 3.5-2.8h3v1.8h-2.8c-1.2 0-1.7.4-1.7 1.2 0 .7.5 1.1 1.6 1.1h1.5c2.4 0 3.9 1.2 3.9 3.4v7.5h-4.8v-1.6a4.8 4.8 0 01-4 1.8c-2.4 0-4-1.5-4-3.6 0-2.4 1.8-3.7 4.8-3.8h3.2v-.6c0-.9-.6-1.3-1.8-1.3h-2.4v-3.1zm6.5 6.2h-2.4c-1.2 0-1.8.4-1.8 1.1 0 .7.6 1.1 1.5 1.1 1.5 0 2.7-.9 2.7-2.2v-.0z" />
        {/* y */}
        <path d="M64 21h5.2l3.2 8.4L75.6 21H81l-6.2 14.5c-1.5 3.5-3.5 5.5-7.2 5.5h-2.8v-4.2h2c1.8 0 2.7-.8 3.4-2.4L64 21z" />
        {/* m */}
        <path d="M84 21h4.8v2.2a5.5 5.5 0 014.5-2.4c2.2 0 3.8 1 4.5 2.8a5.6 5.6 0 014.8-2.8c3.2 0 4.8 2.2 4.8 5.8V35h-4.8v-7.6c0-1.8-.7-2.6-2.1-2.6-1.5 0-2.5 1-2.5 2.8V35h-4.8v-7.6c0-1.8-.7-2.6-2.1-2.6-1.5 0-2.5 1-2.5 2.8V35H84V21z" />
        {/* e */}
        <path d="M110 28c.2-4.5 3.2-7.2 7.2-7.2 4.2 0 6.8 2.8 6.8 7.2v1.2h-9.5c.2 1.6 1.4 2.5 3 2.5 1.2 0 2.2-.4 2.8-1.2h4.5c-1 2.8-3.8 4.7-7.5 4.7-4.5 0-7.3-2.8-7.3-7.2zm9.5-1.8c-.2-1.4-1.2-2.3-2.5-2.3-1.4 0-2.4.9-2.6 2.3h5.1z" />
      </g>
    </svg>
  );
}

export function PaymeIcon({ size = 64, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="64" height="64" rx="16" fill="#00CCCC" />
      <text
        x="32"
        y="41"
        textAnchor="middle"
        fill="#0B132B"
        fontSize="22"
        fontWeight="900"
        fontFamily="system-ui, -apple-system, sans-serif"
        letterSpacing="-0.5px"
      >
        payme
      </text>
    </svg>
  );
}
