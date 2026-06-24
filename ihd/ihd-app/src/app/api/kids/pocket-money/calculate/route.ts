import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import { join } from "path";

const GRID_FILE = join(process.cwd(), ".data", "pocket-money-grid.json");

const RATES: Record<string, number> = {
  room_tidy: 40,
  behaviour: 20,
  homework: 20,
  special_boost: 200,
};

const CATEGORY_LABELS: Record<string, string> = {
  room_tidy: "Room Tidy",
  behaviour: "Behaviour",
  homework: "Homework",
  special_boost: "Boost",
};

const CATEGORIES = ["room_tidy", "behaviour", "homework", "special_boost"] as const;
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function currentWeekKey(): string {
  const now = new Date();
  const jsDay = now.getDay();
  const diff = jsDay === 0 ? 6 : jsDay - 1;
  const monday = new Date(now);
  monday.setDate(monday.getDate() - diff);
  return monday.toISOString().slice(0, 10);
}

function formatPence(pence: number): string {
  return `\u00a3${(pence / 100).toFixed(2)}`;
}

function buildChildSummary(name: string, grid: Record<string, Record<string, boolean>>) {
  let total = 0;
  const lines: string[] = [];
  lines.push(`${name}'s Pocket Money Grid:`);
  lines.push(`         ${DAY_LABELS.join("  ")}`);

  for (const cat of CATEGORIES) {
    const row = grid[cat] || {};
    const ticks = DAYS.map((d) => (row[d] ? "\u2713" : "\u2717"));
    const count = DAYS.filter((d) => row[d]).length;
    const rate = RATES[cat];
    const subtotal = count * rate;
    total += subtotal;

    const label = (CATEGORY_LABELS[cat] || cat).padEnd(8);
    const rateLabel = rate >= 100 ? formatPence(rate) : `${rate}p`;
    lines.push(`${label} ${ticks.join("   ")}  (${count} \u00d7 ${rateLabel} = ${formatPence(subtotal)})`);
  }

  lines.push(`Total: ${formatPence(total)}`);

  return { lines, total };
}

export async function GET(request: NextRequest) {
  const weekKey = request.nextUrl.searchParams.get("week") || currentWeekKey();

  let data;
  try {
    const raw = await readFile(GRID_FILE, "utf-8");
    data = JSON.parse(raw);
  } catch {
    data = {};
  }

  const week = data[weekKey];
  if (!week) {
    return NextResponse.json({
      week: weekKey,
      message: `No grid data for week ${weekKey}`,
      emmie: { total: 0, formatted: "\u00a30.00" },
      max: { total: 0, formatted: "\u00a30.00" },
    });
  }

  const emmie = buildChildSummary("Emmie", week.emmie || {});
  const max = buildChildSummary("Max", week.max || {});

  const message = [
    `Pocket Money Summary for week of ${weekKey}`,
    "",
    ...emmie.lines,
    "",
    ...max.lines,
    "",
    `Combined total: ${formatPence(emmie.total + max.total)}`,
  ].join("\n");

  return NextResponse.json({
    week: weekKey,
    message,
    emmie: { total: emmie.total, formatted: formatPence(emmie.total) },
    max: { total: max.total, formatted: formatPence(max.total) },
  });
}
