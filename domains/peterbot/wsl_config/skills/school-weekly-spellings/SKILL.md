---
name: school-weekly-spellings
description: Weekly spelling list post for Max and Emmie
trigger:
  - "spellings this week"
  - "spelling words"
  - "what are the spellings"
  - "this weeks spellings"
scheduled: true
conversational: true
channel: "#peter-chat"
whatsapp: true
---

# Weekly Spellings

## Purpose
Post this week's spelling words for both children every Monday morning.
Also responds to on-demand requests about spellings.

## Schedule
- Monday 07:30 UK

## Data Access

### Scheduled mode
Pre-fetcher `get_school_data()` injects data into context automatically.

### Conversational mode (ad-hoc requests)
If no pre-fetched data is in context, query Supabase directly via MCP:

```sql
-- Calculate current academic week: ((current_date - '2025-09-04') / 7) + 1
-- Then query spellings for that week:
SELECT child_name, words, phoneme, year_group
FROM school_spellings
WHERE academic_year = '2025-26'
  AND week_number = <calculated_week>;

-- Optionally fetch upcoming school events:
SELECT event_name, event_date, event_type, child_name, notes
FROM school_events
WHERE event_date >= current_date
ORDER BY event_date LIMIT 10;
```

The `words` column is a JSON array of strings. `phoneme` may be null (Max's class doesn't always have one).

## Pre-fetched Data Structure

```json
{
  "spellings": {
    "week_number": 22,
    "children": {
      "Emmie": {
        "words": ["grammar", "increase", "interest", "library", "natural", "probably", "promise", "recent", "wrong", "ferry", "error", "redder"],
        "phoneme": "r",
        "year_group": "Year 4"
      },
      "Max": {
        "words": ["cold", "gold", "hold", "told"],
        "year_group": "Year 2"
      }
    }
  },
  "today_events": [...],
  "upcoming_events": [...],
  "date": "2026-03-02"
}
```

## Output Format

```
**Spellings This Week** (Week {week_number})

**Emmie** (Year 4) - Phoneme: _{phoneme}_
1. grammar  2. increase  3. interest
4. library  5. natural  6. probably
7. promise  8. recent  9. wrong
10. ferry  11. error  12. redder

**Max** (Year 2)
1. cold  2. gold  3. hold  4. told

Practice 10 mins, twice this week!
```

**If no spellings found for a child:**
Show "No spellings loaded for {child} this week - check class email"

## Guidelines
- Number the words for easy reference
- Group in rows of 3-4 for readability
- Show the phoneme/pattern if available
- Keep it brief and scannable
- WhatsApp format: use *bold* not **bold**
- If upcoming school events exist, add a brief "This week at school:" section at the bottom
