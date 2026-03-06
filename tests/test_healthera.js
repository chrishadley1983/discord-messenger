/**
 * Test Healthera checkbox selection — login, select meds, verify, but DON'T order.
 */

const { chromium } = require('playwright');
const http = require('http');

const STEALTH_ARGS = [
  '--disable-blink-features=AutomationControlled',
  '--no-first-run',
  '--no-default-browser-check',
];

const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const STEALTH_SCRIPT = `
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
`;

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`JSON parse: ${data.substring(0, 200)}`)); }
      });
    }).on('error', reject);
  });
}

async function login(page) {
  await page.goto('https://healthera.co.uk/app', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.locator('button:has-text("Sign in")').click();
  await page.waitForTimeout(2000);
  await page.fill('#register-email', 'chrishadley1983@googlemail.com');
  await page.locator('button[type="submit"]:has-text("Continue")').click();
  await page.waitForTimeout(3000);

  let otp = null;
  for (let i = 0; i < 6; i++) {
    await new Promise(r => setTimeout(r, 5000));
    const result = await fetchJson(
      'http://172.19.64.1:8100/gmail/search?q=from:noreply@healthera.co.uk+subject:Sign+in+to+Healthera+newer_than:2m&max_results=1'
    );
    if (result.count > 0) {
      const match = result.emails[0].snippet.match(/(\d{6})/);
      if (match) { otp = match[1]; break; }
    }
  }
  if (!otp) throw new Error('Could not get OTP');

  await page.fill('#verify-otp', otp);
  await page.locator('button:has-text("Submit code")').click();
  await page.waitForTimeout(3000);
  console.log('[LOGIN] Done\n');
}

async function test() {
  console.log('=== Healthera Checkbox Test (DRY RUN — no order placed) ===\n');

  const browser = await chromium.launch({
    executablePath: '/home/chris_hadley/.cache/ms-playwright/chromium-1212/chrome-linux64/chrome',
    headless: true,
    args: STEALTH_ARGS,
  });

  const context = await browser.newContext({ userAgent: USER_AGENT });
  await context.addInitScript(STEALTH_SCRIPT);
  const page = await context.newPage();

  try {
    await login(page);

    // Navigate to prescriptions
    console.log('[1] Loading prescription page...');
    await page.goto('https://healthera.co.uk/app/prescriptions/add-medicine', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Get initial state
    const bodyBefore = (await page.textContent('body')).replace(/\s+/g, ' ');
    const selectedBefore = bodyBefore.match(/Selected (\d+) of (\d+)/);
    console.log(`    Before: ${selectedBefore ? selectedBefore[0] : 'unknown'}`);

    // Find and click both checkboxes
    console.log('\n[2] Clicking checkboxes...');
    const checkboxes = await page.locator('input[type="checkbox"]').all();
    console.log(`    Found ${checkboxes.length} checkboxes`);

    for (let i = 0; i < checkboxes.length; i++) {
      const wasBefore = await checkboxes[i].isChecked();
      await checkboxes[i].click({ force: true });
      await page.waitForTimeout(500);
      const isAfter = await checkboxes[i].isChecked();
      console.log(`    Checkbox ${i}: ${wasBefore} -> ${isAfter}`);
    }

    await page.waitForTimeout(1000);

    // Get new state
    const bodyAfter = (await page.textContent('body')).replace(/\s+/g, ' ');
    const selectedAfter = bodyAfter.match(/Selected (\d+) of (\d+)/);
    console.log(`\n    After: ${selectedAfter ? selectedAfter[0] : 'unknown'}`);

    // Check the Order button state
    const orderBtn = page.locator('button:has-text("Order")');
    const orderBtnVisible = await orderBtn.first().isVisible().catch(() => false);
    const orderBtnEnabled = await orderBtn.first().isEnabled().catch(() => false);
    const orderBtnText = await orderBtn.first().textContent().catch(() => '');
    console.log(`\n    Order button: visible=${orderBtnVisible}, enabled=${orderBtnEnabled}, text="${orderBtnText.trim()}"`);

    await page.screenshot({ path: 'test_healthera_selected.png', fullPage: true });
    console.log('    Screenshot: test_healthera_selected.png');

    // IMPORTANT: Uncheck both to leave state clean
    console.log('\n[3] Unchecking (cleanup)...');
    for (const cb of checkboxes) {
      if (await cb.isChecked()) {
        await cb.click({ force: true });
        await page.waitForTimeout(300);
      }
    }
    const bodyFinal = (await page.textContent('body')).replace(/\s+/g, ' ');
    const selectedFinal = bodyFinal.match(/Selected (\d+) of (\d+)/);
    console.log(`    Final: ${selectedFinal ? selectedFinal[0] : 'unknown'}`);

    console.log('\n=== DRY RUN COMPLETE — No order was placed ===');
  } catch (err) {
    console.error(`ERROR: ${err.message}`);
    await page.screenshot({ path: 'test_healthera_error.png', fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }
}

test().catch(console.error);
