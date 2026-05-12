"""Conversation session and message domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Message:
    """A single turn in a conversation.

    Attributes:
        role: Either ``"user"`` or ``"assistant"``.
        content: Text content of the message.
        timestamp: When the message was recorded.
    """

    role: str
    content: str
    timestamp: datetime | None = None


@dataclass
class Session:
    """Mutable aggregate representing an ongoing conversation session.

    Attributes:
        id: Unique session identifier.
        messages: Ordered list of user/assistant turns.
        summary: LLM-generated compression of earlier turns for
            long-context management.
        created_at: Session creation timestamp.
        updated_at: Last-turn timestamp.
    """

    id: str
    messages: list[Message] = field(default_factory=list)
    summary: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ConversationSummary:
    """Immutable summary of a conversation segment for memory compaction."""

    summary: str
    """Compressed text representing the gist of the segment."""

    turn_count: int
    """Number of turns this summary covers."""

    key_entities: list[str] = field(default_factory=list)
    """Notable named entities mentioned (people, topics, document refs)."""
