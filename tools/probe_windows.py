# -*- coding: utf-8 -*-
"""开发用探针：列出当前桌面会话里的可见窗口（用于核对程序是否真的显示出来）。"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# 先声明 DPI 感知，否则拿到的坐标是被缩放虚化过的
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                               wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

rows = []


def callback(hwnd, _lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    title = ctypes.create_unicode_buffer(256)
    klass = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    user32.GetClassNameW(hwnd, klass, 256)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    rows.append((pid.value, klass.value, title.value,
                 rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
    return True


user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback), 0)

print(f"屏幕(SM_CXSCREEN x SM_CYSCREEN): {user32.GetSystemMetrics(0)} x {user32.GetSystemMetrics(1)}")
try:
    print(f"系统 DPI: {user32.GetDpiForSystem()}")
except Exception:
    pass

r = wintypes.RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
work_top, work_bottom = r.top, r.bottom
print(f"工作区: ({r.left},{r.top}) - ({r.right},{r.bottom})")

print(f"可见顶层窗口共 {len(rows)} 个")
shell = [r for r in rows if r[1] in ("Progman", "WorkerW", "Shell_TrayWnd", "SHELLDLL_DefView")]
print("桌面/任务栏窗口:", ", ".join(sorted({r[1] for r in shell})) or "无")

titles = [r[2] for r in rows]
app_rows = [r for r in rows if r[2] in ("桌面收纳盒",) or r[1].startswith("Tk")]
print(f"疑似本程序窗口 {len(app_rows)} 个")
for pid, klass, title, x, y, w, h in sorted(app_rows, key=lambda r: (r[4], r[3])):
    print(f"  pid={pid} class={klass:<24} title={title:<12} x={x:<5} y={y:<5} {w}x{h}")

for pid, klass, title, x, y, w, h in app_rows:
    if title != "桌面收纳盒":
        continue
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        continue
    client = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    bottom = origin.y + client.bottom
    print(f"  客户区: ({origin.x},{origin.y}) {client.right - client.left}x{client.bottom - client.top}")
    print(f"  屏幕顶边可见的客户区高度: {max(0, min(bottom, work_bottom) - max(origin.y, work_top))} px")

panel = [r for r in app_rows if r[2] == "桌面收纳盒"]
boxes = [r for r in app_rows if r[2] != "桌面收纳盒"]
if panel and boxes:
    px, py, pw, ph = panel[0][3], panel[0][4], panel[0][5], panel[0][6]
    overlap = 0
    for _pid, _cls, tname, x, y, w, h in boxes:
        if x < px + pw and px < x + w and y < py + ph and py < y + h:
            overlap += 1
            print(f"  ! 与主面板重叠的盒子: {tname or '(无标题)'}")
    print(f"主面板 {pw}x{ph} @ ({px},{py})，与盒子重叠 {overlap} 个")
