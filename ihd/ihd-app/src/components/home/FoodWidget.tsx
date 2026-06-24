"use client";

import { useState, useEffect, useCallback } from "react";
import RecipePopup from "../meals/RecipePopup";

const SOURCE_COLOURS: Record<string, { bg: string; text: string }> = {
  gousto: { bg: "#dbeafe", text: "#1d4ed8" },
  familyfuel: { bg: "#fef3c7", text: "#92400e" },
  family_fuel: { bg: "#fef3c7", text: "#92400e" },
  homemade: { bg: "#dcfce7", text: "#166534" },
  leftovers: { bg: "#f3e8ff", text: "#7c3aed" },
  lunch: { bg: "#e0f2fe", text: "#0369a1" },
};

interface MealItem {
  date: string;
  meal_slot: number;
  adults_meal: string;
  kids_meal: string | null;
  source_tag: string;
  cook_time_mins: number | null;
  servings: number | null;
  notes: string | null;
}

function MealSubCard({
  label,
  emoji,
  meal,
  onClick,
}: {
  label: string;
  emoji: string;
  meal: MealItem;
  onClick: () => void;
}) {
  const source = SOURCE_COLOURS[meal.source_tag] || {
    bg: "#f3f4f6",
    text: "#374151",
  };
  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center gap-2.5 p-2.5 bg-surface-alt rounded-xl cursor-pointer border-none hover:brightness-95 transition-all"
    >
      <span className="text-xl">{emoji}</span>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-bold uppercase text-text-dim tracking-wide">
          {label}
        </div>
        <div className="text-sm font-semibold leading-tight truncate mt-0.5">
          {meal.adults_meal}
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <span
            className="inline-block px-1.5 py-0.5 rounded text-xs font-bold uppercase"
            style={{ background: source.bg, color: source.text }}
          >
            {meal.source_tag}
          </span>
          {meal.cook_time_mins && (
            <span className="text-xs text-text-dim">
              🕐 {meal.cook_time_mins >= 60
                ? `${Math.floor(meal.cook_time_mins / 60)}h${meal.cook_time_mins % 60 > 0 ? ` ${meal.cook_time_mins % 60}m` : ""}`
                : `${meal.cook_time_mins}m`}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

export default function FoodWidget() {
  const [dinner, setDinner] = useState<MealItem | null>(null);
  const [lunch, setLunch] = useState<MealItem | null>(null);
  const [prepNotes, setPrepNotes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecipe, setSelectedRecipe] = useState<string | null>(null);

  const fetchMeals = useCallback(async () => {
    try {
      const planRes = await fetch("/api/meals?action=current");
      if (planRes.ok) {
        const data = await planRes.json();
        if (data.plan?.items) {
          const today = new Date().toISOString().slice(0, 10);
          const todayItems = data.plan.items.filter(
            (item: MealItem) => item.date === today
          );
          setDinner(todayItems.find((i: MealItem) => i.meal_slot === 2) || null);
          setLunch(todayItems.find((i: MealItem) => i.meal_slot === 1) || null);
          // Extract prep notes directly from today's meal items
          const notes = todayItems
            .filter((i: MealItem) => i.notes)
            .map((i: MealItem) => i.notes as string);
          setPrepNotes(notes);
        }
      }
    } catch {
      // keep last known
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMeals();
    const t = setInterval(fetchMeals, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchMeals]);

  if (loading) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex flex-col gap-2">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Today&apos;s Meals
        </div>
        <div className="text-xs text-text-dim text-center py-4">Loading...</div>
      </div>
    );
  }

  if (!dinner && !lunch && prepNotes.length === 0) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex flex-col gap-2">
        <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
          Today&apos;s Meals
        </div>
        <div className="text-xs text-text-dim text-center py-4">
          No meal plan for today
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm flex flex-col gap-2">
      <div className="text-xs font-bold uppercase tracking-widest text-text-mid">
        Today&apos;s Meals
      </div>

      <div className="flex flex-col gap-2">
        {/* Prep notes from today's meals */}
        {prepNotes.map((note, i) => (
          <div
            key={i}
            className="flex items-center gap-2.5 p-2.5 rounded-xl"
            style={{ background: "var(--accent-glow, #c47f0a15)" }}
          >
            <span className="text-xl">⚡</span>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-bold uppercase text-accent tracking-wide">
                Prep
              </div>
              <div className="text-sm font-semibold leading-tight mt-0.5">
                {note}
              </div>
            </div>
          </div>
        ))}

        {/* Lunch */}
        {lunch && <MealSubCard label="Lunch" emoji="🥪" meal={lunch} onClick={() => setSelectedRecipe(lunch.adults_meal)} />}

        {/* Dinner */}
        {dinner && <MealSubCard label="Dinner" emoji="🍽" meal={dinner} onClick={() => setSelectedRecipe(dinner.adults_meal)} />}
      </div>

      {selectedRecipe && (
        <RecipePopup
          recipeName={selectedRecipe}
          onClose={() => setSelectedRecipe(null)}
        />
      )}
    </div>
  );
}
