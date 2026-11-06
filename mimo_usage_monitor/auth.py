import json
import os
import threading
import time
from pathlib import Path

import requests

from . import config
from .api import DETAIL_PATH, AuthExpiredError, CookieAuth, MimoApiClient, TicketAuth
from .browser_cookies import load_chromium_cookie_header
from .storage import CredentialStore

BASE_URL = "https://platform.xiaomimimo.com"
CONSOLE_URL = f"{BASE_URL}/console/usage"
GEN_LOGIN_PATH = "/api/v1/genLoginUrl?currentPath=/console/usage"
WEBVIEW_TIMEOUT_S = 300
SSO_DOMAIN = "account.xiaomi.com"
MIMO_DOMAIN = "xiaomimimo.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0"
)


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


def _login_from_browser(user_data_dir: Path) -> CookieAuth | None:
    header = load_chromium_cookie_header(user_data_dir, "xiaomimimo.com")
    if header and _probe_auth(CookieAuth(header)):
        return CookieAuth(header)
    return None


def login_from_edge(user_data_dir: Path | None = None) -> CookieAuth | None:
    if user_data_dir is None:
        user_data_dir = (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
        )
    return _login_from_browser(user_data_dir)


def login_from_chrome(user_data_dir: Path | None = None) -> CookieAuth | None:
    if user_data_dir is None:
        user_data_dir = (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
        )
    return _login_from_browser(user_data_dir)


def login_from_browsers() -> CookieAuth | None:
    """依次尝试 Edge、Chrome 的已登录会话；都不行返回 None。"""
    for login in (login_from_edge, login_from_chrome):
        try:
            auth = login()
        except Exception:
            auth = None
        if auth is not None:
            return auth
    return None


def webview_user_data_dir() -> Path:
    return config.data_dir() / "webview_profile" / "EBWebView"


def login_from_webview_profile(user_data_dir: Path | None = None) -> CookieAuth | None:
    """读取内置 WebView 登录窗自己落盘的会话 cookie（无需再开登录窗）。

    WebView2 profile 不走 App-Bound Encryption，v10/v11 cookie 可用 DPAPI 解出。
    """
    if user_data_dir is None:
        user_data_dir = webview_user_data_dir()
    return _login_from_browser(user_data_dir)


def login_via_sso(make_session=None) -> CookieAuth | None:
    """用 webview 会话库里的小米 SSO 登录态（passToken）无感换出平台会话。

    原理：未带平台 cookie 调接口会 401 并返回 loginUrl（SSO serviceLogin，
    callback 指向 /sts）；携带 passToken 访问后重定向链自动在
    platform.xiaomimimo.com 域落下会话 cookie。SSO 过期则返回 None。
    """
    sso_header = load_chromium_cookie_header(webview_user_data_dir(), SSO_DOMAIN)
    if not sso_header:
        return None
    session = (make_session or requests.Session)()
    session.headers["User-Agent"] = _UA
    for pair in sso_header.split("; "):
        name, _, value = pair.partition("=")
        if name:
            session.cookies.set(name, value, domain=f".{SSO_DOMAIN}")
    login_url = None
    try:
        resp = session.get(BASE_URL + DETAIL_PATH, timeout=15, allow_redirects=False)
        if resp.status_code == 401:
            login_url = (resp.json() or {}).get("loginUrl")
        elif resp.status_code == 200:  # 已带有效会话（少见）
            login_url = None
        if not login_url:
            r = session.get(BASE_URL + GEN_LOGIN_PATH, timeout=15, allow_redirects=False)
            login_url = r.headers.get("Location")
        if login_url:
            session.get(login_url, timeout=20)  # SSO → /sts → 平台会话 cookie
    except (requests.RequestException, ValueError):
        return None
    pairs = []
    seen = set()
    for c in session.cookies:
        host = (c.domain or "").lstrip(".")
        if host != MIMO_DOMAIN and not host.endswith(f".{MIMO_DOMAIN}"):
            continue
        if c.name in seen:
            continue
        seen.add(c.name)
        pairs.append(f"{c.name}={c.value}")
    if not pairs:
        return None
    auth = CookieAuth("; ".join(pairs))
    return auth if _probe_auth(auth) else None


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

    def try_header(header: str | None) -> None:
        """以探活为准：拿到的凭证能调通接口才算登录成功。"""
        if header and _probe_auth(CookieAuth(header)):
            result["auth"] = CookieAuth(header)

    def capture_from_window() -> None:
        try:
            pairs = _cookie_pairs(window.get_cookies())
        except Exception:
            return
        try_header("; ".join(f"{n}={v}" for n, v in pairs))

    def capture_from_disk() -> None:
        """webview 自己的 cookie 库兜底：运行时 API 拿不到也能读到登录会话。"""
        try:
            header = load_chromium_cookie_header(webview_user_data_dir(), "xiaomimimo.com")
        except Exception:
            header = None
        try_header(header)

    def capture_from_sso() -> None:
        """SSO 已登录但 /sts 回跳中断时，用 passToken 无感补换平台会话。"""
        try:
            auth = login_via_sso()
        except Exception:
            auth = None
        if auth is not None:
            result["auth"] = auth

    def poll():
        deadline = time.time() + timeout_s
        last_capture = 0.0
        while time.time() < deadline and not result.get("auth"):
            time.sleep(0.5)
            if time.time() - last_capture < 1.5:
                continue
            last_capture = time.time()
            capture_from_window()
            if not result.get("auth"):
                capture_from_disk()
            if not result.get("auth"):
                capture_from_sso()
            if result.get("auth"):
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
    if not result.get("auth"):
        capture_from_disk()  # 窗口已关：cookie 已写进 webview 自己的库，再读一次落盘库
    if not result.get("auth"):
        capture_from_sso()
    return result.get("auth")


def login_with_webview(
    launcher=None, profile_login=None, sso_login=None
) -> CookieAuth | TicketAuth | None:
    """WebView 通道：落盘会话 → SSO 无感换会话 → 登录窗。"""
    logins = (
        profile_login if profile_login is not None else login_from_webview_profile,
        sso_login if sso_login is not None else login_via_sso,
    )
    for login in logins:
        try:
            auth = login()
        except Exception:
            auth = None
        if auth is not None:
            return auth
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
    login_chrome=None,
    login_webview=None,
    login_paste=None,
) -> CookieAuth | TicketAuth:
    logins = (
        ("Edge 导入", login_edge if login_edge is not None else login_from_edge),
        ("Chrome 导入", login_chrome if login_chrome is not None else login_from_chrome),
        ("WebView/SSO", login_webview if login_webview is not None else login_with_webview),
        ("粘贴 Cookie", login_paste if login_paste is not None else login_with_paste),
    )
    blob = store.load()
    if blob:
        try:
            auth = auth_from_blob(blob)
        except (ValueError, TypeError, json.JSONDecodeError):
            auth = None
        if auth is not None and _stored_probe(client_factory, auth) != "expired":
            return auth
    for name, login in logins:
        try:
            auth = login()
        except Exception:
            auth = None
        print(f"[登录] {name}: {'成功' if auth is not None else '未取到'}")
        if auth is not None:
            store.save(auth_to_blob(auth))
            return auth
    raise RuntimeError("需要登录")
