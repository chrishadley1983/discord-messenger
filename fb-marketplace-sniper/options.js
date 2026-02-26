const $ = id => document.getElementById(id);

chrome.storage.local.get(['webhookUrl', 'minPrice', 'maxPrice', 'interval', 'maxPosts', 'refreshMinutes'], data => {
  if (data.webhookUrl) $('webhookUrl').value = data.webhookUrl;
  if (data.minPrice) $('minPrice').value = data.minPrice;
  if (data.maxPrice) $('maxPrice').value = data.maxPrice;
  if (data.interval) $('interval').value = data.interval;
  if (data.maxPosts) $('maxPosts').value = data.maxPosts;
  if (data.refreshMinutes) $('refreshMinutes').value = data.refreshMinutes;
});

$('saveBtn').addEventListener('click', () => {
  const webhookUrl = $('webhookUrl').value.trim();
  if (!webhookUrl.startsWith('https://discord.com/api/webhooks/') &&
      !webhookUrl.startsWith('https://discordapp.com/api/webhooks/')) {
    showStatus('Invalid Discord webhook URL', 'error');
    return;
  }
  chrome.storage.local.set({
    webhookUrl,
    minPrice: parseInt($('minPrice').value) || 0,
    maxPrice: parseInt($('maxPrice').value) || 0,
    interval: parseInt($('interval').value) || 45,
    maxPosts: parseInt($('maxPosts').value) || 5,
    refreshMinutes: parseInt($('refreshMinutes').value) || 5
  }, () => showStatus('Settings saved ✓', 'success'));
});

$('testBtn').addEventListener('click', async () => {
  const webhookUrl = $('webhookUrl').value.trim();
  if (!webhookUrl) {
    showStatus('Enter a webhook URL first', 'error');
    return;
  }
  try {
    const res = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: null,
        embeds: [{
          title: '🏪 FB Marketplace Sniper — Test',
          description: 'If you see this, notifications are working!',
          color: 15844367,
          timestamp: new Date().toISOString()
        }]
      })
    });
    if (res.ok || res.status === 204) {
      showStatus('Test message sent! Check Discord.', 'success');
    } else {
      showStatus(`Discord returned ${res.status}. Check your webhook URL.`, 'error');
    }
  } catch (e) {
    showStatus('Failed to reach Discord: ' + e.message, 'error');
  }
});

function showStatus(msg, type) {
  const el = $('status');
  el.textContent = msg;
  el.className = 'status ' + type;
  setTimeout(() => { el.textContent = ''; }, 4000);
}
