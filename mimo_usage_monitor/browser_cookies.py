"""从 Edge（Chromium）的 cookie 库提取指定域的会话 cookie。

只读取目标域的 cookie；解密使用 DPAPI + AES-GCM（v10/v11），
App-Bound Encryption（v20）无法用纯 DPAPI 解密，直接放弃并返回 None。
"""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .storage import dpapi_unprotect

DEFAULT_PROFILES = ("Default", "Profile 1", "Profile 2", "Profile 3")


def _load_key(user_data_dir: Path) -> bytes | None:
    try:
        state = json.loads(
            (user_data_dir / "Local State").read_text(encoding="utf-8")
        )
        raw = base64.b64decode(state["os_crypt"]["encrypted_key"])
    except (OSError, ValueError, KeyError):
        return None
    if not raw.startswith(b"DPAPI"):
        return None
    try:
        return dpapi_unprotect(raw[5:])
    except OSError:
        return None


def _decrypt(key: bytes, blob: bytes, host: str) -> str | None:
    if not blob.startswith((b"v10", b"v11")):
        return None
    nonce, body = blob[3:15], blob[15:]
    try:
        plain = AESGCM(key).decrypt(nonce, body, None)
    except Exception:
        return None
    # 新版 Chromium 在明文前加 SHA-256(host_key) 32 字节域名绑定前缀
    digest = hashlib.sha256(host.encode("utf-8")).digest()
    if plain.startswith(digest):
        plain = plain[len(digest):]
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _open_db_cookies(db_path: Path, domain: str) -> list[tuple[str, str, bytes]] | None:
    """读目标域的 cookie 行；Edge 运行中会锁库，先试复制副本，再试只读直连。"""
    con = None
    tmp = None
    try:
        tmp = Path(tempfile.mkdtemp()) / "cookies.db"
        shutil.copy2(db_path, tmp)
        con = sqlite3.connect(tmp)
    except OSError:
        try:
            con = sqlite3.connect(
                f"file:{db_path}?mode=ro".replace("\\", "/"), uri=True, timeout=3
            )
        except sqlite3.Error:
            return None
    try:
        return con.execute(
            "SELECT host_key, name, encrypted_value FROM cookies "
            "WHERE host_key LIKE ? ORDER BY rowid",
            (f"%{domain}%",),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp.parent, ignore_errors=True)


def load_edge_cookie_header(user_data_dir: Path, domain: str) -> str | None:
    """返回形如 "k=v; k2=v2" 的 Cookie 头；找不到或无法解密返回 None。"""
    key = _load_key(user_data_dir)
    if key is None:
        return None
    for profile in DEFAULT_PROFILES:
        db_path = user_data_dir / profile / "Network" / "Cookies"
        rows = _open_db_cookies(db_path, domain) or []
        pairs = []
        for host, name, blob in rows:
            value = _decrypt(key, blob, host)
            if value is not None:
                pairs.append(f"{name}={value}")
        if pairs:
            return "; ".join(pairs)
    return None
