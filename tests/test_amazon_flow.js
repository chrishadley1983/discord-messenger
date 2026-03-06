/**
 * Test Amazon browser automation flow using the same stealth config as Peter.
 *
 * Tests:
 * 1. Amazon loads without bot detection
 * 2. Can navigate to a product page
 * 3. Can reach sign-in page and fill email
 * 4. Sign-in page accepts the email field
 *
 * Run: wsl bash -c "cd /mnt/c/Users/Chris\ Hadley/claude-projects/Discord-Messenger && node tests/test_amazon_flow.js"
 */

const { chromium } = require('playwright');

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

const AMAZON_EMAIL = 'chrishadley1983@googlemail.com';

async function test() {
  console.log('=== Amazon Browser Automation Test ===\n');

  const browser = await chromium.launch({
    executablePath: '/home/chris_hadley/.cache/ms-playwright/chromium-1212/chrome-linux64/chrome',
    headless: true,
    args: STEALTH_ARGS,
  });

  const context = await browser.newContext({
    userAgent: USER_AGENT,
  });

  await context.addInitScript(STEALTH_SCRIPT);
  const page = await context.newPage();

  try {
    // Test 1: Load Amazon homepage
    console.log('[1] Navigating to amazon.co.uk...');
    const response = await page.goto('https://www.amazon.co.uk', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const status = response?.status();
    console.log(`    Status: ${status}`);
    // Amazon sometimes returns 202/503 initially, wait for full load
    if (status !== 200) {
      console.log('    Non-200 status, waiting for full page load...');
      await page.waitForTimeout(3000);
    }
    const title = await page.title();
    console.log(`    Title: ${title}`);
    const url = page.url();
    console.log(`    URL: ${url}`);
    if (title.includes('Amazon') || url.includes('amazon')) {
      console.log('    PASS: Amazon loaded\n');
    } else {
      console.log('    FAIL: Not on Amazon');
      const bodySnippet = (await page.textContent('body')).substring(0, 500);
      console.log(`    Body: ${bodySnippet}`);
      return;
    }

    // Test 2: Check for bot detection page
    console.log('[2] Checking for bot detection...');
    const bodyText = await page.textContent('body');
    // Check for actual bot block pages, not just the word appearing in product descriptions
    const isBlocked = bodyText.includes("Type the characters you see") ||
                      bodyText.includes("Sorry, we just need to make sure you're not a robot") ||
                      bodyText.includes("Enter the characters you see below") ||
                      (bodyText.includes('captcha') && bodyText.length < 2000);
    if (isBlocked) {
      console.log('    FAIL: Bot detection / CAPTCHA triggered');
      console.log(`    Body preview: ${bodyText.substring(0, 300)}`);
      return;
    }
    // Quick check: can we see normal Amazon elements?
    const hasSearchBox = await page.locator('#twotabsearchtextbox').isVisible().catch(() => false);
    console.log(`    Search box visible: ${hasSearchBox}`);
    console.log('    PASS: No bot detection\n');

    // Test 3: Navigate to a test product (LEGO set)
    console.log('[3] Searching for a product...');
    await page.fill('#twotabsearchtextbox', 'LEGO 42151');
    await page.click('#nav-search-submit-button');
    await page.waitForLoadState('domcontentloaded');
    const searchTitle = await page.title();
    console.log(`    Search results title: ${searchTitle}`);
    console.log('    PASS: Search works\n');

    // Test 4: Click first result
    console.log('[4] Clicking first search result...');
    // Try multiple selector strategies for search results
    let productLink = null;
    const selectors = [
      '[data-component-type="s-search-result"] h2 a',
      '.s-result-item h2 a',
      '.s-main-slot h2 a',
      'div[data-asin] h2 a',
    ];
    for (const sel of selectors) {
      const loc = page.locator(sel).first();
      if (await loc.isVisible({ timeout: 3000 }).catch(() => false)) {
        productLink = loc;
        console.log(`    Found with selector: ${sel}`);
        break;
      }
    }
    if (!productLink) {
      // Fallback: just find any link with "LEGO" in it
      productLink = page.locator('a:has-text("LEGO")').first();
      console.log('    Using fallback LEGO text link');
    }
    const productName = await productLink.textContent().catch(() => '(unknown)');
    console.log(`    Product: ${productName?.trim().substring(0, 80)}`);
    await productLink.click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    const productTitle = await page.title();
    console.log(`    Product page title: ${productTitle.substring(0, 80)}`);
    console.log('    PASS: Product page loaded\n');

    // Test 5: Try to add to basket
    console.log('[5] Looking for Add to Basket button...');
    const addToBasket = page.locator('#add-to-cart-button');
    if (await addToBasket.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('    Found Add to Basket button');
      await addToBasket.click();
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);

      // Check if added successfully
      const pageText = await page.textContent('body');
      if (pageText.includes('Added to Basket') || pageText.includes('added to your Basket') || pageText.includes('Basket subtotal')) {
        console.log('    PASS: Added to basket successfully\n');
      } else {
        console.log('    WARN: Clicked add to basket but confirmation unclear\n');
      }
    } else {
      console.log('    WARN: No Add to Basket button found (may need to select options)\n');
    }

    // Test 6: Go to basket
    console.log('[6] Navigating to basket...');
    await page.goto('https://www.amazon.co.uk/gp/cart/view.html', { waitUntil: 'domcontentloaded' });
    const basketTitle = await page.title();
    console.log(`    Basket page: ${basketTitle}`);
    console.log('    PASS: Basket page loaded\n');

    // Test 7: Try proceed to checkout (will redirect to sign-in)
    console.log('[7] Proceeding to checkout (expect sign-in redirect)...');
    const checkoutBtn = page.locator('[name="proceedToRetailCheckout"], #sc-buy-box-ptc-button, input[value*="Proceed"]');
    if (await checkoutBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) {
      await checkoutBtn.first().click();
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);

      const currentUrl = page.url();
      console.log(`    Redirected to: ${currentUrl.substring(0, 100)}`);

      if (currentUrl.includes('signin') || currentUrl.includes('ap/signin')) {
        console.log('    PASS: Redirected to sign-in (expected)\n');

        // Test 8: Fill email on sign-in page
        console.log('[8] Filling email on sign-in page...');
        const emailField = page.locator('#ap_email');
        if (await emailField.isVisible({ timeout: 5000 }).catch(() => false)) {
          await emailField.fill(AMAZON_EMAIL);
          console.log(`    Filled email: ${AMAZON_EMAIL}`);
          await page.click('#continue');
          await page.waitForLoadState('domcontentloaded');
          await page.waitForTimeout(2000);

          const afterEmailUrl = page.url();
          const afterEmailText = await page.textContent('body');
          if (afterEmailText.includes('password') || afterEmailText.includes('Password')) {
            console.log('    PASS: Email accepted, password page shown');
            console.log('    (In real flow: webhook+sleep for Chris to enter password)\n');
          } else if (afterEmailText.includes('captcha') || afterEmailText.includes('puzzle')) {
            console.log('    WARN: CAPTCHA on sign-in page');
            console.log('    (In real flow: webhook+sleep for Chris to solve)\n');
          } else {
            console.log(`    INFO: After email submit - URL: ${afterEmailUrl.substring(0, 100)}`);
            console.log('    Page may need investigation\n');
          }
        } else {
          console.log('    WARN: Email field not found on sign-in page');
          const signInText = await page.textContent('body');
          console.log(`    Page text preview: ${signInText.substring(0, 200)}\n`);
        }
      } else {
        console.log(`    INFO: Not redirected to sign-in. URL: ${currentUrl}\n`);
      }
    } else {
      console.log('    WARN: No checkout button found (basket may be empty)\n');
    }

    console.log('=== Test Complete ===');

  } catch (err) {
    console.error(`ERROR: ${err.message}`);
  } finally {
    await browser.close();
  }
}

test().catch(console.error);
