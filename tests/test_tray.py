from datetime import datetime, timedelta, timezone

from mimo_usage_monitor.display.tray import format_tooltip, render_percent_icon
from mimo_usage_monitor.models import UsageSnapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)  # 北京 20:00，非高峰外
BJ = timezone(timedelta(hours=8))

GREEN = (34, 197, 94)
YELLOW = (234, 179, 8)
RED = (239, 68, 68)
GRAY = (156, 163, 175)


def _top_pixels(img):
    w, _h = img.size
    return [img.getpixel((w // 2, y))[:3] for y in range(0, w // 2)]


def _assert_color_near(pixels, expected, tol=10):
    assert any(
        all(abs(p[i] - expected[i]) <= tol for i in range(3)) for p in pixels
    ), f"未在环顶找到颜色 {expected}，采样: {pixels[:12]}"


def test_render_icon_colors():
    for pct, color in ((80, GREEN), (40, YELLOW), (10, RED), (None, GRAY)):
        img = render_percent_icon(pct)
        _assert_color_near(_top_pixels(img), color)


def test_render_icon_size():
    img = render_percent_icon(50, size=64)
    assert img.size == (64, 64)


def test_format_tooltip_lines():
    s = UsageSnapshot(
        fetched_at=NOW,
        plan_name="Standard",
        remaining_pct=45.3,
        remaining_credits=4_981_186_538.0,
        total_credits=11_000_000_000.0,
        expire_at=datetime(2026, 11, 13, 23, 59, 59, tzinfo=BJ),
        month_used_credits=6_018_813_462.0,
    )
    assert format_tooltip(s) == (
        "Standard\n"
        "剩余 45.3%（4,981,186,538 / 11,000,000,000 Credits）\n"
        "到期 2026-11-13\n"
        "本月消耗 6,018,813,462"
    )


def test_format_tooltip_offpeak():
    s = UsageSnapshot(
        fetched_at=datetime(2026, 11, 2, 3, 0, tzinfo=BJ),  # 北京 3 点
        remaining_pct=50.0,
    )
    assert "非高峰时段（0.8x）" in format_tooltip(s)


def test_format_tooltip_stale():
    s = UsageSnapshot(fetched_at=NOW, remaining_pct=50.0, is_stale=True)
    assert "⚠ 数据过期" in format_tooltip(s)
