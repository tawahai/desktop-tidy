# -*- coding: utf-8 -*-
"""桌面收纳盒：系统托盘图标（纯 ctypes 调用 Shell_NotifyIcon，不依赖第三方库）。"""

from __future__ import annotations

import ctypes
from ctypes import byref, sizeof, wintypes

import dt_icon
import dt_winapi

user32 = dt_winapi.user32
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]

WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_SHOW_REQUEST = WM_APP + 2  # 已有实例时，用这条消息把面板叫到前面
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = 0xF020
SC_RESTORE = 0xF120

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x01
NOTIFYICON_VERSION_4 = 4

MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
TPM_RETURNCMD, TPM_RIGHTBUTTON, TPM_NONOTIFY = 0x0100, 0x0002, 0x0080
WM_NULL = 0x0000

GWLP_WNDPROC = -4

user32.CreatePopupMenu.restype = ctypes.c_void_p
user32.CreatePopupMenu.argtypes = []
user32.AppendMenuW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class TrayIcon:
    """托盘图标：左键点击 = 回调，右键 = 回调，最小化时拦截（可选）。"""

    def __init__(self, window, tooltip: str = "桌面收纳盒", uid: int = 1):
        self.window = window
        self.hwnd = dt_winapi.window_frame_hwnd(window)
        self.uid = uid
        self.visible = False
        self.hicon = dt_icon.icon_hicon(32)
        self.on_click = None          # 回调：左键单击 / 双击
        self.on_right_click = None    # 回调：右键
        self.on_minimize = None       # 回调：点了最小化按钮
        self.on_show_request = None   # 回调：别的进程请求把面板显示出来
        self.logger = None            # 可选日志函数（排查"莫名退出"用）
        self._sub = None
        self._last_right_click = 0.0  # 一次右键会同时发 RBUTTONUP 和 CONTEXTMENU，去重
        self._pending: str | None = None
        self._alive = True
        self._poll_job = None
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._install_hook()
        try:
            self._poll_job = self.window.after(120, self._poll_pending)
        except Exception:
            self._poll_job = None

    # ------------------------------------------------------------- 窗口过程
    def _install_hook(self) -> None:
        if not self.hwnd:
            return
        hook = dt_winapi.WindowSubclass(self.hwnd, self._on_message)
        self._sub = hook if hook.alive else None

    def _on_message(self, hwnd, msg, wparam, lparam):
        """窗口过程：只记标记，绝不在这里调用 Tk。

        真实托盘场景下资源管理器会连发几十条通知，如果在系统模态循环里回调进 Tcl
        （例如直接调用 after / 改控件），会导致进程硬崩——没有异常也没有崩溃日志。
        """
        if msg == WM_TRAY:
            value = int(lparam)
            low, high = value & 0xFFFF, (value >> 16) & 0xFFFF
            # 事件具体在哪一半由系统版本决定，两半都看一眼
            events = {low, high}
            if events & {WM_LBUTTONUP, WM_LBUTTONDBLCLK}:
                self._pending = "click"
            elif events & {WM_RBUTTONUP, WM_CONTEXTMENU}:
                import time as _time

                now = _time.monotonic()
                if now - self._last_right_click < 0.5:
                    return 0  # 同一次右键的第二条消息，忽略
                self._last_right_click = now
                self._pending = "right"
            return 0
        if msg == WM_SYSCOMMAND and (int(wparam) & 0xFFF0) == SC_MINIMIZE:
            self._pending = "minimize"
            return 0
        if msg == WM_SHOW_REQUEST:
            self._pending = "show"
            return 0
        if self._taskbar_created and msg == self._taskbar_created:
            # 资源管理器重启后要重新加回图标
            was_visible = self.visible
            self.visible = False
            if was_visible:
                self._pending = "readd"
            return 0
        return None

    def _poll_pending(self) -> None:
        """在 Tk 自己的事件循环里处理托盘动作（窗口过程只负责记标记）。"""
        pending, self._pending = self._pending, None
        if pending:
            if self.logger:
                try:
                    self.logger({"click": "托盘左键", "right": "托盘右键",
                                 "minimize": "托盘最小化请求",
                                 "show": "收到显示请求（双击启动.bat）"}.get(pending, pending))
                except Exception:
                    pass
            callback = {"click": self.on_click, "right": self.on_right_click,
                        "minimize": self.on_minimize, "readd": self.show,
                        "show": self.on_show_request}.get(pending)
            if callback is not None:
                try:
                    callback()
                except Exception as exc:
                    if self.logger:
                        try:
                            self.logger(f"处理托盘动作出错: {exc!r}")
                        except Exception:
                            pass
        if self._alive:
            try:
                self._poll_job = self.window.after(120, self._poll_pending)
            except Exception:
                self._poll_job = None

    # ------------------------------------------------------------- 图标操作
    def _data(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = self.uid
        data.uCallbackMessage = WM_TRAY
        return data

    def show(self, balloon: str = "", tip: str | None = None) -> bool:
        """加入或更新托盘图标（图标不存在就加入，存在就更新）。"""
        if not self.hwnd:
            return False
        data = self._data()
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.hIcon = self.hicon
        data.szTip = (tip or self.window.title() or "桌面收纳盒")[:100]
        if balloon:
            data.uFlags |= NIF_INFO
            data.szInfo = balloon[:200]
            data.szInfoTitle = "桌面收纳盒"
            data.dwInfoFlags = NIIF_INFO
        ok = bool(shell32.Shell_NotifyIconW(NIM_ADD if not self.visible else NIM_MODIFY, byref(data)))
        if ok:
            self.visible = True
            try:
                data.uVersion = NOTIFYICON_VERSION_4
                shell32.Shell_NotifyIconW(NIM_SETVERSION, byref(data))
            except Exception:
                pass
        return ok

    def hide(self) -> None:
        if not self.visible or not self.hwnd:
            return
        data = self._data()
        try:
            shell32.Shell_NotifyIconW(NIM_DELETE, byref(data))
        except Exception:
            pass
        self.visible = False

    def destroy(self) -> None:
        self._alive = False
        if self._poll_job:
            try:
                self.window.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        self.hide()
        if self.hicon:
            try:
                user32.DestroyIcon(self.hicon)
            except Exception:
                pass
            self.hicon = 0
        if self._sub is not None:
            self._sub.detach()
            self._sub = None


def popup_menu(hwnd: int, x: int, y: int, items, gap: int = 14) -> int | None:
    """弹原生菜单，返回被选中的命令 id（没选返回 None）。

    items 形如 [(1, "显示面板"), (None, None), (2, "退出程序")]，None 表示分隔线。
    用原生菜单是因为它在窗口隐藏/最小化状态下也能正常弹出。

    gap 是"菜单离鼠标的间距"：托盘图标在屏幕右下角，菜单会贴着光标弹出，
    鼠标很容易正好落在最后一项上，随手一点就误触，所以这里主动往上让开一段。
    """
    menu = user32.CreatePopupMenu()
    if not menu:
        return None
    try:
        for command_id, label in items:
            if label is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                user32.AppendMenuW(menu, MF_STRING, int(command_id), label)
        user32.SetForegroundWindow(hwnd)  # 不加这句菜单点外面不会消失
        chosen = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                       int(x), int(y) - int(gap), 0, hwnd, None)
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        return int(chosen) or None
    finally:
        user32.DestroyMenu(menu)
