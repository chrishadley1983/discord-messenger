"""Task Management API Routes.

Provides CRUD operations for the task management system:
- Personal Todos
- Peter Work Queue
- Ideas
- Research

Uses Supabase for storage with REST API.
"""

import os
import httpx
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from enum import Enum
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

router = APIRouter(prefix="/ptasks", tags=["Peterbot Tasks"])

# ============================================================
# Configuration
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase_headers():
    """Get Supabase REST API headers."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ============================================================
# Enums (matching Postgres)
# ============================================================

class TaskListType(str, Enum):
    personal_todo = "personal_todo"
    peter_queue = "peter_queue"
    idea = "idea"
    research = "research"


class TaskStatus(str, Enum):
    inbox = "inbox"
    scheduled = "scheduled"
    queued = "queued"
    heartbeat_scheduled = "heartbeat_scheduled"
    in_heartbeat = "in_heartbeat"
    in_progress = "in_progress"
    review = "review"
    findings_ready = "findings_ready"
    done = "done"
    cancelled = "cancelled"
    parked = "parked"


class TaskPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    someday = "someday"


class ResearchDepth(str, Enum):
    shallow = "shallow"
    standard = "standard"
    deep = "deep"


class IdeaSource(str, Enum):
    discord_message = "discord_message"
    conversation = "conversation"
    research = "research"
    manual = "manual"
    pattern = "pattern"
    external = "external"


# ============================================================
# Pydantic Models
# ============================================================

class TaskCreate(BaseModel):
    """Create a new task."""
    list_type: TaskListType
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    status: Optional[TaskStatus] = None  # Will default based on list_type
    due_date: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    estimated_effort: Optional[str] = None
    idea_source: Optional[IdeaSource] = None
    research_depth: Optional[ResearchDepth] = None
    created_by: str = "chris"
    category_slugs: Optional[List[str]] = None


class TaskUpdate(BaseModel):
    """Update an existing task."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    estimated_effort: Optional[str] = None
    heartbeat_scheduled_for: Optional[date] = None
    heartbeat_slot_order: Optional[int] = None
    is_pinned: Optional[bool] = None
    sort_order: Optional[int] = None


class TaskStatusChange(BaseModel):
    """Change task status."""
    status: TaskStatus
    actor: str = "chris"


class HeartbeatSchedule(BaseModel):
    """Schedule task for heartbeat."""
    schedule_date: Optional[date] = None  # None means current heartbeat
    slot_order: int = 0


class CommentCreate(BaseModel):
    """Create a comment on a task."""
    content: str
    author: str = "chris"
    is_system_message: bool = False


class CategoryResponse(BaseModel):
    """Category response."""
    id: str
    name: str
    slug: str
    color: Optional[str] = None


# ============================================================
# Helper Functions
# ============================================================

def get_default_status(list_type: TaskListType) -> TaskStatus:
    """Get default status for a list type."""
    defaults = {
        TaskListType.personal_todo: TaskStatus.inbox,
        TaskListType.peter_queue: TaskStatus.queued,
        TaskListType.idea: TaskStatus.inbox,
        TaskListType.research: TaskStatus.queued,
    }
    return defaults.get(list_type, TaskStatus.inbox)


# Valid status transitions per list type
VALID_TRANSITIONS = {
    TaskListType.peter_queue: {
        TaskStatus.queued: [TaskStatus.heartbeat_scheduled, TaskStatus.in_heartbeat, TaskStatus.cancelled],
        TaskStatus.heartbeat_scheduled: [TaskStatus.queued, TaskStatus.in_heartbeat, TaskStatus.cancelled],
        TaskStatus.in_heartbeat: [TaskStatus.in_progress, TaskStatus.queued],
        TaskStatus.in_progress: [TaskStatus.review, TaskStatus.in_heartbeat],
        TaskStatus.review: [TaskStatus.done, TaskStatus.in_progress],
        TaskStatus.done: [TaskStatus.queued],
    },
    TaskListType.personal_todo: {
        TaskStatus.inbox: [TaskStatus.scheduled, TaskStatus.in_progress, TaskStatus.done, TaskStatus.cancelled],
        TaskStatus.scheduled: [TaskStatus.inbox, TaskStatus.in_progress, TaskStatus.done],
        TaskStatus.in_progress: [TaskStatus.done, TaskStatus.scheduled],
        TaskStatus.done: [TaskStatus.inbox, TaskStatus.scheduled, TaskStatus.in_progress],  # Allow reopening to any active state
    },
    TaskListType.idea: {
        TaskStatus.inbox: [TaskStatus.scheduled, TaskStatus.review, TaskStatus.done],
        TaskStatus.scheduled: [TaskStatus.inbox, TaskStatus.review],
        TaskStatus.review: [TaskStatus.done, TaskStatus.scheduled],
        TaskStatus.done: [TaskStatus.inbox, TaskStatus.scheduled],  # Allow reopening
    },
    TaskListType.research: {
        TaskStatus.queued: [TaskStatus.in_progress, TaskStatus.cancelled],
        TaskStatus.in_progress: [TaskStatus.findings_ready, TaskStatus.queued],
        TaskStatus.findings_ready: [TaskStatus.done, TaskStatus.in_progress],
        TaskStatus.done: [TaskStatus.queued],
    },
}


# ============================================================
# Endpoints
# ============================================================

@router.get("/categories")
async def get_categories():
    """Get all task categories."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_categories?select=id,name,slug,color,icon&order=sort_order",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch categories: {resp.text}")

        return {"categories": resp.json()}


class CategoryCreate(BaseModel):
    """Model for creating a category."""
    name: str
    slug: Optional[str] = None  # Auto-generated from name if not provided
    color: str = "#6B7280"  # Default gray
    icon: Optional[str] = None


class CategoryUpdate(BaseModel):
    """Model for updating a category."""
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


@router.post("/categories")
async def create_category(category: CategoryCreate):
    """Create a new task category."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    # Generate slug from name if not provided
    slug = category.slug or category.name.lower().replace(" ", "-").replace("_", "-")
    # Remove any non-alphanumeric characters except hyphens
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    async with httpx.AsyncClient() as client:
        # Get max sort_order
        order_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_categories?select=sort_order&order=sort_order.desc&limit=1",
            headers=get_supabase_headers(),
            timeout=10
        )
        max_order = 0
        if order_resp.status_code == 200 and order_resp.json():
            max_order = order_resp.json()[0].get("sort_order", 0)

        # Create category
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/task_categories",
            headers=get_supabase_headers(),
            json={
                "name": category.name,
                "slug": slug,
                "color": category.color,
                "icon": category.icon,
                "sort_order": max_order + 1
            },
            timeout=10
        )

        if resp.status_code not in (200, 201):
            raise HTTPException(resp.status_code, f"Failed to create category: {resp.text}")

        return resp.json()[0] if resp.json() else {"slug": slug, "name": category.name}


@router.put("/categories/{category_id}")
async def update_category(category_id: str, update: CategoryUpdate):
    """Update a task category."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    update_data = {}
    if update.name is not None:
        update_data["name"] = update.name
    if update.color is not None:
        update_data["color"] = update.color
    if update.icon is not None:
        update_data["icon"] = update.icon

    if not update_data:
        raise HTTPException(400, "No fields to update")

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/task_categories?id=eq.{category_id}",
            headers=get_supabase_headers(),
            json=update_data,
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to update category: {resp.text}")

        result = resp.json()
        if not result:
            raise HTTPException(404, "Category not found")

        return result[0]


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str):
    """Delete a task category. Also removes all task-category links."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        # Delete category links first
        await client.delete(
            f"{SUPABASE_URL}/rest/v1/task_category_links?category_id=eq.{category_id}",
            headers=get_supabase_headers(),
            timeout=10
        )

        # Delete category
        resp = await client.delete(
            f"{SUPABASE_URL}/rest/v1/task_categories?id=eq.{category_id}",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to delete category: {resp.text}")

        return {"status": "deleted", "id": category_id}


@router.get("/counts")
async def get_task_counts():
    """Get task counts per list type (excludes done/cancelled)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        # Get counts for each list type
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?select=list_type&status=not.in.(done,cancelled)",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch counts: {resp.text}")

        tasks = resp.json()
        counts = {
            "personal_todo": 0,
            "peter_queue": 0,
            "idea": 0,
            "research": 0,
        }
        for t in tasks:
            lt = t.get("list_type")
            if lt in counts:
                counts[lt] += 1

        return {"counts": counts}


@router.get("")
async def list_tasks(
    list_type: Optional[TaskListType] = None,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List tasks with optional filters."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    # Build query params
    params = []
    params.append("select=*")

    if list_type:
        params.append(f"list_type=eq.{list_type.value}")
    if status:
        params.append(f"status=eq.{status.value}")
    if priority:
        params.append(f"priority=eq.{priority.value}")
    if search:
        params.append(f"title=ilike.*{search}*")

    params.append("order=sort_order.asc,created_at.desc")
    params.append(f"limit={limit}")
    params.append(f"offset={offset}")

    query_string = "&".join(params)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?{query_string}",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch tasks: {resp.text}")

        tasks = resp.json()

        # Fetch categories for each task
        if tasks:
            task_ids = [t["id"] for t in tasks]
            cat_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_category_links?select=task_id,category_id,task_categories(slug,name,color)&task_id=in.({','.join(task_ids)})",
                headers=get_supabase_headers(),
                timeout=10
            )

            if cat_resp.status_code == 200:
                cat_links = cat_resp.json()
                cat_map = {}
                for link in cat_links:
                    tid = link["task_id"]
                    if tid not in cat_map:
                        cat_map[tid] = []
                    if link.get("task_categories"):
                        cat_map[tid].append(link["task_categories"]["slug"])

                for task in tasks:
                    task["categories"] = cat_map.get(task["id"], [])
            else:
                for task in tasks:
                    task["categories"] = []

        # Count comments and attachments
        for task in tasks:
            comm_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_comments?task_id=eq.{task['id']}&select=id",
                headers={**get_supabase_headers(), "Prefer": "count=exact"},
                timeout=5
            )
            task["comments"] = int(comm_resp.headers.get("content-range", "0/0").split("/")[-1]) if comm_resp.status_code == 200 else 0

            att_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_attachments?task_id=eq.{task['id']}&select=id",
                headers={**get_supabase_headers(), "Prefer": "count=exact"},
                timeout=5
            )
            task["attachments"] = int(att_resp.headers.get("content-range", "0/0").split("/")[-1]) if att_resp.status_code == 200 else 0

        return {"tasks": tasks, "count": len(tasks)}


@router.get("/list/{list_type}")
async def list_tasks_by_type(
    list_type: TaskListType,
    include_done: bool = False,
):
    """Get all tasks for a specific list type."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    status_filter = "" if include_done else "&status=not.in.(done,cancelled)"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?list_type=eq.{list_type.value}{status_filter}&order=sort_order.asc,priority,created_at.desc",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch tasks: {resp.text}")

        tasks = resp.json()

        # Fetch categories for each task
        if tasks:
            task_ids = [t["id"] for t in tasks]
            cat_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_category_links?select=task_id,category_id,task_categories(slug,name,color)&task_id=in.({','.join(task_ids)})",
                headers=get_supabase_headers(),
                timeout=10
            )

            if cat_resp.status_code == 200:
                cat_links = cat_resp.json()
                cat_map = {}
                for link in cat_links:
                    tid = link["task_id"]
                    if tid not in cat_map:
                        cat_map[tid] = []
                    if link.get("task_categories"):
                        cat_map[tid].append(link["task_categories"]["slug"])

                for task in tasks:
                    task["categories"] = cat_map.get(task["id"], [])
            else:
                for task in tasks:
                    task["categories"] = []

        # Count comments and attachments (batch)
        for task in tasks:
            comm_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_comments?task_id=eq.{task['id']}&select=id",
                headers={**get_supabase_headers(), "Prefer": "count=exact"},
                timeout=5
            )
            task["comments"] = int(comm_resp.headers.get("content-range", "0/0").split("/")[-1]) if comm_resp.status_code == 200 else 0

            att_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_attachments?task_id=eq.{task['id']}&select=id",
                headers={**get_supabase_headers(), "Prefer": "count=exact"},
                timeout=5
            )
            task["attachments"] = int(att_resp.headers.get("content-range", "0/0").split("/")[-1]) if att_resp.status_code == 200 else 0

        return {"tasks": tasks, "count": len(tasks)}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}&select=*",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch task: {resp.text}")

        tasks = resp.json()
        if not tasks:
            raise HTTPException(404, "Task not found")

        task = tasks[0]

        # Get categories
        cat_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_category_links?select=task_categories(slug,name,color)&task_id=eq.{task_id}",
            headers=get_supabase_headers(),
            timeout=10
        )
        if cat_resp.status_code == 200:
            task["categories"] = [c["task_categories"]["slug"] for c in cat_resp.json() if c.get("task_categories")]
        else:
            task["categories"] = []

        # Get comments
        comm_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_comments?task_id=eq.{task_id}&order=created_at.desc",
            headers=get_supabase_headers(),
            timeout=10
        )
        task["comments_list"] = comm_resp.json() if comm_resp.status_code == 200 else []

        # Get attachments
        att_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_attachments?task_id=eq.{task_id}&order=created_at.desc",
            headers=get_supabase_headers(),
            timeout=10
        )
        task["attachments_list"] = att_resp.json() if att_resp.status_code == 200 else []

        return task


@router.post("")
async def create_task(task: TaskCreate):
    """Create a new task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    # Prepare task data
    task_data = {
        "list_type": task.list_type.value,
        "title": task.title,
        "description": task.description,
        "priority": task.priority.value,
        "status": (task.status or get_default_status(task.list_type)).value,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "scheduled_date": task.scheduled_date.isoformat() if task.scheduled_date else None,
        "estimated_effort": task.estimated_effort,
        "idea_source": task.idea_source.value if task.idea_source else None,
        "research_depth": task.research_depth.value if task.research_depth else None,
        "created_by": task.created_by,
    }

    # Remove None values
    task_data = {k: v for k, v in task_data.items() if v is not None}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/tasks",
            headers=get_supabase_headers(),
            json=task_data,
            timeout=10
        )

        if resp.status_code not in (200, 201):
            raise HTTPException(resp.status_code, f"Failed to create task: {resp.text}")

        created_task = resp.json()[0]

        # Add categories if provided
        if task.category_slugs:
            # Get category IDs
            cat_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_categories?slug=in.({','.join(task.category_slugs)})&select=id,slug",
                headers=get_supabase_headers(),
                timeout=10
            )
            if cat_resp.status_code == 200:
                categories = cat_resp.json()
                links = [{"task_id": created_task["id"], "category_id": c["id"]} for c in categories]
                if links:
                    await client.post(
                        f"{SUPABASE_URL}/rest/v1/task_category_links",
                        headers=get_supabase_headers(),
                        json=links,
                        timeout=10
                    )
                created_task["categories"] = [c["slug"] for c in categories]

        # Add history entry
        await client.post(
            f"{SUPABASE_URL}/rest/v1/task_history",
            headers=get_supabase_headers(),
            json={
                "task_id": created_task["id"],
                "action": "created",
                "actor": task.created_by,
            },
            timeout=10
        )

        return created_task


@router.put("/{task_id}")
async def update_task(task_id: str, update: TaskUpdate):
    """Update a task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    # Prepare update data (only non-None fields)
    update_data = {}
    if update.title is not None:
        update_data["title"] = update.title
    if update.description is not None:
        update_data["description"] = update.description
    if update.priority is not None:
        update_data["priority"] = update.priority.value
    if update.status is not None:
        update_data["status"] = update.status.value
    if update.due_date is not None:
        update_data["due_date"] = update.due_date.isoformat()
    if update.scheduled_date is not None:
        update_data["scheduled_date"] = update.scheduled_date.isoformat()
    if update.estimated_effort is not None:
        update_data["estimated_effort"] = update.estimated_effort
    if update.heartbeat_scheduled_for is not None:
        update_data["heartbeat_scheduled_for"] = update.heartbeat_scheduled_for.isoformat()
    if update.heartbeat_slot_order is not None:
        update_data["heartbeat_slot_order"] = update.heartbeat_slot_order
    if update.is_pinned is not None:
        update_data["is_pinned"] = update.is_pinned
    if update.sort_order is not None:
        update_data["sort_order"] = update.sort_order

    if not update_data:
        raise HTTPException(400, "No fields to update")

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers=get_supabase_headers(),
            json=update_data,
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to update task: {resp.text}")

        tasks = resp.json()
        if not tasks:
            raise HTTPException(404, "Task not found")

        return tasks[0]


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code not in (200, 204):
            raise HTTPException(resp.status_code, f"Failed to delete task: {resp.text}")

        return {"status": "deleted", "id": task_id}


@router.post("/{task_id}/status")
async def change_task_status(task_id: str, change: TaskStatusChange):
    """Change task status with validation."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        # Get current task
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}&select=id,list_type,status",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch task: {resp.text}")

        tasks = resp.json()
        if not tasks:
            raise HTTPException(404, "Task not found")

        task = tasks[0]
        old_status = TaskStatus(task["status"])
        list_type = TaskListType(task["list_type"])
        new_status = change.status

        # Validate transition
        valid_next = VALID_TRANSITIONS.get(list_type, {}).get(old_status, [])
        if new_status not in valid_next:
            raise HTTPException(
                400,
                f"Invalid status transition from {old_status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )

        # Update status
        update_data = {"status": new_status.value}
        if new_status == TaskStatus.done:
            update_data["completed_at"] = datetime.now(UK_TZ).isoformat()

        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers=get_supabase_headers(),
            json=update_data,
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to update status: {resp.text}")

        # Add history entry
        await client.post(
            f"{SUPABASE_URL}/rest/v1/task_history",
            headers=get_supabase_headers(),
            json={
                "task_id": task_id,
                "action": "status_changed",
                "field_name": "status",
                "old_value": old_status.value,
                "new_value": new_status.value,
                "actor": change.actor,
            },
            timeout=10
        )

        return resp.json()[0]


@router.post("/{task_id}/heartbeat")
async def schedule_heartbeat(task_id: str, schedule: HeartbeatSchedule):
    """Schedule a task for heartbeat."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        # Get current task
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}&select=id,list_type,status",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch task: {resp.text}")

        tasks = resp.json()
        if not tasks:
            raise HTTPException(404, "Task not found")

        task = tasks[0]

        if task["list_type"] != "peter_queue":
            raise HTTPException(400, "Only Peter Queue tasks can be scheduled for heartbeat")

        # Determine new status
        if schedule.schedule_date is None:
            # Add to current heartbeat
            new_status = "in_heartbeat"
            update_data = {
                "status": new_status,
                "heartbeat_scheduled_for": None,
            }
        else:
            # Schedule for future heartbeat
            new_status = "heartbeat_scheduled"
            update_data = {
                "status": new_status,
                "heartbeat_scheduled_for": schedule.schedule_date.isoformat(),
                "heartbeat_slot_order": schedule.slot_order,
            }

        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers=get_supabase_headers(),
            json=update_data,
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to schedule heartbeat: {resp.text}")

        return resp.json()[0]


@router.get("/heartbeat/plan")
async def get_heartbeat_plan():
    """Get heartbeat plan showing scheduled tasks by date."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/v_heartbeat_plan?select=*&order=plan_date",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch heartbeat plan: {resp.text}")

        return {"plan": resp.json()}


@router.post("/{task_id}/comments")
async def add_comment(task_id: str, comment: CommentCreate):
    """Add a comment to a task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/task_comments",
            headers=get_supabase_headers(),
            json={
                "task_id": task_id,
                "content": comment.content,
                "author": comment.author,
                "is_system_message": comment.is_system_message,
            },
            timeout=10
        )

        if resp.status_code not in (200, 201):
            raise HTTPException(resp.status_code, f"Failed to add comment: {resp.text}")

        return resp.json()[0]


@router.get("/{task_id}/comments")
async def get_comments(task_id: str):
    """Get comments for a task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/task_comments?task_id=eq.{task_id}&order=created_at.asc",
            headers=get_supabase_headers(),
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to fetch comments: {resp.text}")

        return {"comments": resp.json()}


@router.put("/{task_id}/categories")
async def update_task_categories(task_id: str, category_slugs: List[str]):
    """Update categories for a task."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        # Delete existing links
        await client.delete(
            f"{SUPABASE_URL}/rest/v1/task_category_links?task_id=eq.{task_id}",
            headers=get_supabase_headers(),
            timeout=10
        )

        if category_slugs:
            # Get category IDs
            cat_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/task_categories?slug=in.({','.join(category_slugs)})&select=id,slug",
                headers=get_supabase_headers(),
                timeout=10
            )

            if cat_resp.status_code == 200:
                categories = cat_resp.json()
                links = [{"task_id": task_id, "category_id": c["id"]} for c in categories]
                if links:
                    await client.post(
                        f"{SUPABASE_URL}/rest/v1/task_category_links",
                        headers=get_supabase_headers(),
                        json=links,
                        timeout=10
                    )
                return {"categories": [c["slug"] for c in categories]}

        return {"categories": []}


@router.post("/{task_id}/reorder")
async def reorder_task(task_id: str, new_order: int, actor: str = "chris"):
    """Reorder a task within its column."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{task_id}",
            headers=get_supabase_headers(),
            json={"sort_order": new_order},
            timeout=10
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Failed to reorder task: {resp.text}")

        return resp.json()[0]


@router.post("/bulk/reorder")
async def bulk_reorder_tasks(tasks_order: List[dict]):
    """Bulk reorder tasks. Expects list of {id: str, sort_order: int}."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(500, "Supabase not configured")

    async with httpx.AsyncClient() as client:
        for item in tasks_order:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/tasks?id=eq.{item['id']}",
                headers=get_supabase_headers(),
                json={"sort_order": item["sort_order"]},
                timeout=10
            )

    return {"status": "reordered", "count": len(tasks_order)}
