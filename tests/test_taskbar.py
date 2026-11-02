from datetime import datetime, timezone

from mimo_usage_monitor.display.taskbar import (
    Rect,
    TaskbarWidget,
    compute_placement,
    format_taskbar_text,
)
from mimo_usage_monitor.models import UsageSnapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def test_compute_placement_right_aligns_left_of_tray():
    taskbar = Rect(0, 1040, 1920, 40)
    tray = Rect(1700, 1040, 220, 40)
    r = compute_placement(taskbar, tray, widget_w=180, widget_h=30)
    assert r == Rect(1700 - 180 - 4, 1040 + (40 - 30) // 2, 180, 30)


def test_compute_placement_left_align_avoids_existing_content():
    taskbar = Rect(0, 1040, 1920, 40)
    tray = Rect(1700, 1040, 220, 40)
    r = compute_placement(taskbar, tray, align="left", left_x=240)
    assert r == Rect(240 + 8, 1040 + (40 - 30) // 2, 180, 30)
    r2 = compute_placement(taskbar, tray, align="left")
    assert r2.x == taskbar.x + 8


def test_format_taskbar_text():
    full = UsageSnapshot(
        fetched_at=NOW,
        remaining_pct=87.0,
        expire_at=datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc),
    )
    assert format_taskbar_text(full) == "余87% · 23d"
    # 剩余天数统一按北京口径计算（23:59:59Z = 北京次日 07:59）
    late = UsageSnapshot(
        fetched_at=NOW,
        remaining_pct=87.0,
        expire_at=datetime(2026, 11, 25, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert format_taskbar_text(late) == "余87% · 24d"
    pct_only = UsageSnapshot(fetched_at=NOW, remaining_pct=87.0)
    assert format_taskbar_text(pct_only) == "余87%"
    stale = UsageSnapshot(fetched_at=NOW, remaining_pct=87.0, is_stale=True)
    assert format_taskbar_text(stale) == "余87% ⚠"


class FakeWin32:
    def __init__(self, attach_ok=True):
        self.attach_ok = attach_ok
        self.restored = False

    def shell_tray_rect(self):
        return Rect(0, 1040, 1920, 40)

    def tray_notify_rect(self):
        return Rect(1700, 1040, 220, 40)

    def left_cluster_right_edge(self):
        return None

    def shrink_task_list(self, delta_w):
        return True

    def restore_task_list(self):
        self.restored = True

    def attach_to_taskbar(self, hwnd):
        return self.attach_ok


class FakeWindow:
    hwnd = 123

    def __init__(self):
        self.destroyed = False
        self.text = None

    def set_text(self, text):
        self.text = text

    def destroy(self):
        self.destroyed = True


def test_try_embed_failure_falls_back():
    win32 = FakeWin32(attach_ok=False)
    window = FakeWindow()
    widget = TaskbarWidget(win32=win32, window_factory=lambda rect: window)
    assert widget.try_embed() is False
    assert window.destroyed is True
    assert win32.restored is True
