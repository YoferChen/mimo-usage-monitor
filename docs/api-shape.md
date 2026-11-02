# tokenPlan 控制台 API 字段表

采集时间：2026-11-02，来源：`platform.xiaomimimo.com`，凭证 = 小米账号 SSO 会话 cookie。
原始响应存于 `tools/probe_output/`（gitignore），脱敏后存 `tests/fixtures/`（本样本不含姓名/手机号/邮箱等 PII，按原样入库）。

## GET /api/v1/tokenPlan/detail

响应：`{code: 0, message: "", data: {...}}`，`code != 0` 视为业务错误。

| 字段路径 | 含义 | UsageSnapshot 映射 |
|---|---|---|
| `data.planName`（备选 `data.planCode`） | 套餐名 | `plan_name` |
| `data.currentPeriodEnd` | 当前订阅周期结束时间，格式 `YYYY-MM-DD HH:MM:SS`，**按北京时间（UTC+8）解析** | `expire_at` |
| `data.expired` | 是否已过期（bool） | 供 `expire_at` 展示参考，不单独入快照 |
| `data.enableAutoRenew` / `data.hasAutoRenewSubscribed` | 自动续订开关/订阅态 | v1 tooltip 展示用，不入快照 |
| `data.clawEnabled` / `clawPeriodEnd` / `clawPurchased` | MiMo Claw 权益 | v1 不使用 |
| `data.autoRenewDiscount` | 自动续订折扣（常为 null） | 不使用 |

## GET /api/v1/tokenPlan/usage

| 字段路径 | 含义 | UsageSnapshot 映射 |
|---|---|---|
| `data.usage.items[name=="plan_total_token"].limit` | 套餐 Credits 总量 | `total_credits`（与补偿桶求和） |
| `data.usage.items[name=="plan_total_token"].used` | 套餐 Credits 已用 | `used_credits`（与补偿桶求和） |
| `data.usage.items[name=="compensation_total_token"].limit/.used` | 补偿 Credits 桶（可能为 0） | 并入 `total_credits`/`used_credits` 合计 |
| `data.usage.percent` | 整体**已用**比例（0–1，如 0.55 = 已用 55%） | `remaining_pct = (1 − used/total) × 100`，1 位小数 |
| `data.monthUsage.items[name=="month_total_token"].used` | 本月已用 | `month_used_credits`（快照新增字段；接口无「今日」粒度，`today_used_credits` 恒为 None） |
| — | 无限流（RPM/TPM）字段 | `rate_limit_note = None` |

## 语义要点

- 所有 `percent` 字段是**已用**比例（0–1），不是剩余比例。
- `items` 是按 `name` 标识的桶列表：`plan_total_token`（套餐）、`compensation_total_token`（补偿）。合计口径 = 两桶 sum。
- 鉴权：401 响应体带 `loginUrl`（SSO 重登入口），可用于引导重新登录。
- 时间格式 `YYYY-MM-DD HH:MM:SS` 无时区后缀，按北京时间解析（服务为中国集群）。
