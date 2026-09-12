# Desktop Tidy (桌面收纳盒)

A lightweight **Windows desktop organizer**. All categories live in **one panel window**
instead of scattering folders across the desktop.

- Drag files from the desktop into a panel section to sort them (they are actually moved
  into real folders under `Desktop\收纳盒\`)
- Drop files onto the panel header to auto-classify them by file extension
- One-click "tidy the whole desktop", with one-click undo
- Hide the panel to the **system tray** (no taskbar button), or **dock it to the top edge**
  so it slides out only when the mouse touches the screen edge
- Optionally hide the Windows desktop icons so only the panel remains
- Auto-hide, panel position/size, per-section collapse state and settings are remembered

## Highlights for reviewers

| | |
| --- | --- |
| Language | Python 3.8+ (Windows 7 needs 3.8; 3.9+ dropped Win7 support) |
| Dependencies | **None** — standard library only (tkinter + ctypes) |
| OS | Windows 7 / 8 / 8.1 / 10 / 11, 32-bit and 64-bit |
| DPI | DPI-aware; tested 100%–150% scaling |
| Screens | Tested 1024×728 … 2560×1440; the panel always fits the monitor's work area |
| Multi-monitor | Docking and snapping use the work area of the monitor the window is on |
| Icons | The app icon (a yellow drawer) is **drawn in code** — no image assets |

Everything Windows-specific (real file icons via the shell API, tray icon, file drop,
desktop-icon toggle, per-monitor work area) is implemented with `ctypes`, so the project
has zero third-party dependencies.

## Run it

1. Double-click `启动.bat` (or `pythonw main.py`)
2. Drag desktop files into the panel sections
3. Right-click the tray icon for quick actions; click the window's × to hide it to the tray

`自检.bat` runs a self-test in a temporary folder (it never touches your real files).

## Build a standalone exe

Double-click `打包exe.bat` — it installs PyInstaller, generates `app.ico` from code and
produces `dist\桌面收纳盒.exe` (no Python required on the target machine).

## Documentation

The full documentation (features, settings, compatibility table, troubleshooting) is in
Chinese: **[README.md](README.md)**.

## License

MIT — see [LICENSE](LICENSE). Author: 唐小漫 (tawahai). Built with Codex.
