import { NextResponse } from "next/server";

// Zigbee2MQTT on the Pi
const Z2M_BASE = "http://192.168.0.110:8080/api";
const DEVICE_ID = "0xa4c13805b774ffff"; // Sonoff S60ZBTPG

export async function GET() {
  try {
    // Get device state from Zigbee2MQTT API
    const res = await fetch(`${Z2M_BASE}/devices`, {
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    });

    if (!res.ok) throw new Error(`Z2M returned ${res.status}`);

    const devices = await res.json();
    const plug = devices.find(
      (d: { ieee_address: string }) => d.ieee_address === DEVICE_ID
    );

    if (!plug) {
      return NextResponse.json({ status: "not_found", state: null });
    }

    return NextResponse.json({
      status: "ok",
      state: plug.state?.state || "unknown",
      linkQuality: plug.state?.linkquality ?? null,
      friendly_name: plug.friendly_name,
    });
  } catch {
    return NextResponse.json({ status: "offline", state: null });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const action = body.state === "ON" ? "ON" : "OFF";

    // Use Zigbee2MQTT MQTT publish via its API
    const res = await fetch(`${Z2M_BASE}/devices/${DEVICE_ID}/set`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: action }),
      signal: AbortSignal.timeout(3000),
    });

    if (!res.ok) throw new Error(`Z2M set returned ${res.status}`);

    return NextResponse.json({ status: "ok", state: action });
  } catch (e) {
    return NextResponse.json(
      { status: "error", error: String(e) },
      { status: 500 }
    );
  }
}
