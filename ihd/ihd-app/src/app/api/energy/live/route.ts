import { NextResponse } from "next/server";

// Hadley API on the main PC — serves live Octopus Home Mini telemetry
const HADLEY_ENERGY_LIVE = "http://192.168.0.87:8100/energy/live";

export async function GET() {
  try {
    const res = await fetch(HADLEY_ENERGY_LIVE, {
      signal: AbortSignal.timeout(4000),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Hadley API returned ${res.status}`);
    const data = await res.json();
    return NextResponse.json({ status: "ok", ...data });
  } catch {
    return NextResponse.json({ status: "offline" }, { status: 200 });
  }
}
