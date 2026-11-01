# MiMo Token Plan 用量监控工具 — 设计文档

日期：2026-11-01
状态：已过 builder check，待用户批准后进入实现计划

## 背景与意图

用户在 Windows 上通过 Claude Code 等 AI 编程工具使用 Xiaomi MiMo Token Plan（`tp-` API Key，网关 `token-plan-cn.xiaomimimo.com`）。套餐额度（Credits）只在开放平台网页控制台的进度条里可见，日常开发中想确认剩余额度必须打断工作去开网页。本工具让用量信息常驻桌面（悬浮工具条 / 任务栏 / 托盘三种形态，参考 TrafficMonitor），一眼可见，定时自动刷新。

## 侦察结论（数据来源，2026-11-01 实测验证）

- 网关 `token-plan-cn.xiaomimimo.com` 只有模型调用接口（`POST /anthropic/v1/messages` 等），响应仅含单次请求的 token usage，无套餐余额；响应头无配额/限流信息。`tp-` key 无法查询套餐用量。
- 官方文档（`mimo.mi.com/docs`）无用量查询开放 API。
- 用量数据来自开放平台控制台 API（`platform.xiaomimimo.com`，从前端 JS 逆向确认）：
  - `GET /api/v1/tokenPlan/detail` — 套餐详情（总额度/剩余/有效期/续订状态等）
  - `GET /api/v1/tokenPlan/usage` — 用量进度数据
  - **认证**：小米账号 SSO 会话 cookie（`GET /api/v1/genLoginUrl` → 302 `account.xiaomi.com/pass/serviceLogin` → 回跳 `/sts?sign=` 签发会话）。`tp-` key 调用这两个接口返回 401（实测）。
  - 另有 `mm_ticket` 票据机制：登录回跳 URL 可携带 `mm_ticket` 查询参数通过部分接口鉴权（前端把它存 localStorage 用于带 `skipAuthRedirect` 的调用）。
- 计费背景（用于展示文案）：按 Credits 计费，不同模型扣减比例不同；北京时间 0:00–8:00 为非高峰，消耗系数 0.8x；有 RPM/TPM 限流（429 报错）。

## 目标

1. Windows 10/11 桌面常驻显示 Token Plan 用量，TrafficMonitor 式三种形态，可同时启用、独立开关：
   - **悬浮工具条**：置顶无边框小条，可拖动、可锁定、透明度可调，显示剩余百分比 + 进度条 + 到期时间。
   - **任务栏固定**：内嵌任务栏的小部件（任务栏区域显示用量数字/迷你条）。
   - **系统托盘图标**：动态百分比环图标 + 悬停 tooltip 明细 + 右键菜单。
2. 首次运行弹出内置 WebView 登录窗（pywebview/WebView2）完成小米账号登录；凭证本地加密保存并自动复用，会话过期自动重新弹登录。
3. 定时刷新：默认 60 秒，可配 30 秒–10 分钟；请求失败指数退避（上限 5 分钟）；剩余额度低于阈值（默认 10%）触发系统通知。
4. 数据展示核心字段（最终以登录后实测接口响应为准）：剩余 Credits 百分比（主显示）、剩余/总额度、到期日期、近期/今日消耗、限流提示（如接口提供）；tooltip 附非高峰时段提示。
5. 设置持久化：刷新间隔、阈值、三种形态开关、位置、透明度、锁定、开机自启（可选，默认关）。
6. **v1 承诺范围：Windows 10/11**（用户原话为「适用 windows 平台或者跨平台」，二者取一即可，故取 Windows 优先，对齐 TrafficMonitor 式三形态）；核心逻辑（`api`/`models`/`config`）保持平台无关，Linux/macOS 的托盘 + 悬浮条形态为**非承诺加分项**，v1 不做适配与测试。后续打包为 Windows x64 单文件 exe（Nuitka）。

## 非目标（v1 不做）

- 历史用量曲线 / 本地记账数据库（留 v2）。
- 多账号、团队版席位管理（仅个人版单账号）。
- 修改/代理 API 流量、抓包注入。
- 移动端、网页端。

## 反目标（做了即失败）

- 凭证外传：凭证只存本机（DPAPI 加密），绝不上传任何第三方。
- 高频轮询骚扰官方服务：刷新间隔下限 30 秒，失败退避。
- 篡改系统文件、向资源管理器注入 DLL。

## 约束

- 用量数据源唯一：`platform.xiaomimimo.com` 控制台 API。无 API Key 途径，必须走 SSO 会话，会话会过期。
- 该接口非公开、无 SLA：响应结构可能变化，字段映射必须容错（缺字段优雅降级为不显示）。
- Windows 11 任务栏结构随构建版本变化，任务栏形态需容错并带降级方案。
- 技术栈 Python 3.10+：`requests`、`pystray`、`Pillow`、`pywebview`（WebView2）；悬浮条与任务栏部件用 `tkinter` + `ctypes`（user32）。
- 凭证与配置存放 `%APPDATA%\mimo-usage-monitor\`。凭证存储做成可插拔后端（`storage.py`），v1 仅实现 Windows DPAPI 后端；未来移植其他平台时再补 keyring/文件权限后端。

## 已定的实现方向（builder 可细化，不可推翻）

- **架构分层**：
  - `api.py`：控制台 API 客户端（`/tokenPlan/detail`、`/tokenPlan/usage`），会话与 `mm_ticket` 鉴权、退避重试、快照缓存。
  - `auth.py`：pywebview 登录窗（入口 `genLoginUrl?currentPath=/console/usage`），WebView2 cookie 提取；凭证经 DPAPI 加密落盘。**降级路径**：WebView2 运行时缺失 → 引导安装提示；SSO 在内嵌 WebView 中被拒绝（登录页报错/无法继续）或用户点「登录遇到问题？」链接 → 应急通道：系统浏览器登录 + 手动粘贴一次 cookie，两条路径共用同一凭证存储。粘贴通道是安全网，不是并列的登录方式。
  - `models.py`：`UsageSnapshot` 数据类，容错映射 API 响应（字段实测后定稿）。
  - `display/`：`tray.py`（Pillow 动态绘制百分比环图标）、`floating_bar.py`（tkinter `overrideredirect` 置顶、可拖动、可穿透可选）、`taskbar.py`（ctypes 将部件内嵌进 `Shell_TrayWnd` 并收缩任务列表留位；失败降级为吸附任务栏边缘的置顶窗，视觉等效）。
  - `notify.py`：Windows toast / 托盘气泡阈值提醒。
  - `config.py`：JSON 配置读写。
  - `app.py`：主循环、刷新调度、状态总线（一次刷新广播给三种形态）。
- 阈值提醒语义：向下跌破阈值触发**一次**通知（不随每次刷新重复）；回升至「阈值 +2 个百分点」后重新武装（防抖动）；启动时若已低于阈值，启动后提示一次。
- 实测与 fixtures：登录实测环节需用户在 WebView 中人工完成一次小米账号登录（SSO 含短信/验证码，无法无人值守）；builder 捕获 `/tokenPlan/detail`、`/tokenPlan/usage` 真实响应，脱敏后存为测试 fixtures，字段映射据此定稿。
- 托盘百分比环颜色随余量渐变（绿→黄→红）。
- 双击悬浮条 / 托盘单击打开控制台 `platform.xiaomimimo.com/console/usage`。
- 任务栏形态参考 TrafficMonitor（GPL 开源）的**技术思路**自行用 ctypes 实现，不复制其代码。
- 网络错误时保留最后快照并标记陈旧（灰色时间戳 + 错误图标），不清空显示。
- 一次只有一个应用实例（单实例锁）。

## 留给 builder 的

- 登录后实测 `/tokenPlan/detail`、`/tokenPlan/usage` 响应结构，定稿字段映射与展示排版。
- 任务栏内嵌在具体 Windows 构建上的实现细节与降级判据。
- 图标美术与默认配色。
- `mm_ticket` 与 cookie 两种凭证的优先级与续期策略（以实际存活时长为准）。
- 测试策略与 Nuitka 打包脚本（打包为独立阶段任务）。
