import os
from dataclasses import dataclass

from ..models import UsageSnapshot

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
GWL_HWNDPARENT = -8
HWND_TOPMOST = -1


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


def compute_placement(
    taskbar_rect: Rect,
    tray_rect: Rect,
    widget_w: int = 180,
    widget_h: int = 30,
    align: str = "right",
    left_x: int | None = None,
) -> Rect:
    if align == "left":
        x = (left_x + 8) if left_x is not None else (taskbar_rect.x + 8)
    else:
        x = tray_rect.x - widget_w - 4
    return Rect(
        x,
        taskbar_rect.y + (taskbar_rect.h - widget_h) // 2,
        widget_w,
        widget_h,
    )


def format_taskbar_text(s: UsageSnapshot) -> str:
    from ..models import BJ

    if s.remaining_pct is None:
        return "余—" + (" ⚠" if s.is_stale else "")
    text = f"余{s.remaining_pct:.0f}%"
    if s.expire_at is not None:
        days = (
            s.expire_at.astimezone(BJ).date() - s.fetched_at.astimezone(BJ).date()
        ).days
        text += f" · {days}d"
    if s.is_stale:
        text += " ⚠"
    return text


class Win32Taskbar:
    """ctypes 门面：测量任务栏/托盘区、收缩任务列表、把窗口挂到任务栏。"""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._saved_task_list_rect: Rect | None = None

    def _rect_of(self, hwnd) -> Rect | None:
        if not hwnd:
            return None
        r = self._wintypes.RECT()
        if not self._user32.GetWindowRect(hwnd, self._ctypes.byref(r)):
            return None
        return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)

    def shell_tray_rect(self) -> Rect | None:
        return self._rect_of(self._user32.FindWindowW("Shell_TrayWnd", None))

    def tray_notify_rect(self) -> Rect | None:
        shell = self._user32.FindWindowW("Shell_TrayWnd", None)
        tray = self._user32.FindWindowExW(shell, None, "TrayNotifyWnd", None)
        return self._rect_of(tray)

    def left_cluster_right_edge(self) -> int | None:
        """任务栏左侧已有内容（Start/搜索）的右缘，用于左侧放置时避让。"""
        shell = self._user32.FindWindowW("Shell_TrayWnd", None)
        best = None
        for cls in ("Start", "TrayDummySearchControl", "ReBarWindow32"):
            hwnd = self._user32.FindWindowExW(shell, None, cls, None)
            rect = self._rect_of(hwnd)
            if rect is not None:
                best = max(best or 0, rect.x + rect.w)
        return best

    def _find_task_list(self):
        shell = self._user32.FindWindowW("Shell_TrayWnd", None)
        rebar = self._user32.FindWindowExW(shell, None, "ReBarWindow32", None)
        task_list = self._user32.FindWindowExW(rebar, None, "MSTaskListWClass", None)
        if not task_list:
            task_list = self._user32.FindWindowExW(shell, None, "MSTaskListWClass", None)
        return task_list

    def shrink_task_list(self, delta_w: int) -> bool:
        task_list = self._find_task_list()
        if not task_list:
            return False
        rect = self._rect_of(task_list)
        if rect is None:
            return False
        ok = self._user32.SetWindowPos(
            task_list, 0, rect.x, rect.y, max(50, rect.w - delta_w), rect.h,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        new_rect = self._rect_of(task_list) if ok else None
        if not ok or new_rect is None or new_rect.w >= rect.w:
            return False
        self._saved_task_list_rect = rect
        return True

    def restore_task_list(self) -> None:
        rect = self._saved_task_list_rect
        if rect is None:
            return
        task_list = self._find_task_list()
        if task_list:
            self._user32.SetWindowPos(
                task_list, 0, rect.x, rect.y, rect.w, rect.h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
        self._saved_task_list_rect = None

    def attach_to_taskbar(self, hwnd) -> bool:
        shell = self._user32.FindWindowW("Shell_TrayWnd", None)
        if not shell or not hwnd:
            return False
        set_long = getattr(self._user32, "SetWindowLongPtrW", None) or self._user32.SetWindowLongW
        set_long(hwnd, GWL_HWNDPARENT, shell)
        self._user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        return self._user32.GetParent(hwnd) == shell


class _TkToolWindow:
    _KEY_COLOR = "#00ff01"  # 透明色键（transparentcolor）

    def __init__(
        self,
        rect: Rect,
        master=None,
        bg: str = "#1e1e2e",
        fg: str = "#e0e0e0",
        transparent: bool = False,
    ) -> None:
        import tkinter as tk

        if transparent:
            bg = self._KEY_COLOR
        self._root = tk.Toplevel(master) if master is not None else tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.geometry(f"{rect.w}x{rect.h}+{rect.x}+{rect.y}")
        self._label = tk.Label(
            self._root, text="—", anchor="w",
            font=("Microsoft YaHei UI", 9), bg=bg, fg=fg, padx=6,
        )
        self._label.pack(fill="both", expand=True)
        if transparent:
            try:
                self._root.wm_attributes("-transparentcolor", self._KEY_COLOR)
            except Exception:
                self._label.configure(bg="#2b2b2b")
        self._root.update_idletasks()
        self.hwnd = self._resolve_hwnd()

    def _resolve_hwnd(self) -> int:
        if os.name != "nt":
            return 0
        import ctypes

        wid = self._root.winfo_id()
        parent = ctypes.windll.user32.GetParent(wid)
        return parent if parent else wid

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def destroy(self) -> None:
        self._root.destroy()


class TaskbarWidget:
    """任务栏部件；内嵌失败自动放弃，由调用方切 DockedFallback。"""

    def __init__(self, win32=None, window_factory=None, master=None, align="right") -> None:
        self._win32 = win32 if win32 is not None else Win32Taskbar()
        self._master = master
        self._align = align
        self._window_factory = window_factory
        self._window = None

    def try_embed(self) -> bool:
        taskbar_rect = self._win32.shell_tray_rect()
        tray_rect = self._win32.tray_notify_rect()
        if taskbar_rect is None or tray_rect is None:
            return False
        placement = compute_placement(
            taskbar_rect,
            tray_rect,
            align=self._align,
            left_x=(
                self._win32.left_cluster_right_edge()
                if self._align == "left"
                else None
            ),
        )
        if not self._win32.shrink_task_list(placement.w + 8):
            return False
        factory = self._window_factory or (
            lambda rect: _TkToolWindow(rect, master=self._master, transparent=True)
        )
        self._window = factory(placement)
        if self._window is None or not self._win32.attach_to_taskbar(self._window.hwnd):
            if self._window is not None:
                self._window.destroy()
                self._window = None
            self._win32.restore_task_list()
            return False
        return True

    def update(self, s: UsageSnapshot) -> None:
        if self._window is not None:
            self._window.set_text(format_taskbar_text(s))

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self._win32.restore_task_list()


class DockedFallback:
    """内嵌失败时的降级：吸附任务栏边缘的置顶部件窗。"""

    def __init__(self, rect: Rect, master=None) -> None:
        self._window = _TkToolWindow(rect, master=master, transparent=True)

    def update(self, s: UsageSnapshot) -> None:
        self._window.set_text(format_taskbar_text(s))

    def destroy(self) -> None:
        self._window.destroy()
