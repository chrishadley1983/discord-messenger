import { NextResponse } from "next/server";

const ZIGBEE_API_URL = "http://192.168.0.110:5001";

export async function GET() {
  try {
    const res = await fetch(ZIGBEE_API_URL, {
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Zigbee API returned ${res.status}`);

    const data = await res.json();
    return NextResponse.json({ status: "ok", sensors: data });
  } catch {
    return NextResponse.json(
      { status: "offline", sensors: {} },
      { status: 200 }
    );
  }
}
