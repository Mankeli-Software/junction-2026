"""The Gemini Live side of a call: the client, the connect config and the session interface
the relay uses. Patterns from the #51 spike (spikes/gemini-live/).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from functools import cache
from typing import Any, Protocol

from google.genai import types

from app.settings import get_settings

IN_RATE = 16_000  # Live input: 16-bit little-endian mono PCM
OUT_RATE = 24_000  # Live output: the same at 24 kHz
IN_MIME = f"audio/pcm;rate={IN_RATE}"


class LiveSession(Protocol):
    """The part of `google.genai.live.AsyncSession` the relay uses (tests fake it)."""

    async def send_realtime_input(self, **kwargs: Any) -> None: ...

    async def send_tool_response(self, **kwargs: Any) -> None: ...

    def receive(self) -> AsyncIterator[types.LiveServerMessage]: ...


Connect = Callable[[str, types.LiveConnectConfig], AbstractAsyncContextManager[LiveSession]]


@cache
def _client(api_key: str) -> Any:
    from google import genai

    # v1beta: the 3.x Live models are not on the SDK's default v1 (#51).
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def connect(model: str, config: types.LiveConnectConfig) -> AbstractAsyncContextManager[Any]:
    """Opens a Gemini Live session (about 0.4 s in the spike)."""
    api_key = get_settings().gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return _client(api_key).aio.live.connect(model=model, config=config)


def connect_config(
    *,
    system_prompt: str,
    declarations: list[types.FunctionDeclaration],
    vocabulary: list[str],
    voice: str,
    silence_ms: int | None,
) -> types.LiveConnectConfig:
    """Audio out in the call voice, both transcriptions on, the caller's transcription with
    the catalogue vocabulary (#51: always send it), and the tools."""
    config: dict[str, Any] = {
        "response_modalities": [types.Modality.AUDIO],
        "system_instruction": system_prompt,
        "input_audio_transcription": types.AudioTranscriptionConfig(custom_vocabulary=vocabulary),
        "output_audio_transcription": types.AudioTranscriptionConfig(),
        "speech_config": types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        "tools": [types.Tool(function_declarations=declarations)],
    }
    if silence_ms is not None:
        config["realtime_input_config"] = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=silence_ms
            )
        )
    return types.LiveConnectConfig(**config)


def audio_blob(pcm: bytes) -> types.Blob:
    return types.Blob(data=pcm, mime_type=IN_MIME)


def is_rate_limit(error: BaseException) -> bool:
    text = f"{type(error).__name__} {error}"
    return "429" in text or "RESOURCE_EXHAUSTED" in text
