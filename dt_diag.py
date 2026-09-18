# -*- coding: utf-8 -*-
"""诊断日志：把异常和"硬崩溃"都写进文件，方便排查程序莫名退出。

- 普通事件：追加到 %APPDATA%\\DesktopTidy\\tray.log
- 致命错误：写进 %APPDATA%\\DesktopTidy\\crash.log
  （把 C 运行库的 stderr 重定向过去，Python 的 "Fatal Python error"、
   Tcl 的 panic 信息都能留下来；再加 faulthandler 记录崩溃时的调用栈）
"""

from __future__ import annotations

import datetime
import faulthandler
import os
import sys
import threading
import traceback
from pathlib import Path

import dt_config

# 逐条图标的详细日志（排查时才打开，平时关着免得日志太长）
VERBOSE = False

_installed = False
_lock = threading.Lock()
MAX_LOG_BYTES = 400_000


def log_path() -> Path:
    return dt_config.appdata_dir() / "tray.log"


def crash_path() -> Path:
    return dt_config.appdata_dir() / "crash.log"


def event(text: str) -> None:
    """写一行带时间戳的日志；日志本身出错绝不能影响程序。"""
    try:
        path = log_path()
        with _lock:
            try:
                if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
                    path.write_text("", encoding="utf-8")
            except OSError:
                pass
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp}  {text}\n")
                handle.flush()
    except Exception:
        pass


def detail(text: str) -> None:
    """只在排查期写入的详细日志。"""
    if VERBOSE:
        event(text)


def note_exception(where: str, exc_type, exc, tb) -> None:
    try:
        text = "".join(traceback.format_exception(exc_type, exc, tb)).strip()
        event("[异常] " + where + ": " + text.replace("\n", " | "))
    except Exception:
        pass


def _append_crash(text: str) -> None:
    try:
        with crash_path().open("a", encoding="utf-8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
            handle.flush()
    except Exception:
        pass


def install() -> None:
    """在程序最开头调用一次。"""
    global _installed
    if _installed:
        return
    _installed = True

    try:
        dt_config.appdata_dir().mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    handle = None
    try:
        handle = open(crash_path(), "w", encoding="utf-8", buffering=1)
    except Exception:
        handle = None

    if handle is not None:
        kernel32 = None
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.SetStdHandle(-12, handle.fileno())  # STD_ERROR_HANDLE
            kernel32.SetStdHandle(-11, handle.fileno())  # STD_OUTPUT_HANDLE
        except Exception:
            pass
        for fd in (1, 2):
            try:
                os.dup2(handle.fileno(), fd)
            except Exception:
                pass
        if sys.stdout is None:
            sys.stdout = handle
        if sys.stderr is None:
            sys.stderr = handle
        try:
            # Python 层的崩溃（访问越界、栈溢出等）会连调用栈一起打下来
            faulthandler.enable(file=handle, all_threads=True)
        except Exception:
            pass

    def _excepthook(exc_type, exc, tb):
        note_exception("主线程未捕获", exc_type, exc, tb)
        try:
            _append_crash("".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    sys.excepthook = _excepthook

    def _thread_hook(args):
        note_exception(f"线程 {getattr(args.thread, 'name', '?')}",
                       args.exc_type, args.exc_value, args.exc_traceback)

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


def install_tk(root) -> None:
    """Tk 回调里抛的异常默认只在控制台一闪而过（打包成 exe 后根本看不到），这里改成写日志。"""

    def _report(exc_type, exc, tb):
        note_exception("Tk 回调", exc_type, exc, tb)

    try:
        root.report_callback_exception = _report
    except Exception:
        pass
