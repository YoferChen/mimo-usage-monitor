from ..models import UsageSnapshot


def format_credits(x: float) -> str:
    if x >= 1e6:
        return f"{x / 1e6:.1f}M"
    if x >= 1e3:
        return f"{x / 1e3:.1f}K"
    return f"{x:.0f}"


def format_bar_text(s: UsageSnapshot) -> str:
    segments = []
    if s.remaining_pct is not None:
        filled = min(10, max(0, int(s.remaining_pct // 10)))
        bar = "▓" * filled + "░" * (10 - filled)
        segments.append(f"剩余 {s.remaining_pct:.1f}% {bar}")
    if s.remaining_credits is not None and s.total_credits is not None:
        segments.append(
            f"{format_credits(s.remaining_credits)} / "
            f"{format_credits(s.total_credits)} Credits"
        )
    if s.expire_at is not None:
        segments.append(f"到期 {s.expire_at.date().isoformat()}")
    text = " · ".join(segments)
    if s.is_stale:
        text += " ⚠ 已过期"
    return text


class FloatingBar:
    """置顶无边框悬浮工具条：可拖动、可锁定、双击打开控制台、右键菜单。"""

    def __init__(
        self,
        callbacks: dict,
        rect: tuple[int, int, int, int],
        opacity: float,
        locked: bool,
    ) -> None:
        import tkinter as tk

        self._tk = tk
        self._callbacks = callbacks
        self._locked = locked
        self._press_offset = (0, 0)
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.geometry(f"{rect[2]}x{rect[3]}+{rect[0]}+{rect[1]}")
        self._root.wm_attributes("-alpha", opacity)
        self._label = tk.Label(
            self._root,
            text="—",
            anchor="w",
            font=("Microsoft YaHei UI", 10),
            bg="#1e1e2e",
            fg="#e0e0e0",
            padx=10,
            pady=6,
        )
        self._label.pack(fill="both", expand=True)
        self._root.bind("<Button-1>", self._on_press)
        self._root.bind("<B1-Motion>", self._on_drag)
        self._root.bind("<Double-Button-1>", lambda _e: self._fire("on_open_console"))
        self._root.bind("<Button-3>", self._on_menu)

    def _fire(self, name: str) -> None:
        cb = self._callbacks.get(name)
        if cb:
            cb()

    def _on_press(self, event) -> None:
        self._press_offset = (event.x_root - self._root.winfo_x(),
                              event.y_root - self._root.winfo_y())

    def _on_drag(self, event) -> None:
        if self._locked:
            return
        x = event.x_root - self._press_offset[0]
        y = event.y_root - self._press_offset[1]
        self._root.geometry(f"+{x}+{y}")

    def _on_menu(self, event) -> None:
        menu = self._tk.Menu(self._root, tearoff=0)
        for name, label in (
            ("on_refresh", "立即刷新"),
            ("on_open_console", "打开控制台"),
            ("on_toggle_taskbar", "任务栏部件"),
            ("on_toggle_notify", "额度提醒"),
            ("on_open_settings", "设置…"),
            ("on_quit", "退出"),
        ):
            menu.add_command(label=label, command=lambda n=name: self._fire(n))
        menu.tk_popup(event.x_root, event.y_root)

    def update(self, s: UsageSnapshot) -> None:
        self._label.configure(text=format_bar_text(s))

    def set_locked(self, locked: bool) -> None:
        self._locked = locked

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
