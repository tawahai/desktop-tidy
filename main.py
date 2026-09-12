# -*- coding: utf-8 -*-
"""桌面收纳盒：程序入口。

用法：双击「启动.bat」，或在本目录执行  pythonw main.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
import traceback
import zlib
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog

import dt_config
import dt_icon
import dt_organize
import dt_panel
import dt_tray
import dt_winapi

WINDOW_TITLE = "桌面收纳盒"
_MUTEX = None

# 字体规格（家族名在运行时按系统可用性挑选，Win7 上没有 YaHei UI 也能正常显示）
FONT_SPECS = {
    "ui": (9, "normal"),
    "ui_tiny": (8, "normal"),
    "ui_small": (8, "normal"),
    "ui_section": (9, "bold"),
    "ui_title": (13, "bold"),
    "item": (8, "normal"),
    "hint": (9, "normal"),
    "status": (8, "normal"),
    "ghost": (9, "normal"),
    "menu": (9, "normal"),
    "fallback": (8, "bold"),
}
FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑",
                   "SimHei", "黑体", "Segoe UI", "Tahoma")


class App:
    """把配置、收纳面板和文件操作串起来。"""

    def __init__(self, config: dict):
        self.config = config
        self._photos: dict = {}
        self._tip: tk.Toplevel | None = None

        self.root = tk.Tk()
        self.root.withdraw()  # 只作为宿主，界面上只出现收纳面板
        # 隐藏的宿主窗口不该被关闭：真收到关闭请求就记一笔并收进托盘，绝不静默退出
        self.root.protocol("WM_DELETE_WINDOW", self._root_close)
        try:
            self.root.tk.call("tk", "scaling", dt_winapi.system_dpi() / 72)
        except Exception:
            pass
        self.font_family = self._pick_font()
        self._fonts = self._build_fonts()
        try:
            self._icon_photos = [tk.PhotoImage(data=dt_winapi.png_to_data(dt_icon.icon_png(size)))
                                 for size in (64, 32, 16)]
            self.root.iconphoto(True, *self._icon_photos)
        except Exception:
            pass

        dt_config.ensure_folders(self.config)
        self.config["autostart"] = dt_winapi.autostart_enabled()
        self.panel = dt_panel.OrganizerPanel(self, self.config)
        self.panel.apply_style()
        self.tray: dt_tray.TrayIcon | None = None
        self.root.after(300, self._setup_tray)
        self.root.after(400, self._apply_tool_window)
        self.root.after(30_000, self._heartbeat)
        if self.config.get("hide_desktop_icons") and dt_winapi.desktop_icons_visible():
            dt_winapi.set_desktop_icons_visible(False)

    # ------------------------------------------------------------- 基础
    def _heartbeat(self) -> None:
        """每 30 秒记一次心跳：日志里能看到程序在某个时刻是否还活着。"""
        try:
            self.log_event(f"心跳（程序运行中，PID={os.getpid()}）")
        except Exception:
            pass
        try:
            self.root.after(30_000, self._heartbeat)
        except Exception:
            pass

    def _root_close(self) -> None:
        self.log_event("收到宿主窗口关闭请求（已忽略并收进托盘）")
        self.hide_to_tray()

    def _apply_tool_window(self) -> None:
        dt_winapi.set_tool_window(self.panel, True)

    def _pick_font(self) -> str:
        try:
            import tkinter.font as tkfont

            families = set(tkfont.families(self.root))
        except Exception:
            families = set()
        for name in FONT_CANDIDATES:
            if name in families:
                return name
        return "Tahoma"

    def _build_fonts(self) -> dict:
        fonts = {}
        for key, (size, weight) in FONT_SPECS.items():
            fonts[key] = ((self.font_family, size, weight) if weight != "normal"
                          else (self.font_family, size))
        return fonts

    def font(self, name: str):
        return self._fonts.get(name, self._fonts["ui"])

    def photo(self, path: Path, size: int):
        png = dt_winapi.icon_png(path, size)
        if not png:
            return None
        key = (len(png), zlib.crc32(png), size)
        cached = self._photos.get(key)
        if cached is not None:
            return cached
        try:
            image = tk.PhotoImage(data=dt_winapi.png_to_data(png))
        except Exception:
            return None
        self._photos[key] = image
        return image

    def bind_tip(self, widget, text: str) -> None:
        widget.bind("<Enter>", lambda _e, w=widget, t=text: self._show_tip(w, t), add="+")
        widget.bind("<Leave>", lambda _e: self._hide_tip(), add="+")
        widget.bind("<Button-1>", lambda _e: self._hide_tip(), add="+")

    def _show_tip(self, widget, text: str) -> None:
        self._hide_tip()
        try:
            tip = tk.Toplevel(self.root)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(tip, text=text, bg="#11151a", fg="#e9ecf1", font=self.font("ui_tiny"),
                     padx=7, pady=3).pack()
            tip.geometry(f"+{widget.winfo_rootx() + 4}"
                         f"+{widget.winfo_rooty() + widget.winfo_height() + 4}")
            self._tip = tip
        except Exception:
            self._tip = None

    def _hide_tip(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def save(self) -> None:
        try:
            dt_config.save_config(self.config)
        except Exception:
            pass

    def log_event(self, text: str) -> None:
        """把托盘/退出相关的动作记到托盘日志里，方便排查"莫名退出"。"""
        try:
            path = dt_config.appdata_dir() / "tray.log"
            if path.exists() and path.stat().st_size > 200_000:
                path.write_text("", encoding="utf-8")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
        except Exception:
            pass

    # ------------------------------------------------------------- 托盘
    def _setup_tray(self) -> None:
        try:
            tray = dt_tray.TrayIcon(self.panel, "桌面收纳盒")
            tray.on_click = self.toggle_from_tray
            tray.on_right_click = self.tray_menu
            tray.on_minimize = self.panel._on_close
            tray.on_show_request = self.show_from_tray
            tray.logger = self.log_event
            self.tray = tray
            if not tray.hicon:
                self._log_tray_issue("托盘图标句柄创建失败（HICON=0）")
            # 程序一启动就把图标放进托盘，之后一直存在（收起/展开不再增删图标）
            joined = bool(tray.show(tip="桌面收纳盒（运行中）"))
            self.log_event(f"托盘初始化: hwnd={hex(tray.hwnd or 0)} 图标已加入={joined}")
            if not joined:
                self._log_tray_issue("托盘图标加入失败（Shell_NotifyIcon 返回失败）")
            if self.config.get("hidden_to_tray"):
                self.hide_to_tray()
        except Exception:
            self.tray = None
            self._log_tray_issue(traceback.format_exc())

    def _log_tray_issue(self, detail: str) -> None:
        try:
            (dt_config.appdata_dir() / "tray_error.log").write_text(detail, encoding="utf-8")
        except Exception:
            pass

    def hide_to_tray(self, balloon: str | None = None) -> None:
        """收起到系统托盘（面板关掉，任务栏不留按钮）。"""
        self.log_event(f"hide_to_tray 被调用（面板可见={self.panel.winfo_viewable()}）")
        if self.tray is None:
            self._tray_unavailable()
            return
        hint = "已收起到系统托盘，点击托盘图标可以再打开"
        first_time = not self.config.get("tray_hint_shown")
        # 顺手确认一次图标确实在托盘里（返回失败就不把窗口藏起来）
        if not self.tray.show(balloon if balloon is not None else (hint if first_time else ""),
                              tip="桌面收纳盒（已收起）"):
            self._tray_unavailable()
            return
        if first_time:
            self.config["tray_hint_shown"] = True
        self.config["hidden_to_tray"] = True
        self.save()
        try:
            self.panel.withdraw()
        except Exception:
            pass

    def _tray_unavailable(self) -> None:
        try:
            self.panel.flash("系统托盘不可用，窗口保持显示；可在「设置 → 关于」里退出")
        except Exception:
            pass

    def show_from_tray(self) -> None:
        self.log_event("show_from_tray 被调用")
        self.config["hidden_to_tray"] = False
        self.save()
        try:
            self.panel.deiconify()
            self.panel.lift()
            if self.panel.panel_cfg.get("docked"):
                self.panel.reveal_and_hold(10.0)  # 显式显示时先保持 10 秒，别马上又缩回去
        except Exception:
            pass
        if self.tray is not None:
            self.tray.show(tip="桌面收纳盒（运行中）")  # 图标保留，只更新提示文字

    def toggle_from_tray(self) -> None:
        try:
            visible = bool(self.panel.winfo_viewable())
        except Exception:
            visible = False
        self.log_event(f"点击托盘图标（面板可见={visible}）")
        if visible:
            self.hide_to_tray()
        else:
            self.show_from_tray()

    def tray_menu(self) -> None:
        """托盘右键菜单。

        用 Tk 自己的菜单而不是系统原生菜单：原生菜单要抢前台、要跑系统级模态循环，
        在"资源管理器占着前台、鼠标压在托盘图标上"的真实场景里容易出问题。
        Tk 菜单是我们自己进程里的普通窗口，不依赖前台状态。
        """
        self.log_event("准备弹出托盘菜单")
        items = (
            (1, "显示收纳面板"),
            (None, None),
            (2, "一键整理桌面"),
            (3, "撤销上次整理"),
            (4, "设置（退出程序也在里面）"),
        )
        x, y = dt_winapi.cursor_pos()
        menu = tk.Menu(self.root, tearoff=0, bg="#242a33", fg="#e9ecf1",
                       activebackground="#3d4b5e", activeforeground="#ffffff", bd=0,
                       font=self.font("menu"))
        for command_id, label in items:
            if label is None:
                menu.add_separator()
            else:
                menu.add_command(label=label,
                                 command=lambda c=command_id: self._tray_action(c))
        # 让菜单出现在鼠标上方，鼠标不会正好压在某一项上（避免误点）
        menu.update_idletasks()
        _left, top, _right, _bottom = dt_winapi.monitor_work_area(self.panel)
        y = max(top + 4, y - menu.winfo_reqheight() - 6)
        try:
            menu.tk_popup(x, y)
            self.log_event(f"托盘菜单已关闭（弹出位置=({x},{y})）")
        except Exception as exc:
            self.log_event(f"弹出托盘菜单失败: {exc!r}")
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _tray_action(self, command_id: int) -> None:
        actions = {
            1: self.show_from_tray,
            2: self.organize_desktop,
            3: self.undo_organize,
            4: self._tray_settings,
        }
        action = actions.get(command_id)
        if action is not None:
            self.log_event(f"托盘菜单选中 {command_id}：{getattr(action, '__name__', action)}")
            self.root.after(10, action)

    def quit_confirmed(self) -> None:
        """从托盘菜单/关于页退出前确认一次，避免误点。"""
        import dt_ui

        try:
            answer = dt_ui.ask_confirm(
                self.panel, "退出桌面收纳盒",
                "确定要退出程序吗？\n\n退出后收纳盒面板和托盘图标都会关闭，\n"
                "桌面上的「收纳盒」文件夹和里面的文件不受影响。",
                font=self.font("ui"))
        except Exception as exc:
            self.log_event(f"退出确认框异常，已按「取消」处理: {exc!r}")
            return
        self.log_event(f"退出确认框: 用户选择={'退出' if answer else '取消/看不到框'}")
        if not answer:
            return
        self.quit()

    def _tray_settings(self) -> None:
        self.show_from_tray()
        try:
            self.panel.show_view("settings")
        except Exception:
            pass

    # ------------------------------------------------------------- 面板
    def apply_panel_style(self) -> None:
        try:
            self.panel.apply_style()
        except Exception:
            pass

    def rebuild_sections(self) -> None:
        try:
            self.panel.rebuild_sections()
        except Exception:
            pass

    def refresh_sections(self, force: bool = False) -> None:
        try:
            self.panel.refresh_sections(force=force)
        except Exception:
            pass

    def refresh_panel(self) -> None:
        self.refresh_sections(force=True)
        try:
            if self.panel.settings is not None:
                self.panel.settings.refresh()
        except Exception:
            pass

    # ------------------------------------------------------------- 分区管理
    def rename_box(self, box: dict) -> None:
        name = simpledialog.askstring("重命名分区", "新的分区名称：",
                                      initialvalue=box.get("name", ""), parent=self.panel)
        if not name or name == box.get("name"):
            return
        old_folder = dt_config.box_folder(self.config, box)
        box["name"] = name
        if not Path(str(box.get("folder", ""))).is_absolute():
            box["folder"] = name
            new_folder = dt_config.resolve_root(self.config) / name
            try:
                if old_folder.exists() and old_folder != new_folder and not new_folder.exists():
                    old_folder.rename(new_folder)
            except OSError as exc:
                messagebox.showwarning("重命名", f"文件夹改名失败：{exc}", parent=self.panel)
        self.save()
        self.rebuild_sections()
        self.refresh_panel()

    def move_box(self, box: dict, delta: int) -> None:
        boxes = self.config["boxes"]
        try:
            index = boxes.index(box)
        except ValueError:
            return
        target = index + delta
        if 0 <= target < len(boxes):
            boxes[index], boxes[target] = boxes[target], boxes[index]
            self.save()
            self.rebuild_sections()
            self.refresh_panel()

    def remove_box(self, box: dict) -> None:
        folder = dt_config.box_folder(self.config, box)
        if not messagebox.askyesno(
            "移除分区",
            f"从面板移除「{box.get('name', '')}」？\n\n分区里的文件不会被删除，仍保留在：\n{folder}",
            parent=self.panel,
        ):
            return
        self.config["boxes"] = [b for b in self.config["boxes"] if b["id"] != box["id"]]
        self.save()
        self.rebuild_sections()
        self.refresh_panel()

    # ------------------------------------------------------------- 文件操作
    def move_paths_into(self, paths: list[Path], box: dict) -> None:
        folder = dt_config.box_folder(self.config, box)
        safe: list[Path] = []
        for path in paths:
            if folder == path or dt_organize.is_inside(folder, path):
                continue
            safe.append(path)
        if not safe:
            return
        moved, errors = dt_organize.move_into([str(p) for p in safe], folder)
        self.refresh_sections(force=True)
        self.refresh_panel()
        if moved:
            self.panel.flash(f"已把 {len(moved)} 个文件移到「{box.get('name', '')}」")
        elif errors:
            self.panel.flash(errors[0][:60])

    def move_to_desktop(self, paths: list[Path]) -> None:
        done = 0
        for path in paths:
            if dt_organize.move_to_desktop(path):
                done += 1
        self.refresh_sections(force=True)
        self.refresh_panel()
        self.panel.flash(f"已把 {done} 个文件移回桌面")

    def delete_items(self, paths: list[Path]) -> None:
        if not paths:
            return
        names = "\n".join("　" + p.name for p in paths[:10])
        more = f"\n　…还有 {len(paths) - 10} 个" if len(paths) > 10 else ""
        if not messagebox.askyesno("删除", f"把下面 {len(paths)} 项放进回收站？\n\n{names}{more}",
                                   parent=self.panel):
            return
        ok = dt_winapi.send_to_recycle_bin(paths)
        self.panel.selected.clear()
        self.refresh_sections(force=True)
        self.refresh_panel()
        self.panel.flash("已删除到回收站" if ok else "删除失败，请手动处理")

    # ------------------------------------------------------------- 整理
    def organize_desktop(self) -> None:
        plan = dt_organize.build_plan(self.config)
        if not plan:
            messagebox.showinfo("整理桌面", "桌面上没有需要整理的文件。", parent=self.panel)
            return
        lines = "\n".join(f"　{k}：{v} 个" for k, v in sorted(dt_organize.summarize(plan).items()))
        root_dir = dt_config.resolve_root(self.config)
        if not messagebox.askyesno(
            "整理桌面",
            f"把桌面上 {len(plan)} 个文件收纳到：\n{root_dir}\n\n{lines}\n\n"
            "整理后可以点「撤销」还原。是否继续？",
            parent=self.panel,
        ):
            return
        record = dt_organize.apply_plan(plan)
        self.config["last_organize"] = record["time"]
        self.save()
        self.refresh_sections(force=True)
        self.refresh_panel()
        message = f"已收纳 {len(record['moves'])} 个文件"
        if record["errors"]:
            message += f"，{len(record['errors'])} 个失败"
        self.panel.flash(message)
        if record["errors"]:
            messagebox.showwarning("整理桌面", message + "\n\n" + "\n".join(record["errors"][:6]),
                                   parent=self.panel)

    def undo_organize(self) -> None:
        if not messagebox.askyesno("撤销整理", "把上次整理的文件搬回桌面？", parent=self.panel):
            return
        result = dt_organize.undo_last()
        self.refresh_sections(force=True)
        self.refresh_panel()
        message = f"已还原 {len(result['restored'])} 个文件"
        if result["errors"]:
            message += f"，{len(result['errors'])} 个没能还原"
        self.panel.flash(message)
        detail = "\n\n" + "\n".join(result["errors"][:6]) if result["errors"] else ""
        messagebox.showinfo("撤销整理", message + detail, parent=self.panel)

    def welcome(self) -> None:
        messagebox.showinfo(
            "桌面收纳盒",
            "所有分区都在这一个面板里，桌面只需要留它一个窗口。\n\n"
            "· 把文件拖到某个分区上，就收进那个分区\n"
            "· 拖到面板顶部（标题/按钮那片空白），自动按类型分区\n"
            "· 按住分区里的文件拖到另一个分区，可以换分类\n"
            "· 点分区标题折叠它，拖窗口边缘可以缩放面板\n"
            "· 把「桌面收纳盒」标题拖到屏幕最上方，面板会贴边藏起来，\n"
            "  鼠标碰到屏幕顶边再滑出来；拖下来就取消\n"
            "· 点右上角的 × 按「设置 → 关闭按钮」里的选择：收起到系统托盘，或直接退出\n"
            "· 「设置」页里能改图标大小、隐藏系统桌面图标、换收纳目录\n\n"
            f"收纳目录：{dt_config.resolve_root(self.config)}\n\n"
            f"作者：{dt_config.APP_AUTHOR} ｜ 开发工具：{dt_config.APP_TOOL} ｜ "
            f"v{dt_config.APP_VERSION}（{dt_config.APP_DATE}）",
            parent=self.panel,
        )

    # ------------------------------------------------------------- 生命周期
    def quit(self) -> None:
        caller = "?"
        try:
            caller = traceback.extract_stack()[-2].name
        except Exception:
            pass
        self.log_event(f"quit() 被调用，来源={caller}")
        self.save()
        self._hide_tip()
        try:
            if self.tray is not None:
                self.tray.destroy()
        except Exception:
            pass
        try:
            self.panel.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


def single_instance(name: str = "DesktopTidy_SingleInstance") -> bool:
    global _MUTEX
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        _MUTEX = kernel32.CreateMutexW(None, False, name)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def write_crash_log(exc_text: str) -> None:
    try:
        (dt_config.appdata_dir() / "crash.log").write_text(exc_text, encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    dt_winapi.make_dpi_aware()
    if not single_instance():
        # 已经在运行：直接把它的面板叫到前面来（贴边隐藏时也能弹出来）
        if not dt_winapi.request_show(WINDOW_TITLE):
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo(WINDOW_TITLE, "程序已经在运行了。")
                root.destroy()
            except Exception:
                pass
        return 0
    try:
        config = dt_config.load_config()
        first_run = bool(config.get("first_run"))
        if first_run:
            config["first_run"] = False
            dt_config.save_config(config)
        app = App(config)
        if first_run:
            app.root.after(600, app.welcome)
        app.run()
    except Exception:
        write_crash_log(traceback.format_exc())
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                WINDOW_TITLE,
                "程序启动出错，详情已记录到：\n" + str(dt_config.appdata_dir() / "crash.log"),
            )
            root.destroy()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
