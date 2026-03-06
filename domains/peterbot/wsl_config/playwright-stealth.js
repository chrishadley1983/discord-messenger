// Stealth patches to make Playwright Chromium look like a real browser
// Injected via --init-script before any page scripts run

// Remove navigator.webdriver flag (biggest bot detection signal)
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Fake plugins (real Chrome has at least these)
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ],
});

// Fake languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });

// Fix chrome.runtime (missing in automation mode, present in real Chrome)
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };

// Patch permissions query (Playwright returns 'denied' for notifications, real Chrome returns 'prompt')
const originalQuery = window.Permissions?.prototype?.query;
if (originalQuery) {
  window.Permissions.prototype.query = function (parameters) {
    return parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery.call(this, parameters);
  };
}
