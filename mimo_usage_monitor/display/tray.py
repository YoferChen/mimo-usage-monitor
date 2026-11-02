from PIL import Image, ImageDraw

from ..models import UsageSnapshot, is_offpeak
from ..notify import NotifierSink

GREEN = (34, 197, 94)
YELLOW = (234, 179, 8)
RED = (239, 68, 68)
GRAY = (156, 163, 175)
TRACK = (68, 68, 68)


def _ring_color(pct: float | None) -> tuple[int, int, int]:
    if pct is None:
        return GRAY
    if pct >= 60:
        return GREEN
    if pct >= 20:
        return YELLOW
    return RED


def render_percent_icon(pct: float | None, size: int = 64) -> Image.Image:
    """圆环起于 12 点顺时针，颜色随剩余百分比渐变。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size * 0.1
    width = max(2, int(size * 0.16))
    box = (pad, pad, size - pad, size - pad)
    if pct is None:
        draw.arc(box, 0, 360, fill=GRAY + (255,), width=width)
    else:
        draw.arc(box, 0, 360, fill=TRACK + (255,), width=width)
        clamped = min(max(pct, 0.0), 100.0)
        draw.arc(box, -90, -90 + 360 * clamped / 100, fill=_ring_color(pct) + (255,), width=width)
    return img


def format_tooltip(s: UsageSnapshot) -> str:
    lines = []
    if s.plan_name:
        lines.append(s.plan_name)
    if s.remaining_pct is not None:
        line = f"剩余 {s.remaining_pct:.1f}%"
        if s.remaining_credits is not None and s.total_credits is not None:
            line += (
                f"（{s.remaining_credits:,.0f} / {s.total_credits:,.0f} Credits）"
            )
        lines.append(line)
    if s.expire_at is not None:
        lines.append(f"到期 {s.expire_at.date().isoformat()}")
    if s.today_used_credits is not None:
        lines.append(f"今日消耗 {s.today_used_credits:,.0f}")
    if s.month_used_credits is not None:
        lines.append(f"本月消耗 {s.month_used_credits:,.0f}")
    if s.rate_limit_note:
        lines.append(s.rate_limit_note)
    if is_offpeak(s.fetched_at):
        lines.append("非高峰时段（0.8x）")
    if s.is_stale:
        lines.append("⚠ 数据过期")
    return "\n".join(lines)


class TrayDisplay:
    """系统托盘百分比环图标；notify() 即 NotifierSink（气泡通知）。"""

    def __init__(self, menu_items: list, on_notify: NotifierSink | None = None) -> None:
        import pystray

        self._pystray = pystray
        self._on_notify = on_notify
        self._snapshot: UsageSnapshot | None = None

        def build_item(item):
            if len(item) == 2:
                label, action = item
                checked = None
            else:
                label, action, checked = item
            if action is None and checked is None and label == "sep":
                return pystray.Menu.SEPARATOR
            kwargs = {}
            if checked is not None:
                kwargs["checked"] = lambda _item, fn=checked: fn()
            return pystray.MenuItem(label, action, **kwargs)

        menu = pystray.Menu(*[build_item(item) for item in menu_items])
        self._icon = pystray.Icon(
            "mimo-usage-monitor",
            icon=render_percent_icon(None),
            title="MiMo Token Plan",
            menu=menu,
        )

    def run_detached(self) -> None:
        self._icon.run_detached()

    def update(self, s: UsageSnapshot) -> None:
        self._snapshot = s
        self._icon.icon = render_percent_icon(s.remaining_pct)
        self._icon.title = format_tooltip(s)[:120]

    def notify(self, title: str, body: str) -> None:
        try:
            self._icon.notify(message=body, title=title)
        except Exception:
            if self._on_notify is not None:
                self._on_notify.notify(title, body)

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass
