# -*- coding: utf-8 -*-
"""桌面收纳盒：自检脚本（不会影响真实桌面，全部在临时目录里跑）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import dt_config
import dt_organize
import dt_winapi

PASS, FAIL = "  [OK] ", "  [!!] "
failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(PASS + label + (f"  {detail}" if detail else ""))
    else:
        failures += 1
        print(FAIL + label + (f"  {detail}" if detail else ""))


def test_rules() -> None:
    print("分类规则")
    rules = dt_config.DEFAULT_RULES
    cases = {
        "报告.docx": "文档",
        "截图.png": "图片",
        "电影.mp4": "视频",
        "备份.tar.gz": "压缩包",
        "安装程序.exe": "程序",
        "微博.lnk": "快捷方式",
        "神秘文件.xyz": "其他",
    }
    for name, expect in cases.items():
        got = dt_organize.category_for(Path(name), rules)
        check(f"{name} → {expect}", got == expect, "" if got == expect else f"实际 {got}")


def test_png_and_icon(tmp: Path) -> None:
    print("图标与图片编码")
    sample = tmp / "示例.txt"
    sample.write_text("hello", encoding="utf-8")
    png = dt_winapi.icon_png(sample, 48)
    check("文本文件图标", bool(png) and png.startswith(b"\x89PNG"), f"{len(png or b'')} 字节")

    folder_png = dt_winapi.icon_png(tmp, 48)
    check("文件夹图标", bool(folder_png) and folder_png.startswith(b"\x89PNG"))

    lnk = tmp / "演示.lnk"
    lnk.write_bytes(b"")
    check("快捷方式图标", bool(dt_winapi.icon_png(lnk, 48)))

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        img = tk.PhotoImage(data=dt_winapi.png_to_data(png))
        ok = img.width() == 48 and img.height() == 48
        check("Tk 能加载生成的图标", ok, f"{img.width()}x{img.height()}")
        # 极端尺寸
        for size in (32, 64, 96):
            check(f"图标尺寸 {size}", bool(dt_winapi.icon_png(sample, size)))
        root.destroy()
    except Exception as exc:  # noqa: BLE001
        check("Tk 能加载生成的图标", False, str(exc))


def test_organize(tmp: Path) -> None:
    print("整理与撤销")
    fake_desktop = tmp / "Desktop"
    fake_desktop.mkdir(exist_ok=True)
    root = tmp / "收纳盒"
    for name in ["报告.docx", "照片.jpg", "音乐.mp3", "包.rar", "工具.exe", "杂项.xyz"]:
        (fake_desktop / name).write_text("x", encoding="utf-8")
    (fake_desktop / "收藏夹").mkdir(exist_ok=True)
    (fake_desktop / "desktop.ini").write_text("", encoding="utf-8")

    cfg = {
        "root": str(root),
        "rules": dt_config.DEFAULT_RULES,
        "custom_rules": {},
        "boxes": [dt_config.make_box(n) for n in list(dt_config.DEFAULT_RULES) + ["其他"]],
    }
    original_desktop = dt_config.desktop_dir
    original_history = dt_config.history_dir
    dt_config.desktop_dir = lambda: fake_desktop  # type: ignore[assignment]
    dt_config.history_dir = lambda: tmp / "history"  # type: ignore[assignment]
    (tmp / "history").mkdir(exist_ok=True)
    try:
        found = dt_organize.desktop_entries(cfg)
        check("只挑文件、跳过文件夹和系统文件", len(found) == 6, f"找到 {len(found)} 个")

        plan = dt_organize.build_plan(cfg)
        summary = dt_organize.summarize(plan)
        check("分类结果", summary.get("文档") == 1 and summary.get("图片") == 1
              and summary.get("压缩包") == 1 and summary.get("程序") == 1
              and summary.get("其他") == 1, str(summary))

        record = dt_organize.apply_plan(plan)
        check("搬运完成", len(record["moves"]) == 6 and not record["errors"])
        check("文档已进盒子", (root / "文档" / "报告.docx").exists())
        check("桌面已清空", len(dt_organize.desktop_entries(cfg)) == 0)

        (fake_desktop / "报告.docx").write_text("新文件", encoding="utf-8")
        plan2 = dt_organize.build_plan(cfg)
        dt_organize.apply_plan(plan2)
        check("同名文件自动改名", (root / "文档" / "报告 (2).docx").exists())

        undo = dt_organize.undo_last()
        check("撤销还原", len(undo["restored"]) == 1 and (fake_desktop / "报告.docx").exists(),
              str(undo["errors"]))

        extra = fake_desktop / "拖入示例.png"
        extra.write_text("x", encoding="utf-8")
        moved, errors = dt_organize.move_into([str(extra)], root / "图片")
        check("拖入收纳", len(moved) == 1 and not errors and (root / "图片" / "拖入示例.png").exists(),
              str(errors))
        check("移回桌面", dt_organize.move_to_desktop(root / "图片" / "拖入示例.png") is not None
              and extra.exists())
    finally:
        dt_config.desktop_dir = original_desktop  # type: ignore[assignment]
        dt_config.history_dir = original_history  # type: ignore[assignment]


def test_windows() -> None:
    print("系统接口")
    visible = dt_winapi.desktop_icons_visible()
    if visible is None:
        print(PASS + "读取桌面图标状态  当前环境没有桌面窗口，跳过（真机上可用）")
    else:
        check("读取桌面图标状态", True, f"当前 {'显示' if visible else '隐藏'}")
    check("桌面图标开关接口可用", hasattr(dt_winapi, "set_desktop_icons_visible")
          and dt_winapi.ADVANCED_KEY.endswith("Advanced"))
    dpi = dt_winapi.system_dpi()
    check("读取屏幕缩放", dpi >= 96, f"{dpi} dpi")
    check("图标列表缓存可用", len(dt_winapi._ICON_CACHE) > 0, f"{len(dt_winapi._ICON_CACHE)} 项")


def main() -> int:
    print("桌面收纳盒 自检")
    print("-" * 42)
    with tempfile.TemporaryDirectory(prefix="desktoptidy_") as tmpdir:
        tmp = Path(tmpdir)
        test_rules()
        test_png_and_icon(tmp)
        test_organize(tmp)
        test_windows()
    print("-" * 42)
    if failures:
        print(f"有 {failures} 项未通过")
        return 1
    print("全部通过，可以正常使用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
