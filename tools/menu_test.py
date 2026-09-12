# -*- coding: utf-8 -*-
"""开发用探针：验证托盘右键菜单与鼠标的相对位置，以及误点退出是否已被挡住。

用法: python _menu_test.py              # 只检查菜单位置，然后用 ESC 关掉
      python _menu_test.py click-exit   # 点最后一项（退出程序），验证会弹确认框
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
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p]

WM_TRAY = 0x8001
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_CANCELMODE = 0x001F
VK_ESCAPE = 0x1B
LEFTDOWN, LEFTUP = 0x0002, 0x0004


def tray_message(event: int, uid: int = 1) -> int:
    return ((event & 0xFFFF) << 16) | (uid & 0xFFFF)


def menu_rect():
    hwnd = user32.FindWindowW("#32768", None)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect


def icon_exists(hwnd, uid: int = 1) -> bool:
    data = dt_tray.NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = hwnd
    data.uID = uid
    data.uFlags = dt_tray.NIF_TIP
    data.szTip = "桌面收纳盒"
    return bool(dt_tray.shell32.Shell_NotifyIconW(dt_tray.NIM_MODIFY, ctypes.byref(data)))


def main() -> int:
    click_exit = len(sys.argv) > 1 and sys.argv[1] == "click-exit"
    panel = user32.FindWindowW(None, "桌面收纳盒")
    if not panel:
        print("没找到面板窗口")
        return 1
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(panel, ctypes.byref(pid))
    print(f"目标窗口={hex(panel)} 进程={pid.value} 可见={bool(user32.IsWindowVisible(panel))} "
          f"托盘图标已注册={icon_exists(panel)}")
    if not user32.IsWindowVisible(panel):
        user32.PostMessageW(panel, WM_TRAY, 1, tray_message(WM_LBUTTONUP))
        time.sleep(1.2)

    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    original = (point.x, point.y)

    # 把鼠标放到右下角托盘图标附近再右键，模拟真实操作
    left, top, right, bottom = dt_winapi.monitor_work_area(None)
    user32.SetCursorPos(right - 120, bottom + 20)
    time.sleep(0.3)
    user32.PostMessageW(panel, WM_TRAY, 1, tray_message(WM_RBUTTONUP))
    time.sleep(1.0)

    found = menu_rect()
    if not found:
        print("菜单没有弹出")
        user32.SetCursorPos(*original)
        return 1
    menu_hwnd, rect = found
    user32.GetCursorPos(ctypes.byref(point))
    print(f"鼠标位置=({point.x},{point.y})  菜单=({rect.left},{rect.top})-"
          f"({rect.right},{rect.bottom})")
    inside = rect.left <= point.x <= rect.right and rect.top <= point.y <= rect.bottom
    print(f"鼠标是否落在菜单范围内（会误触）: {inside} → {'仍有风险 FAIL' if inside else '已让开 OK'}")

    if click_exit:
        # 现在菜单最后一项是"设置"，点它不应该退出程序
        user32.SetCursorPos(rect.left + 60, rect.bottom - 12)
        time.sleep(0.2)
        user32.mouse_event(LEFTDOWN, 0, 0, 0, None)
        user32.mouse_event(LEFTUP, 0, 0, 0, None)
        time.sleep(1.2)
        alive = bool(user32.IsWindow(panel))
        print(f"点菜单最后一项后: 程序仍在运行={alive} → {'OK' if alive else 'FAIL'}")
    else:
        user32.PostMessageW(menu_hwnd, WM_CANCELMODE, 0, 0)
        time.sleep(0.4)

    user32.SetCursorPos(*original)
    print("鼠标位置已恢复")
    return 0


if __name__ == "__main__":
    sys.exit(main())
