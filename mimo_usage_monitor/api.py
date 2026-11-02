import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from .models import UsageSnapshot, parse_snapshot

DETAIL_PATH = "/api/v1/tokenPlan/detail"
USAGE_PATH = "/api/v1/tokenPlan/usage"
MAX_ATTEMPTS = 3


class AuthExpiredError(Exception):
    """会话失效（401/302），需要重新登录。"""


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CookieAuth:
    cookie_header: str


@dataclass(frozen=True)
class TicketAuth:
    ticket: str


class MimoApiClient:
    def __init__(
        self,
        auth: CookieAuth | TicketAuth,
        base_url: str = "https://platform.xiaomimimo.com",
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._sleep = sleep

    def fetch_snapshot(self) -> UsageSnapshot:
        detail = self._request_json(DETAIL_PATH)
        usage = self._request_json(USAGE_PATH)
        for payload in (detail, usage):
            code = payload.get("code") if isinstance(payload, dict) else None
            if code not in (0, None):
                raise ApiError(f"业务错误 code={code}", None)
        return parse_snapshot(detail, usage, datetime.now(timezone.utc))

    def _request_json(self, path: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(1 << (attempt - 1))  # 1s、2s
            try:
                resp = self._get(path)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if resp.status_code in (401, 302):
                raise AuthExpiredError(f"{path} 返回 {resp.status_code}")
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    last_error = ApiError(f"{path} 响应非 JSON", resp.status_code)
                    continue
            last_error = ApiError(f"{path} 返回 {resp.status_code}", resp.status_code)
        if isinstance(last_error, ApiError):
            raise last_error
        raise ApiError(f"{path} 请求失败: {last_error}")

    def _get(self, path: str):
        url = self._base_url + path
        headers = {}
        if isinstance(self._auth, CookieAuth):
            headers["Cookie"] = self._auth.cookie_header
        else:
            url = f"{url}?mm_ticket={quote(self._auth.ticket)}"
        return self._session.get(url, headers=headers, timeout=15, allow_redirects=False)
