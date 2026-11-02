from mimo_usage_monitor.app import RefreshLoop
from mimo_usage_monitor.config import AppConfig
from mimo_usage_monitor.settings import RUN_KEY, apply_settings, set_autostart


def test_apply_settings_clamps():
    cfg = AppConfig()
    values = {
        "refresh_interval_s": 5,
        "threshold_pct": 150.0,
        "floating_opacity": 0.1,
    }
    new = apply_settings(cfg, values)
    assert new.refresh_interval_s == 30
    assert new.threshold_pct == 100.0
    assert new.floating_opacity == 0.3


def test_apply_settings_updates_toggles():
    cfg = AppConfig()
    new = apply_settings(
        cfg,
        {
            "show_tray": False,
            "show_floating": False,
            "show_taskbar": True,
            "notify_enabled": False,
            "autostart": True,
            "floating_locked": True,
        },
    )
    assert new.show_tray is False
    assert new.show_floating is False
    assert new.show_taskbar is True
    assert new.notify_enabled is False
    assert new.autostart is True
    assert new.floating_locked is True


class FakeReg:
    def __init__(self):
        self.calls = []

    def set_value(self, path, name, value):
        self.calls.append(("set", path, name, value))

    def delete_value(self, path, name):
        self.calls.append(("delete", path, name, None))


def test_set_autostart_writes_run_key():
    reg = FakeReg()
    set_autostart(True, "pythonw -m mimo_usage_monitor", reg_writer=reg)
    set_autostart(False, "pythonw -m mimo_usage_monitor", reg_writer=reg)
    assert reg.calls == [
        ("set", RUN_KEY, "MimoUsageMonitor", "pythonw -m mimo_usage_monitor"),
        ("delete", RUN_KEY, "MimoUsageMonitor", None),
    ]


def test_apply_settings_taskbar_align():
    cfg = AppConfig()
    assert apply_settings(cfg, {"taskbar_align": "left"}).taskbar_align == "left"
    assert apply_settings(cfg, {"taskbar_align": "diagonal"}).taskbar_align == "right"


def test_refresh_loop_set_interval():
    loop = RefreshLoop(lambda: None, 60, lambda s: None, lambda e: None)
    loop.set_interval(30)
    assert loop._interval == 30
