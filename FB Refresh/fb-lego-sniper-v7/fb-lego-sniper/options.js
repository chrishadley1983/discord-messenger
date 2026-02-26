const $ = id => document.getElementById(id);

// Load saved settings
chrome.storage.local.get(['webhookUrl', 'keywords', 'interval', 'maxPosts', 'refreshMinutes'], data => {
  $('webhookUrl').value = data.webhookUrl || 'https://discordapp.com/api/webhooks/1470092279585706089/efND5z6IviV06mM5L_Wv5GKEUzkIbDnIlGsMt5aK6cXimu2KrWpKvF1bEllFuu3kcSji';
  if (data.keywords) $('keywords').value = data.keywords;
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
    keywords: $('keywords').value.trim(),
    interval: parseInt($('interval').value) || 45,
    maxPosts: parseInt($('maxPosts').value) || 5,
    refreshMinutes: parseInt($('refreshMinutes').value) || 7
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
          title: '🧱 FB Group Sniper — Test',
          description: 'If you see this, notifications are working!',
          color: 5793266,
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
