"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import RecipePopup from "./RecipePopup";
import { Card } from "../ui/Card";
import Icon from "../ui/Icon";
import EmptyState from "../ui/EmptyState";

const SOURCE_BADGE: Record<string, { bg: string; label: string }> = {
  gousto: { bg: "var(--calendar-tint)", label: "Gousto" },
  familyfuel: { bg: "var(--kids-tint)", label: "Family Fuel" },
  family_fuel: { bg: "var(--kids-tint)", label: "Family Fuel" },
  homemade: { bg: "var(--control-tint)", label: "Homemade" },
  leftovers: { bg: "var(--home-tint)", label: "Leftovers" },
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

/** Mon–Sun dates for the current week — used as a fallback day-nav when no plan exists yet. */
function getCurrentWeekDates(): string[] {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const day = now.getDay(); // 0=Sun..6=Sat
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(now);
  monday.setDate(monday.getDate() + mondayOffset);
  const result: string[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    result.push(d.toISOString().slice(0, 10));
  }
  return result;
}

function SourceBadge({ tag }: { tag: string }) {
  const cfg = SOURCE_BADGE[tag] || {
    bg: "var(--surface-alt)",
    label: tag.replace(/_/g, " "),
  };
  return (
    <span
      className="inline-block whitespace-nowrap"
      style={{
        background: cfg.bg,
        color: "var(--ink)",
        border: "2px solid var(--ink)",
        borderRadius: 999,
        transform: "rotate(-1.5deg)",
        fontFamily: "var(--font-display), sans-serif",
        fontWeight: 700,
        fontSize: 13,
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        padding: "5px 12px",
      }}
    >
      {cfg.label}
    </span>
  );
}

function MealCard({
  item,
  onRecipeClick,
}: {
  item: MealItem;
  onRecipeClick: (name: string) => void;
}) {
  return (
    <Card
      section="meals"
      chip={SLOT_LABELS[item.meal_slot] || `Slot ${item.meal_slot}`}
      chipIcon={<Icon name="utensils" size={16} />}
      headerRight={<SourceBadge tag={item.source_tag} />}
      onClick={() => onRecipeClick(item.adults_meal)}
      className="w-full"
    >
      <div
        style={{
          fontFamily: "var(--font-display), sans-serif",
          fontWeight: 700,
          fontSize: 24,
          lineHeight: 1.2,
        }}
      >
        {item.adults_meal}
      </div>
      {item.kids_meal && item.kids_meal !== item.adults_meal && (
        <div className="text-base mt-1.5" style={{ color: "var(--ink-60)" }}>
          Kids: {item.kids_meal}
        </div>
      )}
      <div
        className="flex items-center gap-4 mt-2 text-base font-semibold"
        style={{ color: "var(--ink-60)" }}
      >
        {formatCookTime(item.cook_time_mins) && (
          <span>🕐 {formatCookTime(item.cook_time_mins)}</span>
        )}
        {item.servings && <span>👥 Serves {item.servings}</span>}
      </div>
      {item.notes && (
        <div
          className="text-base font-bold mt-2"
          style={{ color: "var(--meals)" }}
        >
          ⚡ {item.notes}
        </div>
      )}
    </Card>
  );
}

export default function MealsView() {
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [loaded, setLoaded] = useState(false);
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
    } finally {
      setLoaded(true);
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
  const hasPlan = dates.length > 0;
  // When there's no plan yet, still show a full week of day-nav pills
  // (all 7 days, today selected) rather than collapsing to one message.
  const weekDates = hasPlan ? dates : getCurrentWeekDates();

  // Auto-select today on first load
  useEffect(() => {
    if (weekDates.length === 0) return;
    const todayStr = new Date().toISOString().slice(0, 10);
    const todayIdx = weekDates.indexOf(todayStr);
    if (todayIdx >= 0) setCurrentIndex(todayIdx);
  }, [plan]); // eslint-disable-line react-hooks/exhaustive-deps

  const goLeft = useCallback(() => {
    setCurrentIndex((i) => Math.max(0, i - 1));
  }, []);

  const goRight = useCallback(() => {
    setCurrentIndex((i) => Math.min(weekDates.length - 1, i + 1));
  }, [weekDates.length]);

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

  if (!loaded) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="text-center"
          style={{
            fontFamily: "var(--font-display), sans-serif",
            fontWeight: 700,
            fontSize: 22,
            color: "var(--ink-60)",
          }}
        >
          Loading meal plan...
        </div>
      </div>
    );
  }

  const currentDate = weekDates[currentIndex] ?? weekDates[0];
  const currentItems = hasPlan
    ? (byDate[currentDate] || []).sort((a, b) => a.meal_slot - b.meal_slot)
    : [];
  const today = isToday(currentDate);

  return (
    <div
      ref={containerRef}
      className="h-full flex flex-col stagger-in"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Day navigation bar */}
      <div className="flex items-center gap-2 pb-3 shrink-0">
        <button
          onClick={goLeft}
          disabled={currentIndex === 0}
          aria-label="Previous day"
          className="pressable flex items-center justify-center shrink-0"
          style={{
            width: 56,
            height: 56,
            borderRadius: 16,
            border: "2px solid var(--ink)",
            background: "var(--surface)",
            fontSize: 22,
            fontWeight: 700,
            cursor: currentIndex === 0 ? "default" : "pointer",
            opacity: currentIndex === 0 ? 0.3 : 1,
          }}
        >
          ‹
        </button>

        {/* Day pills */}
        <div className="flex-1 flex items-center justify-center gap-2 overflow-x-auto">
          {weekDates.map((d, i) => {
            const isCurrent = i === currentIndex;
            const isT = isToday(d);
            const dt = new Date(d + "T00:00:00");
            return (
              <button
                key={d}
                onClick={() => setCurrentIndex(i)}
                className="pressable flex flex-col items-center justify-center shrink-0"
                style={{
                  minWidth: 56,
                  minHeight: 56,
                  borderRadius: 16,
                  padding: "6px 14px",
                  background: isCurrent ? "var(--meals)" : "var(--surface)",
                  color: isCurrent ? "#fff" : "var(--ink)",
                  border: "2px solid var(--ink)",
                  boxShadow: isCurrent ? "3px 3px 0 var(--ink)" : "none",
                  cursor: "pointer",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontSize: 13,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                    opacity: isCurrent ? 0.9 : 0.6,
                  }}
                >
                  {dt.toLocaleDateString("en-GB", { weekday: "short" })}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontSize: 18,
                    fontWeight: 800,
                    lineHeight: 1.2,
                  }}
                >
                  {dt.getDate()}
                  {!isCurrent && isT && (
                    <span style={{ color: "var(--meals)" }}>•</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>

        <button
          onClick={goRight}
          disabled={currentIndex === weekDates.length - 1}
          aria-label="Next day"
          className="pressable flex items-center justify-center shrink-0"
          style={{
            width: 56,
            height: 56,
            borderRadius: 16,
            border: "2px solid var(--ink)",
            background: "var(--surface)",
            fontSize: 22,
            fontWeight: 700,
            cursor: currentIndex === weekDates.length - 1 ? "default" : "pointer",
            opacity: currentIndex === weekDates.length - 1 ? 0.3 : 1,
          }}
        >
          ›
        </button>
      </div>

      {/* Current day content */}
      <div className="flex-1 min-h-0 overflow-y-auto pb-6">
        <div
          className="max-w-[720px] mx-auto flex flex-col gap-3 stagger-in"
          key={currentDate}
        >
          {/* Day header */}
          <div className="text-center mb-1">
            <div
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 800,
                fontSize: 28,
                color: today ? "var(--meals)" : "var(--ink)",
              }}
            >
              {formatDayLabel(currentDate)}
            </div>
            <div className="text-base font-semibold" style={{ color: "var(--ink-60)" }}>
              {formatDateFull(currentDate)}
            </div>
            <div className="text-[13px] font-bold uppercase tracking-wide mt-1" style={{ color: "var(--ink-30)" }}>
              {currentItems.length} meal{currentItems.length !== 1 ? "s" : ""}
            </div>
          </div>

          {currentItems.length === 0 ? (
            <Card section="meals" tinted className="items-center" style={{ padding: "32px 24px" }}>
              <EmptyState
                icon="utensils"
                headline={hasPlan ? "No meal plan today" : "No meal plan this week"}
                subtext={hasPlan ? undefined : "Plan one and it'll show up here."}
              />
            </Card>
          ) : (
            <>
              {/* Notes/prep for the day */}
              {currentItems
                .filter((item) => item.notes)
                .map((item) => (
                  <div
                    key={`note-${item.id}`}
                    className="card-v2 flex items-center gap-3"
                    style={{ padding: 16, background: "var(--meals-tint)" }}
                  >
                    <span className="text-2xl">⚡</span>
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--font-display), sans-serif",
                          fontWeight: 700,
                          fontSize: 13,
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                          color: "var(--meals)",
                        }}
                      >
                        Prep
                      </div>
                      <div className="text-base font-bold mt-0.5">
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
            </>
          )}
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
