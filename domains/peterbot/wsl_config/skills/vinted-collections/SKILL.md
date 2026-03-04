# Vinted Collections

Check for Vinted parcels ready to collect from locker/pickup points.

## Triggers
- "vinted collections"
- "ready to collect"
- "check vinted"
- "vinted parcels"
- "any parcels to collect"

## Data Source

Pre-fetched via `vinted-collections` data fetcher (Hadley API `/vinted/collections`).

The API searches Gmail for Vinted "ready to collect" notifications, parses item name, delivery service, and pickup location, and deduplicates against previously reported items.

## Output Format

Compact bullet list with pipe separators. Separate NEW items from previously reported.

```
**Vinted Collections** — {date}
{new_count} new items ready to collect:

**NEW:**
- {item} | {service} | {location} ({date})
- {item} | {service} | {location} ({date})

**Previously reported:**
- {item} | {service} | {location} ({date})
```

## Rules

- If `new_count` is 0 and `total_count` is 0: "No Vinted parcels waiting for collection."
- If `new_count` is 0 but there are previously reported items: "No new parcels, but {n} still waiting."
- Always show the NEW section first if there are new items.
- Keep dates short (e.g., "12 Feb" not the full RFC date string).
- If location is long, truncate to the first meaningful part (postcode area or shop name).
