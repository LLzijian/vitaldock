# VitalDock · 个人健康数据坞

**让个人 agent 用得上自己的健康数据。**

VitalDock 将穿戴设备平台的数据保存为可追溯的本地健康记录，向个人 agent 提供有范围限制的查询接口。先从华为运动健康开始，逐步接入其他厂商。

> Local, traceable wearable health data for personal agents. Huawei first.

## 第一版可以做什么

- 从华为个人数据副本导入 JSON 文件、已解密文件夹或未加密 ZIP。
- 识别心率、静息心率、血氧、体重、体脂、睡眠阶段、步数和运动时长。
- 按原始字节保存源 JSON，以 SHA-256 和 JSON 路径追溯每条记录。
- 重复导入不重复存储同一记录；不同数值的记录会分别保留。
- 用 JSON 命令行或只读 MCP 工具按指标、时间和人员查询。
- 对未知结构、无法解析的数值和单位给出明确导入报告。

**当前为 0.1.0：数据副本导入与本地 agent 接口。** 已使用自建虚构样例验证，尚未通过项目所有者的真实华为数据副本验收。华为官方 API 的持续同步方案已完成调研，接入实现安排在取得对应资质和授权之后。

## 为什么从数据副本开始

项目首个使用场景是“中国大陆华为账号＋其他安卓手机”。[华为官方个人数据副本](https://consumer.huawei.com/cn/support/content/zh-cn16044986/)可以通过电脑端隐私中心申请，适合先取回历史数据。官方文档另提供 Health Service Kit 云侧 REST 和 Android SDK 等接入路径；API 需要开发者应用审批和用户授权，不能直接用运动健康账号密码调用。

数据副本用于首批历史数据；经批准的官方 API 用于未来持续同步。两条路径共用数据模型、存储和 agent 接口。详细的[接入操作](docs/huawei-onboarding.md)、[来源核对](docs/research.md)与[产品设计](docs/design.md)放在文档中。

## 安装

需要 Python 3.11 或以上。核心导入和查询不依赖第三方包。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
.\.venv\Scripts\vitaldock.exe --help
```

macOS / Linux 使用 `.venv/bin/python` 和 `.venv/bin/vitaldock`。无需 MCP 时安装 `pip install -e .`。

## 先用虚构样例跑通

以下路径在仓库根目录执行，`examples` 内全部数据均为人为构造：

```powershell
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo inspect examples/huawei-export-synthetic
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo import-huawei examples/huawei-export-synthetic
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo coverage
.\.venv\Scripts\vitaldock.exe --vault .vitaldock/demo query --subject self --metric heart_rate --since 2026-10-01T00:00:00+08:00 --until 2026-11-01T00:00:00+08:00
```

示例的运动文件包含尚未核实单位的字段，所以导入会返回 `needs_review` 和退出码 `2`；已识别的记录仍会保存，未识别字段保留在源 JSON 中。这是有提示的部分导入。`--strict` 则会在任何提示出现时回滚本次全部记录。

## 导入自己的数据

1. 在华为运动健康中，将手表／手环数据同步到手机，并确认需要的云同步已开启。
2. 自己登录[华为隐私中心](https://privacy.consumer.huawei.com/tool?lang=zh-cn)，选择“获取您的数据副本”，勾选“运动健康”。
3. 下载后在本机解密，再运行下面的命令。完整步骤见[华为接入指南](docs/huawei-onboarding.md)。

```powershell
.\.venv\Scripts\vitaldock.exe inspect "D:/HealthPrivate/huawei-export"
.\.venv\Scripts\vitaldock.exe import-huawei "D:/HealthPrivate/huawei-export" --profile self
.\.venv\Scripts\vitaldock.exe coverage
```

默认数据目录为 Windows 的 `%LOCALAPPDATA%/VitalDock`，macOS / Linux 的 `~/.local/share/vitaldock`；真实数据建议使用仓库以外的独立目录。多个华为账号应使用不同 `--profile`。导出中明确的家庭成员标识会转换为独立的人员标识；没有标识的记录归入当前 profile，导入者应先确认属于谁。

## 连接个人 agent

MCP 是让 agent 调用外部工具的通用协议。VitalDock 通过本地标准输入输出连接，不启动网络端口。安装可选 MCP 依赖后，在 agent 支持的 MCP 配置中加入以下启动项，并替换成自己的绝对路径：

```json
{
  "mcpServers": {
    "vitaldock": {
      "command": "D:/path/to/vitaldock/.venv/Scripts/python.exe",
      "args": [
        "-m", "vitaldock", "--vault", "D:/HealthPrivate/vitaldock",
        "mcp", "--subject", "self", "--metrics", "heart_rate", "steps", "sleep_stage"
      ]
    }
  }
}
```

`--subject` 必须为 `coverage` 中的准确人员标识；`--metrics` 明确授予该 agent 可访问的指标。工具为 `health_coverage`、`health_query` 和 `health_provenance`。查询要求起止时间，每次最多 500 条，支持继续分页。配置格式由使用的 agent 客户端决定；其他客户端也可使用相同的进程启动参数。

数据在本地存储，但 agent 客户端可能将查询结果发送给远端模型；请按实际使用范围配置指标。接口细节、返回示例和时间语义见[agent 使用约定](docs/agent-contract.md)。

## 数据含义

| 指标 | 单位／含义 | 当前处理 |
|---|---|---|
| `heart_rate` / `resting_heart_rate` | bpm | 保留原始采样时间 |
| `oxygen_saturation` | % | 不自动猜测比例换算 |
| `body_weight` / `body_fat` | kg / % | 分开保存，有哪项导入哪项 |
| `sleep_stage` | light / deep / rem / awake / nap | 保留原始阶段区间 |
| `steps` | count | 同一来源区间内的条目求和 |
| `workout_duration` | s | 运动起止时间差，属于经过时长 |

距离、热量的原始单位及 HiTrack 细节将在真实副本核对后扩展；目前源文件完整保留，报告会列明。未知数据不补零。查询按记录**开始时间**落在 `[since, until)` 内筛选，不把区间总量切分成每天的值，不合并可能重叠的设备来源。覆盖范围表示观察到的首末时间，不表示期间没有缺失。

## 开发与开源

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,dev]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check .
```

CI 在 Windows / Linux、Python 3.11 / 3.12 / 3.13 下执行核心和真实 MCP 进程通信测试。可选 MCP 依赖限制为官方 SDK 1.x，以保持已验证的接口；SDK 2.x 迁移单独验收。

独立仓库，MIT 许可证。数据格式参考来源、固定版本和许可证见 [research.md](docs/research.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，数据保护约定见 [SECURITY.md](SECURITY.md)。
