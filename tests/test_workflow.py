import unittest
from pathlib import Path

from wechat_rule_assistant.adapters.mock_adapter import MockAdapter
from wechat_rule_assistant.app import sample_rule
from wechat_rule_assistant.domain.models import InboundEvent
from wechat_rule_assistant.services.monitor_service import MonitorService
from wechat_rule_assistant.services.send_coordinator import SendCoordinator
from wechat_rule_assistant.storage.database import Database


class WorkflowTests(unittest.TestCase):
    def test_requires_explicit_approval_before_mock_send(self):
        path = Path(".test-workflow.db")
        path.unlink(missing_ok=True)
        db = Database(path)
        try:
                db.save_rule(sample_rule())
                event = InboundEvent("group", "family-group", "li-ge", "李哥", "incoming", "text", "会展中心活动报名", True, True, adapter_event_key="one")
                jobs = MonitorService(db).handle_event(event)
                self.assertEqual(len(jobs), 1)
                adapter = MockAdapter()
                coordinator = SendCoordinator(db, adapter)
                self.assertEqual(adapter.sent, [])
                self.assertTrue(coordinator.approve(jobs[0].id))
                result = coordinator.execute_approved(jobs[0].id)
                self.assertEqual(result.status, "sent_ui")
                self.assertEqual(adapter.sent, [("xiao-chen", "会展中心活动报名")])
                self.assertEqual(db.get_job(jobs[0].id).status, "sent_ui")
        finally:
            db.close()
            path.unlink(missing_ok=True)

    def test_one_event_can_create_jobs_for_multiple_matching_rules(self):
        path = Path(".test-workflow.db")
        path.unlink(missing_ok=True)
        db = Database(path)
        try:
            first = sample_rule()
            second = first.__class__(**{**first.__dict__, "id": "second", "name": "第二条规则", "target_binding_id": "xiao-chen"})
            db.save_rule(first)
            db.save_rule(second)
            event = InboundEvent("group", "family-group", "li-ge", "李哥", "incoming", "text", "会展中心活动报名", True, True, adapter_event_key="shared-event")
            self.assertEqual(len(MonitorService(db).handle_event(event)), 2)
            self.assertEqual(len(MonitorService(db).handle_event(event)), 0)
        finally:
            db.close()
            path.unlink(missing_ok=True)
