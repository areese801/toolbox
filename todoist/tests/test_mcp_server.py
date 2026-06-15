"""Tests for todoist.mcp_server MCP tool functions."""

from unittest.mock import MagicMock, patch
from datetime import date

import pytest

from todoist.tests.helpers import (
    make_task,
    make_due,
    make_label,
    make_section,
    make_comment,
)


def _make_project(
    project_id="proj_1",
    name="Work",
    color="sky_blue",
    is_favorite=False,
    url="https://todoist.com/project/1",
):
    """Create a mock Todoist Project object."""
    p = MagicMock()
    p.id = project_id
    p.name = name
    p.color = color
    p.is_favorite = is_favorite
    p.url = url
    return p


# --------------------------------------------------------------------------- #
# _task_to_dict
# --------------------------------------------------------------------------- #


class TestTaskToDict:
    """Tests for the _task_to_dict helper."""

    def test_basic_fields(self):
        from todoist.mcp_server import _task_to_dict

        task = make_task(
            task_id="42",
            content="Buy milk",
            description="2%",
            priority=1,
            labels=["Errands"],
            is_completed=False,
            created_at="2026-01-01T00:00:00Z",
            project_id="proj_1",
            _no_due=True,
        )

        result = _task_to_dict(task)

        assert result["id"] == "42"
        assert result["content"] == "Buy milk"
        assert result["description"] == "2%"
        assert result["priority"] == 1
        assert result["labels"] == ["Errands"]
        assert result["is_completed"] is False
        assert result["url"] == "https://app.todoist.com/app/task/42"
        assert result["due"] is None

    def test_with_project_map(self):
        from todoist.mcp_server import _task_to_dict

        task = make_task(task_id="1", content="Task", project_id="proj_1", _no_due=True)
        project_map = {"proj_1": "Work"}

        result = _task_to_dict(task, project_map)

        assert result["project_name"] == "Work"
        assert result["project_id"] == "proj_1"

    def test_unknown_project_id(self):
        from todoist.mcp_server import _task_to_dict

        task = make_task(
            task_id="1", content="Task", project_id="missing", _no_due=True
        )
        project_map = {"proj_1": "Work"}

        result = _task_to_dict(task, project_map)

        assert result["project_name"] == "Unknown"

    def test_with_due_date(self):
        from todoist.mcp_server import _task_to_dict

        due = make_due(
            due_date=date(2026, 4, 10), due_string="tomorrow", is_recurring=False
        )
        task = make_task(task_id="1", content="Task", due=due, project_id="proj_1")

        result = _task_to_dict(task)

        assert result["due"]["date"] == str(date(2026, 4, 10))
        assert result["due"]["is_recurring"] is False
        assert result["due"]["string"] == "tomorrow"


# --------------------------------------------------------------------------- #
# _project_to_dict
# --------------------------------------------------------------------------- #


class TestProjectToDict:
    """Tests for the _project_to_dict helper."""

    def test_converts_project(self):
        from todoist.mcp_server import _project_to_dict

        project = _make_project(
            project_id="p1",
            name="Personal",
            color="red",
            is_favorite=True,
            url="https://todoist.com/p1",
        )

        result = _project_to_dict(project)

        assert result == {
            "id": "p1",
            "name": "Personal",
            "color": "red",
            "is_favorite": True,
            "url": "https://todoist.com/p1",
        }


# --------------------------------------------------------------------------- #
# get_tasks (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetTasks:
    """Tests for the get_tasks MCP tool."""

    def _patch_api_and_projects(self, tasks, projects):
        """Return context managers that patch _get_api and _get_projects_from_api."""
        mock_api = MagicMock()
        return (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=projects),
            patch("todoist.mcp_server.get_active_tasks", return_value=tasks),
            mock_api,
        )

    def test_returns_all_active_tasks(self):
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task = make_task(
            task_id="1",
            content="Do stuff",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        api_patch, proj_patch, tasks_patch, _ = self._patch_api_and_projects(
            [task], [proj]
        )

        with api_patch, proj_patch, tasks_patch:
            result = get_tasks()

        assert len(result) == 1
        assert result[0]["content"] == "Do stuff"
        assert result[0]["project_name"] == "Work"

    def test_filter_by_project_name(self):
        from todoist.mcp_server import get_tasks

        proj_work = _make_project(project_id="p1", name="Work")
        proj_personal = _make_project(project_id="p2", name="Personal")
        task1 = make_task(
            task_id="1",
            content="Work task",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )
        task2 = make_task(
            task_id="2",
            content="Personal task",
            project_id="p2",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        api_patch, proj_patch, tasks_patch, _ = self._patch_api_and_projects(
            [task1, task2], [proj_work, proj_personal]
        )

        with api_patch, proj_patch, tasks_patch:
            result = get_tasks(project_name="personal")

        assert len(result) == 1
        assert result[0]["content"] == "Personal task"

    def test_filter_by_label(self):
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task1 = make_task(
            task_id="1",
            content="Labeled",
            project_id="p1",
            description="",
            priority=1,
            labels=["Work"],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )
        task2 = make_task(
            task_id="2",
            content="Not labeled",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        api_patch, proj_patch, tasks_patch, _ = self._patch_api_and_projects(
            [task1, task2], [proj]
        )

        with api_patch, proj_patch, tasks_patch:
            result = get_tasks(label="Work")

        assert len(result) == 1
        assert result[0]["content"] == "Labeled"

    def test_excludes_completed_by_default(self):
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task = make_task(
            task_id="1",
            content="Done",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=True,
            created_at="2026-01-01",
            _no_due=True,
        )

        api_patch, proj_patch, tasks_patch, _ = self._patch_api_and_projects(
            [task], [proj]
        )

        with api_patch, proj_patch, tasks_patch:
            result = get_tasks()

        assert len(result) == 0

    def test_includes_completed_when_requested(self):
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task = make_task(
            task_id="1",
            content="Done",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=True,
            created_at="2026-01-01",
            _no_due=True,
        )

        api_patch, proj_patch, tasks_patch, _ = self._patch_api_and_projects(
            [task], [proj]
        )

        with api_patch, proj_patch, tasks_patch:
            result = get_tasks(include_completed=True)

        assert len(result) == 1
        assert result[0]["content"] == "Done"

    def test_uses_todoist_filter(self):
        """When a filter string is provided, it should use api.filter_tasks(query=...)."""
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task = make_task(
            task_id="1",
            content="Today task",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.filter_tasks.return_value = [[task]]  # paginator returns pages

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = get_tasks(filter="today")

        mock_api.filter_tasks.assert_called_once_with(query="today")
        assert len(result) == 1

    def test_filter_error_returns_error_dict(self):
        """When the Todoist filter API fails, return an error dict instead of raising."""
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        mock_api = MagicMock()
        mock_api.filter_tasks.side_effect = Exception("bad filter")

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = get_tasks(filter="invalid!!")

        assert len(result) == 1
        assert "error" in result[0]
        assert "bad filter" in result[0]["error"]

    def test_calls_get_projects_from_api_not_mcp_tool(self):
        """Regression: get_tasks must call _get_projects_from_api (todoist_tasks),
        not the MCP tool get_projects which doesn't accept api=."""
        from todoist.mcp_server import get_tasks

        proj = _make_project(project_id="p1", name="Work")
        task = make_task(
            task_id="1",
            content="Task",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server._get_projects_from_api", return_value=[proj]
            ) as mock_gp,
            patch("todoist.mcp_server.get_active_tasks", return_value=[task]),
        ):
            get_tasks()

        mock_gp.assert_called_once_with(api=mock_api)


# --------------------------------------------------------------------------- #
# get_projects (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetProjects:
    """Tests for the get_projects MCP tool."""

    def test_returns_project_dicts_from_list(self):
        from todoist.mcp_server import get_projects

        proj = _make_project(project_id="p1", name="Work", color="sky_blue")
        mock_api = MagicMock()
        mock_api.get_projects.return_value = [proj]

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = get_projects()

        assert len(result) == 1
        assert result[0]["name"] == "Work"
        assert result[0]["color"] == "sky_blue"

    def test_handles_paginated_response(self):
        from todoist.mcp_server import get_projects

        p1 = _make_project(project_id="p1", name="Work")
        p2 = _make_project(project_id="p2", name="Personal")

        mock_api = MagicMock()
        # Simulate paginator: not a list, but an iterable of pages
        paginator = MagicMock()
        paginator.__iter__ = MagicMock(return_value=iter([[p1], [p2]]))
        paginator.__class__ = type("Paginator", (), {})  # not a list
        mock_api.get_projects.return_value = paginator

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = get_projects()

        assert len(result) == 2
        assert result[0]["name"] == "Work"
        assert result[1]["name"] == "Personal"


# --------------------------------------------------------------------------- #
# get_task_summary (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetTaskSummary:
    """Tests for the get_task_summary MCP tool."""

    def test_basic_summary(self):
        from todoist.mcp_server import get_task_summary

        proj = _make_project(project_id="p1", name="Work")

        overdue_task = make_task(
            task_id="1",
            content="Overdue",
            due=make_due(due_date=date(2026, 4, 1), is_recurring=False),
            project_id="p1",
            priority=4,
            is_completed=False,
        )
        today_task = make_task(
            task_id="2",
            content="Today",
            due=make_due(due_date=date.today(), is_recurring=False),
            project_id="p1",
            priority=1,
            is_completed=False,
        )
        no_due_task = make_task(
            task_id="3",
            content="Someday",
            project_id="p1",
            priority=1,
            is_completed=False,
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.get_projects.return_value = [proj]

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server.get_active_tasks",
                return_value=[overdue_task, today_task, no_due_task],
            ),
        ):
            result = get_task_summary()

        assert result["total_open_tasks"] == 3
        assert result["overdue_count"] == 1
        assert result["overdue_tasks"] == ["Overdue"]
        assert result["due_today_count"] == 1
        assert result["due_today_tasks"] == ["Today"]
        assert result["no_due_date_count"] == 1
        assert result["by_project"]["Work"] == 3
        assert result["by_priority"]["p1_urgent"] == 1  # priority 4
        assert result["by_priority"]["p4_normal"] == 2  # priority 1


# --------------------------------------------------------------------------- #
# get_config_info (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetConfigInfo:
    """Tests for the get_config_info MCP tool."""

    def test_returns_config(self):
        from todoist.mcp_server import get_config_info

        fake_config = {"work_label": "Work", "project_color": "sky_blue"}

        with patch("todoist.mcp_server.get_config", return_value=fake_config):
            result = get_config_info()

        assert result == fake_config


# --------------------------------------------------------------------------- #
# update_task (MCP tool)
# --------------------------------------------------------------------------- #


class TestUpdateTask:
    """Tests for the update_task MCP tool."""

    def test_updates_content(self):
        from todoist.mcp_server import update_task

        proj = _make_project(project_id="p1", name="Inbox")
        updated_task = make_task(
            task_id="1001",
            content="Fixed typo",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.update_task.return_value = updated_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = update_task(task_id="1001", content="Fixed typo")

        mock_api.update_task.assert_called_once_with("1001", content="Fixed typo")
        assert result["content"] == "Fixed typo"

    def test_updates_multiple_fields(self):
        from todoist.mcp_server import update_task

        proj = _make_project(project_id="p1", name="Inbox")
        due = make_due(
            due_date=date(2026, 4, 15), due_string="tomorrow", is_recurring=False
        )
        updated_task = make_task(
            task_id="1001",
            content="Task",
            project_id="p1",
            description="Added context",
            priority=3,
            labels=["Work"],
            is_completed=False,
            created_at="2026-01-01",
            due=due,
        )

        mock_api = MagicMock()
        mock_api.update_task.return_value = updated_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = update_task(
                task_id="1001",
                description="Added context",
                priority=3,
                due_string="tomorrow",
                labels=["Work"],
            )

        mock_api.update_task.assert_called_once_with(
            "1001",
            description="Added context",
            priority=3,
            due_string="tomorrow",
            labels=["Work"],
        )
        assert result["description"] == "Added context"
        assert result["due"]["string"] == "tomorrow"

    def test_no_fields_returns_error(self):
        from todoist.mcp_server import update_task

        mock_api = MagicMock()

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = update_task(task_id="1001")

        assert "error" in result
        mock_api.update_task.assert_not_called()

    def test_api_error_returns_error(self):
        from todoist.mcp_server import update_task

        mock_api = MagicMock()
        mock_api.update_task.side_effect = Exception("not found")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = update_task(task_id="9999", content="x")

        assert "error" in result
        assert "not found" in result["error"]


# --------------------------------------------------------------------------- #
# move_task (MCP tool)
# --------------------------------------------------------------------------- #


class TestMoveTask:
    """Tests for the move_task MCP tool."""

    def test_move_to_project(self):
        from todoist.mcp_server import move_task

        proj = _make_project(project_id="p2", name="Work")
        moved_task = make_task(
            task_id="1001",
            content="Task",
            project_id="p2",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.move_task.return_value = True
        mock_api.get_task.return_value = moved_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = move_task(task_id="1001", project_name="Work")

        mock_api.move_task.assert_called_once_with("1001", project_id="p2")
        assert result["project_name"] == "Work"

    def test_move_to_section(self):
        from todoist.mcp_server import move_task

        proj = _make_project(project_id="p1", name="Inbox")
        moved_task = make_task(
            task_id="1001",
            content="Task",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.move_task.return_value = True
        mock_api.get_task.return_value = moved_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_section_id", return_value="sec_1"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = move_task(task_id="1001", section_name="Next Actions")

        mock_api.move_task.assert_called_once_with("1001", section_id="sec_1")

    def test_move_to_project_and_section(self):
        from todoist.mcp_server import move_task

        proj = _make_project(project_id="p2", name="Work")
        moved_task = make_task(
            task_id="1001",
            content="Task",
            project_id="p2",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.move_task.return_value = True
        mock_api.get_task.return_value = moved_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._resolve_section_id", return_value="sec_1"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = move_task(
                task_id="1001", project_name="Work", section_name="Next Actions"
            )

        mock_api.move_task.assert_called_once_with(
            "1001", project_id="p2", section_id="sec_1"
        )

    def test_no_destination_returns_error(self):
        from todoist.mcp_server import move_task

        result = move_task(task_id="1001")

        assert "error" in result

    def test_invalid_project_returns_error(self):
        from todoist.mcp_server import move_task

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server._resolve_project_id",
                side_effect=ValueError(
                    "Project 'Nope' not found. Available projects: ['Work']"
                ),
            ),
        ):
            result = move_task(task_id="1001", project_name="Nope")

        assert "error" in result
        assert "not found" in result["error"]

    def test_api_error_returns_error(self):
        from todoist.mcp_server import move_task

        mock_api = MagicMock()
        mock_api.move_task.side_effect = Exception("server error")

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[]),
        ):
            result = move_task(task_id="1001", project_name="Work")

        assert "error" in result
        assert "server error" in result["error"]


# --------------------------------------------------------------------------- #
# add_task_comment (MCP tool)
# --------------------------------------------------------------------------- #


class TestAddTaskComment:
    """Tests for the add_task_comment MCP tool."""

    def test_adds_comment(self):
        from todoist.mcp_server import add_task_comment

        comment = make_comment(
            comment_id="com_1",
            content="Reference link",
            task_id="1001",
            posted_at="2026-04-14T12:00:00Z",
        )

        mock_api = MagicMock()
        mock_api.add_comment.return_value = comment

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = add_task_comment(task_id="1001", content="Reference link")

        mock_api.add_comment.assert_called_once_with(
            task_id="1001", content="Reference link"
        )
        assert result["id"] == "com_1"
        assert result["content"] == "Reference link"
        assert result["posted_at"] == "2026-04-14T12:00:00Z"

    def test_api_error_returns_error(self):
        from todoist.mcp_server import add_task_comment

        mock_api = MagicMock()
        mock_api.add_comment.side_effect = Exception("task not found")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = add_task_comment(task_id="9999", content="note")

        assert "error" in result
        assert "task not found" in result["error"]


# --------------------------------------------------------------------------- #
# complete_task (MCP tool)
# --------------------------------------------------------------------------- #


class TestCompleteTask:
    """Tests for the complete_task MCP tool."""

    def test_completes_task(self):
        from todoist.mcp_server import complete_task

        task = make_task(
            task_id="1001",
            content="Done task",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-01-01",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.get_task.return_value = task
        mock_api.complete_task.return_value = True

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = complete_task(task_id="1001")

        mock_api.get_task.assert_called_once_with("1001")
        mock_api.complete_task.assert_called_once_with("1001")
        assert result["status"] == "completed"
        assert result["id"] == "1001"
        assert result["content"] == "Done task"

    def test_task_not_found_returns_error(self):
        from todoist.mcp_server import complete_task

        mock_api = MagicMock()
        mock_api.get_task.side_effect = Exception("not found")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = complete_task(task_id="9999")

        assert "error" in result
        assert "not found" in result["error"]
        mock_api.complete_task.assert_not_called()

    def test_complete_api_error_returns_error(self):
        from todoist.mcp_server import complete_task

        task = make_task(task_id="1001", content="Task", _no_due=True)
        mock_api = MagicMock()
        mock_api.get_task.return_value = task
        mock_api.complete_task.side_effect = Exception("server error")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = complete_task(task_id="1001")

        assert "error" in result
        assert "server error" in result["error"]


# --------------------------------------------------------------------------- #
# get_labels (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetLabels:
    """Tests for the get_labels MCP tool."""

    def test_returns_labels(self):
        from todoist.mcp_server import get_labels

        lab1 = make_label(
            label_id="l1", name="Work", color="sky_blue", is_favorite=True
        )
        lab2 = make_label(label_id="l2", name="Errands", color="red", is_favorite=False)

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_labels_from_api", return_value=[lab1, lab2]),
        ):
            result = get_labels()

        assert len(result) == 2
        assert result[0] == {
            "id": "l1",
            "name": "Work",
            "color": "sky_blue",
            "is_favorite": True,
        }
        assert result[1] == {
            "id": "l2",
            "name": "Errands",
            "color": "red",
            "is_favorite": False,
        }

    def test_returns_empty_list(self):
        from todoist.mcp_server import get_labels

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_labels_from_api", return_value=[]),
        ):
            result = get_labels()

        assert result == []


# --------------------------------------------------------------------------- #
# get_sections (MCP tool)
# --------------------------------------------------------------------------- #


class TestGetSections:
    """Tests for the get_sections MCP tool."""

    def test_returns_all_sections(self):
        from todoist.mcp_server import get_sections

        sec1 = make_section(section_id="s1", name="Next Actions", project_id="p1")
        sec2 = make_section(section_id="s2", name="Waiting For", project_id="p1")

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server._get_sections_from_api", return_value=[sec1, sec2]
            ),
        ):
            result = get_sections()

        assert len(result) == 2
        assert result[0] == {"id": "s1", "name": "Next Actions", "project_id": "p1"}

    def test_filters_by_project_name(self):
        from todoist.mcp_server import get_sections

        sec = make_section(section_id="s1", name="Next Actions", project_id="p2")

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._get_sections_from_api", return_value=[sec]),
        ):
            result = get_sections(project_name="Work")

        assert len(result) == 1

    def test_invalid_project_returns_error(self):
        from todoist.mcp_server import get_sections

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server._resolve_project_id",
                side_effect=ValueError(
                    "Project 'Nope' not found. Available projects: []"
                ),
            ),
        ):
            result = get_sections(project_name="Nope")

        assert len(result) == 1
        assert "error" in result[0]


# --------------------------------------------------------------------------- #
# create_task (MCP tool)
# --------------------------------------------------------------------------- #


class TestCreateTask:
    """Tests for the create_task MCP tool."""

    def test_creates_basic_task(self):
        from todoist.mcp_server import create_task

        proj = _make_project(project_id="p1", name="Inbox")
        created_task = make_task(
            task_id="2001",
            content="Buy groceries",
            project_id="p1",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-04-14",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.add_task.return_value = created_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = create_task(content="Buy groceries")

        mock_api.add_task.assert_called_once_with(content="Buy groceries")
        assert result["id"] == "2001"
        assert result["content"] == "Buy groceries"

    def test_creates_task_with_all_fields(self):
        from todoist.mcp_server import create_task

        proj = _make_project(project_id="p2", name="Work")
        due = make_due(
            due_date=date(2026, 4, 15), due_string="tomorrow", is_recurring=False
        )
        created_task = make_task(
            task_id="2002",
            content="Write report",
            project_id="p2",
            description="Q1 summary",
            priority=3,
            labels=["Work"],
            is_completed=False,
            created_at="2026-04-14",
            due=due,
        )

        mock_api = MagicMock()
        mock_api.add_task.return_value = created_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._resolve_section_id", return_value="sec_1"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            result = create_task(
                content="Write report",
                project_name="Work",
                section_name="Next Actions",
                description="Q1 summary",
                priority=3,
                due_string="tomorrow",
                labels=["Work"],
            )

        mock_api.add_task.assert_called_once_with(
            content="Write report",
            project_id="p2",
            section_id="sec_1",
            description="Q1 summary",
            priority=3,
            due_string="tomorrow",
            labels=["Work"],
        )
        assert result["content"] == "Write report"
        assert result["due"]["string"] == "tomorrow"

    def test_creates_task_in_project(self):
        from todoist.mcp_server import create_task

        proj = _make_project(project_id="p2", name="Work")
        created_task = make_task(
            task_id="2003",
            content="Task",
            project_id="p2",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-04-14",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.add_task.return_value = created_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            create_task(content="Task", project_name="Work")

        mock_api.add_task.assert_called_once_with(content="Task", project_id="p2")

    def test_creates_task_in_section(self):
        from todoist.mcp_server import create_task

        proj = _make_project(project_id="p2", name="Work")
        created_task = make_task(
            task_id="2004",
            content="Task",
            project_id="p2",
            description="",
            priority=1,
            labels=[],
            is_completed=False,
            created_at="2026-04-14",
            _no_due=True,
        )

        mock_api = MagicMock()
        mock_api.add_task.return_value = created_task

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch("todoist.mcp_server._resolve_project_id", return_value="p2"),
            patch("todoist.mcp_server._resolve_section_id", return_value="sec_1"),
            patch("todoist.mcp_server._get_projects_from_api", return_value=[proj]),
        ):
            create_task(
                content="Task", project_name="Work", section_name="Next Actions"
            )

        mock_api.add_task.assert_called_once_with(
            content="Task",
            project_id="p2",
            section_id="sec_1",
        )

    def test_invalid_project_returns_error(self):
        from todoist.mcp_server import create_task

        mock_api = MagicMock()

        with (
            patch("todoist.mcp_server._get_api", return_value=mock_api),
            patch(
                "todoist.mcp_server._resolve_project_id",
                side_effect=ValueError(
                    "Project 'Nope' not found. Available projects: ['Work']"
                ),
            ),
        ):
            result = create_task(content="Task", project_name="Nope")

        assert "error" in result
        assert "not found" in result["error"]
        mock_api.add_task.assert_not_called()

    def test_api_error_returns_error(self):
        from todoist.mcp_server import create_task

        mock_api = MagicMock()
        mock_api.add_task.side_effect = Exception("server error")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_task(content="Task")

        assert "error" in result
        assert "server error" in result["error"]


# --------------------------------------------------------------------------- #
# create_project (MCP tool)
# --------------------------------------------------------------------------- #


class TestCreateProject:
    """Tests for the create_project MCP tool."""

    def test_creates_basic_project(self):
        from todoist.mcp_server import create_project

        proj = _make_project(
            project_id="p10",
            name="New Project",
            color="charcoal",
            is_favorite=False,
            url="https://todoist.com/project/p10",
        )

        mock_api = MagicMock()
        mock_api.add_project.return_value = proj

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_project(name="New Project")

        mock_api.add_project.assert_called_once_with(name="New Project")
        assert result["id"] == "p10"
        assert result["name"] == "New Project"

    def test_creates_project_with_all_fields(self):
        from todoist.mcp_server import create_project

        proj = _make_project(
            project_id="p11",
            name="Hobbies",
            color="berry_red",
            is_favorite=True,
            url="https://todoist.com/project/p11",
        )

        mock_api = MagicMock()
        mock_api.add_project.return_value = proj

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_project(name="Hobbies", color="berry_red", is_favorite=True)

        mock_api.add_project.assert_called_once_with(
            name="Hobbies",
            color="berry_red",
            is_favorite=True,
        )
        assert result["color"] == "berry_red"
        assert result["is_favorite"] is True

    def test_api_error_returns_error(self):
        from todoist.mcp_server import create_project

        mock_api = MagicMock()
        mock_api.add_project.side_effect = Exception("quota exceeded")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_project(name="Fail")

        assert "error" in result
        assert "quota exceeded" in result["error"]


# --------------------------------------------------------------------------- #
# create_label (MCP tool)
# --------------------------------------------------------------------------- #


class TestCreateLabel:
    """Tests for the create_label MCP tool."""

    def test_creates_basic_label(self):
        from todoist.mcp_server import create_label

        lab = make_label(label_id="l10", name="Errands", color="charcoal", is_favorite=False)

        mock_api = MagicMock()
        mock_api.add_label.return_value = lab

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_label(name="Errands")

        mock_api.add_label.assert_called_once_with(name="Errands")
        assert result["id"] == "l10"
        assert result["name"] == "Errands"

    def test_creates_label_with_all_fields(self):
        from todoist.mcp_server import create_label

        lab = make_label(
            label_id="l11", name="@phone", color="sky_blue", is_favorite=True
        )

        mock_api = MagicMock()
        mock_api.add_label.return_value = lab

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_label(name="@phone", color="sky_blue", is_favorite=True)

        mock_api.add_label.assert_called_once_with(
            name="@phone",
            color="sky_blue",
            is_favorite=True,
        )
        assert result["color"] == "sky_blue"
        assert result["is_favorite"] is True

    def test_api_error_returns_error(self):
        from todoist.mcp_server import create_label

        mock_api = MagicMock()
        mock_api.add_label.side_effect = Exception("duplicate name")

        with patch("todoist.mcp_server._get_api", return_value=mock_api):
            result = create_label(name="Fail")

        assert "error" in result
        assert "duplicate name" in result["error"]
