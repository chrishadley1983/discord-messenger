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
- **Windows/Drive paths in a message** — e.g. `G:\My Drive\...\<name>.<ext>`, any `[A-Z]:\...` path, or `/mnt/g/...`. These are Chris's Google Drive on Windows. Peter runs in WSL and CANNOT read them directly. The peter-channel forwarder will usually pre-rewrite these into a `[Google Drive file: <filename>...]` hint — treat that hint as a drive-search trigger.

## Handling Windows / Google Drive Paths

When the user message contains a Windows path to a media file (or the forwarder-injected `[Google Drive file: <filename>...]` hint):

1. Extract just the filename (e.g. `chrome_e3kc58HevZ.png`) — ignore the directory.
2. `GET /drive/search?q=<filename>` via Hadley API.
3. If exactly one plausible match: `curl -o /tmp/<filename> "http://172.19.64.1:8100/drive/file?file_id=<id>"` to fetch the **actual bytes** into `/tmp/`, then `Read` the `/tmp/` path to view/analyse. Do NOT use `/drive/download` to fetch bytes — it returns metadata JSON, not the file.
4. If multiple matches: show the top 2-3 and ask which one, OR pick the one whose name matches exactly and mention the others.
5. **If zero matches or the lookup fails: reply on Discord saying so clearly** — e.g. `Couldn't find "<filename>" in your Drive — can you re-share it or check the filename?`. Never silently drop the request.
6. Never attempt `Read()` on a `G:\...` or `/mnt/g/...` path — it will fail with a 400 image error. Always go through `/drive/search` → `/drive/file` → `/tmp/<name>` → `Read`.
7. Sanity-check the downloaded file before `Read`ing it as an image: `file /tmp/<name>` — if it says "JSON text data" or the size is <1KB, something went wrong (probably hit `/drive/download` instead of `/drive/file`). Tell Chris what happened rather than letting `Read` hit a 400.

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
- `GET /drive/download?file_id=<id>` — **Metadata + share link only** (returns JSON, NOT bytes). Use when Chris wants a link to send or share.
- `GET /drive/file?file_id=<id>` — **Raw bytes** of a file (images, PDFs, etc.). Use this when you need to actually view or process the file. Native Google types (Docs/Sheets/Slides) return 415 — use `/drive/export` instead.
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
