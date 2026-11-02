# mimo-usage-monitor

MiMo Token Plan 用量桌面监控：以**悬浮工具条 / 任务栏部件 / 系统托盘图标**三种形态常驻显示套餐 Credits 用量，内置登录（优先从 Edge 导入已登录会话），定时自动刷新。

## 快速开始

```bash
pip install -e .[dev]
pytest
python -m mimo_usage_monitor
```

## 显示形态

- 悬浮工具条：置顶无边框小条，可拖动/锁定/调透明度，双击打开控制台
- 任务栏部件：内嵌任务栏的小部件（Win10）；Win11 任务栏不可扩展，自动降级为贴托盘左侧的吸附窗
- 托盘图标：动态百分比环（绿→黄→红）+ tooltip 明细 + 阈值提醒气泡

三形态可同开、独立开关（托盘右键菜单），设置里可调刷新间隔（30–600 秒）、提醒阈值、透明度、开机自启。

## 登录与凭证

按优先级自动选择：

1. **从 Edge 导入**：读取 Edge 已登录的 `xiaomimimo.com` 会话（Edge 未运行时可用；浏览器加密 v20 时不可用）
2. **内置 WebView 登录窗**：小米账号登录一次，凭证 DPAPI 加密存本地
3. **粘贴 Cookie 应急通道**：WebView 不可用时，浏览器登录后手动粘贴 cookie

## 故障排查

- 登录窗空白/打不开：安装 [WebView2 运行时](https://developer.microsoft.com/microsoft-edge/webview2/)（Win11 自带）
- Edge 导入不生效：关闭 Edge 后重试，或用 WebView 登录一次
- 用量显示「⚠ 已过期」：网络故障保留的是上次数据，恢复后自动续上

## 文档

- 设计文档：`docs/superpowers/specs/2026-11-01-mimo-usage-monitor-design.md`
- 实现计划：`docs/superpowers/plans/2026-11-01-mimo-usage-monitor.md`
