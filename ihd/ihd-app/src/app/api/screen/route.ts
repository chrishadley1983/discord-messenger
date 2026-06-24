import { NextResponse } from "next/server";

const SCREEN_API_URL = "http://localhost:5002";

export async function GET() {
  try {
    const res = await fetch(SCREEN_API_URL, {
      signal: AbortSignal.timeout(2000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Screen API returned ${res.status}`);
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json(
      { state: "active", idle_seconds: 0, display_on: true, night_mode: false },
      { status: 200 }
    );
  }
}
