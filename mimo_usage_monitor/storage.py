import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

SESSION_FILENAME = "session.bin"

if os.name == "nt":
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _to_blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.c_char_p]:
    buf = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    return blob, buf


def _from_blob(blob: _DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def dpapi_protect(data: bytes) -> bytes:
    blob_in, keep = _to_blob(data)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    del keep
    return _from_blob(blob_out)


def dpapi_unprotect(data: bytes) -> bytes:
    blob_in, keep = _to_blob(data)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    del keep
    return _from_blob(blob_out)


class CredentialStore(Protocol):
    def save(self, blob: str) -> None: ...
    def load(self) -> str | None: ...
    def clear(self) -> None: ...


class DpapiCredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / SESSION_FILENAME

    def save(self, blob: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        cipher = dpapi_protect(blob.encode("utf-8"))
        tmp = self._path.with_suffix(".bin.tmp")
        tmp.write_bytes(cipher)
        os.replace(tmp, self._path)

    def load(self) -> str | None:
        try:
            cipher = self._path.read_bytes()
        except OSError:
            return None
        try:
            return dpapi_unprotect(cipher).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def clear(self) -> None:
        try:
            self._path.unlink()
        except OSError:
            pass


def get_default_store(data_dir: Path) -> CredentialStore:
    if os.name == "nt":
        return DpapiCredentialStore(data_dir)
    raise NotImplementedError("v1 仅实现 Windows DPAPI 凭证存储")
