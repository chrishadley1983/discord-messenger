import { NextResponse } from "next/server";

const SCREEN_API_URL = "http://localhost:5002";

export async function POST() {
  try {
    await fetch(`${SCREEN_API_URL}/heartbeat`, {
      method: "POST",
      signal: AbortSignal.timeout(2000),
      cache: "no-store",
    });
  } catch {
    // Controller down — nothing to record; the beat is best-effort.
  }
  return NextResponse.json({ ok: true });
}
