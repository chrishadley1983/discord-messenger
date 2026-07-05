"use client";

import { useEffect, useState, type ReactNode } from "react";
import Takeover from "../ui/Takeover";

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

const DIET_TAGS: { key: "isVegetarian" | "isVegan" | "isDairyFree" | "isGlutenFree"; icon: string; label: string }[] = [
  { key: "isVegetarian", icon: "🌿", label: "Vegetarian" },
  { key: "isVegan", icon: "🌱", label: "Vegan" },
  { key: "isDairyFree", icon: "🥛", label: "Dairy-free" },
  { key: "isGlutenFree", icon: "🌾", label: "Gluten-free" },
];

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

function MetaPill({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 font-bold"
      style={{
        fontSize: 13,
        borderRadius: 999,
        background: "var(--surface)",
        border: "2px solid var(--ink)",
        padding: "5px 12px",
      }}
    >
      {children}
    </span>
  );
}

function SourceSticker({ label }: { label: string }) {
  return (
    <span
      className="inline-block whitespace-nowrap"
      style={{
        background: "var(--surface)",
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
      {label}
    </span>
  );
}

export default function RecipePopup({
  recipeName,
  onClose,
}: {
  recipeName: string;
  onClose: () => void;
}) {
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

  const sortedIngredients = recipe?.ingredients
    ? [...recipe.ingredients].sort((a, b) => a.sortOrder - b.sortOrder)
    : [];
  const sortedInstructions = recipe?.instructions
    ? [...recipe.instructions].sort((a, b) => a.sortOrder - b.sortOrder)
    : [];
  const activeDietTags = recipe ? DIET_TAGS.filter((t) => recipe[t.key]) : [];

  const title = loading ? "Loading…" : error ? "Recipe" : recipe?.recipeName || "Recipe";

  return (
    <Takeover onClose={onClose} accent="var(--meals)" accentText="#fff" title={title}>
      {loading ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-base font-semibold" style={{ color: "var(--ink-60)" }}>
            Loading recipe...
          </div>
        </div>
      ) : error ? (
        <div className="h-full flex flex-col items-center justify-center gap-4">
          <div className="text-base font-semibold" style={{ color: "var(--ink-60)" }}>
            {error}
          </div>
          <button
            onClick={onClose}
            className="pressable"
            style={{
              minHeight: 56,
              padding: "0 28px",
              borderRadius: 16,
              border: "2px solid var(--ink)",
              background: "var(--meals)",
              color: "#fff",
              fontFamily: "var(--font-display), sans-serif",
              fontWeight: 700,
              fontSize: 16,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      ) : recipe ? (
        <div className="h-full flex">
          {/* Left: meta + ingredients (tinted panel) */}
          <div
            className="overflow-y-auto shrink-0"
            style={{
              width: 360,
              background: "var(--meals-tint)",
              borderRight: "2px solid var(--ink)",
              padding: 20,
              paddingBottom: 32,
            }}
          >
            <div className="flex flex-wrap gap-2 mb-3">
              {formatTime(recipe.cookTimeMinutes) && (
                <MetaPill>🕐 {formatTime(recipe.cookTimeMinutes)}</MetaPill>
              )}
              {recipe.servings && <MetaPill>👥 Serves {recipe.servings}</MetaPill>}
              {recipe.freezable && <MetaPill>❄️ Freezable</MetaPill>}
              {recipe.recipeSource && <SourceSticker label={recipe.recipeSource} />}
            </div>

            {activeDietTags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {activeDietTags.map((t) => (
                  <MetaPill key={t.key}>
                    {t.icon} {t.label}
                  </MetaPill>
                ))}
              </div>
            )}

            {recipe.caloriesPerServing && (
              <div
                className="flex gap-4 mb-4 text-base font-bold"
                style={{ color: "var(--ink)" }}
              >
                <span>{Math.round(recipe.caloriesPerServing)} kcal</span>
                {recipe.proteinPerServing && (
                  <span>P {Math.round(recipe.proteinPerServing)}g</span>
                )}
                {recipe.carbsPerServing && (
                  <span>C {Math.round(recipe.carbsPerServing)}g</span>
                )}
                {recipe.fatPerServing && (
                  <span>F {Math.round(recipe.fatPerServing)}g</span>
                )}
              </div>
            )}

            <div
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 13,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--ink-60)",
                marginBottom: 10,
              }}
            >
              Ingredients
            </div>
            <div className="flex flex-col gap-2">
              {sortedIngredients.map((ing, i) => (
                <div key={i} className="flex items-start gap-2 text-base">
                  <span style={{ color: "var(--meals)", marginTop: 6, fontSize: 10 }}>
                    ●
                  </span>
                  <span>{ing.ingredientName}</span>
                </div>
              ))}
              {sortedIngredients.length === 0 && (
                <div className="text-base" style={{ color: "var(--ink-60)" }}>
                  No ingredients listed
                </div>
              )}
            </div>
          </div>

          {/* Right: method */}
          <div className="flex-1 overflow-y-auto" style={{ padding: 20, paddingBottom: 32 }}>
            <div
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontWeight: 700,
                fontSize: 13,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--ink-60)",
                marginBottom: 10,
              }}
            >
              Method
            </div>
            <div className="flex flex-col gap-4">
              {sortedInstructions.map((step, i) => (
                <div key={i} className="flex gap-3">
                  <div
                    className="shrink-0 flex items-center justify-center"
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 999,
                      fontFamily: "var(--font-display), sans-serif",
                      fontWeight: 800,
                      fontSize: 14,
                      background: "var(--meals)",
                      color: "#fff",
                      border: "2px solid var(--ink)",
                    }}
                  >
                    {step.stepNumber || i + 1}
                  </div>
                  <div className="text-base leading-relaxed pt-0.5">
                    {cleanStepText(step.instruction)}
                    {step.timerMinutes && (
                      <span
                        className="inline-block ml-2 font-bold"
                        style={{
                          fontSize: 13,
                          borderRadius: 999,
                          background: "var(--home-tint)",
                          border: "2px solid var(--ink)",
                          padding: "3px 10px",
                        }}
                      >
                        ⏱ {step.timerMinutes} min
                      </span>
                    )}
                  </div>
                </div>
              ))}
              {sortedInstructions.length === 0 && (
                <div className="text-base" style={{ color: "var(--ink-60)" }}>
                  No method steps listed
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </Takeover>
  );
}
