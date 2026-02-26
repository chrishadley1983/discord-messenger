/**
 * Vinted Sniper — Content Script v1
 *
 * Monitors Vinted catalog/search pages for new listings.
 * - Finds /items/ITEMID links in the grid
 * - Extracts price, title, condition, brand, image
 * - Looks up Lego set numbers against Supabase price_snapshots
 * - Compares Vinted price vs Amazon buy box price
 * - Sends colour-coded Discord alerts for deals
 * - Status bar with scan count and refresh countdown
 */

(function () {
  'use strict';

  const DEFAULT_WEBHOOK = 'https://discordapp.com/api/webhooks/1470092279585706089/efND5z6IviV06mM5L_Wv5GKEUzkIbDnIlGsMt5aK6cXimu2KrWpKvF1bEllFuu3kcSji';

  // Supabase config
  const SUPABASE_URL = 'https://modjoikyuhqzouxvieua.supabase.co';
  const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA';

  // ── State ──────────────────────────────────────────────────────────
  const sentHashes = new Set();
  let config = {
    webhookUrl: DEFAULT_WEBHOOK,
    minDiscount: 0, interval: 45, maxPosts: 5,
    refreshMinSecs: 60, refreshMaxSecs: 240,
    quietStart: null, quietEnd: null,  // 0-23 hour values, null = disabled
    vintedPostage: 2.39,               // Vinted buyer postage added to COG
    minMarginGreen: 25,                // Profit margin % for green (great deal)
    minMarginAmber: 15                 // Profit margin % for amber (good deal)
  };
  let isRunning = false;
  let pollTimer = null;
  let refreshTimer = null;
  let firstScanDone = false;
  let scanCount = 0;
  let lastRefreshTime = new Date();
  let lastAlertTime = null;
  let priceCache = {}; // set_num → { price, name, rrp, fetched }
  let visionCache = {}; // listing_id → set number or 'UNKNOWN'
  let nextRefreshAt = Date.now() + 120000;

  // ── Init ───────────────────────────────────────────────────────────
  if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
    console.log('[Vinted Sniper] Extension context not available. Please refresh.');
    return;
  }

  chrome.storage.local.get(
    ['webhookUrl', 'minDiscount', 'interval', 'maxPosts', 'refreshMinSecs', 'refreshMaxSecs', 'quietStart', 'quietEnd', 'vintedPostage', 'minMarginGreen', 'minMarginAmber', 'vintedSentHashes'],
    data => {
      config.webhookUrl = data.webhookUrl || DEFAULT_WEBHOOK;
      config.minDiscount = data.minDiscount || 0;
      config.interval = data.interval || 45;
      config.maxPosts = data.maxPosts || 5;
      config.refreshMinSecs = data.refreshMinSecs || 60;
      config.refreshMaxSecs = data.refreshMaxSecs || 240;
      config.quietStart = (data.quietStart !== undefined && data.quietStart !== null && data.quietStart !== '') ? parseInt(data.quietStart) : null;
      config.quietEnd = (data.quietEnd !== undefined && data.quietEnd !== null && data.quietEnd !== '') ? parseInt(data.quietEnd) : null;
      config.vintedPostage = (data.vintedPostage !== undefined && data.vintedPostage !== null && data.vintedPostage !== '') ? parseFloat(data.vintedPostage) : 2.39;
      config.minMarginGreen = (data.minMarginGreen !== undefined && data.minMarginGreen !== null && data.minMarginGreen !== '') ? parseFloat(data.minMarginGreen) : 25;
      config.minMarginAmber = (data.minMarginAmber !== undefined && data.minMarginAmber !== null && data.minMarginAmber !== '') ? parseFloat(data.minMarginAmber) : 15;

      if (data.vintedSentHashes) data.vintedSentHashes.forEach(h => sentHashes.add(h));

      if (!config.webhookUrl) {
        console.log('[Vinted Sniper] No webhook URL configured.');
        showBanner('⚙️ Vinted Sniper: No webhook URL set. Right-click extension → Options.', 'warn');
        return;
      }

      console.log(`[Vinted Sniper] Active. Poll: ${config.interval}s. Refresh: ${config.refreshMinSecs}-${config.refreshMaxSecs}s. Min discount: ${config.minDiscount}%`);
      const quietStr = config.quietStart !== null ? ` | Quiet: ${config.quietStart}:00-${config.quietEnd}:00` : '';
      showBanner(`👗 Vinted Sniper active — poll ${config.interval}s, refresh ${config.refreshMinSecs}-${config.refreshMaxSecs}s${quietStr}`, 'ok');
      showStatusBar();

      setTimeout(() => {
        startPolling();
        startAutoRefresh();
      }, 3000);
    }
  );

  if (chrome.storage?.onChanged) {
    chrome.storage.onChanged.addListener(changes => {
      if (changes.webhookUrl) config.webhookUrl = changes.webhookUrl.newValue || DEFAULT_WEBHOOK;
      if (changes.minDiscount) config.minDiscount = changes.minDiscount.newValue || 0;
      if (changes.interval) {
        config.interval = changes.interval.newValue || 45;
        if (isRunning) { stopPolling(); startPolling(); }
      }
      if (changes.maxPosts) config.maxPosts = changes.maxPosts.newValue || 5;
      if (changes.refreshMinSecs !== undefined) config.refreshMinSecs = changes.refreshMinSecs?.newValue || 60;
      if (changes.refreshMaxSecs !== undefined) config.refreshMaxSecs = changes.refreshMaxSecs?.newValue || 240;
      if (changes.quietStart !== undefined) {
        const v = changes.quietStart?.newValue;
        config.quietStart = (v !== undefined && v !== null && v !== '') ? parseInt(v) : null;
      }
      if (changes.quietEnd !== undefined) {
        const v = changes.quietEnd?.newValue;
        config.quietEnd = (v !== undefined && v !== null && v !== '') ? parseInt(v) : null;
      }
      if (changes.vintedPostage !== undefined) {
        const v = changes.vintedPostage?.newValue;
        config.vintedPostage = (v !== undefined && v !== null && v !== '') ? parseFloat(v) : 2.39;
      }
      if (changes.minMarginGreen !== undefined) {
        const v = changes.minMarginGreen?.newValue;
        config.minMarginGreen = (v !== undefined && v !== null && v !== '') ? parseFloat(v) : 25;
      }
      if (changes.minMarginAmber !== undefined) {
        const v = changes.minMarginAmber?.newValue;
        config.minMarginAmber = (v !== undefined && v !== null && v !== '') ? parseFloat(v) : 15;
      }
      // Re-evaluate quiet time and refresh schedule on any config change
      startAutoRefresh();
    });
  }

  // ── Polling ────────────────────────────────────────────────────────
  function startPolling() {
    if (isRunning) return;
    isRunning = true;
    scan();
    // Randomise poll interval ±15s around configured interval
    schedulePoll();
  }

  function schedulePoll() {
    const jitter = (Math.random() - 0.5) * 30000; // ±15s
    const ms = Math.max(15000, config.interval * 1000 + jitter);
    pollTimer = setTimeout(() => { scan(); schedulePoll(); }, ms);
  }

  function stopPolling() {
    isRunning = false;
    if (pollTimer) clearTimeout(pollTimer);
  }

  let pollCycle = 0;
  function maybeScroll() {
    pollCycle++;
    if (pollCycle % 3 === 0) {
      const y = window.scrollY;
      window.scrollBy(0, window.innerHeight * 2);
      setTimeout(() => window.scrollTo(0, y), 2000);
    }
  }

  // ── Quiet Time ───────────────────────────────────────────────────
  let isQuiet = false;

  function isInQuietTime() {
    if (config.quietStart === null || config.quietEnd === null) return false;
    const hour = new Date().getHours();
    if (config.quietStart < config.quietEnd) {
      // e.g. 23:00 start, 7:00 end won't hit this — but 9:00-17:00 would
      return hour >= config.quietStart && hour < config.quietEnd;
    } else {
      // Wraps midnight, e.g. quietStart=23, quietEnd=7
      return hour >= config.quietStart || hour < config.quietEnd;
    }
  }

  // ── Auto Refresh ───────────────────────────────────────────────────
  let quietCheckTimer = null;

  function startAutoRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    if (quietCheckTimer) clearInterval(quietCheckTimer);

    if (isInQuietTime()) {
      enterQuietMode();
    } else {
      exitQuietMode();
      scheduleNextRefresh();
    }
  }

  function enterQuietMode() {
    isQuiet = true;
    if (refreshTimer) clearTimeout(refreshTimer);
    nextRefreshAt = null;
    // Stop polling during quiet time
    stopPolling();
    console.log(`[Vinted Sniper] 😴 Quiet time active (${config.quietStart}:00-${config.quietEnd}:00). Paused.`);
    // Check every 60s if quiet time has ended
    quietCheckTimer = setInterval(() => {
      if (!isInQuietTime()) {
        console.log('[Vinted Sniper] ☀️ Quiet time ended — resuming!');
        clearInterval(quietCheckTimer);
        quietCheckTimer = null;
        exitQuietMode();
        startPolling();
        scheduleNextRefresh();
      }
    }, 60000);
  }

  function exitQuietMode() {
    isQuiet = false;
    if (quietCheckTimer) { clearInterval(quietCheckTimer); quietCheckTimer = null; }
  }

  function scheduleNextRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);

    // Check quiet time before scheduling
    if (isInQuietTime()) {
      enterQuietMode();
      return;
    }

    const minMs = config.refreshMinSecs * 1000;
    const maxMs = config.refreshMaxSecs * 1000;
    const ms = minMs + Math.random() * (maxMs - minMs);
    const secs = Math.round(ms / 1000);
    nextRefreshAt = Date.now() + ms;
    console.log(`[Vinted Sniper] Next refresh in ${secs}s`);
    refreshTimer = setTimeout(() => {
      // Double-check quiet time at the moment of refresh
      if (isInQuietTime()) {
        enterQuietMode();
        return;
      }
      console.log('[Vinted Sniper] Auto-refreshing...');
      saveState(() => window.location.reload());
    }, ms);
  }

  function saveState(callback) {
    if (chrome.storage?.local) {
      chrome.storage.local.set({
        vintedSentHashes: [...sentHashes].slice(-500)
      }, callback);
    } else if (callback) callback();
  }

  // ── Scanning ───────────────────────────────────────────────────────
  async function scan() {
    scanCount++;
    maybeScroll();
    const listings = extractListings();

    const newListings = [];
    for (const listing of listings) {
      const contentHash = hashCode(listing.id + listing.title + listing.price);
      if (sentHashes.has(contentHash)) continue;
      listing.contentHash = contentHash;
      newListings.push(listing);
    }

    if (!firstScanDone) {
      firstScanDone = true;
      const preview = newListings.slice(0, 5);
      console.log(`[Vinted Sniper] First scan: ${listings.length} listings. Sending ${preview.length} as preview.`);
      for (const listing of preview) {
        await enrichAndSend(listing);
      }
      saveState();
      return;
    }

    if (newListings.length === 0) return;

    const toAlert = newListings.slice(0, config.maxPosts);
    console.log(`[Vinted Sniper] ${toAlert.length} new listing(s)!`);

    for (const listing of toAlert) {
      await enrichAndSend(listing);
    }
    saveState();
  }

  // ── Gemini Vision — identify set number from image ─────────────────
  // Sends image URL to background script which fetches (CORS-free with host_permissions)
  // and calls Gemini Vision API
  async function identifySetFromImage(imageUrl, listingId) {
    if (visionCache[listingId] !== undefined) return visionCache[listingId];

    if (!imageUrl || !imageUrl.startsWith('https')) {
      visionCache[listingId] = null;
      return null;
    }

    try {
      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { type: 'identifyImage', imageUrl, listingId },
          response => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve(response);
            }
          }
        );
      });

      if (result.error) {
        console.log(`  👁️ Vision: error — ${result.error}`);
        visionCache[listingId] = null;
        return null;
      }

      if (result.setNum) {
        console.log(`  👁️ Vision: identified set ${result.setNum} (Gemini said: "${result.raw || result.setNum}")`);
        visionCache[listingId] = result.setNum;
        return result.setNum;
      } else {
        console.log(`  👁️ Vision: no set found (Gemini said: "${result.raw || 'UNKNOWN'}")`);
        visionCache[listingId] = null;
        return null;
      }
    } catch (e) {
      console.log(`  👁️ Vision: error — ${e.message}`);
      visionCache[listingId] = null;
      return null;
    }
  }

  // ── Enrich with Supabase price data and send ──────────────────────
  // Title exclusions — skip listings matching these patterns
  const TITLE_EXCLUSIONS = [
    /button.?block.?dinosaur/i,
  ];

  async function enrichAndSend(listing) {
    // Check title exclusions (also check URL slug)
    const textToCheck = (listing.title || '') + ' ' + (listing.url || '');
    for (const pattern of TITLE_EXCLUSIONS) {
      if (pattern.test(textToCheck)) {
        console.log(`[Vinted] ── ${listing.id} ── EXCLUDED: "${listing.title}" matched ${pattern}`);
        sentHashes.add(listing.contentHash);
        return;
      }
    }
    // Try to extract set numbers from title first, then URL slug
    let setNums = extractSetNumbers(listing.title);
    if (setNums.length === 0 && listing.slugSetNums) {
      setNums = listing.slugSetNums;
    }
    // Also try extracting from the URL itself
    if (setNums.length === 0 && listing.url) {
      setNums = extractSetNumbers(listing.url);
    }

    const vintedPrice = listing.priceInclNum || listing.priceNum;
    const cog = vintedPrice ? vintedPrice + config.vintedPostage : null;

    // Verbose logging for every listing
    console.log(`[Vinted] ── ${listing.id} ──`);
    console.log(`  Title: "${listing.title}"`);
    console.log(`  URL: ${listing.url}`);
    console.log(`  Price: ${listing.price || 'n/a'} | Incl: ${listing.priceWithFees || 'n/a'} | Postage: £${config.vintedPostage} | COG: £${cog?.toFixed(2) || 'n/a'}`);
    console.log(`  Condition: ${listing.condition || 'n/a'}`);
    console.log(`  Set #s (text): ${setNums.length > 0 ? setNums.join(', ') : 'NONE'}`);

    // If no set number from text, try Gemini vision on the thumbnail
    if (setNums.length === 0 && listing.imageUrl) {
      console.log(`  👁️ Vision: attempting image identification...`);
      const visionSet = await identifySetFromImage(listing.imageUrl, listing.id);
      if (visionSet) {
        setNums = [visionSet];
        console.log(`  Set #s (vision): ${visionSet}`);
      }
    }

    let lookup = null;
    let cogPercent = null;
    let dealTier = null;
    let source = setNums.length > 0 ? 'text' : 'none';
    if (listing.slugSetNums?.includes(setNums[0])) source = 'slug';

    if (setNums.length > 0) {
      lookup = await lookupAmazonPrice(setNums[0]);

      if (lookup?.price) {
        console.log(`  Amazon: £${lookup.price.toFixed(2)} | RRP: £${lookup.rrp || 'n/a'} | "${lookup.name || '?'}"`);
      } else {
        console.log(`  Amazon: NOT FOUND for set ${setNums[0]}`);
      }

      if (lookup?.price && cog) {
        cogPercent = Math.round((cog / lookup.price) * 100);
        const _fees = lookup.price * 0.1836;
        const _ship = lookup.price < 14 ? 3 : 4;
        const _profit = lookup.price - _fees - _ship - cog;
        const _margin = ((_profit / lookup.price) * 100);
        console.log(`  COG%: ${cogPercent}% (£${cog.toFixed(2)} / £${lookup.price.toFixed(2)}) | Margin: ${_margin.toFixed(1)}% | Profit: £${_profit.toFixed(2)}`);

        if (_margin >= config.minMarginGreen) {
          dealTier = 'green';
          console.log(`  → 🟢 GREAT DEAL — Margin ${_margin.toFixed(1)}% >= ${config.minMarginGreen}% — sending`);
        } else if (_margin >= config.minMarginAmber) {
          dealTier = 'amber';
          console.log(`  → 🟠 GOOD DEAL — Margin ${_margin.toFixed(1)}% >= ${config.minMarginAmber}% — sending`);
        } else {
          console.log(`  → ❌ SKIP — Margin ${_margin.toFixed(1)}% (need >=${config.minMarginAmber}%)`);
          sentHashes.add(listing.contentHash);
          return;
        }
      }
    }

    if (!lookup?.price || !dealTier) {
      console.log(`  → ❌ SKIP — ${setNums.length === 0 ? 'no set number (text+vision)' : 'no Amazon price'}`);
      sentHashes.add(listing.contentHash);
      return;
    }

    sentHashes.add(listing.contentHash);
    await sendToDiscord(listing, setNums, lookup, cog, cogPercent, dealTier);
  }

  function extractSetNumbers(title) {
    if (!title) return [];
    const sets = new Set();

    // "set 10294", "#10294", "10294"
    const patterns = [
      /(?:set|#)\s*(\d{4,6})/gi,
      /\b([1-9]\d{4,5})\b/g
    ];

    for (const pattern of patterns) {
      let m;
      while ((m = pattern.exec(title)) !== null) {
        const num = m[1];
        if (num.length >= 4 && num.length <= 6) sets.add(num);
      }
    }

    return [...sets].slice(0, 3);
  }

  // Keepa config
  const KEEPA_KEY = '6nmo380ptlgeh7m8lpu829r1vtb9mr7sh7fv75ij4uknhs1ovjfoqop133siprkd';

  async function lookupAmazonPrice(setNum) {
    // seeded_asin_pricing uses format "75178-1"
    const dbSetNum = setNum.includes('-') ? setNum : setNum + '-1';

    // Check cache first (30 day cache)
    if (priceCache[dbSetNum] && (Date.now() - priceCache[dbSetNum].fetched < 30 * 86400000)) {
      return priceCache[dbSetNum];
    }

    // Step 1: Try Supabase
    try {
      const url = `${SUPABASE_URL}/rest/v1/seeded_asin_pricing?set_number=eq.${dbSetNum}&select=set_number,set_name,amazon_price,was_price_90d,uk_retail_price,asin&limit=1`;
      const res = await fetch(url, {
        headers: {
          'apikey': SUPABASE_KEY,
          'Authorization': `Bearer ${SUPABASE_KEY}`
        }
      });

      if (res.ok) {
        const data = await res.json();
        if (data.length > 0 && data[0].amazon_price) {
          const result = {
            price: data[0].amazon_price,
            name: data[0].set_name,
            rrp: data[0].uk_retail_price,
            wasPrice90d: data[0].was_price_90d || null,
            salesRank: null,
            asin: data[0].asin || null,
            source: 'supabase',
            fetched: Date.now()
          };
          priceCache[dbSetNum] = result;
          console.log(`  💾 Supabase: ${dbSetNum} "${result.name}" → £${result.price} | RRP £${result.rrp || 'n/a'}`);
          return result;
        }
      }
    } catch (e) {
      console.log(`  💾 Supabase error: ${e.message}`);
    }

    // Step 2: Supabase miss — try Keepa search
    console.log(`  💾 Supabase: no result for ${dbSetNum} — trying Keepa...`);
    try {
      const keepaResult = await lookupKeepa(setNum);
      if (keepaResult) {
        priceCache[dbSetNum] = keepaResult;
        return keepaResult;
      }
    } catch (e) {
      console.log(`  🔍 Keepa error: ${e.message}`);
    }

    // Both missed — cache the miss
    priceCache[dbSetNum] = { price: null, name: null, rrp: null, source: 'miss', fetched: Date.now() };
    return null;
  }

  async function lookupKeepa(setNum) {
    // Search Keepa for "LEGO <setNum>" on Amazon.co.uk (domain=2)
    // stats=1 gives current price summary
    const term = encodeURIComponent(`LEGO ${setNum}`);
    const url = `https://api.keepa.com/search?key=${KEEPA_KEY}&domain=2&type=product&term=${term}&stats=1&page=0`;

    const res = await fetch(url);
    if (!res.ok) {
      console.log(`  🔍 Keepa: API error ${res.status}`);
      return null;
    }

    const data = await res.json();
    if (!data.products || data.products.length === 0) {
      console.log(`  🔍 Keepa: no results for "LEGO ${setNum}"`);
      return null;
    }

    // Find best matching product — look for one with the set number in the title
    let product = null;
    for (const p of data.products) {
      if (p.title && p.title.includes(setNum)) {
        product = p;
        break;
      }
    }
    // Fallback to first result if no title match
    if (!product) product = data.products[0];

    // Extract price from stats — Keepa prices are in pence (divide by 100)
    // Priority: buyBoxPrice → current NEW → current AMAZON
    const stats = product.stats;
    let priceInPence = null;

    if (stats) {
      // current array: [AMAZON, NEW, USED, SALES_RANK, ...]
      // Index 0 = Amazon price, Index 1 = New 3rd party price
      // buyBoxPrice is in stats.buyBoxPrice
      if (stats.buyBoxPrice && stats.buyBoxPrice > 0) {
        priceInPence = stats.buyBoxPrice;
      } else if (stats.current && stats.current[0] > 0) {
        priceInPence = stats.current[0]; // Amazon price
      } else if (stats.current && stats.current[1] > 0) {
        priceInPence = stats.current[1]; // New 3rd party
      }
    }

    if (!priceInPence || priceInPence < 0) {
      console.log(`  🔍 Keepa: found "${product.title}" but no current price`);
      return null;
    }

    const price = priceInPence / 100;
    const name = product.title || null;

    // Sales rank — current[3] is SALES rank in stats.current array
    let salesRank = null;
    if (stats && stats.current && stats.current[3] > 0) {
      salesRank = stats.current[3];
    }

    // 90-day average price (avg90 array: index 0 = AMAZON, index 1 = NEW)
    let wasPrice90d = null;
    if (stats && stats.avg90) {
      const avg = stats.avg90[0] > 0 ? stats.avg90[0] : stats.avg90[1];
      if (avg > 0) wasPrice90d = avg / 100;
    }

    console.log(`  🔍 Keepa: "${name}" → £${price.toFixed(2)} | 90d avg: £${wasPrice90d?.toFixed(2) || 'n/a'} | Rank: ${salesRank || 'n/a'} (ASIN: ${product.asin})`);

    return {
      price,
      name,
      rrp: null,
      wasPrice90d,
      salesRank,
      source: 'keepa',
      asin: product.asin,
      fetched: Date.now()
    };
  }

  // ── Listing Extraction ─────────────────────────────────────────────
  function extractListings() {
    const listings = [];
    const seen = new Set();

    const itemLinks = document.querySelectorAll('a[href*="/items/"]');

    for (const link of itemLinks) {
      const href = link.getAttribute('href') || '';
      const idMatch = href.match(/\/items\/(\d+)/);
      if (!idMatch) continue;

      const id = idMatch[1];
      if (seen.has(id)) continue;
      seen.add(id);

      // Walk up to find the card that contains both link and price
      const card = findVintedCard(link);
      if (!card) continue;

      const info = extractVintedCardInfo(card);
      const url = href.startsWith('http') ? href : 'https://www.vinted.co.uk' + href;

      // Extract set numbers from URL slug
      const slugSetNums = extractSetNumbers(href);

      listings.push({ id, url, slugSetNums: slugSetNums.length > 0 ? slugSetNums : null, ...info });

      if (listings.length >= 40) break;
    }

    return listings;
  }

  function findVintedCard(link) {
    let el = link;
    for (let i = 0; i < 8; i++) {
      el = el.parentElement;
      if (!el) return null;
      // Found a container that has both an item link and a price element
      const hasPrice = el.querySelector('.title-content p, p');
      const hasLink = el.querySelector('a[href*="/items/"]');
      if (hasPrice && hasLink) {
        const priceText = hasPrice.textContent.trim();
        if (/^£[\d,.]+$/.test(priceText)) return el;
      }
    }
    // Fallback: go up 4 levels
    el = link;
    for (let i = 0; i < 4; i++) { if (el.parentElement) el = el.parentElement; }
    return el;
  }

  function extractVintedCardInfo(card) {
    const info = {
      title: '(untitled)', price: null, priceNum: null,
      condition: null, brand: null, imageUrl: null,
      priceWithFees: null, priceInclNum: null
    };

    // ── Base price — <p> with £ ──
    const allP = card.querySelectorAll('p');
    for (const p of allP) {
      const t = p.textContent.trim();
      const m = t.match(/^£([\d,.]+)$/);
      if (m) {
        info.price = t;
        info.priceNum = parseFloat(m[1].replace(/,/g, ''));
        break;
      }
    }

    // ── Price incl. fees — <span> with £ near "incl." ──
    const spans = card.querySelectorAll('span');
    for (const span of spans) {
      const t = span.textContent.trim();
      const m = t.match(/^£([\d,.]+)$/);
      if (m && span.parentElement?.textContent?.includes('incl.')) {
        info.priceWithFees = t;
        info.priceInclNum = parseFloat(m[1].replace(/,/g, ''));
        break;
      }
    }

    // Fallback: any element containing "£X.XX incl."
    if (!info.priceInclNum) {
      const allEls = card.querySelectorAll('span, p, div');
      for (const el of allEls) {
        if (el.children.length > 2) continue; // skip containers
        const t = el.textContent.trim();
        if (t.includes('incl.') && t.includes('£')) {
          const m = t.match(/£([\d,.]+)/);
          if (m) {
            info.priceWithFees = '£' + m[1];
            info.priceInclNum = parseFloat(m[1].replace(/,/g, ''));
            break;
          }
        }
      }
    }

    // ── Brand, Condition, Title from all text ──
    const textEls = card.querySelectorAll('p, span, a');
    const allText = [];
    for (const el of textEls) {
      const t = el.textContent.trim();
      if (t && t.length > 0 && t.length < 200 && !t.startsWith('£') && !t.includes('incl.')) {
        allText.push(t);
      }
    }

    for (const t of allText) {
      if (/^(LEGO|Lego)\b/.test(t) && t.length < 30 && !info.brand) {
        info.brand = t.trim();
      }
      if (/\b(New with tags|New without tags|Very good|Good|Satisfactory)\b/i.test(t) && !info.condition) {
        info.condition = t.trim();
      }
    }

    // Title: longest meaningful text
    let bestTitle = '';
    for (const t of allText) {
      if (t === info.brand || t === info.condition) continue;
      if (/^(LEGO|Bumped|Removed|Pro)$/i.test(t)) continue;
      if (t.length > bestTitle.length && t.length >= 3 && t.length <= 150) {
        bestTitle = t;
      }
    }
    if (bestTitle) info.title = bestTitle;

    // ── Image ──
    for (const img of card.querySelectorAll('img')) {
      const src = img.src || img.getAttribute('data-src') || '';
      if (src && src.startsWith('http')) {
        info.imageUrl = src;
        break;
      }
    }

    return info;
  }

  // ── Discord Webhook ────────────────────────────────────────────────
  async function sendToDiscord(listing, setNums, lookup, cog, cogPercent, dealTier) {
    if (!config.webhookUrl) return;

    // Use set name from Supabase if available
    const displayTitle = lookup.name || listing.title || '(untitled)';
    const safeTitle = displayTitle.replace(/\0/g, '').substring(0, 200);
    const fields = [];

    // Vinted price (base + incl. + postage = COG)
    if (listing.price) {
      let priceText = listing.price;
      if (listing.priceWithFees) priceText += ` (${listing.priceWithFees} incl.)`;
      priceText += ` + £${config.vintedPostage.toFixed(2)} post`;
      priceText += `\n**COG: £${cog.toFixed(2)}**`;
      fields.push({ name: '👗 Vinted (COG)', value: priceText, inline: true });
    }

    // Amazon price — include Keepa link if we have an ASIN
    const srcLabel = lookup.source === 'keepa' ? '🛒 Amazon (Keepa)' : '🛒 Amazon';
    let amazonValue = `£${lookup.price.toFixed(2)}`;
    if (lookup.asin) {
      amazonValue += `\n[Keepa](https://keepa.com/#!product/2-${lookup.asin})`;
    }
    fields.push({ name: srcLabel, value: amazonValue, inline: true });

    // UK RRP if available
    if (lookup.rrp) {
      fields.push({ name: '🏷️ UK RRP', value: `£${lookup.rrp.toFixed(2)}`, inline: true });
    }

    // 90-day average price
    if (lookup.wasPrice90d) {
      fields.push({ name: '📊 90d Avg', value: `£${lookup.wasPrice90d.toFixed(2)}`, inline: true });
    }

    // Sales rank
    if (lookup.salesRank) {
      const rankStr = lookup.salesRank.toLocaleString();
      fields.push({ name: '📈 Sales Rank', value: `#${rankStr}`, inline: true });
    }

    // Profit & Margin calculation
    // salePrice = Amazon price, cost = COG (Vinted incl. fees price)
    const salePrice = lookup.price;
    const fees = salePrice * 0.1836;
    const shipping = salePrice < 14 ? 3 : 4;
    const profit = salePrice - fees - shipping - cog;
    const marginPct = ((profit / salePrice) * 100).toFixed(1);
    const cogPctOfSale = ((cog / salePrice) * 100).toFixed(1);

    const profitEmoji = profit >= 0 ? '💰' : '🔻';
    fields.push({
      name: `${profitEmoji} Profit / Margin`,
      value: `Profit: **£${profit.toFixed(2)}** (${marginPct}%)\nCOG: ${cogPctOfSale}% | Fees: £${fees.toFixed(2)} | Ship: £${shipping}`,
      inline: false
    });

    // Deal tier indicator — show margin % as decision driver, COG % as context
    const tierEmoji = dealTier === 'green' ? '🟢' : '🟠';
    const tierLabel = dealTier === 'green' ? 'GREAT DEAL' : 'GOOD DEAL';
    fields.push({
      name: `${tierEmoji} ${tierLabel}`,
      value: `Margin: **${marginPct}%** | COG: ${cogPercent}% of Amazon`,
      inline: true
    });

    // Set numbers with Brickset links
    if (setNums.length > 0) {
      const links = setNums.map(n => `[${n}](https://brickset.com/sets/${n})`);
      fields.push({ name: '🧱 Set #', value: links.join(', '), inline: true });
    }

    if (listing.condition) fields.push({ name: 'Condition', value: listing.condition, inline: true });

    // Colour: green for < 40%, amber/gold for < 50%
    const color = dealTier === 'green' ? 3066993 : 15844367;

    const embed = {
      title: `${tierEmoji} ${safeTitle}`.substring(0, 256),
      url: listing.url,
      color,
      timestamp: new Date().toISOString(),
      footer: { text: 'Vinted Sniper' }
    };
    if (fields.length > 0) embed.fields = fields;
    if (listing.imageUrl?.startsWith('https') && listing.imageUrl.length < 2000) {
      embed.thumbnail = { url: listing.imageUrl };
    }

    try {
      const res = await fetch(config.webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ embeds: [embed] })
      });
      if (!res.ok) {
        const err = await res.text().catch(() => '');
        console.error(`[Vinted Sniper] Discord ${res.status}: ${err}`);
        if (embed.thumbnail) {
          delete embed.thumbnail;
          await fetch(config.webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ embeds: [embed] })
          });
        }
      } else {
        lastAlertTime = new Date();
        console.log(`[Vinted Sniper] → Discord: ${listing.id} | ${safeTitle} | COG £${cog} = ${cogPercent}% of Amazon £${lookup.price} | Profit £${profit.toFixed(2)} (${marginPct}%) | ${tierLabel}`);
      }
    } catch (e) {
      console.error('[Vinted Sniper] Discord error:', e);
    }
  }

  // ── Status Bar ─────────────────────────────────────────────────────
  function showStatusBar() {
    let bar = document.getElementById('vinted-sniper-status');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'vinted-sniper-status';
      Object.assign(bar.style, {
        position: 'fixed', bottom: '0', left: '0', right: '0', zIndex: '999999',
        padding: '6px 16px', fontSize: '12px', fontWeight: '500',
        fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
        background: 'rgba(22, 33, 62, 0.95)', color: '#a0aec0',
        borderTop: '1px solid #2d3748', display: 'flex',
        justifyContent: 'space-between', alignItems: 'center'
      });
      document.body.appendChild(bar);
    }
    updateStatusBar();
  }

  function updateStatusBar() {
    const bar = document.getElementById('vinted-sniper-status');
    if (!bar) return;

    const now = new Date();

    const lastStr = lastAlertTime ? lastAlertTime.toLocaleTimeString() : 'never';
    const cacheSize = Object.keys(priceCache).length;

    let refreshDisplay;
    if (isQuiet) {
      refreshDisplay = `<strong style="color:#a78bfa">😴 QUIET (${config.quietStart}:00-${config.quietEnd}:00)</strong>`;
    } else if (nextRefreshAt) {
      const nextRefresh = Math.max(0, Math.round((nextRefreshAt - Date.now()) / 1000));
      const nextStr = nextRefresh > 60
        ? `${Math.floor(nextRefresh / 60)}m ${nextRefresh % 60}s`
        : `${nextRefresh}s`;
      refreshDisplay = `<strong style="color:#f6e05e">${nextStr}</strong> <span style="color:#718096">(${config.refreshMinSecs}-${config.refreshMaxSecs}s)</span>`;
    } else {
      refreshDisplay = '<strong>—</strong>';
    }

    bar.innerHTML = `
      <span>👗 <strong style="color:#00b894">Vinted Sniper${isQuiet ? ' (Paused)' : ' Active'}</strong> —
        Page loaded: <strong>${lastRefreshTime.toLocaleTimeString()}</strong> |
        Scans: <strong>${scanCount}</strong> |
        Price cache: <strong>${cacheSize} sets</strong></span>
      <span>Last alert: <strong>${lastStr}</strong> |
        Next refresh: ${refreshDisplay}</span>
    `;
  }

  setInterval(updateStatusBar, 5000);

  // ── UI Banner ──────────────────────────────────────────────────────
  function showBanner(message, type) {
    const el = document.getElementById('vinted-sniper-banner');
    if (el) el.remove();
    const banner = document.createElement('div');
    banner.id = 'vinted-sniper-banner';
    banner.textContent = message;
    Object.assign(banner.style, {
      position: 'fixed', top: '8px', right: '8px', zIndex: '999999',
      padding: '10px 18px', borderRadius: '8px', fontSize: '13px',
      fontWeight: '600', fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      boxShadow: '0 4px 12px rgba(0,0,0,0.3)', transition: 'opacity 0.5s',
      background: type === 'ok' ? '#00b894' : '#7f4f24', color: '#fff'
    });
    document.body.appendChild(banner);
    setTimeout(() => { banner.style.opacity = '0'; setTimeout(() => banner.remove(), 600); }, 5000);
  }

  // ── Helpers ────────────────────────────────────────────────────────
  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36);
  }

})();
