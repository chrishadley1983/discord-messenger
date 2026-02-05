# Drive Search

## Purpose
Find documents in Google Drive by name or content.

## Triggers
- "find document", "find doc", "search drive"
- "where's the {document}"
- "find the {topic} doc"
- "show me {filename}"
- "drive search {query}"

## Schedule
None (conversational only)

## Data Source
Google Drive API via MCP server

## Parameters
Extract from user message:
- `query` - search terms (title or content)
- `type` - document type filter (optional): doc, sheet, slides, pdf, folder
- `modified` - date filter (optional): "this week", "last month"
- `owner` - owner filter (optional)

## Output Format

**If results found:**
```
📁 Found {count} files matching "{query}":

1. **{filename}**
   📄 Google Doc • Modified {date}
   📂 {folder path}

2. **{filename}**
   📊 Google Sheet • Modified {date}
   📂 {folder path}

3. **{filename}**
   📑 PDF • Modified {date}
   📂 {folder path}
```

**If no results:**
```
📁 No files found matching "{query}"

Try:
- Different keywords
- Check spelling
- Broader search terms
```

## Icons by Type
- 📄 Google Doc
- 📊 Google Sheet  
- 📽️ Google Slides
- 📑 PDF
- 📁 Folder
- 📎 Other

## Guidelines
- Show max 5 results initially
- Include folder path for context
- Show modification date (relative: "yesterday", "2 days ago")
- If exact filename match, show that first
- For ambiguous queries, ask clarifying questions
- Support natural language: "the presentation from last week"

## Conversational
Yes - follow-ups:
- "Open the first one"
- "Show me more results"
- "What's in that doc?"
- "Find sheets only"
- "Anything more recent?"

## Example Interaction
**User:** "Find the Q4 budget doc"
**Peter:** 📁 Found 3 files matching "Q4 budget":

1. **Q4 Budget 2025 - Final**
   📊 Google Sheet • Modified 2 days ago
   📂 Finance / Budgets

2. **Q4 Budget Planning Notes**
   📄 Google Doc • Modified last week
   📂 Finance / Planning

3. **Q4 Budget Presentation**
   📽️ Google Slides • Modified 3 weeks ago
   📂 Finance / Presentations

Want me to open or summarize any of these?
