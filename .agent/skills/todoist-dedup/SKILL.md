---
name: todoist-dedup
description: >-
  Audits Todoist tasks for duplicates, near-duplicates, stale tasks, and empty projects
  using the todoist-toolbox MCP server. Presents findings for user review, then consolidates
  approved duplicates into a single task with merged metadata and links to originals.
  Use when the user asks to find duplicate tasks, clean up Todoist, run a task hygiene check,
  or deduplicate their task list. Do not use for creating new tasks, managing labels, or
  running recipe automations.
---

# SKILL: Todoist Task Deduplication & Hygiene

## Description

You are an expert at analyzing task lists for redundancy and hygiene issues. When activated,
you use the `todoist-toolbox` MCP tools to fetch all open tasks, detect duplicates and
near-duplicates across projects, flag stale tasks, identify empty projects, and present
structured findings for user review. When the user approves consolidation, you merge
duplicate groups into a single canonical task with the best content, merged metadata, and
comments linking back to the original tasks before closing the duplicates.

## Core Instructions

When activated, execute this workflow in order. Always complete detection and review before
taking any write actions.

---

### Step 1: Fetch All Task Data

Use the MCP tools to gather the full picture. Make these calls in parallel:

- `mcp__todoist-toolbox__get_tasks` (no filters — fetch all open tasks)
- `mcp__todoist-toolbox__get_projects`
- `mcp__todoist-toolbox__get_labels`
- `mcp__todoist-toolbox__get_config_info`

Store the results for analysis. Note: the `_no_robots` label from config is used to exclude
tasks from scheduled recipe automations — it does **not** apply here. Include all tasks
regardless of labels.

---

### Step 2: Detect Duplicates

Compare every pair of open tasks and classify matches into three confidence tiers:

#### Tier 1 — Exact Duplicates (High Confidence)

Two tasks are exact duplicates when their `content` fields are identical after:
1. Lowercasing
2. Stripping leading/trailing whitespace
3. Removing trailing punctuation (`.`, `!`, `?`)

These are presented as definite duplicates.

#### Tier 2 — Near Duplicates (Medium Confidence)

Two tasks are near duplicates when they are not exact but share strong similarity:
- Content differs only by articles (`a`, `an`, `the`), filler words, or minor rephrasing
- One content is a substring of the other (e.g., "Buy milk" vs "Buy milk at the store")
- Same core verb + noun with different modifiers

Use your judgment as an LLM — you are good at this. When in doubt, include the pair at
this tier rather than dropping it.

#### Tier 3 — Semantic Duplicates (Low Confidence)

Two tasks describe the same intent but use different words entirely:
- "Schedule dentist appointment" vs "Book dental checkup"
- "Fix login bug" vs "Auth page not working"

Be conservative here. Only flag pairs where you are reasonably confident they refer to the
same real-world action.

#### Grouping Rules

- Group duplicates transitively: if A matches B and B matches C, present {A, B, C} as one group.
- Within each group, note which tasks are in different projects (cross-project duplicates are
  especially valuable to surface).
- Sort groups by highest confidence tier first, then by group size (larger groups first).

---

### Step 3: Detect Stale Tasks

Flag tasks that meet **all** of these criteria:
- No due date (`due` is null)
- `created_at` is more than 30 days ago
- Not in a project the user has marked as a favorite (favorites may be intentional backlogs)

Sort by age, oldest first.

---

### Step 4: Detect Empty Projects

Compare the project list against all open tasks. Flag any project that:
- Has zero open tasks
- Is not marked as a favorite

---

### Step 5: Present the Hygiene Report

Present findings in a structured report. Use this exact format:

```
## Todoist Hygiene Report

### Duplicate Task Groups

#### Group 1 — [Confidence: High/Medium/Low]
| # | Task | Project | Priority | Due | Created | URL |
|---|------|---------|----------|-----|---------|-----|
| 1 | ...  | ...     | ...      | ... | ...     | ... |
| 2 | ...  | ...     | ...      | ... | ...     | ... |

**Recommendation:** Keep task #N (reason), close the rest.

---

(repeat for each group)

### Stale Tasks (no due date, 30+ days old)
| Task | Project | Created | Age (days) | URL |
|------|---------|---------|------------|-----|
| ...  | ...     | ...     | ...        | ... |

### Empty Projects
| Project | Color | Favorite |
|---------|-------|----------|
| ...     | ...   | ...      |

### Summary
- **X** duplicate groups found (Y total redundant tasks)
- **Z** stale tasks flagged
- **W** empty projects detected
```

After presenting the report, ask the user:

> "Which duplicate groups would you like me to consolidate? You can say 'all', list group
> numbers, or 'none'. For stale tasks, would you like to set due dates, add to a review
> project, or leave them? For empty projects, want me to flag them or leave them?"

**Do not take any write actions until the user responds.**

---

### Step 6: Consolidate Approved Duplicate Groups

For each approved group, execute consolidation in this order:

#### 6a: Determine the Canonical Task

Pick the best task from the group to serve as the basis for the new consolidated task:
- Prefer the task with the most complete description
- Prefer the task with a due date over one without
- Prefer higher priority
- Prefer the task in the most relevant project (use judgment)
- If all else is equal, prefer the oldest task (first created)

#### 6b: Merge Metadata

Build the consolidated task with these rules:

| Field | Merge Strategy |
|-------|---------------|
| `content` | Use the most descriptive/complete version from the group |
| `description` | Combine unique description content from all tasks. Append a "Consolidated from" section (see template below) |
| `priority` | Use the highest priority from any task in the group |
| `due` | Use the earliest due date. If only some tasks have due dates, use the one that exists |
| `labels` | Union of all labels from all tasks in the group |
| `project` | Use the canonical task's project (or ask the user if ambiguous) |

#### 6c: Build the Description

Use this template for the consolidated description:

```
{merged description content}

---
Consolidated from duplicate tasks on {today's date}:
- {task.content} (Project: {project_name}) — {task.url}
- {task.content} (Project: {project_name}) — {task.url}
```

#### 6d: Create the New Task

Use `mcp__todoist-toolbox__create_task` to create the consolidated task with all merged
fields.

#### 6e: Comment on and Close Originals

For each original task in the group:

1. Use `mcp__todoist-toolbox__add_task_comment` to add a comment:
   ```
   This task was consolidated into a new task as part of a duplicate cleanup on {date}.
   New task: {new_task.url}
   ```
2. Use `mcp__todoist-toolbox__complete_task` to close it.

#### 6f: Confirm

After processing all groups, present a summary:

```
## Consolidation Complete

| Group | New Task | Closed Tasks | URL |
|-------|----------|-------------|-----|
| 1     | "..."    | 3           | ... |
| 2     | "..."    | 2           | ... |

Total: X new tasks created, Y duplicates closed.
```

---

### Step 7: Handle Stale Tasks (If Requested)

If the user wants action on stale tasks, offer these options per task or in bulk:
- **Set a due date**: Use `mcp__todoist-toolbox__update_task` to add a due date
- **Move to a review project**: Use `mcp__todoist-toolbox__move_task`
- **Add a label**: Use `mcp__todoist-toolbox__update_task` to tag for later review
- **Complete**: Use `mcp__todoist-toolbox__complete_task` if the user says it's done

---

### Step 8: Handle Empty Projects (If Requested)

If the user wants to clean up empty projects, note that the MCP server does not currently
have a `delete_project` tool. Inform the user which projects are empty and suggest they
delete them manually in Todoist, or offer to create a task reminding them to clean up.

---

## Rules & Guardrails

- **NEVER** modify, complete, or create tasks without explicit user approval for each action group.
- **NEVER** skip tasks based on the `_no_robots` label — that label only applies to scheduled recipe automations, not to this skill.
- **NEVER** delete or close a task without first adding a comment explaining the consolidation and linking to the replacement.
- **ALWAYS** present the full hygiene report and wait for user instructions before any write operations.
- **ALWAYS** preserve all metadata (labels, priority, due dates, descriptions) during consolidation — nothing should be lost.
- **ALWAYS** include original task URLs in the consolidated task's description so the user can trace history.
- **ALWAYS** use the MCP tools from the `todoist-toolbox` server — do not attempt direct API calls.
- **ALWAYS** respect task priority ordering: 4=urgent > 3=high > 2=medium > 1=normal (Todoist's scale is inverted from intuition).
