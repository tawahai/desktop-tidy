# -*- coding: utf-8 -*-
"""回归测试：图标颜色是否正确 + 单击/双击是否响应。

跑法（在项目根目录）：python tools/item_click_test.py
"""

from __future__ import annotations

import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_config  # noqa: E402
import dt_winapi  # noqa: E402

SAMPLES = {
    "文档": ["季度汇报.docx", "会议纪要.md"],
    "图片": ["屏幕截图.png", "旅行照片.jpg"],
    "视频": ["演示视频.mp4"],
    "音频": ["背景音乐.mp3"],
    "压缩包": ["素材包.zip"],
    "程序": ["安装程序.exe"],
    "快捷方式": ["微信.lnk"],
    "其他": ["未知文件.xyz"],
}

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    print(("  [OK] " if ok else "  [!!] ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        failures += 1


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
    cfg["panel"] = {"x": 300, "y": 120, "w": 560, "h": 800, "view": "organize",
                    "alpha": 1.0, "topmost": False}
    cfg["boxes"] = []
    for index, (name, files) in enumerate(SAMPLES.items()):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            (folder / file_name).write_text("x", encoding="utf-8")
        cfg["boxes"].append(dt_config.make_box(name, name, index))
    return cfg


def main() -> int:
    dt_winapi.make_dpi_aware()
    tmp = Path(tempfile.mkdtemp(prefix="tidy_click_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    print("单击 / 双击")
    import main as app_main

    app = app_main.App(cfg)
    panel = app.panel
    pump(app, 1.2)

    print("图标颜色")
    folder_png = dt_winapi.icon_png(tmp, 64)  # 文件夹图标应为黄色系
    image = tk.PhotoImage(master=app.root, data=dt_winapi.png_to_data(folder_png))
    total = [0, 0, 0]
    count = 0
    for y in range(16, 48):
        for x in range(16, 48):
            r, g, b = image.get(x, y)
            total[0] += r
            total[1] += g
            total[2] += b
            count += 1
    avg = [value // max(1, count) for value in total]
    check("文件夹图标是黄色系（R 应大于 B）", avg[0] > avg[2], f"平均色 RGB={avg}")
    check("红色分量明显（说明没有红蓝互换）", avg[0] > 120, f"R={avg[0]}")

    item_path, frame = panel.items[0]
    target = frame.winfo_children()[-1]
    before = str(item_path) in panel.selected
    target.event_generate("<Button-1>", x=5, y=5)
    pump(app, 0.2)
    check("单击后被选中", (not before) and str(item_path) in panel.selected)
    check("选中后控件仍然存在（没有重建）", frame.winfo_exists())

    opened: list[str] = []
    original = dt_winapi.shell_open
    dt_winapi.shell_open = lambda p: opened.append(str(p))
    try:
        # Tk 不允许直接生成 <Double-Button-1>，改成快速连发两次按下事件（Tk 会自行判成双击）
        target.event_generate("<Button-1>", x=5, y=5)
        pump(app, 0.05)
        target.event_generate("<Button-1>", x=5, y=5)
        pump(app, 0.3)
    finally:
        dt_winapi.shell_open = original
    check("双击触发打开", bool(opened), str(opened[:1]))

    app.quit()
    print("-" * 40)
    print("全部通过" if not failures else f"有 {failures} 项未通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
