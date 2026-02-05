# Email Search

## Purpose
Search emails by sender, subject, or content.

## Triggers
- "find email from {person}"
- "email about {topic}"
- "search emails for {query}"
- "emails from {sender}"
- "did {person} email me"

## Schedule
None (conversational only)

## Data Source
Gmail API via MCP server (read-only)

## Parameters
Extract from user message:
- `from:` - sender email or name
- `subject:` - subject line keywords
- `query` - general search terms
- `after:` / `before:` - date range (optional)

## Output Format

**If results found:**
```
📧 Found {count} emails matching "{query}":

1. **{subject}**
   From: {sender} • {date}
   {snippet...}

2. **{subject}**
   From: {sender} • {date}
   {snippet...}
```

**If no results:**
```
📧 No emails found matching "{query}"
```

## Guidelines
- Show max 5 results initially
- Include snippet (first ~100 chars of body)
- Offer to show more or read full email
- If ambiguous sender, search both name and likely email patterns
- Support natural date ranges: "last week", "this month", "in January"

## Conversational
Yes - follow-ups:
- "Show me more"
- "Read the first one"
- "What about from {other person}?"
- "Anything more recent?"

## Example Interaction
**User:** "Did Sarah email me about the meeting?"
**Peter:** 📧 Found 2 emails from Sarah about meetings:

1. **Re: Team sync Thursday**
   From: sarah@company.com • Yesterday
   "Hi Chris, confirming 2pm works for me..."

2. **Meeting notes - Q4 planning**
   From: sarah@company.com • 3 days ago
   "Attached are the notes from our planning..."

Want me to open either of these?
