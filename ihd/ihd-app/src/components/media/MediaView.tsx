"use client";

/**
 * Media screen (DESIGN_SPEC_V2 §8, "Media `/media` (magenta)").
 * Three giant sticker brand-tiles + a distinct ink-outline close pill.
 * Functionality unchanged: POST /api/media {action:'launch'|'close', app}.
 */

import { useState } from "react";
import { SectionChip } from "@/components/ui/Card";
import Icon from "@/components/ui/Icon";

function NetflixLogo({ size = 48 }: { size?: number }) {
  return (
    <span
      style={{
        fontFamily: "var(--font-display), sans-serif",
        fontWeight: 800,
        fontSize: size * 0.58,
        letterSpacing: "0.06em",
        color: "#E50914",
        transform: "scaleY(1.25)",
        display: "inline-block",
      }}
    >
      NETFLIX
    </span>
  );
}

function NowTVLogo({ size = 48 }: { size?: number }) {
  return (
    <span
      style={{
        fontFamily: "var(--font-display), sans-serif",
        fontWeight: 800,
        fontSize: size * 0.62,
        letterSpacing: "-0.02em",
        color: "#fff",
      }}
    >
      NOW
    </span>
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

interface StreamingApp {
  id: string;
  name: string;
  bg: string;
  Logo: (props: { size?: number }) => React.ReactElement;
}

const STREAMING_APPS: StreamingApp[] = [
  { id: "netflix", name: "Netflix", bg: "#000000", Logo: NetflixLogo },
  { id: "youtube", name: "YouTube", bg: "#ffffff", Logo: YouTubeLogo },
  { id: "nowtv", name: "Now TV", bg: "#046A63", Logo: NowTVLogo },
];

export default function MediaView() {
  const [launching, setLaunching] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [closed, setClosed] = useState(false);

  const launchApp = async (appId: string) => {
    setLaunching(appId);
    try {
      await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "launch", app: appId }),
      });
    } catch {
      // ignore — kiosk network blips shouldn't crash the tile
    } finally {
      setTimeout(() => setLaunching(null), 2200);
    }
  };

  const closeMedia = async () => {
    setClosing(true);
    try {
      await fetch("/api/media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "close" }),
      });
      setClosed(true);
      setTimeout(() => setClosed(false), 1800);
    } catch {
      // ignore
    } finally {
      setClosing(false);
    }
  };

  return (
    <div className="h-full flex flex-col items-center justify-center gap-10 stagger-in">
      <div className="flex flex-col items-center gap-2">
        <SectionChip section="media" icon={<Icon name="tv" size={16} />}>
          Media
        </SectionChip>
        <span className="text-sm" style={{ color: "var(--ink-60)" }}>
          Tap a tile to launch on the lounge TV
        </span>
      </div>

      <div className="flex gap-7">
        {STREAMING_APPS.map((app) => {
          const isLaunching = launching === app.id;
          const isDimmed = launching !== null && !isLaunching;
          return (
            <button
              key={app.id}
              onClick={() => launchApp(app.id)}
              disabled={launching !== null}
              className={`card-v2 pressable relative flex items-center justify-center overflow-hidden cursor-pointer disabled:cursor-default transition-opacity ${isDimmed ? "opacity-40" : ""}`}
              style={{
                width: 280,
                height: 200,
                background: app.bg,
              }}
              aria-label={`Launch ${app.name}`}
            >
              <app.Logo size={56} />

              {isLaunching && (
                <div
                  className="absolute inset-0 flex flex-col items-center justify-center gap-3"
                  style={{
                    background: "rgba(20,16,42,0.7)",
                    borderRadius: 18,
                    animation: "sparkle 1.1s ease-in-out infinite",
                  }}
                >
                  <span
                    className="rounded-full"
                    style={{
                      width: 14,
                      height: 14,
                      background: "var(--media)",
                      border: "2px solid #fff",
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-display), sans-serif",
                      fontWeight: 700,
                      fontSize: 18,
                      color: "#fff",
                      letterSpacing: "0.01em",
                    }}
                  >
                    Launching…
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Close button — distinct ink-outline pill, clearly separated */}
      <button
        onClick={closeMedia}
        disabled={closing}
        className="pressable cursor-pointer"
        style={{
          minHeight: 64,
          padding: "0 36px",
          borderRadius: 999,
          border: "2px solid var(--ink)",
          background: closed ? "var(--good)" : "var(--surface)",
          color: closed ? "#fff" : "var(--ink)",
          fontFamily: "var(--font-display), sans-serif",
          fontWeight: 700,
          fontSize: 15,
          letterSpacing: "0.03em",
          boxShadow: "3px 3px 0 var(--ink-08)",
        }}
      >
        {closed ? "Closed ✓" : closing ? "Closing…" : "⏹  Close streaming app"}
      </button>
    </div>
  );
}
