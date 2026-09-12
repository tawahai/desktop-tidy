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


def capture(panel, path: Path) -> None:
    metrics = dt_winapi.window_metrics(panel)
    pixels = grab(metrics["cx"], metrics["cy"], metrics["cw"], metrics["ch"])
    path.write_bytes(dt_winapi.png_encode(metrics["cw"], metrics["ch"], pixels))
    print(f"已保存 {path.name}（{metrics['cw']}x{metrics['ch']}）")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tidy_shot_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    dt_winapi.make_dpi_aware()
    import main as app_main

    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = app_main.App(cfg)
    panel = app.panel
    pump(app, 1.4)
    capture(panel, out_dir / "screenshot-main.png")

    panel.show_view("settings")
    pump(app, 1.2)
    capture(panel, out_dir / "screenshot-settings.png")

    app.quit()
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
