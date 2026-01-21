"""Todoist REST API v1 client for TLDRist."""

import re
from dataclasses import dataclass

import httpx

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

TODOIST_API_BASE = "https://api.todoist.com/api/v1"

URL_PATTERN = re.compile(r"https?://[^\s<>\[\]()]+")


@dataclass
class TodoistTask:
    """Represents a Todoist task."""

    id: str
    content: str
    description: str
    url: str | None

    @classmethod
    def from_api_response(cls, data: dict) -> "TodoistTask":
        """Create a TodoistTask from API response data."""
        content = data["content"]
        url = cls._extract_url(content)
        return cls(
            id=data["id"],
            content=content,
            description=data.get("description", ""),
            url=url,
        )

    @staticmethod
    def _extract_url(content: str) -> str | None:
        """Extract a URL from task content."""
        match = URL_PATTERN.search(content)
        return match.group(0) if match else None


class TodoistClient:
    """Client for interacting with the Todoist REST API v1."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=TODOIST_API_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TodoistClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def get_tasks(self, project_id: str) -> list[TodoistTask]:
        """Get all tasks in a project.

        Args:
            project_id: The ID of the project.

        Returns:
            List of TodoistTask objects.
        """
        logger.info("Fetching tasks for project", project_id=project_id)
        response = await self._client.get("/tasks", params={"project_id": project_id})
        response.raise_for_status()
        data = response.json()
        # API v1 wraps results in a "results" array
        results = data.get("results", [])
        tasks = [TodoistTask.from_api_response(t) for t in results]
        logger.info("Found tasks", count=len(tasks))
        return tasks

    async def update_task_description(self, task_id: str, description: str) -> None:
        """Update a task's description.

        Args:
            task_id: The ID of the task to update.
            description: The new description content.
        """
        logger.info("Updating task description", task_id=task_id)
        response = await self._client.post(
            f"/tasks/{task_id}",
            json={"description": description},
        )
        response.raise_for_status()
        logger.info("Task description updated", task_id=task_id)
