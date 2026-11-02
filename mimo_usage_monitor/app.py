import dataclasses
import threading
import time
from datetime import datetime, timezone

from . import config
from .api import CookieAuth, MimoApiClient
from .auth import CONSOLE_URL, ensure_auth
from .models import UsageSnapshot
from .notify import ThresholdNotifier, threshold_message
from .storage import get_default_store

_SINGLETON_MUTEX = None


def acquire_single_instance() -> bool:
    """命名互斥量；False 表示已有实例在运行。"""
    global _SINGLETON_MUTEX
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, True, "Local\\mimo-usage-monitor-singleton")
    if not handle:
        return False
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _SINGLETON_MUTEX = handle  # 保持句柄存活以持有互斥量
    return True


def backoff_wait(interval_s: float, failures: int) -> float:
    """连续失败第 n 次后的等待秒数：interval × 2^(n-1)，封顶 300s，指数封顶防溢出。"""
    exp = min(max(failures - 1, 0), 10)
    return min(float(interval_s) * (2 ** exp), 300.0)


class RefreshLoop:
    """后台刷新线程：失败退避（60→120→240→封顶 300s），保留最后快照并标记陈旧。"""

    def __init__(
        self,
        fetch,
        interval_s: float,
        on_snapshot,
        on_error,
        sleep=None,
    ) -> None:
        self._fetch = fetch
        self._interval = float(interval_s)
        self._on_snapshot = on_snapshot
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._wake = threading.Event()
        self._sleep = sleep or self._interruptible_sleep
        self._thread: threading.Thread | None = None
        self._last_snapshot: UsageSnapshot | None = None
        self._failures = 0

    def _interruptible_sleep(self, seconds: float) -> None:
        self._wake.wait(timeout=seconds)
        self._wake.clear()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def trigger_now(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            if self._stop_event.is_set():
                break
            self._sleep(backoff_wait(self._interval, self._failures))

    def _tick(self) -> None:
        try:
            snap = self._fetch()
        except Exception as exc:
            self._failures += 1
            self._on_error(exc)
            if self._last_snapshot is not None:
                stale = dataclasses.replace(self._last_snapshot, is_stale=True)
                self._last_snapshot = stale
                self._on_snapshot(stale)
            return
        self._failures = 0
        self._last_snapshot = snap
        self._on_snapshot(snap)


def run() -> None:
    import tkinter as tk
    import webbrowser

    from .display.floating_bar import FloatingBar
    from .display.taskbar import DockedFallback, Rect, TaskbarWidget, compute_placement
    from .display.tray import TrayDisplay

    if not acquire_single_instance():
        print("mimo-usage-monitor 已在运行（单实例）")
        return

    data_dir = config.data_dir()
    cfg = config.load_config(data_dir)
    store = get_default_store(data_dir)

    def client_factory(auth):
        return MimoApiClient(auth)

    try:
        auth = ensure_auth(store, client_factory)
    except RuntimeError:
        print("登录未完成，退出")
        return
    client = MimoApiClient(auth)

    root = tk.Tk()
    root.withdraw()

    windows: dict[str, object] = {}
    state = {"first": True, "snapshot": None}

    def make_taskbar():
        widget = TaskbarWidget(master=root)
        if widget.try_embed():
            return widget
        rect = None
        from .display.taskbar import Win32Taskbar

        win32 = Win32Taskbar()
        taskbar_rect, tray_rect = win32.shell_tray_rect(), win32.tray_notify_rect()
        if taskbar_rect and tray_rect:
            rect = compute_placement(taskbar_rect, tray_rect)
        else:
            rect = Rect(1200, 1040, 180, 30)
        return DockedFallback(rect, master=root)

    def set_taskbar_enabled(enabled: bool) -> None:
        cfg.show_taskbar = enabled
        config.save_config(data_dir, cfg)
        if enabled and "taskbar" not in windows:
            windows["taskbar"] = make_taskbar()
        elif not enabled and "taskbar" in windows:
            windows["taskbar"].destroy()
            del windows["taskbar"]
        if state["snapshot"] is not None and "taskbar" in windows:
            windows["taskbar"].update(state["snapshot"])

    def set_floating_enabled(enabled: bool) -> None:
        cfg.show_floating = enabled
        config.save_config(data_dir, cfg)
        if enabled and "floating" not in windows:
            windows["floating"] = FloatingBar(
                callbacks, cfg.floating_rect, cfg.floating_opacity, cfg.floating_locked,
                master=root,
            )
        elif not enabled and "floating" in windows:
            rect = windows["floating"].rect()
            windows["floating"].destroy()
            del windows["floating"]
            cfg.floating_rect = rect
            config.save_config(data_dir, cfg)
        if state["snapshot"] is not None and "floating" in windows:
            windows["floating"].update(state["snapshot"])

    def set_notify_enabled(enabled: bool) -> None:
        cfg.notify_enabled = enabled
        config.save_config(data_dir, cfg)

    def quit_app() -> None:
        loop.stop()
        for w in windows.values():
            w.destroy()
        tray.stop()
        root.after(0, root.quit)

    def open_console() -> None:
        webbrowser.open(CONSOLE_URL)

    callbacks = {
        "on_refresh": lambda: loop.trigger_now(),
        "on_open_console": open_console,
        "on_toggle_taskbar": lambda: set_taskbar_enabled(not cfg.show_taskbar),
        "on_toggle_notify": lambda: set_notify_enabled(not cfg.notify_enabled),
        "on_open_settings": lambda: None,  # Task 13 接线设置对话框
        "on_quit": quit_app,
        "on_toggle_floating": lambda: set_floating_enabled(not cfg.show_floating),
    }

    if cfg.show_floating:
        windows["floating"] = FloatingBar(
            callbacks, cfg.floating_rect, cfg.floating_opacity, cfg.floating_locked,
            master=root,
        )
    if cfg.show_taskbar:
        windows["taskbar"] = make_taskbar()

    menu_items = [
        ("立即刷新", lambda: loop.trigger_now()),
        ("打开控制台", open_console),
        ("悬浮条", lambda: set_floating_enabled(not cfg.show_floating),
         lambda: cfg.show_floating),
        ("任务栏部件", lambda: set_taskbar_enabled(not cfg.show_taskbar),
         lambda: cfg.show_taskbar),
        ("额度提醒", lambda: set_notify_enabled(not cfg.notify_enabled),
         lambda: cfg.notify_enabled),
        ("设置…", callbacks["on_open_settings"], None),
        ("退出", quit_app),
    ]
    tray = TrayDisplay(menu_items)

    notifier = ThresholdNotifier(cfg.threshold_pct)

    def on_snapshot(s: UsageSnapshot) -> None:
        state["snapshot"] = s
        for w in windows.values():
            w.update(s)
        tray.update(s)
        if cfg.notify_enabled and notifier.update(s, at_startup=state["first"]):
            title, body = threshold_message(s)
            tray.notify(title, body)
        state["first"] = False

    def on_error(exc: Exception) -> None:
        pass  # 陈旧标记由 RefreshLoop 负责

    loop = RefreshLoop(
        client.fetch_snapshot, cfg.refresh_interval_s, on_snapshot, on_error
    )
    loop.start()
    tray.run_detached()
    root.mainloop()
