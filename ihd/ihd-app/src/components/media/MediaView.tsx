"use client";

import { useState } from "react";

function NetflixLogo({ size = 48 }: { size?: number }) {
  return (
    <svg viewBox="0 0 111 30" width={size * 3.7} height={size} fill="none">
      <path
        d="M105.062 14.28L111 30c-1.75-.25-3.499-.563-5.28-.845l-3.345-8.686-3.437 7.969c-1.687-.282-3.344-.626-5.031-.845l6.218-13.843L94.55 0h5.063l3.062 7.874L105.813 0h5.063l-5.814 14.28zM90.425 27.28c-1.063 0-2.063-.063-3.094-.094V0h5.25v27.563c-.719.03-1.437.03-2.156-.282zm-8.187-9.03c2.687 0 4.093-1.875 4.093-4.688 0-2.843-1.344-4.718-4.093-4.718h-2.813v9.406h2.813zM76.988 0h8.343c5.094 0 8.907 3.219 8.907 9.406 0 5.375-3.156 9.094-8.156 9.437V30h-5.094V18.843h-4V30h-5.094V0h5.094zm-11.25 0v5.063h-4.5V30h-5.25V5.063h-4.5V0h14.25zM48.113 30H37.8V0h10.313v5.063h-5.25v7.312h5.25v4.875h-5.25v7.688h5.25V30zM28.175 0l3.813 18.75L35.8 0h5.25l-6.375 30h-4.5L26.394 12 22.55 30h-4.5L11.55 0h5.531l3.813 18.75L24.675 0h3.5zM0 0h5.25v24.938h5.063V30H0V0z"
        fill="#e50914"
      />
    </svg>
  );
}

function NowTVLogo({ size = 48 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 40" width={size * 3} height={size} fill="none">
      <rect width="120" height="40" rx="6" fill="#1bb7e0" />
      <text
        x="60"
        y="28"
        textAnchor="middle"
        fontFamily="sans-serif"
        fontWeight="900"
        fontSize="24"
        fill="white"
      >
        NOW
      </text>
    </svg>
  );
}

function YouTubeLogo({ size = 48 }: { size?: number }) {
  return (
    <svg viewBox="0 0 159 110" width={size * 1.45} height={size} fill="none">
      <path
        d="M154 17.5c-1.82-6.73-7.07-12-13.8-13.8C128.05 0 79.5 0 79.5 0S30.95 0 18.8 3.7C12.07 5.5 6.82 10.77 5 17.5 1.3 29.65 1.3 55 1.3 55s0 25.35 3.7 37.5c1.82 6.73 7.07 12 13.8 13.8C30.95 110 79.5 110 79.5 110s48.55 0 60.7-3.7c6.73-1.82 12-7.07 13.8-13.8 3.7-12.15 3.7-37.5 3.7-37.5s0-25.35-3.7-37.5z"
        fill="#FF0000"
      />
      <path d="M64 79.5L105 55 64 30.5v49z" fill="white" />
    </svg>
  );
}

const STREAMING_APPS = [
  {
    id: "netflix",
    name: "Netflix",
    bg: "#000000",
    border: "#e50914",
    Logo: NetflixLogo,
  },
  {
    id: "youtube",
    name: "YouTube",
    bg: "#ffffff",
    border: "#ff0000",
    Logo: YouTubeLogo,
  },
  {
    id: "nowtv",
    name: "Now TV",
    bg: "#0f1923",
    border: "#1bb7e0",
    Logo: NowTVLogo,
  },
];

export default function MediaView() {
  const [launching, setLaunching] = useState<string | null>(null);

  const launchApp = async (appId: string) => {
    setLaunching(appId);
    try {
      await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "launch", app: appId }),
      });
    } catch {
      // ignore
    } finally {
      setTimeout(() => setLaunching(null), 2000);
    }
  };

  const closeMedia = async () => {
    try {
      await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "close" }),
      });
    } catch {
      // ignore
    }
  };

  return (
    <div
      className="h-full flex flex-col items-center justify-center gap-8"
      style={{ animation: "fadeIn .2s ease both" }}
    >
      {/* App launcher grid */}
      <div className="flex gap-6">
        {STREAMING_APPS.map((app) => {
          const isLaunching = launching === app.id;
          return (
            <button
              key={app.id}
              onClick={() => launchApp(app.id)}
              disabled={launching !== null}
              className="flex items-center justify-center rounded-3xl cursor-pointer border-2 hover:scale-105 active:scale-95 transition-all shadow-lg disabled:opacity-50 disabled:cursor-default"
              style={{
                width: 280,
                height: 160,
                background: app.bg,
                borderColor: isLaunching ? app.border : "transparent",
                boxShadow: isLaunching
                  ? `0 0 24px ${app.border}40`
                  : "0 4px 20px rgba(0,0,0,0.1)",
              }}
            >
              {isLaunching ? (
                <span
                  className="text-lg font-bold"
                  style={{ color: app.border }}
                >
                  Opening...
                </span>
              ) : (
                <app.Logo size={48} />
              )}
            </button>
          );
        })}
      </div>

      {/* Close button */}
      <button
        onClick={closeMedia}
        className="px-8 py-3 rounded-xl border border-border bg-surface text-text-mid font-semibold text-sm cursor-pointer hover:bg-surface-alt transition-colors"
      >
        Close streaming app
      </button>
    </div>
  );
}
