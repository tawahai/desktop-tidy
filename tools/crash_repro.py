# -*- coding: utf-8 -*-
"""开发用探针：复现真实右键托盘图标时 Windows 发出的消息序列，看程序会不会挂。

真实序列（日志实测）：lParam = MAKELONG(事件, 图标id)
  0x200 鼠标移动（会刷很多条）→ 0x204 右键按下 → 0x205 右键抬起 → 0x7B WM_CONTEXTMENU
"""

import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                               wintypes.LPARAM]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

WM_TRAY = 0x8001
UID = 1
SEQ = [0x200] * 30 + [0x204, 0x205, 0x007B]


def tray_message(event: int, uid: int = UID) -> int:
    """事件在低位、图标 id 在高位（Windows 真实发法）。"""
    return ((uid & 0xFFFF) << 16) | (event & 0xFFFF)


def main() -> int:
    hwnd = user32.FindWindowW(None, "桌面收纳盒")
    if not hwnd:
        print("没找到面板窗口（程序可能已经退出了）")
        return 1
    print("开始发送真实右键消息序列（事件在低位）…")
    before = visible_windows()
    for event in SEQ:
        user32.PostMessageW(hwnd, WM_TRAY, 0x04D1082B, tray_message(event))
        time.sleep(0.03)
    time.sleep(1.5)
    alive = bool(user32.IsWindow(hwnd))
    print(f"2 秒后窗口是否还在: {alive} → {'没崩 OK' if alive else '程序挂了 FAIL'}")
    menu_windows = visible_windows() - before
    if menu_windows:
        for menu_hwnd in menu_windows:
            rect = wintypes.RECT()
            user32.GetWindowRect(wintypes.HWND(menu_hwnd), ctypes.byref(rect))
            print(f"新窗口 {hex(menu_hwnd)} 位置=({rect.left},{rect.top})-"
                  f"({rect.right},{rect.bottom}) → 菜单已弹出 OK")
            user32.PostMessageW(wintypes.HWND(menu_hwnd), 0x0100, 0x1B, 0)  # ESC 关掉
    else:
        print("没有新窗口 → 菜单没有弹出 FAIL")
    time.sleep(0.5)
    alive = bool(user32.IsWindow(hwnd))
    print(f"关掉菜单后窗口是否还在: {alive} → {'OK' if alive else '程序挂了 FAIL'}")
    return 0 if alive else 1


def visible_windows() -> set:
    found = set()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(h, _l):
        if user32.IsWindowVisible(h):
            found.add(int(h))
        return True

    user32.EnumWindows(proc(callback), 0)
    return found


if __name__ == "__main__":
    sys.exit(main())
