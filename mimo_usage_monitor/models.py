import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BJ = timezone(timedelta(hours=8))

# Snapshot 字段 → 候选 key 路径（按序取第一个命中）。
# 路径语法：点号分段；`items[name==X]` 按 name 过滤列表；列表值自动逐元素下探；
# `sum:` 前缀对命中的多个数值求和。字段名依据 docs/api-shape.md。
FIELD_MAP: dict[str, tuple[str, ...]] = {
    "plan_name": ("data.planName", "data.planCode"),
    "expire_at": ("data.currentPeriodEnd", "data.clawPeriodEnd"),
    "used_credits": ("sum:data.usage.items.used", "data.usage.used"),
    "total_credits": ("sum:data.usage.items.limit", "data.usage.limit"),
    "month_used_credits": (
        "data.monthUsage.items[name==month_total_token].used",
        "data.monthUsage.used",
    ),
    "rate_limit_note": ("data.rateLimitNote", "data.rateLimit"),
}

_TOKEN_RE = re.compile(r"^([^[\]]+)(?:\[name==([^\]]+)\])?$")


@dataclass(frozen=True)
class UsageSnapshot:
    fetched_at: datetime
    plan_name: str | None = None
    total_credits: float | None = None
    used_credits: float | None = None
    remaining_credits: float | None = None
    remaining_pct: float | None = None
    expire_at: datetime | None = None
    today_used_credits: float | None = None
    month_used_credits: float | None = None
    rate_limit_note: str | None = None
    is_stale: bool = False


def _walk(obj, tokens: list[str]) -> list:
    if not tokens:
        return [obj]
    m = _TOKEN_RE.match(tokens[0])
    if m is None or not isinstance(obj, dict):
        return []
    key, name_sel = m.group(1), m.group(2)
    if key not in obj:
        return []
    val = obj[key]
    if name_sel is not None:
        if not isinstance(val, list):
            return []
        val = [it for it in val if isinstance(it, dict) and it.get("name") == name_sel]
    values = val if isinstance(val, list) else [val]
    out: list = []
    for v in values:
        out.extend(_walk(v, tokens[1:]))
    return out


def _dig_one(source: dict, path: str):
    want_sum = path.startswith("sum:")
    tokens = path[4:].split(".") if want_sum else path.split(".")
    hits = [h for h in _walk(source, tokens) if h is not None]
    if not hits:
        return None
    if want_sum:
        total = 0.0
        for h in hits:
            num = _to_float(h)
            if num is None:
                return None
            total += num
        return total
    return hits[0]


def _dig(sources: tuple[dict, ...], *candidates: str):
    for cand in candidates:
        for src in sources:
            try:
                hit = _dig_one(src, cand)
            except Exception:
                hit = None
            if hit is not None:
                return hit
    return None


def _to_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_str(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=BJ)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # 中国集群接口输出无时区时间戳，按北京时间解释
    return dt.replace(tzinfo=BJ) if dt.tzinfo is None else dt


def is_offpeak(now: datetime) -> bool:
    return now.astimezone(BJ).hour < 8


def parse_snapshot(detail: dict, usage: dict, now: datetime) -> UsageSnapshot:
    try:
        sources = (detail if isinstance(detail, dict) else {},
                   usage if isinstance(usage, dict) else {})
        plan_name = _to_str(_dig(sources, *FIELD_MAP["plan_name"]))
        total = _to_float(_dig(sources, *FIELD_MAP["total_credits"]))
        used = _to_float(_dig(sources, *FIELD_MAP["used_credits"]))
        month_used = _to_float(_dig(sources, *FIELD_MAP["month_used_credits"]))
        rate_note = _to_str(_dig(sources, *FIELD_MAP["rate_limit_note"]))
        expire_at = _parse_time(_dig(sources, *FIELD_MAP["expire_at"]))
        remaining = None if total is None or used is None else total - used
        pct = None
        if remaining is not None and total:
            pct = round(remaining / total * 100, 1)
        return UsageSnapshot(
            fetched_at=now,
            plan_name=plan_name,
            total_credits=total,
            used_credits=used,
            remaining_credits=remaining,
            remaining_pct=pct,
            expire_at=expire_at,
            today_used_credits=None,
            month_used_credits=month_used,
            rate_limit_note=rate_note,
        )
    except Exception:
        return UsageSnapshot(fetched_at=now)
