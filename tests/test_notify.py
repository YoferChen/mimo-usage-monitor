from datetime import datetime, timezone

from mimo_usage_monitor.models import UsageSnapshot
from mimo_usage_monitor.notify import ThresholdNotifier, threshold_message

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def snap(pct, remaining=50.0, total=1000.0):
    return UsageSnapshot(
        fetched_at=NOW,
        remaining_pct=pct,
        remaining_credits=remaining,
        total_credits=total,
    )


def test_fires_once_on_crossing_below():
    n = ThresholdNotifier(threshold_pct=20)
    assert n.update(snap(25)) is False   # 高于阈值
    assert n.update(snap(15)) is True    # 跌破，触发
    assert n.update(snap(9)) is False    # 仍低于，静默


def test_silent_while_still_below():
    n = ThresholdNotifier(threshold_pct=10)
    results = [n.update(snap(5)) for _ in range(5)]
    assert results == [True, False, False, False, False]


def test_rearms_above_plus_delta_then_fires_again():
    n = ThresholdNotifier(threshold_pct=10)
    assert n.update(snap(9)) is True
    assert n.update(snap(11.9)) is False   # 未达 12，不重武装
    assert n.update(snap(12.0)) is False   # 重武装但不弹
    assert n.update(snap(9)) is True       # 再次跌破，再弹


def test_startup_below_fires_once():
    n = ThresholdNotifier(threshold_pct=10)
    assert n.update(snap(5), at_startup=True) is True
    assert n.update(snap(5)) is False


def test_no_fire_when_pct_unknown():
    n = ThresholdNotifier(threshold_pct=10)
    assert n.update(snap(None)) is False
    assert n.update(snap(None), at_startup=True) is False


def test_threshold_message():
    title, body = threshold_message(snap(5.0, remaining=50.0, total=1000.0))
    assert title == "MiMo Token Plan 额度不足"
    assert body == "剩余 5.0%（50 / 1000 Credits）"
