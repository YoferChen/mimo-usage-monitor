from datetime import datetime, timezone

from mimo_usage_monitor.display.floating_bar import format_bar_text, format_credits
from mimo_usage_monitor.models import UsageSnapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def test_format_bar_text_full():
    s = UsageSnapshot(
        fetched_at=NOW,
        remaining_pct=73.5,
        remaining_credits=4_500_000.0,
        total_credits=12_300_000.0,
        expire_at=datetime(2026, 11, 13, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert (
        format_bar_text(s)
        == "剩余 73.5% ▓▓▓▓▓▓▓░░░ · 4.5M / 12.3M Credits · 到期 2026-11-13"
    )


def test_format_bar_text_partial_fields():
    s = UsageSnapshot(fetched_at=NOW, remaining_pct=42.0)
    assert format_bar_text(s) == "剩余 42.0% ▓▓▓▓░░░░░░"


def test_format_bar_text_stale_suffix():
    s = UsageSnapshot(fetched_at=NOW, remaining_pct=50.0, is_stale=True)
    assert format_bar_text(s).endswith(" ⚠ 已过期")


def test_format_credits():
    assert format_credits(12_300_000) == "12.3M"
    assert format_credits(8_500) == "8.5K"
    assert format_credits(420) == "420"
