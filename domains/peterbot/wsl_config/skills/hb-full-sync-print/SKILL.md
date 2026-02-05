---
name: hb-full-sync-print
description: Full sync, pick list generation, Discord delivery, and printing
trigger:
  - "full sync"
  - "sync and print"
  - "morning workflow"
  - "print pick lists"
  - "hb sync"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Hadley Bricks Full Sync + Print

## Purpose

Automates the morning Hadley Bricks workflow:
1. Runs full inventory sync across all platforms (Amazon, eBay, BrickLink)
2. Generates pick lists for Amazon and eBay
3. Downloads PDFs and attaches them to Discord
4. Prints PDFs to configured printer
5. Reports completion summary

Scheduled for 09:35 UK daily or triggered conversationally.

## Pre-fetched Data

The data fetcher runs the complete workflow and provides:

- `data.sync`: Sync operation results
  - `status`: "success", "error", or "pending"
  - `data`: Platform sync counts (ebay, amazon, bricklink orders)
- `data.pick_lists.amazon`: Amazon pick list
  - `status`: "success" or "error"
  - `items`: Number of items to pick
  - `orders`: Number of unique orders
  - `pdf_path`: Local path to downloaded PDF (if items > 0)
- `data.pick_lists.ebay`: eBay pick list (same structure)
- `data.print_status`: Print job results
  - `amazon`: `{success: bool, message: string}` or null (null if no items)
  - `ebay`: `{success: bool, message: string}` or null (null if no items)
  - `skipped`: Message if PETERBOT_PRINTER not configured
  - `error`: Error message if printer unavailable
- `data.errors`: Array of error messages encountered
- `data.fetch_time`: When workflow was executed

**IMPORTANT:**
- PDF files are automatically attached to Discord by the system (both scheduled and manual runs)
- Check `data.print_status.amazon.success` and `data.print_status.ebay.success` to determine if printing succeeded
- If `print_status.amazon` or `print_status.ebay` has `success: true`, printing worked - show "printed ✅"
- If `print_status` has `skipped` key, printer is not configured - omit print status from output
- Do NOT guess or assume print status - always check the actual data

## Output Format

```
**Morning Workflow Complete** — Mon 3 Feb 09:35

**Sync Results**
eBay: 5 orders | Amazon: 3 orders | BrickLink: 2

**Pick Lists**
📋 Amazon: 4 items (3 orders) — printed ✅
📋 eBay: 7 items (5 orders) — printed ✅

PDFs attached below.
```

**With attention items (unmatched or missing location):**
```
**Morning Workflow Complete** — Mon 3 Feb 09:35

**Sync Results**
eBay: 3 orders | Amazon: 1 order | BrickLink: —

**Pick Lists**
📋 Amazon: 1 item (1 order) — printed ✅
📋 eBay: 6 items (3 orders) — printed ✅

⚠️ **Attention needed:**
Amazon: 1 item has no location (60239 Police Patrol Car)
eBay: 1 unmatched item (Train Track multi-variant)

PDFs attached below.
```

## Variations

**All caught up (no items to pick):**
```
**Morning Workflow Complete** — Mon 3 Feb 09:35

**Sync Results**
eBay: 0 orders | Amazon: 0 orders | BrickLink: 0

All caught up! No items to pick.
```

**Print failed:**
```
**Morning Workflow Complete** — Mon 3 Feb 09:35

**Sync Results**
eBay: 5 orders | Amazon: 3 orders | BrickLink: 2

**Pick Lists**
📋 Amazon: 4 items (3 orders) — print failed ❌
📋 eBay: 7 items (5 orders) — print failed ❌

PDFs attached below — please print manually.
```

**Printer not configured (print_status has "skipped" key):**
```
**Morning Workflow Complete** — Mon 3 Feb 09:35

**Sync Results**
eBay: 5 orders | Amazon: 3 orders | BrickLink: 2

**Pick Lists**
📋 Amazon: 4 items (3 orders)
📋 eBay: 7 items (5 orders)

PDFs attached below.
```

## Rules

1. Always show sync results first (even if 0 orders)
2. Show pick list counts with order counts in parentheses
3. **Determine print status from data (CRITICAL):**
   - Check `data.print_status.amazon.success` and `data.print_status.ebay.success`
   - If `success: true` → show "— printed ✅"
   - If `success: false` → show "— print failed ❌"
   - If `print_status` has `skipped` key → omit print suffix entirely
   - NEVER guess - always check the actual data values
4. Show attention items if any:
   - Check `data.pick_lists.amazon.data.unknownLocationItems` for items missing storage location
   - Check `data.pick_lists.ebay.data.unmatchedItems` for items needing SKU mapping
5. If PDFs exist (items > 0), mention they're attached
6. Keep output concise - this is a status report
7. Use pipes `|` for inline stats, em-dashes `—` for print status
8. If no items to pick on both platforms, celebrate with "All caught up!"

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Sync API fails | Show "error" for that platform, continue with others |
| No items to pick | Show "All caught up!" message |
| PDF download fails | Show "unavailable" for that platform |
| Printer offline | Show "print failed (printer offline)", attach PDFs anyway |
| Printer not configured | Omit print status, just show counts |
| Total failure | Report what went wrong, suggest manual check |
