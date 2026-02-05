# Email Summary

## Purpose
Provide a summary of unread emails and inbox status.

## Triggers
- "emails", "inbox", "any emails", "check email", "email summary"
- "what's in my inbox", "unread messages"

## Schedule
- 08:00 UK daily (part of morning-briefing)

## Data Source
Gmail API via MCP server (read-only)

## Pre-fetcher
`get_email_summary_data()` - fetches:
- Unread count
- Recent emails (last 24h) with: sender, subject, snippet, time
- Priority/important flagged emails

## Output Format

**If unread emails exist:**
```
📧 **{count} unread emails**

**Priority:**
• {sender}: {subject} ({time ago})

**Recent:**
• {sender}: {subject} ({time ago})
• {sender}: {subject} ({time ago})
```

**If inbox is clear:**
```
📧 Inbox clear - no unread emails
```

## Guidelines
- Group by priority first, then chronological
- Show max 5 recent emails in summary
- Use relative time ("2h ago", "yesterday")
- Don't include full email bodies - just subject/snippet
- For scheduled runs, skip if no unread emails (no Discord post)

## Conversational
Yes - user can ask follow-up questions like:
- "What's the email from {sender} about?"
- "Any emails about {topic}?"
- "Show me more"
