"""Read-only prerequisite report; never opens, logs in to, or controls WeChat."""
from __future__ import annotations

import importlib.util
import platform
import sys


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Windows: {platform.platform()}")
    supported = (3, 11) <= sys.version_info[:2] < (3, 14)
    print(f"Python for planned wxauto adapters: {'PASS' if supported else 'BLOCKED (requires 3.11–3.13)'}")
    for package in ("PySide6", "wxauto4", "wxautox4", "pywinauto"):
        print(f"{package}: {'installed' if importlib.util.find_spec(package) else 'not installed'}")
    try:
        import ctypes
        found = bool(ctypes.windll.user32.FindWindowW(None, "WeChat")) or bool(ctypes.windll.user32.FindWindowW(None, "微信"))
    except Exception:
        found = False
    print(f"Visible WeChat main window: {'detected' if found else 'not detected'}")
    print("Result: real-client adapter remains disabled until every prerequisite and manual binding check passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
