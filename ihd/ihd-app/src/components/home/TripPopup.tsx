"use client";

import { useEffect, useState, useCallback } from "react";
import Takeover from "../ui/Takeover";

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
      className={`pressable w-full text-left border-2 cursor-pointer p-3 rounded-xl transition-all ${
        selected ? "shadow-md" : "hover:bg-[var(--surface-alt)]"
      }`}
      style={{
        minHeight: 64,
        background: selected ? "var(--ink-08)" : "var(--surface)",
        borderColor: selected ? "var(--ink)" : "var(--ink-12)",
      }}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl">{venue.emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="text-base font-semibold leading-tight truncate">
            {venue.name}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ background: cityCol }}
            />
            <span className="text-sm text-ink/60">{venue.area}</span>
          </div>
          <div className="flex items-center gap-2 mt-1.5">
            <span
              className="inline-block px-1.5 py-0.5 rounded text-[13px] font-bold uppercase"
              style={{ background: rating.bg, color: rating.text }}
            >
              {rating.label}
            </span>
            {venue.price && (
              <span className="text-[13px] text-ink/50">{venue.price}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function FilterPill({
  active,
  onClick,
  children,
  color,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className="pressable px-3 rounded-full text-[13px] font-bold uppercase cursor-pointer border-2 transition-colors"
      style={{
        minHeight: 40,
        background: active ? (color || "var(--ink)") : "var(--surface)",
        color: active ? "#fff" : "var(--ink)",
        borderColor: active ? (color || "var(--ink)") : "var(--ink-12)",
      }}
    >
      {children}
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
    <Takeover
      onClose={onClose}
      accent="var(--ink)"
      accentText="#fff"
      title="Japan 2026"
      actions={
        <span className="text-sm font-bold text-white">{daysToGo} days to go</span>
      }
    >
      <div className="flex h-full overflow-hidden">
        {/* Left panel — filters + venue list */}
        <div className="w-[380px] flex-shrink-0 border-r-2 border-ink/10 flex flex-col" style={{ background: "var(--surface)" }}>
          {/* Filters */}
          <div className="p-3 border-b-2 border-ink/10">
            <div className="flex gap-1.5 mb-2 flex-wrap">
              <FilterPill active={!filterCity} onClick={() => setFilterCity(null)}>All</FilterPill>
              {cities.map((c) => (
                <FilterPill key={c} active={filterCity === c} onClick={() => setFilterCity(filterCity === c ? null : c)} color={CITY_COLOURS[c]}>
                  {c}
                </FilterPill>
              ))}
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <FilterPill active={!filterCategory} onClick={() => setFilterCategory(null)}>All</FilterPill>
              {categories.map((cat) => (
                <FilterPill key={cat} active={filterCategory === cat} onClick={() => setFilterCategory(filterCategory === cat ? null : cat)}>
                  {formatCategory(cat)}
                </FilterPill>
              ))}
            </div>
            <div className="text-[13px] text-ink/50 mt-2">
              {sorted.length} of {venues.length} venues
            </div>
          </div>

          {/* Scrollable venue list */}
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
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
              <div className="flex items-center gap-3 p-3 border-b-2 border-ink/10 flex-shrink-0">
                <button
                  onClick={() => setShowGuide(false)}
                  className="pressable flex items-center gap-1.5 px-3 rounded-lg text-sm font-semibold border-2 border-ink/15 cursor-pointer"
                  style={{ minHeight: 56, background: "var(--surface-alt)" }}
                >
                  ‹ Back
                </button>
                <span className="text-sm text-ink/60 truncate flex-1">
                  {selected.emoji} {selected.name} — Full Guide
                </span>
                {/* Nav arrows */}
                <div className="flex gap-1.5">
                  <button
                    onClick={() => navigateVenue("prev")}
                    className="pressable rounded-lg border-2 border-ink/15 flex items-center justify-center cursor-pointer text-ink/60"
                    style={{ width: 56, height: 56, background: "var(--surface-alt)" }}
                  >
                    ‹
                  </button>
                  <button
                    onClick={() => navigateVenue("next")}
                    className="pressable rounded-lg border-2 border-ink/15 flex items-center justify-center cursor-pointer text-ink/60"
                    style={{ width: 56, height: 56, background: "var(--surface-alt)" }}
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
                  <h1 className="text-3xl font-semibold leading-tight" style={{ fontFamily: "var(--font-display), sans-serif" }}>
                    {selected.name}
                  </h1>
                  <div className="flex items-center gap-2 mt-2">
                    <span
                      className="inline-block w-3 h-3 rounded-full"
                      style={{ background: CITY_COLOURS[selected.city] || "#888" }}
                    />
                    <span className="text-sm text-ink/60">
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
                <span className="text-sm text-ink/60">
                  {formatCategory(selected.category)}
                </span>
                {selected.price && (
                  <span className="text-sm text-ink/60">
                    {selected.price}
                  </span>
                )}
              </div>

              {/* Verdict */}
              <div className="rounded-2xl p-5 mb-5" style={{ background: "var(--surface-alt)" }}>
                <div className="text-[13px] font-bold uppercase tracking-widest text-ink/50 mb-2">
                  Verdict
                </div>
                <div className="text-base leading-relaxed">
                  {selected.verdict}
                </div>
              </div>

              {/* Tags */}
              {selected.tags && (
                <div className="rounded-2xl p-5 mb-5" style={{ background: "var(--surface-alt)" }}>
                  <div className="text-[13px] font-bold uppercase tracking-widest text-ink/50 mb-2">
                    Tags
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selected.tags.split(" · ").map((tag, i) => (
                      <span
                        key={i}
                        className="inline-block px-3 py-1 rounded-full text-sm border-2 border-ink/12"
                        style={{ background: "var(--surface)" }}
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
                  className="pressable w-full rounded-2xl font-semibold text-base cursor-pointer border-2"
                  style={{ minHeight: 56, background: "var(--ink-08)", borderColor: "var(--ink-30)", color: "var(--ink)" }}
                >
                  View Full Guide
                </button>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-ink/50 text-sm">
                Select a venue to see details
              </div>
            </div>
          )}
        </div>
      </div>
    </Takeover>
  );
}
