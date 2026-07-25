"use client";

import { useState, useEffect, useCallback, useRef, type CSSProperties } from "react";
import TripPopup from "./TripPopup";
import { Card } from "../ui/Card";

interface Venue {
  id: string;
  name: string;
  emoji: string;
  city: string;
  area: string;
  price: string;
  rating: string;
  verdict: string;
  tags: string;
  category: string;
  guide: string;
}

interface TripData {
  daysToGo: number;
  totalNights: number;
  departure: string;
  route: string;
  venues: Venue[];
  siteUrl: string;
}

const RATING_COLOURS: Record<string, { bg: string; text: string; label: string }> = {
  green: { bg: "#dcfce7", text: "#166534", label: "Must do" },
  amber: { bg: "#fef3c7", text: "#92400e", label: "Worth it" },
  skip: { bg: "#f3f4f6", text: "#6b7280", label: "Optional" },
};

function formatCategory(cat: string): string {
  return cat
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Edge-safety rule 6: auto-rotation pauses for 60s on any pointerdown inside the card
const ROTATE_MS = 30_000;
const PAUSE_MS = 60_000;

export default function TripWidget() {
  const [trip, setTrip] = useState<TripData | null>(null);
  const [featured, setFeatured] = useState<Venue | null>(null);
  const [showPopup, setShowPopup] = useState(false);
  const pauseUntilRef = useRef(0);

  const fetchTrip = useCallback(async () => {
    try {
      const res = await fetch("/api/trip");
      if (res.ok) {
        const data: TripData = await res.json();
        setTrip(data);
      }
    } catch {
      // keep last known data
    }
  }, []);

  useEffect(() => {
    fetchTrip();
    const t = setInterval(fetchTrip, 60 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchTrip]);

  // Rotate a random venue every 30 seconds — prefer green-rated
  useEffect(() => {
    if (!trip?.venues.length) return;

    const greens = trip.venues.filter((v) => v.rating === "green");
    const pool = greens.length > 10 ? greens : trip.venues;

    const pick = () => {
      if (Date.now() < pauseUntilRef.current) return; // paused by a recent tap
      const idx = Math.floor(Math.random() * pool.length);
      setFeatured(pool[idx]);
    };

    pick();
    const t = setInterval(pick, ROTATE_MS);
    return () => clearInterval(t);
  }, [trip?.venues]);

  const handlePointerDown = useCallback(() => {
    pauseUntilRef.current = Date.now() + PAUSE_MS;
  }, []);

  const fallbackDays = Math.ceil(
    (new Date("2026-04-03").getTime() - new Date().getTime()) / 864e5
  );
  const daysToGo = trip?.daysToGo ?? fallbackDays;
  const rating = featured ? RATING_COLOURS[featured.rating] || RATING_COLOURS.skip : null;

  return (
    <>
      <Card className="flex flex-col gap-2">
        <div
          className="flex flex-col gap-2 flex-1 min-h-0"
          onPointerDownCapture={handlePointerDown}
        >
          {/* Header: ink chip (not a standard section colour) */}
          <div className="flex items-center justify-between shrink-0">
            <span
              className="chip-v2"
              style={{ "--chip": "var(--ink)", "--chip-text": "#fff" } as CSSProperties}
            >
              🇯🇵 Japan Trip
            </span>
            <div className="flex items-baseline gap-1.5">
              <span
                className="text-4xl leading-none font-extrabold"
                style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink)" }}
              >
                {daysToGo}
              </span>
              <span className="text-sm font-semibold text-ink/60">days</span>
            </div>
          </div>

          {/* Featured venue — large, tappable */}
          {featured && (
            <button
              onClick={() => setShowPopup(true)}
              className="pressable flex-1 text-left rounded-xl p-3 cursor-pointer border-2"
              style={{ background: "var(--ink-08)", borderColor: "var(--ink-30)" }}
            >
              <div className="flex items-start gap-3">
                <span className="text-3xl mt-0.5">{featured.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-base font-semibold leading-tight">
                    {featured.name}
                  </div>
                  <div className="text-sm text-ink/60 mt-1">
                    {featured.area}
                  </div>
                  <div className="text-sm text-ink/60 mt-1.5 leading-snug line-clamp-2">
                    {featured.verdict}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    {rating && (
                      <span
                        className="inline-block px-1.5 py-0.5 rounded text-[13px] font-bold uppercase"
                        style={{ background: rating.bg, color: rating.text }}
                      >
                        {rating.label}
                      </span>
                    )}
                    <span className="text-[13px] text-ink/50">
                      {formatCategory(featured.category)}
                    </span>
                    {featured.price && (
                      <span className="text-[13px] text-ink/50">
                        {featured.price}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          )}
        </div>
      </Card>

      {showPopup && trip && (
        <TripPopup
          venue={featured}
          venues={trip.venues}
          daysToGo={daysToGo}
          siteUrl={trip.siteUrl}
          onClose={() => setShowPopup(false)}
        />
      )}
    </>
  );
}
