# -*- coding: utf-8 -*-
"""桌面收纳盒：分类判断、搬运与撤销。"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import dt_config

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "iconcache.db"}
SKIP_SUFFIX = (".tmp", ".part", ".crdownload", ".download")
SKIP_PREFIX = ("~$", "~", "._")


def category_for(path: Path, rules: dict[str, list[str]]) -> str:
    name = path.name.lower()
    best_cat = dt_config.DEFAULT_CATEGORY
    best_len = -1
    for cat, exts in rules.items():
        for ext in exts:
            ext = str(ext).lower()
            if ext and name.endswith(ext) and len(ext) > best_len:
                best_cat, best_len = cat, len(ext)
    return best_cat


def desktop_entries(cfg: dict) -> list[Path]:
    """桌面上可以被收纳的文件（不含文件夹和系统文件）。"""
    desk = dt_config.desktop_dir()
    skip_dirs = {str(dt_config.resolve_root(cfg)).lower()}
    for box in cfg.get("boxes", []):
        skip_dirs.add(str(dt_config.box_folder(cfg, box)).lower())

    items: list[Path] = []
    try:
        entries = list(desk.iterdir())
    except OSError:
        return items

    for p in entries:
        try:
            if p.is_dir():
                continue
            low = p.name.lower()
            if low in SKIP_NAMES or low.endswith(SKIP_SUFFIX):
                continue
            if low.startswith(SKIP_PREFIX):
                continue
            if str(p).lower() in skip_dirs:
                continue
            attrs = getattr(p.stat(), "st_file_attributes", 0)
            if attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM):
                continue
            items.append(p)
        except OSError:
            continue
    return items


def unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(2, 1000):
        cand = folder / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    return folder / f"{stem} ({int(time.time())}){suffix}"


def build_plan(cfg: dict) -> list[tuple[Path, Path, str]]:
    """返回 [(源文件, 目标路径, 分类名)]。"""
    rules = dt_config.all_rules(cfg)
    plan: list[tuple[Path, Path, str]] = []
    for src in desktop_entries(cfg):
        cat = category_for(src, rules)
        box = next((b for b in cfg.get("boxes", []) if b.get("name") == cat), None)
        folder = dt_config.box_folder(cfg, box) if box else dt_config.resolve_root(cfg) / cat
        plan.append((src, unique_target(folder, src.name), cat))
    return plan


def apply_plan(plan: list[tuple[Path, Path, str]], note: str = "整理桌面") -> dict:
    moved, errors = [], []
    for src, dst, cat in plan:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append({"from": str(src), "to": str(dst), "category": cat})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "moves": moved,
        "errors": errors,
    }
    if moved:
        path = dt_config.history_dir() / f"{int(time.time())}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def last_history() -> Path | None:
    files = sorted(dt_config.history_dir().glob("*.json"), key=lambda p: p.name)
    return files[-1] if files else None


def undo_last() -> dict:
    path = last_history()
    if not path:
        return {"restored": [], "errors": ["没有可撤销的整理记录"]}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"restored": [], "errors": [f"记录读取失败：{exc}"]}

    restored, errors = [], []
    for item in reversed(record.get("moves", [])):
        src, dst = Path(item["to"]), Path(item["from"])
        try:
            if not src.exists():
                errors.append(f"{src.name} 已不在收纳盒中")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            target = dst if not dst.exists() else unique_target(dst.parent, dst.name)
            shutil.move(str(src), str(target))
            restored.append(str(target))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
    try:
        path.unlink()
    except OSError:
        pass
    return {"restored": restored, "errors": errors}


def move_into(paths: list[str], folder: Path) -> tuple[list[Path], list[str]]:
    """把外部拖入的文件移动进盒子目录。"""
    moved, errors = [], []
    for raw in paths:
        src = Path(raw)
        try:
            if not src.exists():
                errors.append(f"{src.name} 不存在")
                continue
            if src.parent == folder:
                continue
            target = unique_target(folder, src.name)
            folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            moved.append(target)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
    return moved, errors


def move_to_desktop(path: Path) -> Path | None:
    try:
        desk = dt_config.desktop_dir()
        target = desk / path.name if not (desk / path.name).exists() else unique_target(desk, path.name)
        shutil.move(str(path), str(target))
        return target
    except Exception:
        return None


def is_inside(child: Path, parent: Path) -> bool:
    """child 是否位于 parent 目录内。

    自己实现而不用 Path.is_relative_to，是为了兼容 Windows 7 上只能装的 Python 3.8。
    """
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except Exception:
        return False


def folder_size_text(folder: Path, limit: int = 60) -> str:
    try:
        names = sorted(p.name for p in folder.iterdir())
    except OSError:
        return ""
    if len(names) > limit:
        names = names[:limit] + ["…"]
    return "、".join(names)


def summarize(plan: list[tuple[Path, Path, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for _, _, cat in plan:
        out[cat] = out.get(cat, 0) + 1
    return out


def open_path(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass
