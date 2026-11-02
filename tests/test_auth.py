import json

import pytest

from mimo_usage_monitor.api import AuthExpiredError, CookieAuth, TicketAuth
from mimo_usage_monitor.auth import (
    auth_from_blob,
    auth_to_blob,
    ensure_auth,
    login_with_webview,
    parse_cookie_header,
)


class FakeStore:
    def __init__(self, blob=None):
        self.blob = blob
        self.saved = []

    def save(self, blob):
        self.saved.append(blob)
        self.blob = blob

    def load(self):
        return self.blob

    def clear(self):
        self.blob = None


class FakeClient:
    def __init__(self, behavior):
        self._behavior = behavior

    def fetch_snapshot(self):
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return self._behavior


def _factory(behavior):
    return lambda auth: FakeClient(behavior)


def test_auth_blob_roundtrip():
    for auth in (CookieAuth("a=b; c=d"), TicketAuth("tk-1")):
        assert auth_from_blob(auth_to_blob(auth)) == auth


def test_parse_cookie_header():
    assert parse_cookie_header("Cookie: a=b; c=d") == "a=b; c=d"
    assert parse_cookie_header("a=b") == "a=b"
    assert parse_cookie_header("") is None
    assert parse_cookie_header("hello world") is None


def test_ensure_auth_uses_stored_valid():
    store = FakeStore(auth_to_blob(CookieAuth("stale=1")))
    called = []

    def no_login():
        called.append(1)
        return None

    auth = ensure_auth(
        store,
        _factory(object()),
        login_edge=no_login,
        login_webview=no_login,
        login_paste=no_login,
    )
    assert auth == CookieAuth("stale=1")
    assert called == []


def test_ensure_auth_relogins_when_expired():
    store = FakeStore(auth_to_blob(CookieAuth("stale=1")))
    webview_calls = []

    def webview():
        webview_calls.append(1)
        return CookieAuth("fresh=2")

    auth = ensure_auth(
        store,
        _factory(AuthExpiredError("401")),
        login_edge=lambda: None,
        login_webview=webview,
        login_paste=lambda: None,
    )
    assert auth == CookieAuth("fresh=2")
    assert webview_calls == [1]
    assert store.saved == [auth_to_blob(CookieAuth("fresh=2"))]


def test_login_falls_back_to_paste_when_webview_unavailable():
    store = FakeStore()

    def broken_launcher():
        raise RuntimeError("no webview backend")

    def paste():
        return CookieAuth("pasted=3")

    auth = ensure_auth(
        store,
        _factory(object()),
        login_edge=lambda: None,
        login_webview=lambda: login_with_webview(launcher=broken_launcher),
        login_paste=paste,
    )
    assert auth == CookieAuth("pasted=3")


def test_ensure_auth_uses_edge_when_no_stored_auth():
    store = FakeStore()
    called = []

    def edge():
        return CookieAuth("from-edge=4")

    def no_call():
        called.append(1)
        return None

    auth = ensure_auth(
        store,
        _factory(object()),
        login_edge=edge,
        login_webview=no_call,
        login_paste=no_call,
    )
    assert auth == CookieAuth("from-edge=4")
    assert called == []
