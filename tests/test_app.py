import threading
import time
from datetime import datetime, timezone

from mimo_usage_monitor.app import (
    RefreshLoop,
    acquire_single_instance,
    backoff_wait,
    clamp_floating_rect,
)
from mimo_usage_monitor.models import UsageSnapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
SNAP = UsageSnapshot(
    fetched_at=NOW,
    plan_name="Standard",
    remaining_pct=50.0,
    remaining_credits=50.0,
    total_credits=100.0,
)


def test_acquire_single_instance_second_call_false():
    name = "Local\\mimo-usage-monitor-test-mutex"
    assert acquire_single_instance(name) is True
    assert acquire_single_instance(name) is False


def test_refresh_loop_invokes_callbacks():
    got = []
    done = threading.Event()

    def fetch():
        got.append(1)
        if len(got) >= 2:
            done.set()
        return SNAP

    loop = RefreshLoop(fetch, 0.05, on_snapshot=lambda s: None, on_error=lambda e: None)
    loop.start()
    try:
        assert done.wait(5)
    finally:
        loop.stop()
    assert len(got) >= 2


def test_refresh_loop_backoff_on_error():
    waits = []
    errors = []
    stopper = threading.Event()

    def fetch():
        raise RuntimeError("boom")

    def sleep(secs):
        waits.append(secs)
        if len(waits) >= 2:
            stopper.set()

    loop = RefreshLoop(
        fetch, 60, on_snapshot=lambda s: None, on_error=errors.append, sleep=sleep
    )
    loop.start()
    try:
        assert stopper.wait(5)
    finally:
        loop.stop()
    assert waits[:2] == [60, 120]
    assert len(errors) >= 2


def test_stale_marking_when_fetch_fails():
    snaps = []
    done = threading.Event()
    results = [SNAP, RuntimeError("down")]

    def fetch():
        r = results.pop(0) if results else RuntimeError("down")
        if isinstance(r, Exception):
            raise r
        return r

    def on_snapshot(s):
        snaps.append(s)
        if len(snaps) >= 2:
            done.set()

    loop = RefreshLoop(fetch, 0.05, on_snapshot=on_snapshot, on_error=lambda e: None)
    loop.start()
    try:
        assert done.wait(5)
    finally:
        loop.stop()
    assert snaps[0].is_stale is False
    assert snaps[1].is_stale is True
    assert snaps[1].plan_name == "Standard"
    assert snaps[1].remaining_pct == 50.0


def test_backoff_wait_capped_at_300():
    assert backoff_wait(60, 1) == 60
    assert backoff_wait(60, 2) == 120
    assert backoff_wait(60, 4) == 300
    assert backoff_wait(60, 1000) == 300  # 指数不溢出


def test_trigger_now_shortens_wait():
    got = []
    done = threading.Event()

    def fetch():
        got.append(time.monotonic())
        if len(got) >= 2:
            done.set()
        return SNAP

    loop = RefreshLoop(fetch, 60, on_snapshot=lambda s: None, on_error=lambda e: None)
    loop.start()
    try:
        time.sleep(0.3)  # 第一帧完成，进入 60s 等待
        loop.trigger_now()
        assert done.wait(5)
    finally:
        loop.stop()
    assert len(got) >= 2


FULLSCREEN_VROOT = (0, 0, 1600, 1000)


def test_clamp_rect_unplaced_returns_none():
    assert clamp_floating_rect((0, 0, 126, 40), FULLSCREEN_VROOT) is None


def test_clamp_rect_off_screen_returns_none():
    # 实际踩过的坑：位置保存于旧的大屏（y=1945），换到 1600x1000 后整体在屏外
    assert clamp_floating_rect((600, 1945, 126, 40), FULLSCREEN_VROOT) is None
    assert clamp_floating_rect((2000, 500, 126, 40), FULLSCREEN_VROOT) is None
    assert clamp_floating_rect((-200, -100, 126, 40), FULLSCREEN_VROOT) is None


def test_clamp_rect_visible_is_kept():
    rect = (600, 500, 126, 40)
    assert clamp_floating_rect(rect, FULLSCREEN_VROOT) == rect


def test_clamp_rect_multi_monitor_negative_coords_kept():
    rect = (-800, 200, 126, 40)  # 主屏左侧的副屏
    assert clamp_floating_rect(rect, (-1280, 0, 2880, 1000)) == rect
