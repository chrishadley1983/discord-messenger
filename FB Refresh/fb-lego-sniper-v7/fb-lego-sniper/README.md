# 🧱 FB Group Sniper

A Chrome extension that monitors Facebook group feeds for new posts and sends instant Discord notifications. Built for sniping deals in buy/sell/trade groups.

## Setup (5 minutes)

### Step 1: Create a Discord Webhook

1. In your Discord server, go to a channel where you want alerts
2. Click the gear icon → **Integrations** → **Webhooks** → **New Webhook**
3. Name it something like "Lego Deals" and copy the **Webhook URL**

### Step 2: Install the Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked** and select this `fb-lego-sniper` folder
4. The extension will appear in your toolbar

### Step 3: Configure

1. Right-click the extension icon → **Options** (or click the extension and go to Options)
2. Paste your Discord webhook URL
3. (Optional) Add keyword filters like `modular, UCS, creator expert, 10294, bulk`
   - Leave blank to be notified about ALL new posts
   - Comma-separated, case-insensitive
4. Set poll interval (default 45 seconds — don't go below 15s)
5. Click **Save**, then **Send Test Message** to verify Discord works

### Step 4: Use It

1. Navigate to your Facebook group page (e.g. `facebook.com/groups/177707179101917/`)
2. You'll see a small green banner: "🧱 FB Sniper active"
3. Keep the tab open — the extension monitors while you browse
4. New posts trigger Discord notifications with the post text, author, and a direct link

## How It Works

- Runs a content script on `facebook.com/groups/*` pages
- Every N seconds, scans the DOM for post permalink patterns (`/posts/POSTID`)
- Compares against seen post IDs (persisted in chrome.storage)
- On first load, seeds all visible posts as "seen" so you don't get flooded
- New posts are sent to Discord via webhook with an embed containing:
  - Post author name
  - Post text preview (first 300 chars)
  - Direct link to the post
  - Thumbnail if an image is detected

## Keyword Filtering

If you set keywords like `modular, UCS, 10294, bulk, retired`, only posts containing at least one of those terms will trigger a notification. Great for high-volume groups where you only care about specific types of deals.

## Tips

- **Keep the group tab open** — the extension only works while the tab is loaded
- **Sort by New** — click "New posts" at the top of the group feed so newest posts load first
- **Pin the tab** to prevent accidentally closing it
- **Multiple groups** — open multiple group tabs and the extension runs on each one
- **Don't set interval too low** — 30-60 seconds is plenty. Going below 15s adds no value since Facebook's feed doesn't update that fast

## Limitations

- Only works while the Facebook group tab is open in Chrome
- Facebook obfuscates their DOM — if FB changes their HTML structure significantly, the post detection may need updating
- Cannot detect posts that haven't been loaded into the DOM (you need to have scrolled to them or have them in the initial feed load)
- Not affiliated with Facebook/Meta in any way
