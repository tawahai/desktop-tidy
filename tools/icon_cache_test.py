# -*- coding: utf-8 -*-
"""回归测试：文件被替换后，图标缓存要失效并重新取图标。

跑法（项目根目录）：python tools/icon_cache_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_winapi  # noqa: E402

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    print(("  [OK] " if ok else "  [!!] ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        failures += 1


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tidy_icon_cache_"))
    # 用 .ico（属于"按文件本身取图标"的那类，和 .lnk/.exe 一样）
    source = Path(__file__).resolve().parent.parent / "app.ico"
    target = tmp / "示例.ico"
    if source.exists():
        target.write_bytes(source.read_bytes())
    else:
        target.write_bytes(b"\x00\x00\x01\x00")

    dt_winapi.clear_icon_cache()
    dt_winapi.icon_png(target, 44)
    first = len(dt_winapi._ICON_CACHE)
    check("第一次取图标会写进缓存", first >= 1, f"缓存条目={first}")

    dt_winapi.icon_png(target, 44)
    check("同一个文件再取一次不新增缓存", len(dt_winapi._ICON_CACHE) == first)

    # 同名同路径，但内容变了（模拟"把快捷方式换成新的"）
    os.utime(target, (1_700_000_000, 1_700_000_000))
    dt_winapi.icon_png(target, 44)
    check("文件改动后会重新取图标（缓存失效）",
          len(dt_winapi._ICON_CACHE) == first + 1,
          f"缓存条目={len(dt_winapi._ICON_CACHE)}")

    print("-" * 40)
    print("全部通过" if not failures else f"有 {failures} 项未通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
