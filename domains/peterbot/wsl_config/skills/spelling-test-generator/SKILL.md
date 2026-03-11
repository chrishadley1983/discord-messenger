---
name: spelling-test-generator
description: Process Max's spelling photo, add to DB, and generate the spelling test page
trigger:
  - "max spellings"
  - "max's spellings this week"
  - "here are max's spellings"
  - "spelling test"
  - "generate spelling test"
  - "update spelling test"
  - "max's words this week"
  - "spelling photo"
scheduled: true
conversational: true
channel: "#peterbot"
whatsapp: false
---

# Spelling Test Generator

## Purpose
Process Max's weekly spelling words (from a photo), add them to the database alongside Emmie's existing spellings, and deploy an updated spelling test page.

## When Triggered

### Conversationally (natural language)
Chris sends a photo of Max's spellings (usually a handwritten list from school) along with a trigger phrase. Peter should:

1. **Extract words from the image** — Read the handwritten/printed words from the photo
2. **Extract the phoneme/sound** if visible (e.g., "Sound /f/")
3. **Confirm with Chris** — List the extracted words and ask Chris to confirm before saving
4. **Save to database** — Call the Hadley API to add the spellings
5. **Generate sentences** — Create a sentence for each word and save via the sentences API
6. **Fetch Emmie's spellings** — Query the database for Emmie's current week
7. **Flag if missing** — If Emmie's spellings aren't available for the current week, tell Chris
8. **Confirm test page ready** — The page reads from Supabase automatically, no deploy needed

### Scheduled (Friday reminder)
On Friday at 19:00, remind Chris to send Max's spellings for the week so the test page can be updated for the weekend.

## API Endpoints

### Add spellings
```
POST http://172.19.64.1:8100/spellings/add
Content-Type: application/json

{
  "child_name": "Max",
  "year_group": "Year 2",
  "academic_year": "2025-26",
  "week_number": <current_week>,
  "phoneme": "f",
  "words": ["before", "flag", "coffee", "effort", "gift", "stiff"]
}
```

### Get current week number
```
GET http://172.19.64.1:8100/spellings/current-week
```
Returns: `{"academic_year": "2025-26", "week_number": 20}`

### Add sentences for words
After saving spellings, generate a kid-friendly sentence for each word (with the word used in context) and save them:
```
POST http://172.19.64.1:8100/spellings/sentences
Content-Type: application/json

{
  "sentences": {
    "before": "We need to wash our hands before dinner.",
    "flag": "The pirate ship had a big black flag.",
    "coffee": "Mum likes to drink coffee in the morning.",
    "effort": "She put in a lot of effort to finish her painting.",
    "gift": "He wrapped the gift in shiny paper.",
    "stiff": "The cardboard was too stiff to bend."
  }
}
```
The spelling test page shows these as expandable hints (with the word blanked as `____`).

### Check Emmie's spellings exist
Query Supabase directly via MCP:
```sql
SELECT child_name, words, phoneme, year_group
FROM school_spellings
WHERE academic_year = '2025-26'
  AND week_number = <current_week>
  AND child_name = 'Emmie';
```

## Deployment

The spelling test page is at `hadley-spelling-test.surge.sh`. It reads directly from Supabase so **no HTML regeneration is needed** — once the words and sentences are in the database, the page picks them up automatically.

After adding Max's spellings, just confirm:
- Max's words are saved for the correct week
- Sentences generated and saved for all words
- Emmie's words exist for the same week
- The test page URL: https://hadley-spelling-test.surge.sh

## Output Format

### After processing the photo:
```
📝 **Max's Spellings — Week {week}**
Sound: /{phoneme}/

Words: {word1}, {word2}, {word3}, {word4}, {word5}, {word6}

✅ Saved to database
✅ Emmie's spellings also available (Week {week})
🔗 Test page ready: hadley-spelling-test.surge.sh
```

### If Emmie's spellings are missing:
```
📝 **Max's Spellings — Week {week}**
Words saved ✅

⚠️ Emmie's spellings not found for Week {week} — they may not have been synced yet from the school website. I'll check again on Monday.
```

### Friday reminder format:
```
📝 **Spelling Test Reminder**
Have you got Max's spellings for this week? Send me a photo and I'll update the test page for the weekend!

🔗 Current test: hadley-spelling-test.surge.sh
```

## Guidelines
- Always confirm extracted words before saving (handwriting can be tricky)
- Use the `/spellings/current-week` endpoint to get the correct week number
- Max is in Year 2, academic year 2025-26
- The phoneme/sound is usually shown at the top of the spelling sheet
- If Chris says the words directly (no photo), skip the OCR step and just save them
- Always generate sentences after saving words — keep them simple, age-appropriate, and fun
- Sentences should use the word naturally in context so kids understand meaning
- Also generate sentences for Emmie's words if they don't have sentences yet
