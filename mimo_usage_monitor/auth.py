import json
import os
import threading
import time
from pathlib import Path

import requests

from . import config
from .api import DETAIL_PATH, AuthExpiredError, CookieAuth, MimoApiClient, TicketAuth
from .browser_cookies import load_edge_cookie_header
from .storage import CredentialStore

BASE_URL = "https://platform.xiaomimimo.com"
CONSOLE_URL = f"{BASE_URL}/console/usage"
GEN_LOGIN_PATH = "/api/v1/genLoginUrl?currentPath=/console/usage"
WEBVIEW_TIMEOUT_S = 300


def auth_to_blob(auth: CookieAuth | TicketAuth) -> str:
    if isinstance(auth, CookieAuth):
        return json.dumps({"type": "cookie", "value": auth.cookie_header}, ensure_ascii=False)
    return json.dumps({"type": "ticket", "value": auth.ticket}, ensure_ascii=False)


def auth_from_blob(blob: str) -> CookieAuth | TicketAuth:
    data = json.loads(blob)
    kind, value = data.get("type"), data.get("value")
    if kind == "cookie" and isinstance(value, str):
        return CookieAuth(value)
    if kind == "ticket" and isinstance(value, str):
        return TicketAuth(value)
    raise ValueError("未知凭证格式")


def parse_cookie_header(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[7:].strip()
    if not raw or "=" not in raw:
        return None
    pairs = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            return None
        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            return None
        pairs.append(f"{name}={value}")
    return "; ".join(pairs) if pairs else None


def _probe_auth(auth: CookieAuth | TicketAuth) -> bool:
    try:
        resp = MimoApiClient(auth, BASE_URL, sleep=lambda s: None)._get(DETAIL_PATH)
    except requests.RequestException:
        return False
    return resp.status_code == 200


def login_from_edge(user_data_dir: Path | None = None) -> CookieAuth | None:
    if user_data_dir is None:
        user_data_dir = (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
        )
    header = load_edge_cookie_header(user_data_dir, "xiaomimimo.com")
    if header and _probe_auth(CookieAuth(header)):
        return CookieAuth(header)
    return None


def _cookie_pairs(cookies) -> list[tuple[str, str]]:
    pairs = []
    items = cookies.items() if hasattr(cookies, "items") else [(None, c) for c in cookies or []]
    for key, value in items:
        name = key if key is not None else getattr(value, "name", None)
        val = getattr(value, "value", value)
        if isinstance(val, dict):
            name = name or val.get("name")
            val = val.get("value")
        if name and val is not None:
            pairs.append((str(name), str(val)))
    return pairs


def _webview_login_gui(timeout_s: int = WEBVIEW_TIMEOUT_S) -> CookieAuth | None:
    import webview

    window = webview.create_window(
        "MiMo 登录", BASE_URL + GEN_LOGIN_PATH, width=520, height=760
    )
    result: dict = {}

    def poll():
        deadline = time.time() + timeout_s
        while time.time() < deadline and not result.get("auth"):
            time.sleep(0.5)
            try:
                url = window.get_current_url() or ""
            except Exception:
                continue
            if "platform.xiaomimimo.com/console" not in url:
                continue
            try:
                pairs = _cookie_pairs(window.get_cookies())
            except Exception:
                continue
            if pairs:
                auth = CookieAuth("; ".join(f"{n}={v}" for n, v in pairs))
                if _probe_auth(auth):
                    result["auth"] = auth
                    try:
                        window.destroy()
                    except Exception:
                        pass
                    return
        try:
            window.destroy()
        except Exception:
            pass

    threading.Thread(target=poll, daemon=True).start()
    try:
        webview.start(
            private_mode=False,
            storage_path=str(config.data_dir() / "webview_profile"),
        )
    except TypeError:
        webview.start()
    return result.get("auth")


def login_with_webview(launcher=None) -> CookieAuth | TicketAuth | None:
    try:
        return (launcher or _webview_login_gui)()
    except Exception:
        return None


def login_with_paste() -> CookieAuth | None:
    import tkinter as tk
    import webbrowser

    webbrowser.open(CONSOLE_URL)
    result: dict = {}
    root = tk.Tk()
    root.title("粘贴 Cookie 登录")
    root.attributes("-topmost", True)
    tk.Label(
        root,
        text=(
            "浏览器已打开控制台页面。\n"
            "F12 → 网络 → 任意请求 → 请求标头 → 复制 cookie 值，粘贴到下方："
        ),
        justify="left",
    ).pack(padx=12, pady=(12, 4))
    text = tk.Text(root, width=56, height=5)
    text.pack(padx=12, pady=4)

    def on_ok():
        result["header"] = parse_cookie_header(text.get("1.0", "end"))
        root.destroy()

    tk.Button(root, text="登录", command=on_ok).pack(pady=(4, 12))
    root.mainloop()
    header = result.get("header")
    if header and _probe_auth(CookieAuth(header)):
        return CookieAuth(header)
    return None


def _stored_probe(client_factory, auth) -> str:
    try:
        client_factory(auth).fetch_snapshot()
        return "ok"
    except AuthExpiredError:
        return "expired"
    except Exception:
        return "error"


def ensure_auth(
    store: CredentialStore,
    client_factory,
    login_edge=None,
    login_webview=None,
    login_paste=None,
) -> CookieAuth | TicketAuth:
    logins = (
        login_edge if login_edge is not None else login_from_edge,
        login_webview if login_webview is not None else login_with_webview,
        login_paste if login_paste is not None else login_with_paste,
    )
    blob = store.load()
    if blob:
        try:
            auth = auth_from_blob(blob)
        except (ValueError, TypeError, json.JSONDecodeError):
            auth = None
        if auth is not None and _stored_probe(client_factory, auth) != "expired":
            return auth
    for login in logins:
        try:
            auth = login()
        except Exception:
            auth = None
        if auth is not None:
            store.save(auth_to_blob(auth))
            return auth
    raise RuntimeError("需要登录")
