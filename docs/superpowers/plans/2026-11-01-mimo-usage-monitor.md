# MiMo Token Plan 用量监控工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 10/11 上以悬浮工具条 / 任务栏部件 / 托盘图标三种形态常驻显示 MiMo Token Plan 的 Credits 用量，内置 WebView 登录小米账号后定时轮询开放平台控制台 API。

**Architecture:** 分层：`api`/`models`/`config`/`storage`/`notify` 为无 GUI 依赖的纯逻辑层（可单测）；`display/` 三个形态各自独立、消费同一个 `UsageSnapshot`；`app.py` 负责调度、单实例、状态广播。认证走 pywebview WebView2 登录一次抓 cookie（应急通道：手动粘贴 cookie），DPAPI 加密落盘。

**Tech Stack:** Python 3.10+；requests、pystray、Pillow、pywebview（运行依赖），pytest（开发）；不引入 pywin32（DPAPI/任务栏/单实例均用 ctypes，开机自启用 winreg）。

**Spec:** `docs/superpowers/specs/2026-11-01-mimo-usage-monitor-design.md`（本仓库内）

## Global Constraints

- v1 承诺平台 Windows 10/11；`config`/`storage`/`models`/`api`/`notify` 禁止 import GUI 库（tkinter/pystray/pywebview 只允许出现在 `display/`、`auth.py`、`app.py`）。
- API 基址 `https://platform.xiaomimimo.com`，端点 `GET /api/v1/tokenPlan/detail`、`GET /api/v1/tokenPlan/usage`。
- 刷新间隔 clamp 到 [30, 600] 秒，默认 60；阈值默认 10%；通知重置条件 = 回升到「阈值 +2.0 个百分点」。
- 凭证仅存本机 DPAPI 加密文件，绝不上传；数据/配置目录由 `data_dir()` 决定：`MIMO_MONITOR_HOME` 环境变量优先，否则 `%APPDATA%\mimo-usage-monitor\`。
- UI 文案中文；图标颜色：pct≥60 绿 `#22c55e`，20≤pct<60 黄 `#eab308`，pct<20 红 `#ef4444`，未知 灰 `#9ca3af`。
- 反目标：不做历史曲线、多账号、流量代理、DLL 注入。
- 每个 Task 一个提交周期；提交信息 `feat:`/`test:`/`fix:` 前缀，结尾附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 时区：内部一律 tz-aware UTC；北京时间 = UTC+8，非高峰 = 北京时间小时数 ∈ [0, 8)。

## Review Focus

1. **会话过期（401/302）后的行为**：用户会续期/过期 SSO 会话；期望触发一次重新登录而非崩溃或无限重试 → `test_fetch_snapshot_401_raises_auth_expired`（Task 6）、`test_ensure_auth_relogins_when_expired`（Task 7）。
2. **接口字段缺失/结构漂移**（非公开接口会变）：期望优雅降级为 None 字段，渲染层跳过该行，绝不抛异常 → `test_parse_snapshot_empty_dicts_no_raise`、`test_parse_snapshot_alternate_field_names`（Task 5）。
3. **网络断开/超时**：期望保留上一次快照并标记陈旧，指数退避，不清空显示 → `test_fetch_retries_then_raises_api_error`（Task 6）、`test_stale_marking_when_fetch_fails`（Task 12）。
4. **阈值附近振荡导致通知轰炸**：期望跌破只弹一次、回升 +2pp 才重新武装 → `test_silent_while_still_below`、`test_rearms_above_plus_delta_then_fires_again`（Task 8）。
5. **WebView2 缺失或 SSO 拒绝内嵌登录**：期望自动落到「浏览器登录 + 粘贴 cookie」通道，绝不死路 → `test_login_falls_back_to_paste_when_webview_unavailable`（Task 7）。

---

### Task 1: 项目脚手架与仓库初始化

**Files:**
- Create: `pyproject.toml`、`README.md`、`.gitignore`、`mimo_usage_monitor/__init__.py`、`mimo_usage_monitor/__main__.py`、`tests/test_smoke.py`

**Interfaces:**
- Consumes: 无（全新项目，仓库根 = `D:\AI_Agents\mimo-usage-monitor`）
- Produces: 可运行的 `pytest`；包名 `mimo_usage_monitor`；`__main__.py` 暂打印「组件未就绪」即可（Task 12 替换为真入口）。

- [ ] **Step 1: 初始化仓库与依赖文件**

`git init`（仓库根为项目目录）。`pyproject.toml`：`[project]` name `mimo-usage-monitor`，requires-python `>=3.10`，dependencies = `requests>=2.31`、`pystray>=0.19`、`Pillow>=10`、`pywebview>=5.0`；`[tool.pytest.ini_options]` testpaths = `["tests"]`。`.gitignore` 含 `__pycache__/`、`.venv/`、`tools/probe_output/`、`*.pyc`。`README.md` 写明：用途一段 + `pip install -e .` + `pytest` + `python -m mimo_usage_monitor` 三条命令。

- [ ] **Step 2: 写失败的冒烟测试**

```python
# tests/test_smoke.py
def test_package_imports():
    import mimo_usage_monitor  # noqa: F401
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL（ModuleNotFoundError 或无测试收集失败）。

- [ ] **Step 4: 建包骨架使测试通过**

`mimo_usage_monitor/__init__.py` 留空或 `__version__ = "0.1.0"`；`__main__.py` 含 `if __name__ == "__main__": print("mimo-usage-monitor 组件未就绪")`。安装：`pip install -e .`。

- [ ] **Step 5: 运行测试通过并提交**

Run: `pytest -v` → 全部 PASS。`git add -A && git commit -m "feat: 项目脚手架与 pytest 骨架"`（提交结尾加 Co-Authored-By 行，下同）。

### Task 2: 配置模块

**Files:**
- Create: `mimo_usage_monitor/config.py`、`tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `data_dir() -> Path`；`@dataclass AppConfig`（字段与默认值见下）；`load_config(data_dir: Path) -> AppConfig`；`save_config(data_dir: Path, cfg: AppConfig) -> None`（原子写：tmp + `os.replace`）。

`AppConfig` 字段（默认值即规格钉死值）：`refresh_interval_s: int = 60`、`threshold_pct: float = 10.0`、`notify_enabled: bool = True`、`show_tray: bool = True`、`show_floating: bool = True`、`show_taskbar: bool = False`、`floating_rect: tuple[int, int, int, int] = (0, 0, 380, 76)`（首次显示时由 app 解析为屏幕右上）；`floating_opacity: float = 0.9`、`floating_locked: bool = False`、`autostart: bool = False`。

- [ ] **Step 1: 写失败测试**

```python
def test_load_config_missing_returns_defaults(): ...   # load 后等于 AppConfig()
def test_load_config_corrupt_json_returns_defaults(): ...  # 写入 b"{bad json" 后 load == AppConfig()
def test_save_load_roundtrip(): ...                    # 改 refresh_interval_s=300, show_taskbar=True → save → load 相等
def test_refresh_interval_clamped(): ...               # 25→30, 9999→600（load 时 clamp）
def test_data_dir_env_override(monkeypatch, tmp_path): ...  # MIMO_MONITOR_HOME=tmp_path → data_dir()==tmp_path
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_config.py -v` → FAIL（模块不存在）。

- [ ] **Step 3: 实现 `config.py`**

按 Interfaces 的签名实现；clamp 只作用于 `refresh_interval_s`；文件名固定 `config.json`。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_config.py -v` → PASS。

- [ ] **Step 5: 提交**：`git add -A && git commit -m "feat: 配置模块（默认值/容错加载/原子保存）"`。

### Task 3: 凭证存储（DPAPI）

**Files:**
- Create: `mimo_usage_monitor/storage.py`、`tests/test_storage.py`

**Interfaces:**
- Consumes: 无
- Produces: `class CredentialStore(Protocol): save(blob: str) -> None; load() -> str | None; clear() -> None`；`class DpapiCredentialStore(data_dir: Path)`（实现该 Protocol，文件名 `session.bin`）；`get_default_store(data_dir: Path) -> CredentialStore`（win32 返回 `DpapiCredentialStore`，否则 `NotImplementedError`）。

- [ ] **Step 1: 写失败测试**（Windows 专属，`pytest.mark.skipif(os.name != "nt")`）

```python
def test_save_load_roundtrip_dpapi(tmp_path): ...   # save("blob-测试-123") → load() == 同串
def test_load_missing_returns_none(tmp_path): ...   # 全新目录 load() is None
def test_clear_removes(tmp_path): ...               # save 后 clear → load() is None
def test_get_default_store_returns_dpapi_on_windows(tmp_path): ...
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_storage.py -v` → FAIL。

- [ ] **Step 3: 实现 `storage.py`**

DPAPI 用 ctypes `crypt32.CryptProtectData` / `CryptUnprotectData`（DATA_BLOB 结构），无需 pywin32；`save` 原子写。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_storage.py -v` → PASS。

- [ ] **Step 5: 提交**：`git add -A && git commit -m "feat: DPAPI 凭证存储"`。

### Task 4: API 探查工具与 fixtures 采集（含人工登录）

**Files:**
- Create: `tools/probe_api.py`、`tests/fixtures/tokenplan_detail.json`、`tests/fixtures/tokenplan_usage.json`、`docs/api-shape.md`

**Interfaces:**
- Consumes: 无（独立脚本，可 import `mimo_usage_monitor.storage` 复用 DPAPI 存储）
- Produces: 两份脱敏 fixture（字段名/类型与线上一致，PII 值替换为占位）；`docs/api-shape.md` 记录字段表（字段路径 → 含义 → 对应 `UsageSnapshot` 字段）。**Task 5 的 FIELD_MAP 以这两份产物为准。**

- [ ] **Step 1: 写探查脚本**

`tools/probe_api.py`：pywebview 打开 `https://platform.xiaomimimo.com/api/v1/genLoginUrl?currentPath=/console/usage`；轮询 `window.get_cookies()`（0.5s 间隔）直到非空且 `window.get_current_url()` 主机为 `platform.xiaomimimo.com`；随后用 cookies 调两个端点，原始 JSON 落 `tools/probe_output/`（gitignore），同时打印字段结构（key 路径树）。

- [ ] **Step 2: 人工登录环节（需要用户在场）**

运行 `python tools/probe_api.py`，请用户在弹出的 WebView 窗口完成小米账号登录（含短信/验证码，无法无人值守）。脚本成功后退出。

- [ ] **Step 3: 脱敏并提交 fixtures**

把 `tools/probe_output/` 的两个响应脱敏后写入 `tests/fixtures/`（规则：key 全保留，数值保留量级，id/昵称/手机号/邮箱换成 `"TEST_*"` 占位）；`docs/api-shape.md` 写字段表。提交：`git add -A && git commit -m "test: 采集 tokenPlan 接口 fixtures 与字段表"`。

### Task 5: 数据模型与容错映射

**Files:**
- Create: `mimo_usage_monitor/models.py`、`tests/test_models.py`

**Interfaces:**
- Consumes: `tests/fixtures/tokenplan_detail.json`、`tests/fixtures/tokenplan_usage.json`、`docs/api-shape.md`（Task 4）
- Produces:

```python
@dataclass(frozen=True)
class UsageSnapshot:
    fetched_at: datetime            # tz-aware UTC
    plan_name: str | None = None
    total_credits: float | None = None
    used_credits: float | None = None
    remaining_credits: float | None = None
    remaining_pct: float | None = None   # 派生：remaining/total*100，1 位小数；total 缺失/0 → None
    expire_at: datetime | None = None
    today_used_credits: float | None = None
    rate_limit_note: str | None = None
    is_stale: bool = False

def parse_snapshot(detail: dict, usage: dict, now: datetime) -> UsageSnapshot: ...  # 永不抛异常
def is_offpeak(now: datetime) -> bool: ...   # 北京时间 hour ∈ [0, 8)
```

字段映射由模块级 `FIELD_MAP: dict[str, tuple[str, ...]]`（Snapshot 字段 → 候选 key 路径元组，按序取第一个命中）驱动，字段名取自 `docs/api-shape.md`。

- [ ] **Step 1: 写失败测试**

```python
def test_parse_snapshot_full_fixture(): ...          # 两份 fixture 解析后各字段 == fixture 映射值；remaining_pct == pytest.approx(remaining/total*100, abs=0.1)
def test_parse_snapshot_empty_dicts_no_raise(): ...  # parse_snapshot({}, {}, now) → 全 None，不抛
def test_parse_snapshot_alternate_field_names(): ... # 用 FIELD_MAP 里的候选 key 构造小 dict，验证第二候选也能命中
def test_remaining_pct_none_when_total_zero(): ...   # total=0 或缺失 → remaining_pct is None
def test_is_offpeak_beijing(): ...                   # 2026-11-01T23:00Z → True（北京 7 点）；2026-11-01T12:00Z → False（北京 20 点）
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_models.py -v` → FAIL。

- [ ] **Step 3: 实现 `models.py`**

`_dig(data, *candidates)` 逐路径取值；数值容错（str→float 尝试转换，失败→None）；时间解析 ISO 8601（无 tz 视为 UTC）。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_models.py -v` → PASS。

- [ ] **Step 5: 提交**：`git add -A && git commit -m "feat: UsageSnapshot 模型与容错字段映射"`。

### Task 6: 控制台 API 客户端

**Files:**
- Create: `mimo_usage_monitor/api.py`、`tests/test_api.py`

**Interfaces:**
- Consumes: `models.parse_snapshot`
- Produces:

```python
class AuthExpiredError(Exception): ...
class ApiError(Exception): status_code: int | None

@dataclass(frozen=True)
class CookieAuth: cookie_header: str
@dataclass(frozen=True)
class TicketAuth: ticket: str

class MimoApiClient:
    def __init__(self, auth: CookieAuth | TicketAuth,
                 base_url: str = "https://platform.xiaomimimo.com",
                 session: requests.Session | None = None) -> None: ...
    def fetch_snapshot(self) -> UsageSnapshot: ...
```

行为：`CookieAuth` → 请求头 `Cookie: {cookie_header}`；`TicketAuth` → 查询参数 `mm_ticket={ticket}`；两个 GET 各最多 3 次尝试（间隔 1s、2s），401/302 → `AuthExpiredError`（不重试），其余非 200 或传输错误 → 重试后抛 `ApiError`；成功 → `parse_snapshot(detail, usage, datetime.now(timezone.utc))`。

- [ ] **Step 1: 写失败测试**（用注入的假 `requests.Session`，monkeypatch 其 `get`）

```python
def test_fetch_snapshot_happy_path(fake_session, fixtures): ...     # 返回 fixture JSON；断言 UsageSnapshot 字段与 Task 5 一致
def test_fetch_snapshot_401_raises_auth_expired(fake_session): ...  # 401 → AuthExpiredError，且只调用 1 次
def test_fetch_snapshot_302_raises_auth_expired(fake_session): ...
def test_fetch_retries_then_raises_api_error(fake_session): ...     # 始终 500 → ApiError，call_count == 3
def test_cookie_auth_sets_header(...): ...                          # 捕获请求 kwargs：headers["Cookie"] == "a=b; c=d"
def test_ticket_auth_appends_query_param(...): ...                  # 捕获 URL：含 "mm_ticket=abc123"
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_api.py -v` → FAIL。

- [ ] **Step 3: 实现 `api.py`**

按 Interfaces 实现；`time.sleep` 用可注入的 `sleep=time.sleep` 构造参数以便测试传入 no-op。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_api.py -v` → PASS。

- [ ] **Step 5: 提交**：`git add -A && git commit -m "feat: tokenPlan 控制台 API 客户端（重试/退避/双鉴权）"`。

### Task 7: 登录与凭证管理

**Files:**
- Create: `mimo_usage_monitor/auth.py`、`tests/test_auth.py`

**Interfaces:**
- Consumes: `storage.CredentialStore`、`api.{CookieAuth, TicketAuth, MimoApiClient, AuthExpiredError}`
- Produces:

```python
def auth_to_blob(auth: CookieAuth | TicketAuth) -> str: ...          # JSON {"type": "cookie"|"ticket", "value": ...}
def auth_from_blob(blob: str) -> CookieAuth | TicketAuth: ...
def parse_cookie_header(text: str) -> str | None: ...                # 剥掉 "Cookie:" 前缀与空白，返回 "k=v; k2=v2"；无效 → None
def login_with_webview(launcher=None) -> CookieAuth | TicketAuth | None: ...  # launcher 可注入以便测试
def login_with_paste() -> CookieAuth | None: ...
def ensure_auth(store: CredentialStore, client_factory, login_webview=None, login_paste=None) -> CookieAuth | TicketAuth: ...
```

行为钉死：`login_with_webview` 打开 Task 4 同款 genLoginUrl，轮询 `window.get_cookies()`，**以探活为准**——用抓到的凭证立即调 `/tokenPlan/detail`，成功才返回；失败/超时（300s）→ None。WebView 不可用（pywebview 抛错）或返回 None → `login_with_paste`：`webbrowser.open` 控制台 + tkinter 文本框收集 Cookie 头，同样探活。`ensure_auth`：load blob → 探活 → 失效则 webview 登录 → 失败则 paste → 仍无则抛 `RuntimeError("需要登录")`。

- [ ] **Step 1: 写失败测试**（launcher/探活全部注入假对象，不真开窗）

```python
def test_auth_blob_roundtrip(): ...                          # CookieAuth 与 TicketAuth 各一轮
def test_parse_cookie_header(): ...                          # "Cookie: a=b; c=d" → "a=b; c=d"；纯 "a=b" → 原样；空/垃圾 → None
def test_ensure_auth_uses_stored_valid(): ...                # 存量凭证探活成功 → 不触发登录
def test_ensure_auth_relogins_when_expired(): ...            # 探活抛 AuthExpiredError → 调 webview 登录一次
def test_login_falls_back_to_paste_when_webview_unavailable(): ...  # launcher 抛 RuntimeError → 走 login_paste 并返回其结果
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_auth.py -v` → FAIL。

- [ ] **Step 3: 实现 `auth.py`**

pywebview 的导入放函数内（GUI 依赖延迟导入）；探活复用 `MimoApiClient.fetch_snapshot` 的轻量替代：只 GET detail 看状态码（新增内部函数 `_probe(auth) -> bool`）。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_auth.py -v` → PASS。

- [ ] **Step 5: 手工验证登录窗**：运行 `python tools/probe_api.py` 弹窗正常（复用 Task 4 脚本即验证）→ 提交：`git add -A && git commit -m "feat: WebView 登录 + 粘贴 cookie 应急通道"`。

### Task 8: 阈值通知状态机

**Files:**
- Create: `mimo_usage_monitor/notify.py`、`tests/test_notify.py`

**Interfaces:**
- Consumes: `models.UsageSnapshot`
- Produces:

```python
class NotifierSink(Protocol):
    def notify(self, title: str, body: str) -> None: ...

class ThresholdNotifier:
    def __init__(self, threshold_pct: float, rearm_delta_pp: float = 2.0) -> None: ...
    def update(self, snapshot: UsageSnapshot, at_startup: bool = False) -> bool: ...  # True = 本次应弹通知
```

语义钉死（规格原文）：`remaining_pct` 非 None 且 `< threshold_pct` 且（已武装或 `at_startup`）→ 返回 True 并解除武装；`remaining_pct >= threshold_pct + rearm_delta_pp` → 重新武装；其余 → False。标题「MiMo Token Plan 额度不足」，正文「剩余 {pct:.1f}%（{remaining} / {total} Credits）」。

- [ ] **Step 1: 写失败测试**

```python
def test_fires_once_on_crossing_below(): ...            # 15%→True，9%→True，8%→False
def test_silent_while_still_below(): ...                # 连续 5 次 <阈值 仅首次 True
def test_rearms_above_plus_delta_then_fires_again(): ...# 阈值 10：9%→True，11.9%→False（未达 12 不重武装），12.0%→False（重武装但不弹），9%→True
def test_startup_below_fires_once(): ...                # 首次 update(..., at_startup=True) 5% → True，随后 False
def test_no_fire_when_pct_unknown(): ...                # remaining_pct=None → 恒 False
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_notify.py -v` → FAIL。

- [ ] **Step 3: 实现 `notify.py`**（纯状态机，不含真实弹窗；弹窗 sink 在 Task 10/12 接）。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_notify.py -v` → PASS。

- [ ] **Step 5: 提交**：`git add -A && git commit -m "feat: 阈值通知状态机（跌破一次/防振荡重武装）"`。

### Task 9: 悬浮工具条

**Files:**
- Create: `mimo_usage_monitor/display/__init__.py`、`mimo_usage_monitor/display/floating_bar.py`、`tests/test_floating_bar.py`

**Interfaces:**
- Consumes: `models.UsageSnapshot`、`config.AppConfig.floating_rect/opacity/locked`
- Produces:

```python
def format_bar_text(s: UsageSnapshot) -> str: ...
def format_credits(x: float) -> str: ...   # ≥1e6 → "{x/1e6:.1f}M"；≥1e3 → "{x/1e3:.1f}K"；否则 "{x:.0f}"
class FloatingBar:
    def __init__(self, callbacks: dict, rect: tuple[int, int, int, int], opacity: float, locked: bool) -> None: ...
    def update(self, s: UsageSnapshot) -> None: ...
    def set_locked(self, locked: bool) -> None: ...
    def apply_opacity(self, opacity: float) -> None: ...
    def destroy(self) -> None: ...
```

`format_bar_text` 钉死格式（缺字段跳过对应段，段间 ` · `）：`剩余 {remaining_pct:.1f}%` + 进度条（10 格，字符 `▓`/`░`）；有 credits → `{remaining_credits} / {total_credits} Credits`（数字用 `format_credits`：≥1e6 显示 `{x/1e6:.1f}M`，≥1e3 显示 `{x/1e3:.1f}K`，否则 `{x:.0f}`）；有到期 → `到期 {YYYY-MM-DD}`；`is_stale` → 追加 ` ⚠ 已过期`。`callbacks` 键：`on_refresh`、`on_open_console`、`on_quit`、`on_toggle_taskbar`、`on_toggle_notify`、`on_open_settings`（右键菜单接线，Task 12 传入）。

- [ ] **Step 1: 写失败测试**（只测纯函数，不建窗）

```python
def test_format_bar_text_full(): ...          # 断言精确字符串（进度条 7/10 格）
def test_format_bar_text_partial_fields(): ...# 只有 pct → "剩余 42.0% ▓▓▓▓░░░░░░"
def test_format_bar_text_stale_suffix(): ...
def test_format_credits(): ...                # 12_300_000→"12.3M"，8_500→"8.5K"，420→"420"
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_floating_bar.py -v` → FAIL。

- [ ] **Step 3: 实现 `floating_bar.py`**

tkinter `overrideredirect(True)` + `topmost`；`<B1-Motion>` 拖动（`locked=True` 时禁用）；`<Double-Button-1>` 绑定 `callbacks["on_open_console"]`；`wm_attributes("-alpha", opacity)`；右键弹 `tk.Menu` 接 callbacks。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_floating_bar.py -v` → PASS。

- [ ] **Step 5: 手工验证 + 提交**：临时脚本实例化 FloatingBar 塞假 snapshot——窗口置顶、可拖动、锁定后不可拖、右键菜单出现；`git add -A && git commit -m "feat: 悬浮工具条"`。

### Task 10: 托盘图标与 tooltip

**Files:**
- Create: `mimo_usage_monitor/display/tray.py`、`tests/test_tray.py`

**Interfaces:**
- Consumes: `models.{UsageSnapshot, is_offpeak}`、`notify.NotifierSink`
- Produces:

```python
def render_percent_icon(pct: float | None, size: int = 64) -> Image.Image: ...  # Pillow 圆环
def format_tooltip(s: UsageSnapshot) -> str: ...
class TrayDisplay:
    def __init__(self, menu_items: list, on_notify: NotifierSink | None = None) -> None: ...
    def update(self, s: UsageSnapshot) -> None: ...   # 换图标 + tooltip
    def notify(self, title: str, body: str) -> None: ...  # 实现 NotifierSink：pystray icon.notify
    def stop(self) -> None: ...
```

`format_tooltip` 行为：行 = 套餐名（有则）、`剩余 {pct:.1f}%（{remaining} / {total} Credits）`（缺省跳过）、`到期 {YYYY-MM-DD}`、`今日消耗 {today_used_credits}`、`rate_limit_note`（有则单独一行）、`is_offpeak(now)` 为 True 时追加「非高峰时段（0.8x）」；`is_stale` 追加「⚠ 数据过期」。`render_percent_icon`：圆环起于 12 点顺时针，颜色按 Global Constraints 的四档；`pct=None` 全灰。

- [ ] **Step 1: 写失败测试**

```python
def test_render_icon_colors(): ...    # pct=80/40/10/None：环上采样像素 RGB 接近对应色（容差 ±10）
def test_render_icon_size(): ...      # size=64 → (64, 64)
def test_format_tooltip_lines(): ...  # 全字段 → 各行精确断言
def test_format_tooltip_offpeak(): ...# now=北京 3 点 → 含「非高峰」
def test_format_tooltip_stale(): ...  # 含「数据过期」
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_tray.py -v` → FAIL。

- [ ] **Step 3: 实现 `tray.py`**

pystray 在守护线程跑（`pystray.Icon.run_detached()` 或独立线程 `run()`）；Pillow 画环用 `ImageDraw.arc`。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_tray.py -v` → PASS。

- [ ] **Step 5: 手工验证 + 提交**：临时脚本显示托盘图标——百分比环颜色正确、悬停 tooltip、气泡通知可达；`git add -A && git commit -m "feat: 托盘百分比环图标与 tooltip"`。

### Task 11: 任务栏部件（含降级）

**Files:**
- Create: `mimo_usage_monitor/display/taskbar.py`、`tests/test_taskbar.py`

**Interfaces:**
- Consumes: `models.UsageSnapshot`
- Produces:

```python
@dataclass(frozen=True)
class Rect: x: int; y: int; w: int; h: int

def compute_placement(taskbar_rect: Rect, tray_rect: Rect, widget_w: int = 180, widget_h: int = 30) -> Rect: ...
def format_taskbar_text(s: UsageSnapshot) -> str: ...   # "余87% · 23d"；stale → "余87% ⚠"；仅 pct → "余87%"
class TaskbarWidget:
    def try_embed(self) -> bool: ...    # 成功 True；失败 False（调用方切降级）
    def update(self, s: UsageSnapshot) -> None: ...
    def destroy(self) -> None: ...
class DockedFallback:                   # 吸附任务栏边缘的置顶 tool 窗
    def __init__(self, rect: Rect) -> None: ...
    def update(self, s: UsageSnapshot) -> None: ...
    def destroy(self) -> None: ...
```

`compute_placement` 钉死：贴 `tray_rect` 左缘向左排（`x = tray_rect.x - widget_w - 4`），垂直居中于任务栏（`y = taskbar_rect.y + (taskbar_rect.h - widget_h) // 2`）。`try_embed` 实现：ctypes `FindWindowW("Shell_TrayWnd", None)` → 量取任务栏与托盘区（`TrayNotifyWnd`）矩形 → 创建无激活 tool 窗口（`WS_EX_TOOLWINDOW|WS_EX_TOPMOST`，父/属主为任务栏）置于 `compute_placement` 位置，并把任务列表区（`MSTaskListWClass`）`SetWindowPos` 收缩让位；任何一步失败或让位校验不通过 → 返回 False。

- [ ] **Step 1: 写失败测试**

```python
def test_compute_placement_right_aligns_left_of_tray(): ...  # 精确 Rect 断言
def test_format_taskbar_text(): ...                          # 全字段/仅 pct/stale 三例
def test_try_embed_failure_falls_back(): ...                 # 注入假 embedder 恒 False → try_embed() is False
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_taskbar.py -v` → FAIL。

- [ ] **Step 3: 实现 `taskbar.py`**（ctypes user32；`try_embed` 的可测性通过可注入的 `_win32` 门面实现，默认真 ctypes）。

- [ ] **Step 4: 测试通过**：Run: `pytest tests/test_taskbar.py -v` → PASS。

- [ ] **Step 5: 手工验证 + 提交**：临时脚本 `try_embed()` → 真机任务栏出现部件且任务列表让位；人为构造失败 → 出现 `DockedFallback` 吸附窗；`git add -A && git commit -m "feat: 任务栏内嵌部件与吸附降级"`。

### Task 12: 应用主循环与整合

**Files:**
- Create: `mimo_usage_monitor/app.py`、`tests/test_app.py`
- Modify: `mimo_usage_monitor/__main__.py`

**Interfaces:**
- Consumes: 前面全部模块的产出
- Produces:

```python
def acquire_single_instance() -> bool: ...   # 命名互斥量 Local\mimo-usage-monitor-singleton；False = 已有实例
class RefreshLoop:
    def __init__(self, fetch: Callable[[], UsageSnapshot], interval_s: float,
                 on_snapshot: Callable[[UsageSnapshot], None],
                 on_error: Callable[[Exception], None],
                 sleep: Callable[[float], None] = time.sleep) -> None: ...
    def start(self) -> None: ...   # 守护线程
    def stop(self) -> None: ...
    def trigger_now(self) -> None: ...   # 菜单「立即刷新」
```

行为钉死：`fetch` 抛异常 → 保留最近快照、置 `is_stale=True` 后仍回调 `on_snapshot`，同时 `on_error(e)`，下次等待 `min(interval * 2**连续失败次数, 300)`；成功则清零退避。`__main__.py` 装配：`ensure_auth` →（失败则登录流程）→ 建三形态（按配置开关）→ `RefreshLoop` → 托盘/悬浮右键菜单（立即刷新、打开控制台 `https://platform.xiaomimimo.com/console/usage`、悬浮条✓、任务栏✓、通知✓、设置…、退出）→ `ThresholdNotifier` + `TrayDisplay.notify` sink。启动时首帧标记 `at_startup=True`。

- [ ] **Step 1: 写失败测试**（假 client/假 clock，不建窗）

```python
def test_acquire_single_instance_second_call_false(): ...      # 第一次 True 第二次 False（Windows）
def test_refresh_loop_invokes_callbacks(): ...                 # interval=0.05，2 次回调后 stop
def test_refresh_loop_backoff_on_error(): ...                  # fetch 恒抛错 → sleep 记录为 60→120（interval=60）
def test_stale_marking_when_fetch_fails(): ...                 # 先成功后失败 → 第二帧 is_stale True 且字段保留
def test_trigger_now_shortens_wait(): ...                      # trigger_now 后立刻产生一次 fetch
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_app.py -v` → FAIL。

- [ ] **Step 3: 实现 `app.py` 与 `__main__.py`**（装配细节可自由发挥，接口不许变）。

- [ ] **Step 4: 测试通过**：Run: `pytest -v` → 全绿。

- [ ] **Step 5: 手工验证 + 提交**：`python -m mimo_usage_monitor`——登录一次、三形态同开、60s 自动刷新、断网后显示 ⚠ 并保留数据、恢复后自动续上、二次启动提示单实例；`git add -A && git commit -m "feat: 应用主循环/单实例/菜单整合"`。

### Task 13: 设置对话框、开机自启与收尾

**Files:**
- Create: `mimo_usage_monitor/settings.py`、`tests/test_settings.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `config.{AppConfig, load_config, save_config}`、`app` 的菜单接线
- Produces:

```python
def apply_settings(cfg: AppConfig, values: dict) -> AppConfig: ...   # 纯函数：表单值 → 新配置（含 clamp）
def set_autostart(enabled: bool, command: str, reg_writer=None) -> None: ...  # HKCU\...\Run 值 "MimoUsageMonitor"
class SettingsDialog: ...   # tkinter 表单：间隔/阈值/三开关/通知/自启；确定 → apply_settings + save_config + 回调
```

`apply_settings` 钉死：`refresh_interval_s` clamp [30,600]、`threshold_pct` clamp [0,100]、`floating_opacity` clamp [0.3,1.0]。

- [ ] **Step 1: 写失败测试**

```python
def test_apply_settings_clamps(): ...              # 间隔 5→30、阈值 150→100、透明度 0.1→0.3
def test_apply_settings_updates_toggles(): ...
def test_set_autostart_writes_run_key(): ...       # 假 reg_writer 记录 (path, name, command)；enable/disable 各一
```

- [ ] **Step 2: 运行确认失败**：Run: `pytest tests/test_settings.py -v` → FAIL。

- [ ] **Step 3: 实现 `settings.py`** 并接入 `app.py` 菜单「设置…」（`apply_settings`/`set_autostart` 保持可单测，tkinter 代码分离）。

- [ ] **Step 4: 测试通过**：Run: `pytest -v` → 全绿。

- [ ] **Step 5: 手工验证 + 提交**：改间隔为 30s 生效、勾选自启后 `HKCU\...\Run` 出现 `MimoUsageMonitor`、重启应用配置保留；README 补「三种显示形态 / 设置 / 登录与凭证 / 故障排查（WebView2 安装、粘贴 cookie 通道）」。`git add -A && git commit -m "feat: 设置对话框与开机自启"`。

（打包 Nuitka 单文件 exe 按规格属独立阶段，不在本计划内。）
