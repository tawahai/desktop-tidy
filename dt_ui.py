# -*- coding: utf-8 -*-
"""桌面收纳盒：界面公共件（配色、按钮、细滚动条、滚轮支持）。"""

from __future__ import annotations

import tkinter as tk

import dt_winapi

BG = "#1b2027"
CARD = "#272e38"
CARD_HOVER = "#313947"
BODY = "#161a20"
TEXT = "#e9ecf1"
DIM = "#98a2ae"
ACCENT = "#7fb0e0"
DANGER = "#e08a8a"

TRACK = "#12161c"
THUMB = "#5d6b7d"
THUMB_HOVER = "#8ba0b8"

WHEEL_TAG = "DesktopTidyWheel"
WHEEL_STEP_HINT = 40  # 一格滚轮滚 40 像素


def flat_button(parent, text, command, *, bg: str = "#39414f", fg: str = TEXT,
                hover: str = CARD_HOVER, font=None, padx: int = 10, pady: int = 5) -> tk.Button:
    btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                    activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                    highlightthickness=0, padx=padx, pady=pady, cursor="hand2", font=font)
    btn.bind("<Enter>", lambda _e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
    return btn


class SlimScrollbar(tk.Canvas):
    """细滚动条：可拖动滑块、点空白翻页、悬停变亮，接口与 Tk 滚动条一致。"""

    def __init__(self, master, command, bg: str = BG, width: int = 12, **kw):
        super().__init__(master, width=width, highlightthickness=0, bd=0, bg=bg, **kw)
        self.command = command
        self._range = (0.0, 1.0)
        self._drag_offset: int | None = None
        self._hover = False
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first, last) -> None:
        try:
            self._range = (float(first), float(last))
        except (TypeError, ValueError):
            return
        self._redraw()

    def _thumb_span(self) -> tuple[int, int]:
        height = self.winfo_height()
        first, last = self._range
        if height < 12 or last - first >= 0.999:
            return 0, 0
        y0 = int(first * height)
        y1 = int(last * height)
        if y1 - y0 < 34:
            y1 = min(height, y0 + 34)
            y0 = max(0, y1 - 34)
        return y0, y1

    def _redraw(self) -> None:
        self.delete("all")
        height = self.winfo_height()
        if height < 12:
            return
        y0, y1 = self._thumb_span()
        if y1 <= y0:
            return
        self.create_rectangle(4, 2, 9, height - 2, fill=TRACK, outline="")
        self.create_rectangle(3, y0, 10, y1, fill=THUMB_HOVER if self._hover else THUMB, outline="")

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._redraw()

    def _press(self, event) -> None:
        y0, y1 = self._thumb_span()
        if y1 <= y0:
            return
        if y0 <= event.y <= y1:
            self._drag_offset = event.y - y0
        else:
            self._drag_offset = (y1 - y0) // 2
            self.command("scroll", "1" if event.y > y1 else "-1", "pages")

    def _motion(self, event) -> None:
        if self._drag_offset is None:
            return
        y0, y1 = self._thumb_span()
        thumb = max(1, y1 - y0)
        track = max(1, self.winfo_height() - thumb)
        fraction = (event.y - self._drag_offset) / track
        self.command("moveto", f"{max(0.0, min(1.0, fraction)):.5f}")

    def _release(self, _event) -> None:
        self._drag_offset = None


def _ensure_wheel_binding(interp) -> None:
    """在整个解释器上注册一次滚轮绑定（按自定义 bindtag 分发）。"""
    if getattr(interp, "_dts_wheel_bound", False):
        return

    def on_wheel(event):
        canvas = getattr(event.widget, "_dts_canvas", None)
        if canvas is None:
            return None
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        if abs(delta) >= 120:
            step = -int(delta / 120) or (-1 if delta > 0 else 1)
        else:
            step = -1 if delta > 0 else 1
        try:
            canvas.yview_scroll(step, "units")
        except Exception:
            pass
        return "break"

    try:
        interp.bind_class(WHEEL_TAG, "<MouseWheel>", on_wheel)
        interp._dts_wheel_bound = True
    except Exception:
        pass


def attach_wheel(widget, canvas) -> None:
    """让鼠标位于该区域任意位置（含子控件）都能用滚轮滚动。"""
    _ensure_wheel_binding(widget.winfo_toplevel())

    def walk(current) -> None:
        try:
            current._dts_canvas = canvas
            tags = list(current.bindtags())
            if WHEEL_TAG not in tags:
                tags.insert(1, WHEEL_TAG)
                current.bindtags(tuple(tags))
        except Exception:
            pass
        for child in current.winfo_children():
            walk(child)

    walk(widget)


def make_scroll_area(parent, *, bg: str = BG):
    """建一个"画布 + 细滚动条"的滚动区域，返回 (canvas, 内容容器, 外层容器)。"""
    holder = tk.Frame(parent, bg=bg)
    holder.pack(fill="both", expand=True)

    canvas = tk.Canvas(holder, bg=bg, highlightthickness=0, bd=0,
                       yscrollincrement=WHEEL_STEP_HINT)
    bar = SlimScrollbar(holder, canvas.yview, bg=bg)
    bar.pack(side="right", fill="y", padx=(3, 1))
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=bar.set)

    inner = tk.Frame(canvas, bg=bg)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
    canvas.bar = bar  # 方便外部取用
    attach_wheel(inner, canvas)
    return canvas, inner, holder


def ask_confirm(parent, title: str, message: str, *, font=None,
                yes: str = "是", no: str = "否") -> bool:
    """自己画的确认框。

    不用系统 messagebox 的原因：它的位置由系统决定，父窗口贴在屏幕上沿隐藏时
    有可能被摆到屏幕外面——用户看不到框、程序又卡在模态里。这里位置自己定，
    保证出现在鼠标所在屏幕的可见区域；任何异常都按"否"处理（绝不擅自确认）。
    """
    answer = {"ok": False}
    try:
        win = tk.Toplevel(parent)
        win.title(title)
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        try:
            win.attributes("-toolwindow", True)  # 不在任务栏留按钮
        except Exception:
            pass

        box = tk.Frame(win, bg=BG, padx=20, pady=16)
        box.pack(fill="both", expand=True)
        tk.Label(box, text=message, bg=BG, fg=TEXT, font=font, justify="left").pack(anchor="w")
        row = tk.Frame(box, bg=BG)
        row.pack(anchor="e", pady=(16, 0))

        def close(value: bool) -> None:
            answer["ok"] = value
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        flat_button(row, no, lambda: close(False), font=font).pack(side="right")
        flat_button(row, yes, lambda: close(True), bg="#4a3038", fg=DANGER, hover="#5b3a44",
                    font=font).pack(side="right", padx=(0, 10))
        win.protocol("WM_DELETE_WINDOW", lambda: close(False))
        win.bind("<Escape>", lambda _e: close(False))
        # 回车也按"否"处理，避免手快点掉
        win.bind("<Return>", lambda _e: close(False))

        win.update_idletasks()
        width, height = win.winfo_width(), win.winfo_height()
        left, top, right, bottom = dt_winapi.monitor_work_area(parent)
        x = max(left + 10, min((left + right) // 2 - width // 2, right - width - 10))
        y = max(top + 10, min(top + (bottom - top) // 3, bottom - height - 10))
        win.geometry(f"+{x}+{y}")
        try:
            win.focus_force()
        except Exception:
            pass
        win.grab_set()
        win.wait_window()
    except Exception:
        return False
    return bool(answer["ok"])
