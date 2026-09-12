# Desktop Tidy (桌面收纳盒)

A lightweight **Windows desktop organizer**: every category lives inside **one panel window**,
so your desktop keeps a single window instead of scattered folders.

Drag files from the desktop into a section and they are moved into a real folder
(`Desktop\收纳盒\<category>\`), auto-classified by extension. Hide the panel to the
**system tray**, or **dock it to the top edge** of the screen so it slides out only when
your mouse touches the edge.

![Main panel](docs/screenshot-main.png)

## Features

- **Single panel, many sections** — 文档 / 图片 / 视频 / 音频 / 压缩包 / 程序 / 快捷方式 / 其他,
  each one a card you can collapse, rename, recolor, reorder, add or remove
- **Drag & drop** — drag files in from Explorer; drag a file between sections to re-classify it
- **Drop on the header** to auto-classify a whole batch by file extension
- **Tidy the whole desktop** with one click and **undo** it with another; preview before running it
- **System tray** — a permanent tray icon and **no taskbar button at all** (the window uses the
  TOOLWINDOW style, so it stays out of the taskbar and Alt+Tab)
- **Edge auto-hide** — drag the panel to the top of the screen and it tucks away leaving a
  6-pixel strip; touch the screen edge and it slides back out
- **Hide the Windows desktop icons** so only the panel remains
- **Remembers everything** — panel position and size, current tab, per-section collapsed
  state, icon size, transparency, auto-start
- **Real Windows file icons** extracted from the shell, including program and shortcut icons
- The application icon (a yellow drawer) is **drawn in code** — no image assets

![Settings](docs/screenshot-settings.png)

## Requirements and compatibility

| | |
| --- | --- |
| OS | Windows 7 / 8 / 8.1 / 10 / 11, 32-bit and 64-bit |
| Python | 3.8+ (Windows 7 needs 3.8 — Python 3.9 dropped Win7 support) |
| Dependencies | **None** — Python standard library only (tkinter + ctypes) |
| DPI | DPI-aware; tested at 100% / 125% / 150% scaling |
| Screen | Tested from 1024×728 up to 2560×1440; the panel always fits the monitor work area |
| Multi-monitor | Docking, snapping and small-screen fitting use the work area of the monitor the window is on |
| Fonts | Picks an available Chinese font automatically (YaHei UI → YaHei → SimHei → Tahoma) |

The dark title bar and rounded corners are used on Windows 10 1809+ and Windows 11, and
degrade gracefully to the system default look elsewhere. Nothing else depends on the OS version.

## Run it

1. Double-click `启动.bat` (or run `pythonw main.py`)
2. Drag desktop files into the panel sections
3. Click the window's × to hide it to the tray; click the tray icon to bring it back

`自检.bat` runs a self-test in a temporary folder — it never touches your real files.

## Typical operations

| What you want | How |
| --- | --- |
| Store a file | Drag it from the desktop onto a section |
| Auto-classify | Drop files on the panel header (the empty area next to the title) |
| Re-classify | Drag a file from one section onto another |
| Collapse a section | Click its title row |
| Tidy the desktop | 「一键整理桌面」 (with preview and one-click undo) |
| Edge auto-hide | Drag the panel title to the top of the screen, or press 「贴边隐藏」 |
| Hide to tray | Click × (configurable: hide to tray, or exit) |
| Multi-select | Ctrl+click; Delete sends the selection to the Recycle Bin |
| Scroll | Mouse wheel anywhere in the panel, or drag the slim scrollbar |

## Where things live

- Everything you store: `Desktop\收纳盒\` (changeable in Settings)
- Configuration: `%APPDATA%\DesktopTidy\config.json`
- Undo history: `%APPDATA%\DesktopTidy\history\`
- Logs: `%APPDATA%\DesktopTidy\crash.log`, `tray_error.log`, and `tray.log`
  (a 30-second heartbeat plus every tray action)

Classification rules can be extended in the config file: `rules` holds the defaults and
`custom_rules` adds your own extensions, e.g. `"设计": [".psd", ".ai", ".fig"]`
(create a matching section in Settings).

## Build a standalone exe

Double-click `打包exe.bat`: it installs PyInstaller, generates `app.ico` from code and
produces `dist\桌面收纳盒.exe` — no Python needed on the target machine.

Tagged releases are built automatically by GitHub Actions (`.github/workflows/build.yml`)
and attached to the release as `DesktopTidy.exe`.

## Project layout

| File | Purpose |
| --- | --- |
| `main.py` | Entry point: wiring for config, tray, panel and file operations |
| `dt_panel.py` | The panel window: sections, icon grid, drag & drop, edge docking |
| `dt_control.py` | Settings view (including the About section) |
| `dt_ui.py` | Shared widgets: palette, buttons, slim scrollbar, wheel support, confirm dialog |
| `dt_icon.py` | The drawer icon, drawn in code; also writes `app.ico` |
| `dt_tray.py` | Tray icon and tray menu |
| `dt_config.py` | Config, paths, default rules, version info |
| `dt_organize.py` | Classification, file moves, undo history |
| `dt_winapi.py` | Windows layer: icons, DPI, monitors, desktop-icon toggle, file drop |
| `selftest.py` | Self-test (temporary folders only) |
| `tools/` | Development probes: UI smoke test, tray/menu probes, screenshot generator |

## Troubleshooting

- **The panel disappeared** — it is either hidden in the tray (click the tray icon) or docked
  to the top edge (touch the top edge of the screen within the panel's width)
- **No tray icon** — Windows 11 hides new tray icons in the overflow flyout; drag it out, or
  enable it in Settings → Personalization → Taskbar
- **The program exited by itself** — check `%APPDATA%\DesktopTidy\tray.log`; it records a
  heartbeat every 30 seconds, every tray action and the caller of any exit

## Documentation

Full documentation (Chinese): [README.md](README.md).

## License

MIT — see [LICENSE](LICENSE).

Author: 唐小漫 (tawahai) · Built with [Codex](https://openai.com/codex).
