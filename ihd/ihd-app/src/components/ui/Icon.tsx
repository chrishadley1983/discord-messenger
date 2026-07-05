"use client";

/**
 * Monoline icon set (challenge fix: emoji-as-iconography was the #1 AI tell).
 * 24x24 stroke icons, stroke=currentColor — inherits text colour, flat and
 * consistent across dev machine and the Pi's Chromium (no emoji font drift).
 *
 * <Icon name="calendar" size={18} />
 */

import type { CSSProperties } from "react";

const PATHS: Record<string, React.ReactNode> = {
  home: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M9.5 21v-6h5v6" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </>
  ),
  utensils: (
    <>
      <path d="M7 3v7a2 2 0 0 0 4 0V3" />
      <path d="M9 12v9" />
      <path d="M17 3c-1.5 1.5-2 4-2 6v3h3v9" />
    </>
  ),
  backpack: (
    <>
      <path d="M6 8a6 6 0 0 1 12 0v13H6V8Z" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
      <path d="M6 13h12" />
      <path d="M9 17h6" />
    </>
  ),
  film: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" />
    </>
  ),
  bulb: (
    <>
      <path d="M9 18h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 1 4 10.5c-.8.7-1 1.6-1 2.5H9c0-.9-.2-1.8-1-2.5A6 6 0 0 1 12 3Z" />
    </>
  ),
  brick: (
    <>
      <rect x="3" y="9" width="18" height="11" rx="1.5" />
      <path d="M7 9V6.5A1.5 1.5 0 0 1 8.5 5h1A1.5 1.5 0 0 1 11 6.5V9M13 9V6.5A1.5 1.5 0 0 1 14.5 5h1A1.5 1.5 0 0 1 17 6.5V9" />
    </>
  ),
  zap: <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />,
  thermometer: (
    <>
      <path d="M12 4a2 2 0 0 1 4 0v9.5a4.5 4.5 0 1 1-4 0V4Z" transform="translate(-2 0)" />
      <circle cx="12" cy="17.5" r="1.5" transform="translate(-2 0)" />
    </>
  ),
  paw: (
    <>
      <circle cx="7" cy="9" r="1.8" />
      <circle cx="12" cy="7" r="1.8" />
      <circle cx="17" cy="9" r="1.8" />
      <path d="M12 12c-3 0-5.5 2.4-5.5 4.7 0 1.5 1.2 2.3 2.5 2.3 1.1 0 2-.5 3-.5s1.9.5 3 .5c1.3 0 2.5-.8 2.5-2.3C17.5 14.4 15 12 12 12Z" />
    </>
  ),
  plug: (
    <>
      <path d="M9 3v5M15 3v5" />
      <path d="M6 8h12v3a6 6 0 0 1-6 6 6 6 0 0 1-6-6V8Z" />
      <path d="M12 17v4" />
    </>
  ),
  monitor: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M9 21h6M12 17v4" />
    </>
  ),
  tv: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="m8 3 4 4 4-4" />
    </>
  ),
  sparkle: (
    <>
      <path d="M12 4c.6 3.5 2.5 5.4 6 6-3.5.6-5.4 2.5-6 6-.6-3.5-2.5-5.4-6-6 3.5-.6 5.4-2.5 6-6Z" />
      <path d="M19 15c.3 1.6 1.1 2.4 2.7 2.7-1.6.3-2.4 1.1-2.7 2.7-.3-1.6-1.1-2.4-2.7-2.7 1.6-.3 2.4-1.1 2.7-2.7Z" />
    </>
  ),
  speech: <path d="M21 12a8 8 0 0 1-8 8H4l2.3-2.9A8 8 0 1 1 21 12Z" />,
  coins: (
    <>
      <circle cx="9" cy="9" r="6" />
      <path d="M15.7 5.1a6 6 0 1 1-8.6 8.6" />
      <path d="M9 6.5v5M7 8h4" />
    </>
  ),
  package: (
    <>
      <path d="M3 8 12 3l9 5v8l-9 5-9-5V8Z" />
      <path d="M3 8l9 5 9-5M12 13v8" />
    </>
  ),
  rocket: (
    <>
      <path d="M12 15c-1-3 0-7.5 3.5-11 2 .5 4 2.5 4.5 4.5C16.5 12 12 13 12 15Z" transform="translate(-1.5 1.5)" />
      <path d="M9 12c-2 .3-3.5 1.6-4.5 4.5C7.4 15.5 8.7 15 10 15M9 18c-.3 2-1.6 3.5-4.5 4.5.9-2.9 2.4-4.2 4.5-4.5Z" transform="translate(-1.5 1.5) scale(0.9)" />
      <circle cx="14.5" cy="8.5" r="1.3" transform="translate(-1.5 1.5)" />
    </>
  ),
  chart: (
    <>
      <path d="M4 4v16h16" />
      <path d="M8 16v-5M12 16V8M16 16v-8" />
    </>
  ),
  gear: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  cart: (
    <>
      <circle cx="9" cy="20" r="1.5" />
      <circle cx="17" cy="20" r="1.5" />
      <path d="M3 4h2l2.5 11h10L20 7H6" />
    </>
  ),
  clipboard: (
    <>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4a3 3 0 0 1 6 0" />
      <path d="M9 10h6M9 14h6M9 18h4" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 8a8 8 0 1 0 .7 6" />
      <path d="M20 3v5h-5" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="0.5" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  flag: (
    <>
      <path d="M5 21V4" />
      <path d="M5 4h13l-2.5 4L18 12H5" />
    </>
  ),
  history: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  bell: (
    <>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </>
  ),
};

export type IconName = keyof typeof PATHS;

export default function Icon({
  name,
  size = 18,
  strokeWidth = 2,
  className = "",
  style,
}: {
  name: string;
  size?: number;
  strokeWidth?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const paths = PATHS[name];
  if (!paths) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ flexShrink: 0, ...style }}
      aria-hidden
    >
      {paths}
    </svg>
  );
}
