from typing import Protocol

from .models import UsageSnapshot


class NotifierSink(Protocol):
    def notify(self, title: str, body: str) -> None: ...


class ThresholdNotifier:
    """跌破阈值触发一次；回升到「阈值 + rearm_delta_pp」后重新武装。"""

    def __init__(self, threshold_pct: float, rearm_delta_pp: float = 2.0) -> None:
        self._threshold = float(threshold_pct)
        self._rearm_delta = float(rearm_delta_pp)
        self._armed = True

    def update(self, snapshot: UsageSnapshot, at_startup: bool = False) -> bool:
        pct = snapshot.remaining_pct
        if pct is None:
            return False
        if pct >= self._threshold + self._rearm_delta:
            self._armed = True
            return False
        if pct < self._threshold and (self._armed or at_startup):
            self._armed = False
            return True
        return False


def threshold_message(snapshot: UsageSnapshot) -> tuple[str, str]:
    title = "MiMo Token Plan 额度不足"
    pct = snapshot.remaining_pct
    if pct is None:
        return title, "套餐额度信息不可用，请打开控制台查看"
    body = f"剩余 {pct:.1f}%"
    if snapshot.remaining_credits is not None and snapshot.total_credits is not None:
        body += (
            f"（{snapshot.remaining_credits:g} / {snapshot.total_credits:g} Credits）"
        )
    return title, body
