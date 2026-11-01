# mimo-usage-monitor

MiMo Token Plan 用量桌面监控：以**悬浮工具条 / 任务栏部件 / 系统托盘图标**三种形态常驻显示套餐 Credits 用量，内置登录（优先从 Edge 导入已登录会话），定时自动刷新。

## 快速开始

```bash
pip install -e .[dev]
pytest
python -m mimo_usage_monitor
```

## 显示形态

- 悬浮工具条：置顶无边框小条，可拖动/锁定/调透明度
- 任务栏部件：内嵌任务栏的小部件（失败时自动降级为吸附窗）
- 托盘图标：动态百分比环 + tooltip 明细

## 文档

- 设计文档：`docs/superpowers/specs/2026-11-01-mimo-usage-monitor-design.md`
- 实现计划：`docs/superpowers/plans/2026-11-01-mimo-usage-monitor.md`
