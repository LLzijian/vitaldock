# VitalDock · 个人健康数据坞

**你说“我刚跑完”，个人 agent 就去获取最新数据，和你聊这次跑得怎样。**

VitalDock 为个人 agent 提供按需读取的运动与健康数据接口。当前主路线是 **华为运动健康原生连接 → Intervals.icu → VitalDock → agent**，每次查询都访问 API，返回最新可用跑步、历史比较和近期恢复指标。

> Fresh running and recovery context for personal agents. Huawei first.

## 从零开始

- [注册 Intervals.icu、连接华为、获取 API key 并配置 VitalDock](docs/intervals-setup.md)
- [给 agent 调用的接口：MCP、JSON 命令和 Python](docs/agent-api.md)
- [MCP 工具参数 JSON](interfaces/mcp-tools.json)、[通用客户端配置](examples/mcp-client.json)、[Codex 配置](examples/codex-mcp.toml)

## 日常如何使用

一次性连接自己的 Intervals.icu 账号，把 MCP 启动项交给个人 agent。之后直接说：

> 我刚跑完，看看这次和上次相近距离的跑步有什么变化，再结合最近睡眠和静息心率聊聊。

agent 调用 `running_context`，获取：

- 刚完成的华为跑步：距离、运动时间、经过时长、配速、平均／最高心率、爬升、平台训练负荷。
- 历史中距离相近、跑步类型相同的一次记录，以及两次的数值差异。
- 按授权读取的近期睡眠、静息心率及有数据时的 HRV，与之前有记录日期的均值。
- 可选的心率、速度、距离等时间序列，每序列最多 400 个展示点，不包含 GPS。
- 本次读取时间、平台同步时间、资料缺失情况和等待同步状态。

如果刚完成的运动还没上传，工具返回 `awaiting_upstream_sync`，不会拿上次的记录冒充新数据。重新调用时会重新读取 API；工具不能替桌面端强制唤醒手表或手机同步。

## 当前版本

**0.3.0：完整注册教程与可直接调用的 agent 接口。** 提供连接检查、华为活动列表、独立恢复查询和跑后上下文，覆盖 MCP、JSON 命令和 Python。个人 API 认证、真实活动及 wellness 读取已验证；公开自动测试和示例全部使用虚构数据。跑步比较的真实验收需要相应跑步记录。

[Intervals.icu 官方华为接入指南](https://www.intervals.icu/integrations/huawei/)已提供原生连接。中国大陆账号是否能授权，以自己的实际连接结果为准；已经连接的账号可直接配置 API key。完整路线比较见[原生接入方案](docs/native-sync.md)。

## 安装与一次性授权

Python 3.11 或以上。Windows PowerShell，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,live]"
.\.venv\Scripts\vitaldock.exe connect-intervals
```

最后一条命令由本人在本机终端运行，隐藏输入 Intervals.icu 的个人 API key；程序先验证可读取本人账号，再将 key 保存到 Windows 凭据管理器。macOS 使用 Keychain；Linux 需要受支持的系统密钥服务，也可通过进程环境变量 `VITALDOCK_INTERVALS_API_KEY` 注入。

在 Intervals.icu 的设置底部找到 Developer Settings／API key。不要把 key 发到聊天、写在命令参数里或提交 GitHub。个人使用不需要申请 Intervals.icu OAuth 应用；多人产品应改用经批准的 OAuth 应用和最小只读权限。

如果尚未完成华为连接，先打开[连接设置](https://intervals.icu/settings/connections?services=huawei)，授权 HUAWEI Health，并在手机运动健康中确认 Health Service Kit 已连接。已经连接则直接配置 API key。

## 连接个人 agent

MCP 是 agent 调用工具的通用协议。使用自己的绝对路径配置，密钥由启动服务的同一系统用户从凭据管理器读取：

```json
{
  "mcpServers": {
    "vitaldock-live": {
      "command": "D:/path/to/vitaldock/.venv/Scripts/python.exe",
      "args": ["-m", "vitaldock", "mcp-live", "--wellness", "--streams"]
    }
  }
}
```

`--wellness` 授予近期恢复指标，`--streams` 授予跑步的心率等采样序列。省略时不会读取相应类别。接口固定访问 API key 所属本人账号，只返回来源为 `HUAWEI` 的活动；跑后上下文进一步筛选跑步类型。只使用本地标准输入输出，不开放网络端口，不修改平台数据。

agent 可以发现以下工具：

| 工具 | 作用 |
|---|---|
| `connection_status` | 验证 API 连接，不返回密钥或具体健康值 |
| `recent_activities` | 读取华为跑步、通用训练等近期活动 |
| `wellness_context` | 独立查询近期恢复观测；需要 `--wellness` |
| `running_context` | 刚跑完时读取本次、历史对照与已授权恢复资料 |

无 MCP 的 agent 也能调用 JSON 命令：

```powershell
.\.venv\Scripts\vitaldock.exe check-connection --day 2026-10-27
.\.venv\Scripts\vitaldock.exe recent-activities --day 2026-10-27 --history-days 7 --limit 5
.\.venv\Scripts\vitaldock.exe wellness-context --day 2026-10-27 --history-days 28
.\.venv\Scripts\vitaldock.exe agent-tools --wellness
```

以上日期仅为示例，调用时使用本人当地日期。`agent-tools` 无需密钥或网络；其余命令读取本人的最新 API 数据。完整参数和错误约定见 [agent-api.md](docs/agent-api.md)。

命令行也可直接读取，例如：

```powershell
.\.venv\Scripts\vitaldock.exe run-context --day 2026-10-27 --completed-after 2026-10-27T16:00:00+08:00 --wellness
```

`--day` 是本人的当地日期，`--completed-after` 是用于识别刚完成跑步的最近时间下限；实际使用时由 agent 按对话确定。每次读取历史默认 28 天，可设置 1～90 天。返回缺失数据或等待状态时，agent 应据实回应。

## 三条接入路线

| 路线 | 定位 |
|---|---|
| 华为 → Intervals.icu 原生连接 → VitalDock | 当前主路线；已连接华为的账号可直接继续 API key 联调 |
| 华为官方开发者应用 → Health Service Kit REST／Android SDK | 后续独立直连；需要核实账号、地区、产品、权限和应用审批 |
| 华为 → Strava → Strava 官方 MCP | 可评估的独立使用方案；按官方当前支持的客户端与订阅要求接入 |

普通 Strava API 的 AI／MCP 限制与官方 MCP 的授权是两套规则。不能把普通 API 数据装进自建 MCP，也不能依赖 Intervals.icu 转发 Strava 源数据。依据与链接见[路线核对](docs/native-sync.md)。

## 数据如何解释

配速差异是两次运动的描述性比较；路线、天气、强度等还没有控制，不能自动等同于体能进步。平台的训练负荷也不是身体恢复结论。恢复讨论需要看实际可用的连续观测；缺失值保持缺失，不补零。华为原生连接不保证每日 HRV，运动后的心率恢复也需要停止运动后的采样。

云端记录只按需读取，不写入本地健康数据库；返回上下文包含读取时间和摘要用于核对。agent 客户端如果使用云端模型，工具结果可能发给该模型。具体字段、来源和时间含义见[agent 接口约定](docs/agent-contract.md)。

## 历史副本导入

0.1 的本地源 JSON、SQLite、来源追溯及归档 MCP 保留，用于历史补录与兼容性检查。它们不是日常刷新前提，见[历史副本操作](docs/huawei-onboarding.md)。归档示例全为虚构数据：

```powershell
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo import-huawei examples/huawei-export-synthetic
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo coverage
```

## 开发与开源

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,live,dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
```

独立实现，MIT 许可证。原生 API 与档案导入各有测试，CI 覆盖 Windows／Linux 和 Python 3.11／3.12／3.13。参考来源与许可见 [research.md](docs/research.md)、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；验证范围见 [validation.md](docs/validation.md)。
