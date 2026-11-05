from __future__ import annotations

from wechat_rule_assistant.domain.models import ActionJob, InboundEvent
from wechat_rule_assistant.domain.rule_engine import evaluate
from wechat_rule_assistant.storage.database import Database


class MonitorService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def handle_event(self, event: InboundEvent) -> list[ActionJob]:
        evaluations = [(rule, *evaluate(event, rule)) for rule in self.database.list_rules()]
        return self.database.record_event_and_jobs(event, evaluations)
