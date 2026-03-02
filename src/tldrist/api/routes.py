"""API routes for TLDRist."""

from fastapi import APIRouter, Depends, Query

from tldrist import __version__
from tldrist.api.auth import verify_oidc_token
from tldrist.api.models import HealthResponse, SummarizeResponse
from tldrist.clients.article import ArticleFetcher
from tldrist.clients.gemini import GeminiClient
from tldrist.clients.gmail import GmailClient
from tldrist.clients.storage import ImageStorage
from tldrist.clients.todoist import TodoistClient
from tldrist.clients.tts import TTSClient
from tldrist.config import get_settings
from tldrist.services.orchestrator import Orchestrator
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api"])


def _determine_status(
    tasks_found: int,
    articles_processed: int,
    articles_failed: int,
    tasks_update_failed: int,
    skipped: bool,
) -> str:
    """Determine the response status based on processing results."""
    if skipped:
        return "skipped"
    if articles_processed == 0 and tasks_found > 0:
        return "failed"
    if articles_failed > 0 or tasks_update_failed > 0:
        return "partial_success"
    return "success"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version=__version__)


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    dependencies=[Depends(verify_oidc_token)],
)
async def summarize(
    dry_run: bool = Query(default=False, description="Run without sending email"),
    min: int | None = Query(default=None, description="Minimum articles required"),
    max: int | None = Query(default=None, description="Maximum articles to process"),
) -> SummarizeResponse:
    """Run the article summarization workflow.

    This endpoint:
    1. Fetches tasks from the Todoist "Read" project
    2. Extracts article content from task URLs
    3. Generates AI summaries using Gemini
    4. Sends a digest email
    5. Updates Todoist tasks with summaries

    Args:
        dry_run: If True, performs all steps except sending email and updating tasks.
        min: Minimum number of articles required to proceed. If there are fewer articles,
            no email is sent and the response status is "skipped".
        max: Maximum number of articles to process. If None, process all.

    Returns:
        SummarizeResponse with statistics about the run.
    """
    logger.info("Summarize endpoint called", dry_run=dry_run, min=min, max=max)

    settings = get_settings()

    async with TodoistClient(settings.todoist_token) as todoist:
        async with ArticleFetcher() as fetcher:
            async with GeminiClient(
                project_id=settings.gcp_project_id,
                region=settings.gcp_region,
            ) as gemini:
                async with GmailClient(
                    gmail_address=settings.gmail_address,
                    app_password=settings.gmail_app_password,
                ) as gmail:
                    # Create ImageStorage and TTSClient if bucket is configured
                    image_storage = None
                    tts_client = None
                    if settings.gcs_images_bucket:
                        image_storage = ImageStorage(settings.gcs_images_bucket)
                        tts_client = TTSClient(project_id=settings.gcp_project_id)

                    orchestrator = Orchestrator(
                        todoist_client=todoist,
                        article_fetcher=fetcher,
                        gemini_client=gemini,
                        gmail_client=gmail,
                        recipient_email=settings.recipient_email,
                        todoist_project_id=settings.todoist_project_id,
                        image_storage=image_storage,
                        tts_client=tts_client,
                    )

                    result = await orchestrator.run(
                        dry_run=dry_run or settings.dry_run,
                        min=min,
                        max=max,
                    )

    status = _determine_status(
        result.tasks_found,
        result.articles_processed,
        result.articles_failed,
        result.tasks_update_failed,
        result.skipped,
    )

    return SummarizeResponse(
        status=status,
        tasks_found=result.tasks_found,
        articles_processed=result.articles_processed,
        articles_failed=result.articles_failed,
        tasks_updated=result.tasks_updated,
        tasks_update_failed=result.tasks_update_failed,
        tasks_closed=result.tasks_closed,
        tasks_close_failed=result.tasks_close_failed,
        email_sent=result.email_sent,
        dry_run=result.dry_run,
        skipped=result.skipped,
        podcast_url=result.podcast_url,
    )
