"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import RecipePopup from "./RecipePopup";

const SOURCE_COLOURS: Record<string, { bg: string; text: string }> = {
  gousto: { bg: "#dbeafe", text: "#1d4ed8" },
  familyfuel: { bg: "#fef3c7", text: "#92400e" },
  family_fuel: { bg: "#fef3c7", text: "#92400e" },
  homemade: { bg: "#dcfce7", text: "#166534" },
  leftovers: { bg: "#f3e8ff", text: "#7c3aed" },
  lunch: { bg: "#e0f2fe", text: "#0369a1" },
};

const SLOT_LABELS: Record<number, string> = { 1: "Lunch", 2: "Dinner" };

interface MealItem {
  id: string;
  date: string;
  meal_slot: number;
  adults_meal: string;
  kids_meal: string | null;
  source_tag: string;
  cook_time_mins: number | null;
  servings: number | null;
  notes: string | null;
}

interface MealPlan {
  id: string;
  week_start: string;
  items: MealItem[];
}

function formatCookTime(mins: number | null): string | null {
  if (!mins) return null;
  if (mins >= 60) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  return `${mins} min`;
}

function formatDayLabel(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (d.getTime() === today.getTime()) return "Today";
  if (d.getTime() === tomorrow.getTime()) return "Tomorrow";
  return d.toLocaleDateString("en-GB", { weekday: "long" });
}

function formatDateFull(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function isToday(dateStr: string): boolean {
  return dateStr === new Date().toISOString().slice(0, 10);
}

function MealCard({
  item,
  onRecipeClick,
}: {
  item: MealItem;
  onRecipeClick: (name: string) => void;
}) {
  const source = SOURCE_COLOURS[item.source_tag] || {
    bg: "#f3f4f6",
    text: "#374151",
  };
  const isLeftover = item.adults_meal.toLowerCase().includes("leftover");

  return (
    <button
      onClick={() => onRecipeClick(item.adults_meal)}
      className="w-full text-left bg-surface border border-border cursor-pointer p-5 rounded-2xl hover:bg-surface-alt transition-colors shadow-sm"
    >
      <div className="flex items-start gap-4">
        <span className="text-3xl mt-1">
          {isLeftover ? "♻️" : item.meal_slot === 1 ? "🥪" : "🍽"}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-sm font-bold uppercase text-text-dim tracking-wide">
              {SLOT_LABELS[item.meal_slot] || `Slot ${item.meal_slot}`}
            </span>
            <span
              className="inline-block px-2 py-0.5 rounded text-xs font-bold uppercase"
              style={{ background: source.bg, color: source.text }}
            >
              {item.source_tag}
            </span>
          </div>
          <div className="text-xl font-semibold leading-tight">
            {item.adults_meal}
          </div>
          {item.kids_meal && item.kids_meal !== item.adults_meal && (
            <div className="text-sm text-text-mid mt-1.5">
              Kids: {item.kids_meal}
            </div>
          )}
          <div className="flex items-center gap-4 mt-2 text-sm text-text-dim">
            {formatCookTime(item.cook_time_mins) && (
              <span>🕐 {formatCookTime(item.cook_time_mins)}</span>
            )}
            {item.servings && <span>👥 Serves {item.servings}</span>}
          </div>
          {item.notes && (
            <div className="text-sm text-accent font-semibold mt-2">
              ⚡ {item.notes}
            </div>
          )}
        </div>
        <span className="text-text-dim text-lg mt-1">›</span>
      </div>
    </button>
  );
}

export default function MealsView() {
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedRecipe, setSelectedRecipe] = useState<string | null>(null);
  const touchStartX = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchPlan = useCallback(async () => {
    try {
      const res = await fetch("/api/meals?action=current");
      if (res.ok) {
        const data = await res.json();
        if (data.plan) setPlan(data.plan);
      }
    } catch {
      // keep last known
    }
  }, []);

  useEffect(() => {
    fetchPlan();
    const t = setInterval(fetchPlan, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchPlan]);

  // Group items by date and sort
  const byDate: Record<string, MealItem[]> = {};
  if (plan) {
    for (const item of plan.items) {
      if (!byDate[item.date]) byDate[item.date] = [];
      byDate[item.date].push(item);
    }
  }
  const dates = Object.keys(byDate).sort();

  // Auto-select today on first load
  useEffect(() => {
    if (dates.length === 0) return;
    const todayStr = new Date().toISOString().slice(0, 10);
    const todayIdx = dates.indexOf(todayStr);
    if (todayIdx >= 0) setCurrentIndex(todayIdx);
  }, [plan]); // eslint-disable-line react-hooks/exhaustive-deps

  const goLeft = useCallback(() => {
    setCurrentIndex((i) => Math.max(0, i - 1));
  }, []);

  const goRight = useCallback(() => {
    setCurrentIndex((i) => Math.min(dates.length - 1, i + 1));
  }, [dates.length]);

  // Touch swipe handling
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (touchStartX.current === null) return;
      const dx = e.changedTouches[0].clientX - touchStartX.current;
      if (Math.abs(dx) > 60) {
        if (dx < 0) goRight();
        else goLeft();
      }
      touchStartX.current = null;
    },
    [goLeft, goRight]
  );

  if (!plan) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text-mid text-sm">Loading meal plan...</div>
      </div>
    );
  }

  if (dates.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text-mid text-sm">No meal plan this week</div>
      </div>
    );
  }

  const currentDate = dates[currentIndex] || dates[0];
  const currentItems = (byDate[currentDate] || []).sort(
    (a, b) => a.meal_slot - b.meal_slot
  );
  const today = isToday(currentDate);

  return (
    <div
      ref={containerRef}
      className="h-full flex flex-col"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      style={{ animation: "fadeIn .2s ease both" }}
    >
      {/* Day navigation bar */}
      <div className="flex items-center justify-between px-2 pt-3 pb-2">
        <button
          onClick={goLeft}
          disabled={currentIndex === 0}
          className="w-10 h-10 rounded-full flex items-center justify-center text-xl bg-transparent border border-border cursor-pointer disabled:opacity-20 disabled:cursor-default hover:bg-surface-alt transition-colors"
        >
          ‹
        </button>

        {/* Day dots / labels */}
        <div className="flex items-center gap-1.5">
          {dates.map((d, i) => {
            const isCurrent = i === currentIndex;
            const isT = isToday(d);
            return (
              <button
                key={d}
                onClick={() => setCurrentIndex(i)}
                className="flex flex-col items-center gap-0.5 bg-transparent border-none cursor-pointer px-2 py-1 rounded-lg hover:bg-surface-alt transition-colors"
              >
                <div
                  className={`text-xs font-bold uppercase tracking-wide ${
                    isCurrent
                      ? isT
                        ? "text-accent"
                        : "text-text"
                      : "text-text-dim"
                  }`}
                >
                  {new Date(d + "T00:00:00").toLocaleDateString("en-GB", {
                    weekday: "short",
                  })}
                </div>
                <div
                  className={`w-2 h-2 rounded-full transition-all ${
                    isCurrent
                      ? isT
                        ? "bg-accent scale-125"
                        : "bg-text scale-125"
                      : "bg-border"
                  }`}
                />
              </button>
            );
          })}
        </div>

        <button
          onClick={goRight}
          disabled={currentIndex === dates.length - 1}
          className="w-10 h-10 rounded-full flex items-center justify-center text-xl bg-transparent border border-border cursor-pointer disabled:opacity-20 disabled:cursor-default hover:bg-surface-alt transition-colors"
        >
          ›
        </button>
      </div>

      {/* Current day content */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div
          className="max-w-[700px] mx-auto"
          key={currentDate}
          style={{ animation: "fadeIn .15s ease both" }}
        >
          {/* Day header */}
          <div className="text-center mb-4">
            <div
              className={`text-2xl font-semibold ${
                today ? "text-accent" : ""
              }`}
            >
              {formatDayLabel(currentDate)}
            </div>
            <div className="text-sm text-text-mid">
              {formatDateFull(currentDate)}
            </div>
            <div className="text-xs text-text-dim mt-1">
              {currentItems.length} meal{currentItems.length !== 1 ? "s" : ""}
            </div>
          </div>

          {/* Meal cards */}
          <div className="flex flex-col gap-3">
            {/* Notes/prep for the day */}
            {currentItems
              .filter((item) => item.notes)
              .map((item) => (
                <div
                  key={`note-${item.id}`}
                  className="flex items-center gap-3 p-4 rounded-2xl"
                  style={{ background: "var(--accent-glow, #c47f0a15)" }}
                >
                  <span className="text-2xl">⚡</span>
                  <div>
                    <div className="text-xs font-bold uppercase text-accent tracking-wide">
                      Prep
                    </div>
                    <div className="text-sm font-semibold mt-0.5">
                      {item.notes}
                    </div>
                  </div>
                </div>
              ))}

            {currentItems.map((item) => (
              <MealCard
                key={item.id}
                item={item}
                onRecipeClick={setSelectedRecipe}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Recipe popup */}
      {selectedRecipe && (
        <RecipePopup
          recipeName={selectedRecipe}
          onClose={() => setSelectedRecipe(null)}
        />
      )}
    </div>
  );
}
