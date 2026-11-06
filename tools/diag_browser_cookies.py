"""诊断浏览器 cookie 导入：报告各浏览器/配置文件里 xiaomimimo.com 会话 cookie 的可解密性。

只打印 cookie 名与加密前缀（v10/v11/v20），不打印任何值。

用法：
  python tools/diag_browser_cookies.py            # 扫描 Edge + Chrome
  python tools/diag_browser_cookies.py <user-data-dir>  # 扫描指定目录
"""

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mimo_usage_monitor.browser_cookies import (  # noqa: E402
    DEFAULT_PROFILES,
    _decrypt,
    _load_key,
)

DOMAIN = "xiaomimimo.com"


def _prefix(blob: bytes) -> str:
    for p in (b"v10", b"v11", b"v20"):
        if blob.startswith(p):
            return p.decode()
    return f"unknown({blob[:4]!r})"


def diag_profile(user_data_dir: Path, profile: str) -> None:
    db_path = user_data_dir / profile / "Network" / "Cookies"
    if not db_path.exists():
        print(f"  [{profile}] 无 Cookies 库")
        return
    tmp = Path(tempfile.mkdtemp()) / "cookies.db"
    try:
        try:
            shutil.copy2(db_path, tmp)
            con = sqlite3.connect(tmp)
        except (OSError, sqlite3.Error):
            try:
                con = sqlite3.connect(
                    f"file:{db_path}?mode=ro".replace("\\", "/"), uri=True, timeout=3
                )
            except sqlite3.Error as exc:
                print(f"  [{profile}] 读库失败（浏览器运行中锁库？）: {exc}")
                return
        try:
            rows = con.execute(
                "SELECT host_key, name, length(encrypted_value), encrypted_value "
                "FROM cookies WHERE host_key = ? OR host_key LIKE ? ORDER BY rowid",
                (DOMAIN, f"%.{DOMAIN}"),
            ).fetchall()
        except sqlite3.Error as exc:
            print(f"  [{profile}] 查询失败: {exc}")
            return
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)

    if not rows:
        print(f"  [{profile}] 无 {DOMAIN} cookie（未在此配置文件登录过？）")
        return
    print(f"  [{profile}] 共 {len(rows)} 个 {DOMAIN} cookie：")
    key = _load_key(user_data_dir)
    for host, name, _len, blob in rows:
        pref = _prefix(blob)
        status = "不可解（v20 App-Bound）" if pref == "v20" else (
            "未解出" if key is None or _decrypt(key, blob, host) is None else "可解"
        )
        print(f"    {name:<24} host={host:<28} 加密={pref:<4} {status}")


def diag_browser(label: str, user_data_dir: Path) -> None:
    print(f"\n== {label}: {user_data_dir}")
    if not user_data_dir.exists():
        print("  目录不存在（未安装此浏览器？）")
        return
    state_path = user_data_dir / "Local State"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            osc = state.get("os_crypt", {})
            has_key = "encrypted_key" in osc
            abe = osc.get("app_bound_encrypted_key")
            print(f"  Local State: encrypted_key={'有' if has_key else '无'}"
                  f", app_bound_encrypted_key={'有（v20）' if abe else '无'}")
            if abe:
                try:
                    raw = base64.b64decode(abe)
                    print(f"    app_bound_encrypted_key 前缀: {raw[:4]!r}, 长度 {len(raw)}")
                except Exception:
                    pass
        except (OSError, ValueError) as exc:
            print(f"  Local State 解析失败: {exc}")
    key = _load_key(user_data_dir)
    print(f"  DPAPI 主密钥: {'解出' if key is not None else '解不出'}")
    profiles = DEFAULT_PROFILES
    extra = sorted(
        p.name for p in user_data_dir.glob("Profile *") if p.name not in profiles
    )
    if extra:
        print(f"  额外配置文件（默认不扫描）: {extra}")
        profiles = profiles + tuple(extra)
    for profile in profiles:
        diag_profile(user_data_dir, profile)


def main() -> None:
    if len(sys.argv) > 1:
        diag_browser("custom", Path(sys.argv[1]))
        return
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    diag_browser("Edge", local / "Microsoft" / "Edge" / "User Data")
    diag_browser("Chrome", local / "Google" / "Chrome" / "User Data")


if __name__ == "__main__":
    main()
