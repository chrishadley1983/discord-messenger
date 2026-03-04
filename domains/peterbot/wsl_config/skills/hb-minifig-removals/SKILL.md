---
name: hb-minifig-removals
description: Review and approve minifig cross-platform removal queue
trigger:
  - "minifig removals"
  - "pending removals"
  - "approve removals"
  - "minifig sold"
  - "removal queue"
scheduled: false
conversational: true
channel: #peter-chat
---

# Minifig Removal Queue

## Purpose

When a minifig sells on eBay or Bricqer, the system queues a cross-platform removal (remove from the other platform). This skill lets you check pending removals and approve them.

Sale notifications arrive in #peter-chat automatically. When you see one, check and approve the removal.

## API Endpoints

All via the HB proxy (auth handled automatically):

| Action | Endpoint | Method | Body |
|--------|----------|--------|------|
| List pending removals | `/hb/minifigs/sync/removals` | GET | — |
| Approve single removal | `/hb/minifigs/sync/removals/approve` | POST | `{"removalId": "<uuid>"}` |
| Approve all pending | `/hb/minifigs/sync/removals/bulk-approve` | POST | — |

## Workflow

### When a sale notification arrives in #peter-chat

1. Fetch pending removals:
   ```
   GET http://172.19.64.1:8100/hb/minifigs/sync/removals
   ```

2. Review the response — each removal shows:
   - `id` — the removal UUID (use this for approval)
   - `sold_on` — platform where it sold (EBAY or BRICQER)
   - `remove_from` — platform to remove from (the other one)
   - `sale_price` — what it sold for
   - `sale_date` — when it sold
   - `minifig_sync_items.name` — the minifig name

3. Approve the removal:
   ```
   POST http://172.19.64.1:8100/hb/minifigs/sync/removals/approve
   Body: {"removalId": "<id from step 2>"}
   ```

4. Report the result to the channel.

### For bulk approval (multiple pending)

```
POST http://172.19.64.1:8100/hb/minifigs/sync/removals/bulk-approve
```

Returns `{"data": {"approved": N, "failed": N, "errors": []}}`.

## Output Format

### After approving a removal:
```
**Minifig Removal Approved**

**Cavalry General** sold on eBay for £8.74
Removed from Bricqer (item #14583)

Status: EXECUTED
```

### When checking pending removals:
```
**Pending Minifig Removals** (1)

1. **Cavalry General** - Sold on eBay £8.74 (2 Mar)
   └ Remove from: Bricqer | ID: 7167984d...

Reply "approve all" to process, or I can approve individually.
```

### No pending removals:
```
All clear — no pending minifig removals.
```

## Rules

- Always approve removals promptly — delays mean the item stays listed on both platforms
- If approval fails, report the error and suggest Chris checks manually
- After approval, confirm what was removed and from where
- If Chris says "approve removals" or "approve all", use the bulk-approve endpoint
