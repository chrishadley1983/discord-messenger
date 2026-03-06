---
name: property-valuation
description: Monthly home valuation estimate using HM Land Registry House Price Index
trigger:
  - "how much is the house worth"
  - "property value"
  - "house value"
  - "home valuation"
  - "what's our house worth"
  - "house price"
scheduled: true
conversational: true
channel: "#peterbot"
whatsapp: false
---

# Property Valuation

## Purpose

Monthly estimate of the value of 47 Correnden Road, TN10 3AU using the HM Land Registry UK House Price Index for Tonbridge & Malling (detached properties).

## Property Details

- **Address**: 47 Correnden Road, Tonbridge, TN10 3AU
- **Purchase price**: £507,500
- **Purchase date**: November 2015
- **Property type**: Detached, Freehold
- **HPI region**: tonbridge-and-malling
- **HPI at purchase (Nov 2015, Detached)**: 70.1

## Data Source

HM Land Registry UK HPI API (free, open data, no auth required):

```bash
# Get latest available month — try current month minus 2 (typical lag)
curl -s "https://landregistry.data.gov.uk/data/ukhpi/region/tonbridge-and-malling/month/YYYY-MM.json"
```

The response includes `housePriceIndexDetached` and `averagePriceDetached`.

If the requested month returns 404, try the previous month (data has ~2 month lag).

## Calculation

```
estimated_value = 507500 * (latest_detached_hpi / 70.1)
```

Also extract from the response:
- `averagePriceDetached` — area average for context
- `housePriceIndex` — overall index (all property types)
- `averagePrice` — overall average price

## Output Format (Scheduled)

```
PROPERTY VALUATION — March 2026

47 Correnden Road, TN10 3AU

Estimated value: £XXX,XXX
Change since purchase: +XX.X% (+£XXX,XXX)
Monthly change: +/-X.X%

Area context (Tonbridge & Malling):
  Avg detached: £XXX,XXX
  Avg all types: £XXX,XXX

Data: HM Land Registry HPI (Month YYYY)
```

## Output Format (Conversational)

When asked "how much is the house worth":

1. First check Second Brain for the latest saved valuation
2. If the saved data is from the current or previous month, use it
3. If older, fetch fresh data from the API and update Second Brain

Reply conversationally with the estimate, change since purchase, and area context.

## Updating Second Brain

After fetching new data, save to Second Brain to replace the previous entry:

```
mcp__second-brain__save_to_brain(
  content="# Property Valuation — 47 Correnden Road, TN10 3AU\n\n## Current Estimate\n- Estimated value: £XXX,XXX (as of Month YYYY)\n- Method: HM Land Registry UK HPI (Tonbridge & Malling, Detached)\n\n## Purchase Details\n- Purchase price: £507,500\n- Purchase date: November 2015\n...",
  tags="property,home,finance,valuation"
)
```

## Schedule

Monthly on the 1st at 10:00 UK. HPI data has ~2 month lag so we fetch the latest available.

## Logic

1. Calculate target month: current month minus 2
2. Fetch HPI data for that month
3. If 404, try month minus 3
4. Extract `housePriceIndexDetached`
5. Calculate: `estimated_value = 507500 * (hpi / 70.1)`
6. Compare with previous month's saved value (search Second Brain)
7. Format and post
8. Save updated valuation to Second Brain

## Rules

- Always show the data month (e.g. "Data: HM Land Registry HPI (Dec 2025)") so it's clear how recent it is
- Round estimated value to nearest £1,000
- Show percentage change since purchase and absolute £ change
- If data hasn't updated since last check, say so rather than re-posting the same number
