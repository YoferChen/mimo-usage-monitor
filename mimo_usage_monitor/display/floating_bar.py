"""悬浮工具条：苹果暗色玻璃卡片风格。

信息随宽度渐进显示（宽：百分比+进度条+额度+剩余天；窄：只留百分比+进度条）。
窗口常驻任务栏之上（定期重申 topmost），Win11 圆角。
"""

import ctypes
import os

from ..models import BJ, UsageSnapshot

GREEN = "#30d158"
YELLOW = "#ffd60a"
RED = "#ff453a"
GRAY = "#98989d"
TRACK = "#3a3a3e"
CARD = "#1c1c1e"
FG = "#f5f5f7"
DIM = "#aeaeb2"


def format_credits(x: float) -> str:
    if x >= 1e6:
        return f"{x / 1e6:.1f}M"
    if x >= 1e3:
        return f"{x / 1e3:.1f}K"
    return f"{x:.0f}"


def pct_color(pct: float | None) -> str:
    if pct is None:
        return GRAY
    if pct >= 60:
        return GREEN
    if pct >= 20:
        return YELLOW
    return RED


def format_pct(s: UsageSnapshot) -> str:
    return "—" if s.remaining_pct is None else f"{s.remaining_pct:.0f}%"


def bar_ratio(s: UsageSnapshot | None) -> float | None:
    """已用比例（进度条填充量），0–1；无法计算返回 None。"""
    if s is None:
        return None
    if s.total_credits and s.used_credits is not None:
        return max(0.0, min(1.0, s.used_credits / s.total_credits))
    if s.remaining_pct is not None:
        return max(0.0, min(1.0, (100 - s.remaining_pct) / 100))
    return None


def tier_for_width(w: int) -> int:
    """2=宽（额度+天数）；1=中（天数）；0=窄（仅关键数据）。"""
    if w >= 340:
        return 2
    if w >= 200:
        return 1
    return 0


def extras_text(s: UsageSnapshot, tier: int) -> str:
    parts = []
    if (
        tier >= 2
        and s.remaining_credits is not None
        and s.total_credits is not None
    ):
        parts.append(
            f"{format_credits(s.remaining_credits)}/{format_credits(s.total_credits)}"
        )
    if tier >= 1 and s.expire_at is not None:
        days = (s.expire_at.astimezone(BJ).date() - s.fetched_at.astimezone(BJ).date()).days
        parts.append(f"{days}d")
    if s.is_stale:
        parts.append("⚠")
    return "  ".join(parts)


class FloatingBar:
    def __init__(
        self,
        callbacks: dict,
        rect: tuple[int, int, int, int],
        opacity: float,
        locked: bool,
        master=None,
        font_family: str = "Segoe UI",
        font_size: int = 13,
    ) -> None:
        import tkinter as tk

        self._tk = tk
        self._callbacks = callbacks
        self._locked = locked
        self._font_family = font_family
        self._font_size = font_size
        self._snapshot: UsageSnapshot | None = None
        self._press_offset = (0, 0)
        self._root = tk.Toplevel(master) if master is not None else tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.geometry(f"{rect[2]}x{rect[3]}+{rect[0]}+{rect[1]}")
        self._root.wm_attributes("-alpha", opacity)
        self._root.configure(bg=CARD)

        self._ring = tk.Label(self._root, bg=CARD)
        self._ring.pack(side="left", fill="y", padx=(8, 2))

        self._pct = tk.Label(
            self._root,
            text="—",
            font=(font_family, font_size, "bold"),
            bg=CARD,
            fg=FG,
        )
        self._pct.pack(side="left", fill="y")

        self._extras = tk.Label(
            self._root,
            text="",
            font=(font_family, max(7, font_size - 5)),
            bg=CARD,
            fg=DIM,
        )
        self._extras.pack(side="left", fill="y", padx=(2, 8))

        self._resize_origin = (0, 0, 0, 0)
        self._grip = tk.Frame(
            self._root, width=10, height=10, cursor="size_nw_se", bg="#48484a"
        )
        self._grip.place(relx=1.0, rely=1.0, anchor="se")
        self._grip.bind("<Button-1>", self._on_resize_start)
        self._grip.bind("<B1-Motion>", self._on_resize_motion)

        self._root.bind("<Button-1>", self._on_press)
        self._root.bind("<B1-Motion>", self._on_drag)
        self._root.bind("<Double-Button-1>", lambda _e: self._fire("on_open_console"))
        self._root.bind("<Button-3>", self._on_menu)
        self._root.bind("<Configure>", self._relayout)

        self._apply_rounded_corners()
        self._keep_topmost()

    # ---------- 布局与绘制 ----------

    def _relayout(self, _event=None) -> None:
        w = self._root.winfo_width()
        tier = tier_for_width(w)
        if self._snapshot is not None:
            self._extras.configure(text=extras_text(self._snapshot, tier))

    def _update_ring(self, pct: float | None) -> None:
        """托盘同款圆环扇形图（render_percent_icon 复用同一视觉语言）。"""
        try:
            from PIL import ImageTk

            from .tray import render_percent_icon

            size = max(18, self._font_size + 8)
            self._ring_img = ImageTk.PhotoImage(render_percent_icon(pct, size=size))
            self._ring.configure(image=self._ring_img)
        except Exception:
            pass

    def update(self, s: UsageSnapshot) -> None:
        self._snapshot = s
        self._pct.configure(text=format_pct(s), fg=pct_color(s.remaining_pct))
        self._update_ring(s.remaining_pct)
        self._relayout()

    # ---------- 交互 ----------

    def _fire(self, name: str) -> None:
        cb = self._callbacks.get(name)
        if cb:
            cb()

    def _on_press(self, event) -> None:
        self._press_offset = (
            event.x_root - self._root.winfo_x(),
            event.y_root - self._root.winfo_y(),
        )

    def _on_drag(self, event) -> None:
        if self._locked:
            return
        x = event.x_root - self._press_offset[0]
        y = event.y_root - self._press_offset[1]
        self._root.geometry(f"+{x}+{y}")

    def _on_resize_start(self, event):
        self._resize_origin = (
            event.x_root,
            event.y_root,
            self._root.winfo_width(),
            self._root.winfo_height(),
        )
        return "break"

    def _on_resize_motion(self, event):
        ox, oy, w0, h0 = self._resize_origin
        w = max(110, w0 + event.x_root - ox)
        h = max(24, h0 + event.y_root - oy)
        self._root.geometry(f"{w}x{h}")
        return "break"

    def _on_menu(self, event) -> None:
        menu = self._tk.Menu(self._root, tearoff=0, bg=CARD, fg=FG)
        for name, label in (
            ("on_refresh", "立即刷新"),
            ("on_open_console", "打开控制台"),
            ("on_toggle_floating", "隐藏悬浮条"),
            ("on_toggle_notify", "额度提醒"),
            ("on_open_settings", "设置…"),
            ("on_quit", "退出"),
        ):
            menu.add_command(label=label, command=lambda n=name: self._fire(n))
        menu.tk_popup(event.x_root, event.y_root)

    # ---------- 平台特性 ----------

    def _resolve_hwnd(self) -> int:
        if os.name != "nt":
            return 0
        wid = self._root.winfo_id()
        parent = ctypes.windll.user32.GetParent(wid)
        return parent if parent else wid

    def _apply_rounded_corners(self) -> None:
        """Win11 DWM 圆角（2 = DWMWCP_ROUND）。"""
        if os.name != "nt":
            return
        try:
            hwnd = self._resolve_hwnd()
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except Exception:
            pass

    def _keep_topmost(self) -> None:
        """任务栏本身也是 topmost 窗口，点击它会盖住我们——定期重申置顶。"""
        try:
            self._root.attributes("-topmost", True)
            self._root.after(1500, self._keep_topmost)
        except Exception:
            pass

    # ---------- 外部控制 ----------

    def set_locked(self, locked: bool) -> None:
        self._locked = locked

    def apply_font(self, family: str, size: int) -> None:
        self._font_family, self._font_size = family, size
        self._pct.configure(font=(family, size, "bold"))
        self._extras.configure(font=(family, max(7, size - 5)))
        if self._snapshot is not None:
            self._update_ring(self._snapshot.remaining_pct)

    def apply_opacity(self, opacity: float) -> None:
        self._root.wm_attributes("-alpha", opacity)

    def rect(self) -> tuple[int, int, int, int]:
        return (
            self._root.winfo_x(),
            self._root.winfo_y(),
            self._root.winfo_width(),
            self._root.winfo_height(),
        )

    def destroy(self) -> None:
        self._root.destroy()
