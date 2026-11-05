import unittest

from wechat_rule_assistant.domain.models import InboundEvent, MatchRule
from wechat_rule_assistant.domain.rule_engine import evaluate


class RuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.rule = MatchRule("r", "报名", True, "group", "li", "chen", ("活动报名", "会展中心"), "报名", keyword_mode="ALL")
        self.event = InboundEvent("group", "group", "li", "李哥", "incoming", "text", "会展中心活动报名开始", True, True)

    def test_all_keywords_and_verified_sender_match(self):
        self.assertEqual(evaluate(self.event, self.rule), (True, "matched"))

    def test_other_sender_does_not_match(self):
        event = InboundEvent("group", "group", "other", "小王", "incoming", "text", "会展中心活动报名开始", True, True)
        self.assertEqual(evaluate(event, self.rule)[1], "wrong_sender")

    def test_old_message_does_not_match(self):
        event = InboundEvent("group", "group", "li", "李哥", "incoming", "text", "会展中心活动报名开始", False, True)
        self.assertEqual(evaluate(event, self.rule)[1], "historical_or_unverified_newness")

    def test_excluded_keyword_does_not_match(self):
        rule = MatchRule("r", "报名", True, "group", "li", "chen", ("活动报名",), "报名", exclude_keywords=("取消",))
        event = InboundEvent("group", "group", "li", "李哥", "incoming", "text", "活动报名取消", True, True)
        self.assertEqual(evaluate(event, rule)[1], "excluded_keyword")
