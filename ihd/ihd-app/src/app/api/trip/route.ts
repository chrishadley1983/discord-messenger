import { NextResponse } from "next/server";

const CALENDAR_URL = "https://hadley-japan-2026.surge.sh/calendar-planner.html";
const SITE_URL = "https://hadley-japan-2026.surge.sh";

interface Venue {
  id: string;
  name: string;
  city: string;
  area: string;
  price: string;
  rating: string;
  verdict: string;
  tags: string;
  category: string;
  emoji: string;
  guide: string;
}

function parseVenues(html: string): Venue[] {
  const venues: Venue[] = [];

  // Match full venue objects with all 13 fields
  // {id:'...',name:'...',city:'...',area:'...',lat:N,lng:N,price:'...',rating:'...',verdict:'...',tags:'...',category:'...',emoji:'...',guide:'...'}
  const pattern =
    /\{id:'([^']*)',name:'([^']*)',city:'([^']*)',area:'([^']*)',lat:[^,]*,lng:[^,]*,price:'([^']*)',rating:'([^']*)',verdict:'([^']*)',tags:'([^']*)',category:'([^']*)',emoji:'([^']*)',guide:'([^']*)'\}/g;
  let m;

  while ((m = pattern.exec(html)) !== null) {
    venues.push({
      id: m[1],
      name: m[2],
      city: m[3],
      area: m[4],
      price: m[5],
      rating: m[6],
      verdict: m[7],
      tags: m[8],
      category: m[9],
      emoji: m[10],
      guide: m[11],
    });
  }

  return venues;
}

export async function GET() {
  const now = new Date();
  const departure = new Date("2026-04-03T00:00:00");
  const daysToGo = Math.ceil((departure.getTime() - now.getTime()) / 864e5);
  const route = "Tokyo · Osaka · Kyoto · Tokyo";

  let venues: Venue[] = [];

  try {
    const res = await fetch(CALENDAR_URL, { next: { revalidate: 3600 } });
    if (res.ok) {
      const html = await res.text();
      venues = parseVenues(html);
    }
  } catch {
    // Fallback — widget still shows countdown
  }

  return NextResponse.json({
    departure: "2026-04-03",
    totalNights: 16,
    daysToGo: Math.max(daysToGo, 0),
    route,
    venues,
    siteUrl: SITE_URL,
  });
}
