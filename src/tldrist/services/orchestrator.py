"""Main workflow orchestrator for TLDRist."""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tldrist.clients.article import ArticleFetcher, is_arxiv_url
from tldrist.clients.gemini import GeminiClient
from tldrist.clients.gmail import GmailClient
from tldrist.clients.storage import ImageStorage
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
    """Orchestrates the complete TL;DRist workflow."""

    def __init__(
        self,
        todoist_client: TodoistClient,
        article_fetcher: ArticleFetcher,
        gemini_client: GeminiClient,
        gmail_client: GmailClient,
        recipient_email: str,
        todoist_project_id: str,
        image_storage: ImageStorage | None = None,
    ) -> None:
        self._todoist = todoist_client
        self._fetcher = article_fetcher
        self._gemini = gemini_client
        self._gmail = gmail_client
        self._recipient_email = recipient_email
        self._project_id = todoist_project_id

        self._summarizer = SummarizerService(gemini_client)
        self._digest = DigestService(gemini_client, image_storage)

    async def run(self, dry_run: bool = False, limit: int | None = None) -> OrchestrationResult:
        """Run the complete workflow.

        Args:
            dry_run: If True, skip sending email and updating Todoist tasks.
            limit: Maximum number of articles to process. If None, process all.

        Returns:
            OrchestrationResult with statistics about the run.
        """
        logger.info("Starting orchestration", dry_run=dry_run, limit=limit, project_id=self._project_id)

        # Get tasks with URLs from the configured project
        tasks = await self._todoist.get_tasks(self._project_id)
        tasks_with_urls = [t for t in tasks if t.url is not None]
        logger.info("Found tasks with URLs", count=len(tasks_with_urls))

        # Apply limit if specified
        if limit is not None:
            tasks_with_urls = tasks_with_urls[:limit]
            logger.info("Applied limit", limit=limit, tasks_to_process=len(tasks_with_urls))

        if not tasks_with_urls:
            logger.info("No tasks with URLs found, sending empty digest")
            subject, html = await self._digest.compose_digest([])
            if not dry_run:
                self._gmail.send_email(self._recipient_email, subject, html)
            else:
                logger.info("Dry run - generated email subject", subject=subject)
                html_path = self._write_dry_run_html(html)
                logger.info("Dry run - HTML written to file", path=str(html_path))
                print(f"Dry run HTML saved to: {html_path}")
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
            logger.info("Dry run - generated email subject", subject=subject)
            html_path = self._write_dry_run_html(html)
            logger.info("Dry run - HTML written to file", path=str(html_path))
            print(f"Dry run HTML saved to: {html_path}")

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

        # Route arXiv URLs to specialized processing
        if is_arxiv_url(task.url):
            return await self._process_arxiv_task(task)

        article = await self._fetcher.fetch(task.url)
        if article is None:
            logger.warning("Failed to fetch article", task_id=task.id, url=task.url)
            return None

        return await self._summarizer.summarize(task.id, article)

    async def _process_arxiv_task(self, task: TodoistTask) -> ProcessedArticle | None:
        """Process an arXiv task by fetching PDF and summarizing with Gemini."""
        if task.url is None:
            return None

        logger.info("Processing arXiv task", task_id=task.id, url=task.url)

        arxiv_content = await self._fetcher.fetch_arxiv(task.url)
        if arxiv_content is None:
            logger.warning("Failed to fetch arXiv paper", task_id=task.id, url=task.url)
            return None

        return await self._summarizer.summarize_arxiv(task.id, arxiv_content)

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

    def _write_dry_run_html(self, html: str) -> Path:
        """Write HTML to a temporary file for dry run preview.

        Returns:
            Path to the generated HTML file.
        """
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            prefix="tldrist_digest_",
            delete=False,
        ) as f:
            f.write(html)
            return Path(f.name)
