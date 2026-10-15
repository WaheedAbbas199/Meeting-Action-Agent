"""Provider abstractions and shared exceptions."""

from dataclasses import dataclass, field


class ProviderError(Exception):
    """Permanent failure: do not retry."""


class TransientProviderError(ProviderError):
    """Temporary failure (timeout, 429, 5xx): retry with backoff, bounded."""


class ProviderNotConfigured(ProviderError):
    pass


@dataclass
class ExtractedTask:
    title: str
    owner: str = ""
    due_text: str = ""
    priority: str = "medium"
    evidence_quote: str = ""
    confidence: float = 0.6
    depends_on_titles: list[str] = field(default_factory=list)
    blocker: str = ""


@dataclass
class ExtractedDecision:
    text: str
    topic: str = ""
    evidence_quote: str = ""
    confidence: float = 0.6
    kind: str = "decision"  # decision | question


@dataclass
class ExtractionResult:
    summary: str = ""
    tasks: list[ExtractedTask] = field(default_factory=list)
    decisions: list[ExtractedDecision] = field(default_factory=list)


@dataclass
class SendResult:
    message_id: str
    status: str = "accepted"  # provider acknowledgement, not delivery proof
