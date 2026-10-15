"""Email / WhatsApp / calendar providers.

Real providers (Gmail API, WhatsApp Cloud API) are implemented against the official APIs but are
UNVERIFIED in this repository because they need live credentials. They are blocked in APP_ENV=test.
Mock providers record calls so tests can assert on them without any external traffic.
"""

import base64
import hashlib
import hmac
from email.message import EmailMessage

import httpx

from app.config import get_settings
from app.providers.base import ProviderError, ProviderNotConfigured, SendResult, TransientProviderError


class MockChannel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[dict] = []
        self.failures: list[Exception] = []  # popped one per call (failure injection for tests)
        self._seen: dict[str, str] = {}

    def reset(self) -> None:
        self.sent.clear()
        self.failures.clear()
        self._seen.clear()

    def send(self, to: str, body: str, subject: str = "", idempotency_key: str = "") -> SendResult:
        if self.failures:
            raise self.failures.pop(0)
        if idempotency_key and idempotency_key in self._seen:  # provider-side dedupe
            return SendResult(message_id=self._seen[idempotency_key])
        mid = f"mock-{self.name}-{len(self.sent) + 1}"
        self.sent.append({"to": to, "subject": subject, "body": body, "key": idempotency_key, "id": mid})
        if idempotency_key:
            self._seen[idempotency_key] = mid
        return SendResult(message_id=mid)


MOCKS = {"email": MockChannel("email"), "whatsapp": MockChannel("whatsapp"), "calendar": MockChannel("calendar")}


def _raise_for(r: httpx.Response, what: str) -> None:
    if r.status_code in (429, 500, 502, 503, 504):
        raise TransientProviderError(f"{what} temporary error {r.status_code}")
    if r.status_code >= 400:
        raise ProviderError(f"{what} rejected the request ({r.status_code})")


class GmailEmail:
    name = "gmail"

    def __init__(self) -> None:
        s = get_settings()
        if not all([s.gmail_client_id, s.gmail_client_secret, s.gmail_refresh_token, s.gmail_sender]):
            raise ProviderNotConfigured("Gmail credentials are incomplete")
        self.s = s

    def _token(self) -> str:
        try:
            r = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.s.gmail_client_id,
                    "client_secret": self.s.gmail_client_secret,
                    "refresh_token": self.s.gmail_refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise TransientProviderError("Gmail token request failed") from e
        _raise_for(r, "Gmail auth")
        return r.json()["access_token"]

    def send(self, to: str, body: str, subject: str = "", idempotency_key: str = "") -> SendResult:
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = to, self.s.gmail_sender, subject
        msg["X-Idempotency-Key"] = idempotency_key
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            r = httpx.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                json={"raw": raw},
                headers={"Authorization": f"Bearer {self._token()}"},
                timeout=30,
            )
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise TransientProviderError("Gmail send failed") from e
        _raise_for(r, "Gmail")
        return SendResult(message_id=r.json().get("id", ""))


class WhatsAppCloud:
    name = "cloud"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.whatsapp_token and s.whatsapp_phone_number_id):
            raise ProviderNotConfigured("WhatsApp Cloud API credentials are incomplete")
        self.s = s

    def send(self, to: str, body: str, subject: str = "", idempotency_key: str = "") -> SendResult:
        to = to.lstrip("+")
        if self.s.whatsapp_template_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": self.s.whatsapp_template_name,
                    "language": {"code": self.s.whatsapp_template_lang},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": body[:900]}]}],
                },
            }
        else:  # only valid inside the 24h customer-service window
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4000]}}
        try:
            r = httpx.post(
                f"https://graph.facebook.com/v20.0/{self.s.whatsapp_phone_number_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {self.s.whatsapp_token}"},
                timeout=30,
            )
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise TransientProviderError("WhatsApp send failed") from e
        _raise_for(r, "WhatsApp")
        return SendResult(message_id=r.json().get("messages", [{}])[0].get("id", ""))


def verify_whatsapp_signature(raw_body: bytes, header: str | None, secret: str) -> bool:
    """Validate X-Hub-Signature-256 using constant-time comparison."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def _resolve(kind: str, configured: str, real: dict):
    s = get_settings()
    if configured == "disabled":
        raise ProviderNotConfigured(f"{kind.title()} sending is disabled. Configure a provider to enable it")
    if configured == "mock":
        if s.is_production:
            raise ProviderError("Mock providers are not allowed in production")
        return MOCKS[kind]
    if s.is_test:
        raise ProviderError("Real external sends are blocked in test mode")
    if configured in real:
        return real[configured]()
    raise ProviderNotConfigured(f"Unknown {kind} provider '{configured}'")


def get_channel(channel: str):
    s = get_settings()
    if channel == "email":
        return _resolve("email", s.email_provider, {"gmail": GmailEmail})
    if channel == "whatsapp":
        return _resolve("whatsapp", s.whatsapp_provider, {"cloud": WhatsAppCloud})
    if channel == "calendar":
        return _resolve("calendar", s.calendar_provider, {})
    raise ProviderError(f"Unknown channel {channel}")


def channel_status(channel: str) -> dict:
    """Health summary safe to show in the UI (never includes secrets)."""
    s = get_settings()
    cfg = {"email": s.email_provider, "whatsapp": s.whatsapp_provider, "calendar": s.calendar_provider}[channel]
    try:
        get_channel(channel)
        return {"provider": cfg, "ready": True, "message": "Ready" if cfg != "mock" else "Test mode (no real messages are sent)"}
    except ProviderError as e:
        return {"provider": cfg, "ready": False, "message": str(e)}
