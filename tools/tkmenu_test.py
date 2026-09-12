# -*- coding: utf-8 -*-
"""开发用探针：验证"面板已隐藏（收进托盘）时，Tk 菜单能否正常弹出并选中"。"""

import ctypes
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                               wintypes.LPARAM]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

chosen: list[str] = []


def visible_windows() -> set:
    found = set()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _l):
        if user32.IsWindowVisible(hwnd):
            found.add(int(hwnd))
        return True

    user32.EnumWindows(proc(callback), 0)
    return found


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    panel = tk.Toplevel(root)
    panel.geometry("300x200+200+200")
    panel.update()
    panel.withdraw()  # 模拟"面板已收进系统托盘"
    panel.update()

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="显示收纳面板", command=lambda: chosen.append("显示"))
    menu.add_separator()
    menu.add_command(label="一键整理桌面", command=lambda: chosen.append("整理"))
    menu.add_command(label="设置", command=lambda: chosen.append("设置"))

    before = visible_windows()
    result: dict = {}

    def probe() -> None:
        time.sleep(0.8)
        new = visible_windows() - before
        result["new_windows"] = new
        for hwnd in new:
            rect = wintypes.RECT()
            user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
            print(f"  新出现窗口 {hex(hwnd)} 位置=({rect.left},{rect.top})-"
                  f"({rect.right},{rect.bottom})")
            user32.PostMessageW(wintypes.HWND(hwnd), 0x0100, 0x1B, 0)  # ESC 关闭菜单
            break
        time.sleep(0.4)

    threading.Thread(target=probe, daemon=True).start()
    user32.SetCursorPos(700, 500)
    time.sleep(0.2)
    menu.tk_popup(700, 500)  # 会阻塞到菜单关闭
    print("菜单已关闭，" + ("弹出成功 OK" if result.get("new_windows") else "没有弹出 FAIL"))
    print("选中项:", chosen or "（ESC 关闭，无选中）")
    root.destroy()
    return 0 if result.get("new_windows") else 1


if __name__ == "__main__":
    sys.exit(main())
