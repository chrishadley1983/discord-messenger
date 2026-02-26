# 🏪 FB Marketplace Sniper

Chrome extension that monitors Facebook Marketplace search results and sends Discord notifications when new listings appear. Built for sniping deals.

## Setup (5 minutes)

### Step 1: Create a Discord Webhook
1. In your Discord server, pick a channel for alerts
2. Channel Settings → **Integrations** → **Webhooks** → **New Webhook**
3. Copy the **Webhook URL**

### Step 2: Install the Extension
1. Open `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select this `fb-marketplace-sniper` folder

### Step 3: Configure
1. Right-click extension icon → **Options**
2. Paste your Discord webhook URL
3. (Optional) Set min/max price filters
4. Adjust poll interval (default 45s) and refresh interval (default 5min)
5. Click **Save**, then **Send Test Message** to verify

### Step 4: Use It
1. Go to Facebook Marketplace and set up your search with filters
   - Example: `https://www.facebook.com/marketplace/106038522769760/search?daysSinceListed=1&sortBy=creation_time_descend&query=lego`
2. Keep the tab open — the extension monitors while you browse
3. New listings trigger Discord notifications with title, price, location, and thumbnail

## How It Works

- Content script runs on any `facebook.com/marketplace/*` page
- Every N seconds, scans the DOM for `/marketplace/item/ITEMID` links
- First scan seeds existing listings as "seen"
- New listings are sent to Discord with structured embeds
- Page auto-refreshes every N minutes to ensure fresh results
- Seen listing IDs persist across refreshes (stored in chrome.storage)

## Features

- **Price filtering** — Set min/max price in options to ignore listings outside your range
- **Auto-refresh** — Page reloads periodically to catch new listings
- **Set number detection** — Extracts 4-6 digit Lego set numbers and links to Brickset
- **Colour-coded alerts** — Green for cheap/free, gold for mid-range, orange for pricey
- **Thumbnail preview** — Shows listing image in Discord embed
- **Multiple searches** — Open multiple Marketplace search tabs for different queries

## Tips

- **Sort by "Date listed: newest first"** in your Marketplace search for best results
- **Use Facebook's built-in filters** (distance, price range, date listed) to pre-filter
- **Pin the tab** to avoid accidentally closing it
- **5-minute refresh** is a good default — Marketplace doesn't update as fast as groups
- Works alongside the FB Group Sniper extension — run both simultaneously
