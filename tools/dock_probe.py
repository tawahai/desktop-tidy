# -*- coding: utf-8 -*-
"""开发用探针：检查"以贴边状态启动"时的窗口几何变化。"""

import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dt_config  # noqa: E402
import dt_winapi  # noqa: E402


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.02)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tidy_dock_"))
    cfg = dt_config.default_config()
    cfg["root"] = str(tmp / "收纳盒")
    cfg["panel"] = dt_config.default_panel()
    cfg["panel"].update({"docked": True, "dock_x": 300, "dock_w": 520})
    dt_config.config_path = lambda: tmp / "config.json"  # type: ignore[assignment]
    dt_config.appdata_dir = lambda: tmp  # type: ignore[assignment]
    dt_winapi.make_dpi_aware()

    import main as app_main

    app = app_main.App(cfg)
    panel = app.panel
    print("工作区:", dt_config.work_area(), "| 目标隐藏 外框y:", panel._hidden_frame_y())
    for step in (0.3, 0.6, 1.0, 1.5):
        pump(app, step)
        metrics = dt_winapi.window_metrics(panel)
        print(f"+{step}s -> 外框y={metrics['fy']} hidden={panel._hidden_frame_y()} "
              f"state={panel._dock_state} docked={panel.panel_cfg.get('docked')} "
              f"客户区={metrics['cw']}x{metrics['ch']}")
    panel.reveal()
    pump(app, 1.0)
    print("reveal 后 外框y =", dt_winapi.window_metrics(panel)["fy"], "state =", panel._dock_state)
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
