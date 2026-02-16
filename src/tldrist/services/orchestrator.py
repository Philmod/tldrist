"""Main workflow orchestrator for TLDRist."""

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tldrist.clients.article import ArticleFetcher, FetchError, is_arxiv_url
from tldrist.clients.gemini import ArticleSummary, GeminiClient
from tldrist.clients.gmail import GmailClient
from tldrist.clients.storage import ImageStorage
from tldrist.clients.todoist import TodoistClient, TodoistTask
from tldrist.clients.tts import TTSClient
from tldrist.models import FailedArticle
from tldrist.services.digest import DigestService
from tldrist.services.podcast import PodcastService
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
    tasks_closed: int
    tasks_close_failed: int
    email_sent: bool
    dry_run: bool
    skipped: bool = False
    podcast_url: str | None = None


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
        tts_client: TTSClient | None = None,
        podcast_enabled: bool = True,
    ) -> None:
        self._todoist = todoist_client
        self._fetcher = article_fetcher
        self._gemini = gemini_client
        self._gmail = gmail_client
        self._recipient_email = recipient_email
        self._project_id = todoist_project_id
        self._storage = image_storage
        self._tts_client = tts_client
        self._podcast_enabled = podcast_enabled

        self._summarizer = SummarizerService(gemini_client)
        self._digest = DigestService(gemini_client, image_storage)
        self._podcast = PodcastService(gemini_client) if podcast_enabled else None

    async def run(
        self,
        dry_run: bool = False,
        min: int | None = None,
        max: int | None = None,
    ) -> OrchestrationResult:
        """Run the complete workflow.

        Args:
            dry_run: If True, skip sending email and updating Todoist tasks.
            min: Minimum number of articles required to proceed. If there are fewer
                articles available, the workflow is skipped and no email is sent.
            max: Maximum number of articles to include in the digest. All articles
                are fetched and summarized; only the first `max` successes are kept.

        Returns:
            OrchestrationResult with statistics about the run.
        """
        logger.info(
            "Starting orchestration",
            dry_run=dry_run,
            min=min,
            max=max,
            project_id=self._project_id,
        )

        # Get tasks with URLs from the configured project
        tasks = await self._todoist.get_tasks(self._project_id)
        tasks_with_urls = [t for t in tasks if t.url is not None]
        logger.info("Found tasks with URLs", count=len(tasks_with_urls))

        # Check minimum threshold
        if min is not None and len(tasks_with_urls) < min:
            logger.info(
                "Skipping workflow: not enough articles",
                found=len(tasks_with_urls),
                min=min,
            )
            return OrchestrationResult(
                tasks_found=len(tasks_with_urls),
                articles_processed=0,
                articles_failed=0,
                tasks_updated=0,
                tasks_update_failed=0,
                tasks_closed=0,
                tasks_close_failed=0,
                email_sent=False,
                dry_run=dry_run,
                skipped=True,
            )

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
                tasks_closed=0,
                tasks_close_failed=0,
                email_sent=not dry_run,
                dry_run=dry_run,
            )

        # Process all articles concurrently
        processed_articles: list[ProcessedArticle] = []
        failed_articles: list[FailedArticle] = []

        results = await asyncio.gather(
            *[self._process_task(task) for task in tasks_with_urls],
            return_exceptions=True,
        )

        for task, result in zip(tasks_with_urls, results):
            if isinstance(result, BaseException):
                logger.error("Task processing failed", task_id=task.id, url=task.url, error=str(result))
                failed_articles.append(FailedArticle(url=task.url or "", reason=str(result)))
            elif isinstance(result, FailedArticle):
                failed_articles.append(result)
            elif isinstance(result, ProcessedArticle):
                processed_articles.append(result)

        # Apply max limit to successful results
        if max is not None:
            processed_articles = processed_articles[:max]

        logger.info(
            "Article processing complete",
            processed=len(processed_articles),
            failed=len(failed_articles),
        )

        # Generate podcast if enabled and we have articles
        podcast_url = None
        if (
            self._podcast_enabled
            and self._podcast
            and self._tts_client
            and self._storage
            and processed_articles
        ):
            try:
                podcast_url = await self._podcast.generate_podcast(
                    processed_articles, self._tts_client, self._storage
                )
                logger.info("Podcast generated", url=podcast_url)
            except Exception as e:
                logger.error("Failed to generate podcast", error=str(e))
                # Continue without podcast - don't fail the whole digest

        # Generate and upload web page version of the digest
        web_page_url = None
        if self._storage and processed_articles:
            try:
                # Generate intro for the web page
                summaries = [
                    ArticleSummary(url=a.url, title=a.title, summary=a.summary)
                    for a in processed_articles
                ]
                intro = await self._gemini.generate_digest_intro(summaries)

                # Render the web-friendly HTML
                web_html = self._digest.render_web_html(intro, processed_articles, podcast_url)

                # Upload to GCS
                date_str = datetime.now(UTC).strftime("%Y-%m-%d")
                web_page_url = self._storage.upload_html(web_html, date_str)
                logger.info("Web digest page uploaded", url=web_page_url)
            except Exception as e:
                logger.error("Failed to generate web page", error=str(e))
                # Continue without web page - don't fail the whole digest

        # Compose and send digest
        subject, html = await self._digest.compose_digest(
            processed_articles, podcast_url, web_page_url, failed_articles
        )

        tasks_updated = 0
        tasks_update_failed = 0
        tasks_closed = 0
        tasks_close_failed = 0

        if not dry_run:
            self._gmail.send_email(self._recipient_email, subject, html)
            logger.info("Digest email sent", recipient=self._recipient_email)

            # Update Todoist tasks with summaries and close them
            tasks_updated, tasks_update_failed, tasks_closed, tasks_close_failed = (
                await self._update_and_close_tasks(processed_articles)
            )
            logger.info(
                "Tasks updated and closed",
                updated=tasks_updated,
                update_failed=tasks_update_failed,
                closed=tasks_closed,
                close_failed=tasks_close_failed,
            )
        else:
            logger.info("Dry run - generated email subject", subject=subject)
            html_path = self._write_dry_run_html(html)
            logger.info("Dry run - HTML written to file", path=str(html_path))
            print(f"Dry run HTML saved to: {html_path}")

        return OrchestrationResult(
            tasks_found=len(tasks_with_urls),
            articles_processed=len(processed_articles),
            articles_failed=len(failed_articles),
            tasks_updated=tasks_updated,
            tasks_update_failed=tasks_update_failed,
            tasks_closed=tasks_closed,
            tasks_close_failed=tasks_close_failed,
            email_sent=not dry_run,
            dry_run=dry_run,
            podcast_url=podcast_url,
        )

    async def _process_task(
        self, task: TodoistTask
    ) -> ProcessedArticle | FailedArticle:
        """Process a single task by fetching and summarizing its article."""
        if task.url is None:
            return FailedArticle(url="", reason="no URL")

        logger.info("Processing task", task_id=task.id, url=task.url)

        # Route arXiv URLs to specialized processing
        if is_arxiv_url(task.url):
            return await self._process_arxiv_task(task)

        try:
            article = await self._fetcher.fetch(task.url)
        except FetchError as e:
            logger.warning("Failed to fetch article", task_id=task.id, url=task.url, reason=e.reason)
            return FailedArticle(url=task.url, reason=e.reason)

        try:
            return await self._summarizer.summarize(task.id, article)
        except Exception as e:
            logger.warning("Failed to summarize article", task_id=task.id, url=task.url, error=str(e))
            return FailedArticle(url=task.url, reason=f"summarization failed: {e}")

    async def _process_arxiv_task(
        self, task: TodoistTask
    ) -> ProcessedArticle | FailedArticle:
        """Process an arXiv task by fetching PDF and summarizing with Gemini."""
        if task.url is None:
            return FailedArticle(url="", reason="no URL")

        logger.info("Processing arXiv task", task_id=task.id, url=task.url)

        try:
            arxiv_content = await self._fetcher.fetch_arxiv(task.url)
        except FetchError as e:
            logger.warning("Failed to fetch arXiv paper", task_id=task.id, url=task.url, reason=e.reason)
            return FailedArticle(url=task.url, reason=e.reason)

        try:
            return await self._summarizer.summarize_arxiv(task.id, arxiv_content)
        except Exception as e:
            logger.warning("Failed to summarize arXiv paper", task_id=task.id, url=task.url, error=str(e))
            return FailedArticle(url=task.url, reason=f"summarization failed: {e}")

    async def _update_and_close_tasks(
        self, articles: list[ProcessedArticle]
    ) -> tuple[int, int, int, int]:
        """Update Todoist tasks with their summaries and close them.

        Returns:
            Tuple of (updated_count, update_failed_count, closed_count, close_failed_count).
        """
        updated = 0
        update_failed = 0
        closed = 0
        close_failed = 0

        for article in articles:
            # First update the task description
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
                update_failed += 1
                # Skip closing if update failed
                continue

            # Then close the task
            try:
                await self._todoist.close_task(article.task_id)
                closed += 1
            except Exception as e:
                logger.error(
                    "Failed to close task",
                    task_id=article.task_id,
                    error=str(e),
                )
                close_failed += 1

        return updated, update_failed, closed, close_failed

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
