const $ = id => document.getElementById(id);

chrome.storage.local.get(
  ['webhookUrl', 'minDiscount', 'interval', 'maxPosts', 'refreshMinSecs', 'refreshMaxSecs', 'quietStart', 'quietEnd', 'vintedPostage', 'minMarginGreen', 'minMarginAmber'],
  data => {
    $('webhookUrl').value = data.webhookUrl || 'https://discordapp.com/api/webhooks/1470092279585706089/efND5z6IviV06mM5L_Wv5GKEUzkIbDnIlGsMt5aK6cXimu2KrWpKvF1bEllFuu3kcSji';
    if (data.minDiscount) $('minDiscount').value = data.minDiscount;
    if (data.interval) $('interval').value = data.interval;
    if (data.maxPosts) $('maxPosts').value = data.maxPosts;
    if (data.refreshMinSecs) $('refreshMinSecs').value = data.refreshMinSecs;
    if (data.refreshMaxSecs) $('refreshMaxSecs').value = data.refreshMaxSecs;
    if (data.quietStart !== undefined && data.quietStart !== null && data.quietStart !== '') $('quietStart').value = data.quietStart;
    if (data.quietEnd !== undefined && data.quietEnd !== null && data.quietEnd !== '') $('quietEnd').value = data.quietEnd;
    if (data.vintedPostage !== undefined && data.vintedPostage !== null && data.vintedPostage !== '') $('vintedPostage').value = data.vintedPostage;
    if (data.minMarginGreen !== undefined && data.minMarginGreen !== null && data.minMarginGreen !== '') $('minMarginGreen').value = data.minMarginGreen;
    if (data.minMarginAmber !== undefined && data.minMarginAmber !== null && data.minMarginAmber !== '') $('minMarginAmber').value = data.minMarginAmber;
  }
);

$('saveBtn').addEventListener('click', () => {
  const webhookUrl = $('webhookUrl').value.trim();
  if (!webhookUrl.startsWith('https://discord.com/api/webhooks/') &&
      !webhookUrl.startsWith('https://discordapp.com/api/webhooks/')) {
    showStatus('Invalid Discord webhook URL', 'error');
    return;
  }

  const refreshMin = parseInt($('refreshMinSecs').value) || 60;
  const refreshMax = parseInt($('refreshMaxSecs').value) || 240;
  if (refreshMin >= refreshMax) {
    showStatus('Refresh Min must be less than Refresh Max', 'error');
    return;
  }

  const quietStartVal = $('quietStart').value.trim();
  const quietEndVal = $('quietEnd').value.trim();
  const quietStart = quietStartVal !== '' ? parseInt(quietStartVal) : '';
  const quietEnd = quietEndVal !== '' ? parseInt(quietEndVal) : '';

  if ((quietStart !== '' && quietEnd === '') || (quietStart === '' && quietEnd !== '')) {
    showStatus('Set both Quiet Start and End, or leave both blank', 'error');
    return;
  }

  const minMarginGreen = parseFloat($('minMarginGreen').value) || 25;
  const minMarginAmber = parseFloat($('minMarginAmber').value) || 15;
  if (minMarginAmber >= minMarginGreen) {
    showStatus('Green margin must be higher than Amber margin', 'error');
    return;
  }

  chrome.storage.local.set({
    webhookUrl,
    minDiscount: parseInt($('minDiscount').value) || 0,
    interval: parseInt($('interval').value) || 45,
    maxPosts: parseInt($('maxPosts').value) || 5,
    refreshMinSecs: refreshMin,
    refreshMaxSecs: refreshMax,
    quietStart,
    quietEnd,
    vintedPostage: parseFloat($('vintedPostage').value) || 2.39,
    minMarginGreen,
    minMarginAmber
  }, () => showStatus('Settings saved ✓', 'success'));
});

$('testBtn').addEventListener('click', async () => {
  const webhookUrl = $('webhookUrl').value.trim();
  if (!webhookUrl) { showStatus('Enter a webhook URL first', 'error'); return; }
  try {
    const res = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        embeds: [{
          title: '👗 Vinted Sniper — Test',
          description: 'If you see this, notifications are working!',
          color: 47252,
          timestamp: new Date().toISOString()
        }]
      })
    });
    if (res.ok || res.status === 204) showStatus('Test sent! Check Discord.', 'success');
    else showStatus(`Discord returned ${res.status}`, 'error');
  } catch (e) { showStatus('Failed: ' + e.message, 'error'); }
});

function showStatus(msg, type) {
  const el = $('status');
  el.textContent = msg;
  el.className = 'status ' + type;
  setTimeout(() => el.textContent = '', 4000);
}
