# 华为数据获取与首轮验收

适用场景：中国大陆华为账号、其他品牌安卓手机。核对日期：2026-10-27。

## 获取第一份数据

1. 在华为运动健康中确认设备已完成同步；检查隐私管理中的云同步选项，按自己需要开启相关类别。副本能提供哪些记录取决于账号和已同步的数据。
2. 在电脑上打开[华为隐私中心](https://privacy.consumer.huawei.com/tool?lang=zh-cn)，自行完成账号登录和身份验证。
3. 选择“获取您的数据副本”，在可用项目中选择“运动健康”，按页面要求设置包大小和解压密码。
4. 等待华为通知，然后回到官方页面下载到本机。官方说明预计约 7 个工作日准备；在线自助通常提供近一年数据，超过一年可通过官方隐私问题渠道申请指定应用和时间段。
5. 用本机 7-Zip 等工具解密到仓库外的私有目录。密码只在本机解压工具中输入，无需提供给 VitalDock、agent 或 GitHub。

以实际页面和账号中提供的选项为准。入口和等待时间依据[华为官方说明](https://consumer.huawei.com/cn/support/content/zh-cn16044986/)，密码说明见[官方隐私 FAQ](https://consumer.huawei.com/cn/legal/privacy-questions/faq/)。

## 检查与导入

在仓库根目录执行：

```powershell
.\.venv\Scripts\vitaldock.exe inspect "D:/HealthPrivate/huawei-export"
.\.venv\Scripts\vitaldock.exe import-huawei "D:/HealthPrivate/huawei-export" --profile self
.\.venv\Scripts\vitaldock.exe coverage
```

`inspect` 仅读取并返回文件摘要、支持的记录数和结构提示，不写入数据库。确认来源和人员归属后再导入。默认存储在 `%LOCALAPPDATA%/VitalDock`，也可将全局参数 `--vault "D:/HealthPrivate/vitaldock"` 放在子命令之前。

如需遇到任何兼容性提示就停止，使用 `import-huawei ... --strict`。普通导入允许保存已识别数据并报告其他条目，退出码 `2` 表示需要检查报告；退出码 `1` 表示输入或存储失败，标准记录未提交；退出码 `0` 表示本次支持范围内没有提示。

常见提示：

| 提示 | 应对 |
|---|---|
| `invalid_json` | 本地核对原文件和解密结果；不自动删字段修补 |
| `unsupported_sample_key` | 新指标尚未映射，原始文件已保留 |
| `unsupported_unit` | 发现未支持单位，先核对含义 |
| `distance_and_calorie_units_unverified_raw_preserved` | 步数已导入；距离／热量保持原值在源文件中 |
| `hitrack_detail_raw_preserved_not_normalized` | 运动经过时长已导入；轨迹细节留待扩展 |
| `no_supported_records` | 查看文件类型与报告，确认是否选中了运动健康副本 |

## 真实数据验收

首版的格式支持来自官方说明和开源格式参考，测试使用虚构样例。第一份真实副本到位后，在本机完成以下核对，再扩大使用范围：

- 挑选各指标若干日期，与运动健康中对应时间和数值比较；不要只比较全历史总条数。
- 对家庭体脂记录确认人员，多个账号使用不同 profile。
- 核对时区、睡眠跨日、多个设备同时记录的步数和副本缺失日期。
- 查看归一化记录的源 SHA-256 和 JSON 路径，验证能在本地原文定位。
- 对距离／热量单位及 HiTrack 格式建立清楚的映射，再加入新解析规则。
- 只把自己构造的最小复现样例提交公开仓库；不要提交真实导出或截图。

## 官方 API 路线

运动健康开发者服务与华为个人数据副本是两种不同能力。官方提供 REST 以及移动端 SDK；获取运动健康数据的前提包括应用批准的数据范围及用户实际授予的范围。SDK 的授权也不会自动给一段桌面脚本开放云端数据。

后续先在控制台核实个人开发者对 Android／REST 产品的申请条件、正式发布要求和允许读取的指标。已核对的 HarmonyOS 元服务申请文档对个人开发者有应用发布和基础数据范围要求；不能将其直接套用为 Android／REST 的保证。官方“订阅数据”文档明确订阅通知能力不支持个人开发者申请。

目前可以立即做的是发起个人副本申请并运行本地导入。持续同步需取得官方资格和授权后再开发及验收。所有参考链接见 [research.md](research.md)。
