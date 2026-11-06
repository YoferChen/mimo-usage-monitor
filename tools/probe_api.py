"""探查 platform.xiaomimimo.com 的 tokenPlan 接口并采集响应结构。

凭证来源优先级：Edge/Chrome 已登录 cookie → WebView 登录窗。
原始响应写入 tools/probe_output/（gitignore），stdout 打印 key 路径树。
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from mimo_usage_monitor.browser_cookies import load_chromium_cookie_header

BASE = "https://platform.xiaomimimo.com"
ENDPOINTS = {
    "tokenplan_detail": "/api/v1/tokenPlan/detail",
    "tokenplan_usage": "/api/v1/tokenPlan/usage",
}


def key_tree(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_tree(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list) and obj:
        print(f"{prefix}[] -> list[{len(obj)}]")
        key_tree(obj[0], f"{prefix}[0]")
    else:
        print(f"{prefix} -> {type(obj).__name__} = {obj!r}"[:160])


def via_browser() -> str | None:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for label, user_data in (
        ("edge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
    ):
        header = load_chromium_cookie_header(user_data, "xiaomimimo.com")
        if header:
            names = [p.split("=", 1)[0] for p in header.split("; ")]
            print(f"[{label}] 取到 cookie: {names}")
            return header
        print(f"[{label}] 未取到（未登录 / 被锁 / v20 加密）")
    return None


def _cookie_pairs(cookies) -> list[tuple[str, str]]:
    """get_cookies() 可能返回 SimpleCookie、dict 或对象列表，统一成 (name, value)。"""
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


def via_webview() -> str | None:
    import webview

    login_url = f"{BASE}/api/v1/genLoginUrl?currentPath=/console/usage"
    window = webview.create_window("MiMo 登录", login_url, width=520, height=760)
    result = {}

    def poll():
        while not result.get("header"):
            time.sleep(0.5)
            try:
                url = window.get_current_url() or ""
            except Exception:
                continue
            reached_console = "platform.xiaomimimo.com/console" in url
            if not reached_console:
                continue
            try:
                pairs = _cookie_pairs(window.get_cookies())
            except Exception:
                continue
            if pairs:
                result["header"] = "; ".join(f"{n}={v}" for n, v in pairs)
                try:
                    window.destroy()
                except Exception:
                    pass
                return

    threading.Thread(target=poll, daemon=True).start()
    try:
        webview.start(
            private_mode=False,
            storage_path=str(Path(__file__).parent / "probe_output" / "webview_profile"),
        )
    except TypeError:
        webview.start()
    if result.get("header"):
        names = [p.split("=", 1)[0] for p in result["header"].split("; ")]
        print(f"[webview] 取到 cookie: {names}")
    return result.get("header")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--user-data-dir":
        header = load_chromium_cookie_header(Path(sys.argv[2]), "xiaomimimo.com")
        print(f"[user-data-dir] {'取到' if header else '未取到'} cookie")
    else:
        header = via_browser() or via_webview()
    if not header:
        print("未能取得凭证，退出。")
        sys.exit(1)

    out = Path(__file__).parent / "probe_output"
    out.mkdir(exist_ok=True)
    for name, path in ENDPOINTS.items():
        r = requests.get(BASE + path, headers={"Cookie": header}, timeout=15)
        print(f"\n=== GET {path} -> {r.status_code}")
        if r.ok:
            data = r.json()
            (out / f"{name}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            key_tree(data)
            print(f"[saved] tools/probe_output/{name}.json")
        else:
            print(r.text[:300])


if __name__ == "__main__":
    main()
