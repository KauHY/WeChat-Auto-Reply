from __future__ import annotations

from typing import Callable

from wechat_rule_assistant.domain.models import ClientStatus, InboundEvent, SendAttemptResult


class MockAdapter:
    """Offline adapter. Sending is recorded locally and never touches WeChat."""

    def __init__(self, verified_targets: set[str] | None = None) -> None:
        self._callback: Callable[[InboundEvent], None] | None = None
        self._listening = False
        self.verified_targets = verified_targets or {"xiao-chen"}
        self.sent: list[tuple[str, str]] = []

    def get_status(self) -> ClientStatus:
        return ClientStatus(True, True, "offline-simulator", "mock", "offline simulator; no WeChat access")

    def list_candidate_conversations(self) -> list[dict[str, str]]:
        return [
            {"id": "family-group", "kind": "group", "display_name": "相亲相爱一家人"},
            {"id": "xiao-chen", "kind": "friend", "display_name": "小陈"},
        ]

    def start_listening(self, binding_ids: list[str], on_event: Callable[[InboundEvent], None]) -> None:
        self._callback = on_event
        self._listening = True

    def stop_listening(self) -> None:
        self._listening = False
        self._callback = None

    def emit(self, event: InboundEvent) -> None:
        if self._listening and self._callback:
            self._callback(event)

    def verify_target(self, target_binding_id: str) -> bool:
        return target_binding_id in self.verified_targets

    def send_text(self, target_binding_id: str, text: str) -> SendAttemptResult:
        if not self.verify_target(target_binding_id):
            return SendAttemptResult("blocked", "target is not user-verified")
        self.sent.append((target_binding_id, text))
        return SendAttemptResult("sent_ui", "offline simulation recorded; no real message was sent")
