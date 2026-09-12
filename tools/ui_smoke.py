# -*- coding: utf-8 -*-
"""临时界面冒烟测试：用临时目录模拟桌面与分区，运行 18 秒后自动退出。

跑法：python _ui_smoke.py
"""

import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_config  # noqa: E402
import dt_winapi  # noqa: E402

SAMPLES = {
    "文档": ["季度汇报.docx", "会议纪要.md", "方案.pdf"],
    "图片": ["屏幕截图.png", "旅行照片.jpg"],
    "视频": ["演示视频.mp4"],
    "音频": ["背景音乐.mp3"],
    "压缩包": ["素材包.zip"],
    "程序": ["安装程序.exe"],
    "快捷方式": ["微信.lnk"],
    "其他": ["未知文件.xyz"],
}


def build_config(tmp: Path) -> dict:
    root = tmp / "收纳盒"
    cfg = dt_config.default_config()
    cfg["root"] = str(root)
    cfg["rules"] = dt_config.DEFAULT_RULES
    cfg["icon_size"] = 44
    cfg["panel"] = dt_config.default_panel()
    cfg["boxes"] = []
    for index, (name, files) in enumerate(SAMPLES.items()):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            (folder / file_name).write_text("x", encoding="utf-8")
        cfg["boxes"].append(dt_config.make_box(name, name, index))
    return cfg


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def wheel_check(app, widget, canvas, label: str) -> bool:
    """在控件上模拟一次滚轮，看对应画布有没有滚动。"""
    before = canvas.yview()
    try:
        widget.event_generate("<MouseWheel>", delta=-120)
    except Exception as exc:  # noqa: BLE001
        print(f"{label} 滚轮事件发送失败: {exc}")
        return False
    pump(app, 0.15)
    after = canvas.yview()
    moved = abs(after[0] - before[0]) > 1e-6
    print(f"{label} 滚轮: {before[0]:.3f} -> {after[0]:.3f} {'OK' if moved else 'FAIL 没反应'}")
    return moved


SCREEN_SIZES = [(1366, 728), (1536, 824), (1920, 1040), (1024, 728)]


def screen_fit_test(app_main, tmp: Path) -> bool:
    """在模拟的小屏尺寸下检查面板是否完整落在工作区内（笔记本兼容性）。"""
    real_path, real_work = dt_config.config_path, dt_config.work_area
    real_monitor = dt_winapi.monitor_work_area
    results = []
    for width, height in SCREEN_SIZES:
        dt_config.work_area = lambda w=width, h=height: (0, 0, w, h)
        dt_winapi.monitor_work_area = lambda window=None, w=width, h=height: (0, 0, w, h)
        cfg = dt_config.default_config()
        cfg["root"] = str(tmp / f"screen_{width}")
        cfg["panel"] = dt_config.default_panel()
        path = tmp / f"cfg_{width}.json"
        dt_config.config_path = lambda p=path: p
        try:
            app = app_main.App(cfg)
            pump(app, 0.9)
            m = dt_winapi.window_metrics(app.panel)
            inside = (m["fx"] >= 0 and m["fy"] >= 0
                      and m["fx"] + m["fw"] <= width + 2
                      and m["fy"] + m["fh"] <= height + 2)
            results.append(inside)
            print(f"模拟 {width}x{height}: 客户区={m['cw']}x{m['ch']} "
                  f"外框位置=({m['fx']},{m['fy']}) 完整在屏内={inside}")
            app.quit()
            pump(app, 0.3)
        except Exception as exc:  # noqa: BLE001
            print(f"模拟 {width}x{height}: 异常 {exc}")
            results.append(False)
    dt_config.config_path, dt_config.work_area = real_path, real_work
    dt_winapi.monitor_work_area = real_monitor
    return all(results)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tidy_ui_"))
    cfg = build_config(tmp)
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]

    dt_winapi.make_dpi_aware()
    import main as app_main

    screen_ok = screen_fit_test(app_main, tmp)
    app = app_main.App(cfg)
    panel = app.panel
    panel._check_dock_mouse = lambda: None  # 测试里不让鼠标位置干扰

    def exercise():
        print("分区数量:", len(panel.sections))
        print("分区列表:", [s["box"]["name"] for s in panel.sections.values()])
        print("文档分区项目数:", len(panel.sections[cfg["boxes"][0]["id"]]["items"]))
        panel.flash("测试提示")
        panel.toggle_section(cfg["boxes"][0])
        panel.toggle_section(cfg["boxes"][0])
        panel.show_view("settings")
        app.refresh_panel()
        panel.show_view("organize")
        source = panel.sections[cfg["boxes"][1]["id"]]
        target = panel.sections[cfg["boxes"][2]["id"]]
        files = [p for p, _f in source["items"]][:1]
        if files:
            app.move_paths_into(files, target["box"])
            print("搬运后 视频分区项目数:", len(panel.sections[cfg["boxes"][2]["id"]]["items"]))
        panel.set_box_color(cfg["boxes"][3], "#3a3044")
        panel.toggle_all()
        panel.toggle_all()
        panel.refresh_sections(force=True)
        print("汇总:", panel.summary.cget("text"))

        # 滚动条与滚轮
        pump(app, 0.3)
        settings = panel.settings
        panel.show_view("organize")
        pump(app, 0.4)
        bar = getattr(panel.canvas, "bar", None)
        print(f"收纳页 滚动条: 宽度={bar.winfo_width() if bar else 0} "
              f"滑块={bar._thumb_span() if bar else None} 滚动范围={panel.canvas.cget('scrollregion')!r}")
        ok_wheel = wheel_check(app, panel.sections[cfg["boxes"][0]["id"]]["header"],
                               panel.canvas, "收纳页(分区标题)")
        panel.show_view("settings")
        pump(app, 0.4)
        bar = getattr(settings.canvas, "bar", None)
        print(f"设置页 滚动条: 宽度={bar.winfo_width() if bar else 0} "
              f"滑块={bar._thumb_span() if bar else None} 滚动范围={settings.canvas.cget('scrollregion')!r}")
        ok_wheel = wheel_check(app, settings.inner, settings.canvas, "设置页") and ok_wheel
        panel.show_view("organize")
        pump(app, 0.3)

        # 托盘图标 / 任务栏样式 / 程序图标
        hwnd = dt_winapi.window_frame_hwnd(panel)
        style_before = int(dt_winapi.user32.GetWindowLongPtrW(hwnd, -20))
        applied = dt_winapi.set_tool_window(panel, True)
        pump(app, 0.2)
        style_after = int(dt_winapi.user32.GetWindowLongPtrW(hwnd, -20))
        print(f"任务栏样式: 之前=0x{style_before:x} 之后=0x{style_after:x} "
              f"设置返回={applied}")

        # 退出确认：弹不出确认框时必须"不退出"，选"否"时也必须"不退出"
        import main as app_main_module
        import dt_ui as ui_module
        ask = ui_module.ask_confirm
        try:
            ui_module.ask_confirm = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("模拟确认框弹不出来"))
            app.quit_confirmed()
            smoke_ok = bool(app.root.winfo_exists())
            print(f"确认框弹出失败时不退出: {smoke_ok}")
            ui_module.ask_confirm = lambda *a, **k: False
            app.quit_confirmed()
            no_ok = bool(app.root.winfo_exists())
            print(f"确认框选【否】时不退出: {no_ok}")
        finally:
            ui_module.ask_confirm = ask
        import dt_icon
        import tkinter as tk
        photo = tk.PhotoImage(data=dt_winapi.png_to_data(dt_icon.icon_png(32)))
        print(f"抽屉图标可加载: {photo.width()}x{photo.height()}")
        tray = getattr(app, "tray", None)
        ok_tray = True
        if tray is None:
            print("托盘: 本环境没有资源管理器托盘，跳过（真机上可用）")
            app.hide_to_tray()
            pump(app, 0.2)
            print("托盘不可用时窗口保持显示:", panel.winfo_viewable())
        else:
            app.hide_to_tray()
            pump(app, 0.3)
            hid = not panel.winfo_viewable()
            if not hid:
                print("托盘图标加不进去（本环境没有资源管理器托盘）→ 窗口按设计保持显示")
                ok_tray = panel.winfo_viewable()
            else:
                app.show_from_tray()
                pump(app, 0.3)
                back = panel.winfo_viewable()
                ok_tray = hid and back
                print(f"收起到托盘: {hid} / 恢复显示: {back}")

        # 贴边自动隐藏
        top = dt_config.work_area()[1]
        start = dt_winapi.window_metrics(panel)
        panel.dock_top(start["fx"], start["cw"])
        pump(app, 1.2)
        metrics = dt_winapi.window_metrics(panel)
        hidden_ok = abs(metrics["fy"] - panel._hidden_frame_y()) <= 2
        visible = max(0, metrics["cy"] + metrics["ch"] - top)
        print(f"贴边隐藏: 外框y={metrics['fy']} 期望={panel._hidden_frame_y()} "
              f"状态={panel._dock_state} 屏幕上可见={visible}px -> {hidden_ok}")
        panel.reveal()
        pump(app, 1.2)
        metrics = dt_winapi.window_metrics(panel)
        shown_ok = abs(metrics["fy"] - top) <= 2
        print(f"鼠标触碰后展开: 外框y={metrics['fy']} 期望={top} "
              f"状态={panel._dock_state} 客户区高度={metrics['ch']} -> {shown_ok}")
        panel.undock()
        pump(app, 0.5)
        metrics = dt_winapi.window_metrics(panel)
        print(f"取消贴边: 外框y={metrics['fy']} docked={panel.panel_cfg.get('docked')} "
              f"按钮={panel.dock_button.cget('text')}")
        print("全部渲染正常")
        return (hidden_ok and shown_ok and ok_wheel and ok_tray and screen_ok
                and smoke_ok and no_ok)

    result = {}

    def run():
        result["ok"] = exercise()

    app.root.after(700, run)
    app.root.after(18000, app.quit)
    app.run()
    print("贴边测试通过" if result.get("ok") else "贴边测试未通过")
    print("已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
