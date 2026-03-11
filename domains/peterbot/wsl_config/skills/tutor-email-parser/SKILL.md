# Tutor Email Parser (11+ Mate)

## Purpose
Every Tuesday evening, parse the tutor's email to:
1. Identify the subject/topic covered in this week's lesson
2. Extract the homework assigned
3. Update 11+ Mate with the tutor topic and homework details
4. Post a summary to Discord

## Schedule
- Tuesday 19:00 UK

## Pre-fetcher
`get_tutor_email_data()` — searches Gmail for tutor emails from the last 7 days.

Returns:
- `data.email` — most recent email with `id`, `subject`, `from`, `date`, `body`, `gmail_link`
- `data.all_emails` — all matching emails (for context)
- `data.count` — number of emails found
- `data.no_tutor_email` — true if no emails found

## Gmail Search Queries
The data fetcher searches for:
- Subject containing "tutor", "homework", or "lesson" + child names
- Emails from known tutor senders

**To update the tutor's email address**: Edit the search queries in `data_fetchers.py` → `get_tutor_email_data()`.

## Processing Steps

When you receive the email data:

### 1. Parse the Email
Read the email body and extract:
- **Topic**: What subject/topic was covered (e.g. "Fractions", "Comprehension")
- **Subject area**: Maths, English, or Reasoning
- **Homework**: What homework was assigned, with details
- **Student**: Which child the email is about (Emmie or Max)

### 2. Log the Tutor Topic
For each student mentioned, call the 11+ Mate API:

```bash
curl -s -X POST "https://modjoikyuhqzouxvieua.supabase.co/functions/v1/practice-schedule-manage" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA" \
  -d '{
    "action": "set-tutor-topic",
    "service_key": "psk_11plusmate_tutor_2026",
    "family_code": "HADLEY",
    "student_id": "<STUDENT_ID>",
    "week_start": "<MONDAY_DATE_YYYY-MM-DD>",
    "topic": "<topic-slug>",
    "subject": "<maths|english|reasoning>",
    "notes": "<homework summary> | Gmail: <gmail_link>"
  }'
```

**Student IDs:**
- **Emmie**: `a5677d2f-9614-4504-94a2-4dae933af2c1` (Year 5, tutor_day: 0 = Monday)
- **Max**: `2d204872-bfaa-4577-bd16-c07863b52cd1` (Year 4, tutor_day: 0 = Monday)

**Week start**: Calculate this week's Monday (YYYY-MM-DD format).

**Topic slug**: Lowercase, hyphenated (e.g. "fractions", "creative-writing", "verbal-reasoning").

### 3. Update Homework Slot Notes
Update the tutor_homework schedule slot with the homework summary:

```bash
curl -s -X POST "https://modjoikyuhqzouxvieua.supabase.co/functions/v1/practice-schedule-manage" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA" \
  -d '{
    "action": "upsert",
    "service_key": "psk_11plusmate_tutor_2026",
    "family_code": "HADLEY",
    "student_id": "<STUDENT_ID>",
    "day_of_week": <TUTOR_DAY_NUMBER>,
    "slot_order": 2,
    "activity_type": "tutor_homework",
    "subject": "<subject>",
    "duration_minutes": 30,
    "notes": "<homework summary>\nGmail: <gmail_link>"
  }'
```

**Tutor day**: Both Emmie and Max have `tutor_day: 0` (Monday). Use `day_of_week: 1` (Tuesday) for the homework slot since homework is set on tutor day (Tuesday evening).

### 4. Save to Second Brain
Save the parsed tutor info for future reference:
```bash
curl -s -X POST "http://172.19.64.1:8100/brain/save" \
  -H "Content-Type: application/json" \
  -d '{"source": "<parsed content>", "note": "Tutor session: <topic> for <student>", "tags": "tutor,11plus,<student>"}'
```

## Output Format

```
📚 **Tutor Email Parsed** — {date}

**{Student Name}**
📖 Topic: {topic} ({subject})
📝 Homework: {homework summary}
🔗 [View email]({gmail_link})

✅ Logged to 11+ Mate — allocator will use "{topic}" for homework papers this week.
```

**If no tutor email found:**
```
📚 **Tutor Email Parser** — No tutor email found this week.
Check Gmail search queries if the tutor sent an email that wasn't picked up.
```

## Rules
- If `data.no_tutor_email` is true, output the "not found" message
- Always log to both 11+ Mate AND Second Brain
- Include the Gmail link in the homework slot notes
- Topic slug must be lowercase-hyphenated (e.g. "number-sequences" not "Number Sequences")
- If the email mentions multiple students, process each one separately
- If you can't determine the topic/homework from the email, post the email snippet and ask Chris

## Conversational
Yes — Chris can ask:
- "What did the tutor cover this week?"
- "Parse the tutor email"
- "Update tutor topic for Emmie"
