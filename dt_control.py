# -*- coding: utf-8 -*-
"""桌面收纳盒：设置视图（收纳面板里的「设置」页）。"""

from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import dt_config
import dt_organize
import dt_ui
import dt_winapi
from dt_ui import ACCENT, BG, BODY, CARD, CARD_HOVER, DANGER, DIM, TEXT, flat_button


class SettingsView:
    """面板里的设置页：分区管理、外观、系统开关、收纳目录。"""

    def __init__(self, app, parent: tk.Frame):
        self.app = app
        self.parent = parent
        self.inner: tk.Frame | None = None
        self.rows: list[tk.Frame] = []
        self._build()
        self.refresh()

    # ----------------------------------------------------------------- 构建
    def _build(self) -> None:
        app = self.app
        self.canvas, inner, _holder = dt_ui.make_scroll_area(self.parent)
        self.inner = inner

        quick = self._section(inner, "快速整理")
        row = tk.Frame(quick, bg=BG)
        row.pack(fill="x")
        flat_button(row, "一键整理桌面", app.organize_desktop,
                    bg="#3a6ea5", hover="#478099", font=app.font("ui")).pack(side="left")
        flat_button(row, "撤销上次整理", app.undo_organize, font=app.font("ui")).pack(side="left", padx=6)
        flat_button(row, "扫描预览", self.preview, font=app.font("ui")).pack(side="left")

        boxes = self._section(inner, "收纳分区")
        self.box_list = tk.Frame(boxes, bg=BG)
        self.box_list.pack(fill="x")
        actions = tk.Frame(boxes, bg=BG)
        actions.pack(fill="x", pady=(8, 0))
        flat_button(actions, "新建分区", self.add_box, font=app.font("ui")).pack(side="left")
        flat_button(actions, "全部展开", lambda: self.set_all_collapsed(False),
                    font=app.font("ui")).pack(side="left", padx=6)
        flat_button(actions, "全部折叠", lambda: self.set_all_collapsed(True),
                    font=app.font("ui")).pack(side="left")

        look = self._section(inner, "外观")
        self.icon_scale = self._scale(look, "图标大小", 26, 96, int(app.config.get("icon_size", 46)),
                                      self.on_icon_size)
        self.alpha_scale = self._scale(look, "面板透明度", 60, 100,
                                       int(float(app.config.get("panel", {}).get("alpha", 1.0)) * 100),
                                       self.on_alpha)
        self.topmost_var = tk.BooleanVar(value=bool(app.config.get("panel", {}).get("topmost")))
        self._check(look, "面板总在最前面", self.topmost_var, self.on_topmost)
        self.labels_var = tk.BooleanVar(value=bool(app.config.get("show_labels", True)))
        self._check(look, "显示文件名", self.labels_var, self.on_labels)
        self.dock_var = tk.BooleanVar(value=bool(app.config.get("panel", {}).get("docked")))
        self._check(look, "贴边自动隐藏（把面板拖到屏幕上边缘，鼠标碰到顶边就滑出来）",
                    self.dock_var, self.on_dock)

        desk = self._section(inner, "桌面")
        self.hide_icons_var = tk.BooleanVar(value=False)
        self._check(desk, "隐藏系统桌面图标（桌面上只留收纳面板）", self.hide_icons_var, self.on_hide_icons)
        self.autostart_var = tk.BooleanVar(value=bool(app.config.get("autostart")))
        self._check(desk, "开机自动启动", self.autostart_var, self.on_autostart)

        close_box = self._section(inner, "关闭按钮")
        tk.Label(close_box, text="点窗口右上角的 ×（或最小化按钮）时：", bg=BG, fg=DIM,
                 font=app.font("ui_small"), anchor="w").pack(anchor="w")
        self.close_var = tk.StringVar(value=str(app.config.get("close_action") or "tray"))
        self._radio(close_box, "隐藏到系统托盘（任务栏不会留下图标）", "tray",
                    self.close_var, self.on_close_action)
        self._radio(close_box, "直接退出程序", "exit",
                    self.close_var, self.on_close_action)

        folder = self._section(inner, "收纳目录")
        self.root_label = tk.Label(folder, text="", bg=BG, fg=DIM, font=app.font("ui_small"),
                                   wraplength=400, justify="left")
        self.root_label.pack(anchor="w")
        row = tk.Frame(folder, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        flat_button(row, "打开目录",
                    lambda: dt_winapi.shell_open(dt_config.resolve_root(app.config)),
                    font=app.font("ui")).pack(side="left")
        flat_button(row, "更换目录", self.change_root, font=app.font("ui")).pack(side="left", padx=6)
        flat_button(row, "配置文件", lambda: dt_winapi.shell_open(dt_config.appdata_dir()),
                    font=app.font("ui")).pack(side="left")

        help_box = self._section(inner, "规则说明")
        tk.Label(
            help_box,
            text=("· 分区按扩展名归类：文档 / 图片 / 视频 / 音频 / 压缩包 / 程序 / 快捷方式 / 其他\n"
                  "· 想自定义归类，可以改配置文件里的 rules 与 custom_rules\n"
                  "· 拖到面板顶部的空白处，会自动按类型分到对应分区\n"
                  "· 文件只是被移动到桌面下的子文件夹，不会删除"),
            bg=BG, fg=DIM, font=app.font("ui_small"), justify="left", wraplength=420,
        ).pack(anchor="w")

        about = self._section(inner, "关于")
        tk.Label(about, text=f"{dt_config.APP_NAME}  v{dt_config.APP_VERSION}",
                 bg=BG, fg=TEXT, font=app.font("ui")).pack(anchor="w", pady=(0, 4))
        info_rows = (
            ("作者", dt_config.APP_AUTHOR),
            ("开发工具", dt_config.APP_TOOL),
            ("版本日期", dt_config.APP_DATE),
            ("实现方式", dt_config.APP_TECH),
        )
        grid = tk.Frame(about, bg=BG)
        grid.pack(anchor="w")
        for row_index, (key, value) in enumerate(info_rows):
            tk.Label(grid, text=key, bg=BG, fg=DIM, font=app.font("ui_small"),
                     anchor="w").grid(row=row_index, column=0, sticky="w", pady=1)
            tk.Label(grid, text=value, bg=BG, fg=TEXT, font=app.font("ui_small"),
                     anchor="w", justify="left", wraplength=330).grid(
                row=row_index, column=1, sticky="w", padx=(12, 0), pady=1)

        buttons = tk.Frame(about, bg=BG)
        buttons.pack(anchor="w", pady=(8, 0))
        flat_button(buttons, "收起到托盘", lambda: app.hide_to_tray(),
                    font=app.font("ui")).pack(side="left")
        flat_button(buttons, "退出程序", app.quit_confirmed, bg="#4a3038", fg=DANGER, hover="#5b3a44",
                    font=app.font("ui")).pack(side="left", padx=6)

        self.status = tk.Label(inner, text="", bg=BG, fg=ACCENT, font=app.font("ui_small"), anchor="w")
        self.status.pack(fill="x", padx=2, pady=(12, 6))

    def _section(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(outer, text=title, bg=BG, fg=ACCENT, font=self.app.font("ui_section")).pack(anchor="w")
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="x", pady=(6, 0))
        return body

    def _scale(self, parent, label: str, lo: int, hi: int, value: int, command) -> tk.Scale:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text=label, bg=BG, fg=DIM, font=self.app.font("ui_small"),
                 width=10, anchor="w").pack(side="left")
        scale = tk.Scale(row, from_=lo, to=hi, orient="horizontal", bg=BG, fg=DIM,
                         troughcolor=CARD, highlightthickness=0, bd=0, sliderrelief="flat",
                         activebackground=ACCENT, font=self.app.font("ui_small"),
                         showvalue=True, length=230, command=command)
        scale.set(value)
        scale.pack(side="left", fill="x", expand=True)
        return scale

    def _check(self, parent, label: str, var: tk.BooleanVar, command) -> tk.Checkbutton:
        check = tk.Checkbutton(parent, text=label, variable=var, command=command, bg=BG, fg=TEXT,
                               activebackground=BG, activeforeground=TEXT, selectcolor=CARD,
                               highlightthickness=0, bd=0, anchor="w", font=self.app.font("ui_small"))
        check.pack(anchor="w", pady=2)
        return check

    def _radio(self, parent, label: str, value: str, var: tk.StringVar, command) -> tk.Radiobutton:
        radio = tk.Radiobutton(parent, text=label, value=value, variable=var, command=command,
                               bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT,
                               selectcolor=CARD, highlightthickness=0, bd=0, anchor="w",
                               font=self.app.font("ui_small"))
        radio.pack(anchor="w", pady=1)
        return radio

    # ----------------------------------------------------------------- 刷新
    def refresh(self) -> None:
        for row in self.rows:
            row.destroy()
        self.rows = []
        for index, box in enumerate(self.app.config["boxes"]):
            folder = dt_config.box_folder(self.app.config, box)
            try:
                count = sum(1 for _ in folder.iterdir())
            except OSError:
                count = 0
            self.rows.append(self._box_row(box, count, index))
        self.root_label.configure(text=str(dt_config.resolve_root(self.app.config)))
        visible = dt_winapi.desktop_icons_visible()
        if visible is not None:
            self.hide_icons_var.set(visible is False)
        self.autostart_var.set(bool(self.app.config.get("autostart")))
        self.dock_var.set(bool((self.app.config.get("panel") or {}).get("docked")))
        self.close_var.set(str(self.app.config.get("close_action") or "tray"))
        if self.inner is not None:
            dt_ui.attach_wheel(self.inner, self.canvas)  # 新建的控件也要能滚轮滚动

    def _box_row(self, box: dict, count: int, index: int) -> tk.Frame:
        app = self.app
        row = tk.Frame(self.box_list, bg=CARD)
        row.pack(fill="x", pady=2)

        tk.Label(row, text="●", bg=CARD, fg=box.get("color", "#2f333d"),
                 font=app.font("ui")).pack(side="left", padx=(8, 2))
        name = tk.Label(row, text=f"{box.get('name', '')}（{count}）", bg=CARD, fg=TEXT,
                        font=app.font("ui_small"), anchor="w")
        name.pack(side="left", padx=4, fill="x", expand=True)

        flat_button(row, "移除", lambda b=box: app.remove_box(b), bg=CARD, hover="#4a3038",
                    fg=DANGER, font=app.font("ui_tiny"), padx=7).pack(side="right", padx=(3, 7))
        flat_button(row, "改名", lambda b=box: app.rename_box(b), bg=CARD, hover="#39414f",
                    font=app.font("ui_tiny"), padx=7).pack(side="right", padx=3)
        flat_button(row, "↓", lambda b=box: app.move_box(b, 1), bg=CARD, hover="#39414f",
                    font=app.font("ui_tiny"), padx=5).pack(side="right", padx=1)
        flat_button(row, "↑", lambda b=box: app.move_box(b, -1), bg=CARD, hover="#39414f",
                    font=app.font("ui_tiny"), padx=5).pack(side="right", padx=1)
        return row

    def flash(self, message: str, ms: int = 6000) -> None:
        self.status.configure(text=message)
        self.parent.after(ms, lambda: self.status.configure(text=""))

    # ----------------------------------------------------------------- 操作
    def preview(self) -> None:
        plan = dt_organize.build_plan(self.app.config)
        if not plan:
            messagebox.showinfo("扫描预览", "桌面上没有需要整理的文件。", parent=self.parent)
            return
        lines = "\n".join(f"　{k}：{v} 个" for k, v in sorted(dt_organize.summarize(plan).items()))
        names = "\n".join(f"　{p.name}" for p, _d, _c in plan[:15])
        more = f"\n　…还有 {len(plan) - 15} 个" if len(plan) > 15 else ""
        messagebox.showinfo(
            "扫描预览",
            f"共 {len(plan)} 个文件会被收纳：\n\n{lines}\n\n文件列表：\n{names}{more}",
            parent=self.parent,
        )

    def add_box(self) -> None:
        name = simpledialog.askstring("新建分区", "分区名称（同时作为文件夹名）：", parent=self.parent)
        if not name or not name.strip():
            return
        name = name.strip()
        if any(b.get("name") == name for b in self.app.config["boxes"]):
            messagebox.showwarning("新建分区", "已经有同名分区了。", parent=self.parent)
            return
        index = len(self.app.config["boxes"])
        box = dt_config.make_box(name, name, index)
        self.app.config["boxes"].append(box)
        dt_config.ensure_folders(self.app.config)
        self.app.save()
        self.app.rebuild_sections()
        self.refresh()
        self.flash(f"已创建分区「{name}」")

    def set_all_collapsed(self, collapsed: bool) -> None:
        for box in self.app.config["boxes"]:
            box["collapsed"] = collapsed
        self.app.save()
        self.app.rebuild_sections()
        self.refresh()

    def on_icon_size(self, value) -> None:
        self.app.config["icon_size"] = int(float(value))
        self.app.refresh_sections(force=True)
        self.app.save()

    def on_alpha(self, value) -> None:
        self.app.config.setdefault("panel", {})["alpha"] = int(float(value)) / 100
        self.app.apply_panel_style()
        self.app.save()

    def on_topmost(self) -> None:
        value = bool(self.topmost_var.get())
        if not value and (self.app.config.get("panel") or {}).get("docked"):
            self.topmost_var.set(True)
            self.flash("贴边自动隐藏时面板需要保持最前，先取消贴边再改")
            return
        self.app.config.setdefault("panel", {})["topmost"] = value
        self.app.apply_panel_style()
        self.app.save()

    def on_dock(self) -> None:
        panel = getattr(self.app, "panel", None)
        if panel is None:
            return
        if self.dock_var.get():
            panel.dock_now()
            self.flash("已贴到屏幕上边缘，鼠标碰到屏幕顶边就会滑出来")
        else:
            panel.undock()
            self.flash("已取消贴边，面板回到原来的位置")

    def on_labels(self) -> None:
        self.app.config["show_labels"] = bool(self.labels_var.get())
        self.app.refresh_sections(force=True)
        self.app.save()

    def on_hide_icons(self) -> None:
        want_hidden = bool(self.hide_icons_var.get())
        ok = dt_winapi.set_desktop_icons_visible(not want_hidden)
        self.app.config["hide_desktop_icons"] = want_hidden
        self.app.save()
        if not ok:
            messagebox.showwarning("桌面图标", "没能切换桌面图标，请稍后再试。", parent=self.parent)
        self.flash("桌面图标已" + ("隐藏" if want_hidden else "显示"))

    def on_autostart(self) -> None:
        value = bool(self.autostart_var.get())
        ok = dt_winapi.set_autostart(value)
        self.app.config["autostart"] = value if ok else False
        self.app.save()
        if not ok:
            messagebox.showwarning("开机启动", "写入启动项失败，可能被安全软件拦截了。", parent=self.parent)
        else:
            self.flash("已" + ("开启" if value else "关闭") + "开机自动启动")

    def on_close_action(self) -> None:
        value = self.close_var.get()
        self.app.config["close_action"] = value
        self.app.save()
        self.flash("关闭按钮已设为：" + ("隐藏到系统托盘" if value == "tray" else "直接退出程序"))

    def change_root(self) -> None:
        folder = filedialog.askdirectory(title="选择新的收纳目录", parent=self.parent,
                                         initialdir=str(dt_config.resolve_root(self.app.config).parent))
        if not folder:
            return
        old_root = dt_config.resolve_root(self.app.config)
        new_root = Path(folder)
        if new_root == old_root:
            return
        move = messagebox.askyesno(
            "更换目录",
            f"新的收纳目录：\n{new_root}\n\n是否把现有分区里的文件一起搬过去？",
            parent=self.parent,
        )
        self.app.config["root"] = str(new_root)
        dt_config.ensure_folders(self.app.config)
        if move:
            moved = 0
            for box in self.app.config["boxes"]:
                target = dt_config.box_folder(self.app.config, box)
                source = old_root / str(box.get("name", ""))
                if not source.exists() or source == target:
                    continue
                for entry in list(source.iterdir()):
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(entry), str(dt_organize.unique_target(target, entry.name)))
                        moved += 1
                    except Exception:
                        continue
            self.flash(f"已搬家 {moved} 个文件到新目录")
        self.app.save()
        self.app.refresh_sections(force=True)
        self.refresh()
