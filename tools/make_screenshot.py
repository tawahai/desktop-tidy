# -*- coding: utf-8 -*-
"""生成 README 用的界面截图。

用临时目录当"桌面"、放一批示例文件，全程不碰真实文件；
截图只截面板客户区（不含桌面背景），生成到 docs/ 下。

用法: python tools/make_screenshot.py
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

SRCCOPY = 0x00CC0020

# 本程序的配色（用于自检：确认截到的确实是我们的面板，而不是被别的窗口盖住）
APP_PALETTE = (
    (0x1B, 0x20, 0x27),  # 面板底色
    (0x27, 0x2E, 0x38),  # 分区卡片
    (0x16, 0x1A, 0x20),  # 分区内容底色
    (0x31, 0x39, 0x47),  # 悬停色
    (0x24, 0x2A, 0x33),  # 菜单底色
)
PALETTE_TOLERANCE = 14
MIN_PALETTE_RATIO = 0.5

SAMPLES = {
    "文档": ["季度汇报.docx", "会议纪要.md", "产品需求.pdf", "报价单.xlsx"],
    "图片": ["截图_001.png", "旅行照片.jpg", "背景图.webp"],
    "视频": ["项目演示.mp4", "剪辑素材.mov"],
    "音频": ["录音_0812.mp3"],
    "压缩包": ["素材包.zip"],
    "程序": ["安装程序.exe"],
    "快捷方式": ["微信.lnk", "浏览器.url"],
    "其他": ["待整理文件.xyz"],
}

gdi32 = dt_winapi.gdi32
user32 = dt_winapi.user32
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL


def grab(x: int, y: int, width: int, height: int) -> bytes:
    """抓屏幕上一块区域，返回 RGBA 字节。"""
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    old = gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, width, height, hdc, x, y, SRCCOPY)
    bmi = dt_winapi.BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(dt_winapi.BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(bmi), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, hdc)
    data = bytearray(buf.raw)
    data[0::4], data[2::4] = data[2::4], data[0::4]  # BGRA -> RGBA
    return bytes(data)


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def palette_ratio(pixels: bytes, width: int, height: int, step: int = 2) -> float:
    """统计属于本程序配色的像素比例，用来判断截图有没有被别的窗口盖住。"""
    total = 0
    hit = 0
    for y in range(0, height, step):
        row = y * width * 4
        for x in range(0, width, step):
            i = row + x * 4
            r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
            total += 1
            for pr, pg, pb in APP_PALETTE:
                if (abs(r - pr) <= PALETTE_TOLERANCE and abs(g - pg) <= PALETTE_TOLERANCE
                        and abs(b - pb) <= PALETTE_TOLERANCE):
                    hit += 1
                    break
    return hit / total if total else 0.0


def build_config(tmp: Path) -> dict:
    root = tmp / "收纳盒"
    cfg = dt_config.default_config()
    cfg["root"] = str(root)
    cfg["icon_size"] = 44
    cfg["panel"] = {"x": 300, "y": 120, "w": 560, "h": 820, "view": "organize",
                    "alpha": 1.0, "topmost": False}
    cfg["boxes"] = []
    for index, (name, files) in enumerate(SAMPLES.items()):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            (folder / file_name).write_text("sample", encoding="utf-8")
        cfg["boxes"].append(dt_config.make_box(name, name, index))
    return cfg


def capture(app, panel, path: Path) -> bool:
    """把面板切到前台再截图，并自检画面确实是本程序。"""
    hwnd = dt_winapi.window_frame_hwnd(panel)
    user32.SetForegroundWindow(hwnd)
    panel.lift()
    panel.focus_force()
    pump(app, 0.6)
    metrics = dt_winapi.window_metrics(panel)
    pixels = grab(metrics["cx"], metrics["cy"], metrics["cw"], metrics["ch"])
    ratio = palette_ratio(pixels, metrics["cw"], metrics["ch"])
    ok = ratio >= MIN_PALETTE_RATIO
    if ok:
        path.write_bytes(dt_winapi.png_encode(metrics["cw"], metrics["ch"], pixels))
        print(f"已保存 {path.name}（{metrics['cw']}x{metrics['ch']}，"
              f"面板配色占比 {ratio:.0%}）")
    else:
        print(f"截图自检未通过：{path.name} 里只有 {ratio:.0%} 的像素属于本程序，"
              f"可能被其它窗口盖住了")
    return ok


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tidy_shot_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    dt_winapi.make_dpi_aware()
    import main as app_main

    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    previous_foreground = user32.GetForegroundWindow()
    app = app_main.App(cfg)
    panel = app.panel
    panel.attributes("-topmost", True)  # 截图期间置顶，避免被别的窗口盖住
    pump(app, 1.4)

    results = [capture(app, panel, out_dir / "screenshot-main.png")]

    panel.show_view("settings")
    pump(app, 1.2)
    results.append(capture(app, panel, out_dir / "screenshot-settings.png"))

    panel.attributes("-topmost", False)
    if previous_foreground:
        user32.SetForegroundWindow(previous_foreground)  # 把焦点还给原来的窗口
    app.quit()
    if all(results):
        print("完成")
        return 0
    print("有截图未通过自检，请重跑（或手动截图）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
