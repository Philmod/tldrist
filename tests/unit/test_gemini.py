"""Unit tests for GeminiClient."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai.types import FinishReason, ThinkingLevel

from tldrist.clients.gemini import GeminiClient


@pytest.fixture
def client() -> GeminiClient:
    return GeminiClient(project_id="test-project")


@pytest.fixture
def settings() -> Iterator[None]:
    """Patch get_settings so tests don't read real environment config."""
    with patch(
        "tldrist.clients.gemini.get_settings",
        return_value=MagicMock(summary_paragraphs="2-4"),
    ):
        yield


def _mock_genai_client(text: str, finish_reason: FinishReason) -> MagicMock:
    """Build a fake google-genai client whose response has the given text
    and finish reason."""
    response = MagicMock()
    response.text = text
    response.candidates = [MagicMock(finish_reason=finish_reason)]
    genai_client = MagicMock()
    genai_client.aio.models.generate_content = AsyncMock(return_value=response)
    return genai_client


class TestGeminiClientDefaults:
    """Pins the default model/location so a retired model can't silently return."""

    def test_default_model_and_location(self, client: GeminiClient) -> None:
        # gemini-2.0-flash-001 was shut down 2026-06-01; gemini-3.5-flash is GA
        # and is served from the global endpoint (not europe-west1).
        assert client._model_name == "gemini-3.5-flash"
        assert client._region == "global"


class TestThinkingConfig:
    """Pins minimal thinking: thinking tokens share max_output_tokens, so
    default thinking would eat the cap and truncate summaries mid-sentence."""

    async def test_summarize_article_uses_minimal_thinking(
        self, client: GeminiClient, settings: None
    ) -> None:
        genai_client = _mock_genai_client("A summary.", FinishReason.STOP)

        with patch.object(client, "_get_client", return_value=genai_client):
            await client.summarize_article(title="Test", content="Body")

        config = genai_client.aio.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config.thinking_level == ThinkingLevel.MINIMAL
        assert config.max_output_tokens == 2048


class TestTruncatedResponses:
    """A response that hits max_output_tokens is cut mid-sentence and must
    fail instead of being emailed."""

    async def test_summarize_article_raises_on_max_tokens(
        self, client: GeminiClient, settings: None
    ) -> None:
        genai_client = _mock_genai_client(
            "Recent reports of enterprises", FinishReason.MAX_TOKENS
        )
        with patch.object(client, "_get_client", return_value=genai_client):
            with pytest.raises(RuntimeError, match="truncated"):
                await client.summarize_article(title="Test", content="Body")

    async def test_summarize_article_returns_complete_text(
        self, client: GeminiClient, settings: None
    ) -> None:
        genai_client = _mock_genai_client("A complete summary.", FinishReason.STOP)
        with patch.object(client, "_get_client", return_value=genai_client):
            result = await client.summarize_article(title="Test", content="Body")

        assert result == "A complete summary."

    async def test_summarize_pdf_raises_on_max_tokens(
        self, client: GeminiClient, settings: None
    ) -> None:
        genai_client = _mock_genai_client("Originating in", FinishReason.MAX_TOKENS)
        with patch.object(client, "_get_client", return_value=genai_client):
            with pytest.raises(RuntimeError, match="truncated"):
                await client.summarize_pdf(title="Test", pdf_bytes=b"%PDF")

    async def test_generate_content_raises_on_max_tokens(self, client: GeminiClient) -> None:
        genai_client = _mock_genai_client("partial script", FinishReason.MAX_TOKENS)
        with patch.object(client, "_get_client", return_value=genai_client):
            with pytest.raises(RuntimeError, match="truncated"):
                await client.generate_content("prompt")
