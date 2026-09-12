# -*- coding: utf-8 -*-
"""桌面收纳盒：单窗口收纳面板。

所有分区集中在一个窗口里上下排列，窗口可缩放、分区可折叠，
因此桌面上只需要留这一个窗口。
"""

from __future__ import annotations

import ctypes
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import dt_config
import dt_organize
import dt_ui
import dt_winapi
from dt_control import SettingsView
from dt_ui import (ACCENT, BG, BODY, CARD, CARD_HOVER, DIM, TEXT, SlimScrollbar, attach_wheel,
                   flat_button)

MAX_ITEMS = 200
SEL_BG = "#3b5a80"
HOVER = "#2f3947"
SECTION_BORDER = "#333c49"
SLIVER = 6            # 隐藏时留在屏幕上的高度
DOCK_TRIGGER = 22     # 拖到离屏幕上边缘这么近就贴边
UNDOCK_DISTANCE = 70  # 往下拖这么多就取消贴边
REVEAL_POLL_MS = 140
HIDE_DELAY = 0.55     # 鼠标离开多久后自动收起


class OrganizerPanel(tk.Toplevel):
    """一个窗口装下所有收纳分区。"""

    def __init__(self, app, config: dict):
        super().__init__(app.root)
        self.app = app
        self.config = config
        self.panel_cfg = config.setdefault("panel", dt_config.default_panel())
        self.sections: dict[str, dict] = {}
        self.selected: set[str] = set()
        self.items: list[tuple[Path, tk.Frame]] = []
        self.views: dict[str, tk.Frame] = {}
        self.settings: SettingsView | None = None
        self._current_view = ""
        self._drop_hooks: list = []
        self._item_drag: dict | None = None
        self._ghost: tk.Toplevel | None = None
        self._hover_section: dict | None = None
        self._save_job = None
        self._relayout_job = None
        self._dock_anim = None
        self._docking = False
        self._dock_state = "expanded"
        self._away_since: float | None = None
        self._head_drag: tuple | None = None
        self._menu_open = False
        self._ready = False
        self._last_geometry = None

        self.title("桌面收纳盒")
        self.configure(bg=BG)
        self.minsize(380, 360)
        self._apply_geometry()
        self._dark_titlebar()

        self._build_head()
        self.view_host = tk.Frame(self, bg=BG)
        self.view_host.pack(fill="both", expand=True)
        self._build_organize_view()
        self._build_settings_view()
        self.rebuild_sections()
        self.show_view(self.panel_cfg.get("view", "organize"))
        self._sync_dock_button()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_configure)
        self.bind("<F5>", lambda _e: self.refresh_sections(force=True))
        self.bind("<Delete>", lambda _e: self.delete_selected())
        self._ready = True
        self.after(500, self._after_resize)  # 首次启动也记下位置尺寸
        if self.panel_cfg.get("docked"):
            self.after(320, self._enter_docked_state)
        self.after(300, self._install_drop)
        self._dock_job = self.after(REVEAL_POLL_MS, self._dock_tick)
        self._tick_job = self.after(2000, self._tick)

    # ------------------------------------------------------------- 窗口
    def _apply_geometry(self) -> None:
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        w = int(self.panel_cfg.get("w", 520))
        h = int(self.panel_cfg.get("h", 820))
        w = max(380, min(w, right - left))
        h = max(360, min(h, bottom - top))
        x = int(self.panel_cfg.get("x", right - w - 20))
        y = int(self.panel_cfg.get("y", top + 24))
        x = max(left, min(x, right - 120))
        y = max(top, min(y, bottom - 120))
        self.geometry(self._geom(x, y, w, h))
        self._fit_into_work_area()

    def _fit_into_work_area(self) -> None:
        """带标题栏的窗口外框会比客户区大，别让它超出工作区（小屏笔记本上尤其明显）。"""
        try:
            self.update_idletasks()
            left, top, right, bottom = dt_winapi.monitor_work_area(self)
            m = dt_winapi.window_metrics(self)
            if not m["fw"] or not m["fh"]:
                return
            # 优先压缩高度，尽量不动窗口位置（上移会被当成"拖到屏幕上边缘"）
            overflow = (m["fy"] + m["fh"]) - bottom
            if overflow > 0:
                new_client_h = max(320, m["ch"] - overflow)
                if new_client_h < m["ch"]:
                    self.geometry(self._geom(m["fx"], m["fy"], m["cw"], new_client_h))
                    self.update_idletasks()
                    m = dt_winapi.window_metrics(self)
            x = min(max(m["fx"], left), max(left, right - m["fw"]))
            y = min(max(m["fy"], top), max(top, bottom - m["fh"]))
            if (x, y) != (m["fx"], m["fy"]):
                dt_winapi.move_frame(self, x, y)
            self._dock_guard = time.time() + 1.5
        except Exception:
            pass

    def _dark_titlebar(self) -> None:
        try:
            hwnd = dt_winapi.window_frame_hwnd(self)
            dwm = ctypes.WinDLL("dwmapi")
            for attribute in (20, 19):
                value = ctypes.c_int(1)
                if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                             ctypes.sizeof(value)) == 0:
                    break
            corner = ctypes.c_int(2)  # DWMWCP_ROUND
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
        except Exception:
            pass

    def apply_style(self) -> None:
        dt_winapi.set_alpha(self, float(self.panel_cfg.get("alpha", 1.0)))
        self.attributes("-topmost", bool(self.panel_cfg.get("topmost")))

    def _geom(self, x: int, y: int, width: int | None = None, height: int | None = None) -> str:
        """拼窗口几何字符串，负坐标要写成 +x-y（+-954 这种写法 Tk 不认）。"""
        width = int(width or self.winfo_width())
        height = int(height or self.winfo_height())
        xs = f"+{x}" if x >= 0 else str(x)
        ys = f"+{y}" if y >= 0 else str(y)
        return f"{width}x{height}{xs}{ys}"

    def _on_configure(self, event) -> None:
        if not self._ready or event.widget is not self:
            return
        if self._relayout_job:
            try:
                self.after_cancel(self._relayout_job)
            except Exception:
                pass
        self._relayout_job = self.after(160, self._after_resize)

    def _after_resize(self) -> None:
        self._relayout_job = None
        self.layout_items()
        if self._docking:
            return
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        docked = bool(self.panel_cfg.get("docked"))
        metrics = dt_winapi.window_metrics(self)
        frame_y = metrics["fy"] if metrics["fy"] else self.winfo_y()
        if (not docked and frame_y <= top + DOCK_TRIGGER
                and time.time() > getattr(self, "_dock_guard", 0)):
            # 拖到屏幕上边缘 → 贴边并自动隐藏
            self.dock_top(metrics["fx"] or self.winfo_x(), metrics["cw"] or self.winfo_width())
            return
        if docked:
            if frame_y >= top + UNDOCK_DISTANCE:
                self.undock()
                return
            self.panel_cfg["dock_x"] = metrics["fx"] or self.winfo_x()
            self.panel_cfg["dock_w"] = metrics["cw"] or self.winfo_width()
            if self._save_job:
                try:
                    self.after_cancel(self._save_job)
                except Exception:
                    pass
            self._save_job = self.after(500, self.app.save)
            return
        size = (self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y())
        if size == self._last_geometry:
            return
        self._last_geometry = size
        self.panel_cfg["w"], self.panel_cfg["h"] = size[0], size[1]
        self.panel_cfg["x"], self.panel_cfg["y"] = size[2], size[3]
        if self._save_job:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.after(500, self.app.save)

    # ------------------------------------------------------------- 贴边自动隐藏
    def dock_top(self, x: int | None = None, width: int | None = None) -> None:
        """贴到屏幕上边缘并收起，只留一条边；鼠标碰到顶边再滑出来。"""
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        metrics = dt_winapi.window_metrics(self)
        if not self.panel_cfg.get("docked"):
            self.panel_cfg["pre_dock_y"] = metrics["fy"] or self.winfo_y()
        client_w = max(320, min(int(width or metrics["cw"] or self.winfo_width()), right - left))
        frame_x = int(x if x is not None else metrics["fx"])
        frame_x = max(left, min(frame_x, right - client_w))
        self.panel_cfg["docked"] = True
        self.panel_cfg["dock_edge"] = "top"
        self.panel_cfg["dock_x"] = frame_x
        self.panel_cfg["dock_w"] = client_w
        # 贴边时必须保持最前，否则会被最大化的窗口盖住，鼠标就碰不到它了
        self.panel_cfg["topmost"] = True
        self.attributes("-topmost", True)
        self._docking = True
        frame_w = metrics["fw"] + (client_w - metrics["cw"]) if metrics["fw"] else None
        dt_winapi.move_frame(self, frame_x, top, frame_w)
        self._dock_state = "expanded"
        self.after(110, self._animate_hide)
        self._sync_dock_button()
        self._away_since = None
        self.app.save()

    def undock(self) -> None:
        """取消贴边，回到原来的位置。"""
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        self.panel_cfg["docked"] = False
        y = int(self.panel_cfg.get("pre_dock_y", top + 24))
        y = max(top, min(y, bottom - 200))
        self._docking = True
        metrics = dt_winapi.window_metrics(self)
        x = metrics["fx"] or self.winfo_x()
        x = max(left, min(x, right - 160))  # 别停在屏幕外面
        dt_winapi.move_frame(self, x, y)
        self._docking = False
        self._dock_state = "expanded"
        self._away_since = None
        self._sync_dock_button()
        self.app.save()

    def reveal(self) -> None:
        self.reveal_and_hold(0.0)

    def reveal_and_hold(self, hold_seconds: float = 10.0) -> None:
        """把面板滑出来，并在接下来 hold_seconds 秒内不自动回缩。

        用于「托盘菜单选了显示面板」「双击启动.bat」这类显式请求：
        否则贴边模式下窗口刚滑出来，就会因为鼠标不在上面而立刻收回去。
        """
        if hold_seconds:
            self._dock_suspend_until = time.time() + hold_seconds
        if not self.panel_cfg.get("docked") or self._dock_state == "expanded":
            return
        self._docking = True
        self._animate_to(dt_winapi.monitor_work_area(self)[1], done=self._on_revealed)

    def _animate_hide(self) -> None:
        if not self.panel_cfg.get("docked"):
            self._docking = False
            return
        self._docking = True
        self._animate_to(self._hidden_frame_y(), done=self._on_hidden)

    def _hidden_frame_y(self) -> int:
        """收起后的窗口外框 y：在屏幕顶边只露出 SLIVER 像素的客户区。"""
        metrics = dt_winapi.window_metrics(self)
        top = dt_winapi.monitor_work_area(self)[1]
        client_h = metrics["ch"] or self.winfo_height()
        return top + SLIVER - client_h - metrics["top_border"]

    def _animate_to(self, target_y: int, steps: int = 7, done=None) -> None:
        if self._dock_anim:
            try:
                self.after_cancel(self._dock_anim)
            except Exception:
                pass
            self._dock_anim = None
        metrics = dt_winapi.window_metrics(self)
        start = metrics["fy"] or self.winfo_y()
        x = metrics["fx"] or self.winfo_x()

        def finish() -> None:
            dt_winapi.move_frame(self, x, target_y)
            self._dock_anim = None
            self._docking = False
            if done:
                done()

        if abs(target_y - start) < 3:
            finish()
            return

        def step(index: int) -> None:
            y = start + int((target_y - start) * index / steps)
            dt_winapi.move_frame(self, x, y)
            if index < steps:
                self._dock_anim = self.after(16, lambda: step(index + 1))
            else:
                finish()

        step(1)

    def _on_hidden(self) -> None:
        self._dock_state = "hidden"
        self._log_dock("已收起为顶部细边")

    def _on_revealed(self) -> None:
        self._dock_state = "expanded"
        self._away_since = None
        self._log_dock("已滑出展开")

    def _enter_docked_state(self) -> None:
        """启动时如果上次是贴边状态，直接摆到顶边并收起。"""
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        metrics = dt_winapi.window_metrics(self)
        client_w = max(320, min(int(self.panel_cfg.get("dock_w", metrics["cw"] or 520)), right - left))
        frame_x = max(left, min(int(self.panel_cfg.get("dock_x", metrics["fx"])), right - client_w))
        self._docking = True
        self.update_idletasks()
        frame_w = metrics["fw"] + (client_w - metrics["cw"]) if metrics["fw"] else None
        dt_winapi.move_frame(self, frame_x, self._hidden_frame_y(), frame_w)
        self._docking = False
        self._dock_state = "hidden"
        self.attributes("-topmost", True)
        self._sync_dock_button()

    def _dock_span(self) -> tuple[int, int]:
        metrics = dt_winapi.window_metrics(self)
        if metrics["fw"]:
            return metrics["fx"], metrics["fx"] + metrics["fw"]
        x = int(self.panel_cfg.get("dock_x", self.winfo_x()))
        return x, x + int(self.panel_cfg.get("dock_w", self.winfo_width()))

    def _dock_busy(self) -> bool:
        """有菜单/对话框/拖拽在进行时，不要自动收起。"""
        if self._menu_open or self._item_drag or self._head_drag or self._ghost is not None:
            return True
        try:
            return self.grab_current() is not None
        except Exception:
            return False

    def _dock_tick(self) -> None:
        if not self.winfo_exists():
            return
        try:
            # 动画卡住时自愈：正常情况下贴边动画不到 0.3 秒就该结束
            if self._docking:
                if not getattr(self, "_docking_since", 0.0):
                    self._docking_since = time.time()
                elif time.time() - self._docking_since > 3.0:
                    self._docking = False
                    self._dock_anim = None
                    self._docking_since = 0.0
                    self._log_dock("贴边动画超时，已强制复位")
            else:
                self._docking_since = 0.0
            if self.panel_cfg.get("docked") and not self._docking and self.winfo_viewable():
                self._check_dock_mouse()
        except Exception:
            pass
        self._dock_job = self.after(REVEAL_POLL_MS, self._dock_tick)

    def _log_dock(self, message: str) -> None:
        try:
            self.app.log_event("贴边：" + message)
        except Exception:
            pass

    def finish_peek(self) -> None:
        """启动提示结束后的收尾：到点就按设置收回去（鼠标在面板上才保持展开）。

        不依赖鼠标"离开事件"——之前就是这里不够确定，导致开机后一直摊着不收起。
        """
        self._dock_suspend_until = 0.0
        if not self.panel_cfg.get("docked"):
            return
        try:
            x, y = dt_winapi.cursor_pos()
            m = dt_winapi.window_metrics(self)
            inside = (m["fx"] - 2 <= x <= m["fx"] + m["fw"] + 2
                      and m["fy"] - 2 <= y <= m["fy"] + m["fh"] + 2)
        except Exception:
            inside = False
        if inside:
            self._log_dock("启动提示结束：鼠标停在面板上，保持展开")
            return
        self._log_dock(f"启动提示结束：收起（原状态={self._dock_state}）")
        self._dock_state = "expanded"  # 保证下面的收起逻辑一定生效
        self._docking = True
        self._animate_hide()

    def _check_dock_mouse(self) -> None:
        import time

        x, y = dt_winapi.cursor_pos()
        if x < 0:
            return
        _left, top, _right, _bottom = dt_winapi.monitor_work_area(self)
        x0, x1 = self._dock_span()
        if self._dock_state == "hidden":
            if top - 2 <= y <= top + SLIVER + 4 and x0 - 6 <= x <= x1 + 6:
                self.reveal()
            return
        if time.time() < getattr(self, "_dock_suspend_until", 0):
            self._away_since = None  # 显式显示期间不自动回缩
            return
        metrics = dt_winapi.window_metrics(self)
        inside = (metrics["fx"] - 2 <= x <= metrics["fx"] + metrics["fw"] + 2
                  and metrics["fy"] - 2 <= y <= metrics["fy"] + metrics["fh"] + 2)
        if inside or self._dock_busy():
            self._away_since = None
            return
        if self._away_since is None:
            self._away_since = time.time()
        elif time.time() - self._away_since >= HIDE_DELAY:
            self._away_since = None
            self._log_dock("鼠标已离开，自动收起")
            self._animate_hide()

    def _sync_dock_button(self) -> None:
        button = getattr(self, "dock_button", None)
        if button is None:
            return
        try:
            button.configure(text="取消贴边" if self.panel_cfg.get("docked") else "贴边隐藏")
        except Exception:
            pass

    def toggle_dock(self) -> None:
        if self.panel_cfg.get("docked"):
            self.undock()
        else:
            self.dock_now()

    def dock_now(self) -> None:
        """按当前实际位置贴到屏幕上边缘。"""
        metrics = dt_winapi.window_metrics(self)
        self.dock_top(metrics["fx"] or self.winfo_x(), metrics["cw"] or self.winfo_width())

    # ------------------------------------------------------------- 顶部拖动
    def _head_press(self, event) -> None:
        metrics = dt_winapi.window_metrics(self)
        self._head_drag = (event.x_root - (metrics["fx"] or self.winfo_x()),
                           event.y_root - (metrics["fy"] or self.winfo_y()))
        self._docking = True

    def _head_motion(self, event) -> None:
        if not self._head_drag:
            return
        x = event.x_root - self._head_drag[0]
        y = event.y_root - self._head_drag[1]
        dt_winapi.move_frame(self, x, y)

    def _head_release(self, _event) -> None:
        if not self._head_drag:
            return
        self._head_drag = None
        self._docking = False
        left, top, right, bottom = dt_winapi.monitor_work_area(self)
        metrics = dt_winapi.window_metrics(self)
        if metrics["fy"] <= top + DOCK_TRIGGER:
            self.dock_top(metrics["fx"], metrics["cw"])
            return
        if self.panel_cfg.get("docked") and metrics["fy"] >= top + UNDOCK_DISTANCE:
            self.undock()
            return
        if self.panel_cfg.get("docked"):
            self.panel_cfg["dock_x"] = metrics["fx"]
            self._dock_state = "expanded"
            self.app.save()
            return
        self._after_resize()

    # ------------------------------------------------------------- 顶部
    def _build_head(self) -> None:
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 0))

        left = tk.Frame(head, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        self.title_label = tk.Label(left, text="桌面收纳盒", bg=BG, fg=TEXT,
                                    font=self.app.font("ui_title"), cursor="fleur")
        self.title_label.pack(anchor="w")
        self.summary = tk.Label(left, text="", bg=BG, fg=DIM, font=self.app.font("ui_small"))
        self.summary.pack(anchor="w", pady=(1, 0))

        # 顶部这片区域是拖动把手：拖到屏幕上边缘就会贴边隐藏
        for widget in (head, left, self.title_label, self.summary):
            widget.bind("<Button-1>", self._head_press)
            widget.bind("<B1-Motion>", self._head_motion)
            widget.bind("<ButtonRelease-1>", self._head_release)
        self.app.bind_tip(self.title_label, "拖动这里可以贴到屏幕上边缘自动隐藏")

        seg = tk.Frame(head, bg=CARD)
        seg.pack(side="right", pady=2)
        self.view_buttons: dict[str, tk.Label] = {}
        for key, label in (("organize", "收纳"), ("settings", "设置")):
            button = tk.Label(seg, text=label, bg=CARD, fg=DIM, font=self.app.font("ui_small"),
                              padx=16, pady=6, cursor="hand2")
            button.pack(side="left")
            button.bind("<Button-1>", lambda _e, k=key: self.show_view(k))
            self.view_buttons[key] = button

    def show_view(self, key: str) -> None:
        if key not in self.views:
            key = "organize"
        for name, frame in self.views.items():
            if name == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for name, button in self.view_buttons.items():
            active = name == key
            button.configure(bg="#3a6ea5" if active else CARD, fg="#ffffff" if active else DIM)
        self._current_view = key
        if self.panel_cfg.get("view") != key:
            self.panel_cfg["view"] = key
            self.app.save()
        if key == "organize":
            self.refresh_sections(force=True)
        elif self.settings is not None:
            self.settings.refresh()

    # ------------------------------------------------------------- 收纳视图
    def _build_organize_view(self) -> None:
        view = tk.Frame(self.view_host, bg=BG)
        self.views["organize"] = view

        bar = tk.Frame(view, bg=BG)
        bar.pack(fill="x", padx=14, pady=(10, 6))
        flat_button(bar, "一键整理桌面", self.app.organize_desktop,
                    bg="#3a6ea5", hover="#478099", font=self.app.font("ui")).pack(side="left")
        flat_button(bar, "撤销", self.app.undo_organize, font=self.app.font("ui")).pack(side="left", padx=5)
        flat_button(bar, "添加文件", self.add_files, font=self.app.font("ui")).pack(side="left")
        flat_button(bar, "折叠全部", self.toggle_all, font=self.app.font("ui")).pack(side="right")
        self.dock_button = flat_button(bar, "贴边隐藏", self.toggle_dock, font=self.app.font("ui"))
        self.dock_button.pack(side="right", padx=(0, 6))

        body = tk.Frame(view, bg=BG)
        body.pack(fill="both", expand=True, padx=(12, 4), pady=(0, 10))

        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = SlimScrollbar(body, self.canvas.yview, bg=BG)
        self.scrollbar.pack(side="right", fill="y", padx=(3, 1))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.configure(yscrollincrement=dt_ui.WHEEL_STEP_HINT)
        self.canvas.bar = self.scrollbar

        self.sections_host = tk.Frame(self.canvas, bg=BG)
        self._host_window = self.canvas.create_window((0, 0), window=self.sections_host, anchor="nw")
        self.sections_host.bind("<Configure>", self._on_host_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", lambda _e: self.clear_selection())

        self.hint_bar = tk.Label(view, text="", bg=BG, fg=ACCENT, font=self.app.font("ui_small"),
                                 anchor="w", padx=14)

    def _on_host_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._host_window, width=event.width)

    def flash(self, message: str, ms: int = 6000) -> None:
        self.hint_bar.configure(text=message)
        self.hint_bar.pack(fill="x", pady=(0, 6))
        self.after(ms, self._clear_hint)

    def _clear_hint(self) -> None:
        try:
            self.hint_bar.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------- 分区
    def rebuild_sections(self) -> None:
        for child in self.sections_host.winfo_children():
            child.destroy()
        self.sections = {}
        self.items = []
        for box in self.config["boxes"]:
            self._create_section(box)
        self.layout_items()
        attach_wheel(self.sections_host, self.canvas)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.update_summary()

    def _create_section(self, box: dict) -> None:
        app = self.app
        collapsed = bool(box.get("collapsed"))
        card = tk.Frame(self.sections_host, bg=CARD, highlightthickness=1,
                        highlightbackground=SECTION_BORDER)
        card.pack(fill="x", pady=4)

        header = tk.Frame(card, bg=CARD)
        header.pack(fill="x")
        arrow = tk.Label(header, text="▸" if collapsed else "▾", bg=CARD, fg=DIM,
                         font=app.font("ui_small"), width=2, cursor="hand2")
        arrow.pack(side="left", padx=(4, 0), pady=4)
        dot = tk.Label(header, text="●", bg=CARD, fg=box.get("color", "#2f333d"), font=app.font("ui"))
        dot.pack(side="left")
        name_label = tk.Label(header, text=box.get("name", ""), bg=CARD, fg=TEXT,
                              font=app.font("ui_section"), anchor="w")
        name_label.pack(side="left", padx=(3, 0))
        count_label = tk.Label(header, text="", bg=CARD, fg=DIM, font=app.font("ui_small"))
        count_label.pack(side="left", padx=6)

        buttons = (
            ("⋯", lambda b=box: self.section_menu(b), "更多操作"),
            ("＋", lambda b=box: self.add_files(b), "添加文件到本分区"),
            ("夹", lambda b=box: dt_winapi.shell_open(dt_config.box_folder(self.config, b)),
             "打开这个分区的文件夹"),
        )
        for text, command, tip in buttons:
            button = tk.Label(header, text=text, bg=CARD, fg=DIM, font=app.font("ui_small"),
                              width=2, cursor="hand2")
            button.pack(side="right", padx=(0, 3))
            button.bind("<Button-1>", lambda _e, c=command: c())
            button.bind("<Enter>", lambda e: e.widget.configure(fg=TEXT, bg=CARD_HOVER))
            button.bind("<Leave>", lambda e: e.widget.configure(fg=DIM, bg=CARD))
            self.app.bind_tip(button, tip)

        body = tk.Frame(card, bg=BODY)
        if not collapsed:
            body.pack(fill="x", padx=8, pady=(0, 8))

        section = {
            "box": box,
            "card": card,
            "header": header,
            "body": body,
            "arrow": arrow,
            "dot": dot,
            "count": count_label,
            "items": [],
            "sig": (),
        }
        self.sections[box["id"]] = section

        for widget in (header, arrow, dot, name_label, count_label):
            widget.bind("<Button-1>", lambda _e, b=box: self.toggle_section(b))
            widget.bind("<Button-3>", lambda _e, b=box: self.section_menu(b))
        header.bind("<Enter>", lambda _e, s=section: self._hover_header(s, True))
        header.bind("<Leave>", lambda _e, s=section: self._hover_header(s, False))
        self.refresh_section(section, force=True)

    def _hover_header(self, section: dict, entering: bool) -> None:
        color = CARD_HOVER if entering else CARD
        try:
            section["header"].configure(bg=color)
            for child in section["header"].winfo_children():
                child.configure(bg=color)
        except Exception:
            pass

    def toggle_section(self, box: dict) -> None:
        box["collapsed"] = not bool(box.get("collapsed"))
        section = self.sections.get(box["id"])
        if section is None:
            return
        if box["collapsed"]:
            section["body"].pack_forget()
            section["arrow"].configure(text="▸")
        else:
            section["body"].pack(fill="x", padx=8, pady=(0, 8))
            section["arrow"].configure(text="▾")
            self.refresh_section(section, force=True)
        self.app.save()

    def toggle_all(self) -> None:
        collapse = not all(bool(b.get("collapsed")) for b in self.config["boxes"])
        for box in self.config["boxes"]:
            box["collapsed"] = collapse
        self.rebuild_sections()
        self.app.save()

    def update_summary(self) -> None:
        total = sum(len(s["items"]) for s in self.sections.values())
        self.summary.configure(text=f"{len(self.config['boxes'])} 个分区 · 共 {total} 个文件")

    # ------------------------------------------------------------- 分区内容
    def _signature(self, entries: list[Path]) -> tuple:
        sig = []
        for path in entries:
            try:
                sig.append((path.name, int(path.stat().st_mtime), path.is_dir()))
            except OSError:
                sig.append((path.name, 0, False))
        return tuple(sig)

    def folder_entries(self, box: dict) -> list[Path]:
        folder = dt_config.box_folder(self.config, box)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            entries = list(folder.iterdir())
        except OSError:
            return []
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        return entries

    def refresh_section(self, section: dict, force: bool = False) -> None:
        entries = self.folder_entries(section["box"])
        sig = self._signature(entries[:MAX_ITEMS])
        if not force and sig == section["sig"]:
            return
        section["sig"] = sig
        body = section["body"]
        for child in body.winfo_children():
            child.destroy()
        section["items"] = []

        if not entries:
            hint = tk.Label(body, text="把文件拖到这里", bg=BODY, fg="#6d7784",
                            font=self.app.font("ui_small"), anchor="w")
            hint.pack(fill="x", padx=6, pady=10)
        else:
            for path in entries[:MAX_ITEMS]:
                self._make_item(section, path)
            if len(entries) > MAX_ITEMS:
                tk.Label(body, text=f"…还有 {len(entries) - MAX_ITEMS} 个文件，点「夹」打开文件夹查看",
                         bg=BODY, fg="#6d7784", font=self.app.font("ui_small"),
                         anchor="w").pack(fill="x", padx=6, pady=(4, 0))

        section["count"].configure(text=f"（{len(entries)}）")
        attach_wheel(body, self.canvas)
        self.layout_section(section)
        self.update_summary()

    def refresh_sections(self, force: bool = False) -> None:
        for section in list(self.sections.values()):
            if section["box"].get("collapsed") and not force:
                continue
            self.refresh_section(section, force=force)
        self.update_summary()

    def _make_item(self, section: dict, path: Path) -> None:
        body = section["body"]
        size = int(self.config.get("icon_size", 46))
        item_w = size + 26
        selected = str(path) in self.selected
        bg = SEL_BG if selected else BODY
        show_label = bool(self.config.get("show_labels", True))
        frame = tk.Frame(body, bg=bg, width=item_w, height=size + (44 if show_label else 20))
        frame.pack_propagate(False)

        photo = self.app.photo(path, size)
        if photo is not None:
            icon = tk.Label(frame, image=photo, bg=bg, bd=0)
            icon.image = photo  # type: ignore[attr-defined]
        else:
            icon = tk.Label(frame, text=(path.suffix[1:5] or "文件").upper(), bg=bg, fg=TEXT,
                            font=self.app.font("fallback"), width=7, height=3)
        icon.pack(pady=(6 if show_label else 2, 0))

        widgets = [frame, icon]
        if show_label:
            name = path.name
            display = name if len(name) <= 20 else name[:10] + "…" + name[-7:]
            label = tk.Label(frame, text=display, bg=bg, fg=TEXT if selected else DIM,
                             font=self.app.font("item"), wraplength=item_w - 4, justify="center")
            label.pack(fill="x", padx=1)
            widgets.append(label)

        for widget in widgets:
            widget.bind("<Button-1>", lambda e, p=path: self._on_item_press(e, p))
            widget.bind("<B1-Motion>", self._on_item_motion)
            widget.bind("<ButtonRelease-1>", lambda e, p=path: self._on_item_release(e, p))
            widget.bind("<Double-Button-1>", lambda _e, p=path: dt_winapi.shell_open(p))
            widget.bind("<Button-3>", lambda e, p=path: self.item_menu(e, p))
            widget.bind("<Enter>", lambda _e, f=frame, p=path: self._hover_item(f, p, True))
            widget.bind("<Leave>", lambda _e, f=frame, p=path: self._hover_item(f, p, False))
        section["items"].append((path, frame))
        self.items.append((path, frame))

    def _hover_item(self, frame: tk.Frame, path: Path, entering: bool) -> None:
        if str(path) in self.selected:
            return
        bg = HOVER if entering else BODY
        try:
            frame.configure(bg=bg)
            for child in frame.winfo_children():
                child.configure(bg=bg)
        except Exception:
            pass

    def layout_items(self) -> None:
        for section in self.sections.values():
            self.layout_section(section)

    def layout_section(self, section: dict) -> None:
        items = section["items"]
        if not items:
            return
        body = section["body"]
        width = body.winfo_width()
        if width <= 1:
            width = max(200, self.canvas.winfo_width() - 40)
        cell = int(self.config.get("icon_size", 46)) + 26 + 6
        cols = max(1, (width - 8) // cell)
        for index, (_path, frame) in enumerate(items):
            frame.grid(row=index // cols, column=index % cols, padx=2, pady=3, sticky="n")
        for col in range(cols):
            body.grid_columnconfigure(col, weight=0)

    # ------------------------------------------------------------- 选择
    def clear_selection(self) -> None:
        if not self.selected:
            return
        self.selected.clear()
        self.refresh_sections(force=True)

    def select(self, path: Path, additive: bool) -> None:
        if not additive:
            self.selected.clear()
        self.selected.add(str(path))
        self.refresh_sections(force=True)

    def delete_selected(self) -> None:
        if self.selected:
            self.app.delete_items([Path(p) for p in sorted(self.selected)])

    # ------------------------------------------------------------- 拖动
    def _on_item_press(self, event, path: Path) -> None:
        additive = bool(event.state & 0x0004)
        if str(path) not in self.selected:
            self.select(path, additive)
        self._item_drag = {"path": path, "x": event.x_root, "y": event.y_root, "moved": False}

    def _on_item_motion(self, event) -> None:
        drag = self._item_drag
        if not drag:
            return
        if not drag["moved"]:
            if abs(event.x_root - drag["x"]) < 5 and abs(event.y_root - drag["y"]) < 5:
                return
            drag["moved"] = True
            self._make_ghost(drag["path"])
        if self._ghost is not None:
            self._ghost.geometry(f"+{event.x_root + 14}+{event.y_root + 14}")
        target = self.section_at(event.x_root, event.y_root)
        if target is not self._hover_section:
            if self._hover_section is not None:
                self._set_section_highlight(self._hover_section, False)
            self._hover_section = target
            if target is not None:
                self._set_section_highlight(target, True)

    def _on_item_release(self, event, path: Path) -> None:
        drag = self._item_drag
        self._item_drag = None
        if drag and drag["moved"]:
            target = self.section_at(event.x_root, event.y_root)
            if self._hover_section is not None:
                self._set_section_highlight(self._hover_section, False)
            self._hover_section = None
            if target is not None and target["box"]["id"] != self._section_of(path):
                paths = [Path(p) for p in sorted(self.selected)] or [path]
                self.app.move_paths_into(paths, target["box"])
        self._destroy_ghost()

    def _section_of(self, path: Path) -> str:
        for box_id, section in self.sections.items():
            if any(p == path for p, _f in section["items"]):
                return box_id
        return ""

    def _make_ghost(self, path: Path) -> None:
        self._destroy_ghost()
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        ghost.attributes("-alpha", 0.92)
        tk.Label(ghost, text=f"移动到分区：{path.name[:18]}", bg="#2b3440", fg=TEXT,
                 font=self.app.font("ghost"), padx=10, pady=4).pack()
        self._ghost = ghost

    def _destroy_ghost(self) -> None:
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except Exception:
                pass
            self._ghost = None

    def _set_section_highlight(self, section: dict, on: bool) -> None:
        try:
            section["card"].configure(highlightbackground=ACCENT if on else SECTION_BORDER)
        except Exception:
            pass

    def section_at(self, x: int, y: int) -> dict | None:
        for section in self.sections.values():
            card = section["card"]
            try:
                if not card.winfo_exists():
                    continue
                cx, cy = card.winfo_rootx(), card.winfo_rooty()
                cw, ch = card.winfo_width(), card.winfo_height()
            except Exception:
                continue
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return section
        return None

    # ------------------------------------------------------------- 拖入
    def _install_drop(self) -> None:
        try:
            self.update_idletasks()
            self._drop_hooks = dt_winapi.enable_file_drop(self, self._on_external_drop)
        except Exception:
            self._drop_hooks = []

    def _on_external_drop(self, paths: list[str]) -> None:
        self.clear_selection()
        try:
            x, y = self.winfo_pointerxy()
            section = self.section_at(x, y)
        except Exception:
            section = None
        if section is not None:
            self._on_external_drop_for(paths, section["box"])
        else:
            self._auto_classify(paths)
        self.refresh_sections(force=True)

    def _auto_classify(self, paths: list[str]) -> None:
        rules = dt_config.all_rules(self.config)
        buckets: dict[str, int] = {}
        errors: list[str] = []
        for raw in paths:
            path = Path(raw)
            if not path.exists():
                errors.append(f"{path.name} 不存在")
                continue
            category = dt_organize.category_for(path, rules)
            box = next((b for b in self.config["boxes"] if b.get("name") == category), None)
            folder = (dt_config.box_folder(self.config, box) if box
                      else dt_config.resolve_root(self.config) / category)
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            moved, move_errors = dt_organize.move_into([str(path)], folder)
            if moved:
                buckets[category] = buckets.get(category, 0) + len(moved)
            errors.extend(move_errors)
        if buckets:
            detail = "、".join(f"{k} {v} 个" for k, v in buckets.items())
            self.flash(f"已按类型收纳：{detail}")
        elif errors:
            self.flash(errors[0][:60])
        else:
            self.flash("没有可以收纳的文件")

    def _on_external_drop_for(self, paths: list[str], box: dict) -> None:
        moved, errors = dt_organize.move_into(paths, dt_config.box_folder(self.config, box))
        if moved:
            self.flash(f"已把 {len(moved)} 个文件收进「{box.get('name', '')}」")
        elif errors:
            self.flash(errors[0][:60])

    def add_files(self, box: dict | None = None) -> None:
        files = filedialog.askopenfilenames(title="选择要收纳的文件", parent=self)
        if not files:
            return
        if box is None:
            self._auto_classify(list(files))
        else:
            self._on_external_drop_for(list(files), box)
        self.refresh_sections(force=True)

    # ------------------------------------------------------------- 菜单
    def _menu(self) -> tk.Menu:
        return tk.Menu(self, tearoff=0, bg="#242a33", fg=TEXT, activebackground="#3d4b5e",
                       activeforeground="#ffffff", bd=0, font=self.app.font("menu"))

    def section_menu(self, box: dict) -> None:
        menu = self._menu()
        folder = dt_config.box_folder(self.config, box)
        menu.add_command(label=f"打开「{box.get('name', '')}」文件夹",
                         command=lambda: dt_winapi.shell_open(folder))
        menu.add_command(label="添加文件到这里…", command=lambda: self.add_files(box))
        menu.add_command(label="把桌面上同类文件都收进来", command=lambda: self.collect_same_kind(box))
        menu.add_separator()
        menu.add_command(label="重命名分区", command=lambda: self.app.rename_box(box))
        colors = self._menu()
        for color in dt_config.PALETTE:
            colors.add_command(label="●  " + color, foreground=color,
                               command=lambda c=color: self.set_box_color(box, c))
        menu.add_cascade(label="换个颜色", menu=colors)
        menu.add_command(label="折叠 / 展开", command=lambda: self.toggle_section(box))
        menu.add_separator()
        menu.add_command(label="清空分区（移回桌面）", command=lambda: self.empty_section(box))
        menu.add_command(label="从列表移除这个分区", command=lambda: self.app.remove_box(box))
        menu.add_separator()
        menu.add_command(label="贴边自动隐藏" if not self.panel_cfg.get("docked") else "取消贴边",
                         command=self.toggle_dock)
        self._popup(menu, self.winfo_pointerx(), self.winfo_pointery())

    def _popup(self, menu: tk.Menu, x: int, y: int) -> None:
        """弹菜单期间不要自动收起面板。"""
        self._menu_open = True
        try:
            menu.tk_popup(x, y)
        finally:
            self._menu_open = False
            menu.grab_release()

    def item_menu(self, event, path: Path) -> None:
        if str(path) not in self.selected:
            self.select(path, additive=False)
        targets = [Path(p) for p in sorted(self.selected)] or [path]
        menu = self._menu()
        head = path.name if len(path.name) <= 26 else path.name[:24] + "…"
        menu.add_command(label=head, state="disabled")
        menu.add_separator()
        menu.add_command(label="打开", command=lambda: [dt_winapi.shell_open(p) for p in targets])
        menu.add_command(label="打开所在文件夹",
                         command=lambda: dt_winapi.reveal_in_explorer(targets[0]))
        others = [b for b in self.config["boxes"] if b["id"] != self._section_of(path)]
        if others:
            sub = self._menu()
            for box in others:
                sub.add_command(label=box.get("name", ""),
                                command=lambda b=box: self.app.move_paths_into(targets, b))
            menu.add_cascade(label=f"移到其他分区（{len(targets)} 项）", menu=sub)
        menu.add_command(label=f"移回桌面（{len(targets)} 项）",
                         command=lambda: self.app.move_to_desktop(targets))
        menu.add_separator()
        menu.add_command(label="重命名", command=lambda: self.rename_item(targets[0]))
        menu.add_command(label="删除到回收站", command=lambda: self.app.delete_items(targets))
        self._popup(menu, event.x_root, event.y_root)

    # ------------------------------------------------------------- 操作
    def collect_same_kind(self, box: dict) -> None:
        rules = dt_config.all_rules(self.config)
        name = box.get("name", "")
        targets = [p for p in dt_organize.desktop_entries(self.config)
                   if dt_organize.category_for(p, rules) == name]
        if not targets:
            self.flash(f"桌面上没有「{name}」类型的文件")
            return
        moved, _errors = dt_organize.move_into([str(p) for p in targets],
                                               dt_config.box_folder(self.config, box))
        self.refresh_sections(force=True)
        self.flash(f"已把桌面 {len(moved)} 个「{name}」文件收进来")

    def empty_section(self, box: dict) -> None:
        entries = self.folder_entries(box)
        if not entries:
            self.flash("这个分区是空的")
            return
        if not messagebox.askyesno("清空分区",
                                   f"把「{box.get('name', '')}」里的 {len(entries)} 项移回桌面？",
                                   parent=self):
            return
        done = 0
        for path in entries:
            if dt_organize.move_to_desktop(path):
                done += 1
        self.refresh_sections(force=True)
        self.flash(f"已把 {done} 项移回桌面")

    def set_box_color(self, box: dict, color: str) -> None:
        box["color"] = color
        self.app.save()
        section = self.sections.get(box["id"])
        if section is not None:
            try:
                section["dot"].configure(fg=color)
            except Exception:
                pass

    def rename_item(self, path: Path) -> None:
        new = simpledialog.askstring("重命名", "新文件名（不含扩展名）：",
                                     initialvalue=path.stem, parent=self)
        if not new or new == path.stem:
            return
        target = path.with_name(new + path.suffix)
        try:
            path.rename(target)
            self.selected = {str(target)}
        except OSError as exc:
            messagebox.showwarning("重命名", f"失败：{exc}", parent=self)
        self.refresh_sections(force=True)

    # ------------------------------------------------------------- 轮询
    def _build_settings_view(self) -> None:
        view = tk.Frame(self.view_host, bg=BG)
        self.views["settings"] = view
        self.settings = SettingsView(self.app, view)

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        try:
            if self._current_view == "organize":
                self.refresh_sections()
        except Exception:
            pass
        self._tick_job = self.after(2500, self._tick)

    def close(self) -> None:
        dt_winapi.release_drops(self._drop_hooks)
        self._destroy_ghost()
        for job in ("_dock_job", "_tick_job", "_save_job", "_relayout_job"):
            handle = getattr(self, job, None)
            if handle:
                try:
                    self.after_cancel(handle)
                except Exception:
                    pass
                setattr(self, job, None)
        try:
            self.destroy()
        except Exception:
            pass

    def _on_close(self) -> None:
        """点窗口关闭按钮时的行为，由设置里的「关闭按钮」决定。"""
        action = self.config.get("close_action") or "tray"
        try:
            self.app.log_event(f"收到关闭请求（close_action={action}）")
        except Exception:
            pass
        if action == "exit":
            self.app.quit()
        else:
            self.app.hide_to_tray()
