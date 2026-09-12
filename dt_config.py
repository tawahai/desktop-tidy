# -*- coding: utf-8 -*-
"""桌面收纳盒：配置、路径与默认分类规则。"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

APP_NAME = "桌面收纳盒"
APPDATA_NAME = "DesktopTidy"
DEFAULT_CATEGORY = "其他"

# 版本与作者信息（界面上「设置 → 关于」会显示这些）
APP_VERSION = "2.3"
APP_AUTHOR = "唐小漫"
APP_TOOL = "Codex"
APP_DATE = "2026-09-12"
APP_TECH = "纯 Python 标准库实现，不需要第三方依赖"

# 分类规则：按顺序匹配，先命中的优先。".tar.gz" 这类复合扩展名会优先匹配。
DEFAULT_RULES: dict[str, list[str]] = {
    "快捷方式": [".lnk", ".url", ".website"],
    "文档": [
        ".txt", ".md", ".rtf", ".doc", ".docx", ".wps", ".pdf", ".ofd",
        ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".odt", ".ods", ".odp",
        ".epub", ".mobi", ".tex",
    ],
    "图片": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
        ".heic", ".tif", ".tiff", ".psd", ".ai", ".avif", ".raw",
    ],
    "视频": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".rmvb", ".ts"],
    "音频": [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".ape", ".mid"],
    "压缩包": [".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz", ".gz", ".bz2", ".xz", ".iso"],
    "程序": [".exe", ".msi", ".msix", ".appx", ".bat", ".cmd", ".ps1", ".apk", ".jar"],
}

PALETTE = [
    "#2f333d", "#3a3044", "#2b3a3e", "#3d3529",
    "#2e3a4e", "#3f2f38", "#333b2f", "#2d3436",
]

BOX_W = 268
BOX_H = 214


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APPDATA_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return appdata_dir() / "config.json"


def history_dir() -> Path:
    d = appdata_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def desktop_dir() -> Path:
    """桌面路径，兼容 OneDrive 重定向。"""
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            value, _ = winreg.QueryValueEx(k, "Desktop")
        p = Path(os.path.expandvars(value))
        if p.exists():
            return p
    except Exception:
        pass
    for cand in (Path.home() / "Desktop", Path.home() / "桌面"):
        if cand.exists():
            return cand
    return Path.home() / "Desktop"


def work_area() -> tuple[int, int, int, int]:
    """主屏工作区（不含任务栏）。"""
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        if ok:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1920, 1080


def make_box(name: str, folder: str | None = None, index: int = 0, visible: bool = True) -> dict:
    left, top, right, bottom = work_area()
    cols = min(4, max(1, (right - left - 80) // (BOX_W + 16)))
    total_w = cols * BOX_W + (cols - 1) * 16
    x0 = max(left + 20, right - 28 - total_w)
    col = index % cols
    row = index // cols
    x = x0 + col * (BOX_W + 16)
    y = top + 40 + row * (BOX_H + 16)
    x = min(x, max(left, right - BOX_W - 8))
    y = min(y, max(top, bottom - BOX_H - 8))
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "folder": folder or name,
        "color": PALETTE[index % len(PALETTE)],
        "x": x,
        "y": y,
        "w": BOX_W,
        "h": BOX_H,
        "alpha": 0.93,
        "topmost": False,
        "collapsed": False,
        "visible": visible,
    }


def default_panel() -> dict:
    """单个收纳面板的默认位置：贴屏幕右侧，把桌面中间让出来。"""
    left, top, right, bottom = work_area()
    width = 520
    height = min(900, max(420, bottom - top - 60))
    return {
        "x": max(left, right - width - 20),
        "y": top + 24,
        "w": width,
        "h": height,
        "view": "organize",
        "alpha": 1.0,
        "topmost": False,
        "peek_on_start": True,  # 启动后先把面板显示 10 秒，再按设置收回去
    }


def default_config() -> dict:
    names = list(DEFAULT_RULES.keys()) + [DEFAULT_CATEGORY]
    return {
        "version": 1,
        "root": str(desktop_dir() / "收纳盒"),
        "rules": {k: list(v) for k, v in DEFAULT_RULES.items()},
        "custom_rules": {},
        "boxes": [make_box(n, n, i) for i, n in enumerate(names)],
        "panel": default_panel(),
        "icon_size": 44,
        "alpha": 0.93,
        "topmost": False,
        "show_labels": True,
        "autostart": False,
        "hide_desktop_icons": False,
        "hidden_to_tray": False,
        "tray_hint_shown": False,
        "close_action": "tray",  # 点关闭按钮时：tray=收起到托盘，exit=直接退出
        "last_organize": "",
        "first_run": True,
    }


def _merge(base: dict, data: dict) -> dict:
    out = dict(base)
    for k, v in (data or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    cfg = default_config()
    path = config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg = _merge(cfg, data)
        except Exception:
            broken = path.with_suffix(".broken.json")
            try:
                path.replace(broken)
            except Exception:
                pass
    if not cfg.get("boxes"):
        cfg["boxes"] = default_config()["boxes"]
    return cfg


def save_config(cfg: dict) -> None:
    path = config_path()
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".tmp")
    try:
        # 先写临时文件再替换，避免写一半断电把配置写坏
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # %APPDATA% 被重定向或做了软链接时，跨卷替换会失败（WinError 17），直接覆盖写
        try:
            tmp.unlink()
        except OSError:
            pass
        path.write_text(text, encoding="utf-8")


def resolve_root(cfg: dict) -> Path:
    root = Path(os.path.expandvars(str(cfg.get("root") or "")))
    if not str(root):
        root = desktop_dir() / "收纳盒"
    return root


def box_folder(cfg: dict, box: dict) -> Path:
    """盒子的实际目录，支持绝对路径或相对收纳根目录。"""
    folder = str(box.get("folder") or box.get("name") or "")
    p = Path(os.path.expandvars(folder))
    if p.is_absolute():
        return p
    return resolve_root(cfg) / folder


def ensure_folders(cfg: dict) -> None:
    try:
        resolve_root(cfg).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    for box in cfg.get("boxes", []):
        try:
            box_folder(cfg, box).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def all_rules(cfg: dict) -> dict[str, list[str]]:
    rules = {k: list(v) for k, v in (cfg.get("rules") or {}).items()}
    for cat, exts in (cfg.get("custom_rules") or {}).items():
        rules.setdefault(cat, [])
        for e in exts:
            e = str(e).lower()
            if e and not e.startswith("."):
                e = "." + e
            if e and e not in rules[cat]:
                rules[cat].append(e)
    return rules
