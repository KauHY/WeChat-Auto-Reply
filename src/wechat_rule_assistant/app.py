from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import uuid4

from wechat_rule_assistant.adapters.mock_adapter import MockAdapter
from wechat_rule_assistant.domain.models import InboundEvent, MatchRule
from wechat_rule_assistant.services.monitor_service import MonitorService
from wechat_rule_assistant.services.send_coordinator import SendCoordinator
from wechat_rule_assistant.storage.database import Database


def default_database_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local")) / "WeChatRuleAssistant"
    return root / "assistant.db"


def sample_rule() -> MatchRule:
    return MatchRule(
        id="event-signup-rule-001", name="会展中心活动报名", enabled=True,
        source_binding_id="family-group", sender_binding_id="li-ge", target_binding_id="xiao-chen",
        keywords=("活动报名", "会展中心"), reply_text="会展中心活动报名", keyword_mode="ALL",
        mode="notify_confirm", cooldown_sec=60, event_ttl_sec=120, max_actions_per_day=3,
    )


def run_demo(path: Path) -> int:
    database, adapter = Database(path), MockAdapter()
    try:
        database.save_rule(sample_rule())
        monitor, coordinator = MonitorService(database), SendCoordinator(database, adapter)
        adapter.start_listening(["family-group"], lambda event: [print(f"命中待确认任务：{job.id}") for job in monitor.handle_event(event)])
        adapter.emit(InboundEvent("group", "family-group", "li-ge", "李哥", "incoming", "text", "周日会展中心活动报名开始了", True, True, adapter_event_key=str(uuid4())))
        jobs = database.list_jobs(("awaiting_approval",))
        if not jobs:
            print("没有创建任务（可能受冷却或每日上限影响）。")
            return 1
        job = jobs[0]
        print(f"拟发送给已验证目标 {job.target_binding_id}：{job.reply_text}")
        print("离线演示默认不自动批准；使用图形界面或代码调用 approve 后才会模拟发送。")
        return 0
    finally:
        database.close()


def run_gui(path: Path) -> int:
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
    except ImportError:
        print("未安装 PySide6；请用 Python 3.11–3.13 安装依赖，或运行 --demo。")
        return 2
    database, adapter = Database(path), MockAdapter()
    database.save_rule(sample_rule())
    monitor, coordinator = MonitorService(database), SendCoordinator(database, adapter)
    application = QApplication([])
    window = QMainWindow()
    window.setWindowTitle("微信定向消息助手（离线安全模式）")
    layout, label = QVBoxLayout(), QLabel("当前为 MockAdapter：不读取、不操作微信。\n规则：相亲相爱一家人 → 李哥 → 活动报名 + 会展中心 → 小陈")
    layout.addWidget(label)
    simulate, approve = QPushButton("模拟李哥发送命中消息"), QPushButton("确认并模拟发送最近任务")
    layout.addWidget(simulate); layout.addWidget(approve)
    def on_simulate() -> None:
        jobs = monitor.handle_event(InboundEvent("group", "family-group", "li-ge", "李哥", "incoming", "text", "会展中心活动报名开始", True, True, adapter_event_key=str(uuid4())))
        label.setText("已创建待确认任务。" if jobs else "没有创建任务；请检查冷却/日限。")
    def on_approve() -> None:
        jobs = database.list_jobs(("awaiting_approval",))
        if not jobs:
            label.setText("没有待确认任务。")
            return
        if coordinator.approve(jobs[0].id):
            result = coordinator.execute_approved(jobs[0].id)
            label.setText(f"模拟发送结果：{result.status}（未向微信发送）")
    simulate.clicked.connect(on_simulate); approve.clicked.connect(on_approve)
    container = QWidget(); container.setLayout(layout); window.setCentralWidget(container); window.resize(640, 220); window.show()
    try:
        return application.exec()
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="微信定向消息助手：默认离线模拟，不接入微信。")
    parser.add_argument("--demo", action="store_true", help="运行离线规则与待确认任务演示")
    parser.add_argument("--db", type=Path, default=default_database_path(), help="本地 SQLite 路径")
    options = parser.parse_args()
    return run_demo(options.db) if options.demo else run_gui(options.db)


if __name__ == "__main__":
    raise SystemExit(main())
