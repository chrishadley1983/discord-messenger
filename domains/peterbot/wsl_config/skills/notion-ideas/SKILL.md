# Notion Ideas

## Purpose
Browse and add to the "Ideas Backlog" database.

## Triggers
- "ideas backlog", "my ideas", "idea list"
- "what ideas do I have"
- "show ideas", "browse ideas"
- "idea:" (prefix to add new idea)

## Schedule
None (conversational only)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/notion/ideas`

## Pre-fetcher
`get_notion_ideas_data()` - fetches:
- Recent ideas (last 20)
- Properties: title, category/tags, status, created date
- Sorted by: created date (newest first)

## Output Format

**Viewing ideas:**
```
💡 **Ideas Backlog** ({count} ideas)

**Recent:**
• {idea title} [{category}] - {created date}
• {idea title} [{category}] - {created date}
• {idea title} [{category}] - {created date}

**By Category:**
• Business: {count}
• Tech: {count}
• Personal: {count}
```

**After adding:**
```
💡 Added to Ideas Backlog:
"{idea title}"

Category: {category}
Created: just now
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Show newest ideas first
- Group by category if requested
- When adding, auto-detect category from content if possible
- Support search: "ideas about {topic}"
- Don't duplicate existing ideas (check title similarity)

## Adding Ideas
User can add ideas with:
- "idea: {description}"
- "add to ideas: {description}"
- "save this idea: {description}"

## Conversational
Yes - follow-ups:
- "Show business ideas"
- "Add this: {new idea}"
- "Delete/archive {idea}"
- "Expand on {idea}" (→ starts brainstorming)

## Related Skills
- `notion-add-idea` - explicit add skill (same functionality)
