# Google Drive

## Purpose
Search, create, manage, and organise files in Google Drive.

## Triggers
- "find document", "find doc", "search drive"
- "where's the {document}"
- "find the {topic} doc"
- "show me {filename}"
- "drive search {query}"
- "save to drive", "save this to drive"
- "create a doc", "create a document", "make a doc"
- "upload to drive", "put this on drive"
- "share {document} with {person}"
- "move {document} to {folder}"
- "rename {document}"
- "trash {document}", "delete {document}"
- "recent files", "what's on my drive"
- "drive storage", "how much storage"

## Schedule
None (conversational only)

## Data Sources
All endpoints documented in `hadley_api/README.md` under "Drive".
Base URL: `http://172.19.64.1:8100`

**Read:**
- `GET /drive/search?q={query}` — Search files by name/content
- `GET /drive/recent?limit=10` — Recent files
- `GET /drive/starred` — Starred files
- `GET /drive/shared` — Shared with me
- `GET /drive/download?file_id=<id>` — Download file
- `GET /drive/export?file_id=<id>&mime_type=<type>` — Export Google doc
- `GET /drive/permissions?file_id=<id>` — Get file permissions
- `GET /drive/storage` — Storage quota

**Write:**
- `POST /drive/create?title=<name>&type=<doc|sheet|slides>` — Create file (optional JSON body: `{"content": "<text>", "folder_name": "<name>"}`)
- `POST /drive/folder?name=<name>` — Create folder
- `POST /drive/copy?file_id=<id>&name=<new_name>` — Copy file
- `POST /drive/rename?file_id=<id>&name=<new_name>` — Rename file
- `POST /drive/move?file_id=<id>&folder_id=<id>` — Move file
- `POST /drive/share?file_id=<id>&email=<email>&role=<role>` — Share file
- `POST /drive/trash?file_id=<id>` — Move to trash

## Parameters (Search)
Extract from user message:
- `query` - search terms (title or content)
- `type` - document type filter (optional): doc, sheet, slides, pdf, folder
- `modified` - date filter (optional): "this week", "last month"
- `owner` - owner filter (optional)

## Output Formats

**Search results:**
```
📁 Found {count} files matching "{query}":

1. **{filename}**
   📄 Google Doc • Modified {date}
   📂 {folder path}

2. **{filename}**
   📊 Google Sheet • Modified {date}
   📂 {folder path}
```

**No results:**
```
📁 No files found matching "{query}"

Try:
- Different keywords
- Check spelling
- Broader search terms
```

**File created:**
```
✅ Created **{title}**
📄 Google Doc • {folder name or "My Drive"}
🔗 {link}
```

**File shared/moved/renamed:**
```
✅ **{filename}** shared with {email} (role: {role})
```

**Storage quota:**
```
💾 Drive Storage: {used} / {total} ({percent}%)
```

## Icons by Type
- 📄 Google Doc
- 📊 Google Sheet
- 📽️ Google Slides
- 📑 PDF
- 📁 Folder
- 📎 Other

## Guidelines
- **Never show raw JSON** — only present the formatted human-readable output
- Show max 5 results initially for searches
- Include folder path for context
- Show modification date (relative: "yesterday", "2 days ago")
- If exact filename match, show that first
- For ambiguous queries, ask clarifying questions
- When creating docs with content, confirm the title and folder before creating
- For write operations, confirm success with a link to the file

## Conversational
Yes — follow-ups:
- "Open the first one"
- "Show me more results"
- "What's in that doc?"
- "Find sheets only"
- "Anything more recent?"
- "Share that with {email}"
- "Move it to {folder}"
- "Save that to a doc called {title}"

## Example Interactions

**Search:**
**User:** "Find the Q4 budget doc"
**Peter:** 📁 Found 3 files matching "Q4 budget":

1. **Q4 Budget 2025 - Final**
   📊 Google Sheet • Modified 2 days ago
   📂 Finance / Budgets

2. **Q4 Budget Planning Notes**
   📄 Google Doc • Modified last week
   📂 Finance / Planning

Want me to open or summarise any of these?

**Create with content:**
**User:** "Save that recipe to a Google Doc"
**Peter:** ✅ Created **Mediterranean Chicken Recipe**
📄 Google Doc
🔗 https://docs.google.com/document/d/...

The full recipe has been saved to your Drive.
