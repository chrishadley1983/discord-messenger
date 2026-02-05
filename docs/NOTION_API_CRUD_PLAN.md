# Notion CRUD & API Review Plan

## Overview

Implement full CRUD operations for Notion (todos and ideas) and review/update any APIs currently lacking create/delete/edit capabilities.

---

## Phase 1: Notion CRUD Implementation

### Current State
- **Endpoints**: 2 (GET only)
  - `GET /notion/todos` - Fetch incomplete tasks
  - `GET /notion/ideas` - Fetch recent ideas (20 max)
- **Client**: `hadley_api/notion_client.py` supports GET and POST but not PATCH/DELETE
- **Skills expect write ops** but have no API backend

### 1.1 Extend Notion Client (`hadley_api/notion_client.py`)

Add PATCH and DELETE support to `_notion_request()`:

```python
async def _notion_request(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    # Existing GET/POST handling...
    elif method == "PATCH":
        response = await client.patch(url, headers=headers, json=data or {}, timeout=10)
    elif method == "DELETE":
        response = await client.delete(url, headers=headers, timeout=10)
```

Add new functions:

| Function | Purpose | Notion API |
|----------|---------|------------|
| `create_todo(title, priority, due, tags)` | Create new todo | POST /databases/{id}/pages |
| `update_todo(page_id, **updates)` | Update status/priority/due | PATCH /pages/{page_id} |
| `delete_todo(page_id)` | Archive todo | PATCH /pages/{page_id} (archived: true) |
| `create_idea(title, category)` | Create new idea | POST /databases/{id}/pages |
| `update_idea(page_id, **updates)` | Update title/category | PATCH /pages/{page_id} |
| `delete_idea(page_id)` | Archive idea | PATCH /pages/{page_id} (archived: true) |

### 1.2 Add API Endpoints (`hadley_api/main.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/notion/todos` | POST | Create new todo |
| `/notion/todos/{todo_id}` | PATCH | Update todo (status, priority, due) |
| `/notion/todos/{todo_id}` | DELETE | Archive todo |
| `/notion/todos/{todo_id}/complete` | POST | Quick-complete (set status=Done) |
| `/notion/ideas` | POST | Create new idea |
| `/notion/ideas/{idea_id}` | PATCH | Update idea (title, category) |
| `/notion/ideas/{idea_id}` | DELETE | Archive idea |

### 1.3 Request/Response Models

```python
# Todos
class TodoCreate(BaseModel):
    title: str
    priority: Optional[str] = None  # High, Medium, Low
    due: Optional[str] = None       # ISO date string
    tags: Optional[List[str]] = None

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None    # Done, In Progress, Not Done
    priority: Optional[str] = None
    due: Optional[str] = None

# Ideas
class IdeaCreate(BaseModel):
    title: str
    category: Optional[str] = None

class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
```

### 1.4 Update Playbooks

Create/update `docs/playbooks/NOTION.md`:

```markdown
# Notion Playbook

## Hadley API Endpoints

### Todos

| Action | Endpoint | Method |
|--------|----------|--------|
| List incomplete | `/notion/todos` | GET |
| Create todo | `/notion/todos` | POST |
| Update todo | `/notion/todos/{id}` | PATCH |
| Complete todo | `/notion/todos/{id}/complete` | POST |
| Delete (archive) | `/notion/todos/{id}` | DELETE |

### Ideas

| Action | Endpoint | Method |
|--------|----------|--------|
| List recent | `/notion/ideas` | GET |
| Create idea | `/notion/ideas` | POST |
| Update idea | `/notion/ideas/{id}` | PATCH |
| Delete (archive) | `/notion/ideas/{id}` | DELETE |
```

---

## Phase 2: Google Tasks CRUD

### Current State
- `GET /tasks/list` - List tasks from default task list
- `POST /tasks/create` - Create new task
- `POST /tasks/complete` - Mark task complete

### 2.1 New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tasks/{task_id}` | GET | Get specific task details |
| `/tasks/{task_id}` | PATCH | Update task (title, notes, due date) |
| `/tasks/{task_id}` | DELETE | Delete task permanently |
| `/tasks/lists` | GET | List all task lists |
| `/tasks/lists/{list_id}` | GET | Get tasks from specific list |

### 2.2 Request Models

```python
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due: Optional[str] = None  # RFC 3339 timestamp
    status: Optional[str] = None  # "needsAction" or "completed"
```

### 2.3 Implementation

```python
@app.get("/tasks/{task_id}")
async def get_task(task_id: str, tasklist: str = "@default"):
    service = get_tasks_service()
    task = service.tasks().get(tasklist=tasklist, task=task_id).execute()
    return task

@app.patch("/tasks/{task_id}")
async def update_task(task_id: str, update: TaskUpdate, tasklist: str = "@default"):
    service = get_tasks_service()
    body = {k: v for k, v in update.dict().items() if v is not None}
    task = service.tasks().patch(tasklist=tasklist, task=task_id, body=body).execute()
    return task

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str, tasklist: str = "@default"):
    service = get_tasks_service()
    service.tasks().delete(tasklist=tasklist, task=task_id).execute()
    return {"deleted": True, "task_id": task_id}

@app.get("/tasks/lists")
async def list_task_lists():
    service = get_tasks_service()
    results = service.tasklists().list().execute()
    return results.get("items", [])
```

### 2.4 Testing

| Test | Input | Expected |
|------|-------|----------|
| Get task | Valid task_id | Returns task details |
| Get task | Invalid task_id | 404 error |
| Update title | task_id + new title | Title updated |
| Update due date | task_id + due | Due date set |
| Delete task | task_id | Task removed |
| List task lists | None | Array of lists |

---

## Phase 3: Google Contacts CRUD

### Current State
- `GET /contacts/search` - Search contacts by name

### 3.1 New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/contacts/{resource_name}` | GET | Get specific contact |
| `/contacts` | POST | Create new contact |
| `/contacts/{resource_name}` | PATCH | Update contact |
| `/contacts/{resource_name}` | DELETE | Delete contact |
| `/contacts/list` | GET | List all contacts (paginated) |

### 3.2 Request Models

```python
class ContactCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None

class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
```

### 3.3 Implementation

```python
@app.get("/contacts/{resource_name:path}")
async def get_contact(resource_name: str):
    service = get_people_service()
    contact = service.people().get(
        resourceName=resource_name,
        personFields="names,emailAddresses,phoneNumbers,biographies"
    ).execute()
    return contact

@app.post("/contacts")
async def create_contact(contact: ContactCreate):
    service = get_people_service()
    body = {
        "names": [{"givenName": contact.first_name, "familyName": contact.last_name}],
        "emailAddresses": [{"value": contact.email}] if contact.email else [],
        "phoneNumbers": [{"value": contact.phone}] if contact.phone else [],
        "biographies": [{"value": contact.notes}] if contact.notes else []
    }
    result = service.people().createContact(body=body).execute()
    return result

@app.patch("/contacts/{resource_name:path}")
async def update_contact(resource_name: str, update: ContactUpdate):
    service = get_people_service()
    # Get current contact first for etag
    current = service.people().get(
        resourceName=resource_name,
        personFields="names,emailAddresses,phoneNumbers,biographies,metadata"
    ).execute()

    # Build update body
    body = {"etag": current.get("etag")}
    update_fields = []

    if update.first_name or update.last_name:
        body["names"] = [{"givenName": update.first_name, "familyName": update.last_name}]
        update_fields.append("names")
    if update.email:
        body["emailAddresses"] = [{"value": update.email}]
        update_fields.append("emailAddresses")
    if update.phone:
        body["phoneNumbers"] = [{"value": update.phone}]
        update_fields.append("phoneNumbers")

    result = service.people().updateContact(
        resourceName=resource_name,
        body=body,
        updatePersonFields=",".join(update_fields)
    ).execute()
    return result

@app.delete("/contacts/{resource_name:path}")
async def delete_contact(resource_name: str):
    service = get_people_service()
    service.people().deleteContact(resourceName=resource_name).execute()
    return {"deleted": True, "resource_name": resource_name}

@app.get("/contacts/list")
async def list_contacts(page_size: int = 100, page_token: str = None):
    service = get_people_service()
    results = service.people().connections().list(
        resourceName="people/me",
        pageSize=page_size,
        pageToken=page_token,
        personFields="names,emailAddresses,phoneNumbers"
    ).execute()
    return {
        "contacts": results.get("connections", []),
        "next_page_token": results.get("nextPageToken"),
        "total": results.get("totalPeople", 0)
    }
```

### 3.4 Testing

| Test | Input | Expected |
|------|-------|----------|
| Create contact | name + email | Contact created with resource_name |
| Get contact | resource_name | Returns contact details |
| Update email | resource_name + email | Email updated |
| Delete contact | resource_name | Contact removed |
| List contacts | None | Paginated list |

---

## Phase 4: Google Sheets CRUD Enhancement

### Current State
- `GET /sheets/read` - Read range from sheet
- `POST /sheets/write` - Write to range (overwrite)
- `POST /sheets/append` - Append rows
- `POST /sheets/clear` - Clear range
- `GET /sheets/info` - Get spreadsheet metadata

### 4.1 New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sheets/update` | PATCH | Update specific cells (merge with existing) |
| `/sheets/delete-rows` | POST | Delete specific rows |
| `/sheets/insert-rows` | POST | Insert blank rows at position |
| `/sheets/create` | POST | Create new spreadsheet |
| `/sheets/duplicate` | POST | Duplicate a sheet tab |

### 4.2 Request Models

```python
class SheetUpdate(BaseModel):
    spreadsheet_id: str
    range: str  # e.g., "Sheet1!A1:B2"
    values: List[List[Any]]

class SheetDeleteRows(BaseModel):
    spreadsheet_id: str
    sheet_id: int  # Numeric sheet ID (tab)
    start_row: int  # 0-indexed
    end_row: int    # Exclusive

class SheetInsertRows(BaseModel):
    spreadsheet_id: str
    sheet_id: int
    start_row: int
    num_rows: int

class SheetCreate(BaseModel):
    title: str
    sheets: Optional[List[str]] = ["Sheet1"]  # Tab names
```

### 4.3 Implementation

```python
@app.patch("/sheets/update")
async def update_sheet(update: SheetUpdate):
    """Update cells - only changes specified cells, preserves others."""
    service = get_sheets_service()
    result = service.spreadsheets().values().update(
        spreadsheetId=update.spreadsheet_id,
        range=update.range,
        valueInputOption="USER_ENTERED",
        body={"values": update.values}
    ).execute()
    return {"updated_cells": result.get("updatedCells", 0)}

@app.post("/sheets/delete-rows")
async def delete_sheet_rows(request: SheetDeleteRows):
    service = get_sheets_service()
    body = {
        "requests": [{
            "deleteDimension": {
                "range": {
                    "sheetId": request.sheet_id,
                    "dimension": "ROWS",
                    "startIndex": request.start_row,
                    "endIndex": request.end_row
                }
            }
        }]
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=request.spreadsheet_id,
        body=body
    ).execute()
    return {"deleted_rows": request.end_row - request.start_row}

@app.post("/sheets/insert-rows")
async def insert_sheet_rows(request: SheetInsertRows):
    service = get_sheets_service()
    body = {
        "requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": request.sheet_id,
                    "dimension": "ROWS",
                    "startIndex": request.start_row,
                    "endIndex": request.start_row + request.num_rows
                }
            }
        }]
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=request.spreadsheet_id,
        body=body
    ).execute()
    return {"inserted_rows": request.num_rows}

@app.post("/sheets/create")
async def create_spreadsheet(request: SheetCreate):
    service = get_sheets_service()
    body = {
        "properties": {"title": request.title},
        "sheets": [{"properties": {"title": name}} for name in request.sheets]
    }
    result = service.spreadsheets().create(body=body).execute()
    return {
        "spreadsheet_id": result["spreadsheetId"],
        "url": result["spreadsheetUrl"]
    }
```

### 4.4 Testing

| Test | Input | Expected |
|------|-------|----------|
| Update cells | range + values | Cells updated |
| Delete rows | sheet_id + row range | Rows removed |
| Insert rows | sheet_id + position | Blank rows added |
| Create spreadsheet | title | New spreadsheet URL |

---

## Phase 5: Google Docs CRUD Enhancement

### Current State
- `GET /docs/read` - Read document content
- `POST /docs/append` - Append text to end

### 5.1 New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/docs/create` | POST | Create new document |
| `/docs/insert` | POST | Insert text at position |
| `/docs/replace` | POST | Find and replace text |
| `/docs/delete` | POST | Delete text range |
| `/docs/format` | POST | Apply formatting |

### 5.2 Request Models

```python
class DocCreate(BaseModel):
    title: str
    content: Optional[str] = None  # Initial content

class DocInsert(BaseModel):
    document_id: str
    text: str
    index: int  # Character position (1 = start of body)

class DocReplace(BaseModel):
    document_id: str
    find: str
    replace: str
    match_case: bool = False

class DocDelete(BaseModel):
    document_id: str
    start_index: int
    end_index: int
```

### 5.3 Implementation

```python
@app.post("/docs/create")
async def create_document(request: DocCreate):
    service = get_docs_service()
    doc = service.documents().create(body={"title": request.title}).execute()

    if request.content:
        # Insert initial content
        service.documents().batchUpdate(
            documentId=doc["documentId"],
            body={
                "requests": [{
                    "insertText": {
                        "location": {"index": 1},
                        "text": request.content
                    }
                }]
            }
        ).execute()

    return {
        "document_id": doc["documentId"],
        "url": f"https://docs.google.com/document/d/{doc['documentId']}/edit"
    }

@app.post("/docs/insert")
async def insert_text(request: DocInsert):
    service = get_docs_service()
    service.documents().batchUpdate(
        documentId=request.document_id,
        body={
            "requests": [{
                "insertText": {
                    "location": {"index": request.index},
                    "text": request.text
                }
            }]
        }
    ).execute()
    return {"inserted": True, "length": len(request.text)}

@app.post("/docs/replace")
async def replace_text(request: DocReplace):
    service = get_docs_service()
    result = service.documents().batchUpdate(
        documentId=request.document_id,
        body={
            "requests": [{
                "replaceAllText": {
                    "containsText": {
                        "text": request.find,
                        "matchCase": request.match_case
                    },
                    "replaceText": request.replace
                }
            }]
        }
    ).execute()

    occurrences = result.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {"replaced": occurrences}

@app.post("/docs/delete")
async def delete_text(request: DocDelete):
    service = get_docs_service()
    service.documents().batchUpdate(
        documentId=request.document_id,
        body={
            "requests": [{
                "deleteContentRange": {
                    "range": {
                        "startIndex": request.start_index,
                        "endIndex": request.end_index
                    }
                }
            }]
        }
    ).execute()
    return {"deleted": True, "chars": request.end_index - request.start_index}
```

### 5.4 Testing

| Test | Input | Expected |
|------|-------|----------|
| Create doc | title | New document URL |
| Create with content | title + content | Doc with content |
| Insert text | doc_id + text + index | Text inserted |
| Replace text | doc_id + find + replace | Occurrences replaced |
| Delete range | doc_id + range | Text removed |

---

## Phase 6: Comprehensive Testing Plan

### 6.1 Unit Tests

Create test files for each API:

**`tests/test_notion_crud.py`**
```python
# Test create_todo with all fields
# Test create_todo with minimal fields
# Test update_todo status change
# Test update_todo priority change
# Test delete_todo (archive)
# Test create_idea / update_idea / delete_idea
# Test error handling (invalid ID, missing fields)
```

**`tests/test_tasks_crud.py`**
```python
# Test get_task with valid ID
# Test get_task with invalid ID (404)
# Test update_task title
# Test update_task due date
# Test delete_task
# Test list_task_lists
```

**`tests/test_contacts_crud.py`**
```python
# Test create_contact minimal (name only)
# Test create_contact full (name, email, phone, notes)
# Test get_contact
# Test update_contact email
# Test delete_contact
# Test list_contacts pagination
```

**`tests/test_sheets_crud.py`**
```python
# Test update cells
# Test delete rows
# Test insert rows
# Test create spreadsheet
```

**`tests/test_docs_crud.py`**
```python
# Test create document
# Test create document with initial content
# Test insert text at position
# Test replace all occurrences
# Test delete text range
```

### 6.2 Integration Tests

Test against real Google/Notion APIs:

| API | Create | Read | Update | Delete |
|-----|--------|------|--------|--------|
| Notion Todos | ✓ | ✓ | ✓ | ✓ |
| Notion Ideas | ✓ | ✓ | ✓ | ✓ |
| Google Tasks | ✓ | ✓ | ✓ | ✓ |
| Google Contacts | ✓ | ✓ | ✓ | ✓ |
| Google Sheets | ✓ | ✓ | ✓ | ✓ |
| Google Docs | ✓ | ✓ | ✓ | - |

### 6.3 E2E Tests via Peter

| User Says | API Called | Expected Behavior |
|-----------|------------|-------------------|
| "Add a todo: Buy milk" | POST /notion/todos | Creates todo, confirms |
| "Mark buy milk as done" | PATCH /notion/todos/{id} | Updates status |
| "Delete that todo" | DELETE /notion/todos/{id} | Archives |
| "Add an idea: App feature" | POST /notion/ideas | Creates idea |
| "Create a task: Call dentist" | POST /tasks/create | Creates Google task |
| "Delete that task" | DELETE /tasks/{id} | Removes task |
| "Add a contact: John 07700900000" | POST /contacts | Creates contact |
| "Create a spreadsheet called Budget" | POST /sheets/create | Creates sheet |
| "Create a doc called Meeting Notes" | POST /docs/create | Creates doc |

### 6.4 Error Handling Tests

| Scenario | Expected Response |
|----------|-------------------|
| Invalid Notion page ID | 404 Not Found |
| Invalid Google resource ID | 404 Not Found |
| Missing required fields | 400 Bad Request |
| API rate limit exceeded | 429 Too Many Requests |
| Network timeout | 504 Gateway Timeout |
| Invalid enum values | 400 with allowed values |
| Unauthorized (token expired) | 401 Unauthorized |

---

## Phase 7: Validation Checklist

### Pre-Deployment

- [ ] All unit tests pass for all 5 APIs
- [ ] Integration tests pass against real services
- [ ] API documentation updated (playbooks)
- [ ] Request/response models validated
- [ ] Error responses are user-friendly
- [ ] No breaking changes to existing endpoints

### Post-Deployment (Notion)

- [ ] Create todo via API works
- [ ] Update todo status works
- [ ] Delete todo works
- [ ] Create/update/delete idea works
- [ ] GET endpoints still work (no regression)

### Post-Deployment (Google Tasks)

- [ ] Get specific task works
- [ ] Update task title/due works
- [ ] Delete task works
- [ ] List task lists works

### Post-Deployment (Google Contacts)

- [ ] Create contact works
- [ ] Get contact works
- [ ] Update contact works
- [ ] Delete contact works
- [ ] List contacts with pagination works

### Post-Deployment (Google Sheets)

- [ ] Update cells works
- [ ] Delete rows works
- [ ] Insert rows works
- [ ] Create spreadsheet works

### Post-Deployment (Google Docs)

- [ ] Create document works
- [ ] Insert text works
- [ ] Replace text works
- [ ] Delete text range works

### Rollback Plan

If issues detected:
1. Revert `hadley_api/main.py` to previous version
2. Revert `hadley_api/notion_client.py` to previous version
3. Restart HadleyAPI service: `net stop HadleyAPI && net start HadleyAPI`
4. Existing read operations continue working

---

## Implementation Order

### Batch 1: Notion (Critical Priority)
1. Extend `notion_client.py` with PATCH/DELETE + CRUD functions
2. Add Notion endpoints to `main.py`
3. Create `docs/playbooks/NOTION.md`
4. Test and validate

### Batch 2: Google Tasks (Low Priority)
5. Add Tasks endpoints to `main.py`
6. Update relevant playbook
7. Test and validate

### Batch 3: Google Contacts (Low Priority)
8. Add Contacts endpoints to `main.py`
9. Update relevant playbook
10. Test and validate

### Batch 4: Google Sheets (Low Priority)
11. Add Sheets enhancement endpoints
12. Update relevant playbook
13. Test and validate

### Batch 5: Google Docs (Medium Priority)
14. Add Docs enhancement endpoints
15. Update relevant playbook
16. Test and validate

---

## Estimated Scope

| Component | Files | Lines |
|-----------|-------|-------|
| **Notion** | | |
| - notion_client.py (CRUD functions) | 1 | ~120 |
| - main.py (7 endpoints) | 1 | ~150 |
| - Pydantic models | 1 | ~40 |
| - NOTION.md playbook | 1 | ~60 |
| **Google Tasks** | | |
| - main.py (5 endpoints) | 1 | ~100 |
| - Pydantic models | 1 | ~20 |
| **Google Contacts** | | |
| - main.py (5 endpoints) | 1 | ~150 |
| - Pydantic models | 1 | ~30 |
| **Google Sheets** | | |
| - main.py (4 endpoints) | 1 | ~120 |
| - Pydantic models | 1 | ~40 |
| **Google Docs** | | |
| - main.py (5 endpoints) | 1 | ~130 |
| - Pydantic models | 1 | ~30 |
| **Tests** | | |
| - test_notion_crud.py | 1 | ~100 |
| - test_tasks_crud.py | 1 | ~60 |
| - test_contacts_crud.py | 1 | ~80 |
| - test_sheets_crud.py | 1 | ~60 |
| - test_docs_crud.py | 1 | ~60 |

**Total new code**: ~1,350 lines

---

## Summary: New Endpoints

| API | Current | Adding | Total |
|-----|---------|--------|-------|
| Notion | 2 | 7 | 9 |
| Tasks | 3 | 5 | 8 |
| Contacts | 1 | 5 | 6 |
| Sheets | 5 | 4 | 9 |
| Docs | 2 | 5 | 7 |
| **TOTAL** | **13** | **26** | **39** |
