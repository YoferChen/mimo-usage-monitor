import base64
import json
import sqlite3

import pytest

from mimo_usage_monitor.browser_cookies import load_chromium_cookie_header
from mimo_usage_monitor.storage import dpapi_protect

SCHEMA = "CREATE TABLE cookies(host_key TEXT, name TEXT, encrypted_value BLOB)"


def _make_profile(root, key: bytes, rows):
    (root / "Profile 1" / "Network").mkdir(parents=True)
    enc_key = base64.b64encode(b"DPAPI" + dpapi_protect(key)).decode()
    (root / "Local State").write_text(
        json.dumps({"os_crypt": {"encrypted_key": enc_key}}), encoding="utf-8"
    )
    con = sqlite3.connect(root / "Profile 1" / "Network" / "Cookies")
    con.execute(SCHEMA)
    for host, name, value, marker in rows:
        if marker is None:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = b"N" * 12
            body = nonce + AESGCM(key).encrypt(nonce, value.encode("utf-8"), None)
            blob = b"v10" + body
        else:
            blob = marker
        con.execute("INSERT INTO cookies VALUES (?,?,?)", (host, name, blob))
    con.commit()
    con.close()


def test_returns_cookie_header_for_domain(tmp_path):
    _make_profile(
        tmp_path,
        b"K" * 32,
        [
            (".xiaomimimo.com", "serviceToken", "tok-1", None),
            (".xiaomimimo.com", "userId", "42", None),
            (".other.com", "x", "y", None),
        ],
    )
    header = load_chromium_cookie_header(tmp_path, "xiaomimimo.com")
    assert header == "serviceToken=tok-1; userId=42"


def test_returns_none_when_no_match(tmp_path):
    _make_profile(tmp_path, b"K" * 32, [(".other.com", "x", "y", None)])
    assert load_chromium_cookie_header(tmp_path, "xiaomimimo.com") is None


def test_returns_none_on_v20_app_bound_value(tmp_path):
    _make_profile(
        tmp_path,
        b"K" * 32,
        [(".xiaomimimo.com", "serviceToken", "ignored", b"v20" + b"\x00" * 32)],
    )
    assert load_chromium_cookie_header(tmp_path, "xiaomimimo.com") is None


def test_returns_none_on_missing_user_data(tmp_path):
    assert load_chromium_cookie_header(tmp_path / "nope", "xiaomimimo.com") is None


def test_strips_host_hash_prefix(tmp_path):
    import hashlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = b"K" * 32
    host = ".xiaomimimo.com"
    prefixed = hashlib.sha256(host.encode("utf-8")).digest() + b"tok-1"
    nonce = b"N" * 12
    blob = b"v10" + nonce + AESGCM(key).encrypt(nonce, prefixed, None)
    _make_profile(tmp_path, key, [(host, "serviceToken", "", blob)])
    assert load_chromium_cookie_header(tmp_path, "xiaomimimo.com") == "serviceToken=tok-1"
