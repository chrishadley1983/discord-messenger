// Headless E2E assertions for the Reset Cut dashboard LAN page.
// Verifies render correctness: no console errors, all sections populate, the
// hero shows BOTH current + trend numbers in distinct colours, charts actually
// draw, and the page renders on mobile. Prints a JSON verdict; exit 1 on fail.
//
// Run: NODE_PATH="<global node_modules>" node scripts/dashboard-e2e-check.js [url]
const { chromium } = require('playwright');

const URL = process.argv[2] || process.env.DASH_URL || 'http://127.0.0.1:8100/fitness/dashboard/page';
const SECTIONS = ['today', 'progress', 'trends', 'training', 'targets'];

(async () => {
  const result = { url: URL, ok: true, fails: [], checks: {}, consoleErrors: [] };
  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error') result.consoleErrors.push(m.text()); });
    page.on('pageerror', e => result.consoleErrors.push('pageerror: ' + e.message));
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('#app:not(.hidden)', { timeout: 10000 });
    await page.waitForTimeout(800);

    // 1. nav has all 5 sections
    const navCount = await page.$$eval('.navitem', els => els.length);
    result.checks.navItems = navCount;
    if (navCount !== 5) { result.ok = false; result.fails.push(`nav has ${navCount} items, expected 5`); }

    // 2. each section populates with content
    result.checks.sections = {};
    for (const sec of SECTIONS) {
      const sel = `.navitem[data-t="${sec}"]`;
      if (await page.$(sel)) { await page.click(sel); await page.waitForTimeout(sec === 'trends' ? 1600 : 400); }
      const len = await page.$eval(`#p-${sec}`, el => el.innerText.trim().length).catch(() => 0);
      result.checks.sections[sec] = len;
      if (len < 40) { result.ok = false; result.fails.push(`section '${sec}' nearly empty (${len} chars)`); }
    }

    // 3. hero: both numbers present, numeric, distinct colours
    await page.click('.navitem[data-t="today"]'); await page.waitForTimeout(300);
    const hero = await page.evaluate(() => {
      const s = document.querySelector('.numblock.scale .num');
      const t = document.querySelector('.numblock.trend .num');
      const cs = s ? getComputedStyle(s).color : null;
      const ct = t ? getComputedStyle(t).color : null;
      const numOf = el => el ? (el.textContent.match(/[\d.]+/) || [null])[0] : null;
      return { scale: numOf(s), trend: numOf(t), scaleColor: cs, trendColor: ct };
    });
    result.checks.hero = hero;
    if (!hero.scale) { result.ok = false; result.fails.push('hero current/scale number missing'); }
    if (!hero.trend) { result.ok = false; result.fails.push('hero 7-day trend number missing'); }
    if (hero.scaleColor && hero.scaleColor === hero.trendColor) { result.ok = false; result.fails.push('current and trend numbers share the same colour — not visually distinct'); }

    // 4. charts draw (colour variety on the trends canvases)
    await page.click('.navitem[data-t="trends"]'); await page.waitForTimeout(1800);
    const charts = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('#p-trends canvas').forEach(c => {
        try {
          const ctx = c.getContext('2d'); const w = c.width, h = c.height;
          const d = ctx.getImageData(0, 0, w, h).data; const seen = new Set(); let nonblank = 0;
          for (let i = 0; i < d.length; i += 4 * 101) { if (d[i + 3] > 0) { nonblank++; seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]); } }
          out.push({ w, h, colors: seen.size, nonblank });
        } catch (e) { out.push({ err: String(e) }); }
      });
      return out;
    });
    result.checks.charts = charts;
    const drawn = charts.filter(c => c.colors > 3).length;
    result.checks.chartsDrawn = drawn;
    if (charts.length === 0) { result.ok = false; result.fails.push('no chart canvases found on Trends'); }
    else if (drawn === 0) { result.ok = false; result.fails.push('chart canvases are blank (no draw)'); }
    await ctx.close();

    // 5. mobile render — hero both numbers visible
    const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
    const mp = await mctx.newPage();
    await mp.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    await mp.waitForSelector('#app:not(.hidden)', { timeout: 10000 });
    await mp.waitForTimeout(500);
    const mobileHero = await mp.evaluate(() => {
      const s = document.querySelector('.numblock.scale .num'); const t = document.querySelector('.numblock.trend .num');
      const vis = el => el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
      return { scaleVisible: vis(s), trendVisible: vis(t) };
    });
    result.checks.mobileHero = mobileHero;
    if (!mobileHero.scaleVisible || !mobileHero.trendVisible) { result.ok = false; result.fails.push('mobile: a hero number is not visible'); }
    await mctx.close();

    // console errors are a soft signal; treat as failure if any hard JS error
    if (result.consoleErrors.length) { result.ok = false; result.fails.push(`${result.consoleErrors.length} console error(s)`); }
  } catch (e) {
    result.ok = false; result.fails.push('exception: ' + (e && e.message || String(e)));
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
})();
