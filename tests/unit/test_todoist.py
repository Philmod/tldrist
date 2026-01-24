"""Unit tests for Todoist client."""

import pytest
import respx
from httpx import Response

from tldrist.clients.todoist import TodoistClient, TodoistTask


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
    async def test_get_tasks(self, client: TodoistClient) -> None:
        """Should fetch tasks for a project."""
        respx.get("https://api.todoist.com/api/v1/tasks").mock(
            return_value=Response(
                200,
                json={
                    "results": [
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
                    "next_cursor": None,
                },
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

        route = respx.post("https://api.todoist.com/api/v1/tasks/task-123").mock(
            return_value=Response(200, json={})
        )

        await client.update_task_description("task-123", "New summary")

        assert route.called
        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["description"] == "New summary"
        await client.close()

    @respx.mock
    async def test_close_task(self, client: TodoistClient) -> None:
        """Should close a task."""
        route = respx.post("https://api.todoist.com/api/v1/tasks/task-456/close").mock(
            return_value=Response(204)
        )

        await client.close_task("task-456")

        assert route.called
        await client.close()
