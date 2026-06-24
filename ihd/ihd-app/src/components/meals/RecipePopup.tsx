"use client";

import { useEffect, useRef, useState } from "react";

interface Ingredient {
  ingredientName: string;
  quantity: number;
  unit: string;
  notes: string | null;
  sortOrder: number;
}

interface Instruction {
  stepNumber: number;
  instruction: string;
  timerMinutes: number | null;
  sortOrder: number;
}

interface Recipe {
  id: string;
  recipeName: string;
  cuisineType: string | null;
  cookTimeMinutes: number | null;
  prepTimeMinutes: number | null;
  totalTimeMinutes: number | null;
  servings: number | null;
  caloriesPerServing: number | null;
  proteinPerServing: number | null;
  carbsPerServing: number | null;
  fatPerServing: number | null;
  recipeSource: string | null;
  sourceUrl: string | null;
  tags: string[] | null;
  isVegetarian: boolean;
  isVegan: boolean;
  isDairyFree: boolean;
  isGlutenFree: boolean;
  freezable: boolean;
  ingredients: Ingredient[];
  instructions: Instruction[];
}

function formatTime(mins: number | null): string | null {
  if (!mins) return null;
  if (mins >= 60) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  return `${mins} min`;
}

function cleanStepText(text: string): string {
  // Remove leading "1. " or "Step 1:" prefixes since we render step numbers ourselves
  return text.replace(/^\d+\.\s*/, "").replace(/^Step\s*\d+[.:]\s*/i, "");
}

export default function RecipePopup({
  recipeName,
  onClose,
}: {
  recipeName: string;
  onClose: () => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const cleanName = recipeName.replace(/\s*\(.*?\)\s*$/, "").trim();
        const searchRes = await fetch(
          `/api/meals?action=search&q=${encodeURIComponent(cleanName)}`
        );
        if (!searchRes.ok) throw new Error("Search failed");
        const searchData = await searchRes.json();

        // Check if the API proxy returned an error (Hadley API unreachable)
        if (searchData.error) {
          setError("Recipe service unavailable");
          return;
        }

        const recipes = searchData.recipes || [];
        if (recipes.length === 0) {
          setError("Recipe not found");
          return;
        }
        const match =
          recipes.find(
            (r: { recipeName: string }) =>
              r.recipeName.toLowerCase() === cleanName.toLowerCase()
          ) || recipes[0];

        const detailRes = await fetch(`/api/meals?recipe=${match.id}`);
        if (!detailRes.ok) throw new Error("Detail fetch failed");
        const detailData = await detailRes.json();

        if (detailData.error) {
          setError("Recipe service unavailable");
          return;
        }

        if (detailData.recipe) {
          setRecipe(detailData.recipe);
        } else {
          setError("Recipe detail unavailable");
        }
      } catch {
        setError("Could not load recipe");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [recipeName]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const sortedIngredients = recipe?.ingredients
    ? [...recipe.ingredients].sort((a, b) => a.sortOrder - b.sortOrder)
    : [];
  const sortedInstructions = recipe?.instructions
    ? [...recipe.instructions].sort((a, b) => a.sortOrder - b.sortOrder)
    : [];

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      style={{ background: "rgba(26, 23, 16, 0.5)" }}
    >
      <div className="bg-surface rounded-2xl shadow-xl w-[90vw] max-w-[1100px] h-[85vh] overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-text-mid text-sm">Loading recipe...</div>
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="text-text-mid text-sm">{error}</div>
            <button
              onClick={onClose}
              className="text-sm text-accent bg-transparent border border-accent rounded-lg px-4 py-2 cursor-pointer hover:bg-accent/10"
            >
              Close
            </button>
          </div>
        ) : recipe ? (
          <>
            {/* Header */}
            <div className="p-6 pb-4 border-b border-border flex-shrink-0">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="text-2xl font-semibold leading-tight">
                    {recipe.recipeName}
                  </div>
                  <div className="flex items-center gap-3 mt-2 flex-wrap">
                    {formatTime(recipe.cookTimeMinutes) && (
                      <span className="text-sm text-text-mid">
                        🕐 {formatTime(recipe.cookTimeMinutes)}
                      </span>
                    )}
                    {recipe.servings && (
                      <span className="text-sm text-text-mid">
                        👥 Serves {recipe.servings}
                      </span>
                    )}
                    {recipe.recipeSource && (
                      <span className="inline-block px-2 py-0.5 rounded text-xs font-bold uppercase bg-blue-50 text-blue-700 border border-blue-200">
                        {recipe.recipeSource}
                      </span>
                    )}
                    {recipe.isVegetarian && (
                      <span className="text-sm">🌿 Vegetarian</span>
                    )}
                    {recipe.freezable && (
                      <span className="text-sm">❄️ Freezable</span>
                    )}
                  </div>
                  {recipe.caloriesPerServing && (
                    <div className="flex gap-4 mt-2 text-xs text-text-mid">
                      <span>{Math.round(recipe.caloriesPerServing)} kcal</span>
                      {recipe.proteinPerServing && (
                        <span>P: {Math.round(recipe.proteinPerServing)}g</span>
                      )}
                      {recipe.carbsPerServing && (
                        <span>C: {Math.round(recipe.carbsPerServing)}g</span>
                      )}
                      {recipe.fatPerServing && (
                        <span>F: {Math.round(recipe.fatPerServing)}g</span>
                      )}
                    </div>
                  )}
                </div>
                <button
                  onClick={onClose}
                  className="text-text-dim hover:text-text text-2xl cursor-pointer bg-transparent border-none p-1 flex-shrink-0"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Two-column layout: Ingredients | Instructions */}
            <div className="flex-1 overflow-hidden flex">
              {/* Ingredients */}
              <div className="w-[320px] flex-shrink-0 border-r border-border overflow-y-auto p-5">
                <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-3">
                  Ingredients
                </div>
                <div className="flex flex-col gap-2">
                  {sortedIngredients.map((ing, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 text-sm"
                    >
                      <span className="text-accent mt-0.5 text-xs">●</span>
                      <span>{ing.ingredientName}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Instructions */}
              <div className="flex-1 overflow-y-auto p-5">
                <div className="text-xs font-bold uppercase tracking-widest text-text-mid mb-3">
                  Method
                </div>
                <div className="flex flex-col gap-4">
                  {sortedInstructions.map((step, i) => (
                    <div key={i} className="flex gap-3">
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                        style={{
                          background: "var(--accent-glow, #c47f0a22)",
                          color: "var(--accent, #c47f0a)",
                        }}
                      >
                        {step.stepNumber || i + 1}
                      </div>
                      <div className="text-sm leading-relaxed pt-0.5">
                        {cleanStepText(step.instruction)}
                        {step.timerMinutes && (
                          <span className="inline-block ml-2 px-2 py-0.5 rounded text-xs font-bold bg-amber-50 text-amber-700">
                            ⏱ {step.timerMinutes} min
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
