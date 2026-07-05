import { NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";

/**
 * Countdowns — successor to the Japan Trip widget.
 * Items live in .data/countdowns.json (edit on the Pi, survives deploys):
 *   annual: date "MM-DD", rolls to the next occurrence each year
 *   one-off: date "YYYY-MM-DD", disappears once passed
 */

const DATA_DIR = join(process.cwd(), ".data");
const FILE = join(DATA_DIR, "countdowns.json");

interface CountdownItem {
  id: string;
  label: string;
  emoji: string;
  date: string; // "MM-DD" (annual) or "YYYY-MM-DD" (one-off)
  annual: boolean;
}

const SEED: CountdownItem[] = [
  // Holidays (one-off; dates from bookings/diary Jul 2026)
  { id: "cromer", label: "Cromer holiday", emoji: "🏖️", date: "2026-07-31", annual: false },
  { id: "austria", label: "Austria trip", emoji: "🏔️", date: "2026-08-11", annual: false },
  { id: "denmark", label: "Denmark holiday", emoji: "🇩🇰", date: "2026-08-20", annual: false },
  { id: "south-africa", label: "South Africa safari", emoji: "🦁", date: "2026-10-23", annual: false },
  // Annual fixtures
  { id: "abby-bday", label: "Abby's birthday", emoji: "🎂", date: "08-05", annual: true },
  { id: "max-bday", label: "Max's birthday", emoji: "🎂", date: "09-09", annual: true },
  { id: "emmie-bday", label: "Emmie's birthday", emoji: "🎂", date: "11-01", annual: true },
  { id: "halloween", label: "Halloween", emoji: "🎃", date: "10-31", annual: true },
  { id: "bonfire", label: "Bonfire Night", emoji: "🎆", date: "11-05", annual: true },
  { id: "christmas", label: "Christmas", emoji: "🎄", date: "12-25", annual: true },
];

async function loadItems(): Promise<CountdownItem[]> {
  try {
    const raw = await readFile(FILE, "utf-8");
    const data = JSON.parse(raw);
    if (Array.isArray(data.items)) return data.items;
  } catch {
    // seed on first run
    try {
      await mkdir(DATA_DIR, { recursive: true });
      await writeFile(FILE, JSON.stringify({ items: SEED }, null, 2));
    } catch {
      /* read-only fs — fall through with seed */
    }
  }
  return SEED;
}

/** Date-only "today" in Europe/London */
function todayLondon(): Date {
  const s = new Date().toLocaleDateString("en-CA", { timeZone: "Europe/London" });
  return new Date(s + "T00:00:00Z");
}

function nextOccurrence(item: CountdownItem, today: Date): Date | null {
  if (item.annual) {
    const [mm, dd] = item.date.split("-").map(Number);
    let d = new Date(Date.UTC(today.getUTCFullYear(), mm - 1, dd));
    if (d < today) d = new Date(Date.UTC(today.getUTCFullYear() + 1, mm - 1, dd));
    return d;
  }
  const d = new Date(item.date + "T00:00:00Z");
  return d >= today ? d : null; // past one-offs drop out
}

export async function GET() {
  const items = await loadItems();
  const today = todayLondon();

  const upcoming = items
    .map((item) => {
      const next = nextOccurrence(item, today);
      if (!next) return null;
      const days = Math.round((next.getTime() - today.getTime()) / 86400000);
      return {
        id: item.id,
        label: item.label,
        emoji: item.emoji,
        date: next.toISOString().slice(0, 10),
        dateLabel: next.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "long",
          timeZone: "UTC",
        }),
        days,
      };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
    .sort((a, b) => a.days - b.days);

  return NextResponse.json({ countdowns: upcoming });
}
