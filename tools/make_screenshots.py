"""生成 README 用的工具效果截图。

只截取工具自身（悬浮条 / 托盘圆环图标），背景为纯色画布，不包含用户桌面内容。
数据来自 tests/fixtures（脱敏的接口样本）。输出到 docs/screenshots/。

用法：python tools/make_screenshots.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
BG = "#dcdce0"  # 中性浅灰画布
MARGIN = 20


def load_snapshot():
    from mimo_usage_monitor.models import parse_snapshot

    detail = json.loads(
        (ROOT / "tests" / "fixtures" / "tokenplan_detail.json").read_text("utf-8")
    )
    usage = json.loads(
        (ROOT / "tests" / "fixtures" / "tokenplan_usage.json").read_text("utf-8")
    )
    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)  # 固定时间，剩余天数稳定
    return parse_snapshot(detail, usage, now)


def shoot_bar(snap, size: tuple[int, int], out_name: str) -> None:
    from PIL import ImageGrab

    import tkinter as tk

    from mimo_usage_monitor.display.floating_bar import FloatingBar

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry("700x300+200+200")
    root.configure(bg=BG)
    root.deiconify()

    bar = FloatingBar({}, (260, 240, size[0], size[1]), 1.0, True, master=root)
    bar.update(snap)
    root.lift()
    root.update()

    # Tk/窗口坐标是逻辑像素，ImageGrab 抓的是物理像素：先量出 DPI 缩放比再换算
    full = ImageGrab.grab(all_screens=True)
    scale = full.width / root.winfo_screenwidth()
    x, y = bar._root.winfo_rootx(), bar._root.winfo_rooty()
    w, h = bar._root.winfo_width(), bar._root.winfo_height()
    m = round(MARGIN * scale)
    img = ImageGrab.grab(
        bbox=(
            round(x * scale) - m,
            round(y * scale) - m,
            round((x + w) * scale) + m,
            round((y + h) * scale) + m,
        ),
        all_screens=True,
    )
    img.save(OUT / out_name)
    bar.destroy()
    root.destroy()
    print(f"[saved] docs/screenshots/{out_name} ({img.width}x{img.height})")


def shoot_tray_icons() -> None:
    from PIL import Image

    from mimo_usage_monitor.display.tray import render_percent_icon

    size = 64
    pad = 16
    pcts = [65, 35, 12]  # 绿 / 黄 / 红 三态
    strip = Image.new("RGB", (len(pcts) * (size + pad) + pad, size + 2 * pad), BG)
    for i, pct in enumerate(pcts):
        icon = render_percent_icon(pct, size=size).convert("RGBA")
        strip.paste(icon, (pad + i * (size + pad), pad), icon)
    strip.save(OUT / "tray-icons.png")
    print(f"[saved] docs/screenshots/tray-icons.png ({strip.width}x{strip.height})")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    snap = load_snapshot()
    print(
        f"快照: {snap.plan_name} 剩余 {snap.remaining_pct}% "
        f"({snap.remaining_credits}/{snap.total_credits})"
    )
    shoot_bar(snap, (340, 44), "floating-bar.png")
    shoot_bar(snap, (150, 40), "floating-bar-narrow.png")
    shoot_tray_icons()


if __name__ == "__main__":
    main()
