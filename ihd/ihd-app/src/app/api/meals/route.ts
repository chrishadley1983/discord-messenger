import { NextRequest, NextResponse } from "next/server";

const HADLEY_API = process.env.HADLEY_API_URL || "http://localhost:8100";

export async function GET(request: NextRequest) {
  const action = request.nextUrl.searchParams.get("action") || "current";
  const recipeId = request.nextUrl.searchParams.get("recipe");

  try {
    let url: string;

    if (recipeId) {
      url = `${HADLEY_API}/recipes/${encodeURIComponent(recipeId)}`;
    } else if (action === "search") {
      const q = request.nextUrl.searchParams.get("q") || "";
      url = `${HADLEY_API}/recipes/search?q=${encodeURIComponent(q)}`;
    } else if (action === "reminders") {
      url = `${HADLEY_API}/meal-plan/reminders`;
    } else {
      url = `${HADLEY_API}/meal-plan/current`;
    }

    const res = await fetch(url, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Hadley API returned ${res.status}`);

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json(
      { error: "Meals unavailable", detail: String(e) },
      { status: 200 }
    );
  }
}
