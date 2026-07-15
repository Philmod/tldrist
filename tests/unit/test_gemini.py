"""Unit tests for GeminiClient."""

from tldrist.clients.gemini import GeminiClient


class TestGeminiClientDefaults:
    """Pins the default model/location so a retired model can't silently return."""

    def test_default_model_and_location(self) -> None:
        client = GeminiClient(project_id="test-project")

        # gemini-2.0-flash-001 was shut down 2026-06-01; gemini-3.5-flash is GA
        # and is served from the global endpoint (not europe-west1).
        assert client._model_name == "gemini-3.5-flash"
        assert client._region == "global"
