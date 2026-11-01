import os

import pytest

from mimo_usage_monitor.storage import DpapiCredentialStore, get_default_store

pytestmark = pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")


def test_save_load_roundtrip_dpapi(tmp_path):
    store = DpapiCredentialStore(tmp_path)
    store.save("blob-测试-123")
    assert store.load() == "blob-测试-123"


def test_load_missing_returns_none(tmp_path):
    assert DpapiCredentialStore(tmp_path).load() is None


def test_clear_removes(tmp_path):
    store = DpapiCredentialStore(tmp_path)
    store.save("x")
    store.clear()
    assert store.load() is None


def test_get_default_store_returns_dpapi_on_windows(tmp_path):
    assert isinstance(get_default_store(tmp_path), DpapiCredentialStore)
