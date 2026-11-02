from datetime import datetime, timedelta, timezone

from mimo_usage_monitor.display.floating_bar import (
    bar_ratio,
    extras_text,
    format_credits,
    format_pct,
    pct_color,
    tier_for_width,
    GREEN,
    GRAY,
    RED,
    YELLOW,
)
from mimo_usage_monitor.models import UsageSnapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)  # 北京 20:00
BJ = timezone(timedelta(hours=8))

FULL = UsageSnapshot(
    fetched_at=NOW,
    remaining_pct=45.3,
    remaining_credits=4_500_000.0,
    total_credits=12_300_000.0,
    used_credits=7_800_000.0,
    expire_at=datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc),
)


def test_pct_color_tiers():
    assert pct_color(80) == GREEN
    assert pct_color(40) == YELLOW
    assert pct_color(10) == RED
    assert pct_color(None) == GRAY


def test_format_pct():
    assert format_pct(FULL) == "45%"
    assert format_pct(UsageSnapshot(fetched_at=NOW)) == "—"


def test_bar_ratio_prefers_credits():
    assert bar_ratio(FULL) == 7_800_000 / 12_300_000
    only_pct = UsageSnapshot(fetched_at=NOW, remaining_pct=25.0)
    assert bar_ratio(only_pct) == 0.75
    assert bar_ratio(None) is None


def test_tier_for_width():
    assert tier_for_width(400) == 2
    assert tier_for_width(250) == 1
    assert tier_for_width(120) == 0


def test_extras_text_tiers():
    assert extras_text(FULL, 2) == "4.5M/12.3M  23d"
    assert extras_text(FULL, 1) == "23d"
    assert extras_text(FULL, 0) == ""


def test_extras_text_stale_mark():
    stale = UsageSnapshot(fetched_at=NOW, remaining_pct=50.0, is_stale=True)
    assert "⚠" in extras_text(stale, 0)


def test_format_credits():
    assert format_credits(12_300_000) == "12.3M"
    assert format_credits(8_500) == "8.5K"
    assert format_credits(420) == "420"
