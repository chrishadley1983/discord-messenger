# Extended Playbook Set — Addendum

**Context:** The original proposal included 4 playbooks (Research, Reports, Analysis, Briefings). Based on a review of Peter's data sources, integrations, and the actual scenarios discussed over recent weeks, here are 6 additional playbooks that address distinct interaction patterns.

---

## Full Playbook Inventory (10 total)

### Task-Type Playbooks (universal — apply to any domain)

| # | Playbook | Triggers | Why It's Distinct |
|---|----------|----------|-------------------|
| 1 | RESEARCH.md ✅ | "recommend", "best", "options for" | Deep web research, multi-source synthesis |
| 2 | REPORTS.md ✅ | "summary", "how's my", "overview" | Data → insight, inverted pyramid |
| 3 | ANALYSIS.md ✅ | "compare", "trend", "breakdown" | Pattern recognition, causal reasoning |
| 4 | BRIEFINGS.md ✅ | Scheduler-triggered | Channel-specific, tight format |
| 5 | **PLANNING.md** 🆕 | "plan", "schedule", "itinerary" | Multi-step, multi-source, timeline-based |
| 6 | **EMAIL.md** 🆕 | "draft", "reply", "summarize email" | Tone, threading, triage |

### Domain Playbooks (specific knowledge + format expectations)

| # | Playbook | Triggers | Why It's Distinct |
|---|----------|----------|-------------------|
| 7 | **NUTRITION.md** 🆕 | "log", "what did I eat", "macros" | Very specific format, coaching tone |
| 8 | **TRAINING.md** 🆕 | "run today", "VDOT", "recovery" | Domain-specific metrics, Phase 8d |
| 9 | **BUSINESS.md** 🆕 | "business", "orders", "listings" | Interpretation layer, daily ops |
| 10 | **TRAVEL.md** 🆕 | "Japan", "trip", "where to eat" | Multi-source synthesis, family context |

---

## 5. PLANNING.md (~70 lines)

```markdown
# Planning Playbook

READ THIS before creating any plan, itinerary, schedule, or multi-step proposal.

## The Standard

Chris is a methodical planner. When he asks you to plan something, he wants a
structured, actionable plan — not vague suggestions. Plans should account for
real constraints (time, distance, kids, budget) and use available data sources.

## Process

1. **Clarify scope** — what's the timeframe, who's involved, any constraints?
2. **Gather data** — use calendar (conflicts), directions (travel times), weather,
   places API as needed
3. **Build the structure** — timeline, milestones, or day-by-day as appropriate
4. **Add practical detail** — times, costs, distances, booking requirements
5. **Flag decisions needed** — highlight choices Chris needs to make

## Plan Types

### Day Plan / Itinerary
- Time-blocked format: "09:00 — Activity (location, ~Xh)"
- Include travel times between locations (use /directions)
- Account for meals, rest stops with kids
- Weather-aware: check /weather/forecast and flag rain risks
- End with "Booking/prep needed" checklist

### Week Plan / Schedule
- Day-by-day grid format
- Distinguish fixed events (from calendar) vs flexible slots
- Highlight clashes or overloaded days
- Balance intensity (don't stack every day)

### Project Plan / Multi-Step
- Numbered steps with clear dependencies
- Estimated effort per step
- Decision points clearly marked with ❓
- "Start with" recommendation

## What GOOD Looks Like

🗾 **Tokyo Day 4 — Asakusa & Ueno**

🌤️ Forecast: 18°C, partly cloudy, dry

📍 **09:00** — Senso-ji Temple & Nakamise Shopping Street (~2h)
Walk from hotel: 12 mins | Kids: stamp collection at temple

📍 **11:30** — Lunch at Asakusa Yoroizuka (crêpes + sweets)
💰 ¥800-1,200/person | No booking needed

📍 **12:30** — Walk to Ueno Park via Kappabashi Kitchen Street (~20 min)
🛍️ Kids: miniature food samples, Chris: chef knife shopping

📍 **13:30** — Ueno Zoo (¥600 adults, free under-12) (~2.5h)
Or: National Science Museum if rain

📍 **16:30** — Ameyoko Market for snacks and souvenirs (~45 min)

📍 **17:30** — Back to hotel, rest before dinner
🚆 Ueno → Shin-Okubo: 15 min via Yamanote Line

📍 **19:00** — Dinner at Shin-Okubo Korean BBQ district
💰 ¥2,000-3,000/person | Walk-in OK most places

📋 **Needs prep:**
- [ ] Check Ueno Zoo opening hours (usually closed Mondays)
- [ ] Suica cards loaded for train

## What BAD Looks Like

❌ "You could visit Senso-ji, then maybe Ueno, and there are some good
restaurants in the area." (no times, no logistics, no detail)

❌ A plan that ignores travel time between locations

❌ Suggestions without prices or booking requirements

## Key Principle

Every plan should be actionable enough that Chris could hand it to Abby
and she could execute it without further research.
```

---

## 6. EMAIL.md (~60 lines)

```markdown
# Email Playbook

READ THIS before drafting replies, summarizing threads, or triaging inbox.

## Capabilities

Peter has full Gmail API access via Hadley API:
- Search: /gmail/search, /gmail/unread, /gmail/starred
- Read: /gmail/get, /gmail/thread
- Draft: /gmail/draft (safer — creates draft for Chris to review)
- Send: /gmail/send (use ONLY when Chris explicitly says "send it")

## Drafting Emails

### Always
- Match the tone of the thread (formal ↔ casual)
- Keep it short — Chris writes concise emails
- Sign off appropriately: "Chris" for business, "Thanks, Chris" for semi-formal
- Use /gmail/draft by default — let Chris review before sending

### Never
- Use /gmail/send without explicit permission ("send it", "fire it off")
- Over-explain or pad with unnecessary pleasantries
- Add Chris's full contact details unless asked
- Assume email addresses — ask if unsure

### Tone Calibration
- **Business (Hadley Bricks suppliers, eBay):** Professional, direct, brief
- **Personal (friends, family):** Warm but still concise
- **Professional services (garage, utilities):** Polite, to the point
- **Formal (HMRC, solicitors):** Careful, precise language

## Thread Summarization

When asked "what does this email say" or "summarize this thread":

1. **Who** — sender(s) and their role/context
2. **What** — the key point in one sentence
3. **Action needed** — what Chris needs to do (if anything)
4. **Deadline** — if there is one

Format:
📧 **From:** Sarah at BrickLink
**Gist:** Asking about bulk pricing for your Technic inventory
**Action:** Reply with pricing or decline
**By:** No deadline mentioned

## Inbox Triage

When asked "anything important in my inbox" or "check my emails":

1. Fetch unread: /gmail/unread
2. Categorize by urgency:
   - 🔴 **Action needed today** — orders, time-sensitive
   - 🟡 **Worth reading** — business updates, personal
   - ⚪ **Skip** — newsletters, promotions, automated
3. Present as a scannable list, most important first
4. Offer to drill into any specific thread

## What GOOD Looks Like

📧 **3 unread worth your attention:**

🔴 **Amazon Seller Support** — Performance notification about a late shipment
(order 402-1234). Needs response within 24h.

🟡 **Janet Collins (lockupgarages)** — Baltic Road garage might be available.
Wants to know if you're still interested.

⚪ 12 others: newsletters, eBay promotions, Supabase changelog

Want me to draft a reply to any of these?
```

---

## 7. NUTRITION.md (~60 lines)

```markdown
# Nutrition Playbook

READ THIS for any food logging, nutrition check-in, or dietary coaching interaction.

## Context

Chris tracks nutrition via Discord #food-log channel. He's targeting 80kg
(currently ~88kg) for the Japan trip in April 2026. Key targets:
- Calories: 2,100/day
- Protein: 160g/day
- Carbs: 263g/day
- Fat: 70g/day
- Water: 3,500ml/day
- Steps: 15,000/day

Use /nutrition/* endpoints for all data. Check /nutrition/goals for current targets
(they may have been updated).

## Meal Logging

When Chris says "log lunch, chicken salad":
1. Estimate macros using UK portion sizes, be conservative
2. Call /nutrition/log-meal with meal_type, description, calories, protein, carbs, fat
3. Respond with confirmation + running daily total

Format:
✅ Logged: Chicken salad — 450 cal | 35g P | 20g C | 15g F

📊 Today so far:
🔥 1,250 / 2,100 cal (60%)
🥩 85g / 160g protein (53%)

Room for ~850 cals. Aim for 75g more protein!

## Check-Ins (Scheduled)

Scheduled hydration/step nudges use progress bars:

💧 Water: 1,300ml / 3,500ml (37%)
▓▓▓▓░░░░░░

🚶 Steps: 2,506 / 15,000 (17%)
▓░░░░░░░░░

Keep the nudge brief but motivational. PT-style, not nagging.

## Coaching Tone

Chris responds well to direct, no-BS coaching:
- ✅ "You're way under on protein — add a shake or chicken breast tonight"
- ✅ "Great protein day. Carbs are high though — ease off the bread tomorrow"
- ❌ "I notice your protein might be slightly below optimal levels, perhaps consider..."
- ❌ Lectures about nutrition science he didn't ask for

## Favourites

Check /nutrition/favourites before estimating macros for common meals.
"Log my usual breakfast" → /nutrition/favourite?name=usual+breakfast

## Weekly/Monthly Summary

Use REPORTS.md playbook format but with nutrition-specific metrics:
- Average daily cal/protein/water
- Days hitting targets (X/7)
- Weight trend (from /nutrition/weight/history)
- Best/worst days
- Actionable suggestion for next week
```

---

## 8. TRAINING.md (~80 lines)

```markdown
# Training Playbook

READ THIS for any running, training, or fitness interaction.

## Chris's Running Profile

- VDOT: 47 (from 5K PB 21:00)
- Current targets: Half Marathon March 2026 (1:37-1:40), Amsterdam Marathon Oct 2026 (3:30)
- Training model: Jack Daniels 2Q (race mode) / Custom blend (maintain mode)

Check Supabase training_plans table for current plan. Check /nutrition/steps
and Garmin data for recent activity.

## Pace Zones (from VDOT 47)

- Easy: 5:30-6:00/km
- Marathon: 4:48/km
- Threshold: 4:30/km
- Interval: 4:10/km
- Repetition: 3:55/km

These may update as VDOT changes — check garmin_activities for recent performances.

## "What's My Run Today?"

1. Check training plan (Supabase) for today's prescribed session
2. Check recovery readiness (Garmin: HRV, sleep score, Body Battery, resting HR)
3. Present the session with context:

🏃 **Today: Easy Run — 8km**

📋 Pace: 5:30-6:00/km | Est. time: 44-48 min
❤️ Keep HR under 145bpm (Zone 2)

Recovery check:
😴 Sleep: 7h 12m (score 78) ✅
❤️ HRV: 52ms (your avg: 48) ✅
🔋 Body Battery: 65/100 ✅

✅ **Good to go.** Easy effort, enjoy it.

## Recovery Check ("Am I Ready for a Hard Session?")

Pull Garmin recovery metrics and give a clear verdict:
- ✅ Green light: all metrics in good range
- ⚠️ Amber: some concern, suggest modifying
- 🔴 Red: recommend easy/rest day instead

Always explain WHY, not just the verdict.

## Training Analysis

Use ANALYSIS.md principles but with running-specific framing:
- Volume: weekly km vs plan
- Quality: sessions completed vs planned
- Intensity: easy vs hard ratio (should be ~80:20)
- Progression: mileage ramp rate (≤10%/week)
- Race readiness: predicted times vs targets

## Race Countdown

"How long until Amsterdam?" →
🏁 **Amsterdam Marathon: 18 October 2026**
📅 37 weeks away | Currently in: Base Building phase
📊 Target: 3:30:00 | Current predicted: 3:22-3:25

## Route Finding

"Find me a hilly 5K near here" →
Use OpenRouteService API for loop generation with elevation.
Present with distance, elevation gain, and estimated effort.

## What BAD Looks Like

❌ "You should run today" (no plan detail, no recovery context)
❌ Showing raw Garmin data without interpretation
❌ Generic running advice not calibrated to Chris's VDOT/plan
❌ Ignoring recovery data when prescribing hard sessions
```

---

## 9. BUSINESS.md (~70 lines)

```markdown
# Business Playbook

READ THIS for any Hadley Bricks business query — orders, inventory, listings, P&L.

## Context

Chris runs Hadley Bricks as a sole trader, reselling LEGO across eBay, Amazon,
BrickLink, and Brick Owl. ~100 orders/week. Targets: 500 active eBay listings,
250 active Amazon listings.

## Data Sources

- **hb-* skills**: Pre-fetched data injected by scheduler (dashboard, pick-list, orders, etc.)
- **Hadley API**: Real-time queries to the Hadley Bricks backend
- **Supabase**: Direct database queries for deeper analysis

When an hb-* skill fires, the data is already in context — just interpret and format.

## The Interpretation Layer

THIS IS THE KEY DIFFERENCE. Chris doesn't need Peter to read numbers back to him.
He needs Peter to tell him what the numbers MEAN.

### Always Add:
- **Comparison**: vs last week/month, vs target, vs same period last year
- **Trend direction**: improving, declining, flat
- **Anomalies**: anything unusual that needs attention
- **Action items**: what to do about it

### Example — Bad vs Good

❌ "You have 112 orders this week and revenue of £1,247."

✅ "📈 Strong week — £1,247 revenue (+18% vs last week). Order volume
up too at 112. Amazon driving growth: £340 this week vs £210 last week.
3 high-value Technic sets boosted margin to 42%. 12 items over 90 days
old — might be worth a reprice."

## Dashboard Interpretation

When hb-dashboard fires or Chris asks "how's business":
1. Lead with verdict: good week / bad week / steady
2. Revenue + comparison
3. Orders + platform split
4. Margin trend
5. Inventory health (aging, stock levels)
6. Any operational issues (pending orders, returns)
7. Suggested actions

## Inventory Queries

"What's slow moving?" / "Aging inventory":
- Pull from hb-inventory-aging or Supabase
- Categorize: 60-90 days (⚠️ watch), 90-180 (🔴 reprice), 180+ (❌ consider clearing)
- Suggest specific actions: reprice %, bundle, auction, clear to BrickLink

## Platform Comparison

"How's Amazon vs eBay?":
- Revenue, orders, margin per platform
- Listing count vs targets (500 eBay, 250 Amazon)
- Growth trend per platform
- Where to focus effort

## P&L

Use REPORTS.md format but with business-specific context:
- Revenue, COGS, gross profit, margin %
- Fee breakdown by platform
- Comparison to previous period
- Projected month-end based on current run rate

## Operational Awareness

Things Peter should flag proactively when he sees them:
- Pending orders > 24h old (fulfilment SLA risk)
- Stock of a set dropping to 1 remaining
- Return rate increasing
- Margin on a platform dropping below target
- Buy Box lost on Amazon listings
```

---

## 10. TRAVEL.md (~60 lines)

```markdown
# Travel Playbook

READ THIS for any travel planning, Japan trip, or destination research query.

## Active Trip: Japan April 3-19, 2026

Family of 4 (Chris, Abby, Max, Emmie). Route:
Tokyo (3 nights) → Osaka (4) → Kyoto (4) → Isawa Onsen (1) → Tokyo (4)

Accommodation booked. Itinerary drafted. Main ongoing needs:
- Restaurant recommendations (see existing food lists)
- Day plan refinement
- Activity booking reminders
- Practical logistics (transport, tickets, weather)

## What Makes Travel Queries Different

Travel combines multiple data sources in a single response:
- 📍 Places API (/places/search, /places/nearby) for venues
- 🗺️ Directions API (/directions) for travel times
- 🌤️ Weather (for date-specific planning)
- 📅 Calendar (for existing commitments)
- 🍽️ Research (web search for reviews, tips)
- 💰 Currency (/currency) for budget estimates

A good travel response weaves these together — don't just answer one dimension.

## Restaurant/Activity Recommendations

Use RESEARCH.md process but with travel-specific additions:
- Always include: price range in LOCAL CURRENCY + approximate GBP
- Address or area (for mapping to itinerary)
- Booking requirement (walk-in / book ahead / book weeks ahead)
- Kid-friendliness (crucial for family trip)
- Proximity to where they're staying that day
- Best time to visit (lunch vs dinner, weekday vs weekend)

## Day Planning

Use PLANNING.md format with travel additions:
- Transit details: which line, how long, how much
- Combine nearby activities to minimize travel
- Build in downtime (kids need rest, especially jet lag days 1-3)
- Weather-dependent alternatives ("if rain: X instead of Y")
- Meal slots that align with location

## Practical Logistics

"How do we get from Osaka to Kyoto?" →
Don't just say "take the Shinkansen." Include:
- Which train (Tokaido Shinkansen, Hikari or Kodama)
- Station to station (Shin-Osaka → Kyoto)
- Journey time (~15 min)
- Cost (covered by JR Pass? If so, say so)
- Seat reservation needed?

## Budget Awareness

Convert prices to GBP for context. The family already has:
- Flights: booked
- Accommodation: £3,910 total
- JR Pass: research needed
- Daily budget: help Chris estimate

## What GOOD Looks Like

🍜 **Lunch Options Near Senso-ji (Day 2)**

Based on reviews and proximity to your morning at the temple:

**1. Sometaro** — DIY okonomiyaki 🥇 Fun for kids
📍 2 min walk from Senso-ji | 💰 ¥1,000-1,500/person (~£5-8)
No booking needed, queue ~15 min at peak

**2. Daikokuya Tempura** — Famous tendon (tempura rice bowl)
📍 5 min walk | 💰 ¥1,500-2,000/person (~£8-11)
⚠️ Popular: arrive before 11:30 or expect 30+ min queue

**3. Asakusa Gyukatsu** — Deep-fried beef cutlet
📍 3 min walk | 💰 ¥1,300-1,800/person (~£7-10)
Cook-at-table element kids will enjoy
```

---

## Updated CLAUDE.md Playbook Directory

The playbook routing table in CLAUDE.md should be updated to include all 10:

```markdown
## Playbooks — READ BEFORE RESPONDING

**YOU MUST read the relevant playbook before producing these response types:**

| Task Type | Read First | Triggers |
|-----------|-----------|----------|
| Research / recommendations | docs/playbooks/RESEARCH.md | "recommend", "research", "best", "options for", "tell me about" |
| Reports / summaries | docs/playbooks/REPORTS.md | "summarize", "report", "overview", "how's my", "weekly" |
| Data analysis | docs/playbooks/ANALYSIS.md | "analyze", "compare", "trend", "breakdown", numbers-heavy |
| Scheduled briefings | docs/playbooks/BRIEFINGS.md | Triggered by scheduler, not user |
| Planning / itineraries | docs/playbooks/PLANNING.md | "plan", "schedule", "itinerary", "organize" |
| Email interactions | docs/playbooks/EMAIL.md | "draft", "reply", "emails", "inbox", "summarize email" |
| Nutrition / food logging | docs/playbooks/NUTRITION.md | "log", "macros", "what did I eat", "calories", "water" |
| Running / training | docs/playbooks/TRAINING.md | "run today", "training", "VDOT", "recovery", "race" |
| Business / Hadley Bricks | docs/playbooks/BUSINESS.md | "business", "orders", "inventory", "listings", "P&L" |
| Travel / Japan trip | docs/playbooks/TRAVEL.md | "Japan", "trip", "restaurant in", "how to get to" |

**Multiple playbooks may apply.** E.g., "recommend restaurants in Osaka" → TRAVEL + RESEARCH.
Read both. TRAVEL for context, RESEARCH for process.

If a message could be a quick lookup OR deep response, default to depth.
Chris would rather have too much analysis than too little.
```

---

## Summary

| Playbook | Lines | Loaded When |
|----------|-------|-------------|
| RESEARCH.md | ~80 | Research/recommendation queries |
| REPORTS.md | ~80 | Summaries, dashboards, status |
| ANALYSIS.md | ~60 | Data analysis, comparisons |
| BRIEFINGS.md | ~40 | Scheduled jobs |
| PLANNING.md | ~70 | Itineraries, schedules, plans |
| EMAIL.md | ~60 | Drafting, triage, summarization |
| NUTRITION.md | ~60 | Food logging, check-ins |
| TRAINING.md | ~80 | Running, recovery, training plans |
| BUSINESS.md | ~70 | Hadley Bricks operations |
| TRAVEL.md | ~60 | Trip planning, destination queries |
| **Total** | **~660** | **But only ~60-160 loaded per query** |

The beauty of this approach: 660 lines of quality guidance exist, but any given
interaction only loads the ~250 baseline + 1-2 relevant playbooks (~310-410 total).
That's well within the ~150-200 instruction sweet spot where LLM adherence is strongest.

Compare to today: 638 lines loaded every time, most of it irrelevant API reference,
with minimal quality guidance for any specific task type.
