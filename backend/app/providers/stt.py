"""Speech-to-text provider abstraction."""

import base64

import httpx

from app.config import get_settings
from app.providers.base import ProviderError, ProviderNotConfigured, TransientProviderError

AUDIO_MIME = {".mp3": "audio/mp3", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac", ".aac": "audio/aac"}


class FakeSTT:
    """Test-only provider returning a canned transcript."""

    def transcribe(self, data: bytes, filename: str) -> str:
        return "[00:00:05] Alice: I'll prepare the budget report by Friday.\n[00:00:12] Bob: We decided to launch on 2026-11-01."


class GeminiSTT:
    def __init__(self) -> None:
        s = get_settings()
        if not s.gemini_api_key:
            raise ProviderNotConfigured("GEMINI_API_KEY is not set")
        self.key, self.model = s.gemini_api_key, s.gemini_model

    def transcribe(self, data: bytes, filename: str) -> str:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime = AUDIO_MIME.get(ext)
        if not mime:
            raise ProviderError("Unsupported audio format")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Transcribe this meeting. One line per utterance formatted as '[HH:MM:SS] Speaker: text'. Output the transcript only."
                        },
                        {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}},
                    ]
                }
            ]
        }
        try:
            r = httpx.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=180)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise TransientProviderError("Transcription request failed") from e
        if r.status_code in (429, 500, 502, 503, 504):
            raise TransientProviderError(f"Transcription temporary error {r.status_code}")
        if r.status_code >= 400:
            raise ProviderError(f"Transcription rejected ({r.status_code})")
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError("Unexpected transcription response") from e


def get_stt():
    s = get_settings()
    if s.stt_provider == "fake" and s.is_test:
        return FakeSTT()
    if s.is_test or s.stt_provider == "none":
        raise ProviderNotConfigured("No speech-to-text provider is configured. Paste a transcript or set STT_PROVIDER")
    if s.stt_provider == "gemini":
        return GeminiSTT()
    raise ProviderNotConfigured(f"Unknown STT_PROVIDER '{s.stt_provider}'")
