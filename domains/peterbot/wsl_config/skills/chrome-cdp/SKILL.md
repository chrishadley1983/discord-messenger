---
name: chrome-cdp
description: Interact with Chrome browser via CDP — navigate pages, take screenshots, click elements, extract text, fill forms. Use when asked to check a website, scrape data, or automate browser tasks.
trigger:
  - "check this page"
  - "open chrome"
  - "browse to"
  - "screenshot this"
  - "look at this website"
  - "scrape this page"
  - "click on"
  - "what's on this page"
  - "navigate to"
  - "check royal mail"
  - "track my parcel"
  - "check amazon"
  - "check vinted"
  - "check sainsburys"
scheduled: false
conversational: true
channel: null
---

# Chrome CDP — Browser Automation

## Purpose

Interact with the dedicated CDP Chrome browser (running on Windows at port 9222) to navigate pages, take screenshots, extract content, click elements, fill forms, and automate browser workflows.

## How to Call

All commands use `node.exe` with the cdp.mjs script. Since you're running in WSL, you MUST use `node.exe` (Windows Node) not `node` (Linux Node), and use Windows-style paths.

**Important:** The script path uses Windows format:

```bash
CDP="C:/Users/Chris Hadley/claude-projects/chrome-cdp-skill/skills/chrome-cdp/scripts/cdp.mjs"
```

## Commands

### List open tabs (always do this first)

```bash
node.exe "$CDP" list
```

Returns tab IDs and titles. Copy the ID prefix (e.g. `77A68B65`) for subsequent commands.

### Navigate to a URL

```bash
node.exe "$CDP" nav <tab_id> "https://example.com"
```

Waits for page load to complete.

### Take a screenshot

```bash
node.exe "$CDP" shot <tab_id> "C:/Users/Chris Hadley/tmp/screenshot.png"
```

Use a Windows path for the output file. Always save to `C:/Users/Chris Hadley/tmp/`.

### Get page text (accessibility tree)

```bash
node.exe "$CDP" snap <tab_id>
```

Returns semantic structure — better than raw HTML for understanding page content.

### Evaluate JavaScript

```bash
node.exe "$CDP" eval <tab_id> "document.title"
node.exe "$CDP" eval <tab_id> "document.querySelector('h1')?.innerText"
```

### Get HTML

```bash
node.exe "$CDP" html <tab_id>              # full page
node.exe "$CDP" html <tab_id> ".product"    # specific CSS selector
```

### Click an element

```bash
node.exe "$CDP" click <tab_id> "button.submit"
node.exe "$CDP" click <tab_id> "#add-to-cart"
```

### Click at coordinates

```bash
node.exe "$CDP" clickxy <tab_id> 100 200
```

Coordinates are in CSS pixels (divide screenshot pixels by DPR if DPR > 1).

### Type text

```bash
node.exe "$CDP" type <tab_id> "hello world"
```

Types at the currently focused element. Click first to focus, then type.

### Network performance

```bash
node.exe "$CDP" net <tab_id>
```

### Stop daemon

```bash
node.exe "$CDP" stop <tab_id>
```

## Royal Mail Tracking Pattern

For RM tracking lookups, use this specific SPA navigation pattern:

```bash
# 1. Clear Angular state
node.exe "$CDP" nav <tab_id> "about:blank"
sleep 0.5

# 2. Bootstrap Angular
node.exe "$CDP" nav <tab_id> "https://www.royalmail.com/track-your-item"
sleep 2

# 3. Navigate to tracking results (hash URL)
node.exe "$CDP" nav <tab_id> "https://www.royalmail.com/track-your-item#/tracking-results/WQ123456789GB"
sleep 6

# 4. Extract status
node.exe "$CDP" eval <tab_id> "(function(){var t=document.body.innerText; var m=t.match(/Your item was delivered on ([\d-]+)/i); if(m) return 'DELIVERED:'+m[1]; if(t.match(/we have your item/i)) return 'IN_TRANSIT'; if(t.match(/we.ve got it/i)) return 'IN_TRANSIT'; return 'UNKNOWN'})()"
```

**Critical:** You MUST follow the about:blank → base URL → hash URL sequence. Skipping steps breaks Angular's SPA rendering.

## SPA Navigation Strategy

Many sites use client-side routing (React, Angular, Vue, hash-based). Clicking nav links via CSS selectors often fails because the elements use JS event handlers, not standard `<a href>` links. Use this escalation strategy:

### Step 1: Discover the routing scheme

Before clicking anything, extract all navigation links to understand how the site routes:

```bash
node.exe "$CDP" eval <tab_id> "JSON.stringify([...document.querySelectorAll('nav a, .menu a, [role=navigation] a')].map(a => ({text: a.textContent.trim(), href: a.href, hash: a.hash, onclick: !!a.onclick})))"
```

This tells you whether links use paths (`/animal-cafes`), hashes (`#animal-cafes`), or JS handlers (`onclick: true`).

### Step 2: Navigate via JS evaluation (preferred)

For hash-based routing:
```bash
node.exe "$CDP" eval <tab_id> "window.location.hash = '#animal-cafes'; 'navigated'"
```

For path-based SPAs with a router (React Router, Vue Router):
```bash
node.exe "$CDP" eval <tab_id> "document.querySelector('a[href*=\"animal-cafes\"]').click(); 'clicked'"
```

For standard links, just use `nav`:
```bash
node.exe "$CDP" nav <tab_id> "https://site.com/animal-cafes-guide.html"
```

### Step 3: Check if content is already in the DOM

SPAs often load all sections into the DOM and show/hide them. If navigation isn't working, check if the content is already there:

```bash
# Check if a section exists but is hidden
node.exe "$CDP" eval <tab_id> "document.querySelector('#animal-cafes')?.innerHTML?.substring(0, 200) || 'not found'"

# Get all section IDs on the page
node.exe "$CDP" eval <tab_id> "JSON.stringify([...document.querySelectorAll('[id]')].map(el => el.id))"
```

### Step 4: Fall back to full HTML extraction

If navigation completely fails, grab the page HTML and parse it directly:

```bash
node.exe "$CDP" html <tab_id>                    # full page HTML
node.exe "$CDP" html <tab_id> "#animal-cafes"     # specific section by CSS selector
```

### Surge.sh sites

Surge sites with a `200.html` file serve the landing page for any unmatched URL path (no 404). But multi-page Surge sites (like Japan 2026) use real HTML files, not SPA routing — so use direct `nav` to the full filename:

```bash
node.exe "$CDP" nav <tab_id> "https://hadley-japan-2026.surge.sh/animal-cafes-guide.html"
```

## Tips

- Always run `list` first to get tab IDs
- First command against a new tab takes ~2s (daemon startup), subsequent commands are instant
- For SPAs (Angular, React), add `sleep` after navigation to let the page render
- Use `eval` for quick data extraction, `snap` for understanding page structure
- Use `click` with CSS selectors (preferred) or `clickxy` with coordinates (fallback)
- Use `type` for input fields — click to focus first, then type
- Screenshots go to Windows paths (e.g. `C:/Users/Chris Hadley/tmp/`)

## Rules

- Always use `node.exe` not `node` (WSL → Windows interop)
- Always use Windows paths for the script and output files
- Check login state before automating authenticated sites
- Don't rapid-fire requests — add small delays between commands
- If Chrome isn't running, tell Chris: "Chrome CDP doesn't seem to be running — make sure the CDP Chrome at C:\chrome-cdp is open."
- Report results concisely in Discord markdown format
