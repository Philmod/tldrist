"""Unit tests for Orchestrator."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tldrist.clients.article import FetchError
from tldrist.clients.todoist import TodoistTask
from tldrist.models import FailedArticle
from tldrist.services.orchestrator import Orchestrator
from tldrist.services.summarizer import ProcessedArticle


def _make_task(task_id: str, url: str) -> TodoistTask:
    return TodoistTask(id=task_id, content=f"Read {url}", description="", url=url)


def _make_processed(task_id: str, url: str) -> ProcessedArticle:
    return ProcessedArticle(
        task_id=task_id,
        url=url,
        title=f"Title {task_id}",
        summary=f"Summary {task_id}",
        processed_at=datetime.now(timezone.utc),
    )


class TestOrchestratorMaxLimit:
    """Tests that max applies to successful results, not input."""

    @pytest.fixture
    def orchestrator(self) -> Orchestrator:
        todoist = MagicMock()
        todoist.get_tasks = AsyncMock(return_value=[])
        todoist.get_comments = AsyncMock(return_value=[])
        todoist.add_comment = AsyncMock()
        fetcher = MagicMock()
        gemini = MagicMock()
        gmail = MagicMock()
        return Orchestrator(
            todoist_client=todoist,
            article_fetcher=fetcher,
            gemini_client=gemini,
            gmail_client=gmail,
            recipient_email="test@example.com",
            todoist_project_id="project-1",
            podcast_enabled=False,
        )

    async def test_max_applies_to_results_not_input(self, orchestrator: Orchestrator) -> None:
        """max=1 should process all 3 tasks but only include 1 successful article."""
        tasks = [
            _make_task("1", "https://example.com/a"),
            _make_task("2", "https://example.com/b"),
            _make_task("3", "https://example.com/c"),
        ]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        # Task 1 fails, tasks 2 and 3 succeed
        call_count = 0

        async def mock_fetch(url: str):
            nonlocal call_count
            call_count += 1
            if url == "https://example.com/a":
                raise FetchError("HTTP 403")
            return MagicMock(
                url=url, title=f"Title {url}", content="content", word_count=100, is_valid=True
            )

        orchestrator._fetcher.fetch = mock_fetch
        orchestrator._summarizer.summarize = AsyncMock(
            side_effect=lambda tid, art: _make_processed(tid, art.url)
        )
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True, max=1)

        # All 3 tasks were attempted
        assert call_count == 3
        # Only 1 article in the digest (max=1)
        assert result.articles_processed == 1
        # 1 failed
        assert result.articles_failed == 1


class TestOrchestratorFailedArticles:
    """Tests that failed articles are collected and passed to compose_digest."""

    @pytest.fixture
    def orchestrator(self) -> Orchestrator:
        todoist = MagicMock()
        todoist.get_tasks = AsyncMock(return_value=[])
        todoist.get_comments = AsyncMock(return_value=[])
        todoist.add_comment = AsyncMock()
        fetcher = MagicMock()
        gemini = MagicMock()
        gmail = MagicMock()
        return Orchestrator(
            todoist_client=todoist,
            article_fetcher=fetcher,
            gemini_client=gemini,
            gmail_client=gmail,
            recipient_email="test@example.com",
            todoist_project_id="project-1",
            podcast_enabled=False,
        )

    async def test_all_articles_fail_collects_reasons(self, orchestrator: Orchestrator) -> None:
        """When all articles fail, result should reflect failures and skip email."""
        tasks = [
            _make_task("1", "https://nyt.com/article"),
            _make_task("2", "https://ibm.com/article"),
        ]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        async def mock_fetch(url: str):
            if "nyt.com" in url:
                raise FetchError("HTTP 403")
            raise FetchError("content extraction failed")

        orchestrator._fetcher.fetch = mock_fetch
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        assert result.articles_processed == 0
        assert result.articles_failed == 2
        assert result.skipped is True
        # compose_digest is not called when all articles fail
        orchestrator._digest.compose_digest.assert_not_called()

    async def test_single_failure_skips_email(
        self, orchestrator: Orchestrator
    ) -> None:
        """A single failed article (with no successes) should skip email."""
        tasks = [_make_task("1", "https://example.com/fail")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        async def mock_fetch(url: str):
            raise FetchError("timeout")

        orchestrator._fetcher.fetch = mock_fetch
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        assert result.articles_failed == 1
        assert result.skipped is True
        orchestrator._digest.compose_digest.assert_not_called()

    async def test_task_without_url_returns_failed_article(
        self, orchestrator: Orchestrator
    ) -> None:
        """A task with url=None should be tracked as a FailedArticle."""
        task = TodoistTask(id="1", content="Read something", description="", url=None)
        result = await orchestrator._process_task(task)

        assert isinstance(result, FailedArticle)
        assert result.url == ""
        assert result.reason == "no URL"

    async def test_unexpected_exception_tracked_as_failed(
        self, orchestrator: Orchestrator
    ) -> None:
        """When _process_task raises an unexpected exception, it should be tracked as a FailedArticle."""
        tasks = [_make_task("1", "https://example.com/crash")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        # Simulate an unexpected exception bypassing _process_task's own error handling
        orchestrator._process_task = AsyncMock(side_effect=RuntimeError("unexpected crash"))
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        assert result.articles_processed == 0
        assert result.articles_failed == 1
        assert result.skipped is True

    async def test_summarizer_failure_returns_failed_article(
        self, orchestrator: Orchestrator
    ) -> None:
        """When summarizer raises, the article should be tracked as failed."""
        tasks = [_make_task("1", "https://example.com/article")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        orchestrator._fetcher.fetch = AsyncMock(
            return_value=MagicMock(url="https://example.com/article")
        )
        orchestrator._summarizer.summarize = AsyncMock(
            side_effect=RuntimeError("Gemini API error")
        )
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        assert result.articles_processed == 0
        assert result.articles_failed == 1
        assert result.skipped is True


class TestOrchestratorFailureComments:
    """Tests that failure comments are added and previously failed tasks are skipped."""

    @pytest.fixture
    def orchestrator(self) -> Orchestrator:
        todoist = MagicMock()
        todoist.get_tasks = AsyncMock(return_value=[])
        todoist.get_comments = AsyncMock(return_value=[])
        todoist.add_comment = AsyncMock()
        fetcher = MagicMock()
        gemini = MagicMock()
        gmail = MagicMock()
        return Orchestrator(
            todoist_client=todoist,
            article_fetcher=fetcher,
            gemini_client=gemini,
            gmail_client=gmail,
            recipient_email="test@example.com",
            todoist_project_id="project-1",
            podcast_enabled=False,
        )

    async def test_previously_failed_tasks_are_skipped(
        self, orchestrator: Orchestrator
    ) -> None:
        """Tasks with an existing 'tldrist:' comment should be filtered out."""
        tasks = [
            _make_task("1", "https://example.com/good"),
            _make_task("2", "https://example.com/bad"),
        ]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        # Task 2 has a failure comment from a previous run
        async def mock_get_comments(task_id: str) -> list[dict]:
            if task_id == "2":
                return [{"content": "tldrist: HTTP 403"}]
            return []

        orchestrator._todoist.get_comments = AsyncMock(side_effect=mock_get_comments)

        orchestrator._fetcher.fetch = AsyncMock(
            return_value=MagicMock(url="https://example.com/good", content="c", word_count=100)
        )
        orchestrator._summarizer.summarize = AsyncMock(
            side_effect=lambda tid, art: _make_processed(tid, art.url)
        )
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        # Only task 1 should be processed
        assert result.tasks_found == 1
        assert result.articles_processed == 1
        assert result.articles_failed == 0

    async def test_all_tasks_previously_failed_skips_workflow(
        self, orchestrator: Orchestrator
    ) -> None:
        """When all tasks have failure comments, workflow should skip (no email)."""
        tasks = [
            _make_task("1", "https://example.com/a"),
            _make_task("2", "https://example.com/b"),
        ]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)
        orchestrator._todoist.get_comments = AsyncMock(
            return_value=[{"content": "tldrist: content extraction failed"}]
        )
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=False)

        assert result.tasks_found == 0
        assert result.skipped is True
        assert result.email_sent is False
        orchestrator._digest.compose_digest.assert_not_called()

    async def test_failure_comment_added_on_fetch_failure(
        self, orchestrator: Orchestrator
    ) -> None:
        """When an article fails, a comment should be added to the Todoist task."""
        tasks = [_make_task("1", "https://example.com/fail")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        async def mock_fetch(url: str):
            raise FetchError("HTTP 403")

        orchestrator._fetcher.fetch = mock_fetch
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        await orchestrator.run(dry_run=False)

        orchestrator._todoist.add_comment.assert_called_once_with(
            "1", "tldrist: HTTP 403"
        )

    async def test_failure_comment_not_added_in_dry_run(
        self, orchestrator: Orchestrator
    ) -> None:
        """Failure comments should NOT be added during dry runs."""
        tasks = [_make_task("1", "https://example.com/fail")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)

        async def mock_fetch(url: str):
            raise FetchError("HTTP 403")

        orchestrator._fetcher.fetch = mock_fetch
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        await orchestrator.run(dry_run=True)

        orchestrator._todoist.add_comment.assert_not_called()

    async def test_comment_check_failure_does_not_skip_task(
        self, orchestrator: Orchestrator
    ) -> None:
        """If fetching comments fails, the task should still be processed."""
        tasks = [_make_task("1", "https://example.com/article")]
        orchestrator._todoist.get_tasks = AsyncMock(return_value=tasks)
        orchestrator._todoist.get_comments = AsyncMock(
            side_effect=RuntimeError("API error")
        )

        orchestrator._fetcher.fetch = AsyncMock(
            return_value=MagicMock(url="https://example.com/article", content="c", word_count=100)
        )
        orchestrator._summarizer.summarize = AsyncMock(
            side_effect=lambda tid, art: _make_processed(tid, art.url)
        )
        orchestrator._digest.compose_digest = AsyncMock(return_value=("subject", "<html>"))

        result = await orchestrator.run(dry_run=True)

        assert result.articles_processed == 1
