from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

Mode = Literal["ALL", "ANY"]
DispatchMode = Literal["dry_run", "notify_confirm", "auto"]
JobStatus = Literal["awaiting_approval", "approved", "cancelled", "sent_ui", "failed", "blocked", "uncertain"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class InboundEvent:
    source_kind: str
    source_binding_id: str
    sender_binding_id: str | None
    sender_display_name: str
    direction: str
    message_type: str
    content: str
    is_after_startup_baseline: bool
    sender_identity_verified: bool
    observed_at: datetime = field(default_factory=utc_now)
    adapter_event_key: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class MatchRule:
    id: str
    name: str
    enabled: bool
    source_binding_id: str
    sender_binding_id: str
    target_binding_id: str
    keywords: tuple[str, ...]
    reply_text: str
    keyword_mode: Mode = "ALL"
    exclude_keywords: tuple[str, ...] = ()
    case_sensitive: bool = False
    mode: DispatchMode = "notify_confirm"
    cooldown_sec: int = 60
    event_ttl_sec: int = 120
    max_actions_per_day: int = 3
    priority: int = 100


@dataclass(frozen=True)
class ActionJob:
    id: str
    rule_id: str
    event_id: str
    target_binding_id: str
    reply_text: str
    status: JobStatus
    created_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return utc_now() >= self.expires_at


@dataclass(frozen=True)
class ClientStatus:
    connected: bool
    logged_in: bool
    client_version: str | None
    adapter_name: str
    reason: str | None = None


@dataclass(frozen=True)
class SendAttemptResult:
    status: Literal["sent_ui", "uncertain", "failed", "blocked"]
    details: str


def expires_in(seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=seconds)
