"""Google Cloud Text-to-Speech client for podcast generation."""

import io
import re
from dataclasses import dataclass

from google.cloud import texttospeech

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VoiceConfig:
    """Configuration for a TTS voice."""

    name: str
    language_code: str


# Two distinct Neural2 voices for the podcast hosts
VOICE_ALEX = VoiceConfig(name="en-US-Neural2-D", language_code="en-US")  # Male
VOICE_SAM = VoiceConfig(name="en-US-Neural2-F", language_code="en-US")  # Female


class TTSClient:
    """Client for Google Cloud Text-to-Speech API."""

    def __init__(self, project_id: str) -> None:
        """Initialize the TTS client.

        Args:
            project_id: The GCP project ID to use for TTS API calls.
        """
        from google.api_core import client_options

        # Configure client to use specific project for quota/billing
        options = client_options.ClientOptions(quota_project_id=project_id)
        self._client = texttospeech.TextToSpeechClient(client_options=options)
        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
        )

    def synthesize_speech(self, text: str, voice: VoiceConfig) -> bytes:
        """Synthesize speech for a single text segment.

        Args:
            text: The text to synthesize.
            voice: The voice configuration to use.

        Returns:
            MP3 audio bytes.
        """
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=voice.language_code,
            name=voice.name,
        )

        response = self._client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=self._audio_config,
        )

        return response.audio_content

    def synthesize_conversation(self, script: str) -> bytes:
        """Synthesize a conversation script with multiple speakers.

        The script should contain speaker tags like [ALEX]: and [SAM]:.
        Each tagged section will be synthesized with the appropriate voice.

        Args:
            script: The conversation script with speaker tags.

        Returns:
            Combined MP3 audio bytes.
        """
        # Import pydub here to handle audio concatenation
        from pydub import AudioSegment

        # Parse script into segments with speaker tags
        segments = self._parse_script(script)

        if not segments:
            logger.warning("No segments found in script")
            return b""

        logger.info("Synthesizing conversation", segment_count=len(segments))

        # Synthesize each segment and combine
        combined_audio = AudioSegment.empty()

        for speaker, text in segments:
            voice = VOICE_ALEX if speaker == "ALEX" else VOICE_SAM
            audio_bytes = self.synthesize_speech(text, voice)

            # Convert MP3 bytes to AudioSegment
            segment_audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            combined_audio += segment_audio

            logger.debug(
                "Synthesized segment",
                speaker=speaker,
                text_length=len(text),
                audio_duration_ms=len(segment_audio),
            )

        # Export combined audio as MP3
        output_buffer = io.BytesIO()
        combined_audio.export(output_buffer, format="mp3")
        output_buffer.seek(0)

        logger.info(
            "Conversation synthesis complete",
            total_duration_ms=len(combined_audio),
            segment_count=len(segments),
        )

        return output_buffer.read()

    def _parse_script(self, script: str) -> list[tuple[str, str]]:
        """Parse a conversation script into speaker/text segments.

        Args:
            script: Script with [ALEX]: and [SAM]: tags.

        Returns:
            List of (speaker, text) tuples.
        """
        # Match [ALEX]: or [SAM]: followed by text until the next tag or end
        pattern = r"\[(ALEX|SAM)\]:\s*"
        parts = re.split(pattern, script)

        segments: list[tuple[str, str]] = []

        # parts will be: ['intro text', 'ALEX', 'alex text', 'SAM', 'sam text', ...]
        # Skip parts[0] which is text before the first speaker tag
        i = 1

        # Process pairs of (speaker, text)
        while i < len(parts) - 1:
            speaker = parts[i].strip()
            if speaker in ("ALEX", "SAM"):
                text = parts[i + 1].strip()
                if text:
                    segments.append((speaker, text))
                i += 2
            else:
                i += 1

        return segments
