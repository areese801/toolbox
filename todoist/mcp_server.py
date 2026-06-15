"""
MCP (Model Context Protocol) server for the Todoist toolbox.

Exposes read-only Todoist data as tools that any MCP-compatible client
(Claude Desktop, Claude Code, etc.) can call.

== How MCP servers work ==

An MCP server is a long-running process that communicates over stdin/stdout
using JSON-RPC 2.0 messages.  The client (e.g., Claude Desktop) spawns the
server as a subprocess and sends requests like:

    {"method": "tools/call", "params": {"name": "get_tasks", ...}}

The server processes the request (in our case, calling the Todoist REST API)
and writes a JSON-RPC response back to stdout.

The `mcp` Python SDK handles all the protocol plumbing.  We just need to:
  1. Create a FastMCP server instance
  2. Decorate functions with @mcp.tool() to register them
  3. Call mcp.run() to start the stdin/stdout event loop

== Running this server ==

You don't run this directly — the MCP client launches it.  But for testing:

    todoist/venv/bin/python -m todoist.mcp_server

It will sit waiting for JSON-RPC messages on stdin (Ctrl-C to quit).
"""

from mcp.server.fastmcp import FastMCP
from todoist_api_python.api import TodoistAPI

from todoist.todoist_tasks import _get_api_token, get_active_tasks
from todoist.todoist_tasks import get_projects as _get_projects_from_api
from todoist.todoist_tasks import get_labels as _get_labels_from_api
from todoist.todoist_tasks import get_sections as _get_sections_from_api
from todoist.todoist_tasks import _resolve_project_id, _resolve_section_id
from todoist.config import get_config


# --------------------------------------------------------------------------- #
# Initialize the MCP server
#
# FastMCP is the high-level API from the `mcp` SDK.  It handles:
#   - JSON-RPC message parsing
#   - Tool schema generation (from function signatures + type hints)
#   - stdin/stdout transport
#
# The `name` appears in client UIs so the user knows which server a tool
# came from.
# --------------------------------------------------------------------------- #
mcp = FastMCP(name="todoist-toolbox")


def _get_api() -> TodoistAPI:
    """
    Create a TodoistAPI client using the token from .env.
    """
    return TodoistAPI(_get_api_token())


def _task_to_dict(task, project_map: dict | None = None) -> dict:
    """
    Convert a Todoist Task object to a plain dict for JSON serialization.

    We pick the fields that are most useful for an AI making recommendations.
    The project_map (id -> name) enriches task data with human-readable
    project names so the AI doesn't have to make a separate call.
    """
    result = {
        "id": task.id,
        "content": task.content,
        "description": task.description or "",
        "priority": task.priority,  # 1=normal, 4=urgent
        "labels": task.labels,
        "is_completed": task.is_completed,
        "created_at": task.created_at,
        "url": f"https://app.todoist.com/app/task/{task.id}",
    }

    # Include project name if we have the mapping
    if project_map and task.project_id:
        result["project_id"] = task.project_id
        result["project_name"] = project_map.get(task.project_id, "Unknown")

    # Due date info (if present)
    if task.due:
        result["due"] = {
            "date": str(task.due.date),
            "is_recurring": task.due.is_recurring,
            "string": task.due.string,  # Human-readable like "every day"
        }
    else:
        result["due"] = None

    return result


def _label_to_dict(label) -> dict:
    """Convert a Todoist Label object to a plain dict."""
    return {
        "id": label.id,
        "name": label.name,
        "color": label.color,
        "is_favorite": label.is_favorite,
    }


def _section_to_dict(section) -> dict:
    """Convert a Todoist Section object to a plain dict."""
    return {
        "id": section.id,
        "name": section.name,
        "project_id": section.project_id,
    }


def _comment_to_dict(comment) -> dict:
    """Convert a Todoist Comment object to a plain dict."""
    return {
        "id": comment.id,
        "content": comment.content,
        "posted_at": comment.posted_at,
    }


def _project_to_dict(project) -> dict:
    """
    Convert a Todoist Project object to a plain dict.
    """
    return {
        "id": project.id,
        "name": project.name,
        "color": project.color,
        "is_favorite": project.is_favorite,
        "url": project.url,
    }


# --------------------------------------------------------------------------- #
# Tools
#
# Each @mcp.tool() function becomes a tool the AI can call.  The SDK
# auto-generates the JSON Schema for the tool's parameters from the function
# signature and type hints.  The docstring becomes the tool description that
# the AI reads to decide when to use it.
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_tasks(
    filter: str | None = None,
    project_name: str | None = None,
    label: str | None = None,
    include_completed: bool = False,
) -> list[dict]:
    """
    Get tasks from Todoist with optional filtering.

    Use this to understand what the user has on their plate.  Returns all
    open tasks by default.  You can narrow results with the parameters below.

    Args:
        filter: A Todoist filter string (e.g., "today", "overdue",
                "today | overdue", "p1", "next 7 days").  See Todoist filter
                docs for syntax.  If provided, uses the Todoist API's native
                filtering which is fast and precise.
        project_name: Only return tasks from projects whose name contains
                      this string (case-insensitive).
        label: Only return tasks that have this label (exact match).
        include_completed: If True, include completed tasks.  Default False.

    Returns:
        A list of task dicts with fields: id, content, description, priority,
        labels, due, project_name, url, etc.
    """
    api = _get_api()

    # Build a project id->name map for enrichment
    projects = _get_projects_from_api(api=api)
    project_map = {p.id: p.name for p in projects}

    # If a Todoist filter string was provided, use the API's native filter
    # parameter.  This is more efficient and supports Todoist's full filter
    # syntax (dates, priorities, boolean operators, etc.).
    if filter:
        try:
            tasks = []
            for page in api.filter_tasks(query=filter):
                tasks.extend(page)
        except Exception as e:
            return [{"error": f"Todoist filter query failed: {e}"}]
    else:
        tasks = get_active_tasks(api=api)

    # Apply local filters (these stack with the API filter)
    if project_name:
        project_name_lower = project_name.lower()
        tasks = [
            t
            for t in tasks
            if project_map.get(t.project_id, "").lower().find(project_name_lower) != -1
        ]

    if label:
        tasks = [t for t in tasks if label in t.labels]

    if not include_completed:
        tasks = [t for t in tasks if not t.is_completed]

    return [_task_to_dict(t, project_map) for t in tasks]


@mcp.tool()
def get_projects() -> list[dict]:
    """
    List all projects in the user's Todoist account.

    Useful for understanding how the user organizes their work (e.g., by
    area of responsibility, client, or context).  The color field can indicate
    project categories — for instance, this user uses sky_blue for work projects.
    """
    api = _get_api()
    projects = api.get_projects()

    # Handle both list and paginator return types
    if isinstance(projects, list):
        return [_project_to_dict(p) for p in projects]

    result = []
    for page in projects:
        result.extend([_project_to_dict(p) for p in page])
    return result


@mcp.tool()
def get_task_summary() -> dict:
    """
    Get a high-level summary of the user's Todoist state.

    Returns counts and breakdowns to help quickly assess workload without
    downloading every task's details.  Good starting point before drilling
    into specifics with get_tasks().
    """
    api = _get_api()
    tasks = get_active_tasks(api=api)
    projects = api.get_projects()

    # Build project map
    if isinstance(projects, list):
        project_list = projects
    else:
        project_list = []
        for page in projects:
            project_list.extend(page)
    project_map = {p.id: p.name for p in project_list}

    # Compute summary stats
    from datetime import date, datetime

    now = datetime.now()

    overdue = []
    due_today = []
    due_this_week = []
    no_due_date = []
    by_project = {}
    by_priority = {1: 0, 2: 0, 3: 0, 4: 0}

    for task in tasks:
        # Priority counts
        by_priority[task.priority] = by_priority.get(task.priority, 0) + 1

        # Project counts
        pname = project_map.get(task.project_id, "Unknown")
        by_project[pname] = by_project.get(pname, 0) + 1

        # Due date buckets
        if task.due is None:
            no_due_date.append(task.content)
            continue

        due_val = task.due.date
        if isinstance(due_val, datetime):
            due_date = due_val.date() if hasattr(due_val, "date") else due_val
        elif isinstance(due_val, date):
            due_date = due_val
        else:
            continue

        today = date.today()
        if due_date < today:
            overdue.append(task.content)
        elif due_date == today:
            due_today.append(task.content)
        elif (due_date - today).days <= 7:
            due_this_week.append(task.content)

    return {
        "total_open_tasks": len(tasks),
        "overdue_count": len(overdue),
        "overdue_tasks": overdue,
        "due_today_count": len(due_today),
        "due_today_tasks": due_today,
        "due_this_week_count": len(due_this_week),
        "no_due_date_count": len(no_due_date),
        "by_project": by_project,
        "by_priority": {
            "p1_urgent": by_priority[4],  # Todoist: 4 = highest
            "p2_high": by_priority[3],
            "p3_medium": by_priority[2],
            "p4_normal": by_priority[1],
        },
    }


@mcp.tool()
def get_config_info() -> dict:
    """
    Get the todoist-toolbox configuration.

    Returns non-sensitive settings like which label marks work tasks, which
    color identifies work projects, the user's timezone, etc.  Useful for
    understanding the user's organizational scheme.
    """
    return get_config()


# --------------------------------------------------------------------------- #
# Write Tools — GTD Inbox Processing
# --------------------------------------------------------------------------- #


@mcp.tool()
def create_task(
    content: str,
    project_name: str | None = None,
    section_name: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    due_string: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """
    Create a new task in Todoist. By default, the task is added to the Inbox.
    Use project_name and section_name to place it in a specific project or
    section.

    Args:
        content: The task title (required).
        project_name: Project to add the task to (case-insensitive). If not
                      provided, the task goes to the Inbox.
        section_name: Section within the project (case-insensitive). If
                      project_name is also given, the section is looked up
                      within that project.
        description: Optional description text for additional context.
        priority: Priority level: 1=normal, 2=medium, 3=high, 4=urgent.
        due_string: Due date in natural language. Examples: "today",
                    "tomorrow", "next Monday", "Jan 15", "every Friday".
        labels: List of label names to apply to the task.

    Returns:
        The created task dict with id, content, description, priority,
        labels, due, project_name, url, etc.
    """
    api = _get_api()

    kwargs: dict = {"content": content}

    project_id = None
    try:
        if project_name:
            project_id = _resolve_project_id(api, project_name)
            kwargs["project_id"] = project_id
        if section_name:
            kwargs["section_id"] = _resolve_section_id(
                api, section_name, project_id=project_id
            )
    except ValueError as e:
        return {"error": str(e)}

    if description is not None:
        kwargs["description"] = description
    if priority is not None:
        kwargs["priority"] = priority
    if due_string is not None:
        kwargs["due_string"] = due_string
    if labels is not None:
        kwargs["labels"] = labels

    try:
        task = api.add_task(**kwargs)
    except Exception as e:
        return {"error": f"Failed to create task: {e}"}

    projects = _get_projects_from_api(api=api)
    project_map = {p.id: p.name for p in projects}
    return _task_to_dict(task, project_map)


@mcp.tool()
def update_task(
    task_id: str,
    content: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    due_string: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """
    Update an existing Todoist task. Use for GTD inbox processing: fix typos
    (content), add context (description), set due dates, change priority, or
    apply labels. Only the provided fields are updated — omitted fields are
    left unchanged.

    Args:
        task_id: The ID of the task to update.
        content: New task title (use to fix typos or clarify wording).
        description: New description text (use to add context or notes).
        priority: Priority level: 1=normal, 2=medium, 3=high, 4=urgent.
        due_string: Due date in natural language. Examples: "today",
                    "tomorrow", "next Monday", "Jan 15", "every Friday",
                    "every weekday at 9am".
        labels: Full list of labels for the task. Replaces existing labels.

    Returns:
        The updated task dict with id, content, description, priority,
        labels, due, and url fields.
    """
    api = _get_api()

    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if description is not None:
        kwargs["description"] = description
    if priority is not None:
        kwargs["priority"] = priority
    if due_string is not None:
        kwargs["due_string"] = due_string
    if labels is not None:
        kwargs["labels"] = labels

    if not kwargs:
        return {
            "error": "No fields to update. Provide at least one of: content, description, priority, due_string, labels."
        }

    try:
        updated = api.update_task(task_id, **kwargs)
    except Exception as e:
        return {"error": f"Failed to update task {task_id}: {e}"}

    projects = _get_projects_from_api(api=api)
    project_map = {p.id: p.name for p in projects}
    return _task_to_dict(updated, project_map)


@mcp.tool()
def move_task(
    task_id: str,
    project_name: str | None = None,
    section_name: str | None = None,
) -> dict:
    """
    Move a task to a different project and/or section. Use for GTD inbox
    processing to organize tasks into the right project or section (e.g.,
    move from Inbox to "Work" project, "Next Actions" section).

    At least one of project_name or section_name must be provided. Names
    are matched case-insensitively.

    Args:
        task_id: The ID of the task to move.
        project_name: Destination project name (case-insensitive).
        section_name: Destination section name (case-insensitive). If
                      project_name is also given, the section is looked up
                      within that project.

    Returns:
        The updated task dict after moving.
    """
    if not project_name and not section_name:
        return {"error": "At least one of project_name or section_name is required."}

    api = _get_api()

    kwargs = {}
    try:
        project_id = None
        if project_name:
            project_id = _resolve_project_id(api, project_name)
            kwargs["project_id"] = project_id
        if section_name:
            kwargs["section_id"] = _resolve_section_id(
                api, section_name, project_id=project_id
            )
    except ValueError as e:
        return {"error": str(e)}

    try:
        api.move_task(task_id, **kwargs)
    except Exception as e:
        return {"error": f"Failed to move task {task_id}: {e}"}

    # move_task returns bool, so re-fetch the task for the response
    try:
        updated = api.get_task(task_id)
    except Exception as e:
        return {"error": f"Task moved but failed to re-fetch: {e}"}

    projects = _get_projects_from_api(api=api)
    project_map = {p.id: p.name for p in projects}
    return _task_to_dict(updated, project_map)


@mcp.tool()
def add_task_comment(
    task_id: str,
    content: str,
) -> dict:
    """
    Add a comment to a Todoist task. Use for GTD inbox processing to attach
    context, reference links, or notes to a task without changing the task
    itself.

    Args:
        task_id: The ID of the task to comment on.
        content: The comment text (supports Markdown).

    Returns:
        The created comment dict with id, content, and posted_at fields.
    """
    api = _get_api()

    try:
        comment = api.add_comment(task_id=task_id, content=content)
    except Exception as e:
        return {"error": f"Failed to add comment to task {task_id}: {e}"}

    return _comment_to_dict(comment)


@mcp.tool()
def complete_task(
    task_id: str,
) -> dict:
    """
    Mark a Todoist task as complete. Use during GTD inbox review to close
    tasks that are already done or no longer relevant.

    Args:
        task_id: The ID of the task to complete.

    Returns:
        Confirmation dict with the task ID and content.
    """
    api = _get_api()

    try:
        task = api.get_task(task_id)
    except Exception as e:
        return {"error": f"Task {task_id} not found: {e}"}

    try:
        api.complete_task(task_id)
    except Exception as e:
        return {"error": f"Failed to complete task {task_id}: {e}"}

    return {
        "status": "completed",
        "id": task.id,
        "content": task.content,
    }


# --------------------------------------------------------------------------- #
# Write Tools — Project Management
# --------------------------------------------------------------------------- #


@mcp.tool()
def create_project(
    name: str,
    color: str | None = None,
    is_favorite: bool | None = None,
) -> dict:
    """
    Create a new Todoist project.

    Args:
        name: The project name (required).
        color: Project color. Todoist supports colors like "berry_red",
               "red", "orange", "yellow", "olive_green", "lime_green",
               "green", "mint_green", "teal", "sky_blue", "light_blue",
               "blue", "grape", "violet", "lavender", "magenta",
               "salmon", "charcoal", "grey", "taupe".
        is_favorite: If True, the project is marked as a favorite.

    Returns:
        The created project dict with id, name, color, is_favorite, and
        url fields.
    """
    api = _get_api()

    kwargs: dict = {"name": name}
    if color is not None:
        kwargs["color"] = color
    if is_favorite is not None:
        kwargs["is_favorite"] = is_favorite

    try:
        project = api.add_project(**kwargs)
    except Exception as e:
        return {"error": f"Failed to create project: {e}"}

    return _project_to_dict(project)


# --------------------------------------------------------------------------- #
# Write Tools — Label Management
# --------------------------------------------------------------------------- #


@mcp.tool()
def create_label(
    name: str,
    color: str | None = None,
    is_favorite: bool | None = None,
) -> dict:
    """
    Create a new Todoist label. Labels are useful for GTD contexts
    (e.g., @phone, @computer, @errands) and for tagging tasks across
    projects.

    Args:
        name: The label name (required).
        color: Label color. Todoist supports colors like "berry_red",
               "red", "orange", "yellow", "olive_green", "lime_green",
               "green", "mint_green", "teal", "sky_blue", "light_blue",
               "blue", "grape", "violet", "lavender", "magenta",
               "salmon", "charcoal", "grey", "taupe".
        is_favorite: If True, the label is marked as a favorite.

    Returns:
        The created label dict with id, name, color, and is_favorite fields.
    """
    api = _get_api()

    kwargs: dict = {"name": name}
    if color is not None:
        kwargs["color"] = color
    if is_favorite is not None:
        kwargs["is_favorite"] = is_favorite

    try:
        label = api.add_label(**kwargs)
    except Exception as e:
        return {"error": f"Failed to create label: {e}"}

    return _label_to_dict(label)


# --------------------------------------------------------------------------- #
# Supporting Read Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_labels() -> list[dict]:
    """
    List all labels in the user's Todoist account. Use to discover available
    labels before applying them to tasks with update_task(). Labels are a key
    part of GTD contexts (e.g., @phone, @computer, @errands).
    """
    api = _get_api()
    labels = _get_labels_from_api(api=api)
    return [_label_to_dict(l) for l in labels]


@mcp.tool()
def get_sections(
    project_name: str | None = None,
) -> list[dict]:
    """
    List sections, optionally filtered by project name. Use to discover
    available sections before moving tasks with move_task(). Sections
    represent GTD lists like "Next Actions", "Waiting For", "Someday/Maybe".

    Args:
        project_name: If provided, only return sections for the matching
                      project (case-insensitive).

    Returns:
        A list of section dicts with id, name, and project_id fields.
    """
    api = _get_api()

    project_id = None
    if project_name:
        try:
            project_id = _resolve_project_id(api, project_name)
        except ValueError as e:
            return [{"error": str(e)}]

    sections = _get_sections_from_api(api=api, project_id=project_id)
    return [_section_to_dict(s) for s in sections]


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # mcp.run() starts the JSON-RPC event loop on stdin/stdout.
    # The MCP client (Claude Desktop, Claude Code, etc.) will spawn this
    # process and communicate with it over those pipes.
    mcp.run()
