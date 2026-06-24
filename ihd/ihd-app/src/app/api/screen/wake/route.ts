import { NextResponse } from "next/server";

export async function POST() {
  try {
    // Send a simulated motion event via MQTT to wake the screen
    const res = await fetch("http://localhost:5002/wake", {
      method: "POST",
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) throw new Error("Wake failed");
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ ok: false }, { status: 200 });
  }
}
