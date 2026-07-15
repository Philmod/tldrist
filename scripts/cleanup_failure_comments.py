"""One-off cleanup: delete transient failure comments from Todoist tasks.

Between 2026-06-01 (Gemini 2.0 Flash shutdown) and the model fix, every run
stamped tasks with "tldrist: summarization failed: 404 ..." comments, which
the orchestrator treats as a permanent skip marker. This script removes
"tldrist: summarization failed:" comments so those tasks are picked up again.
Fetch-failure comments (paywalls, dead links) are left untouched.

Usage:
    export TLDRIST_TODOIST_TOKEN=...       # from Todoist settings > Integrations
    export TLDRIST_TODOIST_PROJECT_ID=...  # the Read project ID
    uv run python scripts/cleanup_failure_comments.py           # dry run (default)
    uv run python scripts/cleanup_failure_comments.py --delete  # actually delete
"""

import asyncio
import os
import sys

import httpx

TODOIST_API_BASE = "https://api.todoist.com/api/v1"
TRANSIENT_COMMENT_PREFIX = "tldrist: summarization failed:"


async def get_paginated(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    """Fetch all pages of a Todoist API v1 list endpoint."""
    results: list[dict] = []
    cursor: str | None = None
    while True:
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        response = await client.get(path, params=page_params)
        response.raise_for_status()
        data = response.json()
        results.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not cursor:
            return results


async def main(delete: bool) -> None:
    token = os.environ.get("TLDRIST_TODOIST_TOKEN")
    project_id = os.environ.get("TLDRIST_TODOIST_PROJECT_ID")
    if not token or not project_id:
        sys.exit("Set TLDRIST_TODOIST_TOKEN and TLDRIST_TODOIST_PROJECT_ID env vars.")

    async with httpx.AsyncClient(
        base_url=TODOIST_API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        tasks = await get_paginated(client, "/tasks", {"project_id": project_id})
        print(f"Found {len(tasks)} tasks in project {project_id}")

        deleted = 0
        for task in tasks:
            comments = await get_paginated(client, "/comments", {"task_id": task["id"]})
            for comment in comments:
                if not comment.get("content", "").startswith(TRANSIENT_COMMENT_PREFIX):
                    continue
                label = f"task {task['id']} ({task['content'][:60]!r})"
                if delete:
                    response = await client.delete(f"/comments/{comment['id']}")
                    response.raise_for_status()
                    print(f"Deleted comment {comment['id']} on {label}")
                else:
                    print(f"Would delete comment {comment['id']} on {label}")
                deleted += 1

        action = "Deleted" if delete else "Would delete"
        print(f"\n{action} {deleted} comment(s).")
        if not delete and deleted:
            print("Re-run with --delete to apply.")


if __name__ == "__main__":
    asyncio.run(main(delete="--delete" in sys.argv))
