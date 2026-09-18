# -*- coding: utf-8 -*-
"""端到端回归：用真实面板窗口验证"从资源管理器拖文件进来"。

跑法（项目根目录）：python tools/drop_e2e_test.py
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_config  # noqa: E402
import dt_winapi  # noqa: E402

WM_DROPFILES = 0x0233
WS_EX_ACCEPTFILES = 0x00000010
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    print(("  [OK] " if ok else "  [!!] ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        failures += 1


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def make_hdrop(paths) -> int:
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


def get_long(hwnd: int, index: int) -> int:
    getter = getattr(dt_winapi.user32, "GetWindowLongPtrW", None) or dt_winapi.user32.GetWindowLongW
    getter.restype = ctypes.c_ssize_t
    getter.argtypes = [wintypes.HWND, ctypes.c_int]
    return int(getter(hwnd, index))


def ancestors(hwnd: int) -> list[int]:
    chain: list[int] = []
    seen = set()
    while hwnd and hwnd not in seen:
        seen.add(hwnd)
        chain.append(hwnd)
        hwnd = int(dt_winapi.user32.GetParent(hwnd) or 0)
    return chain


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def build_config(tmp: Path) -> dict:
    root = tmp / "收纳盒"
    cfg = dt_config.default_config()
    cfg["root"] = str(root)
    cfg["icon_size"] = 44
    cfg["panel"] = {"x": 300, "y": 120, "w": 560, "h": 800, "view": "organize",
                    "alpha": 1.0, "topmost": True}
    cfg["boxes"] = []
    for index, name in enumerate(("文档", "图片", "视频", "压缩包")):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        cfg["boxes"].append(dt_config.make_box(name, name, index))
    return cfg


def main() -> int:
    dt_winapi.make_dpi_aware()
    tmp = Path(tempfile.mkdtemp(prefix="tidy_drop_e2e_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    import main as app_main

    app = app_main.App(cfg)
    panel = app.panel
    pump(app, 1.6)

    print("1) 钩子安装")
    hooks = getattr(panel, "_drop_hooks", [])
    check("面板装上了拖放钩子", bool(hooks), f"钩子数={len(hooks)}")
    check("没有记录到失败原因", not getattr(panel, "_drop_error", ""),
          getattr(panel, "_drop_error", "") or "")

    print("2) 窗口扩展样式（资源管理器据此决定是否显示禁止光标）")
    hwnd = dt_winapi.hwnd_of(panel)
    for name, handle in (("面板主窗口", hwnd), ("外层包装窗口", int(dt_winapi.user32.GetParent(hwnd) or 0))):
        if not handle:
            continue
        style = get_long(handle, -20)
        check(f"{name} 带 WS_EX_ACCEPTFILES", bool(style & WS_EX_ACCEPTFILES), f"exstyle=0x{style:X}")

    print("3) 鼠标所在的那一点，能不能顺着父窗口找到「接受拖放」的窗口")
    dt_winapi.user32.WindowFromPoint.argtypes = [wintypes.POINT]
    dt_winapi.user32.WindowFromPoint.restype = wintypes.HWND
    left = panel.winfo_rootx()
    top = panel.winfo_rooty()
    width = panel.winfo_width()
    height = panel.winfo_height()
    probes = [(left + width // 2, top + height // 2), (left + 30, top + 60)]
    for point in probes:
        under = int(dt_winapi.user32.WindowFromPoint(wintypes.POINT(point[0], point[1])) or 0)
        chain = ancestors(under)
        hit = [h for h in chain if get_long(h, -20) & WS_EX_ACCEPTFILES]
        check(f"点{point} 能找到接受拖放的窗口", bool(hit),
              " <- ".join(f"0x{h:X}" for h in chain) + f"  命中=0x{hit[0]:X}" if hit else
              " <- ".join(f"0x{h:X}" for h in chain))

    print("4) 发一条真实拖放消息，看文件有没有被收进盒子")
    source_dir = tmp / "桌面"
    source_dir.mkdir(parents=True, exist_ok=True)
    sample = source_dir / "拖放测试.txt"
    sample.write_text("hello", encoding="utf-8")
    dt_winapi.user32.SendMessageW.argtypes = [
        wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
    ]
    dt_winapi.user32.SendMessageW.restype = ctypes.c_ssize_t
    dt_winapi.user32.SendMessageW(hwnd, WM_DROPFILES, make_hdrop([sample]), 0)
    pump(app, 1.2)
    moved_to = [p for p in tmp.rglob(sample.name)]
    check("文件已被收纳（不在原来位置）", not sample.exists(), str(sample))
    check("文件出现在收纳盒目录里", bool(moved_to), str(moved_to[:1]))
    check("面板仍然活着（没有崩）", bool(panel.winfo_exists()))

    app.quit()
    print("-" * 40)
    print("全部通过" if not failures else f"有 {failures} 项未通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
