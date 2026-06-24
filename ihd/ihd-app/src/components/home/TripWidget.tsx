"use client";

import { useState, useEffect, useCallback } from "react";
import TripPopup from "./TripPopup";

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

export default function TripWidget() {
  const [trip, setTrip] = useState<TripData | null>(null);
  const [featured, setFeatured] = useState<Venue | null>(null);
  const [showPopup, setShowPopup] = useState(false);

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
      const idx = Math.floor(Math.random() * pool.length);
      setFeatured(pool[idx]);
    };

    pick();
    const t = setInterval(pick, 30_000);
    return () => clearInterval(t);
  }, [trip?.venues]);

  const fallbackDays = Math.ceil(
    (new Date("2026-04-03").getTime() - new Date().getTime()) / 864e5
  );
  const daysToGo = trip?.daysToGo ?? fallbackDays;
  const rating = featured ? RATING_COLOURS[featured.rating] || RATING_COLOURS.skip : null;

  return (
    <>
      <div className="bg-surface border border-accent rounded-2xl p-4 shadow-sm flex flex-col gap-2">
        {/* Countdown at top */}
        <div className="flex items-center justify-between">
          <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
            Japan Trip
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-serif text-[28px] text-accent leading-none font-extralight">
              {daysToGo}
            </span>
            <span className="text-sm text-text-mid">days</span>
          </div>
        </div>

        {/* Featured venue — large, tappable */}
        {featured && (
          <button
            onClick={() => setShowPopup(true)}
            className="flex-1 text-left bg-accent-glow border border-accent/20 rounded-xl p-3 cursor-pointer hover:border-accent/40 transition-colors"
          >
            <div className="flex items-start gap-3">
              <span className="text-3xl mt-0.5">{featured.emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="text-[15px] font-semibold leading-tight">
                  {featured.name}
                </div>
                <div className="text-sm text-text-mid mt-1">
                  {featured.area}
                </div>
                <div className="text-xs text-text-mid mt-1.5 leading-snug line-clamp-2">
                  {featured.verdict}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  {rating && (
                    <span
                      className="inline-block px-1.5 py-0.5 rounded text-xs font-bold uppercase"
                      style={{ background: rating.bg, color: rating.text }}
                    >
                      {rating.label}
                    </span>
                  )}
                  <span className="text-xs text-text-dim">
                    {formatCategory(featured.category)}
                  </span>
                  {featured.price && (
                    <span className="text-xs text-text-dim">
                      {featured.price}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </button>
        )}
      </div>

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
