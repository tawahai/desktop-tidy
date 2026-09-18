# -*- coding: utf-8 -*-
"""回归测试：拖放消息由「另一个线程」送进来时，程序不能崩。

真实场景里 WM_DROPFILES 是资源管理器用 SendMessage 从别的进程发来的，
此时 Tk 正卡在消息等待里。这里用另一个线程发同样的消息来复现这个状态。

跑法（项目根目录）：
    python tools/drop_thread_test.py              # 现在的实现，应当通过
    set DT_DROP_LEGACY=1 && python tools/drop_thread_test.py   # 旧实现，应当崩
"""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_config  # noqa: E402
import dt_winapi  # noqa: E402

WM_DROPFILES = 0x0233
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
LEGACY = os.environ.get("DT_DROP_LEGACY") == "1"


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def make_hdrop(paths):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    header = DROPFILES()
    header.pFiles = ctypes.sizeof(DROPFILES)
    header.fWide = True
    blob = b"".join(str(p).encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
    data = bytes(header) + blob
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return int(handle)


def build_config(tmp: Path) -> dict:
    root = tmp / "收纳盒"
    cfg = dt_config.default_config()
    cfg["root"] = str(root)
    cfg["icon_size"] = 44
    cfg["panel"] = {"x": 300, "y": 120, "w": 560, "h": 800, "view": "organize",
                    "alpha": 1.0, "topmost": True}
    cfg["boxes"] = []
    for index, name in enumerate(("文档", "图片", "程序")):
        (root / name).mkdir(parents=True, exist_ok=True)
        cfg["boxes"].append(dt_config.make_box(name, name, index))
    return cfg


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def main() -> int:
    dt_winapi.make_dpi_aware()
    tmp = Path(tempfile.mkdtemp(prefix="tidy_drop_thread_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    import main as app_main

    app = app_main.App(cfg)
    panel = app.panel

    if LEGACY:
        # 旧写法：窗口过程里直接排队到 Tcl 的 after
        def legacy_queue(paths):
            panel.after(0, lambda: panel._on_external_drop(paths))

        panel._queue_external_drop = legacy_queue
        print("模式：旧实现（窗口过程里调用 after）")
    else:
        print("模式：现在的实现（窗口过程只记列表，Tk 定时器取走）")

    pump(app, 1.4)
    hwnd = dt_winapi.hwnd_of(panel)
    print(f"面板窗口 hwnd=0x{hwnd:X}，钩子数={len(getattr(panel, '_drop_hooks', []))}")

    source = tmp / "桌面"
    source.mkdir(parents=True, exist_ok=True)
    sample = source / "跨线程拖放.txt"
    sample.write_text("hello", encoding="utf-8")

    def sender() -> None:
        time.sleep(0.6)
        user32 = dt_winapi.user32
        user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW(hwnd, WM_DROPFILES, make_hdrop([sample]), 0)
        print("另一个线程：拖放消息已发送")

    threading.Thread(target=sender, daemon=True).start()
    pump(app, 3.0)

    moved = list(tmp.rglob(sample.name))
    ok = bool(moved) and not sample.exists()
    print("文件是否被收进盒子：", ok, moved[:1])
    print("面板是否还活着：", bool(panel.winfo_exists()))
    try:
        app.quit()
    except Exception:
        pass
    print("结果：", "通过（没崩）" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
