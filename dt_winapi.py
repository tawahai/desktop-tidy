# -*- coding: utf-8 -*-
"""桌面收纳盒：Windows 原生能力，全部用标准库 ctypes 实现。

包括真实文件图标提取、PNG 编码、圆角窗口、桌面图标显示/隐藏、
回收站删除、开机自启，以及接收资源管理器拖入的文件。
"""

from __future__ import annotations

import base64
import ctypes
import os
import struct
import sys
import uuid
import zlib
from ctypes import POINTER, byref, c_int, c_uint, c_void_p, sizeof, wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, c_uint, wintypes.WPARAM, wintypes.LPARAM)

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE, SW_SHOW = 0, 5
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
MONITOR_DEFAULTTONEAREST = 2

SHGFI_ICON = 0x00000100
SHGFI_LARGEICON = 0x00000000
SHGFI_SYSICONINDEX = 0x00004000
SHGFI_USEFILEATTRIBUTES = 0x00000010

SHIL_LARGE, SHIL_EXTRALARGE, SHIL_JUMBO = 0, 2, 4
ILD_TRANSPARENT = 1

FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_DIRECTORY = 0x10

BI_RGB = 0


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_ubyte),
        ("rgbGreen", ctypes.c_ubyte),
        ("rgbRed", ctypes.c_ubyte),
        ("rgbReserved", ctypes.c_ubyte),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 2)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


IID_IImageList = _guid("46eb5926-582e-4017-9fdf-e8998daa0950")


def _setup_prototypes() -> None:
    """声明返回句柄的接口，避免 64 位下句柄被截断。"""
    hwnd_p = wintypes.HWND
    try:
        user32.FindWindowW.restype = hwnd_p
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowExW.restype = hwnd_p
        user32.FindWindowExW.argtypes = [hwnd_p, hwnd_p, wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.GetParent.restype = hwnd_p
        user32.GetParent.argtypes = [hwnd_p]
        user32.GetDC.restype = c_void_p
        user32.GetDC.argtypes = [hwnd_p]
        user32.ReleaseDC.argtypes = [hwnd_p, c_void_p]
        user32.GetIconInfo.argtypes = [wintypes.HICON, POINTER(ICONINFO)]
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.IsWindowVisible.argtypes = [hwnd_p]
        user32.ShowWindow.argtypes = [hwnd_p, c_int]
        user32.GetCursorPos.argtypes = [POINTER(wintypes.POINT)]
        user32.GetWindowRect.argtypes = [hwnd_p, POINTER(wintypes.RECT)]
        user32.GetClientRect.argtypes = [hwnd_p, POINTER(wintypes.RECT)]
        user32.ClientToScreen.argtypes = [hwnd_p, POINTER(wintypes.POINT)]
        user32.SetWindowPos.argtypes = [hwnd_p, hwnd_p, c_int, c_int, c_int, c_int, c_uint]
        user32.PostMessageW.argtypes = [hwnd_p, c_uint, wintypes.WPARAM, wintypes.LPARAM]
        user32.SetForegroundWindow.argtypes = [hwnd_p]
        getter = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        getter.restype = ctypes.c_ssize_t
        getter.argtypes = [hwnd_p, c_int]
        setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        setter.restype = ctypes.c_ssize_t
        setter.argtypes = [hwnd_p, c_int, ctypes.c_ssize_t]
        user32.MonitorFromWindow.restype = c_void_p
        user32.MonitorFromWindow.argtypes = [hwnd_p, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [c_void_p, ctypes.c_void_p]
        user32.SendMessageTimeoutW.restype = LRESULT
        user32.SendMessageTimeoutW.argtypes = [
            hwnd_p, c_uint, wintypes.WPARAM, wintypes.LPCWSTR, c_uint, c_uint, POINTER(ctypes.c_size_t)
        ]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [c_void_p, hwnd_p, c_uint, wintypes.WPARAM,
                                           wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.DefWindowProcW.argtypes = [hwnd_p, c_uint, wintypes.WPARAM, wintypes.LPARAM]
        gdi32.CreateRoundRectRgn.restype = c_void_p
        gdi32.CreateRoundRectRgn.argtypes = [c_int, c_int, c_int, c_int, c_int, c_int]
        gdi32.DeleteObject.argtypes = [c_void_p]
        gdi32.GetObjectW.argtypes = [c_void_p, c_int, c_void_p]
        gdi32.GetDIBits.argtypes = [c_void_p, c_void_p, c_uint, c_uint, c_void_p, POINTER(BITMAPINFO), c_uint]
        gdi32.GetDeviceCaps.restype = c_int
        gdi32.GetDeviceCaps.argtypes = [c_void_p, c_int]
        shell32.SHGetFileInfoW.restype = ctypes.c_size_t
        shell32.SHGetFileInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, POINTER(SHFILEINFOW), c_uint, c_uint
        ]
        shell32.SHGetImageList.restype = ctypes.c_long
        shell32.SHGetImageList.argtypes = [c_int, POINTER(GUID), POINTER(c_void_p)]
        shell32.SHChangeNotify.restype = None
        shell32.SHChangeNotify.argtypes = [ctypes.c_long, c_uint, c_void_p, c_void_p]
    except Exception:
        pass


_setup_prototypes()


# --------------------------------------------------------------------- PNG 编码
def png_encode(width: int, height: int, rgba: bytes) -> bytes:
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def png_to_data(png: bytes) -> str:
    return base64.b64encode(png).decode("ascii")


def downscale(rgba: bytes, width: int, height: int, size: int) -> bytes:
    """区域平均缩放，按 alpha 加权，避免边缘发黑。"""
    if width == size and height == size:
        return rgba
    out = bytearray(size * size * 4)
    for ty in range(size):
        y0 = ty * height // size
        y1 = max(y0 + 1, (ty + 1) * height // size)
        for tx in range(size):
            x0 = tx * width // size
            x1 = max(x0 + 1, (tx + 1) * width // size)
            r = g = b = a = n = 0
            for y in range(y0, y1):
                row = y * width * 4
                for x in range(x0, x1):
                    i = row + x * 4
                    alpha = rgba[i + 3]
                    r += rgba[i] * alpha
                    g += rgba[i + 1] * alpha
                    b += rgba[i + 2] * alpha
                    a += alpha
                    n += 1
            o = (ty * size + tx) * 4
            if a and n:
                out[o] = min(255, r // a)
                out[o + 1] = min(255, g // a)
                out[o + 2] = min(255, b // a)
                out[o + 3] = min(255, a // n)
    return bytes(out)


# --------------------------------------------------------------------- 图标提取
def _get_dib(hdc, hbitmap, width: int, height: int, bit_count: int = 32) -> bytes | None:
    stride = width * 4 if bit_count == 32 else ((width * bit_count + 31) // 32) * 4
    buf = ctypes.create_string_buffer(stride * height)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = bit_count
    bmi.bmiHeader.biCompression = BI_RGB
    if not gdi32.GetDIBits(hdc, hbitmap, 0, height, buf, byref(bmi), 0):
        return None
    return buf.raw


def _hicon_to_rgba(hicon) -> tuple[int, int, bytes] | None:
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, byref(info)):
        return None
    try:
        if not info.hbmColor:
            return None
        bm = BITMAP()
        if not gdi32.GetObjectW(info.hbmColor, sizeof(BITMAP), byref(bm)):
            return None
        width, height = int(bm.bmWidth), int(bm.bmHeight)
        if width <= 0 or height <= 0:
            return None
        hdc = user32.GetDC(None)
        try:
            color = _get_dib(hdc, info.hbmColor, width, height, 32)
            if not color or len(color) < width * height * 4:
                return None
            pixels = bytearray(color[: width * height * 4])
            # GetDIBits 给出的是 BGRA 顺序，而 PNG / PhotoImage 需要 RGBA：
            # 不换这一步，图标就会整体红蓝互换（黄色文件夹会变成青蓝色）。
            pixels[0::4], pixels[2::4] = pixels[2::4], pixels[0::4]
            if not any(pixels[i] for i in range(3, len(pixels), 4)) and info.hbmMask:
                mask = _get_dib(hdc, info.hbmMask, width, height, 1)
                if mask:
                    stride = ((width + 31) // 32) * 4
                    for y in range(height):
                        mrow = y * stride
                        prow = y * width * 4
                        for x in range(width):
                            bit = (mask[mrow + (x >> 3)] >> (7 - (x & 7))) & 1
                            pixels[prow + x * 4 + 3] = 0 if bit else 255
        finally:
            user32.ReleaseDC(None, hdc)
        return width, height, bytes(pixels)
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)


def _image_list_icon(index: int, shil: int = SHIL_JUMBO):
    try:
        ptr = c_void_p()
        if shell32.SHGetImageList(shil, byref(IID_IImageList), byref(ptr)) != 0 or not ptr:
            return None
        vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_int, c_uint, POINTER(wintypes.HICON))
        get_icon = proto(vtable[10])  # IImageList::GetIcon
        hicon = wintypes.HICON()
        if get_icon(ptr, index, ILD_TRANSPARENT, byref(hicon)) != 0 or not hicon:
            return None
        try:
            return _hicon_to_rgba(hicon)
        finally:
            user32.DestroyIcon(hicon)
    except Exception:
        return None


def _icon_index(path: str, use_attributes: bool, is_dir: bool = False):
    info = SHFILEINFOW()
    attrs = FILE_ATTRIBUTE_DIRECTORY if is_dir else FILE_ATTRIBUTE_NORMAL
    flags = SHGFI_SYSICONINDEX | SHGFI_ICON | SHGFI_LARGEICON
    if use_attributes:
        flags |= SHGFI_USEFILEATTRIBUTES
    if not shell32.SHGetFileInfoW(path, attrs, byref(info), sizeof(info), flags):
        return None
    if info.hIcon:
        user32.DestroyIcon(info.hIcon)
    return int(info.iIcon)


_ICON_CACHE: dict[tuple[str, int], bytes | None] = {}
_REAL_ICON_SUFFIX = {".lnk", ".url", ".exe", ".ico", ".scr", ".msi"}


def icon_png(path: Path | str, size: int = 48) -> bytes | None:
    """返回图标 PNG 字节（含透明通道），失败返回 None。"""
    path = Path(path)
    try:
        is_dir = path.is_dir()
    except OSError:
        is_dir = False
    suffix = path.suffix.lower()
    by_extension = bool(suffix) and not is_dir and suffix not in _REAL_ICON_SUFFIX
    key = ((suffix if by_extension else str(path)) + ("|d" if is_dir else "|f"), size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    result = None
    try:
        if by_extension:
            index = _icon_index("x" + suffix, True, False)
        else:
            index = _icon_index(str(path), False, is_dir)
            if index is None or index <= 0:
                index = _icon_index("x" + (suffix or "folder"), True, is_dir)
        if index is not None:
            data = (
                _image_list_icon(index, SHIL_JUMBO)
                or _image_list_icon(index, SHIL_EXTRALARGE)
                or _image_list_icon(index, SHIL_LARGE)
            )
            if data:
                w, h, rgba = data
                result = png_encode(size, size, downscale(rgba, w, h, size))
    except Exception:
        result = None
    _ICON_CACHE[key] = result
    return result


def clear_icon_cache() -> None:
    _ICON_CACHE.clear()


# --------------------------------------------------------------------- 窗口
def hwnd_of(window) -> int:
    try:
        return int(window.winfo_id())
    except Exception:
        return 0


def window_frame_hwnd(window) -> int:
    """带标题栏的窗口，真正的外框句柄是 Tk 窗口的父窗口。"""
    hwnd = hwnd_of(window)
    if not hwnd:
        return 0
    try:
        parent = user32.GetParent(hwnd)
        if parent:
            return int(parent)
    except Exception:
        pass
    return hwnd


def focus_window_by_title(title: str) -> bool:
    try:
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def request_show(title: str, message: int = 0x8002) -> bool:
    """给已在运行的实例发一条"把面板显示出来"的消息（双击启动.bat 时用）。"""
    try:
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.PostMessageW(hwnd, message, 0, 0)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def cursor_pos() -> tuple[int, int]:
    """鼠标当前位置（物理像素），失败返回 (-1, -1)。"""
    try:
        point = wintypes.POINT()
        if user32.GetCursorPos(byref(point)):
            return int(point.x), int(point.y)
    except Exception:
        pass
    return -1, -1


def window_metrics(window) -> dict:
    """窗口外框与客户区的实际屏幕位置（物理像素）。

    Tk 的 winfo_x/winfo_y 只是它自己记录的值，拖动或贴边后未必等于真实位置，
    所以需要定位时一律以这里的数据为准。
    """
    hwnd = window_frame_hwnd(window)
    data = {"fx": 0, "fy": 0, "fw": 0, "fh": 0, "cx": 0, "cy": 0, "cw": 0, "ch": 0,
            "top_border": 0, "left_border": 0}
    if not hwnd:
        return data
    try:
        frame = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, byref(frame)):
            return data
        client = wintypes.RECT()
        if not user32.GetClientRect(hwnd, byref(client)):
            return data
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, byref(origin))
        data.update({
            "fx": frame.left, "fy": frame.top,
            "fw": frame.right - frame.left, "fh": frame.bottom - frame.top,
            "cx": origin.x, "cy": origin.y,
            "cw": client.right - client.left, "ch": client.bottom - client.top,
            "top_border": origin.y - frame.top,
            "left_border": origin.x - frame.left,
        })
    except Exception:
        pass
    return data


def move_frame(window, x: int, y: int, width: int | None = None, height: int | None = None) -> bool:
    """直接按屏幕物理坐标移动窗口外框（Tk 的 geometry 写不出负坐标）。"""
    hwnd = window_frame_hwnd(window)
    if not hwnd:
        return False
    flags = SWP_NOZORDER | SWP_NOACTIVATE
    if width is None or height is None:
        flags |= SWP_NOSIZE
    try:
        return bool(user32.SetWindowPos(hwnd, 0, int(x), int(y),
                                        int(width or 0), int(height or 0), flags))
    except Exception:
        return False


def set_rounded_region(hwnd: int, width: int, height: int, radius: int = 14) -> None:
    if not hwnd or width <= 2 or height <= 2:
        return
    try:
        rgn = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2)
        if rgn and not user32.SetWindowRgn(hwnd, rgn, True):
            gdi32.DeleteObject(rgn)
    except Exception:
        pass


def set_alpha(window, value: float) -> None:
    try:
        window.attributes("-alpha", max(0.35, min(1.0, float(value))))
    except Exception:
        pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def monitor_work_area(window=None) -> tuple[int, int, int, int]:
    """窗口所在显示器的工作区。

    笔记本外接显示器 / 多屏时，贴边和吸附都要按"窗口所在的那块屏"来算。
    """
    if window is not None:
        try:
            hwnd = window_frame_hwnd(window)
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            if monitor:
                info = MONITORINFO()
                info.cbSize = sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, byref(info)):
                    rc = info.rcWork
                    return rc.left, rc.top, rc.right, rc.bottom
        except Exception:
            pass
    try:
        rect = wintypes.RECT()
        if user32.SystemParametersInfoW(0x0030, 0, byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1920, 1080


def set_tool_window(window, enabled: bool = True) -> bool:
    """让窗口不出现在任务栏和 Alt+Tab（托盘程序的标准做法）。"""
    try:
        hwnd = window_frame_hwnd(window)
        if not hwnd:
            return False
        getter = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        style = int(getter(hwnd, GWL_EXSTYLE))
        if enabled:
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        else:
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        setter(hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE
                            | SWP_FRAMECHANGED)
        return True
    except Exception:
        return False


class WindowSubclass:
    """给窗口过程挂一个 Python 回调，可叠加多层（托盘消息、最小化拦截等）。"""

    def __init__(self, hwnd: int, handler):
        self.hwnd = hwnd
        self.handler = handler  # handler(hwnd, msg, wparam, lparam) -> int | None
        self._old = None
        self._proc = WNDPROC(self._dispatch)  # 必须留引用
        try:
            setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            setter.restype = c_void_p
            setter.argtypes = [wintypes.HWND, c_int, c_void_p]
            self._old = setter(hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, c_void_p))
        except Exception:
            self._old = None

    @property
    def alive(self) -> bool:
        return bool(self._old)

    def _dispatch(self, hwnd, msg, wparam, lparam):
        try:
            result = self.handler(hwnd, msg, wparam, lparam)
            if result is not None:
                return result
        except Exception:
            pass
        if self._old:
            try:
                return user32.CallWindowProcW(self._old, hwnd, msg, wparam, lparam)
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def detach(self) -> None:
        if not self._old:
            return
        try:
            setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            setter(self.hwnd, GWLP_WNDPROC, ctypes.cast(self._old, c_void_p))
        except Exception:
            pass
        self._old = None


def make_dpi_aware() -> None:
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def system_dpi() -> int:
    try:
        dpi = int(user32.GetDpiForSystem())
        if dpi:
            return dpi
    except Exception:
        pass
    try:
        hdc = user32.GetDC(None)
        dpi = int(gdi32.GetDeviceCaps(hdc, 88))
        user32.ReleaseDC(None, hdc)
        return dpi or 96
    except Exception:
        return 96


# --------------------------------------------------------------------- 桌面图标
ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
SHCNE_ASSOCCHANGED = 0x08000000
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


def _find_defview() -> int:
    progman = user32.FindWindowW("Progman", None)
    if progman:
        dv = user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
        if dv:
            return dv
    found: list[int] = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        child = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if child:
            found.append(child)
            return False
        return True

    callback = proc_type(cb)
    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def _registry_hide_icons() -> bool | None:
    """读取资源管理器的"隐藏桌面图标"开关。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADVANCED_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "HideIcons")
        return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return None


def _write_registry_hide_icons(hide: bool) -> bool:
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ADVANCED_KEY) as key:
            winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, 1 if hide else 0)
        return True
    except Exception:
        return False


def _notify_desktop_refresh() -> None:
    try:
        shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)
    except Exception:
        pass
    try:
        result = ctypes.c_size_t()
        user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
            SMTO_ABORTIFHUNG, 1000, byref(result),
        )
    except Exception:
        pass


def desktop_icons_visible() -> bool | None:
    dv = _find_defview()
    if dv:
        return bool(user32.IsWindowVisible(dv))
    hidden = _registry_hide_icons()
    return None if hidden is None else (not hidden)


def set_desktop_icons_visible(visible: bool) -> bool:
    """隐藏/显示系统桌面图标，相当于右键桌面-查看-显示桌面图标。"""
    ok = _write_registry_hide_icons(not visible)
    dv = _find_defview()
    if dv:
        try:
            user32.ShowWindow(dv, SW_SHOW if visible else SW_HIDE)
            ok = True
        except Exception:
            pass
    if ok:
        _notify_desktop_refresh()
    return ok


# --------------------------------------------------------------------- 回收站
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_recycle_bin(paths: list[Path]) -> bool:
    if not paths:
        return False
    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = "\0".join(str(p) for p in paths) + "\0\0"
    op.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # 允许还原、不弹确认、静默
    try:
        return shell32.SHFileOperationW(byref(op)) == 0 and not op.fAnyOperationsAborted
    except Exception:
        return False


# --------------------------------------------------------------------- 开机自启
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "DesktopTidy"         # 注册表值名用 ASCII：中文名会让 Windows 的启动项子系统忽略它
RUN_NAME_CN = "桌面收纳盒"        # 旧的中文名，启用时顺手清掉
LEGACY_RUN_NAME = "DesktopTidy"  # 旧版用的名字，启用时顺手清掉
SHORTCUT_NAME = "桌面收纳盒.lnk"   # 启动文件夹里的快捷方式（名字是给人看的）
LAUNCHER_VBS_NAME = "自启.vbs"
LAUNCHER_PY_NAME = "自启.py"
TASK_NAME = "桌面收纳盒"

# C 盘上的启动器（Python 脚本，由 pythonw 执行）。
# 放 C 盘是因为系统盘开机最先就绪，而程序本体在 D 盘：启动器负责等 D 盘就绪、再拉起程序。
LAUNCHER_PY = '''# -*- coding: utf-8 -*-
"""桌面收纳盒 开机启动器（由 pythonw.exe 执行，程序本体在 D 盘时用它等待磁盘就绪）。"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

MAIN = Path(r"{main}")
PYTHONW = Path(r"{pythonw}")
LOG = Path(r"{log}")
TITLE = "{title}"


def log(message: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  [launcher] " + message + "\\n")
    except Exception:
        pass


def app_running() -> bool:
    try:
        user32 = ctypes.WinDLL("user32")
        user32.FindWindowW.restype = ctypes.c_void_p
        return bool(user32.FindWindowW(None, TITLE))
    except Exception:
        return False


time.sleep({wait})
if app_running():
    log("already running, skipped")
    sys.exit(0)

for attempt in range(1, {retries} + 1):
    if MAIN.exists() and PYTHONW.exists():
        try:
            subprocess.Popen([str(PYTHONW), str(MAIN)], cwd=str(MAIN.parent),
                             creationflags=0x00000008)  # DETACHED_PROCESS
            log("started the app (attempt %d)" % attempt)
            sys.exit(0)
        except Exception as exc:
            log("failed to start: %r" % (exc,))
            sys.exit(1)
    time.sleep(10)

log("FAILED - main.py or pythonw.exe was not found")
sys.exit(1)
'''

# VBS 只是极薄的包装：用 pythonw 运行 C 盘上的 Python 启动器
LAUNCHER_VBS = """' Desktop Tidy autostart wrapper
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run Chr(34) & "{exe}" & Chr(34) & " " & Chr(34) & "{launcher}" & Chr(34), 0, False
"""

# 登录时触发的计划任务：比注册表 Run 项更可靠，而且会出现在任务管理器的启动列表里。
# 注意：用 XML + InteractiveToken 创建**不需要管理员权限**（schtasks /sc onlogon 会要权限）。
TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>桌面收纳盒 开机自启</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{wscript}</Command>
      <Arguments>"{vbs}"</Arguments>
    </Exec>
  </Actions>
</Task>
"""

# 启动文件夹里的启动器：等系统就绪再拉起程序，失败会重试，并把结果写进日志。
# 之所以不只靠注册表 Run 项：开机时 Run 项可能排在最前面执行，那时程序所在磁盘还没就绪，
# 命令会静默失败（我们的实例就遇到过：Run 项存在且启用，但进程从没起来）。
STARTUP_LAUNCHER = """' Desktop Tidy autostart launcher
' Waits for the system to be ready, then starts the app and logs what happened.
Option Explicit
Dim sh, fso, wmi, procs, p, exePath, scriptPath, logPath, f, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
exePath = "{exe}"
scriptPath = "{script}"
logPath = "{log}"

WScript.Sleep 12000

' 已经在运行就不再启动
On Error Resume Next
Set wmi = GetObject("winmgmts:\\\\.\\root\\cimv2")
Set procs = wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='pythonw.exe'")
For Each p In procs
    If InStr(p.CommandLine, "main.py") > 0 Then
        WriteLog "autostart: already running, skipped"
        WScript.Quit 0
    End If
Next
On Error Goto 0

' 等磁盘/文件就绪再启动，最多试 6 次
For i = 1 To 6
    If fso.FileExists(exePath) And fso.FileExists(scriptPath) Then
        sh.Run Chr(34) & exePath & Chr(34) & " " & Chr(34) & scriptPath & Chr(34), 0, False
        WriteLog "autostart: started the app (attempt " & i & ")"
        WScript.Quit 0
    End If
    WScript.Sleep 10000
Next
WriteLog "autostart: FAILED - pythonw.exe or main.py was not found"

Sub WriteLog(msg)
    On Error Resume Next
    Set f = fso.OpenTextFile(logPath, 8, True)
    f.WriteLine Year(Now) & "-" & Right("0" & Month(Now), 2) & "-" & Right("0" & Day(Now), 2) & " " & _
        Right("0" & Hour(Now), 2) & ":" & Right("0" & Minute(Now), 2) & ":" & Right("0" & Second(Now), 2) & _
        "  [launcher] " & msg
    f.Close
End Sub
"""


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = frozen_exe_path()
    if exe.exists():
        return f'"{exe}"'   # 有独立 exe 就直接用它（普通程序，最不容易被拦）
    launcher = launcher_py_path()
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    if launcher.exists():
        # 启动器在 C 盘：它负责等 D 盘就绪、再拉起程序（并写日志）
        return f'"{exe}" "{launcher}"'
    script = Path(__file__).resolve().parent / "main.py"
    return f'"{exe}" "{script}"'


def launcher_vbs_path() -> Path:
    """VBS 启动器路径（用户数据目录，在 C 盘）。

    不放"启动"文件夹：安全软件会锁住那里的 .vbs（实测普通 txt 能写、.vbs 被拒绝）。
    放 C 盘是因为系统盘开机最先就绪，而程序本体在 D 盘。
    """
    return launcher_py_path().with_name(LAUNCHER_VBS_NAME)


def launcher_py_path() -> Path:
    """启动器（Python 版）路径——放在用户数据目录（C 盘）。"""
    try:
        import dt_config

        return dt_config.appdata_dir() / LAUNCHER_PY_NAME
    except Exception:
        return Path(os.environ.get("APPDATA", ".")) / "DesktopTidy" / LAUNCHER_PY_NAME


def frozen_exe_path() -> Path:
    """独立 exe 的路径（用户数据目录，C 盘）。

    自启优先用它：exe 是"普通程序"，比"pythonw 跑脚本"这种模式更不容易被杀软拦。
    """
    try:
        import dt_config

        return dt_config.appdata_dir() / "DesktopTidy.exe"
    except Exception:
        return Path(os.environ.get("APPDATA", ".")) / "DesktopTidy" / "DesktopTidy.exe"


def _write_py_launcher() -> bool:
    """生成 C 盘上的启动器脚本，供注册表项和计划任务调用。"""
    try:
        import dt_config

        script = Path(__file__).resolve().parent / "main.py"
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        log = dt_config.appdata_dir() / "tray.log"
        content = LAUNCHER_PY.format(main=script, pythonw=exe, log=log, title="桌面收纳盒",
                                     wait=12, retries=6)
        target = launcher_py_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def _write_startup_launcher() -> bool:
    """生成带等待与重试的启动器脚本（不弹黑窗）。"""
    try:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        content = LAUNCHER_VBS.format(exe=exe, launcher=launcher_py_path())
        target = launcher_vbs_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        # VBS 按 ANSI 写；内容除路径外都是 ASCII
        target.write_text(content, encoding="mbcs", errors="replace")
        return True
    except Exception:
        return False


def _remove_startup_launcher() -> None:
    try:
        launcher_vbs_path().unlink(missing_ok=True)
    except Exception:
        pass


def _run_hidden(args: list[str]) -> int:
    """不弹黑窗地跑一个外部命令，返回退出码（失败返回 -1）。"""
    try:
        import subprocess

        return subprocess.run(args, creationflags=0x08000000,  # CREATE_NO_WINDOW
                              capture_output=True).returncode
    except Exception:
        return -1


def _create_logon_task() -> bool:
    """创建"登录时运行"的计划任务（用 XML + 交互式令牌，无需管理员权限）。"""
    try:
        import tempfile
        from xml.sax.saxutils import escape

        user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
        # 任务计划不会用 PATH 搜索，wscript 必须给完整路径
        wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
        xml = TASK_XML.format(user=escape(user), vbs=escape(str(launcher_vbs_path())),
                              wscript=escape(str(wscript)))
        path = Path(tempfile.gettempdir()) / "desktop_tidy_task.xml"
        path.write_text(xml, encoding="utf-16")
        return _run_hidden(["schtasks", "/create", "/tn", TASK_NAME, "/xml", str(path), "/f"]) == 0
    except Exception:
        return False


def _delete_logon_task() -> None:
    _run_hidden(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])


def startup_folder() -> Path:
    """启动文件夹路径（优先读注册表，兼容用户目录被重定向）。"""
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, _ = winreg.QueryValueEx(handle, "Startup")
        path = Path(os.path.expandvars(value))
        if path.exists():
            return path
    except Exception:
        pass
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_shortcut_path() -> Path:
    return startup_folder() / SHORTCUT_NAME


def _create_startup_shortcut() -> bool:
    """在"启动"文件夹里建快捷方式（最标准、任务管理器一定会列出的自启方式）。

    注意：这个文件夹里放 .vbs 会被安全软件拒绝（本机实测），但放 .lnk 没问题。
    """
    try:
        import dt_config

        pyw = Path(sys.executable).with_name("pythonw.exe")
        launcher = launcher_py_path()
        exe = frozen_exe_path()
        if exe.exists():
            target, arguments = str(exe), ""
        elif launcher.exists():
            target, arguments = str(pyw), f'"{launcher}"'
        else:
            return False
        script_path = dt_config.appdata_dir() / "make_shortcut.ps1"
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            "$sh = New-Object -ComObject WScript.Shell\n"
            f"$sc = $sh.CreateShortcut('{startup_shortcut_path()}')\n"
            f"$sc.TargetPath = '{target}'\n"
            f"$sc.Arguments = '{arguments}'\n"
            f"$sc.WorkingDirectory = '{Path(target).parent}'\n"
            "$sc.Description = 'Desktop Tidy'\n"
            "$sc.Save()\n"
        )
        # 带 BOM 写，PowerShell 才能正确读取中文路径
        script_path.write_text(script, encoding="utf-8-sig")
        return _run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(script_path)]) == 0
    except Exception:
        return False


def _remove_startup_shortcut() -> None:
    try:
        startup_shortcut_path().unlink(missing_ok=True)
    except Exception:
        pass


def set_autostart(on: bool) -> bool:
    try:
        import winreg

        if on:
            # 先写启动器（C 盘），再写注册表与计划任务（它们的命令里带启动器路径）
            _write_py_launcher()
            _create_startup_shortcut()
            # 说明：曾尝试"登录计划任务"通道，但在本机环境下任务计划调用
            # wscript/pythonw 都会失败（结果码 1 / 2），故不再启用。
            _delete_logon_task()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _startup_command())
                for legacy in (RUN_NAME_CN,):  # 清掉以前用中文名写的那条
                    try:
                        winreg.DeleteValue(key, legacy)
                    except FileNotFoundError:
                        pass
            else:
                for name in (RUN_NAME, RUN_NAME_CN, LEGACY_RUN_NAME):
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        if not on:
            _remove_startup_launcher()
            _remove_startup_shortcut()
            try:
                launcher_py_path().unlink(missing_ok=True)
            except Exception:
                pass
            _delete_logon_task()
        return True
    except Exception:
        return False


def autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except Exception:
        return launcher_vbs_path().exists() or launcher_py_path().exists()


# --------------------------------------------------------------------- 拖入文件
LAST_DROP_ERROR = ""  # 最近一次启用拖入失败的原因（空字符串表示没出错）


class FileDropHook:
    """把资源管理器的文件拖放（WM_DROPFILES）接到 Tk 窗口上。"""

    def __init__(self, hwnd: int, callback):
        self.hwnd = hwnd
        self.callback = callback
        self.alive = False
        self.error = ""
        self._old = None
        self._proc = WNDPROC(self._wndproc)  # 必须留引用，回调被回收会崩溃
        try:
            # DragAcceptFiles / DragQueryFileW / DragFinish 都在 shell32.dll 里，
            # 之前误写成 user32.DragAcceptFiles —— 会抛 AttributeError 并被静默吞掉，
            # 结果就是"接受拖放"标志从未设置，拖文件过来一直是红色禁止光标。
            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragAcceptFiles.restype = None
            shell32.DragQueryFileW.restype = c_uint
            shell32.DragQueryFileW.argtypes = [c_void_p, c_uint, ctypes.c_wchar_p, c_uint]
            shell32.DragFinish.argtypes = [c_void_p]
            user32.CallWindowProcW.restype = LRESULT
            user32.CallWindowProcW.argtypes = [
                c_void_p, wintypes.HWND, c_uint, wintypes.WPARAM, wintypes.LPARAM
            ]
            setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            setter.restype = c_void_p
            setter.argtypes = [wintypes.HWND, c_int, c_void_p]
            self._old = setter(hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, c_void_p))
            shell32.DragAcceptFiles(hwnd, True)
            self.alive = bool(self._old)
        except Exception:
            import traceback

            self.error = traceback.format_exc()
            self.alive = False
            global LAST_DROP_ERROR
            LAST_DROP_ERROR = self.error.strip().splitlines()[-1] if self.error.strip() else "未知错误"

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            import dt_diag

            dt_diag.event(f"拖放：收到 WM_DROPFILES（窗口=0x{hwnd:X}）")
            try:
                hdrop = c_void_p(wparam)
                count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                buf = ctypes.create_unicode_buffer(32768)
                paths = []
                for i in range(count):
                    if shell32.DragQueryFileW(hdrop, i, buf, 32768):
                        paths.append(buf.value)
                shell32.DragFinish(hdrop)
                dt_diag.event(f"拖放：解析出 {len(paths)} 个路径 {paths[:3]}")
                if paths:
                    self.callback(paths)
                dt_diag.event("拖放：已交给界面处理")
            except Exception as exc:
                import traceback

                dt_diag.event("拖放：处理失败 " + traceback.format_exc().replace("\n", " | "))
            return 0
        if self._old:
            return user32.CallWindowProcW(self._old, hwnd, msg, wparam, lparam)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def detach(self) -> None:
        if not self.alive or not self._old:
            return
        try:
            setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            setter(self.hwnd, GWLP_WNDPROC, ctypes.cast(self._old, c_void_p))
            shell32.DragAcceptFiles(self.hwnd, False)
        except Exception:
            pass
        self.alive = False


def enable_file_drop(window, callback) -> list[FileDropHook]:
    """在窗口（及其外层包装窗口）上启用文件拖入。"""
    global LAST_DROP_ERROR
    LAST_DROP_ERROR = ""
    hooks: list[FileDropHook] = []
    hwnd = hwnd_of(window)
    if not hwnd:
        LAST_DROP_ERROR = "取不到窗口句柄"
        return hooks
    hook = FileDropHook(hwnd, callback)
    if hook.alive:
        hooks.append(hook)
    try:
        parent = user32.GetParent(hwnd)
    except Exception:
        parent = 0
    if parent and parent != hwnd:
        hook2 = FileDropHook(parent, callback)
        if hook2.alive:
            hooks.append(hook2)
    if not hooks:
        LAST_DROP_ERROR = hook.error.strip().splitlines()[-1] if hook.error.strip() else "钩子未安装成功"
    else:
        LAST_DROP_ERROR = ""
    return hooks


def release_drops(hooks: list[FileDropHook]) -> None:
    for hook in hooks or []:
        try:
            hook.detach()
        except Exception:
            pass


# --------------------------------------------------------------------- 其它
def shell_open(path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def reveal_in_explorer(path) -> None:
    p = Path(path)
    try:
        if p.is_dir():
            os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            os.system(f'explorer /select,"{p}"')
    except Exception:
        pass
