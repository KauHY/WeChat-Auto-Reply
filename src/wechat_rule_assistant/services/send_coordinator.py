from __future__ import annotations

from wechat_rule_assistant.adapters.base import WeChatAdapter
from wechat_rule_assistant.domain.models import SendAttemptResult
from wechat_rule_assistant.storage.database import Database


class SendCoordinator:
    """Explicit approval and target validation gate for all write actions."""
    def __init__(self, database: Database, adapter: WeChatAdapter) -> None:
        self.database, self.adapter = database, adapter

    def approve(self, job_id: str) -> bool:
        job = self.database.get_job(job_id)
        if not job or job.status != "awaiting_approval" or job.expired:
            if job and job.expired:
                self.database.set_job_status(job.id, "cancelled", "expired")
            return False
        self.database.set_job_status(job_id, "approved")
        return True

    def execute_approved(self, job_id: str) -> SendAttemptResult:
        job = self.database.get_job(job_id)
        if not job or job.status != "approved":
            return SendAttemptResult("blocked", "job is not approved")
        if job.expired:
            self.database.set_job_status(job.id, "cancelled", "expired")
            return SendAttemptResult("blocked", "job expired")
        status = self.adapter.get_status()
        if not status.logged_in:
            self.database.set_job_status(job.id, "blocked", "wechat_not_logged_in")
            return SendAttemptResult("blocked", "client is not logged in")
        target_verified = self.adapter.verify_target(job.target_binding_id)
        if not target_verified:
            self.database.set_job_status(job.id, "blocked", "target_not_verified")
            self.database.add_attempt(job.id, False, "blocked", "target not verified")
            return SendAttemptResult("blocked", "target is not verified")
        result = self.adapter.send_text(job.target_binding_id, job.reply_text)
        self.database.add_attempt(job.id, True, result.status, result.details)
        self.database.set_job_status(job.id, result.status, result.details if result.status != "sent_ui" else None)
        return result
