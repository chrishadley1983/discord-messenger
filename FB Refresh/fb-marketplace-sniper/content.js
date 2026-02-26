/**
 * FB Marketplace Sniper — Content Script v2
 *
 * Monitors Facebook Marketplace search results for new listings.
 * - Finds /marketplace/item/ITEMID links in the grid
 * - Extracts price, title, location, condition, image from cards
 * - Detects sale/reduced prices
 * - Hash-based dedup to prevent re-sending
 * - Skips $ listings (non-UK)
 * - Status bar with scan count and refresh countdown
 * - Auto-refreshes page to catch new listings
 */

(function () {
  'use strict';

  const DEFAULT_WEBHOOK = 'https://discordapp.com/api/webhooks/1470092279585706089/efND5z6IviV06mM5L_Wv5GKEUzkIbDnIlGsMt5aK6cXimu2KrWpKvF1bEllFuu3kcSji';

  // ── State ──────────────────────────────────────────────────────────
  const seenListingIds = new Set();
  const sentHashes = new Set();
  let config = {
    webhookUrl: DEFAULT_WEBHOOK,
    minPrice: 0, maxPrice: 0,
    interval: 45, maxPosts: 5, refreshMinutes: 5
  };
  let isRunning = false;
  let pollTimer = null;
  let refreshTimer = null;
  let firstScanDone = false;
  let scanCount = 0;
  let lastRefreshTime = new Date();
  let lastAlertTime = null;

  // ── Init ───────────────────────────────────────────────────────────
  if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
    console.log('[MP Sniper] Extension context not available. Please refresh the page.');
    return;
  }

  chrome.storage.local.get(
    ['webhookUrl', 'minPrice', 'maxPrice', 'interval', 'maxPosts', 'refreshMinutes', 'seenListings', 'mpSentHashes'],
    data => {
      config.webhookUrl = data.webhookUrl || DEFAULT_WEBHOOK;
      config.minPrice = data.minPrice || 0;
      config.maxPrice = data.maxPrice || 0;
      config.interval = data.interval || 45;
      config.maxPosts = data.maxPosts || 5;
      config.refreshMinutes = data.refreshMinutes || 5;

      if (data.seenListings) data.seenListings.forEach(id => seenListingIds.add(id));
      if (data.mpSentHashes) data.mpSentHashes.forEach(h => sentHashes.add(h));

      if (!config.webhookUrl) {
        console.log('[MP Sniper] No webhook URL configured.');
        showBanner('⚙️ MP Sniper: No webhook URL set. Right-click extension → Options.', 'warn');
        return;
      }

      const priceFilter = config.minPrice || config.maxPrice
        ? ` Price: ${config.minPrice ? '£' + config.minPrice + '+' : ''} ${config.maxPrice ? '≤£' + config.maxPrice : ''}`
        : '';
      console.log(`[MP Sniper] Active. Poll: ${config.interval}s. Refresh: ${config.refreshMinutes}min.${priceFilter}`);
      showBanner(`🏪 MP Sniper active — poll ${config.interval}s, refresh ${config.refreshMinutes}min`, 'ok');
      showStatusBar();

      setTimeout(() => {
        startPolling();
        startAutoRefresh();
      }, 3000);
    }
  );

  // Settings changes
  if (chrome.storage?.onChanged) {
    chrome.storage.onChanged.addListener((changes) => {
      if (changes.webhookUrl) config.webhookUrl = changes.webhookUrl.newValue || DEFAULT_WEBHOOK;
      if (changes.minPrice) config.minPrice = changes.minPrice.newValue || 0;
      if (changes.maxPrice) config.maxPrice = changes.maxPrice.newValue || 0;
      if (changes.interval) {
        config.interval = changes.interval.newValue || 45;
        if (isRunning) { stopPolling(); startPolling(); }
      }
      if (changes.maxPosts) config.maxPosts = changes.maxPosts.newValue || 5;
      if (changes.refreshMinutes) {
        config.refreshMinutes = changes.refreshMinutes.newValue || 5;
        startAutoRefresh();
      }
    });
  }

  // ── Polling ────────────────────────────────────────────────────────
  function startPolling() {
    if (isRunning) return;
    isRunning = true;
    scan();
    pollTimer = setInterval(scan, config.interval * 1000);
  }

  function stopPolling() {
    isRunning = false;
    if (pollTimer) clearInterval(pollTimer);
  }

  // Scroll disabled for marketplace — the auto-refresh catches new listings
  // Scrolling causes Facebook to pad results with unrelated items
  function maybeScroll() {
    // no-op
  }

  // ── Auto Refresh ───────────────────────────────────────────────────
  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    const ms = config.refreshMinutes * 60 * 1000;
    refreshTimer = setInterval(() => {
      console.log('[MP Sniper] Auto-refreshing page...');
      saveState(() => window.location.reload());
    }, ms);
  }

  function saveState(callback) {
    if (chrome.storage?.local) {
      chrome.storage.local.set({
        seenListings: [...seenListingIds].slice(-1000),
        mpSentHashes: [...sentHashes].slice(-500)
      }, callback);
    } else if (callback) callback();
  }

  // ── Scanning ───────────────────────────────────────────────────────
  function scan() {
    scanCount++;
    maybeScroll();
    const listings = extractListings();
    const newListings = [];

    for (const listing of listings) {
      if (!listing.id || seenListingIds.has(listing.id)) continue;
      seenListingIds.add(listing.id);

      // Content hash dedup
      const contentHash = hashCode(listing.title + (listing.price || ''));
      if (sentHashes.has(contentHash)) continue;

      // Skip $ listings (non-UK)
      if (listing.price && listing.price.includes('$')) continue;

      // Price filters
      if (listing.priceNum !== null && listing.priceNum !== undefined) {
        if (config.minPrice && listing.priceNum < config.minPrice) continue;
        if (config.maxPrice && listing.priceNum > config.maxPrice) continue;
      }

      newListings.push({ ...listing, contentHash });
    }

    if (!firstScanDone) {
      firstScanDone = true;
      // Seed all current listings as seen — only alert on NEW ones after refresh
      console.log(`[MP Sniper] First scan: ${seenListingIds.size} listings seeded. Sending top 3 as preview.`);
      const preview = newListings.slice(0, 3);
      for (const listing of preview) {
        sentHashes.add(listing.contentHash);
        sendToDiscord(listing);
      }
      saveState();
      return;
    }

    if (newListings.length === 0) return;

    const toAlert = newListings.slice(0, config.maxPosts);
    console.log(`[MP Sniper] ${toAlert.length} new listing(s)!`);

    for (const listing of toAlert) {
      sentHashes.add(listing.contentHash);
      sendToDiscord(listing);
    }
    saveState();
  }

  // ── Listing Extraction ─────────────────────────────────────────────
  function extractListings() {
    const listings = [];
    const seenThisScan = new Set();
    const seenContainers = new Set();

    const itemLinks = document.querySelectorAll('a[href*="/marketplace/item/"]');

    for (const link of itemLinks) {
      const href = link.getAttribute('href') || '';
      const idMatch = href.match(/\/marketplace\/item\/(\d+)/);
      if (!idMatch) continue;

      const listingId = idMatch[1];
      if (seenThisScan.has(listingId)) continue;
      seenThisScan.add(listingId);

      const card = findCardContainer(link);
      if (card && seenContainers.has(card)) continue;
      if (card) seenContainers.add(card);

      const info = extractCardInfo(card || link);
      const listingUrl = 'https://www.facebook.com/marketplace/item/' + listingId + '/';

      listings.push({ id: listingId, url: listingUrl, ...info });

      // Only process first 20 listings (visible on screen) to avoid Facebook's junk padding
      if (listings.length >= 20) break;
    }

    return listings;
  }

  function findCardContainer(element) {
    let el = element;
    for (let i = 0; i < 10; i++) {
      if (!el.parentElement) return el;
      el = el.parentElement;
      const rect = el.getBoundingClientRect();
      if (rect.width > 150 && rect.height > 200 && rect.height < 800) {
        const parentRect = el.parentElement?.getBoundingClientRect();
        if (parentRect && parentRect.width > rect.width * 1.5) return el;
      }
    }
    return el;
  }

  function extractCardInfo(card) {
    const info = {
      title: '(untitled)', price: null, priceNum: null,
      location: null, imageUrl: null, condition: null,
      originalPrice: null, discount: null
    };

    const textElements = card.querySelectorAll('span, div[dir="auto"]');
    const texts = [];
    for (const el of textElements) {
      const t = el.textContent.trim();
      if (t && t.length > 0 && t.length < 200) texts.push(t);
    }

    // ── Price ──
    for (const t of texts) {
      if (/^[£$€]\s*[\d,]+\.?\d*$/.test(t)) {
        info.price = t.trim();
        info.priceNum = parseFloat(t.replace(/[^0-9.]/g, ''));
        break;
      }
      if (/^free$/i.test(t.trim())) {
        info.price = 'Free';
        info.priceNum = 0;
        break;
      }
    }

    // Sale/reduced prices
    for (let i = 0; i < texts.length - 1; i++) {
      const current = texts[i].match(/^[£$€]\s*([\d,]+\.?\d*)$/);
      const next = texts[i + 1].match(/^[£$€]\s*([\d,]+\.?\d*)$/);
      if (current && next) {
        const p1 = parseFloat(current[1].replace(/,/g, ''));
        const p2 = parseFloat(next[1].replace(/,/g, ''));
        if (p1 < p2) {
          info.price = texts[i].trim();
          info.priceNum = p1;
          info.originalPrice = texts[i + 1].trim();
          info.discount = Math.round((1 - p1 / p2) * 100) + '% off';
        }
        break;
      }
    }

    // Fallback price
    if (!info.price) {
      for (const t of texts) {
        const m = t.match(/[£$€]\s*[\d,]+\.?\d*/);
        if (m) {
          info.price = m[0].trim();
          info.priceNum = parseFloat(m[0].replace(/[^0-9.]/g, ''));
          break;
        }
      }
    }

    // ── Title ──
    let bestTitle = '';
    for (const t of texts) {
      if (t === info.price || t === info.originalPrice) continue;
      if (t.length > bestTitle.length && t.length >= 5 && t.length <= 150) {
        if (/^(listed|sponsored|see\s*more|hide|report)/i.test(t)) continue;
        bestTitle = t;
      }
    }
    if (bestTitle) info.title = bestTitle;

    // ── Location ──
    for (const t of texts) {
      if (t === info.price || t === info.title) continue;
      if (/\b(?:miles?\s+away|km\s+away|listed\s+in|collection)\b/i.test(t)) {
        info.location = t.trim();
        break;
      }
      if (t.length >= 3 && t.length <= 50 && !/^[£$€]/.test(t) && t !== info.title) {
        if (t.includes(',') || /^[A-Z][a-z]+/.test(t)) info.location = t.trim();
      }
    }

    // ── Condition ──
    for (const t of texts) {
      const lower = t.toLowerCase();
      if (/\b(?:new|sealed|bnib|brand\s*new)\b/.test(lower)) { info.condition = '🟢 New'; break; }
      if (/\b(?:like\s*new|used\s*-\s*like\s*new)\b/.test(lower)) { info.condition = '🟡 Like New'; break; }
      if (/\b(?:good\s*condition|used\s*-\s*good)\b/.test(lower)) { info.condition = '🟠 Good'; break; }
      if (/\b(?:fair|used\s*-\s*fair)\b/.test(lower)) { info.condition = '🔴 Fair'; break; }
    }

    // ── Image ──
    for (const img of card.querySelectorAll('img')) {
      const src = img.src || '';
      const w = img.naturalWidth || img.width || 0;
      if ((w > 100 || src.includes('scontent')) && !src.includes('emoji') && !src.includes('profile')) {
        info.imageUrl = src;
        break;
      }
    }

    return info;
  }

  // ── Discord Webhook ────────────────────────────────────────────────
  async function sendToDiscord(listing) {
    if (!config.webhookUrl) return;

    const safeTitle = (listing.title || '(untitled)').replace(/\0/g, '').substring(0, 200);
    const fields = [];

    if (listing.price) {
      let priceText = listing.price;
      if (listing.originalPrice) priceText += ` ~~${listing.originalPrice}~~`;
      fields.push({ name: '💷 Price', value: priceText, inline: true });
    }
    if (listing.discount) fields.push({ name: '🏷️ Sale', value: listing.discount, inline: true });
    if (listing.condition) fields.push({ name: 'Condition', value: listing.condition, inline: true });
    if (listing.location) fields.push({ name: '📍 Location', value: listing.location.substring(0, 100), inline: true });

    // Lego set numbers from title
    const setMatches = safeTitle.match(/\b(\d{4,6})\b/g);
    if (setMatches) {
      const setNums = [...new Set(setMatches)].slice(0, 3);
      const setLinks = setNums.map(n => `[${n}](https://brickset.com/sets/${n})`);
      fields.push({ name: '🧱 Set #', value: setLinks.join(', '), inline: true });
    }

    let color = 15844367;
    if (listing.priceNum === 0) color = 3066993;
    else if (listing.priceNum && listing.priceNum <= 20) color = 3066993;
    else if (listing.priceNum && listing.priceNum <= 100) color = 15844367;
    else if (listing.priceNum && listing.priceNum > 100) color = 10038562;

    const embed = {
      title: `🏪 ${safeTitle}`.substring(0, 256),
      url: listing.url,
      color,
      timestamp: new Date().toISOString(),
      footer: { text: 'FB Marketplace Sniper' }
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
        console.error(`[MP Sniper] Discord ${res.status}: ${err}`);
        if (embed.thumbnail) {
          delete embed.thumbnail;
          const retry = await fetch(config.webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ embeds: [embed] })
          });
          if (retry.ok) console.log(`[MP Sniper] → Discord (no thumb): ${listing.id} | ${safeTitle}`);
          else console.error(`[MP Sniper] Retry failed: ${retry.status}`);
        }
      } else {
        lastAlertTime = new Date();
        console.log(`[MP Sniper] → Discord: ${listing.id} | ${safeTitle} | ${listing.price || 'no price'}`);
      }
    } catch (e) {
      console.error('[MP Sniper] Discord error:', e);
    }
  }

  // ── Status Bar ─────────────────────────────────────────────────────
  function showStatusBar() {
    let bar = document.getElementById('mp-sniper-status');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'mp-sniper-status';
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
    const bar = document.getElementById('mp-sniper-status');
    if (!bar) return;

    const now = new Date();
    const refreshAge = Math.round((now - lastRefreshTime) / 1000);
    const nextRefresh = Math.max(0, config.refreshMinutes * 60 - refreshAge);
    const nextStr = nextRefresh > 60
      ? `${Math.floor(nextRefresh / 60)}m ${nextRefresh % 60}s`
      : `${nextRefresh}s`;

    const lastStr = lastAlertTime ? lastAlertTime.toLocaleTimeString() : 'never';
    const priceStr = config.minPrice || config.maxPrice
      ? ` | Filter: ${config.minPrice ? '£' + config.minPrice + '+' : ''} ${config.maxPrice ? '≤£' + config.maxPrice : ''}`
      : '';

    bar.innerHTML = `
      <span>🏪 <strong style="color:#48bb78">MP Sniper Active</strong> —
        Page loaded: <strong>${lastRefreshTime.toLocaleTimeString()}</strong> |
        Scans: <strong>${scanCount}</strong> |
        Seen: <strong>${seenListingIds.size}</strong>${priceStr}</span>
      <span>Last alert: <strong>${lastStr}</strong> |
        Next refresh: <strong style="color:#f6e05e">${nextStr}</strong></span>
    `;
  }

  setInterval(updateStatusBar, 5000);

  // ── UI Banner ──────────────────────────────────────────────────────
  function showBanner(message, type) {
    const el = document.getElementById('mp-sniper-banner');
    if (el) el.remove();
    const banner = document.createElement('div');
    banner.id = 'mp-sniper-banner';
    banner.textContent = message;
    Object.assign(banner.style, {
      position: 'fixed', top: '8px', right: '8px', zIndex: '999999',
      padding: '10px 18px', borderRadius: '8px', fontSize: '13px',
      fontWeight: '600', fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      boxShadow: '0 4px 12px rgba(0,0,0,0.3)', transition: 'opacity 0.5s',
      background: type === 'ok' ? '#2d6a4f' : '#7f4f24', color: '#fff'
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
