"""验证"从资源管理器拖文件进盒子"这条链路真的通。

看三件事：
1. enable_file_drop 能装上钩子（以前 DragAcceptFiles 写错 DLL，抛错被静默吞掉）
2. 窗口扩展样式里带上了 WS_EX_ACCEPTFILES（0x10）—— 这正是资源管理器判断"能不能放"的依据
3. 伪造一个 WM_DROPFILES 消息发进窗口，回调能拿到文件路径

用法：python tools/drop_test.py
"""
import ctypes
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

import dt_winapi  # noqa: E402

WM_DROPFILES = 0x0233
GWL_EXSTYLE = -20
WS_EX_ACCEPTFILES = 0x00000010
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def make_hdrop(paths):
    """在全局内存里拼一个 DROPFILES 结构，当作 HDROP 用（和拖放时系统给的一样）。"""
    header = DROPFILES()
    header.pFiles = ctypes.sizeof(DROPFILES)
    header.fWide = True
    blob = b"".join(str(p).encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
    data = bytes(header) + blob
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def exstyle(hwnd: int) -> int:
    getter = getattr(dt_winapi.user32, "GetWindowLongPtrW", None) or dt_winapi.user32.GetWindowLongW
    getter.restype = ctypes.c_ssize_t
    getter.argtypes = [wintypes.HWND, ctypes.c_int]
    return int(getter(hwnd, GWL_EXSTYLE))


def main() -> int:
    root = tk.Tk()
    root.title("drop probe")
    root.geometry("420x260+1200+700")
    canvas = tk.Canvas(root, bg="#222")
    canvas.pack(fill="both", expand=True)
    card = tk.Frame(canvas, bg="#333")
    card.place(x=20, y=20, width=200, height=120)
    root.update()

    received: list = []
    hooks = dt_winapi.enable_file_drop(root, received.append)
    root.update()

    root_hwnd = dt_winapi.hwnd_of(root)
    parent_hwnd = int(dt_winapi.user32.GetParent(root_hwnd) or 0)
    child_hwnd = int(canvas.winfo_id())

    print("钩子数量        :", len(hooks), "（每层窗口一个，0 表示没装成功）")
    print("最近失败原因    :", dt_winapi.LAST_DROP_ERROR or "（无）")
    for name, hwnd in (("Tk 主窗口", root_hwnd), ("外层包装窗口", parent_hwnd),
                       ("画布子窗口", child_hwnd)):
        if not hwnd:
            continue
        style = exstyle(hwnd)
        ok = "[OK] 接受拖放" if style & WS_EX_ACCEPTFILES else "[NO] 不接受拖放"
        print(f"{name:<8} hwnd=0x{hwnd:X}  exstyle=0x{style:X}  {ok}")

    tmpdir = Path(tempfile.mkdtemp(prefix="dt_drop_"))
    sample = tmpdir / "拖放测试文件.txt"
    sample.write_text("hello", encoding="utf-8")

    def send_drop() -> None:
        handle = make_hdrop([sample])
        dt_winapi.user32.SendMessageW.argtypes = [
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
        ]
        dt_winapi.user32.SendMessageW.restype = ctypes.c_ssize_t
        dt_winapi.user32.SendMessageW(root_hwnd, WM_DROPFILES, handle, 0)

    def finish() -> None:
        got = received[0] if received else []
        print("收到路径        :", got)
        hit = bool(got) and Path(got[0]) == sample
        print("模拟拖放结果    :", "[OK] 回调收到正确路径" if hit else "[NO] 回调没收到路径")
        dt_winapi.release_drops(hooks)
        print("释放后钩子状态  :", [h.alive for h in hooks])
        root.destroy()
        raise SystemExit(0 if (hooks and hit and dt_winapi.LAST_DROP_ERROR == "") else 1)

    root.after(400, send_drop)
    root.after(900, finish)
    try:
        root.mainloop()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 1


if __name__ == "__main__":
    sys.exit(main())
