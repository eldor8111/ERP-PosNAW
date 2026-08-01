import React from 'react';

export function FlagIcon({ code, className = "w-5 h-3.5" }) {
  const c = code?.toLowerCase();

  if (c === 'uz') {
    return (
      <svg viewBox="0 0 500 250" className={`${className} rounded-[2px] shadow-xs inline-block shrink-0 object-cover border border-black/10`}>
        <rect width="500" height="83.3" fill="#0099B5" />
        <rect y="83.3" width="500" height="83.3" fill="#FFFFFF" />
        <rect y="166.6" width="500" height="83.3" fill="#1EB53A" />
        <rect y="80" width="500" height="3.3" fill="#CE1126" />
        <rect y="163.3" width="500" height="3.3" fill="#CE1126" />
        <circle cx="70" cy="41.6" r="24" fill="#FFFFFF" />
        <circle cx="78" cy="41.6" r="20" fill="#0099B5" />
        <g fill="#FFFFFF">
          <circle cx="115" cy="41.6" r="3.5" /><circle cx="132" cy="41.6" r="3.5" /><circle cx="149" cy="41.6" r="3.5" />
          <circle cx="115" cy="27.6" r="3.5" /><circle cx="132" cy="27.6" r="3.5" /><circle cx="149" cy="27.6" r="3.5" /><circle cx="166" cy="27.6" r="3.5" />
          <circle cx="115" cy="55.6" r="3.5" /><circle cx="132" cy="55.6" r="3.5" /><circle cx="149" cy="55.6" r="3.5" /><circle cx="166" cy="55.6" r="3.5" /><circle cx="183" cy="55.6" r="3.5" />
        </g>
      </svg>
    );
  }

  if (c === 'ru') {
    return (
      <svg viewBox="0 0 900 600" className={`${className} rounded-[2px] shadow-xs inline-block shrink-0 object-cover border border-black/10`}>
        <rect width="900" height="200" fill="#FFFFFF" />
        <rect y="200" width="900" height="200" fill="#0039A6" />
        <rect y="400" width="900" height="200" fill="#D52B1E" />
      </svg>
    );
  }

  if (c === 'en' || c === 'gb') {
    return (
      <svg viewBox="0 0 600 300" className={`${className} rounded-[2px] shadow-xs inline-block shrink-0 object-cover border border-black/10`}>
        <clipPath id="flag_gb_clip"><path d="M0,0 v300 h600 v-300 z"/></clipPath>
        <clipPath id="flag_gb_diag"><path d="M300,150 h300 v150 z M300,150 h-300 v150 z M300,150 h300 v-150 z M300,150 h-300 v-150 z"/></clipPath>
        <g clipPath="url(#flag_gb_clip)">
          <path d="M0,0 L600,300 M600,0 L0,300" stroke="#00247D" strokeWidth="300"/>
          <path d="M0,0 L600,300 M600,0 L0,300" stroke="#fff" strokeWidth="60"/>
          <path d="M0,0 L600,300 M600,0 L0,300" stroke="#CF142B" strokeWidth="40" clipPath="url(#flag_gb_diag)"/>
          <path d="M300,0 v300 M0,150 h600" stroke="#fff" strokeWidth="100"/>
          <path d="M300,0 v300 M0,150 h600" stroke="#CF142B" strokeWidth="60"/>
        </g>
      </svg>
    );
  }

  return null;
}

export default FlagIcon;
