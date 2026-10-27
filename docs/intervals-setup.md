# 从注册 Intervals.icu 到让 agent 读取华为数据

这份教程走完整条链路：注册账号 → 连接华为 → 获取个人 API key → 本机配置 → 验证读取 → 接入 agent。已经完成的步骤可以跳过。

核对日期：2026-10-27。来源为 [Intervals.icu 官方华为指南](https://www.intervals.icu/integrations/huawei/)、[个人 API 指南](https://forum.intervals.icu/t/api-access-to-intervals-icu/609)与[开放 API 说明](https://www.intervals.icu/features/open-api/)。

## 1. 注册 Intervals.icu 账号

1. 打开 [Intervals.icu 官网](https://www.intervals.icu/)，点击 **Sign Up Free**；也可直接进入[注册页面](https://intervals.icu/signup)。
2. 使用页面当前提供的方式创建自己的账号。若页面要求确认邮箱或其他验证，按提示完成。
3. 登录后完成页面要求的基本资料，进入自己的训练日历。
4. 检查页面日期与所在地一致。后续工具的 `day` 使用本人当地日期；中国大陆例子采用北京时间 `+08:00`。

官方提供免费账号；个人 API key 访问自己的数据不需要创建多人 OAuth 应用。注册和华为授权都由本人在官方页面完成。

## 2. 连接华为运动健康

1. 打开 [Settings → Connections](https://intervals.icu/settings/connections?services=huawei)。
2. 找到 **HUAWEI Health**，点击 **Connect**。
3. 在华为官方页面登录自己的华为账号，确认要开放的数据范围。
4. 按需开启已完成运动和 wellness 健康数据的下载。只读取数据时，无需开启向手表上传计划训练。
5. 按[官方华为说明](https://www.intervals.icu/integrations/huawei/)检查手机运动健康中的 **Me／我的 → 3rd Party Services／第三方服务 → Health Service Kit** 已连接。不同地区和版本的文字可能不同，以实际界面为准。
6. 让手表／手环完成到手机的同步，再在 Intervals.icu 日历中查看是否有记录。

已完成的活动和健康资料通过华为原生连接进入平台。历史数据可在 HUAWEI Health 卡片中按需使用 **Download Old Data**；官方说明提供最多一年的回查范围。账号、地区和数据权限以实际授权结果为准。

## 3. 获取个人 API key

1. 打开 [Settings](https://intervals.icu/settings)。
2. 滚动到接近底部，找到 **Developer Settings（开发者设置）**。
3. 找到 **API Key**，按页面提示生成或显示密钥，然后复制。

个人 key 的 API 鉴权用户名固定为 `API_KEY`，密码为刚生成的 key。VitalDock 会完成鉴权，agent 无需处理密钥。访问本人账号使用平台支持的 athlete `0`，不用另找自己的运动员 ID。

API key 只交给本机配置程序或受控的进程环境，不放进聊天、截图、命令参数或 Git。若密钥丢失或泄露，在 Intervals.icu 重新生成，然后重新运行本机配置程序。

## 4. 安装 VitalDock 并保存密钥

Windows PowerShell，从准备存放项目的目录执行：

```powershell
git clone https://github.com/LLzijian/vitaldock.git
Set-Location vitaldock
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,live]"
.\.venv\Scripts\vitaldock.exe connect-intervals
```

已安装的项目可直接执行最后一条命令，也可以在文件资源管理器中双击项目根目录的 `connect-intervals.cmd`。

出现以下提示时，粘贴 key 并回车：

```text
Intervals.icu personal API key (hidden):
```

输入不会显示。程序先验证本人账号可读取，再把 key 保存到 Windows 凭据管理器。成功返回：

```json
{
  "status": "connected",
  "account": "authenticated_self",
  "credential_storage": "native_os_store",
  "key_returned": false
}
```

macOS／Linux 把命令中的 `.venv/Scripts` 换成 `.venv/bin`。macOS 使用 Keychain；Linux 需要受支持的系统密钥服务。没有系统密钥服务的环境可由自己的密钥管理器向进程注入 `VITALDOCK_INTERVALS_API_KEY`；程序不会回退到明文文件。

运行配置程序和 agent 服务时应使用同一操作系统用户，才能访问同一份系统凭据。

## 5. 检查连接与已同步的数据

下面使用示例日期；实际操作时换成本人当天的当地日期：

```powershell
.\.venv\Scripts\vitaldock.exe check-connection --day 2026-10-27
.\.venv\Scripts\vitaldock.exe recent-activities --day 2026-10-27 --history-days 28 --limit 5
.\.venv\Scripts\vitaldock.exe wellness-context --day 2026-10-27 --history-days 28
```

- `check-connection` 返回 `connected` 表示 API 读取成功；不会输出密钥或具体健康数值。
- `recent-activities` 返回华为来源的跑步、通用训练等近期活动。
- `wellness-context` 独立返回睡眠、静息心率和实际可用的 HRV 等观测，不要求先有跑步记录。

只有 `Workout` 时，按通用训练展示；缺少距离就不会编造配速。暂时没有活动不代表密钥失效，先检查手机同步、平台日历和时间范围。

## 6. 接入个人 agent

优先使用 MCP。支持 `mcpServers` 配置的客户端可参考 [mcp-client.json](../examples/mcp-client.json)，将 `command` 改成自己虚拟环境 Python 的绝对路径。Codex 使用 [codex-mcp.toml](../examples/codex-mcp.toml)，格式依据 [OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

保存配置后按客户端要求重新加载 MCP 服务，确认出现以下工具：

| 工具 | 用途 |
|---|---|
| `connection_status` | 检查连接与允许读取的类别 |
| `recent_activities` | 读取近期华为跑步和通用训练 |
| `wellness_context` | 读取近期恢复观测；开启 `--wellness` 时提供 |
| `running_context` | 刚跑完时获取本次、历史对照和已授权恢复资料 |

不支持 MCP 的 agent 可以调用相同功能的 JSON 命令，或通过 Python 的 `AgentAPI` 使用。参数、状态、错误和示例见 [agent 调用接口](agent-api.md)。

## 7. 日常使用

完成一次性设置后，直接告诉 agent：

> 我刚跑完，看看这次和上次相近距离的跑步有什么变化。

或者：

> 看看我最近一周的训练，再结合睡眠和静息心率聊聊恢复情况。

agent 每次重新读取 API。若手表数据尚未上传，跑后工具会返回 `awaiting_upstream_sync`；确认手机同步完成后再查询。每次读到的都是平台当前可用数据，不保证手表尚未上传的记录已经存在。

## 常见问题

| 情况 | 处理 |
|---|---|
| 找不到 Developer Settings | 确认已登录，打开完整设置页并滚动到底部 |
| `authentication_failed` | 检查复制的 key 是否完整；重新生成后需再次本机配置 |
| `credential_not_configured`／`credential_unavailable` | 以运行 agent 的同一系统用户执行 `connect-intervals` |
| `access_denied`／`network_unavailable` | 核对账号授权与网络，先确认官网可正常访问 |
| `rate_limited` | 按返回的 `retry_after_seconds` 等待，不连续重试 |
| 有睡眠记录但没有跑步 | 先检查平台运动记录；已同步的通用训练也可通过 `recent_activities` 读取 |
| 没有 HRV | 以接口实际返回为准，缺失不会补零；华为原生连接不保证每日 HRV |
