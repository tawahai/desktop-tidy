# -*- coding: utf-8 -*-
"""开发用探针：在真机上验证托盘功能。

模拟点击窗口的关闭按钮（发 WM_CLOSE），看是否收起到托盘；
再模拟点击托盘图标（发 WM_TRAY + 左键消息），看是否恢复显示。
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_winapi  # noqa: E402
import dt_tray  # noqa: E402

user32 = dt_winapi.user32
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]

WM_CLOSE = 0x0010
WM_TRAY = 0x8001
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CANCELMODE = 0x001F
WM_KEYDOWN = 0x0100
VK_ESCAPE = 0x1B
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20


def tray_message(event: int, uid: int = 1) -> int:
    """版本 4 的托盘回调：低位是图标 id，高位才是鼠标事件。"""
    return ((event & 0xFFFF) << 16) | (uid & 0xFFFF)


def icon_exists(hwnd, uid: int = 1) -> bool:
    """用 NIM_MODIFY 探测该 (窗口, 图标 id) 是否已经在托盘里注册。"""
    data = dt_tray.NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = hwnd
    data.uID = uid
    data.uFlags = dt_tray.NIF_TIP
    data.szTip = "桌面收纳盒（运行中）"
    return bool(dt_tray.shell32.Shell_NotifyIconW(dt_tray.NIM_MODIFY, ctypes.byref(data)))


def main() -> int:
    hwnd = user32.FindWindowW(None, "桌面收纳盒")
    if not hwnd:
        print("没找到面板窗口")
        return 1

    style = int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))
    print(f"扩展样式=0x{style:x} 含 TOOLWINDOW(不在任务栏)={bool(style & WS_EX_TOOLWINDOW)}")
    visible_now = bool(user32.IsWindowVisible(hwnd))
    print(f"点关闭前窗口可见: {visible_now}")

    results = []
    if visible_now:
        exists = icon_exists(hwnd)
        results.append(exists)
        print(f"面板显示中，托盘里是否已有图标: {exists} → {'OK' if exists else 'FAIL'}")
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(1.2)
    hidden = not user32.IsWindowVisible(hwnd)
    results.append(hidden)
    print(f"点关闭后窗口可见: {bool(user32.IsWindowVisible(hwnd))} "
          f"→ {'已收起到托盘 OK' if hidden else '没有收起（说明托盘图标没能建立）FAIL'}")

    if hidden:
        user32.PostMessageW(hwnd, WM_TRAY, 1, tray_message(WM_RBUTTONUP))
        time.sleep(1.0)
        menu_hwnd = user32.FindWindowW("#32768", None)
        print(f"托盘右键菜单: {'已弹出 OK' if menu_hwnd else '没有弹出 FAIL'}")
        results.append(bool(menu_hwnd))
        if menu_hwnd:
            user32.PostMessageW(menu_hwnd, WM_CANCELMODE, 0, 0)
            time.sleep(0.4)
            if user32.FindWindowW("#32768", None):
                user32.PostMessageW(menu_hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
                time.sleep(0.4)
        print(f"菜单关闭后窗口仍然隐藏: {not user32.IsWindowVisible(hwnd)}")

        user32.PostMessageW(hwnd, WM_TRAY, 1, tray_message(WM_LBUTTONUP))
        time.sleep(1.2)
        shown = bool(user32.IsWindowVisible(hwnd))
        results.append(shown)
        print(f"点托盘图标后窗口可见: {shown} → {'已恢复显示 OK' if shown else '没能恢复 FAIL'}")

    print("托盘测试通过" if all(results) and results else "托盘测试未通过")
    return 0 if all(results) and results else 1


if __name__ == "__main__":
    sys.exit(main())
