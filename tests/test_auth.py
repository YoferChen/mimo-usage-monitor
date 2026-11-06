import json
import threading

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
        login_chrome=no_login,
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
        login_chrome=lambda: None,
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
        login_chrome=lambda: None,
        login_webview=lambda: login_with_webview(
            launcher=broken_launcher, profile_login=lambda: None, sso_login=lambda: None
        ),
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
        login_chrome=no_call,
        login_webview=no_call,
        login_paste=no_call,
    )
    assert auth == CookieAuth("from-edge=4")
    assert called == []


def test_ensure_auth_falls_back_to_chrome_when_edge_fails():
    store = FakeStore()
    called = []

    def chrome():
        return CookieAuth("from-chrome=5")

    def no_call():
        called.append(1)
        return None

    auth = ensure_auth(
        store,
        _factory(object()),
        login_edge=lambda: None,
        login_chrome=chrome,
        login_webview=no_call,
        login_paste=no_call,
    )
    assert auth == CookieAuth("from-chrome=5")
    assert called == []
    assert store.saved == [auth_to_blob(CookieAuth("from-chrome=5"))]


def test_login_from_chrome_reads_chrome_user_data(monkeypatch, tmp_path):
    from mimo_usage_monitor import auth as auth_mod

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    seen = {}

    def fake_load(user_data_dir, domain):
        seen["user_data_dir"] = user_data_dir
        seen["domain"] = domain
        return "a=b"

    monkeypatch.setattr(auth_mod, "load_chromium_cookie_header", fake_load)
    monkeypatch.setattr(auth_mod, "_probe_auth", lambda a: True)
    assert auth_mod.login_from_chrome() == CookieAuth("a=b")
    assert seen["user_data_dir"] == tmp_path / "Google" / "Chrome" / "User Data"
    assert seen["domain"] == "xiaomimimo.com"


def test_login_from_browsers_tries_edge_then_chrome(monkeypatch):
    from mimo_usage_monitor import auth as auth_mod

    order = []
    monkeypatch.setattr(
        auth_mod, "login_from_edge", lambda: (order.append("edge"), None)[1]
    )
    monkeypatch.setattr(
        auth_mod,
        "login_from_chrome",
        lambda: (order.append("chrome"), CookieAuth("c=1"))[1],
    )
    assert auth_mod.login_from_browsers() == CookieAuth("c=1")
    assert order == ["edge", "chrome"]


def test_login_from_webview_profile_reads_store(monkeypatch, tmp_path):
    from mimo_usage_monitor import auth as auth_mod

    monkeypatch.setattr(auth_mod.config, "data_dir", lambda: tmp_path)
    seen = {}

    def fake_load(user_data_dir, domain):
        seen["user_data_dir"] = user_data_dir
        return "w=1"

    monkeypatch.setattr(auth_mod, "load_chromium_cookie_header", fake_load)
    monkeypatch.setattr(auth_mod, "_probe_auth", lambda a: True)
    assert auth_mod.login_from_webview_profile() == CookieAuth("w=1")
    assert seen["user_data_dir"] == tmp_path / "webview_profile" / "EBWebView"


def test_login_with_webview_prefers_profile_cookies():
    def boom():
        raise AssertionError("不应打开登录窗")

    auth = login_with_webview(boom, profile_login=lambda: CookieAuth("p=1"))
    assert auth == CookieAuth("p=1")


class FakeWebviewWindow:
    """模拟 pywebview 窗口；get_cookies 抛错时验证磁盘兜底路径。"""

    def __init__(self, cookies=None):
        self._cookies = cookies
        self.destroyed = threading.Event()

    def get_current_url(self):
        return "https://platform.xiaomimimo.com/console/usage"

    def get_cookies(self):
        if isinstance(self._cookies, Exception):
            raise self._cookies
        return self._cookies or {}

    def destroy(self):
        self.destroyed.set()


def _fake_webview_module(window):
    import types

    return types.SimpleNamespace(
        create_window=lambda *a, **k: window,
        start=lambda **k: window.destroyed.wait(timeout=10),
    )


def test_webview_gui_captures_runtime_cookies(monkeypatch):
    import sys

    from mimo_usage_monitor import auth as auth_mod

    window = FakeWebviewWindow(cookies={"serviceToken": "t=1"})
    monkeypatch.setitem(sys.modules, "webview", _fake_webview_module(window))
    monkeypatch.setattr(auth_mod, "_probe_auth", lambda a: True)
    assert auth_mod._webview_login_gui(timeout_s=10) == CookieAuth("serviceToken=t=1")
    assert window.destroyed.is_set()


def test_webview_gui_falls_back_to_disk_cookies(monkeypatch):
    import sys

    from mimo_usage_monitor import auth as auth_mod

    window = FakeWebviewWindow(cookies=RuntimeError("get_cookies unsupported"))
    monkeypatch.setitem(sys.modules, "webview", _fake_webview_module(window))
    monkeypatch.setattr(auth_mod, "load_chromium_cookie_header", lambda udd, d: "disk=1")
    monkeypatch.setattr(auth_mod, "_probe_auth", lambda a: True)
    assert auth_mod._webview_login_gui(timeout_s=10) == CookieAuth("disk=1")
    assert window.destroyed.is_set()


class FakeCookieJar:
    def __init__(self):
        self._items = []

    def set(self, name, value, domain=None):
        import types

        self._items.append(types.SimpleNamespace(name=name, value=value, domain=domain))

    def __iter__(self):
        return iter(self._items)


class FakeSession:
    """模拟 requests.Session：401 取 loginUrl → 访问后 jar 落平台会话 cookie。"""

    def __init__(self):
        self.cookies = FakeCookieJar()
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        import types

        self.calls.append(url.split("?")[0])
        if url.endswith("tokenPlan/detail"):
            return types.SimpleNamespace(
                status_code=401,
                json=lambda: {"code": 401, "loginUrl": "https://account.xiaomi.com/pass/serviceLogin?x"},
                headers={},
            )
        if "serviceLogin" in url:  # SSO 回跳后平台会话落入 jar
            self.cookies.set("api-platform_serviceToken", "st-9", domain=".platform.xiaomimimo.com")
            self.cookies.set("api-platform_slh", "sl-9", domain=".platform.xiaomimimo.com")
            self.cookies.set("userId", "u-9", domain=".xiaomimimo.com")
            self.cookies.set("passToken", "pt-9", domain=".account.xiaomi.com")
            return types.SimpleNamespace(status_code=200, json=lambda: {}, headers={})
        return types.SimpleNamespace(status_code=200, json=lambda: {}, headers={})


def test_login_via_sso_exchanges_pass_token(monkeypatch):
    from mimo_usage_monitor import auth as auth_mod

    monkeypatch.setattr(
        auth_mod, "load_chromium_cookie_header", lambda udd, d: "passToken=pt-9; userId=u-1"
    )
    monkeypatch.setattr(auth_mod, "_probe_auth", lambda a: True)
    auth = auth_mod.login_via_sso(make_session=FakeSession)
    assert auth == CookieAuth(
        "api-platform_serviceToken=st-9; api-platform_slh=sl-9; userId=u-9"
    )


def test_login_via_sso_returns_none_without_sso(monkeypatch):
    from mimo_usage_monitor import auth as auth_mod

    monkeypatch.setattr(auth_mod, "load_chromium_cookie_header", lambda udd, d: None)
    assert auth_mod.login_via_sso(make_session=FakeSession) is None


def test_webview_gui_falls_back_to_sso(monkeypatch):
    import sys

    from mimo_usage_monitor import auth as auth_mod

    window = FakeWebviewWindow(cookies=RuntimeError("get_cookies unsupported"))
    monkeypatch.setitem(sys.modules, "webview", _fake_webview_module(window))
    monkeypatch.setattr(auth_mod, "load_chromium_cookie_header", lambda udd, d: None)
    monkeypatch.setattr(auth_mod, "login_via_sso", lambda: CookieAuth("sso=2"))
    assert auth_mod._webview_login_gui(timeout_s=10) == CookieAuth("sso=2")


def test_login_with_webview_tries_sso_before_window(monkeypatch):
    def boom():
        raise AssertionError("不应打开登录窗")

    auth = login_with_webview(
        boom, profile_login=lambda: None, sso_login=lambda: CookieAuth("sso=3")
    )
    assert auth == CookieAuth("sso=3")
