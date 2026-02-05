"""Notion API client."""

import os
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load .env file
load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_TODOS_DATABASE_ID = os.getenv("NOTION_TODOS_DATABASE_ID")
NOTION_IDEAS_DATABASE_ID = os.getenv("NOTION_IDEAS_DATABASE_ID")

UK_TZ = ZoneInfo("Europe/London")


async def _notion_request(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Make a request to Notion API.

    Supports GET, POST, PATCH, and DELETE methods.
    """
    if not NOTION_API_KEY:
        return {"error": "Notion API key not configured"}

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    url = f"https://api.notion.com/v1{endpoint}"

    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=data or {}, timeout=10)
        elif method == "PATCH":
            response = await client.patch(url, headers=headers, json=data or {}, timeout=10)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers, timeout=10)
        else:
            return {"error": f"Unsupported HTTP method: {method}"}

        # Handle empty responses (some DELETE operations)
        if response.status_code == 204:
            return {"success": True}

        return response.json()


async def get_todos() -> dict:
    """Fetch todos from Notion."""
    if not NOTION_TODOS_DATABASE_ID:
        return {"error": "Notion todos database not configured", "todos": []}

    # Fetch all items first (filtering handled in code for flexibility)
    result = await _notion_request(
        f"/databases/{NOTION_TODOS_DATABASE_ID}/query",
        method="POST",
        data={
            "page_size": 100
        }
    )

    if "error" in result:
        return {"error": result.get("message", "Notion API error"), "todos": []}

    todos = []
    for page in result.get("results", []):
        props = page.get("properties", {})

        # Extract status (handles both "status" and "select" property types)
        status = None
        status_prop = props.get("Status") or props.get("Done") or props.get("Complete")
        if status_prop:
            if status_prop.get("status"):  # Native status type
                status = status_prop["status"].get("name", "").lower()
            elif status_prop.get("select"):  # Select type
                status = status_prop["select"].get("name", "").lower() if status_prop["select"] else None
            elif status_prop.get("checkbox"):  # Checkbox type
                status = "done" if status_prop["checkbox"] else "not done"

        # Skip completed items
        if status in ["done", "complete", "completed", "finished"]:
            continue

        # Extract title (try multiple common property names)
        title = ""
        for title_key in ["Name", "Title", "Task", "Todo", "To-do", "Item"]:
            title_prop = props.get(title_key)
            if title_prop and title_prop.get("title"):
                title = "".join([t.get("plain_text", "") for t in title_prop["title"]])
                break

        # Extract priority
        priority = None
        priority_prop = props.get("Priority")
        if priority_prop:
            if priority_prop.get("select"):
                priority = priority_prop["select"].get("name")
            elif priority_prop.get("multi_select"):
                priority = priority_prop["multi_select"][0].get("name") if priority_prop["multi_select"] else None

        # Extract due date (try multiple property names)
        due_date = None
        for due_key in ["Due", "Due Date", "Deadline", "Date"]:
            due_prop = props.get(due_key)
            if due_prop and due_prop.get("date"):
                due_date = due_prop["date"].get("start")
                break

        if title:  # Only add if we found a title
            todos.append({
                "id": page["id"],
                "title": title,
                "status": status,
                "priority": priority,
                "due": due_date,
                "url": page.get("url")
            })

    # Sort by priority then due date
    priority_order = {"high": 0, "medium": 1, "low": 2, None: 3}
    todos.sort(key=lambda x: (priority_order.get(x.get("priority", "").lower() if x.get("priority") else None, 3), x.get("due") or "9999"))

    return {
        "todos": todos,
        "count": len(todos),
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


async def get_ideas() -> dict:
    """Fetch ideas from Notion."""
    if not NOTION_IDEAS_DATABASE_ID:
        return {"error": "Notion ideas database not configured", "ideas": []}

    result = await _notion_request(
        f"/databases/{NOTION_IDEAS_DATABASE_ID}/query",
        method="POST",
        data={
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": 20
        }
    )

    if "error" in result:
        return {"error": result.get("message", "Notion API error"), "ideas": []}

    ideas = []
    for page in result.get("results", []):
        props = page.get("properties", {})

        # Extract title
        title_prop = props.get("Name") or props.get("Title") or props.get("Idea")
        title = ""
        if title_prop and title_prop.get("title"):
            title = "".join([t.get("plain_text", "") for t in title_prop["title"]])

        # Extract category/tags
        category = None
        if "Category" in props and props["Category"].get("select"):
            category = props["Category"]["select"].get("name")
        elif "Tags" in props and props["Tags"].get("multi_select"):
            category = ", ".join([t["name"] for t in props["Tags"]["multi_select"]])

        ideas.append({
            "id": page["id"],
            "title": title,
            "category": category,
            "created": page.get("created_time"),
            "url": page.get("url")
        })

    return {
        "ideas": ideas,
        "count": len(ideas),
        "fetched_at": datetime.now(UK_TZ).isoformat()
    }


# =============================================================================
# Database Schema Discovery
# =============================================================================

async def get_database_schema(database_id: str) -> dict:
    """Get the schema (properties) of a Notion database."""
    result = await _notion_request(f"/databases/{database_id}", method="GET")
    if "error" in result or result.get("object") == "error":
        return {"error": result.get("message", "Failed to get database schema")}
    return result.get("properties", {})


def find_property_name(schema: dict, candidates: list, prop_type: str = None) -> str | None:
    """Find the actual property name from a list of candidates.

    Args:
        schema: Database properties schema
        candidates: List of possible property names to check
        prop_type: Optional property type filter (title, select, status, date, etc.)
    """
    for candidate in candidates:
        if candidate in schema:
            if prop_type is None:
                return candidate
            if schema[candidate].get("type") == prop_type:
                return candidate
    return None


# =============================================================================
# TODO CRUD Operations
# =============================================================================

async def create_todo(
    title: str,
    priority: str = None,
    due: str = None,
    tags: list = None
) -> dict:
    """Create a new todo in Notion.

    Args:
        title: Todo title (required)
        priority: Priority level (High, Medium, Low)
        due: Due date in ISO format (YYYY-MM-DD)
        tags: List of tag names
    """
    if not NOTION_TODOS_DATABASE_ID:
        return {"error": "Notion todos database not configured"}

    # Get database schema to find actual property names
    schema = await get_database_schema(NOTION_TODOS_DATABASE_ID)
    if "error" in schema:
        return schema

    # Find title property (required)
    title_prop = find_property_name(schema, ["Name", "Title", "Task", "Todo", "To-do", "Item"], "title")
    if not title_prop:
        return {"error": "Could not find title property in database"}

    # Build properties object with discovered property names
    properties = {
        title_prop: {
            "title": [{"text": {"content": title}}]
        }
    }

    # Add priority if provided and property exists
    if priority:
        priority_prop = find_property_name(schema, ["Priority"], "select")
        if priority_prop:
            properties[priority_prop] = {
                "select": {"name": priority.capitalize()}
            }

    # Add due date if provided and property exists
    if due:
        due_prop = find_property_name(schema, ["Due", "Due Date", "Deadline", "Date"], "date")
        if due_prop:
            properties[due_prop] = {
                "date": {"start": due}
            }

    # Add tags if provided and property exists
    if tags:
        tags_prop = find_property_name(schema, ["Tags", "Labels"], "multi_select")
        if tags_prop:
            properties[tags_prop] = {
                "multi_select": [{"name": tag} for tag in tags]
            }

    result = await _notion_request(
        "/pages",
        method="POST",
        data={
            "parent": {"database_id": NOTION_TODOS_DATABASE_ID},
            "properties": properties
        }
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to create todo"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": result.get("id"),
        "url": result.get("url"),
        "title": title,
        "created_at": datetime.now(UK_TZ).isoformat()
    }


async def update_todo(
    todo_id: str,
    title: str = None,
    status: str = None,
    priority: str = None,
    due: str = None
) -> dict:
    """Update an existing todo in Notion.

    Args:
        todo_id: Notion page ID
        title: New title (optional)
        status: New status - Done, In Progress, Not Done (optional)
        priority: New priority - High, Medium, Low (optional)
        due: New due date in ISO format (optional)
    """
    if not any([title, status, priority, due]):
        return {"error": "No update fields provided"}

    # Get database schema to find actual property names
    schema = await get_database_schema(NOTION_TODOS_DATABASE_ID)
    if "error" in schema:
        return schema

    properties = {}

    if title:
        title_prop = find_property_name(schema, ["Name", "Title", "Task", "Todo", "To-do", "Item"], "title")
        if title_prop:
            properties[title_prop] = {
                "title": [{"text": {"content": title}}]
            }

    if status:
        # Try status type first, then checkbox, then select
        status_prop = find_property_name(schema, ["Status", "Done", "Complete"])
        if status_prop:
            prop_type = schema[status_prop].get("type")
            if prop_type == "status":
                properties[status_prop] = {"status": {"name": status}}
            elif prop_type == "checkbox":
                is_done = status.lower() in ["done", "complete", "completed", "finished", "true"]
                properties[status_prop] = {"checkbox": is_done}
            elif prop_type == "select":
                properties[status_prop] = {"select": {"name": status}}

    if priority:
        priority_prop = find_property_name(schema, ["Priority"], "select")
        if priority_prop:
            properties[priority_prop] = {
                "select": {"name": priority.capitalize()}
            }

    if due:
        due_prop = find_property_name(schema, ["Due", "Due Date", "Deadline", "Date"], "date")
        if due_prop:
            properties[due_prop] = {
                "date": {"start": due}
            }

    if not properties:
        return {"error": "No matching properties found in database"}

    result = await _notion_request(
        f"/pages/{todo_id}",
        method="PATCH",
        data={"properties": properties}
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to update todo"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": result.get("id"),
        "url": result.get("url"),
        "updated_at": datetime.now(UK_TZ).isoformat()
    }


async def delete_todo(todo_id: str) -> dict:
    """Archive a todo in Notion (soft delete).

    Args:
        todo_id: Notion page ID
    """
    result = await _notion_request(
        f"/pages/{todo_id}",
        method="PATCH",
        data={"archived": True}
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to delete todo"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": todo_id,
        "archived": True,
        "deleted_at": datetime.now(UK_TZ).isoformat()
    }


async def complete_todo(todo_id: str) -> dict:
    """Mark a todo as complete (shorthand for update with status=Done)."""
    return await update_todo(todo_id, status="Done")


# =============================================================================
# IDEA CRUD Operations
# =============================================================================

async def create_idea(
    title: str,
    category: str = None,
    notes: str = None
) -> dict:
    """Create a new idea in Notion.

    Args:
        title: Idea title (required)
        category: Category name (optional)
        notes: Additional notes (optional)
    """
    if not NOTION_IDEAS_DATABASE_ID:
        return {"error": "Notion ideas database not configured"}

    # Get database schema to find actual property names
    schema = await get_database_schema(NOTION_IDEAS_DATABASE_ID)
    if "error" in schema:
        return schema

    # Find title property (required)
    title_prop = find_property_name(schema, ["Name", "Title", "Idea"], "title")
    if not title_prop:
        return {"error": "Could not find title property in database"}

    properties = {
        title_prop: {
            "title": [{"text": {"content": title}}]
        }
    }

    if category:
        cat_prop = find_property_name(schema, ["Category", "Type"], "select")
        if cat_prop:
            properties[cat_prop] = {
                "select": {"name": category}
            }

    if notes:
        notes_prop = find_property_name(schema, ["Notes", "Description", "Details"], "rich_text")
        if notes_prop:
            properties[notes_prop] = {
                "rich_text": [{"text": {"content": notes}}]
            }

    result = await _notion_request(
        "/pages",
        method="POST",
        data={
            "parent": {"database_id": NOTION_IDEAS_DATABASE_ID},
            "properties": properties
        }
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to create idea"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": result.get("id"),
        "url": result.get("url"),
        "title": title,
        "created_at": datetime.now(UK_TZ).isoformat()
    }


async def update_idea(
    idea_id: str,
    title: str = None,
    category: str = None,
    notes: str = None
) -> dict:
    """Update an existing idea in Notion.

    Args:
        idea_id: Notion page ID
        title: New title (optional)
        category: New category (optional)
        notes: New notes (optional)
    """
    if not any([title, category, notes]):
        return {"error": "No update fields provided"}

    # Get database schema to find actual property names
    schema = await get_database_schema(NOTION_IDEAS_DATABASE_ID)
    if "error" in schema:
        return schema

    properties = {}

    if title:
        title_prop = find_property_name(schema, ["Name", "Title", "Idea"], "title")
        if title_prop:
            properties[title_prop] = {
                "title": [{"text": {"content": title}}]
            }

    if category:
        cat_prop = find_property_name(schema, ["Category", "Type"], "select")
        if cat_prop:
            properties[cat_prop] = {
                "select": {"name": category}
            }

    if notes:
        notes_prop = find_property_name(schema, ["Notes", "Description", "Details"], "rich_text")
        if notes_prop:
            properties[notes_prop] = {
                "rich_text": [{"text": {"content": notes}}]
            }

    if not properties:
        return {"error": "No matching properties found in database"}

    result = await _notion_request(
        f"/pages/{idea_id}",
        method="PATCH",
        data={"properties": properties}
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to update idea"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": result.get("id"),
        "url": result.get("url"),
        "updated_at": datetime.now(UK_TZ).isoformat()
    }


async def delete_idea(idea_id: str) -> dict:
    """Archive an idea in Notion (soft delete).

    Args:
        idea_id: Notion page ID
    """
    result = await _notion_request(
        f"/pages/{idea_id}",
        method="PATCH",
        data={"archived": True}
    )

    if "error" in result or result.get("object") == "error":
        return {
            "error": result.get("message", "Failed to delete idea"),
            "code": result.get("code")
        }

    return {
        "success": True,
        "id": idea_id,
        "archived": True,
        "deleted_at": datetime.now(UK_TZ).isoformat()
    }
