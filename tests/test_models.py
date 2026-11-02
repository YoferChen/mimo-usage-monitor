import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mimo_usage_monitor.models import UsageSnapshot, is_offpeak, parse_snapshot

FIXTURES = Path(__file__).parent / "fixtures"
BJ = timezone(timedelta(hours=8))


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_snapshot_full_fixture():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    snap = parse_snapshot(_load("tokenplan_detail.json"), _load("tokenplan_usage.json"), now)
    assert snap.fetched_at == now
    assert snap.plan_name == "Standard"
    assert snap.total_credits == 11000000000
    assert snap.used_credits == 6018813462
    assert snap.remaining_credits == 11000000000 - 6018813462
    assert snap.remaining_pct == pytest.approx(
        (11000000000 - 6018813462) / 11000000000 * 100, abs=0.1
    )
    assert snap.expire_at == datetime(2026, 11, 13, 23, 59, 59, tzinfo=BJ)
    assert snap.month_used_credits == 6018813462
    assert snap.today_used_credits is None
    assert snap.rate_limit_note is None
    assert snap.is_stale is False


def test_parse_snapshot_empty_dicts_no_raise():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    snap = parse_snapshot({}, {}, now)
    assert snap == UsageSnapshot(fetched_at=now)


def test_parse_snapshot_alternate_field_names():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    detail = {"data": {"planCode": "pro", "clawPeriodEnd": "2026-12-01 00:00:00"}}
    usage = {"data": {"monthUsage": {"used": 5}}}
    snap = parse_snapshot(detail, usage, now)
    assert snap.plan_name == "pro"
    assert snap.expire_at == datetime(2026, 12, 1, 0, 0, 0, tzinfo=BJ)
    assert snap.month_used_credits == 5


def test_remaining_pct_none_when_total_zero():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    usage = {
        "data": {
            "usage": {
                "items": [
                    {"name": "plan_total_token", "used": 0, "limit": 0},
                    {"name": "compensation_total_token", "used": 0, "limit": 0},
                ]
            }
        }
    }
    snap = parse_snapshot({}, usage, now)
    assert snap.total_credits == 0
    assert snap.remaining_credits == 0
    assert snap.remaining_pct is None


def test_is_offpeak_beijing():
    assert is_offpeak(datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc)) is True   # 北京 07:00
    assert is_offpeak(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)) is False  # 北京 20:00
    assert is_offpeak(datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)) is True   # 北京 00:00
