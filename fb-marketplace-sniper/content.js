/**
 * FB Marketplace Sniper — Content Script
 * 
 * Monitors Facebook Marketplace search results for new listings.
 * Extracts listing info (title, price, location, image) from the grid cards.
 * Sends structured Discord notifications via webhook.
 * Auto-refreshes the page periodically to pick up new listings.
 * 
 * Marketplace listings are rendered as cards in a grid/list.
 * Each card links to /marketplace/item/ITEMID/ and contains:
 *   - Title text
 *   - Price text
 *   - Location text
 *   - Thumbnail image
 */

(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────
  const seenListingIds = new Set();
  let config = {
    webhookUrl: '', minPrice: 0, maxPrice: 0,
    interval: 45, maxPosts: 5, refreshMinutes: 5
  };
  let isRunning = false;
  let pollTimer = null;
  let refreshTimer = null;
  let firstScanDone = false;

  // ── Init ───────────────────────────────────────────────────────────
  chrome.storage.local.get(
    ['webhookUrl', 'minPrice', 'maxPrice', 'interval', 'maxPosts', 'refreshMinutes', 'seenListings'],
    data => {
      config.webhookUrl = data.webhookUrl || '';
      config.minPrice = data.minPrice || 0;
      config.maxPrice = data.maxPrice || 0;
      config.interval = data.interval || 45;
      config.maxPosts = data.maxPosts || 5;
      config.refreshMinutes = data.refreshMinutes || 5;

      if (data.seenListings) {
        data.seenListings.forEach(id => seenListingIds.add(id));
      }

      if (!config.webhookUrl) {
        console.log('[MP Sniper] No webhook URL configured. Right-click extension → Options to set up.');
        showBanner('⚙️ MP Sniper: No webhook URL set. Right-click extension icon → Options.', 'warn');
        return;
      }

      const priceFilter = config.minPrice || config.maxPrice
        ? ` Price filter: ${config.minPrice ? '£' + config.minPrice + '+' : ''} ${config.maxPrice ? '≤ £' + config.maxPrice : ''}`
        : '';
      console.log(`[MP Sniper] Active. Polling every ${config.interval}s. Refresh every ${config.refreshMinutes}min.${priceFilter}`);
      showBanner(`🏪 MP Sniper active — polling every ${config.interval}s, refresh every ${config.refreshMinutes}min`, 'ok');

      // Scroll down to load more listings before first scan
      loadMoreListings(() => {
        startPolling();
        startAutoRefresh();
      });
    }
  );

  // Listen for settings changes
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.webhookUrl) config.webhookUrl = changes.webhookUrl.newValue || '';
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

  // ── Auto Refresh ───────────────────────────────────────────────────
  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    const ms = config.refreshMinutes * 60 * 1000;
    refreshTimer = setInterval(() => {
      console.log('[MP Sniper] Auto-refreshing page...');
      const idsArray = [...seenListingIds].slice(-1000);
      chrome.storage.local.set({ seenListings: idsArray }, () => {
        window.location.reload();
      });
    }, ms);
  }

  // ── Scanning ───────────────────────────────────────────────────────
  let scanRetries = 0;

  function scan() {
    const listings = extractListings();
    const newListings = [];

    for (const listing of listings) {
      if (!listing.id || seenListingIds.has(listing.id)) continue;
      seenListingIds.add(listing.id);

      // Price filters
      if (listing.priceNum !== null && listing.priceNum !== undefined) {
        if (config.minPrice && listing.priceNum < config.minPrice) continue;
        if (config.maxPrice && listing.priceNum > config.maxPrice) continue;
      }

      newListings.push(listing);
    }

    // On first scan, send the most recent 5 as a test, then mark as done
    if (!firstScanDone) {
      if (newListings.length === 0 && seenListingIds.size === 0 && scanRetries < 5) {
        scanRetries++;
        console.log(`[MP Sniper] First scan found 0 listings. Retry ${scanRetries}/5 in next cycle...`);
        return;
      }
      firstScanDone = true;
      const initial = newListings.slice(0, 5);
      console.log(`[MP Sniper] First scan: ${seenListingIds.size} listings found. Sending ${initial.length} most recent to Discord as preview.`);
      for (const listing of initial) {
        sendToDiscord(listing);
      }
      const idsArray = [...seenListingIds].slice(-1000);
      chrome.storage.local.set({ seenListings: idsArray });
      return;
    }

    if (newListings.length === 0) return;

    const toAlert = newListings.slice(0, config.maxPosts);
    console.log(`[MP Sniper] ${toAlert.length} new listing(s) found!`);

    for (const listing of toAlert) {
      sendToDiscord(listing);
    }

    const idsArray = [...seenListingIds].slice(-1000);
    chrome.storage.local.set({ seenListings: idsArray });
  }

  // ── Listing Extraction ─────────────────────────────────────────────
  function extractListings() {
    const listings = [];
    const seenThisScan = new Set();

    // Strategy 1: Find all links to /marketplace/item/
    const itemLinks = document.querySelectorAll('a[href*="/marketplace/item/"]');

    for (const link of itemLinks) {
      const href = link.getAttribute('href') || '';
      const idMatch = href.match(/\/marketplace\/item\/(\d+)/);
      if (!idMatch) continue;

      const listingId = idMatch[1];
      if (seenThisScan.has(listingId)) continue;
      seenThisScan.add(listingId);

      // The link itself or its parent is usually the card container
      const card = findCardContainer(link);
      const info = extractCardInfo(card || link);

      const listingUrl = 'https://www.facebook.com/marketplace/item/' + listingId + '/';

      listings.push({
        id: listingId,
        url: listingUrl,
        ...info
      });
    }

    return listings;
  }

  function findCardContainer(element) {
    // Walk up to find the card — usually a container with a reasonable size
    let el = element;
    for (let i = 0; i < 10; i++) {
      if (!el.parentElement) return el;
      el = el.parentElement;

      // Cards are typically square-ish boxes, 200-500px
      const rect = el.getBoundingClientRect();
      if (rect.width > 150 && rect.height > 200 && rect.height < 800) {
        // Check if parent is significantly larger (meaning we found the card boundary)
        const parentRect = el.parentElement?.getBoundingClientRect();
        if (parentRect && parentRect.width > rect.width * 1.5) {
          return el;
        }
      }
    }
    return el;
  }

  function extractCardInfo(card) {
    const info = {
      title: '(untitled)',
      price: null,
      priceNum: null,
      location: null,
      imageUrl: null,
      condition: null
    };

    // ── Get all text nodes ──
    const textElements = card.querySelectorAll('span, div[dir="auto"]');
    const texts = [];
    for (const el of textElements) {
      const t = el.textContent.trim();
      if (t && t.length > 0 && t.length < 200) {
        texts.push(t);
      }
    }

    // ── Price ──
    // Marketplace prices are usually the first prominent text, formatted as £XX or "Free"
    // Also detect sale prices where original price is shown struck through
    for (const t of texts) {
      // Match currency amounts
      const priceMatch = t.match(/^[£$€]\s*[\d,]+\.?\d*$/);
      if (priceMatch) {
        info.price = t.trim();
        info.priceNum = parseFloat(t.replace(/[^0-9.]/g, ''));
        break;
      }
      // Match "Free" listing
      if (/^free$/i.test(t.trim())) {
        info.price = 'Free';
        info.priceNum = 0;
        break;
      }
    }

    // Check for sale/reduced prices (e.g. "£30 £40" where £40 is the original)
    // These appear as two price elements next to each other
    for (let i = 0; i < texts.length - 1; i++) {
      const current = texts[i].match(/^[£$€]\s*([\d,]+\.?\d*)$/);
      const next = texts[i + 1].match(/^[£$€]\s*([\d,]+\.?\d*)$/);
      if (current && next) {
        const price1 = parseFloat(current[1].replace(/,/g, ''));
        const price2 = parseFloat(next[1].replace(/,/g, ''));
        // Lower price first = sale price, higher = original
        if (price1 < price2) {
          info.price = texts[i].trim();
          info.priceNum = price1;
          info.originalPrice = texts[i + 1].trim();
          info.discount = Math.round((1 - price1 / price2) * 100) + '% off';
        }
        break;
      }
    }

    // If no clean match, try finding price anywhere in text
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
    // Title is usually the longest meaningful text that isn't the price or location
    let bestTitle = '';
    for (const t of texts) {
      if (t === info.price) continue;
      if (t.length > bestTitle.length && t.length >= 5 && t.length <= 150) {
        // Skip things that look like UI text
        if (/^(listed|sponsored|see\s*more|hide|report)/i.test(t)) continue;
        bestTitle = t;
      }
    }
    if (bestTitle) info.title = bestTitle;

    // ── Location ──
    // Location is usually a shorter text near the bottom of the card
    // Often contains city/town names or distance info
    for (const t of texts) {
      if (t === info.price || t === info.title) continue;
      // Look for location-like text: "City, County" or "Listed X ago in City"
      if (/\b(?:miles?\s+away|km\s+away|listed\s+in|collection)\b/i.test(t)) {
        info.location = t.trim();
        break;
      }
      // Short text that looks like a place name (not price, not title)
      if (t.length >= 3 && t.length <= 50 && !/^[£$€]/.test(t) && t !== info.title) {
        // Could be location — check if it contains a comma (City, Area pattern)
        if (t.includes(',') || /^[A-Z][a-z]+/.test(t)) {
          info.location = t.trim();
          // Don't break — keep looking for better match
        }
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
    const imgs = card.querySelectorAll('img');
    for (const img of imgs) {
      const src = img.src || '';
      const w = img.naturalWidth || img.width || 0;
      // Marketplace thumbnails are typically decent sized
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

    const fields = [];

    if (listing.price) {
      let priceText = listing.price;
      if (listing.originalPrice) {
        priceText += ` ~~${listing.originalPrice}~~`;
      }
      fields.push({ name: '💷 Price', value: priceText, inline: true });
    }

    if (listing.discount) {
      fields.push({ name: '🏷️ Sale', value: listing.discount, inline: true });
    }

    if (listing.condition) {
      fields.push({ name: 'Condition', value: listing.condition, inline: true });
    }

    if (listing.location) {
      fields.push({ name: '📍 Location', value: listing.location, inline: true });
    }

    // Try to extract Lego set numbers from title
    const setMatches = listing.title.match(/\b(\d{4,6})\b/g);
    if (setMatches) {
      const setNums = [...new Set(setMatches)].slice(0, 3);
      const setLinks = setNums.map(n => `[${n}](https://brickset.com/sets/${n})`);
      fields.push({ name: '🧱 Set #', value: setLinks.join(', '), inline: true });
    }

    // Colour by price
    let color = 15844367; // gold default
    if (listing.priceNum === 0) color = 3066993;        // green for free
    else if (listing.priceNum && listing.priceNum <= 20) color = 3066993;   // green for cheap
    else if (listing.priceNum && listing.priceNum <= 100) color = 15844367; // gold for mid
    else if (listing.priceNum && listing.priceNum > 100) color = 10038562;  // orange for pricey

    const embed = {
      title: `🏪 ${listing.title}`,
      url: listing.url,
      color: color,
      fields: fields.length > 0 ? fields : undefined,
      timestamp: new Date().toISOString(),
      footer: { text: 'FB Marketplace Sniper' }
    };

    if (listing.imageUrl) {
      embed.thumbnail = { url: listing.imageUrl };
    }

    try {
      await fetch(config.webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ embeds: [embed] })
      });
      console.log(`[MP Sniper] → Discord: ${listing.id} | ${listing.title} | ${listing.price || 'no price'}`);
    } catch (e) {
      console.error('[MP Sniper] Discord send failed:', e);
    }
  }

  // ── UI Banner ──────────────────────────────────────────────────────
  function showBanner(message, type) {
    const existing = document.getElementById('mp-sniper-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'mp-sniper-banner';
    banner.textContent = message;
    Object.assign(banner.style, {
      position: 'fixed',
      top: '8px',
      right: '8px',
      zIndex: '999999',
      padding: '10px 18px',
      borderRadius: '8px',
      fontSize: '13px',
      fontWeight: '600',
      fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
      transition: 'opacity 0.5s',
      background: type === 'ok' ? '#2d6a4f' : '#7f4f24',
      color: '#fff'
    });

    document.body.appendChild(banner);

    setTimeout(() => {
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 600);
    }, 5000);
  }

  // ── Load More Listings (scroll to trigger Facebook's lazy loading) ──
  function loadMoreListings(callback) {
    console.log('[MP Sniper] Scrolling to load more listings...');
    let scrollCount = 0;
    const maxScrolls = 4;
    const scrollInterval = setInterval(() => {
      window.scrollBy(0, window.innerHeight * 2);
      scrollCount++;
      if (scrollCount >= maxScrolls) {
        clearInterval(scrollInterval);
        console.log('[MP Sniper] Scroll complete. Waiting for listings to render...');
        setTimeout(() => {
          window.scrollTo(0, 0);
          setTimeout(callback, 2000);
        }, 3000);
      }
    }, 2000);
  }

})();
