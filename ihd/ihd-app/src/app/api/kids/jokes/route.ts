import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";
import { randomUUID } from "crypto";

const DATA_DIR = join(process.cwd(), ".data");
const JOKES_FILE = join(DATA_DIR, "dad-jokes.json");

interface Joke {
  id: string;
  text: string;
  date: string;
}

interface JokesData {
  jokes: Joke[];
}

async function loadJokes(): Promise<JokesData> {
  try {
    const raw = await readFile(JOKES_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return { jokes: [] };
  }
}

async function saveJokes(data: JokesData) {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(JOKES_FILE, JSON.stringify(data, null, 2));
}

function todayStr(): string {
  return new Date().toISOString().split("T")[0];
}

export async function GET() {
  const data = await loadJokes();
  const today = todayStr();

  // Return only today's jokes so the dashboard rotates daily
  const todaysJokes = data.jokes.filter(
    (j) => j.date.startsWith(today)
  );

  // Fallback: if no jokes today, show the most recent batch
  if (todaysJokes.length === 0) {
    const sorted = [...data.jokes].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    const latestDate = sorted[0]?.date.split("T")[0];
    const latest = latestDate
      ? sorted.filter((j) => j.date.startsWith(latestDate))
      : [];
    return NextResponse.json({ jokes: latest, count: latest.length, date: latestDate || null });
  }

  return NextResponse.json({ jokes: todaysJokes, count: todaysJokes.length, date: today });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Bulk replace: POST { jokes: [{text: "..."}, ...] }
    if (Array.isArray(body.jokes)) {
      const today = new Date().toISOString();
      const newJokes: Joke[] = body.jokes.map((j: { text: string }) => ({
        id: randomUUID(),
        text: j.text.trim(),
        date: today,
      }));

      // Keep previous days' jokes for history, replace today's
      const data = await loadJokes();
      const todayPrefix = todayStr();
      const kept = data.jokes.filter((j) => !j.date.startsWith(todayPrefix));
      kept.push(...newJokes);
      await saveJokes({ jokes: kept });

      return NextResponse.json({ ok: true, replaced: newJokes.length });
    }

    // Single joke: POST { text: "..." }
    const { text } = body;
    if (!text || typeof text !== "string") {
      return NextResponse.json({ error: "Missing joke text" }, { status: 400 });
    }

    const data = await loadJokes();
    const joke: Joke = {
      id: randomUUID(),
      text: text.trim(),
      date: new Date().toISOString(),
    };
    data.jokes.push(joke);
    await saveJokes(data);

    return NextResponse.json({ ok: true, id: joke.id });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
