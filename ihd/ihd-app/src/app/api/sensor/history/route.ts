import { NextRequest, NextResponse } from "next/server";

const ZIGBEE_API_URL = "http://192.168.0.110:5001";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const device = params.get("device") || "";
  const hours = params.get("hours") || "24";
  const type = params.get("type") || "readings"; // readings or motion

  const qs = new URLSearchParams({ hours, type });
  if (device) qs.set("device", device);

  try {
    const res = await fetch(`${ZIGBEE_API_URL}/history?${qs}`, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Zigbee API returned ${res.status}`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json([]);
  }
}
