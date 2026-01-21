"""Main workflow orchestrator for TLDRist."""

import asyncio
from dataclasses import dataclass

from tldrist.clients.article import ArticleFetcher
from tldrist.clients.gemini import GeminiClient
from tldrist.clients.gmail import GmailClient
from tldrist.clients.todoist import TodoistClient, TodoistTask
from tldrist.services.digest import DigestService
from tldrist.services.summarizer import ProcessedArticle, SummarizerService
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OrchestrationResult:
    """Result of the orchestration workflow."""

    tasks_found: int
    articles_processed: int
    articles_failed: int
    tasks_updated: int
    tasks_update_failed: int
    email_sent: bool
    dry_run: bool


class Orchestrator:
    """Orchestrates the complete TLDRist workflow."""

    def __init__(
        self,
        todoist_client: TodoistClient,
        article_fetcher: ArticleFetcher,
        gemini_client: GeminiClient,
        gmail_client: GmailClient,
        recipient_email: str,
        todoist_project_id: str,
    ) -> None:
        self._todoist = todoist_client
        self._fetcher = article_fetcher
        self._gemini = gemini_client
        self._gmail = gmail_client
        self._recipient_email = recipient_email
        self._project_id = todoist_project_id

        self._summarizer = SummarizerService(gemini_client)
        self._digest = DigestService(gemini_client)

    async def run(self, dry_run: bool = False) -> OrchestrationResult:
        """Run the complete workflow.

        Args:
            dry_run: If True, skip sending email and updating Todoist tasks.

        Returns:
            OrchestrationResult with statistics about the run.
        """
        logger.info("Starting orchestration", dry_run=dry_run, project_id=self._project_id)

        # Get tasks with URLs from the configured project
        tasks = await self._todoist.get_tasks(self._project_id)
        tasks_with_urls = [t for t in tasks if t.url is not None]
        logger.info("Found tasks with URLs", count=len(tasks_with_urls))

        if not tasks_with_urls:
            logger.info("No tasks with URLs found, sending empty digest")
            subject, html = await self._digest.compose_digest([])
            if not dry_run:
                self._gmail.send_email(self._recipient_email, subject, html)
            return OrchestrationResult(
                tasks_found=0,
                articles_processed=0,
                articles_failed=0,
                tasks_updated=0,
                tasks_update_failed=0,
                email_sent=not dry_run,
                dry_run=dry_run,
            )

        # Process articles concurrently
        processed_articles: list[ProcessedArticle] = []
        failed_count = 0

        results = await asyncio.gather(
            *[self._process_task(task) for task in tasks_with_urls],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, BaseException):
                logger.error("Task processing failed", error=str(result))
                failed_count += 1
            elif result is None:
                failed_count += 1
            elif isinstance(result, ProcessedArticle):
                processed_articles.append(result)

        logger.info(
            "Article processing complete",
            processed=len(processed_articles),
            failed=failed_count,
        )

        # Compose and send digest
        subject, html = await self._digest.compose_digest(processed_articles)

        tasks_updated = 0
        tasks_update_failed = 0

        if not dry_run:
            self._gmail.send_email(self._recipient_email, subject, html)
            logger.info("Digest email sent", recipient=self._recipient_email)

            # Update Todoist tasks with summaries
            tasks_updated, tasks_update_failed = await self._update_tasks(processed_articles)
            logger.info(
                "Tasks updated",
                updated=tasks_updated,
                failed=tasks_update_failed,
            )
        else:
            logger.info("Dry run - skipping email and task updates")

        return OrchestrationResult(
            tasks_found=len(tasks_with_urls),
            articles_processed=len(processed_articles),
            articles_failed=failed_count,
            tasks_updated=tasks_updated,
            tasks_update_failed=tasks_update_failed,
            email_sent=not dry_run,
            dry_run=dry_run,
        )

    async def _process_task(self, task: TodoistTask) -> ProcessedArticle | None:
        """Process a single task by fetching and summarizing its article."""
        if task.url is None:
            return None

        logger.info("Processing task", task_id=task.id, url=task.url)

        article = await self._fetcher.fetch(task.url)
        if article is None:
            logger.warning("Failed to fetch article", task_id=task.id, url=task.url)
            return None

        return await self._summarizer.summarize(task.id, article)

    async def _update_tasks(self, articles: list[ProcessedArticle]) -> tuple[int, int]:
        """Update Todoist tasks with their summaries.

        Returns:
            Tuple of (updated_count, failed_count).
        """
        updated = 0
        failed = 0
        for article in articles:
            try:
                description = self._summarizer.format_task_description(article)
                await self._todoist.update_task_description(article.task_id, description)
                updated += 1
            except Exception as e:
                logger.error(
                    "Failed to update task",
                    task_id=article.task_id,
                    error=str(e),
                )
                failed += 1
        return updated, failed
