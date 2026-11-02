import sys
from dataclasses import replace
from pathlib import Path

from .config import AppConfig

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MimoUsageMonitor"

_BOOL_KEYS = (
    "show_tray",
    "show_floating",
    "show_taskbar",
    "notify_enabled",
    "autostart",
    "floating_locked",
)


def apply_settings(cfg: AppConfig, values: dict) -> AppConfig:
    """表单值 → 新配置（纯函数，含 clamp）。"""
    updates = {}
    if "refresh_interval_s" in values:
        updates["refresh_interval_s"] = max(30, min(600, int(values["refresh_interval_s"])))
    if "threshold_pct" in values:
        updates["threshold_pct"] = max(0.0, min(100.0, float(values["threshold_pct"])))
    if "floating_opacity" in values:
        updates["floating_opacity"] = max(0.3, min(1.0, float(values["floating_opacity"])))
    if values.get("taskbar_align") in ("left", "right"):
        updates["taskbar_align"] = values["taskbar_align"]
    for key in _BOOL_KEYS:
        if key in values:
            updates[key] = bool(values[key])
    return replace(cfg, **updates)


class WinRegWriter:
    def set_value(self, path: str, name: str, value: str) -> None:
        import winreg

        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(key)

    def delete_value(self, path: str, name: str) -> None:
        import winreg

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE)
        except OSError:
            return
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)


def set_autostart(enabled: bool, command: str, reg_writer=None) -> None:
    writer = reg_writer if reg_writer is not None else WinRegWriter()
    if enabled:
        writer.set_value(RUN_KEY, RUN_NAME, command)
    else:
        writer.delete_value(RUN_KEY, RUN_NAME)


def default_command() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    target = pythonw if pythonw.exists() else exe
    return f'"{target}" -m mimo_usage_monitor'


class SettingsDialog:
    """设置表单：间隔 / 阈值 / 透明度 / 形态开关 / 通知 / 自启。确定 → on_apply(values)。"""

    def __init__(self, master, cfg: AppConfig, on_apply) -> None:
        import tkinter as tk

        self._result: dict = {}
        win = tk.Toplevel(master)
        win.title("设置")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        body = tk.Frame(win, padx=12, pady=10)
        body.pack(fill="both", expand=True)

        def row(label):
            f = tk.Frame(body)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=label, width=12, anchor="w").pack(side="left")
            return f

        f = row("刷新间隔（秒）")
        interval = tk.Spinbox(f, from_=30, to=600, width=6)
        interval.delete(0, "end")
        interval.insert(0, str(cfg.refresh_interval_s))
        interval.pack(side="left")

        f = row("提醒阈值（%）")
        threshold = tk.Spinbox(f, from_=0, to=100, width=6)
        threshold.delete(0, "end")
        threshold.insert(0, f"{cfg.threshold_pct:g}")
        threshold.pack(side="left")

        f = row("透明度")
        opacity = tk.Scale(f, from_=0.3, to=1.0, resolution=0.05, orient="horizontal")
        opacity.set(cfg.floating_opacity)
        opacity.pack(side="left", fill="x", expand=True)

        f = row("任务栏位置")
        align_var = tk.StringVar(value="左侧" if cfg.taskbar_align == "left" else "右侧")
        tk.OptionMenu(f, align_var, "左侧", "右侧").pack(side="left")

        checks = {}
        for key, label in (
            ("show_floating", "悬浮工具条"),
            ("show_taskbar", "任务栏部件"),
            ("show_tray", "显示托盘图标"),
            ("notify_enabled", "额度提醒"),
            ("floating_locked", "锁定悬浮条位置"),
            ("autostart", "开机自启"),
        ):
            var = tk.BooleanVar(value=getattr(cfg, key))
            tk.Checkbutton(body, text=label, variable=var).pack(anchor="w")
            checks[key] = var

        def on_ok():
            values = {
                "refresh_interval_s": int(interval.get()),
                "threshold_pct": float(threshold.get()),
                "floating_opacity": float(opacity.get()),
                "taskbar_align": "left" if align_var.get() == "左侧" else "right",
            }
            values.update({key: var.get() for key, var in checks.items()})
            win.destroy()
            on_apply(values)

        tk.Button(body, text="确定", command=on_ok).pack(pady=(8, 0))
        win.grab_set()
