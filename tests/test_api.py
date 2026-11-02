import json
from pathlib import Path

import pytest

from mimo_usage_monitor.api import (
    ApiError,
    AuthExpiredError,
    CookieAuth,
    MimoApiClient,
    TicketAuth,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


def _fixtures():
    detail = json.loads((FIXTURES / "tokenplan_detail.json").read_text(encoding="utf-8"))
    usage = json.loads((FIXTURES / "tokenplan_usage.json").read_text(encoding="utf-8"))
    return detail, usage


def _client(session):
    return MimoApiClient(CookieAuth("a=b; c=d"), session=session, sleep=lambda s: None)


def test_fetch_snapshot_happy_path():
    detail, usage = _fixtures()
    session = FakeSession([FakeResponse(200, detail), FakeResponse(200, usage)])
    snap = _client(session).fetch_snapshot()
    assert snap.plan_name == "Standard"
    assert snap.total_credits == 11000000000
    assert snap.used_credits == 6018813462
    assert snap.remaining_credits == 11000000000 - 6018813462
    assert snap.remaining_pct == pytest.approx(45.3, abs=0.1)


def test_fetch_snapshot_401_raises_auth_expired():
    session = FakeSession([FakeResponse(401)])
    with pytest.raises(AuthExpiredError):
        _client(session).fetch_snapshot()
    assert len(session.calls) == 1


def test_fetch_snapshot_302_raises_auth_expired():
    session = FakeSession([FakeResponse(302)])
    with pytest.raises(AuthExpiredError):
        _client(session).fetch_snapshot()
    assert len(session.calls) == 1


def test_fetch_retries_then_raises_api_error():
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])
    with pytest.raises(ApiError) as exc:
        _client(session).fetch_snapshot()
    assert len(session.calls) == 3
    assert exc.value.status_code == 500


def test_cookie_auth_sets_header():
    detail, usage = _fixtures()
    session = FakeSession([FakeResponse(200, detail), FakeResponse(200, usage)])
    _client(session).fetch_snapshot()
    for _url, kwargs in session.calls:
        assert kwargs["headers"]["Cookie"] == "a=b; c=d"


def test_business_error_raises_instead_of_blank_snapshot():
    bad = {"code": 40301, "message": "quota locked", "data": None}
    session = FakeSession([FakeResponse(200, bad), FakeResponse(200, bad)])
    with pytest.raises(ApiError):
        _client(session).fetch_snapshot()


def test_ticket_auth_appends_query_param():
    detail, usage = _fixtures()
    session = FakeSession([FakeResponse(200, detail), FakeResponse(200, usage)])
    MimoApiClient(
        TicketAuth("abc123"), session=session, sleep=lambda s: None
    ).fetch_snapshot()
    for url, _kwargs in session.calls:
        assert "mm_ticket=abc123" in url
