/**
 * FB Group Sniper — Content Script v3
 * 
 * Timestamp-based approach:
 * - Extracts posts from role="article" elements (skipping comments)
 * - Parses relative timestamps ("3m", "1h", "Just now") into epoch ms
 * - Stores the newest post timestamp per group
 * - Only alerts on posts newer than the last one sent
 * - Sends rich deal info to Discord (price, set #, condition, location)
 * - Auto-refreshes page to keep feed fresh
 */

(function () {
  'use strict';

  const DEFAULT_WEBHOOK = 'https://discordapp.com/api/webhooks/1470092279585706089/efND5z6IviV06mM5L_Wv5GKEUzkIbDnIlGsMt5aK6cXimu2KrWpKvF1bEllFuu3kcSji';

  // ── State ──────────────────────────────────────────────────────────
  let config = {
    webhookUrl: DEFAULT_WEBHOOK,
    keywords: '', interval: 45, maxPosts: 5, refreshMinutes: 7
  };
  let isRunning = false;
  let pollTimer = null;
  let refreshTimer = null;
  let firstScanDone = false;
  let lastSentTimestamp = 0; // epoch ms of the newest post we've sent
  const sentPostHashes = new Set(); // content hashes of posts we've already sent

  // Group ID from URL for per-group storage
  const groupId = window.location.pathname.match(/\/groups\/([^/]+)/)?.[1] || 'unknown';
  const storageKey = `lastSent_${groupId}`;
  const hashesKey = `sentHashes_${groupId}`;

  // ── Init ───────────────────────────────────────────────────────────
  if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
    console.log('[FB Sniper] Extension context not available. Please refresh the page.');
    return;
  }

  chrome.storage.local.get(['webhookUrl', 'keywords', 'interval', 'maxPosts', 'refreshMinutes', storageKey, hashesKey], data => {
    config.webhookUrl = data.webhookUrl || DEFAULT_WEBHOOK;
    config.keywords = data.keywords || '';
    config.interval = data.interval || 45;
    config.maxPosts = data.maxPosts || 5;
    config.refreshMinutes = data.refreshMinutes || 7;
    lastSentTimestamp = data[storageKey] || 0;
    if (data[hashesKey]) {
      data[hashesKey].forEach(h => sentPostHashes.add(h));
    }

    if (!config.webhookUrl) {
      console.log('[FB Sniper] No webhook URL configured.');
      showBanner('⚙️ FB Sniper: No webhook URL set. Right-click extension → Options.', 'warn');
      return;
    }

    const lastSentInfo = lastSentTimestamp
      ? `Last sent: ${new Date(lastSentTimestamp).toLocaleTimeString()}`
      : 'No history';
    console.log(`[FB Sniper] Active on group "${groupId}". Poll: ${config.interval}s. Refresh: ${config.refreshMinutes}min. ${lastSentInfo}. Keywords: ${config.keywords || '(all)'}`);
    showBanner(`🧱 FB Sniper active — poll ${config.interval}s, refresh ${config.refreshMinutes}min`, 'ok');
    showStatusBar();

    // Wait for page to settle, then start
    setTimeout(() => {
      startPolling();
      startAutoRefresh();
    }, 3000);
  });

  // Settings changes
  if (chrome.storage?.onChanged) {
    chrome.storage.onChanged.addListener((changes) => {
      if (changes.webhookUrl) config.webhookUrl = changes.webhookUrl.newValue || DEFAULT_WEBHOOK;
      if (changes.keywords) config.keywords = changes.keywords.newValue || '';
      if (changes.interval) {
        config.interval = changes.interval.newValue || 45;
        if (isRunning) { stopPolling(); startPolling(); }
      }
      if (changes.maxPosts) config.maxPosts = changes.maxPosts.newValue || 5;
      if (changes.refreshMinutes) {
        config.refreshMinutes = changes.refreshMinutes.newValue || 7;
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

  // Periodic scroll to trigger lazy loading
  let pollCount = 0;
  function maybeScroll() {
    pollCount++;
    if (pollCount % 3 === 0) {
      const y = window.scrollY;
      window.scrollBy(0, window.innerHeight * 3);
      setTimeout(() => window.scrollTo(0, y), 2000);
    }
  }

  // ── Auto Refresh ───────────────────────────────────────────────────
  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    const ms = config.refreshMinutes * 60 * 1000;
    refreshTimer = setInterval(() => {
      console.log('[FB Sniper] Auto-refreshing page...');
      saveState(() => window.location.reload());
    }, ms);
  }

  function saveState(callback) {
    if (chrome.storage?.local) {
      const data = {};
      data[storageKey] = lastSentTimestamp;
      // Keep last 200 hashes to avoid unbounded growth
      data[hashesKey] = [...sentPostHashes].slice(-200);
      chrome.storage.local.set(data, callback);
    } else if (callback) {
      callback();
    }
  }

  // ── Scanning ───────────────────────────────────────────────────────
  function scan() {
    scanCount++;
    maybeScroll();
    const posts = extractPosts();

    if (posts.length === 0) {
      if (!firstScanDone) {
        console.log('[FB Sniper] No posts found yet, waiting...');
      }
      return;
    }

    // Sort by timestamp descending (newest first)
    posts.sort((a, b) => b.timestamp - a.timestamp);

    // Filter: skip posts we've already sent (by content hash)
    // skip group description text, posts with no price, and $ listings
    let newPosts = posts.filter(p => {
      const contentHash = hashCode((p.author || '') + (p.text || '').substring(0, 150));
      if (sentPostHashes.has(contentHash)) return false;
      // Skip group about/description text
      if (p.text.includes('This group has been created') || 
          p.text.includes('Welcome to') ||
          p.text.includes('Group designed to help') ||
          p.text.includes('community of') ||
          p.text.startsWith('Posts of your')) return false;
      // Skip posts with no pricing — likely questions or requests
      if (!p.prices || p.prices.length === 0) return false;
      // Skip $ listings — these are from non-UK sellers
      if (p.prices.some(price => price.includes('$'))) return false;
      return true;
    });

    // Keyword filter
    if (config.keywords) {
      const kws = config.keywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean);
      newPosts = newPosts.filter(p => {
        const text = (p.text + ' ' + p.author).toLowerCase();
        return kws.some(kw => text.includes(kw));
      });
    }

    if (!firstScanDone) {
      firstScanDone = true;
      const preview = newPosts.slice(0, 5);
      console.log(`[FB Sniper] First scan: ${posts.length} posts, ${newPosts.length} new. Sending ${preview.length} as preview.`);

      for (const post of preview) {
        const contentHash = hashCode((post.author || '') + (post.text || '').substring(0, 150));
        sentPostHashes.add(contentHash);
        sendToDiscord(post);
      }
      if (preview.length > 0) {
        lastSentTimestamp = Math.max(...preview.map(p => p.timestamp));
        saveState();
      }
      return;
    }

    if (newPosts.length === 0) return;

    const toAlert = newPosts.slice(0, config.maxPosts);
    console.log(`[FB Sniper] ${toAlert.length} new post(s)!`);

    for (const post of toAlert) {
      const contentHash = hashCode((post.author || '') + (post.text || '').substring(0, 150));
      sentPostHashes.add(contentHash);
      sendToDiscord(post);
    }

    lastSentTimestamp = Math.max(...toAlert.map(p => p.timestamp));
    saveState();
  }

  // ── Post Extraction ────────────────────────────────────────────────
  function extractPosts() {
    const posts = [];
    const seen = new Set();

    // Strategy 1: Find post links and walk up to container
    const linkSelectors = [
      'a[href*="/groups/"][href*="/posts/"]',
      'a[href*="/permalink/"]',
      'a[href*="/p/"]',
      'a[href*="story_fbid"]',
      'a[href*="multi_permalinks"]'
    ];

    const seenContainers = new Set(); // deduplicate by container DOM element

    for (const selector of linkSelectors) {
      const links = document.querySelectorAll(selector);
      for (const link of links) {
        const href = link.getAttribute('href') || '';
        const idMatch = href.match(/\/(?:posts|permalink|p)\/(\d+)/)
          || href.match(/story_fbid=(\d+)/)
          || href.match(/multi_permalinks=(\d+)/);
        if (!idMatch) continue;

        const container = findPostContainer(link);
        if (!container) continue;

        // Skip if we've already processed this container element
        if (seenContainers.has(container)) continue;
        seenContainers.add(container);

        const postId = idMatch[1];
        if (seen.has(postId)) continue;
        seen.add(postId);

        // Skip if container text is too short (likely a comment or UI element)
        const containerText = container.innerText || '';
        if (containerText.length < 15) continue;

        const author = extractAuthor(container);
        const text = extractPostText(container);
        const timeStr = extractTimeString(container);
        const timestamp = parseRelativeTime(timeStr);
        const postUrl = href.startsWith('http') ? href.split('?')[0] : 'https://www.facebook.com' + href.split('?')[0];
        const imageUrl = extractImage(container);
        const imageCount = countImages(container);
        const deal = parseDealInfo(text);

        posts.push({
          id: postId, author: author || 'Unknown', text: text || '(no text)',
          timeStr: timeStr || '', timestamp, url: postUrl,
          imageUrl, imageCount, ...deal
        });
      }
    }

    // Strategy 2: role="article" elements (skip comments)
    if (posts.length === 0) {
      const articles = document.querySelectorAll('[role="article"]');
      for (const article of articles) {
        if (article.parentElement?.closest('[role="article"]')) continue;

        const author = extractAuthor(article);
        const text = extractPostText(article);
        if (!author && !text) continue;

        const timeStr = extractTimeString(article);
        const timestamp = parseRelativeTime(timeStr);
        const id = 'art_' + hashCode((author || '') + (text || '').substring(0, 80));
        if (seen.has(id)) continue;
        seen.add(id);

        const postUrl = extractPostUrl(article);
        const imageUrl = extractImage(article);
        const imageCount = countImages(article);
        const deal = parseDealInfo(text);

        posts.push({
          id, author: author || 'Unknown', text: text || '(no text)',
          timeStr: timeStr || '', timestamp, url: postUrl,
          imageUrl, imageCount, ...deal
        });
      }
    }

    // Strategy 3: Content-based — find div[dir="auto"] with substantial text
    // and walk up to find the post boundary
    if (posts.length === 0) {
      const textDivs = document.querySelectorAll('div[dir="auto"]');
      for (const div of textDivs) {
        const t = div.textContent.trim();
        if (t.length < 20 || isUIText(t)) continue;

        // Skip if this looks like a comment:
        // - Has a nearby "Reply" or "Like" button at comment level
        // - Is inside a comment thread (near a "Write a comment" input)
        // - Parent chain contains comment-like indicators
        if (isComment(div)) continue;

        // Walk up to find a reasonable post container
        const container = findPostContainer(div);
        if (!container) continue;

        const author = extractAuthor(container);
        const text = extractPostText(container);
        if (!text) continue;

        // Skip if this container's text overlaps with an already-found post
        const id = 'txt_' + hashCode((author || '') + text.substring(0, 80));
        if (seen.has(id)) continue;
        seen.add(id);

        const timeStr = extractTimeString(container);
        const timestamp = parseRelativeTime(timeStr);
        const postUrl = extractPostUrl(container);
        const imageUrl = extractImage(container);
        const imageCount = countImages(container);
        const deal = parseDealInfo(text);

        posts.push({
          id, author: author || 'Unknown', text,
          timeStr: timeStr || '', timestamp, url: postUrl,
          imageUrl, imageCount, ...deal
        });
      }
    }

    return posts;
  }

  function isComment(element) {
    // Walk up a few levels and check for comment indicators
    let el = element;
    for (let i = 0; i < 8; i++) {
      el = el.parentElement;
      if (!el) return false;

      // Check for comment-specific attributes
      const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
      if (ariaLabel.includes('comment')) return true;

      // Check for "Reply" sibling — comments have Reply buttons, posts don't
      const text = el.innerText || '';
      // Comments typically have "Like · Reply · Xm" pattern nearby
      if (/\bReply\b/.test(text) && /\b\d+[mhd]\b/.test(text) && text.length < 500) return true;

      // Check if this div is small — comments are usually narrow/short
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.width < 350 && rect.height < 100) {
        // Small container with short text is likely a comment
        if (element.textContent.trim().length < 100) return true;
      }
    }

    // Also check: if the text div is preceded by a "Write a comment" or "Write a public comment" input
    const prevSiblings = element.parentElement?.querySelectorAll('input, [contenteditable], [placeholder*="comment" i]');
    if (prevSiblings && prevSiblings.length > 0) return true;

    return false;
  }

  function findPostContainer(element) {
    let el = element;
    for (let i = 0; i < 20; i++) {
      el = el.parentElement;
      if (!el) return null;
      if (el.getAttribute('role') === 'article') return el;

      const rect = el.getBoundingClientRect();
      if (rect.height > 150 && rect.width > 400) {
        if (el.getAttribute('data-pagelet')?.includes('FeedUnit') ||
            (el.classList.length > 0 && rect.height < 1200)) {
          return el;
        }
      }
    }
    return null;
  }

  // ── Timestamp Parsing ──────────────────────────────────────────────
  function extractTimeString(article) {
    // Facebook shows timestamps as "Just now", "3m", "1h", "2d", "Yesterday", etc.
    // These are usually in an <a> tag with aria-label containing the date,
    // or in a short text element near the author name
    
    // Strategy 1: Look for aria-label with date/time info on links
    const links = article.querySelectorAll('a[aria-label]');
    for (const link of links) {
      const label = link.getAttribute('aria-label') || '';
      // Facebook puts full timestamps in aria-label like "2 hours ago" or "February 8, 2026 at 7:30 PM"
      if (/\d+\s*(second|minute|hour|day|week|month|year|ago|at\s)/i.test(label)) {
        return label;
      }
    }

    // Strategy 2: Look for short time text like "3m", "1h", "2d", "Just now"
    const spans = article.querySelectorAll('a span, a');
    for (const span of spans) {
      const t = span.textContent.trim();
      if (/^(\d+[mhd]|Just now|Yesterday|\d+\s*(min|hr|sec|day))s?$/i.test(t)) {
        return t;
      }
    }

    // Strategy 3: Look for any element with time-like content
    const allText = article.querySelectorAll('span, abbr');
    for (const el of allText) {
      const t = el.textContent.trim();
      if (t.length < 20 && /^(\d+[mhd]|Just now|\d+\s*m$)/i.test(t)) {
        return t;
      }
    }

    return null;
  }

  function parseRelativeTime(timeStr) {
    if (!timeStr) return Date.now() - 86400000; // default: 24h ago

    const now = Date.now();
    const str = timeStr.toLowerCase().trim();

    // "just now"
    if (str.includes('just now')) return now;

    // "Xm" or "X min" or "X minutes ago"
    const mins = str.match(/(\d+)\s*m(?:in(?:ute)?s?)?\s*(?:ago)?/i);
    if (mins) return now - parseInt(mins[1]) * 60000;

    // "Xh" or "X hr" or "X hours ago"
    const hrs = str.match(/(\d+)\s*h(?:(?:ou)?rs?)?\s*(?:ago)?/i);
    if (hrs) return now - parseInt(hrs[1]) * 3600000;

    // "Xd" or "X days ago"
    const days = str.match(/(\d+)\s*d(?:ays?)?\s*(?:ago)?/i);
    if (days) return now - parseInt(days[1]) * 86400000;

    // "Xs" or "X seconds ago"
    const secs = str.match(/(\d+)\s*s(?:ec(?:ond)?s?)?\s*(?:ago)?/i);
    if (secs) return now - parseInt(secs[1]) * 1000;

    // "yesterday"
    if (str.includes('yesterday')) return now - 86400000;

    // Full date like "February 8, 2026 at 7:30 PM"
    const fullDate = Date.parse(str.replace(/\s+at\s+/i, ' '));
    if (!isNaN(fullDate)) return fullDate;

    // Fallback
    return now - 86400000;
  }

  // ── DOM Helpers ────────────────────────────────────────────────────
  function extractAuthor(article) {
    // Author is in heading links near the top
    const headings = article.querySelectorAll('h2 a, h3 a, h4 a, strong a');
    for (const h of headings) {
      const name = h.textContent.trim();
      if (name.length > 1 && name.length < 60) return name;
    }
    // Fallback: profile links
    const profileLinks = article.querySelectorAll('a[href*="/user/"], a[href*="facebook.com/"][role="link"]');
    for (const link of profileLinks) {
      const name = link.textContent.trim();
      if (name.length > 1 && name.length < 60 && !name.includes('http')) return name;
    }
    return null;
  }

  function extractPostText(article) {
    const textDivs = article.querySelectorAll('div[dir="auto"]');
    const texts = [];
    for (const div of textDivs) {
      const t = div.textContent.trim();
      if (t.length > 10 && !isUIText(t)) texts.push(t);
    }
    return [...new Set(texts)].join('\n').substring(0, 2000);
  }

  function isUIText(text) {
    const lower = text.toLowerCase().trim();
    const ui = ['like', 'comment', 'share', 'write a comment', 'most relevant',
      'all comments', 'see more', 'see less', 'reply', 'edited',
      'view more comments', 'write a public comment', 'admin',
      'just now', 'pin post', 'turn on notifications', 'save post'];
    return ui.some(u => lower === u) || lower.length < 6;
  }

  function extractPostUrl(article) {
    // Try to find a link to the actual post
    const selectors = [
      'a[href*="/posts/"]', 'a[href*="/permalink/"]', 'a[href*="/p/"]',
      'a[href*="story_fbid"]', 'a[href*="multi_permalinks"]'
    ];
    for (const sel of selectors) {
      const link = article.querySelector(sel);
      if (link) {
        const href = link.getAttribute('href') || '';
        return href.startsWith('http') ? href.split('?')[0] : 'https://www.facebook.com' + href.split('?')[0];
      }
    }
    // Fallback: any link with the group URL
    const groupLink = article.querySelector('a[href*="/groups/"]');
    if (groupLink) {
      const href = groupLink.getAttribute('href') || '';
      return href.startsWith('http') ? href : 'https://www.facebook.com' + href;
    }
    return window.location.href;
  }

  function extractImage(article) {
    const imgs = article.querySelectorAll('img');
    for (const img of imgs) {
      const src = img.src || '';
      const w = img.naturalWidth || img.width || 0;
      if (w > 200 && !src.includes('profile') && !src.includes('emoji')) return src;
    }
    return null;
  }

  function countImages(article) {
    let count = 0;
    for (const img of article.querySelectorAll('img')) {
      const w = img.naturalWidth || img.width || 0;
      if (w > 100 && !img.src?.includes('emoji')) count++;
    }
    return count;
  }

  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36);
  }

  // ── Deal Info Parser ───────────────────────────────────────────────
  function parseDealInfo(text) {
    if (!text) return {};
    const info = {};

    // Prices
    const priceMatches = text.match(/[£$€]\s*\d[\d,]*\.?\d*/g);
    if (priceMatches) {
      info.prices = [...new Set(priceMatches.map(p => p.replace(/\s/g, '')))];
    }
    if (!info.prices) {
      const poundWords = text.match(/(\d+)\s*(?:pounds?|quid)/gi);
      if (poundWords) info.prices = poundWords.map(p => '£' + p.match(/\d+/)[0]);
    }

    // Set numbers
    const setNumbers = new Set();
    for (const pattern of [/(?:set|#)\s*(\d{4,6})/gi, /\b([1-9]\d{4,5})\b/g]) {
      let m;
      while ((m = pattern.exec(text)) !== null) {
        if (m[1].length >= 4 && m[1].length <= 6) setNumbers.add(m[1]);
      }
    }
    if (setNumbers.size > 0) info.setNumbers = [...setNumbers].slice(0, 5);

    // Condition
    const conditions = [
      { p: /\b(?:BNIB|brand\s*new\s*in\s*box|sealed|mint)\b/i, l: '🟢 Sealed/BNIB' },
      { p: /\b(?:new|unused|unopened)\b/i, l: '🟢 New' },
      { p: /\b(?:built\s*once|complete|excellent|great\s*condition|like\s*new)\b/i, l: '🟡 Excellent' },
      { p: /\b(?:good\s*condition|used|pre-?owned|played\s*with)\b/i, l: '🟠 Used/Good' },
      { p: /\b(?:no\s*box|no\s*instructions?|missing\s*parts?|incomplete)\b/i, l: '🔴 Incomplete' },
      { p: /\b(?:damaged|broken|spares|parts\s*only|joblot|job\s*lot|bulk)\b/i, l: '⚪ Parts/Bulk' },
    ];
    for (const { p, l } of conditions) {
      if (p.test(text)) { info.condition = l; break; }
    }

    // Location
    const locPatterns = [
      /(?:collection|collect|pickup)\s+(?:from\s+)?([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d?[A-Z]{0,2})/i,
      /(?:collection|collect|pickup)\s+(?:from\s+)?(?:in\s+)?([A-Za-z\s]{3,25})/i,
      /(?:based\s+in|located?\s+in|from)\s+([A-Za-z\s]{3,25})/i,
      /\b([A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2})\b/,
    ];
    for (const pattern of locPatterns) {
      const match = text.match(pattern);
      if (match) {
        const loc = match[1].trim().replace(/\s+/g, ' ');
        if (loc.length >= 2 && !/^(the|and|for|with|but|all|any|see|more)$/i.test(loc)) {
          info.location = loc; break;
        }
      }
    }

    // Shipping
    if (/free\s+(?:p&p|postage|shipping|delivery|post)/i.test(text) ||
        /(?:postage|shipping)\s+(?:is\s+)?(?:included|free)/i.test(text)) {
      info.freeShipping = true;
    }
    const shipCost = text.match(/(?:postage|shipping|p&p)\s+(?:is\s+)?[£$€]\s*(\d+\.?\d*)/i)
      || text.match(/[£$€]\s*(\d+\.?\d*)\s+(?:postage|shipping|p&p)/i);
    if (shipCost) info.shippingCost = '£' + shipCost[1];

    // Deal type
    if (/\b(?:swap|trade|exchange)\b/i.test(text)) info.dealType = '🔄 Swap/Trade';
    else if (/\b(?:free|giveaway|giving\s*away)\b/i.test(text)) info.dealType = '🎁 Free';
    else if (/\b(?:want(?:ed)?|wtb|looking\s*for|iso|in\s*search\s*of)\b/i.test(text)) info.dealType = '🔍 Wanted';
    else if (/\b(?:sell|sale|selling|for\s*sale)\b/i.test(text)) info.dealType = '💰 For Sale';

    return info;
  }

  // ── Discord Webhook ────────────────────────────────────────────────
  async function sendToDiscord(post) {
    if (!config.webhookUrl) return;

    let preview = (post.text || '').replace(/\0/g, '').substring(0, 500);
    const safeAuthor = (post.author || 'Unknown').replace(/\0/g, '').substring(0, 100);

    const fields = [];
    if (post.prices?.length > 0) fields.push({ name: '💷 Price', value: post.prices.join(', ').substring(0, 100), inline: true });
    if (post.setNumbers?.length > 0) {
      const links = post.setNumbers.map(n => `[${n}](https://brickset.com/sets/${n})`);
      fields.push({ name: '🧱 Set #', value: links.join(', ').substring(0, 200), inline: true });
    }
    if (post.condition) fields.push({ name: 'Condition', value: post.condition, inline: true });
    if (post.dealType) fields.push({ name: 'Type', value: post.dealType, inline: true });
    if (post.location) fields.push({ name: '📍 Location', value: post.location.substring(0, 100), inline: true });
    if (post.freeShipping) fields.push({ name: '📦 Shipping', value: 'Free!', inline: true });
    else if (post.shippingCost) fields.push({ name: '📦 Shipping', value: post.shippingCost, inline: true });
    if (post.imageCount > 1) fields.push({ name: '📸 Photos', value: `${post.imageCount} images`, inline: true });
    if (post.timeStr) fields.push({ name: '🕐 Posted', value: post.timeStr.substring(0, 100), inline: true });

    let color = 5793266;
    if (post.dealType === '🎁 Free') color = 3066993;
    if (post.dealType === '💰 For Sale') color = 15844367;
    if (post.dealType === '🔍 Wanted') color = 3447003;
    if (post.dealType === '🔄 Swap/Trade') color = 10181046;

    const embed = {
      title: `🧱 ${safeAuthor}`.substring(0, 256),
      description: preview || '(no text)',
      url: post.url,
      color,
      timestamp: new Date().toISOString(),
      footer: { text: `FB Group Sniper • ${groupId}` }
    };
    if (fields.length > 0) embed.fields = fields;
    if (post.imageUrl?.startsWith('https') && post.imageUrl.length < 2000) {
      embed.thumbnail = { url: post.imageUrl };
    }

    try {
      const res = await fetch(config.webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ embeds: [embed] })
      });
      if (!res.ok) {
        const err = await res.text().catch(() => '');
        console.error(`[FB Sniper] Discord ${res.status}: ${err}`);
        // Retry without thumbnail
        if (embed.thumbnail) {
          delete embed.thumbnail;
          const retry = await fetch(config.webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ embeds: [embed] })
          });
          if (retry.ok) console.log(`[FB Sniper] → Discord (no thumb): ${post.id} | ${safeAuthor}`);
          else console.error(`[FB Sniper] Retry failed: ${retry.status}`);
        }
      } else {
        console.log(`[FB Sniper] → Discord: ${post.id} | ${safeAuthor} | ${post.dealType || 'post'} | ${post.timeStr || ''} | ${(post.prices || []).join(', ') || 'no price'}`);
      }
    } catch (e) {
      console.error('[FB Sniper] Discord error:', e);
    }
  }

  // ── Persistent Status Bar ────────────────────────────────────────
  let scanCount = 0;
  let lastRefreshTime = new Date();

  function showStatusBar() {
    let bar = document.getElementById('fb-sniper-status');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'fb-sniper-status';
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
    const bar = document.getElementById('fb-sniper-status');
    if (!bar) return;

    const now = new Date();
    const refreshAge = Math.round((now - lastRefreshTime) / 1000);
    const nextRefresh = Math.max(0, config.refreshMinutes * 60 - refreshAge);
    const nextRefreshStr = nextRefresh > 60
      ? `${Math.floor(nextRefresh / 60)}m ${nextRefresh % 60}s`
      : `${nextRefresh}s`;

    const sentCount = sentPostHashes.size;
    const lastSentStr = lastSentTimestamp
      ? new Date(lastSentTimestamp).toLocaleTimeString()
      : 'never';

    bar.innerHTML = `
      <span>🧱 <strong style="color:#48bb78">FB Sniper Active</strong> —
        Page loaded: <strong>${lastRefreshTime.toLocaleTimeString()}</strong> |
        Scans: <strong>${scanCount}</strong> |
        Sent: <strong>${sentCount}</strong></span>
      <span>Last alert: <strong>${lastSentStr}</strong> |
        Next refresh: <strong style="color:#f6e05e">${nextRefreshStr}</strong></span>
    `;
  }

  // Update status bar every 5 seconds
  setInterval(updateStatusBar, 5000);

  // ── UI Banner ──────────────────────────────────────────────────────
  function showBanner(message, type) {
    const el = document.getElementById('fb-sniper-banner');
    if (el) el.remove();

    const banner = document.createElement('div');
    banner.id = 'fb-sniper-banner';
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

})();
