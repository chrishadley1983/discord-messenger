/**
 * Reusable Google Flights scraper (primary data source for flight-prices).
 *
 * Drives the dedicated CDP Chrome (Windows, port 9222) via Playwright and reads
 * fares straight from Google Flights — no API quota. SerpApi is the fallback,
 * handled on the Python side (services/flight_prices.py).
 *
 * Usage:
 *   node flight_scrape.cjs <config.json>
 *
 * Config (JSON):
 *   {
 *     "cdp": "http://localhost:9222",          // optional, default localhost:9222
 *     "searches": [
 *       {
 *         "id": "direct-thu-sun",
 *         "label": "Direct — Thu night / Sun morning",
 *         "origin": "LHR", "destination": "HND",
 *         "outbound": "2027-03-25", "return": "2027-04-11",
 *         "adults": 2, "children": [8, 10],
 *         "maxStops": 0                          // 0=nonstop, 1=<=1 stop, 2=<=2, null=any
 *       }
 *     ]
 *   }
 *
 * Output (stdout, JSON only — all logs go to stderr):
 *   { "ok": true, "results": [ { id, label, query, paxBasis, cheapestBanner,
 *     insight, flights: [ {price, currency, departTime, arriveTime, plusDays,
 *     durationMin, stops, nonstop, layovers:[{min,airport}], layoverMin,
 *     airlines, raw } ] } ] }
 */
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright-core')); }
catch (e) { ({ chromium } = require('playwright')); }

const log = (...a) => console.error('[scrape]', ...a);

function buildUrl(s) {
  const q = `Flights from ${s.origin} to ${s.destination} on ${s.outbound} returning ${s.return}`;
  return 'https://www.google.com/travel/flights?curr=GBP&hl=en-GB&gl=GB&q=' + encodeURIComponent(q);
}

async function dismissConsent(page) {
  for (const t of ['Accept all', 'Reject all', 'I agree', 'Accept']) {
    try {
      const b = page.getByRole('button', { name: t });
      if (await b.count()) { await b.first().click({ timeout: 3000 }); log('consent:', t); return; }
    } catch (e) {}
  }
}

async function setPassengers(page, adults, children) {
  // Best-effort: set adults + children. Returns a human basis string read back from the UI.
  try {
    const btn = page.getByRole('button', { name: /passenger/i });
    if (!(await btn.count())) { log('no passenger button'); return null; }
    await btn.first().click({ timeout: 6000 });
    await page.waitForTimeout(800);
    // adults: default is 1 → click "Add adult" (adults-1) times
    const addAdult = page.getByRole('button', { name: /add adult/i });
    for (let i = 1; i < (adults || 1); i++) { try { await addAdult.first().click({ timeout: 2500 }); await page.waitForTimeout(250); } catch (e) {} }
    // children
    const kids = Array.isArray(children) ? children : [];
    const addChild = page.getByRole('button', { name: /add child/i });
    for (let i = 0; i < kids.length; i++) { try { await addChild.first().click({ timeout: 2500 }); await page.waitForTimeout(250); } catch (e) {} }
    // set child ages via the age comboboxes if present
    try {
      const ageSelects = page.locator('select');
      const n = await ageSelects.count();
      // Google renders one <select> per child age when children > 0
      for (let i = 0; i < kids.length && i < n; i++) {
        try { await ageSelects.nth(i).selectOption(String(kids[i]), { timeout: 1500 }); } catch (e) {}
      }
    } catch (e) {}
    // Done
    for (const t of ['Done', 'Apply']) {
      try { const d = page.getByRole('button', { name: new RegExp(`^${t}$`, 'i') }); if (await d.count()) { await d.first().click({ timeout: 2500 }); break; } } catch (e) {}
    }
    await page.waitForTimeout(1500);
    // read back the passenger button label
    try {
      const label = await page.getByRole('button', { name: /passenger/i }).first().getAttribute('aria-label');
      log('pax label:', label);
      return label;
    } catch (e) { return null; }
  } catch (e) { log('setPassengers failed:', e.message); return null; }
}

async function applyStopsFilter(page, maxStops) {
  if (maxStops === null || maxStops === undefined) return;
  const labelMap = { 0: /Non-?stop only/i, 1: /One stop or fewer/i, 2: /Two stops or fewer/i };
  const want = labelMap[maxStops];
  if (!want) return;
  try {
    await page.getByRole('button', { name: /^Stops/i }).first().click({ timeout: 8000 });
    await page.waitForTimeout(1200);
    let clicked = false;
    for (const sel of [page.getByRole('radio', { name: want }), page.getByText(want)]) {
      try { if (await sel.count()) { await sel.first().click({ timeout: 4000 }); clicked = true; break; } } catch (e) {}
    }
    log('stops filter', maxStops, 'clicked:', clicked);
    await page.keyboard.press('Escape');
  } catch (e) { log('applyStopsFilter failed:', e.message); }
}

function dayDiff(depDate, arrDate) {
  // depDate/arrDate like "March 25" / "March 27" (no year). Assume same year window.
  try {
    const d = new Date(`${depDate}, 2027`);
    const a = new Date(`${arrDate}, 2027`);
    if (isNaN(d) || isNaN(a)) return 0;
    return Math.round((a - d) / 86400000);
  } catch (e) { return 0; }
}

function parseAria(al) {
  // Price (round trip total): "From 864 British pounds round trip total."
  let price = null;
  let m = al.match(/([\d,]+)\s*British pounds/i) || al.match(/£\s*([\d,]+)/);
  if (m) price = parseInt(m[1].replace(/,/g, ''), 10);
  // Airline(s): "1 stop flight with Air India." / "Non-stop flight with Japan Airlines, British Airways."
  let airlines = null;
  const am = al.match(/flight with ([^.]+?)\./i);
  if (am) airlines = am[1].trim();
  // Times (24h): "Leaves Heathrow Airport at 13:30 on Thursday, March 25 and arrives at Haneda Airport at 04:55 on Saturday, March 27"
  const dep = al.match(/Leaves\b[^0-9]*?(\d{1,2}:\d{2})/i);
  const arr = al.match(/arrives\b[^0-9]*?(\d{1,2}:\d{2})/i);
  const depDate = al.match(/Leaves\b.*?\bon\s+(?:[A-Za-z]+,\s*)?([A-Za-z]+\s+\d{1,2})/i);
  const arrDate = al.match(/arrives\b.*?\bon\s+(?:[A-Za-z]+,\s*)?([A-Za-z]+\s+\d{1,2})/i);
  // Duration: "Total duration 30 hrs 25 min."
  let durationMin = null;
  const d = al.match(/Total duration\s*(\d+)\s*hrs?(?:\s*(\d+)\s*min)?/i);
  if (d) durationMin = parseInt(d[1], 10) * 60 + (d[2] ? parseInt(d[2], 10) : 0);
  // Stops
  const nonstop = /Non-?stop flight/i.test(al);
  let stops = nonstop ? 0 : null;
  const sm = al.match(/(\d+)\s*stop flight/i);
  if (sm) stops = parseInt(sm[1], 10);
  // Stopovers: "Stopover (1 of 1) is a 12 hrs 40 min overnight stopover at Delhi Airport"
  // (also handles "Change of airport" phrasing where no "at <Airport>" follows)
  const layovers = [];
  for (const chunk of al.split(/Stopover/i).slice(1)) {
    const dm = chunk.match(/is an?\s*(?:(\d+)\s*hrs?)?\s*(?:(\d+)\s*min)?/i);
    const min = dm ? ((dm[1] ? parseInt(dm[1], 10) * 60 : 0) + (dm[2] ? parseInt(dm[2], 10) : 0)) : 0;
    if (min > 0) {
      // prefer the city ("...Airport in Doha.") else the airport name ("at Delhi Airport")
      const cityM = chunk.match(/\bin\s+([A-Z][A-Za-z]+)\b/);
      const am = chunk.match(/at\s+([A-Za-z][^.,]*?)\s+Airport/i);
      const airport = cityM ? cityM[1] : (am ? am[1].trim() : null);
      layovers.push({ min, airport });
    }
  }
  const layoverMin = layovers.reduce((a, b) => a + b.min, 0) || null;
  const plusDays = (depDate && arrDate) ? dayDiff(depDate[1], arrDate[1]) : 0;
  return {
    price,
    currency: 'GBP',
    airlines,
    departTime: dep ? dep[1] : null,
    arriveTime: arr ? arr[1] : null,
    departDate: depDate ? depDate[1] : null,
    arriveDate: arrDate ? arrDate[1] : null,
    plusDays,
    durationMin, stops, nonstop, layovers, layoverMin,
    raw: al.slice(0, 300),
  };
}

async function sortCheapest(page) {
  // Click the Best | Cheapest toggle so the cheapest fares are guaranteed to load.
  for (const sel of [page.getByRole('tab', { name: /^Cheapest/i }), page.getByRole('radio', { name: /^Cheapest/i }), page.getByText(/^Cheapest/)]) {
    try { if (await sel.count()) { await sel.first().click({ timeout: 4000 }); log('sorted cheapest'); return true; } } catch (e) {}
  }
  return false;
}

async function expandAll(page) {
  // Expand the collapsed "Other departing flights" / "View more flights".
  for (let i = 0; i < 3; i++) {
    let clicked = false;
    for (const sel of [page.getByRole('button', { name: /View more flights/i }), page.getByRole('button', { name: /more flights/i })]) {
      try { if (await sel.count()) { await sel.first().click({ timeout: 3000 }); clicked = true; await page.waitForTimeout(1500); } } catch (e) {}
    }
    try { await page.mouse.wheel(0, 5000); await page.waitForTimeout(800); } catch (e) {}
    if (!clicked) break;
  }
}

async function extractFlights(page) {
  const labels = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('[aria-label]').forEach((el) => {
      const al = el.getAttribute('aria-label') || '';
      if (/round trip total/i.test(al) && /British pounds/i.test(al)) out.push(al);
    });
    return Array.from(new Set(out));
  });
  return labels.map(parseAria).filter((f) => f.price);
}

async function extractContext(page) {
  const txt = await page.evaluate(() => document.body.innerText);
  let cheapestBanner = null, insight = null;
  let m = txt.match(/from\s*£\s*([\d,]+)/i);
  if (m) cheapestBanner = parseInt(m[1].replace(/,/g, ''), 10);
  const im = txt.match(/Prices are currently (typical|low|high)/i);
  if (im) insight = im[1].toLowerCase();
  return { cheapestBanner, insight };
}

async function runSearch(ctx, s) {
  const page = await ctx.newPage();
  const res = { id: s.id, label: s.label, query: { ...s }, paxBasis: null, cheapestBanner: null, insight: null, flights: [] };
  try {
    await page.setViewportSize({ width: 1400, height: 2600 });
    await page.goto(buildUrl(s), { waitUntil: 'domcontentloaded', timeout: 60000 });
    await dismissConsent(page);
    await page.waitForTimeout(5000);
    res.paxBasis = await setPassengers(page, s.adults, s.children);
    await applyStopsFilter(page, s.maxStops);
    await page.waitForTimeout(4000);
    await sortCheapest(page);
    await page.waitForTimeout(4000);
    try { await page.waitForSelector('[aria-label*="round trip total" i]', { timeout: 15000 }); } catch (e) {}
    await expandAll(page);
    const ctxInfo = await extractContext(page);
    res.cheapestBanner = ctxInfo.cheapestBanner;
    res.insight = ctxInfo.insight;
    res.flights = await extractFlights(page);
    log(`search ${s.id}: ${res.flights.length} flights, cheapest banner £${res.cheapestBanner}, insight=${res.insight}`);
  } catch (e) {
    res.error = e.message;
    log(`search ${s.id} ERROR:`, e.message);
  } finally {
    await page.close().catch(() => {});
  }
  return res;
}

(async () => {
  const cfgPath = process.argv[2];
  if (!cfgPath) { console.error('usage: node flight_scrape.cjs <config.json>'); process.exit(2); }
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf-8'));
  const cdp = cfg.cdp || 'http://localhost:9222';
  let browser;
  try {
    browser = await chromium.connectOverCDP(cdp);
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: `CDP connect failed: ${e.message}` }));
    process.exit(1);
  }
  const ctx = browser.contexts()[0] || (await browser.newContext());
  const results = [];
  for (const s of cfg.searches) {
    results.push(await runSearch(ctx, s));
  }
  try { await browser.close(); } catch (e) {}
  console.log(JSON.stringify({ ok: true, results }));
})().catch((e) => { console.log(JSON.stringify({ ok: false, error: e.message })); process.exit(1); });
