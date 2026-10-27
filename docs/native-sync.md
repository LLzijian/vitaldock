# 原生同步与按需读取方案

核对日期：2026-10-27。目标是用户告诉 agent“刚跑完”，agent 即时取回新运动、历史对照和恢复背景。

从注册开始的操作见[完整教程](intervals-setup.md)，当前四个 MCP 工具及 JSON／Python 接口见[agent 调用说明](agent-api.md)。

## 当前选择

**华为手表／手环 → 手机运动健康 → Intervals.icu 原生华为连接 → VitalDock API 查询 → 个人 agent。**

Intervals.icu 已正式提供华为原生接入，不需要 Strava 或 Health Sync 作为中转。原生授权承接厂商的上传与通知，VitalDock 负责每次对话时获取最新可用数据，以及组织比较所需的证据。已有华为连接的用户可以继续完成本机 API key 配置和本人数据验收。

这条路线把“设备上传”和“agent 读取”分开：手表需要先把数据同步到手机和云端；一旦 Intervals.icu 收到，agent 随时可读。每次调用 API 都是一次刷新，但无法承诺在手表尚未上传时凭空获得记录。平台原生说明称运动上传后的通知通常可在数秒内到达；这不是整条设备链路的时延保证。

依据：[官方华为接入页面](https://www.intervals.icu/integrations/huawei/)、[维护者原生接入公告](https://forum.intervals.icu/t/huawei-support-available/120529)。

## 三种方案比较

| 方案 | 能力与接入条件 | 本项目决策 |
|---|---|---|
| 华为原生连接到 Intervals.icu，个人 API key 读取 | 已有原生运动和健康资料；个人 API 可直接使用，开放端点含运动、时间序列和 wellness | 当前实施路线 |
| 自建华为开发者应用，调用 Health Service Kit | 建立应用、配置身份和回调、申请权限、用户 OAuth 授权；云侧与移动端条件需分别核实 | 长期独立直连，先取得对应审批及真实响应 |
| 华为同步 Strava，使用 Strava 官方 MCP | Strava 当前已提供官方 MCP，存在订阅和客户端支持条件；普通开发者 API 不等同于官方 MCP | 独立备选，不在 VitalDock 转发 Strava API 数据 |

个人 API key 访问本人 Intervals.icu 数据时，不需要创建 OAuth 应用。面向多个用户的产品使用 OAuth，申请 `ACTIVITY:READ,WELLNESS:READ` 等实际需要的只读范围；创建后须先获批才能开始授权流程。依据：[官方 API 指南](https://forum.intervals.icu/t/api-access-to-intervals-icu/609)、[OAuth 与 PKCE 说明](https://forum.intervals.icu/t/intervals-icu-oauth-support/2759)。

Strava 的 2026 API Policy 将普通 API 的 AI／MCP 接口与其官方 MCP 分开：第 3.5 节描述官方 MCP，第 5.3、5.16 节限制普通 API 的相关用途。官方 2026-09-18 FAQ 说明先与 Anthropic／Claude 接入，具体客户端以实际支持为准。Intervals.icu 也明确 Strava 来源不通过其 API 提供完整数据。因此“华为 → Strava → Intervals.icu → 自建 agent”不作为本项目方案。依据：[当前 API Policy](https://www.strava.com/legal/api_policy)、[官方 MCP FAQ](https://support.strava.com/en-us/articles/15401526-strava-api-and-mcp-faq)。

## 一次性设置

1. 在 Intervals.icu 设置中连接华为，并在手机运动健康确认 Health Service Kit 开启。已经连接则跳过这一步。
2. 在 Intervals.icu 设置底部 Developer Settings 获取个人 API key。
3. 本机运行 `vitaldock connect-intervals`，隐藏输入 key，程序验证本人读取权限后存入系统凭据库。不要把 key 发到对话、写入参数或公开配置。
4. 在个人 agent 中启动 `vitaldock mcp-live --wellness --streams`。同一系统用户读取凭据；工具只提供 GET，固定本人账号和 HUAWEI 来源。
5. 跑一次短运动，确认手机同步后能在 Intervals.icu 看见，再告诉 agent“刚跑完”。对照两边距离、时间、配速和心率，即完成首个真实闭环。

## Agent 的一次调用

工具 `running_context(day, completed_after, history_days=28)`：

1. 查询本人近期活动，过滤来源为 `HUAWEI` 的 Run／TrailRun／VirtualRun。
2. 使用开始时间加经过时长确认运动已完成，且完成时间晚于对话给定的下限。
3. 找到最近的同类型、距离相差不超过 20% 的历史记录，给出两次配速／心率等差值。这个规则用于挑选对照，不代表路线与强度已相同。
4. 按授权读取最近的每日 wellness 数据，区分今天、此前有值的日期、缺失项和最新观测日期。
5. 按授权读取所选活动的心率、速度等采样序列，限制展示点数，不返回 GPS。
6. 无新运动时返回 `awaiting_upstream_sync`，不替换成旧记录；调用者可以在本人完成手机同步后再次查询。

不在一次调用内无限轮询，也不悄悄增加后台监控。API 限流时返回 `Retry-After`；可选 wellness 查询失败时仍返回已取得的跑步，并说明恢复资料暂时不可用。

## 讨论跑步与恢复的证据

“这次跑得怎么样”看本次距离、经过／运动时间、配速、心率、爬升和序列形态。“比上次是否进步”先说明比较条件与两次差异，再考虑路线、天气、计划强度、停顿及多次表现；单次更快不自动代表体能改变。

“恢复如何”至少区分两件事：运动后的心率回落需要停止运动后的记录；近期恢复背景可以看睡眠、静息心率、已有 HRV、主观疲劳和训练负荷。没有相应数据时明确缺失。维护者说明华为原生接口目前不保证每日汇总 HRV；不能因为平台有 HRV 字段就声称华为一定提供它。

0.2 返回这些可核对的观测和算术差异，交由 agent 结合用户感受交流，不生成未经验证的“恢复百分数”。

## 华为开放控制台的独立路线

如需摆脱第三方训练平台，可创建自己的华为开发者应用：核实中国大陆和 Android／REST 产品资格 → 建立应用与客户端身份 → 申请运动及所需健康数据只读权限 → 配置官方回调 → 用户 OAuth 授权 → 读运动记录及对应采样数据。

创建项目并生成 Client ID／Secret 不等于运动健康权限已获批。审批、接口域名、数据范围、历史窗口和时间单位都需要按实际产品核对。已有[华为官方 Android 示例](https://github.com/HMS-Core/hms-health-demo-java)及[运动健康服务入口](https://developer.huawei.com/consumer/en/hms/huaweihealth/)可参考。官方[订阅文档](https://developer.huawei.com/consumer/cn/doc/hmscore-guides/subscription-0000001078496860)要求企业账号，个人版不能先假设可收到它的推送。

该路线保留为独立连接器；当前使用现成的华为原生连接，优先完成用户实际可用的跑后对话。
