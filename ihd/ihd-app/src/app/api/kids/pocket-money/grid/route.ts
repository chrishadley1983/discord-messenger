import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";

const DATA_DIR = join(process.cwd(), ".data");
const GRID_FILE = join(DATA_DIR, "pocket-money-grid.json");

const CATEGORIES = ["room_tidy", "behaviour", "homework", "special_boost"] as const;
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

type Category = (typeof CATEGORIES)[number];
type Day = (typeof DAYS)[number];
type ChildGrid = Record<Category, Record<Day, boolean>>;

interface WeekData {
  [weekKey: string]: {
    emmie: ChildGrid;
    max: ChildGrid;
  };
}

function emptyGrid(): ChildGrid {
  const grid = {} as ChildGrid;
  for (const cat of CATEGORIES) {
    grid[cat] = {} as Record<Day, boolean>;
    for (const day of DAYS) {
      grid[cat][day] = false;
    }
  }
  return grid;
}

// Get Monday of the current week as YYYY-MM-DD
function currentWeekKey(): string {
  const now = new Date();
  const jsDay = now.getDay(); // 0=Sun
  const diff = jsDay === 0 ? 6 : jsDay - 1; // days since Monday
  const monday = new Date(now);
  monday.setDate(monday.getDate() - diff);
  return monday.toISOString().slice(0, 10);
}

async function loadGrid(): Promise<WeekData> {
  try {
    const raw = await readFile(GRID_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

async function saveGrid(data: WeekData) {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(GRID_FILE, JSON.stringify(data, null, 2));
}

function ensureWeek(data: WeekData, weekKey: string) {
  if (!data[weekKey]) {
    data[weekKey] = { emmie: emptyGrid(), max: emptyGrid() };
  }
}

export async function GET(request: NextRequest) {
  const weekKey = request.nextUrl.searchParams.get("week") || currentWeekKey();
  const data = await loadGrid();
  ensureWeek(data, weekKey);

  return NextResponse.json({
    week: weekKey,
    emmie: data[weekKey].emmie,
    max: data[weekKey].max,
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { child, category, day, value, week } = body;

    if (child !== "emmie" && child !== "max") {
      return NextResponse.json({ error: "Invalid child" }, { status: 400 });
    }
    if (!CATEGORIES.includes(category)) {
      return NextResponse.json({ error: "Invalid category" }, { status: 400 });
    }
    if (!DAYS.includes(day)) {
      return NextResponse.json({ error: "Invalid day" }, { status: 400 });
    }

    const weekKey = week || currentWeekKey();
    const data = await loadGrid();
    ensureWeek(data, weekKey);

    data[weekKey][child as "emmie" | "max"][category as Category][day as Day] = !!value;
    await saveGrid(data);

    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
