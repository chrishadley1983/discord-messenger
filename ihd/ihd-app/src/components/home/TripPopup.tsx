"use client";

import { useEffect, useRef, useState, useCallback } from "react";

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

const RATING_COLOURS: Record<string, { bg: string; text: string; label: string }> = {
  green: { bg: "#dcfce7", text: "#166534", label: "Must do" },
  amber: { bg: "#fef3c7", text: "#92400e", label: "Worth it" },
  skip: { bg: "#f3f4f6", text: "#6b7280", label: "Optional" },
};

const CITY_COLOURS: Record<string, string> = {
  Tokyo: "#e74c3c",
  Osaka: "#f39c12",
  Kyoto: "#27ae60",
};

function formatCategory(cat: string): string {
  return cat.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function VenueCard({
  venue,
  selected,
  onSelect,
}: {
  venue: Venue;
  selected: boolean;
  onSelect: () => void;
}) {
  const rating = RATING_COLOURS[venue.rating] || RATING_COLOURS.skip;
  const cityCol = CITY_COLOURS[venue.city] || "#888";

  return (
    <button
      onClick={onSelect}
      className={`w-full text-left border cursor-pointer p-4 rounded-xl transition-all ${
        selected
          ? "bg-accent-glow border-accent shadow-md"
          : "bg-surface border-border hover:bg-surface-alt"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl">{venue.emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="text-[15px] font-semibold leading-tight truncate">
            {venue.name}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: cityCol }}
            />
            <span className="text-sm text-text-mid">{venue.area}</span>
          </div>
          <div className="flex items-center gap-2 mt-1.5">
            <span
              className="inline-block px-1.5 py-0.5 rounded text-xs font-bold uppercase"
              style={{ background: rating.bg, color: rating.text }}
            >
              {rating.label}
            </span>
            {venue.price && (
              <span className="text-xs text-text-dim">{venue.price}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

export default function TripPopup({
  venue,
  venues,
  daysToGo,
  siteUrl,
  onClose,
}: {
  venue: Venue | null;
  venues: Venue[];
  daysToGo: number;
  siteUrl: string;
  onClose: () => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<Venue | null>(venue);
  const [filterCity, setFilterCity] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);

  // Venues with guides for swipe navigation
  const venuesWithGuides = venues.filter((v) => v.guide);

  const navigateVenue = useCallback(
    (direction: "prev" | "next") => {
      if (!selected || !venuesWithGuides.length) return;
      const idx = venuesWithGuides.findIndex((v) => v.id === selected.id);
      if (idx === -1) return;
      const newIdx =
        direction === "next"
          ? (idx + 1) % venuesWithGuides.length
          : (idx - 1 + venuesWithGuides.length) % venuesWithGuides.length;
      setSelected(venuesWithGuides[newIdx]);
    },
    [selected, venuesWithGuides]
  );



  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Get unique cities and categories
  const cities = [...new Set(venues.map((v) => v.city))].sort();
  const categories = [...new Set(venues.map((v) => v.category))].sort();

  // Filter venues
  const filtered = venues.filter((v) => {
    if (filterCity && v.city !== filterCity) return false;
    if (filterCategory && v.category !== filterCategory) return false;
    return true;
  });

  // Sort: green first, then amber, then skip
  const ratingOrder: Record<string, number> = { green: 0, amber: 1, skip: 2 };
  const sorted = [...filtered].sort(
    (a, b) => (ratingOrder[a.rating] ?? 3) - (ratingOrder[b.rating] ?? 3)
  );

  const rating = selected ? RATING_COLOURS[selected.rating] || RATING_COLOURS.skip : null;
  const guideUrl = selected?.guide ? `${siteUrl}/${selected.guide}` : null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      style={{ background: "rgba(26, 23, 16, 0.5)" }}
    >
      <div className="bg-bg m-3 rounded-2xl shadow-xl flex overflow-hidden w-full">
        {/* Left panel — venue list */}
        <div className="w-[380px] flex-shrink-0 bg-surface border-r border-border flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-semibold">Japan 2026</span>
                <span className="font-serif text-xl text-accent font-extralight">
                  {daysToGo}d
                </span>
              </div>
              <button
                onClick={onClose}
                className="text-text-dim hover:text-text text-xl cursor-pointer bg-transparent border-none p-1"
              >
                ✕
              </button>
            </div>

            {/* City filter */}
            <div className="flex gap-1.5 mb-2">
              <button
                onClick={() => setFilterCity(null)}
                className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase cursor-pointer border-none transition-colors ${
                  !filterCity ? "bg-accent text-white" : "bg-surface-alt text-text-mid hover:bg-border"
                }`}
              >
                All
              </button>
              {cities.map((c) => (
                <button
                  key={c}
                  onClick={() => setFilterCity(filterCity === c ? null : c)}
                  className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase cursor-pointer border-none transition-colors ${
                    filterCity === c ? "text-white" : "text-text-mid hover:bg-border"
                  }`}
                  style={{
                    background: filterCity === c ? CITY_COLOURS[c] || "#888" : undefined,
                  }}
                >
                  {c}
                </button>
              ))}
            </div>

            {/* Category filter */}
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => setFilterCategory(null)}
                className={`px-2 py-0.5 rounded text-xs font-bold uppercase cursor-pointer border-none transition-colors ${
                  !filterCategory ? "bg-accent/20 text-accent" : "bg-surface-alt text-text-dim hover:bg-border"
                }`}
              >
                All
              </button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setFilterCategory(filterCategory === cat ? null : cat)}
                  className={`px-2 py-0.5 rounded text-xs font-bold uppercase cursor-pointer border-none transition-colors ${
                    filterCategory === cat ? "bg-accent/20 text-accent" : "bg-surface-alt text-text-dim hover:bg-border"
                  }`}
                >
                  {formatCategory(cat)}
                </button>
              ))}
            </div>

            <div className="text-xs text-text-dim mt-2">
              {sorted.length} of {venues.length} venues
            </div>
          </div>

          {/* Scrollable venue list */}
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
            {sorted.map((v) => (
              <VenueCard
                key={v.id}
                venue={v}
                selected={selected?.id === v.id}
                onSelect={() => { setSelected(v); setShowGuide(false); }}
              />
            ))}
          </div>
        </div>

        {/* Right panel — venue detail or embedded guide */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selected && showGuide && guideUrl ? (
            /* Embedded guide iframe with swipe navigation */
            <div className="flex-1 flex flex-col relative">
              <div className="flex items-center gap-3 p-3 border-b border-border flex-shrink-0">
                <button
                  onClick={() => setShowGuide(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-surface-alt border border-border cursor-pointer hover:bg-border transition-colors"
                >
                  ‹ Back
                </button>
                <span className="text-sm text-text-mid truncate flex-1">
                  {selected.emoji} {selected.name} — Full Guide
                </span>
                {/* Nav arrows */}
                <div className="flex gap-1">
                  <button
                    onClick={() => navigateVenue("prev")}
                    className="w-8 h-8 rounded-lg bg-surface-alt border border-border flex items-center justify-center cursor-pointer hover:bg-border transition-colors text-text-mid"
                  >
                    ‹
                  </button>
                  <button
                    onClick={() => navigateVenue("next")}
                    className="w-8 h-8 rounded-lg bg-surface-alt border border-border flex items-center justify-center cursor-pointer hover:bg-border transition-colors text-text-mid"
                  >
                    ›
                  </button>
                </div>
              </div>
              <div className="flex-1 relative">
                <iframe
                  src={guideUrl}
                  className="w-full h-full border-none"
                  title={`${selected.name} guide`}
                />
              </div>
            </div>
          ) : selected ? (
            <div
              className="flex-1 overflow-y-auto p-8"
              key={selected.id}
              style={{ animation: "fadeIn .15s ease both" }}
            >
              {/* Big emoji + name */}
              <div className="flex items-start gap-5 mb-6">
                <span className="text-6xl">{selected.emoji}</span>
                <div>
                  <h1 className="text-3xl font-semibold leading-tight">
                    {selected.name}
                  </h1>
                  <div className="flex items-center gap-2 mt-2">
                    <span
                      className="inline-block w-3 h-3 rounded-full"
                      style={{
                        background: CITY_COLOURS[selected.city] || "#888",
                      }}
                    />
                    <span className="text-sm text-text-mid">
                      {selected.area}
                    </span>
                  </div>
                </div>
              </div>

              {/* Rating + meta badges */}
              <div className="flex items-center gap-3 mb-6">
                {rating && (
                  <span
                    className="inline-block px-3 py-1 rounded-full text-sm font-bold uppercase"
                    style={{ background: rating.bg, color: rating.text }}
                  >
                    {rating.label}
                  </span>
                )}
                <span className="text-sm text-text-mid">
                  {formatCategory(selected.category)}
                </span>
                {selected.price && (
                  <span className="text-sm text-text-mid">
                    {selected.price}
                  </span>
                )}
              </div>

              {/* Verdict */}
              <div className="bg-surface-alt rounded-2xl p-5 mb-5">
                <div className="text-xs font-bold uppercase tracking-widest text-text-dim mb-2">
                  Verdict
                </div>
                <div className="text-base leading-relaxed">
                  {selected.verdict}
                </div>
              </div>

              {/* Tags */}
              {selected.tags && (
                <div className="bg-surface-alt rounded-2xl p-5 mb-5">
                  <div className="text-xs font-bold uppercase tracking-widest text-text-dim mb-2">
                    Tags
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selected.tags.split(" · ").map((tag, i) => (
                      <span
                        key={i}
                        className="inline-block px-3 py-1 bg-surface rounded-full text-sm border border-border"
                      >
                        {tag.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* View full guide button */}
              {guideUrl && (
                <button
                  onClick={() => setShowGuide(true)}
                  className="w-full p-4 bg-accent/10 border border-accent/30 rounded-2xl text-accent font-semibold text-sm cursor-pointer hover:bg-accent/20 transition-colors"
                >
                  View Full Guide
                </button>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-text-dim text-sm">
                Select a venue to see details
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
