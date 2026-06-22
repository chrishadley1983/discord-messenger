// Live render check for a DEPLOYED Reset Cut dashboard surface.
// Unlike dashboard-e2e-check.js (LAN/plaintext only), this drives the REAL
// passcode-gated surge page: it enters the passcode, lets WebCrypto decrypt the
// AES-GCM payload, and only then asserts the page renders. On the LAN page (no
// gate) it just renders. Prints a JSON verdict; exit 1 on fail.
//
// Run: NODE_PATH="<global node_modules>" DASH_PASSCODE="<pc>" node scripts/dashboard-live-check.js <url>
const { chromium } = require('playwright');

const URL = process.argv[2] || process.env.DASH_URL;
const PASS = process.env.DASH_PASSCODE || '';
const SECTIONS = ['today', 'progress', 'trends', 'training', 'targets'];

if (!URL) { console.error('usage: node dashboard-live-check.js <url>'); process.exit(2); }

(async () => {
  const result = { url: URL, ok: true, gated: null, unlocked: null, generated_at: null, fails: [], checks: {}, consoleErrors: [] };
  const browser = await chromium.launch();
  try {
    // Ignore transient CDN / benign browser-policy noise; only genuine app JS
    // errors (and any uncaught pageerror) should fail the live test.
    const IGNORE = [/Failed to load resource/i, /Permissions policy/i, /compute-pressure/i, /\b504\b/, /Gateway Time-?out/i, /favicon/i, /ERR_NETWORK/i];
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error') { const t = m.text(); if (!IGNORE.some(rx => rx.test(t))) result.consoleErrors.push(t); } });
    page.on('pageerror', e => result.consoleErrors.push('pageerror: ' + e.message));

    // surge can cold-start (504) — retry the navigation a few times
    let loaded = false;
    for (let i = 0; i < 4 && !loaded; i++) {
      try { const r = await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 }); if (r && r.status() < 500) loaded = true; }
      catch (_) {}
      if (!loaded) await page.waitForTimeout(3000);
    }
    if (!loaded) { result.ok = false; result.fails.push('navigation failed (surge cold-start did not recover)'); throw new Error('nav'); }

    // gate?
    const gateHidden = await page.evaluate(() => { const g = document.getElementById('gate'); return !g || g.classList.contains('hidden'); });
    result.gated = !gateHidden;
    if (result.gated) {
      if (!PASS) { result.ok = false; result.fails.push('page is passcode-gated but no DASH_PASSCODE supplied'); }
      else {
        await page.fill('#pc', PASS);
        await page.click('#gbtn');
        try { await page.waitForSelector('#app:not(.hidden)', { timeout: 12000 }); result.unlocked = true; }
        catch (_) {
          result.unlocked = false; result.ok = false;
          const err = await page.$eval('#gerr', e => e.textContent).catch(() => '');
          result.fails.push('unlock/decrypt failed: ' + (err || 'app did not appear after passcode'));
        }
      }
    }

    if (result.ok && (await page.$('#app:not(.hidden)'))) {
      await page.waitForTimeout(700);
      result.generated_at = await page.evaluate(() => { const b = document.querySelector('#dateline b'); return b ? b.textContent.trim() : null; });

      const navCount = await page.$$eval('.navitem', els => els.length);
      result.checks.navItems = navCount;
      if (navCount !== 5) { result.ok = false; result.fails.push(`nav has ${navCount} items, expected 5`); }

      result.checks.sections = {};
      for (const sec of SECTIONS) {
        const sel = `.navitem[data-t="${sec}"]`;
        if (await page.$(sel)) { await page.click(sel); await page.waitForTimeout(sec === 'trends' ? 1600 : 400); }
        const len = await page.$eval(`#p-${sec}`, el => el.innerText.trim().length).catch(() => 0);
        result.checks.sections[sec] = len;
        if (len < 40) { result.ok = false; result.fails.push(`section '${sec}' nearly empty (${len} chars)`); }
      }

      await page.click('.navitem[data-t="today"]'); await page.waitForTimeout(300);
      const hero = await page.evaluate(() => {
        const s = document.querySelector('.numblock.scale .num'), t = document.querySelector('.numblock.trend .num');
        const numOf = el => el ? (el.textContent.match(/[\d.]+/) || [null])[0] : null;
        return { scale: numOf(s), trend: numOf(t), scaleColor: s && getComputedStyle(s).color, trendColor: t && getComputedStyle(t).color };
      });
      result.checks.hero = hero;
      if (!hero.scale) { result.ok = false; result.fails.push('hero scale number missing'); }
      if (!hero.trend) { result.ok = false; result.fails.push('hero trend number missing'); }
      if (hero.scaleColor && hero.scaleColor === hero.trendColor) { result.ok = false; result.fails.push('scale and trend share a colour — not distinct'); }

      await page.click('.navitem[data-t="trends"]'); await page.waitForTimeout(1800);
      const drawn = await page.evaluate(() => {
        let n = 0;
        document.querySelectorAll('#p-trends canvas').forEach(c => {
          try { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; const seen = new Set(); for (let i = 0; i < d.length; i += 4 * 101) if (d[i + 3] > 0) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]); if (seen.size > 3) n++; } catch (e) {}
        });
        return n;
      });
      result.checks.chartsDrawn = drawn;
      if (drawn === 0) { result.ok = false; result.fails.push('no charts drew on Trends'); }
      await ctx.close();

      // mobile
      const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
      const mp = await mctx.newPage();
      await mp.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
      if (result.gated && PASS) { await mp.fill('#pc', PASS); await mp.click('#gbtn'); await mp.waitForSelector('#app:not(.hidden)', { timeout: 12000 }).catch(() => {}); }
      await mp.waitForTimeout(500);
      const mh = await mp.evaluate(() => {
        const vis = el => el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
        return { scale: vis(document.querySelector('.numblock.scale .num')), trend: vis(document.querySelector('.numblock.trend .num')) };
      });
      result.checks.mobileHero = mh;
      if (!mh.scale || !mh.trend) { result.ok = false; result.fails.push('mobile: a hero number not visible'); }
      await mctx.close();
    }

    if (result.consoleErrors.length) { result.ok = false; result.fails.push(`${result.consoleErrors.length} console error(s)`); }
  } catch (e) {
    result.ok = false; if (String(e.message) !== 'nav') result.fails.push('exception: ' + (e && e.message || String(e)));
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
})();
