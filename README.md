# 微信定向消息助手（安全原型）

这是按 `docs/` 设计文档实现的本地 MVP。它默认只使用离线模拟器：可配置规则、模拟群消息、持久化去重并产生待确认任务；**不会读取或操作微信客户端，更不会默认发送消息**。

## 当前环境结论

- 当前检测到的 Python 是 3.14.7，而设计文档建议的 `wxauto4` 范围最高为 Python 3.12、`wxautox4` 为 Python 3.13。因此不能在当前解释器上承诺真实微信适配。
- 本次检查未发现运行中的微信进程，故真实微信 PoC 未通过，应用保持 Mock 模式。

## 运行

建议安装 Python 3.12（64 位）后：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m wechat_rule_assistant.app
```

没有 PySide6 时仍可运行完整离线演示：

```powershell
$env:PYTHONPATH = "src"
python -m wechat_rule_assistant.app --demo
python -m unittest discover -s tests -v
```

`--demo` 会生成本地 SQLite 数据库（默认位于 `%LOCALAPPDATA%\WeChatRuleAssistant\assistant.db`），并模拟“李哥”在“相亲相爱一家人”发送命中消息。仅当人工批准时，Mock 适配器才会记录一次模拟发送。

## 真实微信接入

真实客户端适配器故意未启用。先运行：

```powershell
python scripts/diagnostic.py
```

只有在 Python、微信版本、登录状态、目标群发言人和目标联系人均通过人工验证，且已取得适当授权时，才应实现并启用受限 UIA 适配器。不得添加 Hook、注入、数据库解密或自动绕过验证的实现。
