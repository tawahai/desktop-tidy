# -*- coding: utf-8 -*-
"""桌面收纳盒：程序图标（黄色抽屉）。

图标是用代码画出来的，不依赖任何图片文件：
先按 4 倍超采样绘制，再按面积平均缩小，所以小尺寸也不会有明显锯齿。

直接运行本文件会把多尺寸 icon 写入 app.ico（打包 exe 用）。
"""

from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from pathlib import Path

import dt_winapi

user32 = dt_winapi.user32
gdi32 = dt_winapi.gdi32

SS = 4  # 超采样倍数
DIB_RGB_COLORS = 0

OUTLINE = (150, 104, 16, 255)
BODY_TOP = (248, 203, 92, 255)
BODY_BOTTOM = (224, 164, 42, 255)
TOP_PLATE = (255, 226, 140, 255)
DRAWER = (252, 214, 118, 255)
DRAWER_EDGE = (214, 166, 52, 255)
HANDLE = (124, 88, 16, 255)

gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(dt_winapi.BITMAPINFO),
                                   ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_void_p, ctypes.c_uint]
gdi32.CreateBitmap.restype = ctypes.c_void_p
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                               ctypes.c_void_p]
user32.CreateIconIndirect.restype = wintypes.HICON
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(dt_winapi.ICONINFO)]


def _mix(a, b, t: float):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _inside_round_rect(x, y, x0, y0, x1, y1, r) -> bool:
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def draw_drawer_rgba(size: int) -> bytes:
    """画出抽屉图标，返回 size×size 的 RGBA 字节。"""
    span = max(8, int(size)) * SS
    buf = bytearray(span * span * 4)

    def paint(x0, y0, x1, y1, radius, color_fn) -> None:
        px0, py0 = x0 * span, y0 * span
        px1, py1 = x1 * span, y1 * span
        r = radius * span
        for y in range(max(0, int(py0)), min(span, int(py1) + 2)):
            for x in range(max(0, int(px0)), min(span, int(px1) + 2)):
                if _inside_round_rect(x, y, px0, py0, px1, py1, r):
                    i = (y * span + x) * 4
                    buf[i:i + 4] = bytes(color_fn(x / span, y / span))

    # 外壳描边
    paint(0.075, 0.095, 0.925, 0.925, 0.10, lambda _x, _y: OUTLINE)
    # 箱体（带竖向渐变）
    paint(0.125, 0.145, 0.875, 0.875, 0.062,
          lambda _x, y: _mix(BODY_TOP, BODY_BOTTOM, (y - 0.145) / 0.73))
    # 顶板
    paint(0.125, 0.145, 0.875, 0.265, 0.055, lambda _x, _y: TOP_PLATE)
    # 两个抽屉：先描边再填面
    for top in (0.305, 0.555):
        paint(0.175, top, 0.825, top + 0.205, 0.035, lambda _x, _y: DRAWER_EDGE)
        paint(0.195, top + 0.022, 0.805, top + 0.183, 0.026, lambda _x, _y: DRAWER)
        # 拉手
        hy = top + 0.085
        paint(0.365, hy, 0.635, hy + 0.048, 0.024, lambda _x, _y: HANDLE)
    # 箱体底部一点暗边，增加立体感
    paint(0.125, 0.845, 0.875, 0.875, 0.03, lambda _x, _y: DRAWER_EDGE)

    return dt_winapi.downscale(bytes(buf), span, span, size)


def icon_png(size: int) -> bytes:
    return dt_winapi.png_encode(size, size, draw_drawer_rgba(size))


def icon_bgra(size: int) -> bytes:
    rgba = draw_drawer_rgba(size)
    data = bytearray(rgba)
    data[0::4], data[2::4] = data[2::4], data[0::4]
    return bytes(data)


def icon_hicon(size: int = 32) -> int:
    """把图标转成 HICON（托盘、任务栏用）。用完要 DestroyIcon。"""
    bmi = dt_winapi.BITMAPINFO()
    bmi.bmiHeader.biSize = dt_winapi.sizeof(dt_winapi.BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    bits = ctypes.c_void_p()
    color = gdi32.CreateDIBSection(None, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits),
                                   None, 0)
    if not color or not bits:
        return 0
    ctypes.memmove(bits, icon_bgra(size), size * size * 4)
    mask = gdi32.CreateBitmap(size, size, 1, 1, None)
    info = dt_winapi.ICONINFO(True, 0, 0, mask, color)
    hicon = user32.CreateIconIndirect(ctypes.byref(info)) or 0
    gdi32.DeleteObject(color)   # CreateIconIndirect 会复制位图
    if mask:
        gdi32.DeleteObject(mask)
    return int(hicon)


def save_ico(path: Path | str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> Path:
    """写出多尺寸 .ico。

    用传统的 BMP 格式存每个尺寸（而不是 PNG 压缩），
    这样老版本 PyInstaller / 图标工具都能正确读取。
    """
    path = Path(path)
    payloads = []
    for size in sizes:
        payloads.append((size, _bmp_payload(size)))
    entries = bytearray()
    offset = 6 + 16 * len(payloads)
    blobs = bytearray()
    for size, data in payloads:
        entries += struct.pack("<BBBBHHII", 0 if size >= 256 else size,
                               0 if size >= 256 else size, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    header = struct.pack("<HHH", 0, 1, len(payloads))
    path.write_bytes(bytes(header) + bytes(entries) + bytes(blobs))
    return path


def _bmp_payload(size: int) -> bytes:
    """ICO 里的单张图片：BITMAPINFOHEADER + 32 位像素（自下而上）+ 掩码。"""
    bgra = icon_bgra(size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
    stride = size * 4
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        pixels += bgra[y * stride:(y + 1) * stride]
    mask_stride = ((size + 31) // 32) * 4
    mask = bytes(mask_stride * size)  # 全 0：透明信息由 32 位 alpha 决定
    return header + bytes(pixels) + mask


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "app.ico"
    save_ico(target)
    print(f"已生成 {target}（{target.stat().st_size} 字节）")
