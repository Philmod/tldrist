"""Unit tests for Todoist client."""

import pytest
import respx
from httpx import Response

from tldrist.clients.todoist import TodoistClient, TodoistTask, TodoistProject


class TestTodoistTask:
    """Tests for TodoistTask data class."""

    def test_extract_url_from_content(self) -> None:
        """Should extract URL from task content."""
        data = {
            "id": "123",
            "content": "Read https://example.com/article",
            "description": "",
        }
        task = TodoistTask.from_api_response(data)
        assert task.url == "https://example.com/article"

    def test_extract_url_only(self) -> None:
        """Should handle content that is just a URL."""
        data = {
            "id": "123",
            "content": "https://example.com/article",
            "description": "",
        }
        task = TodoistTask.from_api_response(data)
        assert task.url == "https://example.com/article"

    def test_no_url_in_content(self) -> None:
        """Should return None when no URL in content."""
        data = {
            "id": "123",
            "content": "Buy groceries",
            "description": "",
        }
        task = TodoistTask.from_api_response(data)
        assert task.url is None

    def test_complex_url(self) -> None:
        """Should extract complex URLs with query params."""
        data = {
            "id": "123",
            "content": "https://example.com/path?foo=bar&baz=qux#section",
            "description": "",
        }
        task = TodoistTask.from_api_response(data)
        assert task.url == "https://example.com/path?foo=bar&baz=qux#section"


class TestTodoistClient:
    """Tests for TodoistClient."""

    @pytest.fixture
    def client(self) -> TodoistClient:
        """Create a test client."""
        return TodoistClient(token="test-token")

    @respx.mock
    async def test_get_projects(self, client: TodoistClient) -> None:
        """Should fetch and parse projects."""
        respx.get("https://api.todoist.com/rest/v2/projects").mock(
            return_value=Response(
                200,
                json=[
                    {"id": "1", "name": "Inbox"},
                    {"id": "2", "name": "Read"},
                ],
            )
        )

        projects = await client.get_projects()
        assert len(projects) == 2
        assert projects[0].name == "Inbox"
        assert projects[1].name == "Read"
        await client.close()

    @respx.mock
    async def test_get_project_by_name_found(self, client: TodoistClient) -> None:
        """Should find project by name."""
        respx.get("https://api.todoist.com/rest/v2/projects").mock(
            return_value=Response(
                200,
                json=[
                    {"id": "1", "name": "Inbox"},
                    {"id": "2", "name": "Read"},
                ],
            )
        )

        project = await client.get_project_by_name("Read")
        assert project is not None
        assert project.id == "2"
        assert project.name == "Read"
        await client.close()

    @respx.mock
    async def test_get_project_by_name_not_found(self, client: TodoistClient) -> None:
        """Should return None when project not found."""
        respx.get("https://api.todoist.com/rest/v2/projects").mock(
            return_value=Response(200, json=[{"id": "1", "name": "Inbox"}])
        )

        project = await client.get_project_by_name("Read")
        assert project is None
        await client.close()

    @respx.mock
    async def test_get_tasks(self, client: TodoistClient) -> None:
        """Should fetch tasks for a project."""
        respx.get("https://api.todoist.com/rest/v2/tasks").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "task1",
                        "content": "https://example.com/article1",
                        "description": "",
                    },
                    {
                        "id": "task2",
                        "content": "https://example.com/article2",
                        "description": "existing desc",
                    },
                ],
            )
        )

        tasks = await client.get_tasks("project-id")
        assert len(tasks) == 2
        assert tasks[0].url == "https://example.com/article1"
        assert tasks[1].description == "existing desc"
        await client.close()

    @respx.mock
    async def test_update_task_description(self, client: TodoistClient) -> None:
        """Should update task description."""
        import json

        route = respx.post("https://api.todoist.com/rest/v2/tasks/task-123").mock(
            return_value=Response(200, json={})
        )

        await client.update_task_description("task-123", "New summary")

        assert route.called
        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["description"] == "New summary"
        await client.close()
